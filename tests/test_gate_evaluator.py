"""Unit tests for the A0–A3 admission gate evaluator (WP-04f / T-04-06).

Covers, for every outcome in the bounded vocabulary:

- auto-clear pass / needs-approval by automation level (A0–A3 tiers),
- grant pass, rejection block, and conservative pending/expired/cancelled
  needs-approval handling driven by a real WP-04e ApprovalLifecycleRecord,
- fail-closed rejection of unknown gate names, malformed inputs, invalid /
  tampered / cross-project policies, stale subject versions, stale grants, and
  cross-bound approval records,
- exact identity/version binding of every decision,
- deterministic serialization, and
- no mutation of the input approval record.
"""

import dataclasses
import unittest

from auto_bioinfo.control_plane.approval_lifecycle import (
    approve,
    cancel,
    create_approval_request,
    expire,
    reject,
)
from auto_bioinfo.control_plane.gate_evaluator import (
    CODE_APPROVAL_CANCELLED,
    CODE_APPROVAL_EXPIRED,
    CODE_APPROVAL_GRANTED,
    CODE_APPROVAL_PENDING,
    CODE_APPROVAL_REJECTED,
    CODE_APPROVAL_REQUIRED,
    CODE_AUTO_CLEARED,
    CODE_INVALID_POLICY,
    CODE_MALFORMED_INPUT,
    CODE_POLICY_PROJECT_MISMATCH,
    CODE_STALE_VERSION,
    CODE_SUBJECT_BINDING_MISMATCH,
    CODE_UNKNOWN_APPROVAL_STATE,
    CODE_UNKNOWN_GATE,
    GATE_NAMES,
    OUTCOME_BLOCK,
    OUTCOME_INSUFFICIENT,
    OUTCOME_NEEDS_APPROVAL,
    OUTCOME_PASS,
    OUTCOMES,
    REASON_CODES,
    GateDecision,
    GateEvaluationInput,
    evaluate_gate,
)
from auto_bioinfo.core.schemas import ApprovalRequest, ProjectPolicy

PROJECT = "proj-alpha"
HUMAN = {"actor_type": "human", "actor_id": "reviewer-1", "display_name": "Reviewer One"}


def _policy(automation_level="A1", project_id=PROJECT, **overrides):
    base = dict(project_id=project_id, execution_mode="DEMO", automation_level=automation_level, policy_version=1)
    base.update(overrides)
    return ProjectPolicy(**base).to_dict()


def _request(gate="A2", subject_version=2, project_id=PROJECT, **overrides):
    base = dict(
        project_id=project_id,
        subject_type="research_spec",
        subject_id="rs-0001",
        subject_version=subject_version,
        gate=gate,
        requested_by={"actor_type": "agent", "actor_id": "planner"},
        reason="needs human sign-off",
    )
    base.update(overrides)
    return ApprovalRequest(**base).to_dict()


def _input(**overrides):
    base = dict(
        gate="A2",
        project_id=PROJECT,
        subject_type="research_spec",
        subject_id="rs-0001",
        subject_version=2,
        policy=_policy(),
    )
    base.update(overrides)
    return GateEvaluationInput(**base)


class GateVocabularyTest(unittest.TestCase):
    def test_gate_names_are_the_a0_a3_tiers(self):
        self.assertEqual(GATE_NAMES, ("A0", "A1", "A2", "A3"))

    def test_outcome_and_reason_vocabularies_are_bounded(self):
        self.assertEqual(OUTCOMES, (OUTCOME_PASS, OUTCOME_BLOCK, OUTCOME_NEEDS_APPROVAL, OUTCOME_INSUFFICIENT))
        # Every reason code is unique and the codes are stable strings.
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        self.assertTrue(all(isinstance(code, str) and code.startswith("GATE_") for code in REASON_CODES))


class AutoClearByAutomationLevelTest(unittest.TestCase):
    def test_gate_at_or_below_automation_level_auto_clears(self):
        # Automation level A2 auto-clears gates A0, A1 and A2.
        for gate in ("A0", "A1", "A2"):
            decision = evaluate_gate(_input(gate=gate, policy=_policy(automation_level="A2")))
            self.assertEqual(decision.outcome, OUTCOME_PASS, gate)
            self.assertEqual(decision.reason_code, CODE_AUTO_CLEARED, gate)
            self.assertTrue(decision.passed)

    def test_gate_above_automation_level_needs_approval(self):
        # Automation level A1 (adopted): A2/A3 require explicit approval.
        for gate in ("A2", "A3"):
            decision = evaluate_gate(_input(gate=gate, policy=_policy(automation_level="A1")))
            self.assertEqual(decision.outcome, OUTCOME_NEEDS_APPROVAL, gate)
            self.assertEqual(decision.reason_code, CODE_APPROVAL_REQUIRED, gate)
            self.assertFalse(decision.passed)

    def test_a0_policy_only_auto_clears_a0(self):
        self.assertEqual(evaluate_gate(_input(gate="A0", policy=_policy(automation_level="A0"))).outcome, OUTCOME_PASS)
        self.assertEqual(evaluate_gate(_input(gate="A1", policy=_policy(automation_level="A0"))).outcome, OUTCOME_NEEDS_APPROVAL)

    def test_a3_policy_auto_clears_every_gate(self):
        for gate in GATE_NAMES:
            self.assertEqual(evaluate_gate(_input(gate=gate, policy=_policy(automation_level="A3"))).outcome, OUTCOME_PASS, gate)


class ApprovalGrantBlockTest(unittest.TestCase):
    def test_granted_approval_passes_even_above_automation_level(self):
        record = approve(create_approval_request(_request(gate="A2", subject_version=2)), decided_by=HUMAN, rationale="ok")
        decision = evaluate_gate(_input(gate="A2", subject_version=2, policy=_policy(automation_level="A0"), approval=record))
        self.assertEqual(decision.outcome, OUTCOME_PASS)
        self.assertEqual(decision.reason_code, CODE_APPROVAL_GRANTED)
        self.assertEqual(decision.binding["approval_request_id"], record.approval_request_id)

    def test_rejected_approval_blocks_even_when_auto_clear_would_pass(self):
        # Gate A1 would auto-clear at automation A1, but an explicit human "no" blocks.
        record = reject(create_approval_request(_request(gate="A1", subject_version=2)), decided_by=HUMAN, rationale="not allowed")
        decision = evaluate_gate(_input(gate="A1", subject_version=2, policy=_policy(automation_level="A1"), approval=record))
        self.assertEqual(decision.outcome, OUTCOME_BLOCK)
        self.assertEqual(decision.reason_code, CODE_APPROVAL_REJECTED)

    def test_pending_approval_needs_approval(self):
        record = create_approval_request(_request(gate="A2", subject_version=2))
        decision = evaluate_gate(_input(gate="A2", subject_version=2, approval=record))
        self.assertEqual(decision.outcome, OUTCOME_NEEDS_APPROVAL)
        self.assertEqual(decision.reason_code, CODE_APPROVAL_PENDING)

    def test_expired_approval_needs_approval(self):
        record = expire(create_approval_request(_request(gate="A2", subject_version=2), expires_at="2026-01-01T00:00:00Z"), as_of="2026-02-01T00:00:00Z")
        decision = evaluate_gate(_input(gate="A2", subject_version=2, approval=record))
        self.assertEqual(decision.outcome, OUTCOME_NEEDS_APPROVAL)
        self.assertEqual(decision.reason_code, CODE_APPROVAL_EXPIRED)

    def test_cancelled_approval_needs_approval(self):
        record = cancel(create_approval_request(_request(gate="A2", subject_version=2)), actor=HUMAN, reason="superseded")
        decision = evaluate_gate(_input(gate="A2", subject_version=2, approval=record))
        self.assertEqual(decision.outcome, OUTCOME_NEEDS_APPROVAL)
        self.assertEqual(decision.reason_code, CODE_APPROVAL_CANCELLED)

    def test_granted_bare_approval_request_dict_also_passes(self):
        # A raw ApprovalRequest projection already in the granted state is honoured.
        req = _request(gate="A2", subject_version=2, state="granted")
        decision = evaluate_gate(_input(gate="A2", subject_version=2, policy=_policy(automation_level="A0"), approval=req))
        self.assertEqual(decision.outcome, OUTCOME_PASS)
        self.assertEqual(decision.reason_code, CODE_APPROVAL_GRANTED)


class StaleAndMismatchedApprovalTest(unittest.TestCase):
    def test_approval_for_a_different_subject_version_cannot_pass(self):
        # Granted for version 2, but the gate is evaluating version 3.
        record = approve(create_approval_request(_request(gate="A2", subject_version=2)), decided_by=HUMAN)
        decision = evaluate_gate(_input(gate="A2", subject_version=3, approval=record))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_SUBJECT_BINDING_MISMATCH)
        self.assertFalse(decision.passed)

    def test_approval_for_a_different_gate_cannot_pass(self):
        record = approve(create_approval_request(_request(gate="A3", subject_version=2)), decided_by=HUMAN)
        decision = evaluate_gate(_input(gate="A2", subject_version=2, approval=record))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_SUBJECT_BINDING_MISMATCH)

    def test_approval_for_a_different_subject_id_cannot_pass(self):
        record = approve(create_approval_request(_request(gate="A2", subject_version=2, subject_id="rs-9999")), decided_by=HUMAN)
        decision = evaluate_gate(_input(gate="A2", subject_version=2, subject_id="rs-0001", approval=record))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_SUBJECT_BINDING_MISMATCH)

    def test_approval_for_a_different_project_cannot_pass(self):
        record = approve(create_approval_request(_request(gate="A2", subject_version=2, project_id="proj-other")), decided_by=HUMAN)
        decision = evaluate_gate(_input(gate="A2", subject_version=2, approval=record))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_SUBJECT_BINDING_MISMATCH)

    def test_subject_superseded_by_current_version_cannot_pass(self):
        # Evaluating version 2 while current is 5 — stale, even with no approval.
        decision = evaluate_gate(_input(gate="A1", subject_version=2, current_version=5, policy=_policy(automation_level="A3")))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_STALE_VERSION)

    def test_subject_matching_current_version_is_not_stale(self):
        decision = evaluate_gate(_input(gate="A1", subject_version=2, current_version=2, policy=_policy(automation_level="A3")))
        self.assertEqual(decision.outcome, OUTCOME_PASS)


class FailClosedInputTest(unittest.TestCase):
    def test_unknown_gate_name_is_insufficient(self):
        decision = evaluate_gate(_input(gate="A9"))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_GATE)

    def test_blank_subject_fields_are_malformed(self):
        for field_name in ("project_id", "subject_type", "subject_id"):
            decision = evaluate_gate(_input(**{field_name: "   "}))
            self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT, field_name)
            self.assertEqual(decision.reason_code, CODE_MALFORMED_INPUT, field_name)

    def test_non_positive_subject_version_is_malformed(self):
        for bad in (0, -1, "2", 2.0, True):
            decision = evaluate_gate(_input(subject_version=bad))
            self.assertEqual(decision.reason_code, CODE_MALFORMED_INPUT, bad)

    def test_non_positive_current_version_is_malformed(self):
        decision = evaluate_gate(_input(current_version=0))
        self.assertEqual(decision.reason_code, CODE_MALFORMED_INPUT)

    def test_non_policy_object_is_malformed(self):
        decision = evaluate_gate(_input(policy="not-a-policy"))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_INPUT)

    def test_invalid_policy_is_insufficient(self):
        bad_policy = _policy()
        bad_policy["automation_level"] = "A9"  # outside the bounded vocabulary
        decision = evaluate_gate(_input(policy=bad_policy))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_INVALID_POLICY)

    def test_tampered_policy_is_insufficient(self):
        tampered = _policy(automation_level="A0")
        tampered["automation_level"] = "A3"  # change body without recomputing the hash
        decision = evaluate_gate(_input(policy=tampered))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_INVALID_POLICY)

    def test_policy_bound_to_a_different_project_is_insufficient(self):
        decision = evaluate_gate(_input(policy=_policy(project_id="proj-other")))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_POLICY_PROJECT_MISMATCH)

    def test_unknown_approval_state_is_insufficient(self):
        weird = _request(gate="A2", subject_version=2)
        weird["state"] = "limbo"
        decision = evaluate_gate(_input(gate="A2", subject_version=2, approval=weird))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_APPROVAL_STATE)

    def test_malformed_approval_container_is_insufficient(self):
        decision = evaluate_gate(_input(gate="A2", subject_version=2, approval=12345))
        self.assertEqual(decision.outcome, OUTCOME_INSUFFICIENT)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_INPUT)


class BindingAndSerializationTest(unittest.TestCase):
    def test_decision_binds_exact_identity_and_version(self):
        policy = _policy(automation_level="A2")
        decision = evaluate_gate(_input(gate="A2", subject_version=2, current_version=2, policy=policy))
        binding = decision.binding
        self.assertEqual(binding["project_id"], PROJECT)
        self.assertEqual(binding["gate"], "A2")
        self.assertEqual(binding["subject_type"], "research_spec")
        self.assertEqual(binding["subject_id"], "rs-0001")
        self.assertEqual(binding["subject_version"], 2)
        self.assertEqual(binding["current_version"], 2)
        self.assertEqual(binding["policy_id"], policy["project_policy_id"])
        self.assertEqual(binding["policy_version"], policy["policy_version"])
        self.assertEqual(binding["policy_content_hash"], policy["content_hash"])
        self.assertEqual(binding["automation_level"], "A2")

    def test_to_dict_is_deterministic_and_stable(self):
        decision = evaluate_gate(_input(gate="A2", policy=_policy(automation_level="A3")))
        first = decision.to_dict()
        second = decision.to_dict()
        self.assertEqual(first, second)
        self.assertEqual(
            list(first.keys()),
            ["gate", "outcome", "reason_code", "message", "passed", "binding"],
        )
        # Two evaluations of identical input produce identical projections.
        again = evaluate_gate(_input(gate="A2", policy=_policy(automation_level="A3"))).to_dict()
        self.assertEqual(first, again)

    def test_decision_is_a_frozen_dataclass(self):
        decision = evaluate_gate(_input())
        self.assertIsInstance(decision, GateDecision)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.outcome = OUTCOME_PASS  # type: ignore[misc]


class NoMutationTest(unittest.TestCase):
    def test_evaluation_does_not_mutate_the_approval_record(self):
        record = approve(create_approval_request(_request(gate="A2", subject_version=2)), decided_by=HUMAN)
        before = record.to_dict()
        evaluate_gate(_input(gate="A2", subject_version=2, approval=record))
        self.assertEqual(record.to_dict(), before)
        self.assertEqual(record.state, "granted")

    def test_evaluation_does_not_mutate_a_supplied_policy_dict(self):
        policy = _policy(automation_level="A2")
        before = dict(policy)
        evaluate_gate(_input(policy=policy))
        self.assertEqual(policy, before)


if __name__ == "__main__":
    unittest.main()
