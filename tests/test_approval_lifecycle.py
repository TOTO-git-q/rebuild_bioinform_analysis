"""Unit tests for the ApprovalRequest lifecycle (WP-04e / T-04-05).

Covers create, expire, cancel, approve, reject, stale/mismatched target,
duplicate/terminal-operation rejection, fail-closed paths, and deterministic
serialization of the lifecycle record.
"""

import unittest

from auto_bioinfo.control_plane.approval_lifecycle import (
    CODE_DUPLICATE_DECISION,
    CODE_INVALID_REQUEST,
    CODE_MALFORMED_PAYLOAD,
    CODE_MISSING_REQUEST_ID,
    CODE_NOT_DUE,
    CODE_NOT_PENDING,
    CODE_STALE_VERSION,
    CODE_TERMINAL_STATE,
    PENDING_STATE,
    TERMINAL_STATES,
    ApprovalLifecycleError,
    ApprovalLifecycleRecord,
    approve,
    cancel,
    create_approval_request,
    decide,
    expire,
    is_due,
    reject,
)
from auto_bioinfo.core.schemas import ApprovalRequest


def _request(**overrides):
    """A valid ApprovalRequest projection bound to an exact subject version."""
    base = dict(
        project_id="proj-alpha",
        subject_type="research_spec",
        subject_id="rs-0001",
        subject_version=2,
        gate="A1",
        requested_by={"actor_type": "agent", "actor_id": "planner"},
        reason="needs human sign-off",
    )
    base.update(overrides)
    return ApprovalRequest(**base).to_dict()


HUMAN = {"actor_type": "human", "actor_id": "reviewer-1", "display_name": "Reviewer One"}


class CreateApprovalRequestTest(unittest.TestCase):
    def test_create_opens_a_pending_record(self):
        record = create_approval_request(_request())
        self.assertIsInstance(record, ApprovalLifecycleRecord)
        self.assertEqual(record.state, PENDING_STATE)
        self.assertTrue(record.is_pending)
        self.assertFalse(record.is_terminal)
        self.assertTrue(record.approval_request_id)
        self.assertEqual(record.history[0]["action"], "created")

    def test_create_accepts_dataclass_directly(self):
        record = create_approval_request(
            ApprovalRequest(
                project_id="proj-alpha",
                subject_type="research_spec",
                subject_id="rs-0001",
                subject_version=1,
                gate="A1",
            )
        )
        self.assertTrue(record.is_pending)

    def test_create_rejects_invalid_request(self):
        bad = _request(subject_version=0)  # version must be a positive integer
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            create_approval_request(bad)
        self.assertEqual(ctx.exception.code, CODE_INVALID_REQUEST)

    def test_create_rejects_missing_request_id(self):
        data = _request()
        data["approval_request_id"] = "   "
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            create_approval_request(data)
        self.assertEqual(ctx.exception.code, CODE_MISSING_REQUEST_ID)

    def test_create_rejects_non_pending_start_state(self):
        data = _request()
        data["state"] = "granted"
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            create_approval_request(data)
        self.assertEqual(ctx.exception.code, CODE_NOT_PENDING)

    def test_create_rejects_non_request_object(self):
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            create_approval_request("not-a-request")  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)


class DecideTest(unittest.TestCase):
    def test_approve_grants_and_binds_decision(self):
        record = create_approval_request(_request())
        decided = approve(record, decided_by=HUMAN, rationale="looks good", current_version=2, decided_at="2026-06-26T00:00:00Z")
        self.assertEqual(decided.state, "granted")
        self.assertTrue(decided.is_terminal)
        self.assertIsNotNone(decided.decision)
        self.assertEqual(decided.decision["decision"], "approved")
        self.assertEqual(decided.decision["approval_request_id"], record.approval_request_id)
        self.assertEqual(decided.decision["subject_version"], 2)

    def test_reject_marks_rejected(self):
        record = create_approval_request(_request())
        decided = reject(record, decided_by=HUMAN, decided_at="2026-06-26T00:00:00Z")
        self.assertEqual(decided.state, "rejected")
        self.assertTrue(decided.is_terminal)
        self.assertEqual(decided.decision["decision"], "rejected")

    def test_original_record_is_not_mutated(self):
        record = create_approval_request(_request())
        approve(record, decided_by=HUMAN, current_version=2)
        self.assertEqual(record.state, PENDING_STATE)
        self.assertIsNone(record.decision)

    def test_unknown_decision_verb_fails_closed(self):
        record = create_approval_request(_request())
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            decide(record, "maybe", decided_by=HUMAN)
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)

    def test_approve_superseded_version_is_stale(self):
        record = create_approval_request(_request(subject_version=2))
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            approve(record, decided_by=HUMAN, current_version=5)
        self.assertEqual(ctx.exception.code, CODE_STALE_VERSION)

    def test_reject_superseded_version_is_stale(self):
        # A reject decision still binds an exact target object/version, so
        # deciding a superseded version must fail closed exactly like approve.
        record = create_approval_request(_request(subject_version=2))
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            reject(record, decided_by=HUMAN, current_version=5)
        self.assertEqual(ctx.exception.code, CODE_STALE_VERSION)

    def test_duplicate_decision_fails_closed(self):
        record = create_approval_request(_request())
        granted = approve(record, decided_by=HUMAN, current_version=2)
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            approve(granted, decided_by=HUMAN, current_version=2)
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_DECISION)

    def test_cannot_decide_a_cancelled_request(self):
        record = create_approval_request(_request())
        cancelled = cancel(record, actor=HUMAN, reason="withdrawn")
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            approve(cancelled, decided_by=HUMAN, current_version=2)
        self.assertEqual(ctx.exception.code, CODE_TERMINAL_STATE)


class CancelTest(unittest.TestCase):
    def test_cancel_marks_cancelled_with_actor_and_reason(self):
        record = create_approval_request(_request())
        cancelled = cancel(record, actor=HUMAN, reason="superseded by new plan", as_of="2026-06-26T01:00:00Z")
        self.assertEqual(cancelled.state, "cancelled")
        self.assertTrue(cancelled.is_terminal)
        self.assertEqual(cancelled.terminal_reason["reason"], "superseded by new plan")
        self.assertEqual(cancelled.terminal_reason["actor"]["actor_id"], "reviewer-1")

    def test_cancel_requires_valid_actor(self):
        record = create_approval_request(_request())
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            cancel(record, actor={"actor_type": "wizard", "actor_id": "x"}, reason="why")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)

    def test_cancel_requires_nonblank_reason(self):
        record = create_approval_request(_request())
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            cancel(record, actor=HUMAN, reason="   ")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)

    def test_cannot_cancel_terminal_request(self):
        record = create_approval_request(_request())
        granted = approve(record, decided_by=HUMAN, current_version=2)
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            cancel(granted, actor=HUMAN, reason="too late")
        self.assertEqual(ctx.exception.code, CODE_TERMINAL_STATE)


class ExpireTest(unittest.TestCase):
    def test_expire_when_deadline_reached(self):
        record = create_approval_request(_request(), expires_at="2026-06-26T00:00:00Z")
        expired = expire(record, as_of="2026-06-26T00:00:01Z")
        self.assertEqual(expired.state, "expired")
        self.assertTrue(expired.is_terminal)
        self.assertEqual(expired.terminal_reason["expires_at"], "2026-06-26T00:00:00Z")

    def test_expire_exactly_at_deadline(self):
        record = create_approval_request(_request(), expires_at="2026-06-26T00:00:00Z")
        expired = expire(record, as_of="2026-06-26T00:00:00Z")
        self.assertEqual(expired.state, "expired")

    def test_expire_before_deadline_is_not_due(self):
        record = create_approval_request(_request(), expires_at="2026-06-26T00:00:00Z")
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            expire(record, as_of="2026-06-25T23:59:59Z")
        self.assertEqual(ctx.exception.code, CODE_NOT_DUE)
        # The original record stays live — a premature expire cannot terminate it.
        self.assertTrue(record.is_pending)

    def test_expire_without_deadline_fails_closed(self):
        record = create_approval_request(_request())  # no expires_at
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            expire(record, as_of="2026-06-26T00:00:00Z")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)

    def test_is_due_predicate(self):
        record = create_approval_request(_request(), expires_at="2026-06-26T00:00:00Z")
        self.assertTrue(is_due(record, "2026-06-26T12:00:00Z"))
        self.assertFalse(is_due(record, "2026-06-25T12:00:00Z"))
        # A record without a deadline is never due.
        self.assertFalse(is_due(create_approval_request(_request()), "2999-01-01T00:00:00Z"))

    def test_is_due_rejects_blank_as_of(self):
        record = create_approval_request(_request(), expires_at="2026-06-26T00:00:00Z")
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            is_due(record, "  ")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)

    def test_cannot_expire_decided_request(self):
        record = create_approval_request(_request(), expires_at="2026-06-26T00:00:00Z")
        granted = approve(record, decided_by=HUMAN, current_version=2)
        with self.assertRaises(ApprovalLifecycleError) as ctx:
            expire(granted, as_of="2026-06-27T00:00:00Z")
        self.assertEqual(ctx.exception.code, CODE_TERMINAL_STATE)


class TerminalImmutabilityTest(unittest.TestCase):
    def test_all_terminal_states_block_every_mutation(self):
        # expired
        expired = expire(create_approval_request(_request(), expires_at="2026-01-01T00:00:00Z"), as_of="2026-02-01T00:00:00Z")
        # cancelled
        cancelled = cancel(create_approval_request(_request()), actor=HUMAN, reason="x")
        # granted / rejected
        granted = approve(create_approval_request(_request()), decided_by=HUMAN, current_version=2)
        rejected = reject(create_approval_request(_request()), decided_by=HUMAN)

        for terminal in (expired, cancelled, granted, rejected):
            self.assertIn(terminal.state, TERMINAL_STATES)
            with self.assertRaises(ApprovalLifecycleError):
                cancel(terminal, actor=HUMAN, reason="again")
            with self.assertRaises(ApprovalLifecycleError):
                approve(terminal, decided_by=HUMAN, current_version=2)


class SerializationTest(unittest.TestCase):
    def test_to_dict_is_deterministic_and_stable(self):
        request = _request()
        r1 = create_approval_request(request, expires_at="2026-06-26T00:00:00Z")
        r2 = create_approval_request(dict(request), expires_at="2026-06-26T00:00:00Z")
        self.assertEqual(r1.to_dict(), r2.to_dict())
        # Repeated serialization of the same record is identical.
        self.assertEqual(r1.to_dict(), r1.to_dict())

    def test_to_dict_carries_full_lifecycle(self):
        record = create_approval_request(_request(), expires_at="2026-06-26T00:00:00Z")
        decided = approve(record, decided_by=HUMAN, current_version=2, decided_at="2026-06-26T00:00:00Z")
        projection = decided.to_dict()
        self.assertEqual(projection["state"], "granted")
        self.assertTrue(projection["is_terminal"])
        self.assertEqual(projection["decision"]["decision"], "approved")
        self.assertEqual([h["action"] for h in projection["history"]], ["created", "decided"])


if __name__ == "__main__":
    unittest.main()
