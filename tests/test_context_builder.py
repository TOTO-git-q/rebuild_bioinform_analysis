"""Unit tests for the local sensitive-content / minimum-context contract (WP-05e / T-05-05).

Covers, for the offline, deterministic pre-egress context-builder foundation:

- sensitivity classification (declared / name-detected / value-detected), with detection
  only ever *escalating* and an undeclared field failing closed to ``unknown``,
- minimum-context construction that uses **only** explicitly requested fields and
  rejects broad / full-object context by default (unrequested fields are omitted),
- ``sensitive`` fields blocked and ``unknown`` fields withheld before the context is
  marked usable, ``internal`` fields admitted only when the policy permits the tier,
- fail-closed build-level handling of a missing / malformed policy, a malformed fields
  mapping, and a malformed / over-bound request, with deterministic reason codes,
- deterministic redaction that never leaks an original sensitive value through the
  decision dict, the included context, or the per-field outcomes, and
- the builder writing no project-state / event / artifact / business side effect and
  mutating none of its inputs.

All fixtures are tiny synthetic values (fake tokens, emails, sample ids, SENSITIVE
markers) — no real human-derived data.  The whole module is offline and deterministic:
no network, provider SDK, credential access, or content egress.
"""

import unittest

from auto_bioinfo.agent_gateway.context_builder import (
    CODE_MALFORMED_FIELDS,
    CODE_MALFORMED_POLICY,
    CODE_MALFORMED_REQUEST,
    CODE_MISSING_POLICY,
    CODE_POLICY_DISALLOWED,
    CODE_SENSITIVE_BLOCKED,
    CODE_TOO_MANY_FIELDS,
    CODE_UNKNOWN_FIELD,
    CODE_UNKNOWN_SENSITIVITY,
    MAX_CONTEXT_FIELDS,
    SENSITIVITY_INTERNAL,
    SENSITIVITY_PUBLIC,
    SENSITIVITY_SENSITIVE,
    SENSITIVITY_UNKNOWN,
    STATUS_BLOCKED,
    STATUS_BUILT,
    ContextBuildDecision,
    build_model_context,
    classify_field_sensitivity,
)
from auto_bioinfo.core.schemas import ProjectPolicy
from auto_bioinfo.observability.redaction import REDACTED


def _public_policy() -> ProjectPolicy:
    """A default-restrictive policy: only ``public`` fields may egress."""
    return ProjectPolicy(project_id="proj-1", execution_mode="DEMO")


def _internal_policy() -> ProjectPolicy:
    """A policy whose export ceiling explicitly permits ``internal`` fields."""
    return ProjectPolicy(
        project_id="proj-1",
        execution_mode="DEMO",
        export_policy={"max_context_sensitivity": SENSITIVITY_INTERNAL},
    )


class ClassifyFieldSensitivityTest(unittest.TestCase):
    """The deterministic per-field sensitivity classifier."""

    def test_declared_public_is_honoured(self):
        self.assertEqual(classify_field_sensitivity("organism", "human", SENSITIVITY_PUBLIC), SENSITIVITY_PUBLIC)

    def test_undeclared_field_fails_closed_to_unknown(self):
        self.assertEqual(classify_field_sensitivity("organism", "human", None), SENSITIVITY_UNKNOWN)

    def test_unrecognised_declaration_fails_closed_to_unknown(self):
        self.assertEqual(classify_field_sensitivity("organism", "human", "totally-made-up"), SENSITIVITY_UNKNOWN)

    def test_credential_like_name_escalates_to_sensitive(self):
        # A sensitive-looking *name* overrides even a public declaration.
        self.assertEqual(classify_field_sensitivity("api_token", "abc123", SENSITIVITY_PUBLIC), SENSITIVITY_SENSITIVE)

    def test_sensitive_value_marker_escalates_to_sensitive(self):
        self.assertEqual(classify_field_sensitivity("note", "patient PHI record", SENSITIVITY_PUBLIC), SENSITIVITY_SENSITIVE)

    def test_declared_sensitive_is_sensitive(self):
        self.assertEqual(classify_field_sensitivity("sample_id", "S-001", SENSITIVITY_SENSITIVE), SENSITIVITY_SENSITIVE)

    def test_nested_sensitive_value_is_detected(self):
        value = {"outer": {"password": "hunter2"}}
        self.assertEqual(classify_field_sensitivity("blob", value, SENSITIVITY_PUBLIC), SENSITIVITY_SENSITIVE)


class MinimumContextConstructionTest(unittest.TestCase):
    """Only explicitly requested fields are used; unrequested fields are omitted."""

    def test_only_requested_public_fields_are_included(self):
        fields = {"organism": "human", "tissue": "liver", "secret_extra": "should-not-appear"}
        decision = build_model_context(
            policy=_public_policy(),
            fields=fields,
            requested_fields=["organism", "tissue"],
            declared_sensitivities={"organism": SENSITIVITY_PUBLIC, "tissue": SENSITIVITY_PUBLIC},
        )
        self.assertTrue(decision.usable)
        self.assertEqual(decision.status, STATUS_BUILT)
        self.assertEqual(set(decision.included_context), {"organism", "tissue"})
        self.assertEqual(decision.included_context["organism"], "human")
        # The unrequested field is omitted entirely — not included, not even mentioned.
        self.assertNotIn("secret_extra", decision.included_context)
        self.assertNotIn("secret_extra", [o.name for o in decision.field_outcomes])

    def test_empty_request_yields_usable_empty_context(self):
        decision = build_model_context(policy=_public_policy(), fields={"a": "1"}, requested_fields=[])
        self.assertTrue(decision.usable)
        self.assertEqual(decision.included_context, {})
        self.assertEqual(decision.field_outcomes, ())

    def test_requested_but_absent_field_is_withheld(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"organism": "human"},
            requested_fields=["organism", "missing"],
            declared_sensitivities={"organism": SENSITIVITY_PUBLIC},
        )
        self.assertTrue(decision.usable)
        self.assertEqual(decision.included_fields, ("organism",))
        withheld = {o.name: o.reason_code for o in decision.withheld()}
        self.assertEqual(withheld, {"missing": CODE_UNKNOWN_FIELD})

    def test_field_outcomes_follow_requested_order(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"a": "1", "b": "2"},
            requested_fields=["b", "a"],
            declared_sensitivities={"a": SENSITIVITY_PUBLIC, "b": SENSITIVITY_PUBLIC},
        )
        self.assertEqual([o.name for o in decision.field_outcomes], ["b", "a"])


class SensitivityGatingTest(unittest.TestCase):
    """Sensitive fields are blocked and unknown fields withheld before usable context."""

    def test_sensitive_field_is_blocked(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"organism": "human", "sample_id": "S-001"},
            requested_fields=["organism", "sample_id"],
            declared_sensitivities={"organism": SENSITIVITY_PUBLIC, "sample_id": SENSITIVITY_SENSITIVE},
        )
        self.assertTrue(decision.usable)  # still usable with the remaining allowed field
        self.assertNotIn("sample_id", decision.included_context)
        blocked = {o.name: o.reason_code for o in decision.withheld()}
        self.assertEqual(blocked["sample_id"], CODE_SENSITIVE_BLOCKED)

    def test_unknown_sensitivity_field_fails_closed(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"mystery": "value"},
            requested_fields=["mystery"],
            # no declared sensitivity -> unknown -> withheld
        )
        self.assertNotIn("mystery", decision.included_context)
        self.assertEqual(decision.withheld()[0].reason_code, CODE_UNKNOWN_SENSITIVITY)
        self.assertEqual(decision.withheld()[0].sensitivity, SENSITIVITY_UNKNOWN)

    def test_internal_field_disallowed_under_public_policy(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"internal_note": "team-only"},
            requested_fields=["internal_note"],
            declared_sensitivities={"internal_note": SENSITIVITY_INTERNAL},
        )
        self.assertNotIn("internal_note", decision.included_context)
        self.assertEqual(decision.withheld()[0].reason_code, CODE_POLICY_DISALLOWED)

    def test_internal_field_admitted_when_policy_permits(self):
        decision = build_model_context(
            policy=_internal_policy(),
            fields={"internal_note": "team-only"},
            requested_fields=["internal_note"],
            declared_sensitivities={"internal_note": SENSITIVITY_INTERNAL},
        )
        self.assertTrue(decision.usable)
        self.assertIn("internal_note", decision.included_context)
        self.assertEqual(decision.included_context["internal_note"], "team-only")

    def test_sensitive_value_marker_blocks_even_a_declared_public_field(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"note": "this record is CONFIDENTIAL"},
            requested_fields=["note"],
            declared_sensitivities={"note": SENSITIVITY_PUBLIC},
        )
        self.assertNotIn("note", decision.included_context)
        self.assertEqual(decision.withheld()[0].reason_code, CODE_SENSITIVE_BLOCKED)


class RedactionNoLeakTest(unittest.TestCase):
    """Redaction is deterministic and never leaks an original sensitive value."""

    def test_blocked_sensitive_value_never_appears_in_any_projection(self):
        leak = "super-secret-token-zzz"
        decision = build_model_context(
            policy=_public_policy(),
            fields={"creds": leak},
            requested_fields=["creds"],
            declared_sensitivities={"creds": SENSITIVITY_SENSITIVE},
        )
        serialized = repr(decision.to_dict())
        self.assertNotIn(leak, serialized)
        self.assertNotIn(leak, str(decision.included_context))
        # The per-field outcome carries only name / sensitivity / reason — no value.
        self.assertNotIn(leak, repr([o.to_dict() for o in decision.field_outcomes]))

    def test_inline_secret_in_an_admitted_public_value_is_redacted(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"summary": "contact token=abc123 for access"},
            requested_fields=["summary"],
            declared_sensitivities={"summary": SENSITIVITY_PUBLIC},
        )
        self.assertTrue(decision.usable)
        admitted = decision.included_context["summary"]
        self.assertNotIn("abc123", admitted)
        self.assertIn(REDACTED, admitted)

    def test_build_is_deterministic(self):
        kwargs = dict(
            policy=_public_policy(),
            fields={"a": "1", "b": "2", "sample": "S"},
            requested_fields=["a", "b", "sample"],
            declared_sensitivities={"a": SENSITIVITY_PUBLIC, "b": SENSITIVITY_PUBLIC, "sample": SENSITIVITY_SENSITIVE},
        )
        first = build_model_context(**kwargs)
        second = build_model_context(**kwargs)
        self.assertEqual(first.to_dict(), second.to_dict())


class FailClosedBuildTest(unittest.TestCase):
    """A missing / malformed policy, fields, or request blocks the whole build."""

    def test_missing_policy_blocks(self):
        decision = build_model_context(policy=None, fields={"a": "1"}, requested_fields=["a"])
        self.assertFalse(decision.usable)
        self.assertEqual(decision.status, STATUS_BLOCKED)
        self.assertEqual(decision.reason_code, CODE_MISSING_POLICY)
        self.assertEqual(decision.included_context, {})

    def test_non_policy_object_is_malformed(self):
        decision = build_model_context(policy=42, fields={"a": "1"}, requested_fields=["a"])
        self.assertEqual(decision.reason_code, CODE_MALFORMED_POLICY)

    def test_policy_configuring_sensitive_egress_is_malformed(self):
        bad = ProjectPolicy(
            project_id="p",
            execution_mode="DEMO",
            export_policy={"max_context_sensitivity": SENSITIVITY_SENSITIVE},
        )
        decision = build_model_context(policy=bad, fields={"a": "1"}, requested_fields=["a"])
        self.assertEqual(decision.reason_code, CODE_MALFORMED_POLICY)

    def test_non_mapping_fields_is_malformed(self):
        decision = build_model_context(policy=_public_policy(), fields=["a", "b"], requested_fields=["a"])
        self.assertEqual(decision.reason_code, CODE_MALFORMED_FIELDS)

    def test_string_request_is_malformed(self):
        # A bare string is iterable but is never a valid *list of field names*.
        decision = build_model_context(policy=_public_policy(), fields={"a": "1"}, requested_fields="a")
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)

    def test_duplicate_requested_name_is_malformed(self):
        decision = build_model_context(policy=_public_policy(), fields={"a": "1"}, requested_fields=["a", "a"])
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)

    def test_blank_requested_name_is_malformed(self):
        decision = build_model_context(policy=_public_policy(), fields={"a": "1"}, requested_fields=["", "a"])
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)

    def test_over_bound_request_fails_closed(self):
        too_many = [f"f{i}" for i in range(MAX_CONTEXT_FIELDS + 1)]
        decision = build_model_context(policy=_public_policy(), fields={}, requested_fields=too_many)
        self.assertEqual(decision.reason_code, CODE_TOO_MANY_FIELDS)

    def test_malformed_declared_sensitivities_is_malformed(self):
        decision = build_model_context(
            policy=_public_policy(),
            fields={"a": "1"},
            requested_fields=["a"],
            declared_sensitivities=["not", "a", "mapping"],
        )
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)


class PolicyShapedMappingTest(unittest.TestCase):
    """A plain policy-shaped mapping is accepted alongside a ProjectPolicy."""

    def test_mapping_policy_default_is_public_only(self):
        decision = build_model_context(
            policy={"project_id": "p", "project_policy_id": "pp-1"},
            fields={"a": "1", "n": "team"},
            requested_fields=["a", "n"],
            declared_sensitivities={"a": SENSITIVITY_PUBLIC, "n": SENSITIVITY_INTERNAL},
        )
        self.assertEqual(decision.policy_ref, "pp-1")
        self.assertEqual(decision.included_fields, ("a",))
        self.assertEqual(decision.withheld()[0].reason_code, CODE_POLICY_DISALLOWED)

    def test_mapping_policy_can_permit_internal(self):
        decision = build_model_context(
            policy={"project_id": "p", "export_policy": {"max_context_sensitivity": SENSITIVITY_INTERNAL}},
            fields={"n": "team"},
            requested_fields=["n"],
            declared_sensitivities={"n": SENSITIVITY_INTERNAL},
        )
        self.assertTrue(decision.usable)
        self.assertIn("n", decision.included_context)


class NoSideEffectTest(unittest.TestCase):
    """The builder mutates none of its inputs and returns inert data only."""

    def test_inputs_are_not_mutated(self):
        fields = {"a": "1", "creds": "tok"}
        declared = {"a": SENSITIVITY_PUBLIC, "creds": SENSITIVITY_SENSITIVE}
        requested = ["a", "creds"]
        build_model_context(policy=_public_policy(), fields=fields, requested_fields=requested, declared_sensitivities=declared)
        self.assertEqual(fields, {"a": "1", "creds": "tok"})
        self.assertEqual(declared, {"a": SENSITIVITY_PUBLIC, "creds": SENSITIVITY_SENSITIVE})
        self.assertEqual(requested, ["a", "creds"])

    def test_decision_is_a_frozen_value(self):
        decision = build_model_context(policy=_public_policy(), fields={}, requested_fields=[])
        self.assertIsInstance(decision, ContextBuildDecision)
        with self.assertRaises(Exception):
            decision.status = "tampered"  # frozen dataclass


if __name__ == "__main__":
    unittest.main()
