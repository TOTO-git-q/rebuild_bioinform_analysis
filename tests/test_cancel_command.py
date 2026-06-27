"""Unit tests for the local cancel-command contract foundation (WP-04j / T-04-10).

Covers, for the bounded cancel decision over the WP-04h operation vocabulary:

- valid cancellation of a pending/running operation, projecting a bounded
  ``cancelled`` operation record (a value, never a real interruption),
- fail-closed request validation (malformed operation id, missing/malformed cancel
  command identity, malformed expected version, malformed reason, malformed/
  forbidden authority facts),
- fail-closed operation handling (missing record, malformed record, operation-id
  mismatch),
- already-terminal / already-cancelled / unsupported state refusals,
- optimistic-concurrency handling (matching version allows, stale fails closed,
  missing/malformed version fails closed),
- deterministic serialisation, stable reason codes, and exact audit binding,
- purity / totality: no mutation of the supplied operation, caller-supplied-time
  only (no real clock), and stable repeated output, and
- the optional additive ``command cancel`` CLI mapping (WP-04i integration).
"""

import unittest

from auto_bioinfo.control_plane.cancel_command import (
    CANCEL_COMMAND_TYPE,
    CODE_ALREADY_CANCELLED,
    CODE_ALREADY_TERMINAL,
    CODE_CANCELLED,
    CODE_FORBIDDEN_AUTHORITY,
    CODE_MALFORMED_AUTHORITY,
    CODE_MALFORMED_IDEMPOTENCY_KEY,
    CODE_MALFORMED_OPERATION,
    CODE_MALFORMED_OPERATION_ID,
    CODE_MALFORMED_REASON,
    CODE_MALFORMED_VERSION,
    CODE_MISSING_COMMAND_IDENTITY,
    CODE_MISSING_EXPECTED_VERSION,
    CODE_MISSING_OPERATION,
    CODE_OPERATION_MISMATCH,
    CODE_STALE_VERSION,
    REASON_CODES,
    STATUS_CANCELLED,
    STATUS_INVALID,
    STATUS_NOT_CANCELLABLE,
    STATUS_VERSION_CONFLICT,
    STATUSES,
    CancelCommand,
    CancelDecision,
    evaluate_cancel_request,
)
from auto_bioinfo.control_plane.cli_contract import (
    CLI_STATUS_OK,
    CLI_STATUS_REJECTED,
    CLI_STATUS_USAGE_ERROR,
    CODE_MALFORMED_OPTION,
    CODE_MISSING_REQUIRED_OPTION,
    run_cli,
)
from auto_bioinfo.control_plane.command_api import MAX_IDEMPOTENCY_KEY_LENGTH
from auto_bioinfo.control_plane.operation_resource import (
    STATUS_CANCELLED as OP_CANCELLED,
)
from auto_bioinfo.control_plane.operation_resource import (
    STATUS_FAILED as OP_FAILED,
)
from auto_bioinfo.control_plane.operation_resource import (
    STATUS_PENDING as OP_PENDING,
)
from auto_bioinfo.control_plane.operation_resource import (
    STATUS_RUNNING as OP_RUNNING,
)
from auto_bioinfo.control_plane.operation_resource import (
    STATUS_SUCCEEDED as OP_SUCCEEDED,
)
from auto_bioinfo.control_plane.operation_resource import (
    OperationRecord,
)

_OP_ID = "op-123"


def _operation(**overrides) -> OperationRecord:
    """A valid running operation record, with optional field overrides."""
    kwargs = {
        "operation_id": _OP_ID,
        "command_type": "create_project",
        "status": OP_RUNNING,
        "idempotency_key": "orig-key",
    }
    kwargs.update(overrides)
    return OperationRecord(**kwargs)


def _request(**overrides) -> CancelCommand:
    """A valid cancel command targeting the default operation."""
    kwargs = {"operation_id": _OP_ID, "idempotency_key": "cancel-key"}
    kwargs.update(overrides)
    return CancelCommand(**kwargs)


class CancelCommandContractTest(unittest.TestCase):
    # --- valid cancellation ---------------------------------------------------

    def test_valid_cancellation_of_running_operation_projects_cancelled(self):
        decision = evaluate_cancel_request(_request(), operation=_operation(status=OP_RUNNING))
        self.assertTrue(decision.cancelled)
        self.assertEqual(decision.status, STATUS_CANCELLED)
        self.assertEqual(decision.reason_code, CODE_CANCELLED)
        self.assertIsNotNone(decision.operation)
        self.assertEqual(decision.operation["status"], OP_CANCELLED)
        self.assertTrue(decision.operation["is_terminal"])

    def test_valid_cancellation_of_pending_operation(self):
        decision = evaluate_cancel_request(_request(), operation=_operation(status=OP_PENDING))
        self.assertTrue(decision.cancelled)
        self.assertEqual(decision.operation["status"], OP_CANCELLED)

    def test_reason_is_recorded_in_cancelled_error_payload(self):
        decision = evaluate_cancel_request(_request(reason="user aborted run"), operation=_operation())
        self.assertTrue(decision.cancelled)
        self.assertEqual(decision.operation["error"]["cancel_reason"], "user aborted run")
        self.assertEqual(decision.operation["error"]["reason_code"], CODE_CANCELLED)

    def test_no_reason_leaves_error_payload_absent(self):
        decision = evaluate_cancel_request(_request(), operation=_operation())
        self.assertIsNone(decision.operation["error"])

    def test_caller_supplied_timestamp_is_recorded_no_clock_read(self):
        decision = evaluate_cancel_request(_request(updated_at="2026-06-27T00:00:00Z"), operation=_operation())
        self.assertEqual(decision.operation["updated_at"], "2026-06-27T00:00:00Z")
        # Without a caller timestamp the field stays absent (the clock is never read).
        bare = evaluate_cancel_request(_request(), operation=_operation())
        self.assertIsNone(bare.operation["updated_at"])

    def test_default_command_type_is_the_cancel_command_type(self):
        self.assertEqual(_request().command_type, CANCEL_COMMAND_TYPE)

    # --- request validation (fail closed) ------------------------------------

    def test_blank_operation_id_fails_closed(self):
        decision = evaluate_cancel_request(_request(operation_id="   "), operation=_operation())
        self.assertEqual(decision.status, STATUS_INVALID)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_OPERATION_ID)

    def test_operation_id_with_space_fails_closed(self):
        decision = evaluate_cancel_request(_request(operation_id="op 1"), operation=_operation(operation_id="op 1"))
        self.assertEqual(decision.reason_code, CODE_MALFORMED_OPERATION_ID)

    def test_padded_operation_id_fails_closed_does_not_retarget_canonical_operation(self):
        # A padded operation id (" op-123 ") must NOT be silently stripped into the
        # canonical id ("op-123") and cancel that operation; it fails closed instead,
        # and never projects a cancelled record nor binds the canonical operation.
        for padded in (" op-123", "op-123 ", " op-123 ", "\top-123", "op-123\n"):
            with self.subTest(operation_id=padded):
                decision = evaluate_cancel_request(_request(operation_id=padded), operation=_operation(operation_id="op-123"))
                self.assertEqual(decision.status, STATUS_INVALID)
                self.assertEqual(decision.reason_code, CODE_MALFORMED_OPERATION_ID)
                self.assertIsNone(decision.operation)
                # The binding records the exact (padded) token considered, not a normalised one.
                self.assertEqual(decision.binding["operation_id"], padded)

    def test_missing_idempotency_key_fails_closed(self):
        decision = evaluate_cancel_request(_request(idempotency_key=""), operation=_operation())
        self.assertEqual(decision.status, STATUS_INVALID)
        self.assertEqual(decision.reason_code, CODE_MISSING_COMMAND_IDENTITY)

    def test_blank_command_type_fails_closed(self):
        decision = evaluate_cancel_request(_request(command_type="  "), operation=_operation())
        self.assertEqual(decision.reason_code, CODE_MISSING_COMMAND_IDENTITY)

    def test_idempotency_key_with_space_fails_closed(self):
        decision = evaluate_cancel_request(_request(idempotency_key="bad key"), operation=_operation())
        self.assertEqual(decision.reason_code, CODE_MALFORMED_IDEMPOTENCY_KEY)

    def test_overlong_idempotency_key_fails_closed(self):
        decision = evaluate_cancel_request(_request(idempotency_key="k" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1)), operation=_operation())
        self.assertEqual(decision.reason_code, CODE_MALFORMED_IDEMPOTENCY_KEY)

    def test_malformed_expected_version_field_fails_closed(self):
        for bad in (0, -1, True):
            with self.subTest(bad=bad):
                decision = evaluate_cancel_request(_request(expected_version=bad), operation=_operation())
                self.assertEqual(decision.reason_code, CODE_MALFORMED_VERSION)

    def test_malformed_reason_fails_closed(self):
        decision = evaluate_cancel_request(_request(reason="bad\nreason"), operation=_operation())
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REASON)

    # --- authority facts ------------------------------------------------------

    def test_forbidden_authority_flag_fails_closed(self):
        decision = evaluate_cancel_request(_request(authority={"kills_worker": True}), operation=_operation())
        self.assertEqual(decision.status, STATUS_INVALID)
        self.assertEqual(decision.reason_code, CODE_FORBIDDEN_AUTHORITY)

    def test_non_mapping_authority_fails_closed(self):
        decision = evaluate_cancel_request(_request(authority="root"), operation=_operation())
        self.assertEqual(decision.reason_code, CODE_MALFORMED_AUTHORITY)

    def test_benign_authority_keys_are_recorded_and_allowed(self):
        decision = evaluate_cancel_request(_request(authority={"requested_by": "alice", "kills_worker": False}), operation=_operation())
        self.assertTrue(decision.cancelled)
        self.assertEqual(decision.binding["authority_keys"], ["kills_worker", "requested_by"])

    # --- operation record handling -------------------------------------------

    def test_missing_operation_record_fails_closed(self):
        decision = evaluate_cancel_request(_request(), operation=None)
        self.assertEqual(decision.status, STATUS_INVALID)
        self.assertEqual(decision.reason_code, CODE_MISSING_OPERATION)

    def test_malformed_operation_record_fails_closed(self):
        decision = evaluate_cancel_request(_request(), operation=_operation(status="bogus"))
        self.assertEqual(decision.reason_code, CODE_MALFORMED_OPERATION)

    def test_operation_id_mismatch_fails_closed(self):
        decision = evaluate_cancel_request(_request(operation_id="op-A"), operation=_operation(operation_id="op-B"))
        self.assertEqual(decision.reason_code, CODE_OPERATION_MISMATCH)

    # --- terminal / unsupported state refusals --------------------------------

    def test_already_cancelled_operation_is_not_cancellable(self):
        decision = evaluate_cancel_request(_request(), operation=_operation(status=OP_CANCELLED))
        self.assertEqual(decision.status, STATUS_NOT_CANCELLABLE)
        self.assertEqual(decision.reason_code, CODE_ALREADY_CANCELLED)
        self.assertIsNone(decision.operation)

    def test_succeeded_operation_is_not_cancellable(self):
        decision = evaluate_cancel_request(_request(), operation=_operation(status=OP_SUCCEEDED))
        self.assertEqual(decision.status, STATUS_NOT_CANCELLABLE)
        self.assertEqual(decision.reason_code, CODE_ALREADY_TERMINAL)

    def test_failed_operation_is_not_cancellable(self):
        decision = evaluate_cancel_request(_request(), operation=_operation(status=OP_FAILED))
        self.assertEqual(decision.reason_code, CODE_ALREADY_TERMINAL)

    # --- optimistic concurrency ----------------------------------------------

    def test_matching_version_allows_cancellation(self):
        decision = evaluate_cancel_request(_request(expected_version=5), operation=_operation(), current_version=5)
        self.assertTrue(decision.cancelled)
        self.assertEqual(decision.binding["expected_version"], 5)
        self.assertEqual(decision.binding["current_version"], 5)

    def test_stale_version_fails_closed(self):
        decision = evaluate_cancel_request(_request(expected_version=4), operation=_operation(), current_version=5)
        self.assertEqual(decision.status, STATUS_VERSION_CONFLICT)
        self.assertEqual(decision.reason_code, CODE_STALE_VERSION)

    def test_missing_expected_version_when_current_supplied_fails_closed(self):
        decision = evaluate_cancel_request(_request(), operation=_operation(), current_version=5)
        self.assertEqual(decision.reason_code, CODE_MISSING_EXPECTED_VERSION)

    def test_malformed_current_version_fails_closed(self):
        decision = evaluate_cancel_request(_request(expected_version=5), operation=_operation(), current_version=0)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_VERSION)

    # --- determinism / purity / binding --------------------------------------

    def test_decision_serialisation_is_deterministic(self):
        a = evaluate_cancel_request(_request(reason="x"), operation=_operation()).to_dict()
        b = evaluate_cancel_request(_request(reason="x"), operation=_operation()).to_dict()
        self.assertEqual(a, b)

    def test_status_and_reason_codes_are_bounded(self):
        decision = evaluate_cancel_request(_request(), operation=_operation())
        self.assertIn(decision.status, STATUSES)
        self.assertIn(decision.reason_code, REASON_CODES)

    def test_binding_records_a_stable_64_hex_fingerprint(self):
        decision = evaluate_cancel_request(_request(), operation=_operation())
        fp = decision.binding["command_fingerprint"]
        self.assertEqual(len(fp), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))
        self.assertEqual(fp, _request().fingerprint())

    def test_operation_record_is_not_mutated(self):
        op = _operation(status=OP_RUNNING)
        evaluate_cancel_request(_request(), operation=op)
        self.assertEqual(op.status, OP_RUNNING)
        self.assertIsNone(op.error)

    def test_decision_is_a_dataclass_value(self):
        decision = evaluate_cancel_request(_request(), operation=_operation())
        self.assertIsInstance(decision, CancelDecision)


class CancelCommandCliTest(unittest.TestCase):
    def _argv(self, *extra: str) -> list[str]:
        return [
            "command",
            "cancel",
            "--operation-id",
            _OP_ID,
            "--key",
            "cancel-key",
            "--operation-command-type",
            "create_project",
            "--operation-key",
            "orig-key",
            *extra,
        ]

    def test_cli_cancel_valid_running_operation(self):
        result = run_cli(self._argv("--operation-status", OP_RUNNING))
        self.assertEqual(result.status, CLI_STATUS_OK)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.reason_code, CODE_CANCELLED)
        self.assertEqual(result.binding["decision"]["operation"]["status"], OP_CANCELLED)

    def test_cli_cancel_defaults_to_running_status(self):
        result = run_cli(self._argv())
        self.assertEqual(result.status, CLI_STATUS_OK)
        self.assertEqual(result.reason_code, CODE_CANCELLED)

    def test_cli_cancel_with_reason(self):
        result = run_cli(self._argv("--reason", "operator stop"))
        self.assertEqual(result.status, CLI_STATUS_OK)
        self.assertEqual(result.binding["decision"]["operation"]["error"]["cancel_reason"], "operator stop")

    def test_cli_cancel_missing_required_option_is_usage_error(self):
        argv = ["command", "cancel", "--operation-id", _OP_ID, "--key", "k", "--operation-key", "orig-key"]
        result = run_cli(argv)
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
        self.assertEqual(result.reason_code, CODE_MISSING_REQUIRED_OPTION)

    def test_cli_cancel_already_terminal_is_rejected(self):
        result = run_cli(self._argv("--operation-status", OP_SUCCEEDED))
        self.assertEqual(result.status, CLI_STATUS_REJECTED)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.reason_code, CODE_ALREADY_TERMINAL)

    def test_cli_cancel_unknown_operation_status_is_usage_error(self):
        result = run_cli(self._argv("--operation-status", "bogus"))
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
        self.assertEqual(result.reason_code, CODE_MALFORMED_OPERATION)

    def test_cli_cancel_stale_version_is_rejected(self):
        result = run_cli(self._argv("--expected-version", "4", "--current-version", "5"))
        self.assertEqual(result.status, CLI_STATUS_REJECTED)
        self.assertEqual(result.reason_code, CODE_STALE_VERSION)

    def test_cli_cancel_malformed_version_option_is_usage_error(self):
        result = run_cli(self._argv("--current-version", "abc"))
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
        self.assertEqual(result.reason_code, CODE_MALFORMED_OPTION)

    def test_cli_cancel_padded_operation_id_is_usage_error(self):
        # The same padded-id target passed through the CLI must fail closed (usage
        # error) rather than be stripped into the canonical operation and cancelled.
        for padded in (" op-123", "op-123 ", " op-123 "):
            with self.subTest(operation_id=padded):
                argv = [
                    "command",
                    "cancel",
                    "--operation-id",
                    padded,
                    "--key",
                    "cancel-key",
                    "--operation-command-type",
                    "create_project",
                    "--operation-key",
                    "orig-key",
                    "--operation-status",
                    OP_RUNNING,
                ]
                result = run_cli(argv)
                self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
                self.assertEqual(result.reason_code, CODE_MALFORMED_OPERATION_ID)
                self.assertIsNone(result.binding["decision"]["operation"])

    def test_cli_cancel_does_not_mutate_argv(self):
        argv = self._argv("--operation-status", OP_RUNNING)
        snapshot = list(argv)
        run_cli(argv)
        self.assertEqual(argv, snapshot)


if __name__ == "__main__":
    unittest.main()
