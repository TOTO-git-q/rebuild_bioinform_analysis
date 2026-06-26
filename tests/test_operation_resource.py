"""Unit tests for the operation-resource state/result contract (WP-04h / T-04-08).

Covers, for the bounded operation status/transition/projection vocabulary:

- the bounded status vocabulary and terminal/non-terminal partition,
- fail-closed construction (malformed id, malformed/terminal initial status,
  missing command identity, malformed fingerprint/key/timestamp/payload),
- valid transitions and invalid-transition fail-closed behaviour,
- terminal immutability and the duplicate-terminal-update refusal,
- deterministic serialisation and the four-way (accepted / succeeded / failed /
  cancelled) plus malformed projection distinction,
- the explicit command-decision -> operation adapter (accepted spawns a pending
  operation; a non-admitted decision fails closed),
- caller-supplied-time-only (the module never reads a real clock), and
- purity: no mutation of caller-supplied payloads and stable repeated output.
"""

import unittest

from auto_bioinfo.control_plane.command_api import (
    CommandRequest,
    evaluate_command_request,
)
from auto_bioinfo.control_plane.operation_resource import (
    ALLOWED_TRANSITIONS,
    CODE_COMMAND_NOT_ADMITTED,
    CODE_INVALID_INITIAL_STATUS,
    CODE_INVALID_TRANSITION,
    CODE_MALFORMED_FINGERPRINT,
    CODE_MALFORMED_IDEMPOTENCY_KEY,
    CODE_MALFORMED_OPERATION_ID,
    CODE_MALFORMED_PAYLOAD,
    CODE_MALFORMED_STATUS,
    CODE_MALFORMED_TIMESTAMP,
    CODE_MISSING_COMMAND_IDENTITY,
    CODE_TERMINAL_IMMUTABLE,
    CODE_UNEXPECTED_PAYLOAD,
    ERROR_CODES,
    NON_TERMINAL_STATUSES,
    OPERATION_STATUSES,
    PROJECTION_ACCEPTED,
    PROJECTION_CANCELLED,
    PROJECTION_CATEGORIES,
    PROJECTION_FAILED,
    PROJECTION_MALFORMED,
    PROJECTION_SUCCEEDED,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    TERMINAL_STATUSES,
    OperationError,
    OperationRecord,
    apply_transition,
    can_transition,
    is_operation_status,
    is_terminal_status,
    new_operation,
    operation_from_command_result,
    project_operation,
    validate_operation_record,
)

_FINGERPRINT = "a" * 64


def _operation(**overrides):
    """A valid fresh pending operation, with optional field overrides."""
    kwargs = {
        "operation_id": "op-123",
        "command_type": "create_project",
        "command_fingerprint": _FINGERPRINT,
        "idempotency_key": "key-123",
    }
    kwargs.update(overrides)
    return new_operation(**kwargs)


class VocabularyTest(unittest.TestCase):
    def test_status_vocabulary_is_bounded_and_partitioned(self):
        self.assertEqual(
            OPERATION_STATUSES,
            (STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED),
        )
        # terminal and non-terminal partition the whole vocabulary, disjointly.
        self.assertEqual(TERMINAL_STATUSES | NON_TERMINAL_STATUSES, set(OPERATION_STATUSES))
        self.assertEqual(TERMINAL_STATUSES & NON_TERMINAL_STATUSES, set())

    def test_predicates_agree_with_vocabulary(self):
        for status in OPERATION_STATUSES:
            self.assertTrue(is_operation_status(status))
            self.assertEqual(is_terminal_status(status), status in TERMINAL_STATUSES)
        self.assertFalse(is_operation_status("PENDING"))  # case-sensitive
        self.assertFalse(is_operation_status("done"))
        self.assertFalse(is_operation_status(None))

    def test_error_and_projection_vocabularies_are_unique(self):
        self.assertEqual(len(ERROR_CODES), len(set(ERROR_CODES)))
        self.assertEqual(len(PROJECTION_CATEGORIES), len(set(PROJECTION_CATEGORIES)))

    def test_terminal_states_have_no_outgoing_edges(self):
        for status in TERMINAL_STATUSES:
            self.assertEqual(ALLOWED_TRANSITIONS[status], frozenset())


class ConstructionTest(unittest.TestCase):
    def test_fresh_operation_defaults_to_pending(self):
        op = _operation()
        self.assertEqual(op.status, STATUS_PENDING)
        self.assertFalse(op.is_terminal)
        self.assertIsNone(op.result)
        self.assertIsNone(op.error)
        self.assertIsNone(op.created_at)
        self.assertEqual(op.projection_category, PROJECTION_ACCEPTED)

    def test_running_is_a_valid_initial_status(self):
        op = _operation(status=STATUS_RUNNING)
        self.assertEqual(op.status, STATUS_RUNNING)

    def test_fingerprint_alone_is_sufficient_identity(self):
        op = _operation(idempotency_key="")
        self.assertEqual(op.command_fingerprint, _FINGERPRINT)
        self.assertEqual(op.idempotency_key, "")

    def test_idempotency_key_alone_is_sufficient_identity(self):
        op = _operation(command_fingerprint="")
        self.assertEqual(op.idempotency_key, "key-123")
        self.assertEqual(op.command_fingerprint, "")

    def test_operation_id_is_trimmed(self):
        op = _operation(operation_id="  op-7  ")
        self.assertEqual(op.operation_id, "op-7")


class ConstructionFailClosedTest(unittest.TestCase):
    def _assert_code(self, code, **overrides):
        with self.assertRaises(OperationError) as ctx:
            _operation(**overrides)
        self.assertEqual(ctx.exception.code, code)

    def test_blank_operation_id_is_rejected(self):
        self._assert_code(CODE_MALFORMED_OPERATION_ID, operation_id="   ")

    def test_non_string_operation_id_is_rejected(self):
        self._assert_code(CODE_MALFORMED_OPERATION_ID, operation_id=123)

    def test_operation_id_with_whitespace_is_rejected(self):
        self._assert_code(CODE_MALFORMED_OPERATION_ID, operation_id="op 7")

    def test_overlong_operation_id_is_rejected(self):
        self._assert_code(CODE_MALFORMED_OPERATION_ID, operation_id="o" * 201)

    def test_terminal_initial_status_is_rejected(self):
        self._assert_code(CODE_INVALID_INITIAL_STATUS, status=STATUS_SUCCEEDED)

    def test_unknown_initial_status_is_rejected(self):
        self._assert_code(CODE_MALFORMED_STATUS, status="done")

    def test_missing_command_type_is_rejected(self):
        self._assert_code(CODE_MISSING_COMMAND_IDENTITY, command_type="  ")

    def test_no_identity_facts_is_rejected(self):
        self._assert_code(CODE_MISSING_COMMAND_IDENTITY, command_fingerprint="", idempotency_key="")

    def test_malformed_fingerprint_is_rejected(self):
        self._assert_code(CODE_MALFORMED_FINGERPRINT, command_fingerprint="not-hex")

    def test_uppercase_fingerprint_is_rejected(self):
        self._assert_code(CODE_MALFORMED_FINGERPRINT, command_fingerprint="A" * 64)

    def test_malformed_idempotency_key_is_rejected(self):
        self._assert_code(CODE_MALFORMED_IDEMPOTENCY_KEY, command_fingerprint="", idempotency_key="bad key")

    def test_malformed_created_at_is_rejected(self):
        self._assert_code(CODE_MALFORMED_TIMESTAMP, created_at="  ")

    def test_created_at_with_control_char_is_rejected(self):
        self._assert_code(CODE_MALFORMED_TIMESTAMP, created_at="2026-06-27\n")

    def test_caller_supplied_created_at_is_stored_verbatim(self):
        op = _operation(created_at="2026-06-27T00:00:00Z")
        self.assertEqual(op.created_at, "2026-06-27T00:00:00Z")


class TransitionTest(unittest.TestCase):
    def test_can_transition_matches_table(self):
        self.assertTrue(can_transition(STATUS_PENDING, STATUS_RUNNING))
        self.assertTrue(can_transition(STATUS_RUNNING, STATUS_SUCCEEDED))
        self.assertFalse(can_transition(STATUS_PENDING, STATUS_SUCCEEDED))
        self.assertFalse(can_transition(STATUS_SUCCEEDED, STATUS_FAILED))
        self.assertFalse(can_transition("done", STATUS_RUNNING))

    def test_pending_to_running_preserves_identity_and_returns_new_value(self):
        op = _operation()
        running = apply_transition(op, STATUS_RUNNING)
        self.assertEqual(running.status, STATUS_RUNNING)
        self.assertEqual(running.operation_id, op.operation_id)
        self.assertEqual(running.command_fingerprint, op.command_fingerprint)
        # original is untouched (immutable value).
        self.assertEqual(op.status, STATUS_PENDING)
        self.assertIsNot(running, op)

    def test_running_to_succeeded_carries_result(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        done = apply_transition(running, STATUS_SUCCEEDED, result={"rows": 3}, updated_at="2026-06-27T01:00:00Z")
        self.assertEqual(done.status, STATUS_SUCCEEDED)
        self.assertEqual(done.result, {"rows": 3})
        self.assertIsNone(done.error)
        self.assertTrue(done.is_terminal)
        self.assertEqual(done.updated_at, "2026-06-27T01:00:00Z")

    def test_running_to_failed_carries_error(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        failed = apply_transition(running, STATUS_FAILED, error={"code": "BOOM"})
        self.assertEqual(failed.status, STATUS_FAILED)
        self.assertEqual(failed.error, {"code": "BOOM"})
        self.assertIsNone(failed.result)

    def test_pending_to_cancelled_is_allowed(self):
        cancelled = apply_transition(_operation(), STATUS_CANCELLED, error={"reason": "user"})
        self.assertEqual(cancelled.status, STATUS_CANCELLED)
        self.assertTrue(cancelled.is_terminal)

    def test_invalid_transition_fails_closed(self):
        with self.assertRaises(OperationError) as ctx:
            apply_transition(_operation(), STATUS_SUCCEEDED)  # pending -> succeeded illegal
        self.assertEqual(ctx.exception.code, CODE_INVALID_TRANSITION)

    def test_unknown_target_status_fails_closed(self):
        with self.assertRaises(OperationError) as ctx:
            apply_transition(_operation(), "done")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_STATUS)

    def test_non_record_input_fails_closed(self):
        with self.assertRaises(OperationError) as ctx:
            apply_transition({"status": "pending"}, STATUS_RUNNING)
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)


class PayloadCoherenceTest(unittest.TestCase):
    def test_non_terminal_transition_rejects_payload(self):
        with self.assertRaises(OperationError) as ctx:
            apply_transition(_operation(), STATUS_RUNNING, result={"x": 1})
        self.assertEqual(ctx.exception.code, CODE_UNEXPECTED_PAYLOAD)

    def test_succeeded_rejects_error_payload(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        with self.assertRaises(OperationError) as ctx:
            apply_transition(running, STATUS_SUCCEEDED, error={"code": "x"})
        self.assertEqual(ctx.exception.code, CODE_UNEXPECTED_PAYLOAD)

    def test_failed_rejects_result_payload(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        with self.assertRaises(OperationError) as ctx:
            apply_transition(running, STATUS_FAILED, result={"rows": 1})
        self.assertEqual(ctx.exception.code, CODE_UNEXPECTED_PAYLOAD)

    def test_non_mapping_payload_is_rejected(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        with self.assertRaises(OperationError) as ctx:
            apply_transition(running, STATUS_SUCCEEDED, result=["not", "a", "mapping"])
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)


class TerminalImmutabilityTest(unittest.TestCase):
    def test_terminal_operation_rejects_further_transition(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        done = apply_transition(running, STATUS_SUCCEEDED)
        with self.assertRaises(OperationError) as ctx:
            apply_transition(done, STATUS_FAILED)
        self.assertEqual(ctx.exception.code, CODE_TERMINAL_IMMUTABLE)

    def test_duplicate_terminal_update_fails_closed(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        done = apply_transition(running, STATUS_SUCCEEDED, result={"ok": True})
        with self.assertRaises(OperationError) as ctx:
            apply_transition(done, STATUS_SUCCEEDED, result={"ok": True})
        self.assertEqual(ctx.exception.code, CODE_TERMINAL_IMMUTABLE)


class ProjectionTest(unittest.TestCase):
    def test_accepted_projection_for_non_terminal(self):
        proj = project_operation(_operation())
        self.assertEqual(proj.category, PROJECTION_ACCEPTED)
        self.assertFalse(proj.terminal)
        self.assertFalse(proj.is_malformed)
        self.assertEqual(proj.operation["status"], STATUS_PENDING)

    def test_succeeded_projection(self):
        op = apply_transition(apply_transition(_operation(), STATUS_RUNNING), STATUS_SUCCEEDED, result={"n": 1})
        proj = project_operation(op)
        self.assertEqual(proj.category, PROJECTION_SUCCEEDED)
        self.assertTrue(proj.terminal)

    def test_failed_projection(self):
        op = apply_transition(apply_transition(_operation(), STATUS_RUNNING), STATUS_FAILED, error={"e": 1})
        self.assertEqual(project_operation(op).category, PROJECTION_FAILED)

    def test_cancelled_projection(self):
        op = apply_transition(_operation(), STATUS_CANCELLED)
        self.assertEqual(project_operation(op).category, PROJECTION_CANCELLED)

    def test_malformed_record_projects_without_raising(self):
        # A hand-built record bypassing the constructor cannot smuggle bad facts
        # past the projection: it classifies as malformed instead of raising.
        bad = OperationRecord(operation_id="bad id", command_type="x", status="done")
        proj = project_operation(bad)
        self.assertEqual(proj.category, PROJECTION_MALFORMED)
        self.assertTrue(proj.is_malformed)
        self.assertIn(proj.error_code, ERROR_CODES)

    def test_non_record_projects_as_malformed(self):
        proj = project_operation("not a record")
        self.assertEqual(proj.category, PROJECTION_MALFORMED)
        self.assertEqual(proj.error_code, CODE_MALFORMED_PAYLOAD)


class ValidateRecordTest(unittest.TestCase):
    def test_well_formed_record_has_no_errors(self):
        self.assertEqual(validate_operation_record(_operation()), [])

    def test_malformed_record_lists_codes(self):
        bad = OperationRecord(operation_id="", command_type="", status="nope")
        codes = {code for code, _ in validate_operation_record(bad)}
        self.assertIn(CODE_MALFORMED_OPERATION_ID, codes)
        self.assertIn(CODE_MALFORMED_STATUS, codes)
        self.assertIn(CODE_MISSING_COMMAND_IDENTITY, codes)

    def test_incoherent_payload_is_flagged(self):
        # pending must not carry a result payload.
        bad = OperationRecord(
            operation_id="op-1",
            command_type="create_project",
            command_fingerprint=_FINGERPRINT,
            status=STATUS_PENDING,
            result={"x": 1},
        )
        codes = {code for code, _ in validate_operation_record(bad)}
        self.assertIn(CODE_UNEXPECTED_PAYLOAD, codes)


class CommandAdapterTest(unittest.TestCase):
    def _accepted_result(self):
        request = CommandRequest(
            command_type="create_project",
            payload={"name": "p"},
            headers={"Idempotency-Key": "key-abc"},
        )
        result = evaluate_command_request(request)
        self.assertTrue(result.accepted)
        return result

    def test_accepted_command_spawns_pending_operation(self):
        op = operation_from_command_result(self._accepted_result(), operation_id="op-xyz", created_at="2026-06-27T00:00:00Z")
        self.assertEqual(op.status, STATUS_PENDING)
        self.assertEqual(op.operation_id, "op-xyz")
        self.assertEqual(op.command_type, "create_project")
        self.assertEqual(op.idempotency_key, "key-abc")
        self.assertEqual(len(op.command_fingerprint), 64)
        self.assertEqual(op.created_at, "2026-06-27T00:00:00Z")

    def test_non_admitted_command_fails_closed(self):
        # A request missing the idempotency key is invalid, not accepted.
        request = CommandRequest(command_type="create_project", payload={"name": "p"})
        result = evaluate_command_request(request)
        self.assertFalse(result.accepted)
        with self.assertRaises(OperationError) as ctx:
            operation_from_command_result(result, operation_id="op-1")
        self.assertEqual(ctx.exception.code, CODE_COMMAND_NOT_ADMITTED)

    def test_non_result_input_fails_closed(self):
        with self.assertRaises(OperationError) as ctx:
            operation_from_command_result({"accepted": True}, operation_id="op-1")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PAYLOAD)


class DeterminismAndPurityTest(unittest.TestCase):
    def test_to_dict_is_deterministic_and_ordered(self):
        op = apply_transition(apply_transition(_operation(), STATUS_RUNNING), STATUS_SUCCEEDED, result={"n": 1})
        self.assertEqual(op.to_dict(), op.to_dict())
        self.assertEqual(
            list(op.to_dict().keys()),
            [
                "operation_id",
                "command_type",
                "command_fingerprint",
                "idempotency_key",
                "status",
                "is_terminal",
                "result",
                "error",
                "created_at",
                "updated_at",
            ],
        )

    def test_caller_payload_is_not_aliased(self):
        running = apply_transition(_operation(), STATUS_RUNNING)
        payload = {"rows": 1}
        done = apply_transition(running, STATUS_SUCCEEDED, result=payload)
        payload["rows"] = 999  # mutate the caller's object after the call
        self.assertEqual(done.result, {"rows": 1})  # stored value is unaffected
        # the to_dict projection is likewise a copy, not an alias.
        snapshot = done.to_dict()
        snapshot["result"]["rows"] = -1
        self.assertEqual(done.result, {"rows": 1})

    def test_repeated_transition_is_stable(self):
        op = _operation()
        first = apply_transition(op, STATUS_RUNNING)
        second = apply_transition(op, STATUS_RUNNING)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_no_clock_is_read(self):
        # Without a caller-supplied timestamp the fields stay None — the module
        # never fills them from a real clock.
        op = _operation()
        self.assertIsNone(op.created_at)
        running = apply_transition(op, STATUS_RUNNING)
        self.assertIsNone(running.updated_at)


if __name__ == "__main__":
    unittest.main()
