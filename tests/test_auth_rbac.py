"""Unit tests for the local auth/RBAC contract foundation (WP-04l / T-04-12).

Covers, for the bounded authorisation decision over the merged WP-04 control-plane
surfaces:

- allow / deny / needs-approval outcomes from explicit caller-supplied grants,
- default-deny when no grant matches (fail closed),
- fail-closed request validation (malformed actor, role, action, resource, policy),
- unknown role / unknown action / unknown-or-mismatched resource type,
- cross-project (resource-scope) mismatch,
- catch-all/wildcard scope rejected unless explicitly bounded,
- duplicate contradictory grants rejected,
- optimistic-concurrency version binding (match allows, stale/missing/malformed
  fail closed),
- malformed / forbidden authority facts,
- deterministic serialisation, stable reason codes, and exact audit binding,
- the action catalogue's binding to the merged OpenAPI operation identifiers, and
- purity / totality: no I/O, no mutation, and stable repeated output.
"""

import unittest

from auto_bioinfo.control_plane import auth_rbac as rbac
from auto_bioinfo.control_plane.auth_rbac import (
    ACTIONS,
    CODE_ALLOW,
    CODE_CONTRADICTORY_GRANT,
    CODE_DENY_EXPLICIT,
    CODE_FORBIDDEN_AUTHORITY,
    CODE_MALFORMED_ACTION,
    CODE_MALFORMED_ACTOR,
    CODE_MALFORMED_AUTHORITY,
    CODE_MALFORMED_POLICY,
    CODE_MALFORMED_REQUEST,
    CODE_MALFORMED_RESOURCE,
    CODE_MALFORMED_ROLE,
    CODE_MISSING_EXPECTED_VERSION,
    CODE_NEEDS_APPROVAL,
    CODE_NO_MATCHING_GRANT,
    CODE_RESOURCE_MISMATCH,
    CODE_STALE_VERSION,
    CODE_UNKNOWN_ACTION,
    CODE_UNKNOWN_RESOURCE,
    CODE_UNKNOWN_ROLE,
    CODE_WILDCARD_SCOPE,
    EFFECT_ALLOW,
    EFFECT_DENY,
    EFFECT_NEEDS_APPROVAL,
    REASON_CODES,
    RESOURCE_TYPES,
    STATUS_ALLOW,
    STATUS_DENY,
    STATUS_INVALID,
    STATUS_NEEDS_APPROVAL,
    STATUS_VERSION_CONFLICT,
    STATUSES,
    WILDCARD,
    AccessRequest,
    AuthorizationPolicy,
    Permission,
    Principal,
    ResourceRef,
    Role,
    actions_for_resource_type,
    authorize,
)
from auto_bioinfo.control_plane.openapi_contract import IMPLEMENTED_OPERATIONS

PROJECT = "proj-001"
OTHER_PROJECT = "proj-002"


def _request(action="project.get", *, resource_type="project", project=PROJECT, roles=("viewer",), actor="alice", expected_version=None, authority=None):
    return AccessRequest(
        principal=Principal(actor_id=actor, roles=tuple(roles), authority=authority),
        action=action,
        resource=ResourceRef(resource_type=resource_type, project=project),
        expected_policy_version=expected_version,
    )


def _policy(*roles, version=None):
    return AuthorizationPolicy(roles=tuple(roles), version=version)


def _role(name, *permissions):
    return Role(name=name, permissions=tuple(permissions))


class AuthRbacAllowDenyApprovalTest(unittest.TestCase):
    """Core allow / deny / needs-approval outcomes from explicit grants."""

    def test_allow_when_role_grants_action_on_project(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(), policy=policy)
        self.assertEqual(decision.status, STATUS_ALLOW)
        self.assertEqual(decision.reason_code, CODE_ALLOW)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.binding["matched_effects"], [EFFECT_ALLOW])
        self.assertEqual(decision.binding["actor_id"], "alice")
        self.assertEqual(decision.binding["project"], PROJECT)

    def test_explicit_deny_grant_refuses(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_DENY, PROJECT)))
        decision = authorize(_request(), policy=policy)
        self.assertEqual(decision.status, STATUS_DENY)
        self.assertEqual(decision.reason_code, CODE_DENY_EXPLICIT)
        self.assertFalse(decision.allowed)

    def test_needs_approval_grant(self):
        policy = _policy(_role("editor", Permission("operation.cancel", EFFECT_NEEDS_APPROVAL, PROJECT)))
        decision = authorize(_request(action="operation.cancel", resource_type="operation", roles=("editor",)), policy=policy)
        self.assertEqual(decision.status, STATUS_NEEDS_APPROVAL)
        self.assertEqual(decision.reason_code, CODE_NEEDS_APPROVAL)

    def test_default_deny_when_no_grant_matches(self):
        policy = _policy(_role("viewer", Permission("project.list", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(action="project.get"), policy=policy)
        self.assertEqual(decision.status, STATUS_DENY)
        self.assertEqual(decision.reason_code, CODE_NO_MATCHING_GRANT)
        self.assertEqual(decision.binding["matched_effects"], [])

    def test_actor_with_no_roles_is_default_denied(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(roles=()), policy=policy)
        self.assertEqual(decision.reason_code, CODE_NO_MATCHING_GRANT)

    def test_grant_across_two_roles_allows(self):
        policy = _policy(
            _role("a", Permission("project.list", EFFECT_ALLOW, PROJECT)),
            _role("b", Permission("project.get", EFFECT_ALLOW, PROJECT)),
        )
        decision = authorize(_request(roles=("a", "b")), policy=policy)
        self.assertEqual(decision.status, STATUS_ALLOW)


class AuthRbacScopeTest(unittest.TestCase):
    """Resource-scope (cross-project) and resource-type handling."""

    def test_cross_project_grant_does_not_match(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, OTHER_PROJECT)))
        decision = authorize(_request(project=PROJECT), policy=policy)
        self.assertEqual(decision.reason_code, CODE_NO_MATCHING_GRANT)

    def test_bounded_wildcard_scope_allows_any_project(self):
        policy = _policy(_role("admin", Permission("project.get", EFFECT_ALLOW, WILDCARD, scope_is_wildcard=True)))
        for project in (PROJECT, OTHER_PROJECT, "proj-999"):
            decision = authorize(_request(project=project, roles=("admin",)), policy=policy)
            self.assertEqual(decision.status, STATUS_ALLOW, project)

    def test_unbounded_wildcard_scope_is_rejected(self):
        policy = _policy(_role("admin", Permission("project.get", EFFECT_ALLOW, WILDCARD)))
        decision = authorize(_request(roles=("admin",)), policy=policy)
        self.assertEqual(decision.status, STATUS_INVALID)
        self.assertEqual(decision.reason_code, CODE_WILDCARD_SCOPE)

    def test_resource_type_mismatch_for_action(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(action="project.get", resource_type="operation"), policy=policy)
        self.assertEqual(decision.reason_code, CODE_RESOURCE_MISMATCH)

    def test_unknown_resource_type(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(resource_type="planet"), policy=policy)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_RESOURCE)

    def test_request_project_may_not_be_wildcard(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(project=WILDCARD), policy=policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_RESOURCE)


class AuthRbacMalformedRequestTest(unittest.TestCase):
    """Fail-closed validation of malformed/ambiguous request facts."""

    def setUp(self):
        self.policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))

    def test_blank_actor_id(self):
        decision = authorize(_request(actor=""), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_ACTOR)
        self.assertEqual(decision.status, STATUS_INVALID)

    def test_actor_with_spaces_is_malformed(self):
        decision = authorize(_request(actor="alice smith"), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_ACTOR)

    def test_blank_role_name_is_malformed(self):
        decision = authorize(_request(roles=("",)), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_ROLE)

    def test_blank_action_is_malformed(self):
        decision = authorize(_request(action=""), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_ACTION)

    def test_unknown_action(self):
        decision = authorize(_request(action="project.nuke"), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_ACTION)

    def test_unknown_assigned_role(self):
        decision = authorize(_request(roles=("ghost",)), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_ROLE)

    def test_malformed_principal_type(self):
        request = AccessRequest(principal="alice", action="project.get", resource=ResourceRef("project", PROJECT))
        decision = authorize(request, policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_ACTOR)

    def test_malformed_resource_type_object(self):
        request = AccessRequest(principal=Principal("alice", ("viewer",)), action="project.get", resource="proj")
        decision = authorize(request, policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_RESOURCE)

    def test_malformed_top_level_request_object_is_bounded_invalid(self):
        # A non-AccessRequest top-level request must fail closed to a bounded,
        # non-allowing decision rather than raising while reading request facts.
        decision = authorize(object(), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)
        self.assertEqual(decision.status, STATUS_INVALID)
        self.assertIsNone(decision.binding["action"])
        self.assertIsNone(decision.binding["actor_id"])
        self.assertEqual(decision.binding["matched_effects"], [])

    def test_none_request_is_bounded_invalid(self):
        decision = authorize(None, policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)
        self.assertEqual(decision.status, STATUS_INVALID)


class AuthRbacPolicyValidationTest(unittest.TestCase):
    """Fail-closed validation of the policy catalogue itself."""

    def test_duplicate_role_name_in_policy(self):
        policy = _policy(
            _role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)),
            _role("viewer", Permission("project.list", EFFECT_ALLOW, PROJECT)),
        )
        decision = authorize(_request(), policy=policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_POLICY)

    def test_unknown_action_in_permission(self):
        policy = _policy(_role("viewer", Permission("bogus.action", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(), policy=policy)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_ACTION)

    def test_malformed_policy_type(self):
        decision = authorize(_request(), policy="not-a-policy")
        self.assertEqual(decision.reason_code, CODE_MALFORMED_POLICY)

    def test_contradictory_grants_rejected(self):
        policy = _policy(
            _role("a", Permission("project.get", EFFECT_ALLOW, PROJECT)),
            _role("b", Permission("project.get", EFFECT_DENY, PROJECT)),
        )
        decision = authorize(_request(roles=("a", "b")), policy=policy)
        self.assertEqual(decision.status, STATUS_INVALID)
        self.assertEqual(decision.reason_code, CODE_CONTRADICTORY_GRANT)
        self.assertEqual(decision.binding["matched_effects"], sorted([EFFECT_ALLOW, EFFECT_DENY]))

    def test_duplicate_identical_grant_is_not_contradictory(self):
        policy = _policy(
            _role("a", Permission("project.get", EFFECT_ALLOW, PROJECT)),
            _role("b", Permission("project.get", EFFECT_ALLOW, PROJECT)),
        )
        decision = authorize(_request(roles=("a", "b")), policy=policy)
        self.assertEqual(decision.status, STATUS_ALLOW)


class AuthRbacAuthorityFlagTest(unittest.TestCase):
    """Forbidden / malformed authority facts fail closed."""

    def setUp(self):
        self.policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))

    def test_forbidden_flag_truthy_fails_closed(self):
        for flag in ("bypasses_rbac", "is_superuser", "escalates_privilege", "grants_all"):
            decision = authorize(_request(authority={flag: True}), policy=self.policy)
            self.assertEqual(decision.reason_code, CODE_FORBIDDEN_AUTHORITY, flag)
            self.assertEqual(decision.status, STATUS_INVALID, flag)

    def test_forbidden_flag_any_truthy_value_fails_closed(self):
        decision = authorize(_request(authority={"is_superuser": 1}), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_FORBIDDEN_AUTHORITY)

    def test_forbidden_flag_falsey_is_accepted(self):
        decision = authorize(_request(authority={"is_superuser": False}), policy=self.policy)
        self.assertEqual(decision.status, STATUS_ALLOW)
        self.assertIn("is_superuser", decision.binding["authority_keys"])

    def test_non_mapping_authority_is_malformed(self):
        decision = authorize(_request(authority=["is_superuser"]), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_AUTHORITY)

    def test_non_string_authority_key_is_malformed(self):
        decision = authorize(_request(authority={1: True}), policy=self.policy)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_AUTHORITY)


class AuthRbacVersionBindingTest(unittest.TestCase):
    """Optimistic-concurrency version binding (only when current_version supplied)."""

    def setUp(self):
        self.policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)), version=5)

    def test_matching_version_allows(self):
        decision = authorize(_request(expected_version=5), policy=self.policy, current_version=5)
        self.assertEqual(decision.status, STATUS_ALLOW)

    def test_stale_version_fails_closed(self):
        decision = authorize(_request(expected_version=4), policy=self.policy, current_version=5)
        self.assertEqual(decision.status, STATUS_VERSION_CONFLICT)
        self.assertEqual(decision.reason_code, CODE_STALE_VERSION)

    def test_missing_expected_version_when_current_supplied(self):
        decision = authorize(_request(expected_version=None), policy=self.policy, current_version=5)
        self.assertEqual(decision.reason_code, CODE_MISSING_EXPECTED_VERSION)

    def test_no_version_check_when_current_not_supplied(self):
        decision = authorize(_request(expected_version=99), policy=self.policy)
        self.assertEqual(decision.status, STATUS_ALLOW)

    def test_version_binding_recorded(self):
        decision = authorize(_request(expected_version=5), policy=self.policy, current_version=5)
        self.assertEqual(decision.binding["expected_policy_version"], 5)
        self.assertEqual(decision.binding["current_version"], 5)
        self.assertEqual(decision.binding["policy_version"], 5)


class AuthRbacBindingAndSerializationTest(unittest.TestCase):
    """Deterministic serialisation, stable reason codes, exact audit binding."""

    def test_to_dict_is_deterministic_and_complete(self):
        policy = _policy(_role("viewer", Permission("operation.cancel", EFFECT_ALLOW, PROJECT)))
        decision = authorize(_request(action="operation.cancel", resource_type="operation"), policy=policy)
        d1 = decision.to_dict()
        d2 = decision.to_dict()
        self.assertEqual(d1, d2)
        self.assertEqual(
            set(d1.keys()),
            {"status", "reason_code", "message", "allowed", "binding"},
        )
        self.assertEqual(d1["binding"]["openapi_operation"], "cancelOperation")
        self.assertEqual(d1["binding"]["contract"], ACTIONS["operation.cancel"]["contract"])

    def test_assigned_roles_binding_is_sorted(self):
        policy = _policy(
            _role("zed", Permission("project.get", EFFECT_ALLOW, PROJECT)),
            _role("abe", Permission("project.list", EFFECT_ALLOW, PROJECT)),
        )
        decision = authorize(_request(roles=("zed", "abe")), policy=policy)
        self.assertEqual(decision.binding["assigned_roles"], ["abe", "zed"])

    def test_every_reason_code_maps_to_a_status(self):
        for code in REASON_CODES:
            self.assertIn(rbac._CODE_STATUS[code], STATUSES, code)

    def test_status_set_is_bounded(self):
        self.assertEqual(len(STATUSES), len(set(STATUSES)))
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))


class AuthRbacContractBindingTest(unittest.TestCase):
    """The action catalogue binds to the merged control-plane / OpenAPI surfaces."""

    def test_declared_openapi_operations_exist(self):
        for meta in ACTIONS.values():
            op = meta["openapi_operation"]
            if op is not None:
                self.assertIn(op, IMPLEMENTED_OPERATIONS, op)

    def test_resource_types_derived_from_actions(self):
        self.assertEqual(RESOURCE_TYPES, frozenset(m["resource_type"] for m in ACTIONS.values()))

    def test_actions_for_resource_type(self):
        project_actions = actions_for_resource_type("project")
        self.assertIn("project.get", project_actions)
        self.assertIn("project.create", project_actions)
        self.assertNotIn("operation.cancel", project_actions)

    def test_every_action_has_a_contract_path(self):
        for name, meta in ACTIONS.items():
            self.assertIsInstance(meta["contract"], str, name)
            self.assertIn(".", meta["contract"], name)


class AuthRbacPurityTest(unittest.TestCase):
    """Purity / totality: no mutation and stable repeated output."""

    def test_repeated_evaluation_is_stable(self):
        policy = _policy(_role("viewer", Permission("project.get", EFFECT_ALLOW, PROJECT)))
        request = _request()
        first = authorize(request, policy=policy).to_dict()
        second = authorize(request, policy=policy).to_dict()
        self.assertEqual(first, second)

    def test_inputs_are_not_mutated(self):
        perm = Permission("project.get", EFFECT_ALLOW, PROJECT)
        role = _role("viewer", perm)
        policy = _policy(role)
        principal = Principal("alice", ("viewer",), authority={"note": "x"})
        request = AccessRequest(principal=principal, action="project.get", resource=ResourceRef("project", PROJECT))
        authorize(request, policy=policy)
        # Frozen dataclasses + original containers are unchanged.
        self.assertEqual(principal.roles, ("viewer",))
        self.assertEqual(policy.roles, (role,))
        self.assertEqual(role.permissions, (perm,))
        self.assertEqual(dict(principal.authority), {"note": "x"})

    def test_permission_matches_predicate(self):
        perm = Permission("project.get", EFFECT_ALLOW, PROJECT)
        self.assertTrue(perm.matches("project.get", PROJECT))
        self.assertFalse(perm.matches("project.get", OTHER_PROJECT))
        self.assertFalse(perm.matches("project.list", PROJECT))


if __name__ == "__main__":
    unittest.main()
