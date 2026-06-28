"""Unit tests for the local initial ProjectPolicy builder (WP-06c / T-06-03).

Covers, for the bounded initial-policy build over synthetic toy user-constraint
facts only (no real user/research content, no real human-derived data, no external
call, no persistence, no event, no granted approval):

- explicit toy constraints → an inert ``built`` policy with the expected
  network/sensitivity/automation/execution/export fields and inert resource policy,
- a missing data-sensitivity policy → a fail-closed ``approval_needed`` outcome
  carrying an inert ``ApprovalNeeded`` object that is never granted,
- malformed truthy sensitivity values (the bool ``True`` / the int ``1`` → wrong
  type; the string ``"true"`` → unrecognised) → ``approval_needed``, never a
  permissive default,
- malformed network / resources / automation / execution-mode values (including
  ``REAL``, which the initial builder may never produce) → ``rejected_malformed``,
- absent optional facts → conservative defaults (isolated / unspecified / A0 / DEMO),
- a malformed constraints shape, non-string keys, an invalid project id, and a
  non-positive-integer policy version → ``rejected_malformed``,
- stable policy identity (a repeated build yields a byte-identical policy with the
  same ``project_policy_id`` and ``content_hash``), input immutability, no granted
  approval, a built policy validating under :func:`validate_project_policy`,
  verbatim preservation of original constraints (including unrecognised keys), and
  the bounded status + reason-code vocabulary with deterministic serialisation.
"""

import dataclasses
import unittest

from auto_bioinfo.core.schemas import AUTOMATION_LEVELS
from auto_bioinfo.core.validation import validate_project_policy
from auto_bioinfo.intake.policy_builder import (
    CODE_AUTOMATION_MALFORMED,
    CODE_BUILT,
    CODE_CONSTRAINTS_MALFORMED,
    CODE_EXECUTION_MODE_NOT_PERMITTED,
    CODE_NETWORK_MALFORMED,
    CODE_POLICY_VERSION_MALFORMED,
    CODE_PROJECT_ID_MALFORMED,
    CODE_RESOURCES_MALFORMED,
    CODE_SENSITIVITY_MALFORMED,
    CODE_SENSITIVITY_MISSING,
    CODE_SENSITIVITY_UNRECOGNIZED,
    GATE_DATA_SENSITIVITY,
    REASON_CODES,
    STATUS_APPROVAL_NEEDED,
    STATUS_BUILT,
    STATUS_REJECTED_MALFORMED,
    STATUSES,
    ApprovalNeeded,
    PolicyBuildOutcome,
    build_initial_policy,
)

PROJECT_ID = "proj_demo_01"


def _toy_constraints(**overrides):
    """A minimal valid synthetic constraint set; overrides tune individual facts."""
    base = {"data_sensitivity": "internal", "network": "local_only", "resources": "standard", "automation_level": "A1"}
    base.update(overrides)
    return base


class BuildInitialPolicyHappyPathTests(unittest.TestCase):
    def test_explicit_toy_constraints_build_expected_policy(self):
        outcome = build_initial_policy(_toy_constraints(), project_id=PROJECT_ID)
        self.assertIsInstance(outcome, PolicyBuildOutcome)
        self.assertEqual(outcome.status, STATUS_BUILT)
        self.assertEqual(outcome.reason_code, CODE_BUILT)
        self.assertTrue(outcome.built)
        self.assertFalse(outcome.approval_needed)
        self.assertIsNone(outcome.approval_request)
        policy = outcome.policy
        self.assertIsNotNone(policy)
        self.assertEqual(policy["project_id"], PROJECT_ID)
        self.assertEqual(policy["data_sensitivity"], "internal")
        self.assertEqual(policy["automation_level"], "A1")
        self.assertEqual(policy["execution_mode"], "DEMO")
        self.assertEqual(policy["network_policy"], {"access": "local_only", "egress_allowed": False})
        self.assertEqual(policy["export_policy"], {"external_export_allowed": False, "requires_approval": True})
        # The inert resource policy is recorded in the binding, not in the policy.
        self.assertNotIn("resource_policy", policy)
        self.assertEqual(outcome.binding["resolved"]["resource_policy"], {"tier": "standard"})

    def test_absent_optional_facts_use_conservative_defaults(self):
        outcome = build_initial_policy({"data_sensitivity": "public"}, project_id=PROJECT_ID)
        self.assertTrue(outcome.built)
        policy = outcome.policy
        self.assertEqual(policy["network_policy"], {"access": "isolated", "egress_allowed": False})
        self.assertEqual(policy["automation_level"], "A0")
        self.assertEqual(policy["execution_mode"], "DEMO")
        # public sensitivity → export does not require approval (still no egress).
        self.assertEqual(policy["export_policy"], {"external_export_allowed": False, "requires_approval": False})
        self.assertEqual(outcome.binding["resolved"]["resources"], "unspecified")

    def test_test_execution_mode_is_permitted(self):
        outcome = build_initial_policy(_toy_constraints(execution_mode="TEST"), project_id=PROJECT_ID)
        self.assertTrue(outcome.built)
        self.assertEqual(outcome.policy["execution_mode"], "TEST")

    def test_each_automation_level_a0_through_a3(self):
        for level in AUTOMATION_LEVELS:
            outcome = build_initial_policy(_toy_constraints(automation_level=level), project_id=PROJECT_ID)
            self.assertTrue(outcome.built, level)
            self.assertEqual(outcome.policy["automation_level"], level)

    def test_built_policy_validates(self):
        outcome = build_initial_policy(_toy_constraints(), project_id=PROJECT_ID)
        self.assertEqual(validate_project_policy(outcome.policy), [])


class SensitivityFailClosedTests(unittest.TestCase):
    def _assert_approval(self, outcome, expected_code):
        self.assertEqual(outcome.status, STATUS_APPROVAL_NEEDED)
        self.assertEqual(outcome.reason_code, expected_code)
        self.assertTrue(outcome.approval_needed)
        self.assertFalse(outcome.built)
        self.assertIsNone(outcome.policy)  # never a permissive fallback policy
        approval = outcome.approval_request
        self.assertIsNotNone(approval)
        self.assertEqual(approval["gate"], GATE_DATA_SENSITIVITY)
        self.assertEqual(approval["subject_type"], "ProjectPolicy")
        self.assertEqual(approval["subject_id"], PROJECT_ID)
        self.assertEqual(approval["state"], "requested")  # never granted

    def test_missing_sensitivity_requests_approval(self):
        outcome = build_initial_policy({"network": "isolated"}, project_id=PROJECT_ID)
        self._assert_approval(outcome, CODE_SENSITIVITY_MISSING)

    def test_none_constraints_request_approval_for_missing_sensitivity(self):
        outcome = build_initial_policy(None, project_id=PROJECT_ID)
        self._assert_approval(outcome, CODE_SENSITIVITY_MISSING)

    def test_bool_true_sensitivity_is_malformed(self):
        outcome = build_initial_policy({"data_sensitivity": True}, project_id=PROJECT_ID)
        self._assert_approval(outcome, CODE_SENSITIVITY_MALFORMED)

    def test_int_one_sensitivity_is_malformed(self):
        outcome = build_initial_policy({"data_sensitivity": 1}, project_id=PROJECT_ID)
        self._assert_approval(outcome, CODE_SENSITIVITY_MALFORMED)

    def test_string_true_sensitivity_is_unrecognized(self):
        outcome = build_initial_policy({"data_sensitivity": "true"}, project_id=PROJECT_ID)
        self._assert_approval(outcome, CODE_SENSITIVITY_UNRECOGNIZED)

    def test_approval_is_never_granted(self):
        outcome = build_initial_policy({}, project_id=PROJECT_ID)
        # An inert ApprovalNeeded carries no real timestamp and is always requested.
        rebuilt = ApprovalNeeded(
            project_id=PROJECT_ID,
            subject_type="ProjectPolicy",
            subject_id=PROJECT_ID,
            subject_version=1,
            gate=GATE_DATA_SENSITIVITY,
            reason_code=CODE_SENSITIVITY_MISSING,
            message="x",
        )
        self.assertEqual(rebuilt.state, "requested")
        self.assertNotIn("created_at", outcome.approval_request)
        self.assertNotIn("provenance", outcome.approval_request)

    def test_approval_state_cannot_be_constructed_as_granted(self):
        # ``state`` is not a constructor field, so a caller cannot build a
        # granted-looking ApprovalNeeded — the invariant is unrepresentable.
        with self.assertRaises(TypeError):
            ApprovalNeeded(
                project_id=PROJECT_ID,
                subject_type="ProjectPolicy",
                subject_id=PROJECT_ID,
                subject_version=1,
                gate=GATE_DATA_SENSITIVITY,
                reason_code=CODE_SENSITIVITY_MISSING,
                message="x",
                state="granted",
            )

    def test_approval_state_cannot_be_mutated_to_granted(self):
        # The frozen dataclass forbids overwriting the fixed state afterwards,
        # so ``to_dict`` can never serialize a granted approval.
        approval = ApprovalNeeded(
            project_id=PROJECT_ID,
            subject_type="ProjectPolicy",
            subject_id=PROJECT_ID,
            subject_version=1,
            gate=GATE_DATA_SENSITIVITY,
            reason_code=CODE_SENSITIVITY_MISSING,
            message="x",
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            approval.state = "granted"
        self.assertEqual(approval.to_dict()["state"], "requested")


class OtherMalformedFailClosedTests(unittest.TestCase):
    def _assert_rejected(self, outcome, expected_code):
        self.assertEqual(outcome.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(outcome.reason_code, expected_code)
        self.assertIsNone(outcome.policy)
        self.assertIsNone(outcome.approval_request)

    def test_malformed_network_value_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(network="open_internet"), project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_NETWORK_MALFORMED)

    def test_non_string_network_value_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(network=True), project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_NETWORK_MALFORMED)

    def test_malformed_resources_value_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(resources="unlimited"), project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_RESOURCES_MALFORMED)

    def test_malformed_automation_level_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(automation_level="A9"), project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_AUTOMATION_MALFORMED)

    def test_int_automation_level_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(automation_level=1), project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_AUTOMATION_MALFORMED)

    def test_real_execution_mode_is_not_permitted(self):
        outcome = build_initial_policy(_toy_constraints(execution_mode="REAL"), project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_EXECUTION_MODE_NOT_PERMITTED)
        self.assertIn("REAL", outcome.message)

    def test_unknown_execution_mode_is_not_permitted(self):
        outcome = build_initial_policy(_toy_constraints(execution_mode="WHATEVER"), project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_EXECUTION_MODE_NOT_PERMITTED)

    def test_non_mapping_constraints_are_rejected(self):
        outcome = build_initial_policy(["data_sensitivity", "public"], project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_CONSTRAINTS_MALFORMED)

    def test_non_string_constraint_keys_are_rejected(self):
        outcome = build_initial_policy({1: "public"}, project_id=PROJECT_ID)
        self._assert_rejected(outcome, CODE_CONSTRAINTS_MALFORMED)

    def test_invalid_project_id_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(), project_id="Has Spaces")
        self._assert_rejected(outcome, CODE_PROJECT_ID_MALFORMED)

    def test_empty_project_id_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(), project_id="")
        self._assert_rejected(outcome, CODE_PROJECT_ID_MALFORMED)

    def test_non_positive_policy_version_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(), project_id=PROJECT_ID, policy_version=0)
        self._assert_rejected(outcome, CODE_POLICY_VERSION_MALFORMED)

    def test_bool_policy_version_is_rejected(self):
        outcome = build_initial_policy(_toy_constraints(), project_id=PROJECT_ID, policy_version=True)
        self._assert_rejected(outcome, CODE_POLICY_VERSION_MALFORMED)


class StableIdentityAndPurityTests(unittest.TestCase):
    def test_stable_policy_identity_across_repeated_builds(self):
        a = build_initial_policy(_toy_constraints(), project_id=PROJECT_ID)
        b = build_initial_policy(_toy_constraints(), project_id=PROJECT_ID)
        self.assertEqual(a.policy, b.policy)
        self.assertEqual(a.policy["project_policy_id"], b.policy["project_policy_id"])
        self.assertEqual(a.policy["content_hash"], b.policy["content_hash"])

    def test_different_facts_change_policy_identity(self):
        a = build_initial_policy(_toy_constraints(data_sensitivity="internal"), project_id=PROJECT_ID)
        b = build_initial_policy(_toy_constraints(data_sensitivity="restricted"), project_id=PROJECT_ID)
        self.assertNotEqual(a.policy["content_hash"], b.policy["content_hash"])

    def test_inputs_are_not_mutated(self):
        constraints = _toy_constraints()
        snapshot = dict(constraints)
        build_initial_policy(constraints, project_id=PROJECT_ID)
        self.assertEqual(constraints, snapshot)

    def test_binding_preserves_original_constraints_verbatim(self):
        constraints = _toy_constraints(unrecognised_key="kept verbatim")
        outcome = build_initial_policy(constraints, project_id=PROJECT_ID)
        self.assertEqual(outcome.binding["original_constraints"], constraints)
        # The snapshot is decoupled: mutating the input afterwards does not change it.
        constraints["data_sensitivity"] = "confidential"
        self.assertEqual(outcome.binding["original_constraints"]["data_sensitivity"], "internal")

    def test_mutating_returned_dicts_does_not_affect_outcome(self):
        outcome = build_initial_policy(_toy_constraints(), project_id=PROJECT_ID)
        d = outcome.to_dict()
        d["policy"]["data_sensitivity"] = "tampered"
        d["binding"]["resolved"]["network"] = "tampered"
        self.assertEqual(outcome.policy["data_sensitivity"], "internal")
        self.assertEqual(outcome.binding["resolved"]["network"], "local_only")

    def test_bounded_vocabulary_and_serialisation(self):
        for cons in (_toy_constraints(), {}, {"data_sensitivity": "bogus"}, _toy_constraints(network="bad")):
            outcome = build_initial_policy(cons, project_id=PROJECT_ID)
            self.assertIn(outcome.status, STATUSES)
            self.assertIn(outcome.reason_code, REASON_CODES)
            self.assertEqual(outcome.to_dict(), outcome.to_dict())
            self.assertEqual(outcome.to_dict()["status"], outcome.status)


if __name__ == "__main__":
    unittest.main()
