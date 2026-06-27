"""Local auth/RBAC contract foundation (WP-04l / T-04-12).

The smallest deterministic, *local* contract layer the control plane needs so a
future API/CLI can answer one question about an explicit access request — *may
this actor perform this action on this resource, given the facts the caller
supplies?* — **without ever consulting a real identity provider, token system,
credential store, session, OS user, environment, GitHub identity, HTTP
middleware, or deployed endpoint**.

This sits beside the other WP-04 control-plane contracts and is *about* them:
where :func:`auto_bioinfo.control_plane.command_api.evaluate_command_request`
decides whether a *mutating* command may be applied,
:mod:`auto_bioinfo.control_plane.operation_resource` models what the caller
tracks afterwards, :func:`auto_bioinfo.control_plane.cancel_command.evaluate_cancel_request`
decides whether a tracked operation may be cancelled, and
:mod:`auto_bioinfo.control_plane.openapi_contract` describes those shapes, this
module decides — purely, from explicit facts — whether an actor's assigned roles
authorise a bounded *action* over a bounded *resource scope*.  "Authorisation"
here is modelled as a deterministic *policy decision only*, never as real
authentication, credential verification, or privilege change.

Design constraints (WP-04l), mirroring the WP-04g/WP-04h/WP-04j/WP-04k style:

- **Pure and deterministic.** :func:`authorize` and every helper is a total
  function of its explicit in-memory inputs.  There is no I/O whatsoever: no file
  access, no network, no environment inspection, no OS-user/GitHub-identity
  lookup, **no real clock**, no token/secret/session/cookie/certificate parsing,
  no threads, async worker, scheduler, broker, queue, DB, outbox, lock, process
  signal, or command execution side effect.  Inputs are never mutated in place.
- **Fail closed.** Every uncertainty resolves to a *non-allowing* decision.  A
  blank/malformed actor, role, action, or resource; an unknown role or action; a
  catch-all/wildcard permission that is not explicitly bounded; a resource-type
  mismatch; a cross-project scope mismatch; a duplicate *contradictory* grant; a
  malformed policy; a stale/malformed version fact when a version binding is used;
  and any forbidden/malformed authority flag all yield a bounded reason-coded
  decision — never a silent allow and never an unhandled exception.  When no grant
  matches at all, the decision is a *default deny*.
- **Bounded vocabulary.** The decision status is one of exactly five values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  A future HTTP/CLI adapter maps these categories to
  transport responses; callers branch on the machine-readable code, never the
  human message.
- **Bound to existing contracts.** Every authorisable *action* in :data:`ACTIONS`
  names an already-merged pure control-plane entry point (and, where one exists,
  the OpenAPI ``operationId`` from
  :data:`auto_bioinfo.control_plane.openapi_contract.IMPLEMENTED_OPERATIONS`).
  This contract invents no new server behaviour and no new product capability; it
  only describes who may invoke the surfaces that already exist.
- **Exact binding.** Every decision records the actor, the assigned roles, the
  action, the resource type/project, the bound contract / OpenAPI operation, the
  matched grant effects, the versions it considered, and the inspected authority
  keys, so the decision can be audited later.

This module defines a *contract* only.  It does not authenticate anyone, open a
socket, register a route, run a real HTTP server, read or issue a token/secret,
persist anything, enforce middleware, or expand any privilege — those are out of
scope for T-04-12.  It only decides, purely, from the facts it is handed, and an
*allow* decision is a bounded policy *value*, never a real grant of access.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .openapi_contract import IMPLEMENTED_OPERATIONS

# --- Bounds (so an unbounded input cannot exhaust a downstream store) --------
# Actor ids, role names, resource types, and project ids are non-blank single-line
# tokens of visible ASCII, capped to the same bound the sibling contracts use so
# the whole control plane agrees on identifier size.
MAX_IDENTIFIER_LENGTH = 200
# A version's digit count is capped so a pathologically long numeric string is
# rejected as malformed rather than parsed.
MAX_VERSION_DIGITS = 18

# The explicit bounded wildcard token.  A permission may use it for its project
# scope *only* when it also sets ``scope_is_wildcard=True`` (an explicit opt-in);
# any other use of a catch-all scope fails closed.  There is no wildcard *action*:
# an action must name a member of :data:`ACTIONS`.
WILDCARD = "*"

# --- The bounded action catalogue -------------------------------------------
# Every authorisable action names an already-merged pure control-plane entry point
# (``contract``), the bounded resource *type* it acts on (``resource_type``), and
# the OpenAPI ``operationId`` it corresponds to when one exists (``openapi_operation``;
# ``None`` for query/create actions that WP-04k did not surface as HTTP operations).
# This dict is the single source of truth: an action absent here is "unknown".
ACTIONS: dict[str, dict[str, str | None]] = {
    "project.create": {
        "contract": "auto_bioinfo.control_plane.create_project.create_project",
        "resource_type": "project",
        "openapi_operation": None,
    },
    "project.get": {
        "contract": "auto_bioinfo.control_plane.queries.get_project",
        "resource_type": "project",
        "openapi_operation": None,
    },
    "project.list": {
        "contract": "auto_bioinfo.control_plane.queries.list_projects",
        "resource_type": "project",
        "openapi_operation": None,
    },
    "project.timeline": {
        "contract": "auto_bioinfo.control_plane.queries.query_timeline",
        "resource_type": "project",
        "openapi_operation": None,
    },
    "project.blockers": {
        "contract": "auto_bioinfo.control_plane.queries.project_blockers",
        "resource_type": "project",
        "openapi_operation": None,
    },
    "command.admit": {
        "contract": "auto_bioinfo.control_plane.command_api.evaluate_command_request",
        "resource_type": "command",
        "openapi_operation": "admitCommand",
    },
    "operation.get": {
        "contract": "auto_bioinfo.control_plane.operation_resource.project_operation",
        "resource_type": "operation",
        "openapi_operation": "getOperation",
    },
    "operation.cancel": {
        "contract": "auto_bioinfo.control_plane.cancel_command.evaluate_cancel_request",
        "resource_type": "operation",
        "openapi_operation": "cancelOperation",
    },
    "cli.run": {
        "contract": "auto_bioinfo.control_plane.cli_contract.run_cli",
        "resource_type": "cli",
        "openapi_operation": "runCli",
    },
}

# The bounded set of resource types, derived from the action catalogue so the two
# can never drift.  A request's resource type must be a member, and must equal the
# action's declared resource type.
RESOURCE_TYPES: frozenset[str] = frozenset(str(meta["resource_type"]) for meta in ACTIONS.values())

# --- Forbidden authority facts ----------------------------------------------
# This contract has no power to authenticate, escalate privilege, or bypass
# authorisation, so a caller may not assert that it does.  Any of these authority
# flags being truthy is a fail-closed condition: the decision is a *value*, never a
# real grant, and it refuses to pretend otherwise.
FORBIDDEN_AUTHORITY_FLAGS = frozenset(
    {
        "bypasses_rbac",
        "bypass_authorization",
        "skip_authorization",
        "disables_authz",
        "is_superuser",
        "superuser",
        "root",
        "admin_override",
        "grants_all",
        "all_permissions",
        "escalates_privilege",
        "privilege_escalation",
        "impersonate",
        "authenticates",
        "authorizes_real_execution",
        "real_execution_authorized",
        "bypasses_gates",
        "force",
    }
)

# --- Bounded effect vocabulary (what a single grant says) -------------------
EFFECT_ALLOW = "allow"
EFFECT_DENY = "deny"
EFFECT_NEEDS_APPROVAL = "needs_approval"

EFFECTS = (EFFECT_ALLOW, EFFECT_DENY, EFFECT_NEEDS_APPROVAL)

# --- Bounded status vocabulary (the decision's outcome) ---------------------
# ``allow`` is the single proceed outcome; ``needs_approval`` is the conservative
# "not yet" outcome; ``deny`` is a legitimate refusal (an explicit deny grant or a
# default deny when nothing matches); ``version_conflict`` is a stale optimistic-
# concurrency fact; ``invalid`` is a malformed/ambiguous request that fails closed.
STATUS_ALLOW = "allow"
STATUS_DENY = "deny"
STATUS_NEEDS_APPROVAL = "needs_approval"
STATUS_VERSION_CONFLICT = "version_conflict"
STATUS_INVALID = "invalid"

STATUSES = (
    STATUS_ALLOW,
    STATUS_DENY,
    STATUS_NEEDS_APPROVAL,
    STATUS_VERSION_CONFLICT,
    STATUS_INVALID,
)

# --- Stable reason codes ----------------------------------------------------
# Callers branch on these, so they must stay stable.
# allow:
CODE_ALLOW = "RBAC_ALLOW"
# needs_approval:
CODE_NEEDS_APPROVAL = "RBAC_NEEDS_APPROVAL"
# deny (legitimate refusal):
CODE_DENY_EXPLICIT = "RBAC_DENY"
CODE_NO_MATCHING_GRANT = "RBAC_NO_GRANT"
# version_conflict:
CODE_STALE_VERSION = "RBAC_STALE_VERSION"
# invalid (fail closed):
CODE_MALFORMED_ACTOR = "RBAC_MALFORMED_ACTOR"
CODE_MALFORMED_ROLE = "RBAC_MALFORMED_ROLE"
CODE_UNKNOWN_ROLE = "RBAC_UNKNOWN_ROLE"
CODE_MALFORMED_ACTION = "RBAC_MALFORMED_ACTION"
CODE_UNKNOWN_ACTION = "RBAC_UNKNOWN_ACTION"
CODE_MALFORMED_RESOURCE = "RBAC_MALFORMED_RESOURCE"
CODE_UNKNOWN_RESOURCE = "RBAC_UNKNOWN_RESOURCE"
CODE_RESOURCE_MISMATCH = "RBAC_RESOURCE_MISMATCH"
CODE_WILDCARD_SCOPE = "RBAC_WILDCARD_SCOPE"
CODE_MALFORMED_PERMISSION = "RBAC_MALFORMED_PERMISSION"
CODE_MALFORMED_POLICY = "RBAC_MALFORMED_POLICY"
CODE_CONTRADICTORY_GRANT = "RBAC_CONTRADICTORY_GRANT"
CODE_MALFORMED_VERSION = "RBAC_MALFORMED_VERSION"
CODE_MISSING_EXPECTED_VERSION = "RBAC_MISSING_EXPECTED_VERSION"
CODE_MALFORMED_AUTHORITY = "RBAC_MALFORMED_AUTHORITY"
CODE_FORBIDDEN_AUTHORITY = "RBAC_FORBIDDEN_AUTHORITY"

REASON_CODES = (
    CODE_ALLOW,
    CODE_NEEDS_APPROVAL,
    CODE_DENY_EXPLICIT,
    CODE_NO_MATCHING_GRANT,
    CODE_STALE_VERSION,
    CODE_MALFORMED_ACTOR,
    CODE_MALFORMED_ROLE,
    CODE_UNKNOWN_ROLE,
    CODE_MALFORMED_ACTION,
    CODE_UNKNOWN_ACTION,
    CODE_MALFORMED_RESOURCE,
    CODE_UNKNOWN_RESOURCE,
    CODE_RESOURCE_MISMATCH,
    CODE_WILDCARD_SCOPE,
    CODE_MALFORMED_PERMISSION,
    CODE_MALFORMED_POLICY,
    CODE_CONTRADICTORY_GRANT,
    CODE_MALFORMED_VERSION,
    CODE_MISSING_EXPECTED_VERSION,
    CODE_MALFORMED_AUTHORITY,
    CODE_FORBIDDEN_AUTHORITY,
)

# The status each reason code resolves to, so a future adapter can map a category
# to a transport status without re-deriving it from the code.
_CODE_STATUS = {
    CODE_ALLOW: STATUS_ALLOW,
    CODE_NEEDS_APPROVAL: STATUS_NEEDS_APPROVAL,
    CODE_DENY_EXPLICIT: STATUS_DENY,
    CODE_NO_MATCHING_GRANT: STATUS_DENY,
    CODE_STALE_VERSION: STATUS_VERSION_CONFLICT,
    CODE_MALFORMED_ACTOR: STATUS_INVALID,
    CODE_MALFORMED_ROLE: STATUS_INVALID,
    CODE_UNKNOWN_ROLE: STATUS_INVALID,
    CODE_MALFORMED_ACTION: STATUS_INVALID,
    CODE_UNKNOWN_ACTION: STATUS_INVALID,
    CODE_MALFORMED_RESOURCE: STATUS_INVALID,
    CODE_UNKNOWN_RESOURCE: STATUS_INVALID,
    CODE_RESOURCE_MISMATCH: STATUS_INVALID,
    CODE_WILDCARD_SCOPE: STATUS_INVALID,
    CODE_MALFORMED_PERMISSION: STATUS_INVALID,
    CODE_MALFORMED_POLICY: STATUS_INVALID,
    CODE_CONTRADICTORY_GRANT: STATUS_INVALID,
    CODE_MALFORMED_VERSION: STATUS_INVALID,
    CODE_MISSING_EXPECTED_VERSION: STATUS_INVALID,
    CODE_MALFORMED_AUTHORITY: STATUS_INVALID,
    CODE_FORBIDDEN_AUTHORITY: STATUS_INVALID,
}

# The effect each single grant maps onto, when it is the sole matching effect.
_EFFECT_DECISION = {
    EFFECT_ALLOW: (CODE_ALLOW, "the actor's roles grant this action on this resource"),
    EFFECT_DENY: (CODE_DENY_EXPLICIT, "an explicit deny grant refuses this action on this resource"),
    EFFECT_NEEDS_APPROVAL: (CODE_NEEDS_APPROVAL, "this action on this resource requires an approval before it may proceed"),
}


# --- Small, pure predicates --------------------------------------------------


def _is_positive_int(value: Any) -> bool:
    """A real positive integer — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_visible_ascii_token(value: str) -> bool:
    """True iff every character is visible ASCII (no spaces/controls, 0x21–0x7e)."""
    return bool(value) and all("\x21" <= ch <= "\x7e" for ch in value)


def _is_identifier(value: Any) -> bool:
    """True iff ``value`` is a non-blank, bounded, visible-ASCII single-line token."""
    return isinstance(value, str) and 0 < len(value) <= MAX_IDENTIFIER_LENGTH and _is_visible_ascii_token(value)


def is_action(value: Any) -> bool:
    """True iff ``value`` names a bounded action in :data:`ACTIONS`."""
    return isinstance(value, str) and value in ACTIONS


def is_effect(value: Any) -> bool:
    """True iff ``value`` is one of the bounded grant effects."""
    return isinstance(value, str) and value in EFFECTS


# --- The contract value objects ---------------------------------------------


@dataclass(frozen=True)
class Permission:
    """A single bounded grant: an ``effect`` for an ``action`` over a project scope.

    Fields:

    - ``action`` — the bounded action this grant concerns (a member of :data:`ACTIONS`);
    - ``effect`` — one of :data:`EFFECTS` (defaults to :data:`EFFECT_ALLOW`);
    - ``project`` — the project id this grant is scoped to, or :data:`WILDCARD`
      (``"*"``) **only** when ``scope_is_wildcard`` is explicitly ``True``;
    - ``scope_is_wildcard`` — an explicit opt-in that this grant applies to *every*
      project.  A catch-all scope is otherwise rejected, so a wildcard can never be
      reached by accident (fail closed).

    This is plain deterministic data supplied by the caller; it grants nothing on
    its own — :func:`authorize` interprets it.
    """

    action: str
    effect: str = EFFECT_ALLOW
    project: str = ""
    scope_is_wildcard: bool = False

    def matches(self, action: str, project: str) -> bool:
        """True iff this grant applies to ``action`` on ``project`` (scope-aware)."""
        if self.action != action:
            return False
        if self.scope_is_wildcard:
            return self.project == WILDCARD
        return self.project == project

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the grant (stable key order)."""
        return {
            "action": self.action,
            "effect": self.effect,
            "project": self.project,
            "scope_is_wildcard": self.scope_is_wildcard,
        }


@dataclass(frozen=True)
class Role:
    """A named bundle of :class:`Permission` grants — plain caller-supplied data."""

    name: str
    permissions: tuple[Permission, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "permissions": [p.to_dict() for p in self.permissions]}


@dataclass(frozen=True)
class AuthorizationPolicy:
    """The bounded role catalogue an actor's assigned roles are resolved against.

    ``version`` is an optional optimistic-concurrency fact recorded into the
    decision binding; the version *check* itself only fires when the caller also
    supplies the authoritative ``current_version`` to :func:`authorize`.
    """

    roles: tuple[Role, ...] = ()
    version: int | None = None

    def role_map(self) -> dict[str, Role]:
        """Index roles by name (last definition wins for a duplicated name)."""
        return {role.name: role for role in self.roles if isinstance(role, Role) and isinstance(role.name, str)}


@dataclass(frozen=True)
class ResourceRef:
    """The bounded resource an access request targets: a type + a project scope."""

    resource_type: str
    project: str

    def to_dict(self) -> dict[str, Any]:
        return {"resource_type": self.resource_type, "project": self.project}


@dataclass(frozen=True)
class Principal:
    """The actor making a request, as pure caller-supplied facts.

    ``actor_id`` is the actor's stable local identity (an opaque token — never an
    OS user, GitHub login, email, token, or session, none of which this contract
    ever inspects).  ``roles`` are the names of the roles assigned to the actor,
    resolved against the policy catalogue.  ``authority`` is optional caller-supplied
    authority facts; any :data:`FORBIDDEN_AUTHORITY_FLAGS` key being truthy fails
    closed.
    """

    actor_id: str
    roles: tuple[str, ...] = ()
    authority: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AccessRequest:
    """The parsed *facts* a future adapter would hand to :func:`authorize`.

    ``expected_policy_version`` is an optional optimistic-concurrency expected
    version, checked only when the caller also supplies the authoritative current
    version to :func:`authorize`.
    """

    principal: Principal
    action: str
    resource: ResourceRef
    expected_policy_version: int | None = None


@dataclass(frozen=True)
class AuthDecision:
    """The deterministic, reason-coded outcome of an authorisation evaluation.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  ``binding`` records the exact facts considered so the
    decision can be audited.  No field ever carries a real credential, token, or
    session — only inert policy facts.
    """

    status: str
    reason_code: str
    message: str
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """The single proceed outcome."""
        return self.status == STATUS_ALLOW

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "allowed": self.allowed,
            "binding": dict(self.binding),
        }


# --- Validation helpers ------------------------------------------------------


def _validate_version_field(value: Any, label: str) -> tuple[str, str] | None:
    """Return ``(code, message)`` if an optional version field is malformed, else ``None``."""
    if value is None:
        return None
    if not _is_positive_int(value):
        return (CODE_MALFORMED_VERSION, f"{label}, when supplied, must be a positive integer")
    if len(str(value)) > MAX_VERSION_DIGITS:
        return (CODE_MALFORMED_VERSION, f"{label} has more than {MAX_VERSION_DIGITS} digits")
    return None


def _validate_authority(authority: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the optional authority facts are unusable, else ``None``.

    ``None`` (absent) is permitted.  When present it must be a mapping with string
    keys, and no :data:`FORBIDDEN_AUTHORITY_FLAGS` key may be truthy — this
    contract cannot authenticate or escalate privilege, so it refuses to accept a
    fact that claims it can.
    """
    if authority is None:
        return None
    if not isinstance(authority, Mapping):
        return (CODE_MALFORMED_AUTHORITY, "authority, when supplied, must be a mapping")
    for key in authority:
        if not isinstance(key, str):
            return (CODE_MALFORMED_AUTHORITY, "authority keys must be strings")
    for flag in FORBIDDEN_AUTHORITY_FLAGS:
        if authority.get(flag):
            return (
                CODE_FORBIDDEN_AUTHORITY,
                f"authority flag {flag!r} is forbidden: this contract cannot authenticate, bypass authorisation, or escalate privilege",
            )
    return None


def _validate_principal(principal: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the principal is unusable, else ``None``."""
    if not isinstance(principal, Principal):
        return (CODE_MALFORMED_ACTOR, "principal must be a Principal")
    if not _is_identifier(principal.actor_id):
        return (CODE_MALFORMED_ACTOR, "actor_id must be a non-blank, bounded, visible-ASCII token")
    if not isinstance(principal.roles, (tuple, list)):
        return (CODE_MALFORMED_ROLE, "principal.roles must be a sequence of role names")
    for name in principal.roles:
        if not _is_identifier(name):
            return (CODE_MALFORMED_ROLE, "each assigned role name must be a non-blank, bounded, visible-ASCII token")
    return _validate_authority(principal.authority)


def _validate_resource(action: str, resource: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the resource is unusable for ``action``, else ``None``."""
    if not isinstance(resource, ResourceRef):
        return (CODE_MALFORMED_RESOURCE, "resource must be a ResourceRef")
    if not _is_identifier(resource.resource_type):
        return (CODE_MALFORMED_RESOURCE, "resource_type must be a non-blank, bounded, visible-ASCII token")
    if resource.resource_type not in RESOURCE_TYPES:
        return (CODE_UNKNOWN_RESOURCE, f"resource_type {resource.resource_type!r} is not a known control-plane resource type")
    if resource.resource_type != ACTIONS[action]["resource_type"]:
        return (
            CODE_RESOURCE_MISMATCH,
            f"action {action!r} acts on resource type {ACTIONS[action]['resource_type']!r}, not {resource.resource_type!r}",
        )
    # The project scope must be a bounded identifier.  A bare wildcard project on a
    # *request* is meaningless (a request always targets a concrete resource) and is
    # rejected as malformed; wildcards live only on bounded grants.
    if not _is_identifier(resource.project):
        return (CODE_MALFORMED_RESOURCE, "resource project must be a non-blank, bounded, visible-ASCII token")
    if resource.project == WILDCARD:
        return (CODE_MALFORMED_RESOURCE, "a request must target a concrete project, not the wildcard scope")
    return None


def _validate_permission(perm: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if a single grant is malformed, else ``None``.

    A catch-all/wildcard project scope is rejected unless the grant explicitly opts
    in via ``scope_is_wildcard=True`` (and then the project must be exactly the
    wildcard token) — so a wildcard can never be reached by accident (fail closed).
    """
    if not isinstance(perm, Permission):
        return (CODE_MALFORMED_PERMISSION, "each permission must be a Permission")
    if not is_action(perm.action):
        # Distinguish a blank/malformed action from a well-formed-but-unknown one.
        if not _is_identifier(perm.action):
            return (CODE_MALFORMED_ACTION, "permission action must be a non-blank, bounded, visible-ASCII token")
        return (CODE_UNKNOWN_ACTION, f"permission action {perm.action!r} is not a known control-plane action")
    if not is_effect(perm.effect):
        return (CODE_MALFORMED_PERMISSION, f"permission effect must be one of {EFFECTS!r}")
    if not isinstance(perm.scope_is_wildcard, bool):
        return (CODE_MALFORMED_PERMISSION, "permission scope_is_wildcard must be a bool")
    if perm.scope_is_wildcard:
        if perm.project != WILDCARD:
            return (CODE_MALFORMED_PERMISSION, "a wildcard-scoped permission must set project to the wildcard token")
        return None
    if perm.project == WILDCARD:
        return (CODE_WILDCARD_SCOPE, "a catch-all wildcard scope requires an explicit scope_is_wildcard=True (fail closed)")
    if not _is_identifier(perm.project):
        return (CODE_MALFORMED_PERMISSION, "permission project must be a non-blank, bounded, visible-ASCII token")
    return None


def _validate_policy(policy: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the policy catalogue is structurally unusable, else ``None``."""
    if not isinstance(policy, AuthorizationPolicy):
        return (CODE_MALFORMED_POLICY, "policy must be an AuthorizationPolicy")
    if not isinstance(policy.roles, (tuple, list)):
        return (CODE_MALFORMED_POLICY, "policy.roles must be a sequence of Role")
    version_error = _validate_version_field(policy.version, "policy.version")
    if version_error is not None:
        return version_error
    seen: set[str] = set()
    for role in policy.roles:
        if not isinstance(role, Role):
            return (CODE_MALFORMED_POLICY, "each policy role must be a Role")
        if not _is_identifier(role.name):
            return (CODE_MALFORMED_ROLE, "each role name must be a non-blank, bounded, visible-ASCII token")
        if role.name in seen:
            return (CODE_MALFORMED_POLICY, f"role {role.name!r} is defined more than once")
        seen.add(role.name)
        if not isinstance(role.permissions, (tuple, list)):
            return (CODE_MALFORMED_POLICY, f"role {role.name!r} permissions must be a sequence of Permission")
        for perm in role.permissions:
            perm_error = _validate_permission(perm)
            if perm_error is not None:
                return perm_error
    return None


# --- The deterministic authorisation decision -------------------------------


def authorize(
    request: AccessRequest,
    *,
    policy: AuthorizationPolicy,
    current_version: int | None = None,
) -> AuthDecision:
    """Decide whether ``request`` is authorised by ``policy``, fail-closed.

    A pure, deterministic function returning a bounded :class:`AuthDecision` (it
    never raises for a domain condition and touches no real identity, token, or
    session).  Precedence:

    1. Validate the action (known), the principal (actor/roles/authority), the
       resource (known type matching the action + concrete project), the policy
       structure, and the optional expected version → otherwise ``invalid``.
    2. Resolve every assigned role against the policy catalogue; an unknown
       assigned role → ``invalid``.
    3. Optimistic concurrency: only when ``current_version`` is supplied, the
       expected version is required and must equal it → otherwise
       ``invalid``/``version_conflict``.
    4. Collect the grant effects matching ``(action, project)`` across the actor's
       resolved roles.  No match → ``deny`` (default deny).  More than one *distinct*
       effect → ``invalid`` (a duplicate contradictory grant fails closed).  A
       single effect → ``allow`` / ``deny`` / ``needs_approval`` accordingly.
    """
    action = request.action
    principal = request.principal

    actor_id = principal.actor_id if isinstance(principal, Principal) else None
    assigned_roles = sorted(str(r) for r in principal.roles) if isinstance(principal, Principal) and isinstance(principal.roles, (tuple, list)) else []
    authority_keys = sorted(str(k) for k in principal.authority) if isinstance(principal, Principal) and isinstance(principal.authority, Mapping) else []
    resource_type = request.resource.resource_type if isinstance(request.resource, ResourceRef) else None
    project = request.resource.project if isinstance(request.resource, ResourceRef) else None
    policy_version = policy.version if isinstance(policy, AuthorizationPolicy) else None
    openapi_operation = ACTIONS[action]["openapi_operation"] if is_action(action) else None
    contract = ACTIONS[action]["contract"] if is_action(action) else None

    def _decide(code: str, message: str, *, matched_effects: list[str] | None = None) -> AuthDecision:
        return AuthDecision(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            binding={
                "actor_id": actor_id,
                "assigned_roles": assigned_roles,
                "action": action if is_action(action) else None,
                "resource_type": resource_type,
                "project": project,
                "openapi_operation": openapi_operation,
                "contract": contract,
                "matched_effects": sorted(matched_effects) if matched_effects is not None else [],
                "expected_policy_version": request.expected_policy_version if isinstance(request, AccessRequest) else None,
                "current_version": current_version,
                "policy_version": policy_version,
                "authority_keys": authority_keys,
            },
        )

    # 1. Action must be known before anything bound to it can be trusted.
    if not is_action(action):
        if not _is_identifier(action):
            return _decide(CODE_MALFORMED_ACTION, "action must be a non-blank, bounded, visible-ASCII token")
        return _decide(CODE_UNKNOWN_ACTION, f"action {action!r} is not a known control-plane action")

    # 1b. Principal, resource, policy structure, and version-field shape.
    for error in (
        _validate_principal(principal),
        _validate_resource(action, request.resource),
        _validate_policy(policy),
        _validate_version_field(request.expected_policy_version if isinstance(request, AccessRequest) else None, "expected_policy_version"),
    ):
        if error is not None:
            code, message = error
            return _decide(code, message)

    # 2. Resolve assigned roles against the catalogue; an unknown role fails closed.
    catalogue = policy.role_map()
    resolved: list[Role] = []
    for name in principal.roles:
        role = catalogue.get(name)
        if role is None:
            return _decide(CODE_UNKNOWN_ROLE, f"assigned role {name!r} is not defined in the policy")
        resolved.append(role)

    # 3. Optimistic concurrency, enforced only when the caller supplies the
    #    authoritative current version of the policy.
    if current_version is not None:
        if not _is_positive_int(current_version):
            return _decide(CODE_MALFORMED_VERSION, "current_version, when supplied, must be a positive integer")
        if request.expected_policy_version is None:
            return _decide(CODE_MISSING_EXPECTED_VERSION, "this request requires an expected_policy_version for optimistic concurrency")
        if request.expected_policy_version != current_version:
            return _decide(
                CODE_STALE_VERSION,
                f"expected policy version {request.expected_policy_version} does not match the current version {current_version}; the policy changed (fail closed)",
            )

    # 4. Collect the distinct grant effects matching this (action, project).
    matched_effects: set[str] = set()
    for role in resolved:
        for perm in role.permissions:
            if perm.matches(action, project):
                matched_effects.add(perm.effect)

    matched = sorted(matched_effects)
    if not matched:
        return _decide(
            CODE_NO_MATCHING_GRANT,
            "no role grants this action on this resource; access is denied by default (fail closed)",
            matched_effects=matched,
        )
    if len(matched) > 1:
        return _decide(
            CODE_CONTRADICTORY_GRANT,
            f"the actor's roles carry contradictory grants {matched!r} for this action/resource; refused (fail closed)",
            matched_effects=matched,
        )

    code, message = _EFFECT_DECISION[matched[0]]
    return _decide(code, message, matched_effects=matched)


def actions_for_resource_type(resource_type: str) -> tuple[str, ...]:
    """Return, in catalogue order, the actions that act on ``resource_type``.

    A small read-only convenience for adapters/tests; it performs no I/O and does
    not authorise anything.
    """
    return tuple(name for name, meta in ACTIONS.items() if meta["resource_type"] == resource_type)


# A defensive, import-time consistency check binding this contract to the merged
# OpenAPI contract: every action that names an OpenAPI ``operationId`` must name one
# that actually exists in IMPLEMENTED_OPERATIONS.  This is a pure assertion over
# already-imported data (no I/O); a drift would be a packaging bug, not a runtime
# condition, so failing fast at import is correct.
_declared_ops = {meta["openapi_operation"] for meta in ACTIONS.values() if meta["openapi_operation"] is not None}
assert _declared_ops <= set(IMPLEMENTED_OPERATIONS), "auth_rbac ACTIONS reference an unknown OpenAPI operationId"


__all__ = [
    "MAX_IDENTIFIER_LENGTH",
    "MAX_VERSION_DIGITS",
    "WILDCARD",
    "ACTIONS",
    "RESOURCE_TYPES",
    "FORBIDDEN_AUTHORITY_FLAGS",
    "EFFECT_ALLOW",
    "EFFECT_DENY",
    "EFFECT_NEEDS_APPROVAL",
    "EFFECTS",
    "STATUS_ALLOW",
    "STATUS_DENY",
    "STATUS_NEEDS_APPROVAL",
    "STATUS_VERSION_CONFLICT",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_ALLOW",
    "CODE_NEEDS_APPROVAL",
    "CODE_DENY_EXPLICIT",
    "CODE_NO_MATCHING_GRANT",
    "CODE_STALE_VERSION",
    "CODE_MALFORMED_ACTOR",
    "CODE_MALFORMED_ROLE",
    "CODE_UNKNOWN_ROLE",
    "CODE_MALFORMED_ACTION",
    "CODE_UNKNOWN_ACTION",
    "CODE_MALFORMED_RESOURCE",
    "CODE_UNKNOWN_RESOURCE",
    "CODE_RESOURCE_MISMATCH",
    "CODE_WILDCARD_SCOPE",
    "CODE_MALFORMED_PERMISSION",
    "CODE_MALFORMED_POLICY",
    "CODE_CONTRADICTORY_GRANT",
    "CODE_MALFORMED_VERSION",
    "CODE_MISSING_EXPECTED_VERSION",
    "CODE_MALFORMED_AUTHORITY",
    "CODE_FORBIDDEN_AUTHORITY",
    "REASON_CODES",
    "is_action",
    "is_effect",
    "Permission",
    "Role",
    "AuthorizationPolicy",
    "ResourceRef",
    "Principal",
    "AccessRequest",
    "AuthDecision",
    "authorize",
    "actions_for_resource_type",
]
