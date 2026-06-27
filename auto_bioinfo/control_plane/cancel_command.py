"""Local cancel-command contract foundation (WP-04j / T-04-10).

The smallest deterministic, *local* contract layer the control plane needs so a
future API/CLI can answer one question about a long-running operation — *may this
operation be cancelled, given the facts the caller supplies?* — **without ever
killing, interrupting, dequeuing, or otherwise touching a real worker, process,
job, queue, scheduler, or broker**.

This sits beside the WP-04g command API and the WP-04h operation resource: where
:func:`auto_bioinfo.control_plane.command_api.evaluate_command_request` decides
whether a *mutating* command may be applied, and
:mod:`auto_bioinfo.control_plane.operation_resource` models *what the caller
tracks afterwards*, this module decides — purely, from explicit facts — whether a
cancel command may move a tracked operation into the bounded ``cancelled``
terminal state, and (only when that move is valid) projects the resulting
cancelled operation record.  "Cancellation" here is modelled as a deterministic
*command/state decision only*, never as real worker cancellation or process
control.

Design constraints (WP-04j), mirroring the WP-04g command-API and WP-04h
operation-resource style:

- **Pure and deterministic.** :func:`evaluate_cancel_request` and every helper is
  a total function of its explicit in-memory inputs.  There is no I/O whatsoever:
  no file access, no network, no environment inspection, **no real clock**, no
  threads, async worker, scheduler, broker, queue, DB, outbox, lock, process
  signal, or command execution side effect.  Timestamps are recorded only when
  the *caller* supplies them.  Inputs are never mutated in place; the operation
  record is evolved into a fresh value via the WP-04h ``apply_transition``.
- **Fail closed.** Every uncertainty resolves to a *non-cancelling* decision.  A
  malformed operation id, a missing/blank/malformed cancel-command identity, a
  stale or malformed version fact, a missing or malformed operation record, an
  operation-id mismatch, an unsupported or already-terminal operation state, a
  duplicate cancel of an already-cancelled operation, a malformed reason, and any
  forbidden/ malformed authority fact all yield a bounded reason-coded decision —
  never silent cancellation and never an unhandled exception.
- **Bounded vocabulary.** The decision status is one of exactly four values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  A future HTTP/CLI adapter maps these categories to
  transport responses; callers branch on the machine-readable code, never the
  human message.
- **Exact binding.** Every decision records the target operation id, the cancel
  command's identity (type, idempotency key, derived fingerprint), the
  expected/current versions it considered, the observed source operation status,
  and the authority-fact keys it inspected, so the decision can be audited later.

This module defines a *contract* only.  It does not open a socket, register a
route, run a real HTTP server, persist anything, execute or cancel a command,
signal a process, dequeue a job, or expose any OpenAPI/auth surface — those are
out of scope for T-04-10 (see the OpenAPI/auth slices T-04-11..12).  It only
decides, purely, from the facts it is handed, and an *accepted* decision is a
bounded ``cancelled`` operation *value*, never a real interruption.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .command_api import MAX_IDEMPOTENCY_KEY_LENGTH, command_fingerprint
from .operation_resource import (
    STATUS_CANCELLED as OPERATION_STATUS_CANCELLED,
)
from .operation_resource import (
    OperationError,
    OperationRecord,
    apply_transition,
    can_transition,
    is_terminal_status,
    validate_operation_record,
)

# --- The cancel command's own command type ----------------------------------
# The cancel command is itself a mutating command; this is its stable type name,
# used to derive the command fingerprint that binds the request for audit.
CANCEL_COMMAND_TYPE = "cancel_operation"

# --- Bounds (so an unbounded input cannot exhaust a downstream store) --------
# An operation id is a non-blank single-line token of visible ASCII, capped to the
# same bound as the WP-04h operation resource so the two agree.
MAX_OPERATION_ID_LENGTH = 200
# A caller-supplied cancel reason is an opaque, bounded, printable-ASCII line.
MAX_REASON_LENGTH = 500
# A version's digit count is capped so a pathologically long numeric string is
# rejected as malformed rather than parsed.
MAX_VERSION_DIGITS = 18

# --- Forbidden authority facts ----------------------------------------------
# This contract has no power to cancel a real worker/process/job, so a caller may
# not assert that it does.  Any of these authority flags being truthy is a
# fail-closed condition: the cancel decision is a *value*, never a real
# interruption, and it refuses to pretend otherwise.
FORBIDDEN_AUTHORITY_FLAGS = frozenset(
    {
        "kills_worker",
        "kills_process",
        "interrupts_worker",
        "interrupts_process",
        "terminates_process",
        "signals_process",
        "dequeues_job",
        "drains_queue",
        "aborts_execution",
        "authorizes_real_execution",
        "real_execution_authorized",
        "bypasses_gates",
        "force",
    }
)

# --- Bounded status vocabulary ----------------------------------------------
# A small, stable set.  ``cancelled`` is the single proceed outcome (the supplied
# operation state makes the transition to ``cancelled`` valid); ``not_cancellable``
# is a legitimate-but-refused state (terminal/unsupported); ``version_conflict``
# is a stale optimistic-concurrency fact; ``invalid`` is a malformed request.
STATUS_CANCELLED = "cancelled"
STATUS_NOT_CANCELLABLE = "not_cancellable"
STATUS_VERSION_CONFLICT = "version_conflict"
STATUS_INVALID = "invalid"

STATUSES = (
    STATUS_CANCELLED,
    STATUS_NOT_CANCELLABLE,
    STATUS_VERSION_CONFLICT,
    STATUS_INVALID,
)

# --- Stable reason codes ----------------------------------------------------
# Callers branch on these, so they must stay stable.
# cancelled:
CODE_CANCELLED = "CANCEL_OK"
# not_cancellable (legitimate request, refused by the operation's state):
CODE_ALREADY_CANCELLED = "CANCEL_ALREADY_CANCELLED"
CODE_ALREADY_TERMINAL = "CANCEL_ALREADY_TERMINAL"
CODE_UNSUPPORTED_STATE = "CANCEL_UNSUPPORTED_STATE"
# version_conflict:
CODE_STALE_VERSION = "CANCEL_STALE_VERSION"
# invalid (fail closed):
CODE_MALFORMED_OPERATION_ID = "CANCEL_MALFORMED_OPERATION_ID"
CODE_MISSING_COMMAND_IDENTITY = "CANCEL_MISSING_COMMAND_IDENTITY"
CODE_MALFORMED_IDEMPOTENCY_KEY = "CANCEL_MALFORMED_IDEMPOTENCY_KEY"
CODE_MALFORMED_VERSION = "CANCEL_MALFORMED_VERSION"
CODE_MISSING_EXPECTED_VERSION = "CANCEL_MISSING_EXPECTED_VERSION"
CODE_MISSING_OPERATION = "CANCEL_MISSING_OPERATION"
CODE_MALFORMED_OPERATION = "CANCEL_MALFORMED_OPERATION"
CODE_OPERATION_MISMATCH = "CANCEL_OPERATION_MISMATCH"
CODE_MALFORMED_REASON = "CANCEL_MALFORMED_REASON"
CODE_MALFORMED_AUTHORITY = "CANCEL_MALFORMED_AUTHORITY"
CODE_FORBIDDEN_AUTHORITY = "CANCEL_FORBIDDEN_AUTHORITY"

REASON_CODES = (
    CODE_CANCELLED,
    CODE_ALREADY_CANCELLED,
    CODE_ALREADY_TERMINAL,
    CODE_UNSUPPORTED_STATE,
    CODE_STALE_VERSION,
    CODE_MALFORMED_OPERATION_ID,
    CODE_MISSING_COMMAND_IDENTITY,
    CODE_MALFORMED_IDEMPOTENCY_KEY,
    CODE_MALFORMED_VERSION,
    CODE_MISSING_EXPECTED_VERSION,
    CODE_MISSING_OPERATION,
    CODE_MALFORMED_OPERATION,
    CODE_OPERATION_MISMATCH,
    CODE_MALFORMED_REASON,
    CODE_MALFORMED_AUTHORITY,
    CODE_FORBIDDEN_AUTHORITY,
)

# The status each reason code resolves to, so a future adapter can map a category
# to a transport status without re-deriving it from the code.
_CODE_STATUS = {
    CODE_CANCELLED: STATUS_CANCELLED,
    CODE_ALREADY_CANCELLED: STATUS_NOT_CANCELLABLE,
    CODE_ALREADY_TERMINAL: STATUS_NOT_CANCELLABLE,
    CODE_UNSUPPORTED_STATE: STATUS_NOT_CANCELLABLE,
    CODE_STALE_VERSION: STATUS_VERSION_CONFLICT,
    CODE_MALFORMED_OPERATION_ID: STATUS_INVALID,
    CODE_MISSING_COMMAND_IDENTITY: STATUS_INVALID,
    CODE_MALFORMED_IDEMPOTENCY_KEY: STATUS_INVALID,
    CODE_MALFORMED_VERSION: STATUS_INVALID,
    CODE_MISSING_EXPECTED_VERSION: STATUS_INVALID,
    CODE_MISSING_OPERATION: STATUS_INVALID,
    CODE_MALFORMED_OPERATION: STATUS_INVALID,
    CODE_OPERATION_MISMATCH: STATUS_INVALID,
    CODE_MALFORMED_REASON: STATUS_INVALID,
    CODE_MALFORMED_AUTHORITY: STATUS_INVALID,
    CODE_FORBIDDEN_AUTHORITY: STATUS_INVALID,
}


# --- Small, pure predicates --------------------------------------------------


def _is_positive_int(value: Any) -> bool:
    """A real positive integer — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_visible_ascii_token(value: str) -> bool:
    """True iff every character is visible ASCII (no spaces/controls, 0x21–0x7e)."""
    return bool(value) and all("\x21" <= ch <= "\x7e" for ch in value)


def _is_printable_ascii_line(value: str) -> bool:
    """True iff every character is printable ASCII incl. space (0x20–0x7e)."""
    return bool(value) and all("\x20" <= ch <= "\x7e" for ch in value)


# --- The cancel command request value ---------------------------------------


@dataclass(frozen=True)
class CancelCommand:
    """A request to cancel a tracked operation, as a pure in-memory contract value.

    Fields:

    - ``operation_id`` — the stable identity of the operation to cancel;
    - ``idempotency_key`` — the cancel command's own idempotency key (the cancel
      command is itself a mutating command, so a non-blank key is required to bind
      its identity, mirroring the WP-04g command API);
    - ``command_type`` — the cancel command's type (defaults to
      :data:`CANCEL_COMMAND_TYPE`); used to derive the audit fingerprint;
    - ``expected_version`` — an optional optimistic-concurrency expected version,
      checked only when the caller also supplies the authoritative current version;
    - ``reason`` — an optional, bounded human reason recorded into the cancelled
      operation's terminal error payload;
    - ``updated_at`` — an optional caller-supplied timestamp for the cancelled
      transition (this module never reads a real clock);
    - ``authority`` — optional caller-supplied authority facts; this contract has
      no power to cancel a real worker, so any forbidden flag being truthy fails
      closed.

    This object holds no transport, connection, or execution state — it is the
    parsed *facts* a future adapter would hand to :func:`evaluate_cancel_request`.
    It never names, signals, or controls a real worker/process/job.
    """

    operation_id: str
    idempotency_key: str
    command_type: str = CANCEL_COMMAND_TYPE
    expected_version: int | None = None
    reason: str = ""
    updated_at: str | None = None
    authority: Mapping[str, Any] | None = None

    def fingerprint(self) -> str:
        """A stable content fingerprint over the cancel command's identity/target.

        Reuses the WP-04g command-API fingerprint facility so the cancel command
        is bound the same deterministic, key-order-independent way every other
        command is.
        """
        return command_fingerprint(self.command_type, {"operation_id": self.operation_id})


# --- The deterministic cancel decision --------------------------------------


@dataclass(frozen=True)
class CancelDecision:
    """The deterministic, reason-coded outcome of a cancel-command evaluation.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  ``binding`` records the exact facts considered (target
    operation id, cancel-command identity, versions, observed source status, and
    inspected authority keys) so the decision can be audited.  ``operation`` is the
    projected *cancelled* operation record (as a plain dict) — present only on an
    accepted ``cancelled`` decision, and is a pure value, never a real
    interruption.
    """

    status: str
    reason_code: str
    message: str
    binding: dict[str, Any] = field(default_factory=dict)
    operation: dict[str, Any] | None = None

    @property
    def cancelled(self) -> bool:
        """The single proceed-and-cancel outcome."""
        return self.status == STATUS_CANCELLED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "cancelled": self.cancelled,
            "binding": dict(self.binding),
            "operation": dict(self.operation) if self.operation is not None else None,
        }


def _binding(
    *,
    operation_id: Any,
    command_type: Any,
    idempotency_key: Any,
    fingerprint: str,
    expected_version: int | None,
    current_version: int | None,
    operation_status: Any,
    authority_keys: list[str],
) -> dict[str, Any]:
    """Assemble the deterministic audit binding for a decision."""
    return {
        "operation_id": operation_id,
        "command_type": command_type,
        "idempotency_key": idempotency_key,
        "command_fingerprint": fingerprint,
        "expected_version": expected_version,
        "current_version": current_version,
        "operation_status": operation_status,
        "authority_keys": authority_keys,
    }


def _validate_operation_id(operation_id: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the target operation id is unusable, else ``None``.

    The id is validated **exactly as supplied** — it is never stripped or otherwise
    normalised.  A value padded with leading/trailing whitespace (e.g. ``" op-123 "``)
    is therefore rejected as malformed rather than silently retargeted at a *different*
    operation (``"op-123"``): the visible-ASCII-token rule already forbids spaces and
    control characters, so the fingerprint/binding and the operation-id comparison stay
    bound to the precise token the caller handed in (fail closed for malformed ids).
    """
    if not isinstance(operation_id, str) or not operation_id:
        return (CODE_MALFORMED_OPERATION_ID, "operation_id must be a non-blank string")
    if len(operation_id) > MAX_OPERATION_ID_LENGTH:
        return (
            CODE_MALFORMED_OPERATION_ID,
            f"operation_id length {len(operation_id)} exceeds the maximum of {MAX_OPERATION_ID_LENGTH}",
        )
    if not _is_visible_ascii_token(operation_id):
        return (
            CODE_MALFORMED_OPERATION_ID,
            "operation_id must be a single-line token of visible ASCII (no spaces or control characters)",
        )
    return None


def _validate_command_identity(command_type: Any, idempotency_key: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the cancel command identity is unusable, else ``None``.

    A cancel command is a mutating command: it must name a non-blank command type
    and carry a well-formed, non-blank idempotency key so it can be deduplicated
    and audited like every other mutating command.
    """
    if not (isinstance(command_type, str) and command_type.strip()):
        return (CODE_MISSING_COMMAND_IDENTITY, "a cancel command requires a non-blank command_type")
    if not (isinstance(idempotency_key, str) and idempotency_key):
        return (CODE_MISSING_COMMAND_IDENTITY, "a cancel command requires a non-blank idempotency_key")
    if len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        return (
            CODE_MALFORMED_IDEMPOTENCY_KEY,
            f"idempotency_key length {len(idempotency_key)} exceeds the maximum of {MAX_IDEMPOTENCY_KEY_LENGTH}",
        )
    if not _is_visible_ascii_token(idempotency_key):
        return (
            CODE_MALFORMED_IDEMPOTENCY_KEY,
            "idempotency_key must be a single-line token of visible ASCII (no spaces or control characters)",
        )
    return None


def _validate_expected_version(expected_version: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the expected version field is malformed, else ``None``.

    ``None`` (absent) is permitted; when present it must be a real positive
    integer with a bounded digit count.  Whether it is *required* is decided later
    by the optimistic-concurrency check.
    """
    if expected_version is None:
        return None
    if not _is_positive_int(expected_version):
        return (CODE_MALFORMED_VERSION, "expected_version, when supplied, must be a positive integer")
    if len(str(expected_version)) > MAX_VERSION_DIGITS:
        return (CODE_MALFORMED_VERSION, f"expected_version has more than {MAX_VERSION_DIGITS} digits")
    return None


def _validate_reason(reason: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the optional cancel reason is malformed, else ``None``.

    The empty string means "no reason"; any non-empty reason must be a bounded,
    printable-ASCII single line.
    """
    if reason == "":
        return None
    if not isinstance(reason, str):
        return (CODE_MALFORMED_REASON, "reason, when supplied, must be a string")
    if len(reason) > MAX_REASON_LENGTH or not _is_printable_ascii_line(reason):
        return (CODE_MALFORMED_REASON, f"reason must be a printable single-line string within {MAX_REASON_LENGTH} characters")
    return None


def _validate_authority(authority: Any) -> tuple[str, str] | None:
    """Return ``(code, message)`` if the optional authority facts are unusable, else ``None``.

    ``None`` (absent) is permitted.  When present it must be a mapping with string
    keys, and no :data:`FORBIDDEN_AUTHORITY_FLAGS` key may be truthy — this
    contract cannot cancel a real worker, so it refuses to accept a fact that
    claims it can.
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
                f"authority flag {flag!r} is forbidden: this contract cannot cancel a real worker/process/job",
            )
    return None


def evaluate_cancel_request(
    request: CancelCommand,
    *,
    operation: OperationRecord | None,
    current_version: int | None = None,
) -> CancelDecision:
    """Decide whether ``request`` may cancel ``operation``, fail-closed.

    A pure, deterministic function returning a bounded :class:`CancelDecision` (it
    never raises for a domain condition; the operation record is *evolved* into a
    fresh value, never mutated, and no real worker/process/job is touched).
    Precedence:

    1. Validate the target operation id, the cancel command's identity (non-blank
       type + well-formed key), the optional expected version, reason, and
       authority facts → otherwise ``invalid`` (or ``invalid`` for a forbidden
       authority flag).
    2. Require a well-formed operation record whose id matches the request's
       target; a missing record, a malformed record, or an id mismatch →
       ``invalid``.
    3. Optimistic concurrency: only when ``current_version`` is supplied, the
       expected version is required and must equal it; a missing/malformed/stale
       version → ``invalid``/``version_conflict``.
    4. State: an already-cancelled operation, another already-terminal operation,
       or a state from which ``cancelled`` is not reachable → ``not_cancellable``.
       Otherwise the transition is valid → ``cancelled``, and the decision carries
       the projected cancelled operation record (a pure value).
    """
    # 1. Request-shape validation (operation id, identity, version, reason, authority).
    op_id_error = _validate_operation_id(request.operation_id)
    # A valid operation id is a visible-ASCII token with no surrounding whitespace, so
    # the cancel target is the id exactly as supplied — it is never stripped into a
    # different value before the operation-record id comparison below.
    op_id = request.operation_id

    fingerprint = ""
    try:
        fingerprint = request.fingerprint()
    except (TypeError, ValueError):
        # A non-canonicalisable identity cannot be fingerprinted; the decision
        # still binds an empty fingerprint rather than raising.
        fingerprint = ""

    authority_keys = sorted(str(k) for k in request.authority) if isinstance(request.authority, Mapping) else []

    def _invalid(code: str, message: str, *, status_value: Any = None) -> CancelDecision:
        return CancelDecision(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            binding=_binding(
                operation_id=request.operation_id,
                command_type=request.command_type,
                idempotency_key=request.idempotency_key,
                fingerprint=fingerprint,
                expected_version=request.expected_version,
                current_version=current_version,
                operation_status=status_value,
                authority_keys=authority_keys,
            ),
        )

    for error in (
        op_id_error,
        _validate_command_identity(request.command_type, request.idempotency_key),
        _validate_expected_version(request.expected_version),
        _validate_reason(request.reason),
        _validate_authority(request.authority),
    ):
        if error is not None:
            code, message = error
            return _invalid(code, message)

    # 2. The operation record must be present, well-formed, and the same operation.
    if operation is None:
        return _invalid(CODE_MISSING_OPERATION, "no operation record supplied; cannot cancel an unknown operation")
    record_errors = validate_operation_record(operation)
    if record_errors:
        ecode, emessage = record_errors[0]
        return _invalid(CODE_MALFORMED_OPERATION, f"operation record is malformed ({ecode}): {emessage}")
    if operation.operation_id != op_id:
        return _invalid(
            CODE_OPERATION_MISMATCH,
            f"operation record id {operation.operation_id!r} does not match the request target {op_id!r}",
            status_value=operation.status,
        )

    status = operation.status

    # 3. Optimistic concurrency, enforced only when the caller supplies the
    #    authoritative current version of the operation/resource.
    if current_version is not None:
        if not _is_positive_int(current_version):
            return _invalid(CODE_MALFORMED_VERSION, "current_version, when supplied, must be a positive integer", status_value=status)
        if request.expected_version is None:
            return _invalid(
                CODE_MISSING_EXPECTED_VERSION,
                "this cancel command requires an expected_version for optimistic concurrency",
                status_value=status,
            )
        if request.expected_version != current_version:
            return _invalid(
                CODE_STALE_VERSION,
                f"expected version {request.expected_version} does not match the current version {current_version}; the operation changed (fail closed)",
                status_value=status,
            )

    # 4. State: only a non-terminal operation from which ``cancelled`` is reachable
    #    may be cancelled.  An already-terminal operation (including a duplicate
    #    cancel of an already-cancelled one) and an unsupported state fail closed.
    if is_terminal_status(status):
        if status == OPERATION_STATUS_CANCELLED:
            return _invalid_state(
                request,
                fingerprint,
                current_version,
                authority_keys,
                status,
                CODE_ALREADY_CANCELLED,
                "operation is already cancelled; a duplicate cancel is not allowed (fail closed)",
            )
        return _invalid_state(
            request,
            fingerprint,
            current_version,
            authority_keys,
            status,
            CODE_ALREADY_TERMINAL,
            f"operation is already terminal ({status}); it cannot be cancelled",
        )
    if not can_transition(status, OPERATION_STATUS_CANCELLED):
        return _invalid_state(
            request, fingerprint, current_version, authority_keys, status, CODE_UNSUPPORTED_STATE, f"operation state {status!r} does not support cancellation"
        )

    # The transition is valid: project a fresh cancelled operation record.  This is
    # a pure value transition (apply_transition never mutates ``operation`` and
    # touches no real worker); a defensive guard maps any residual OperationError
    # to a fail-closed malformed-operation decision rather than raising.
    error_payload = {"reason_code": CODE_CANCELLED, "cancel_reason": request.reason} if request.reason else None
    try:
        cancelled = apply_transition(operation, OPERATION_STATUS_CANCELLED, error=error_payload, updated_at=request.updated_at)
    except OperationError as exc:
        return _invalid(CODE_MALFORMED_OPERATION, f"operation could not be cancelled ({exc.code}): {exc}", status_value=status)

    return CancelDecision(
        status=STATUS_CANCELLED,
        reason_code=CODE_CANCELLED,
        message="cancellation is allowed; the operation is projected to the cancelled terminal state (a value, not a real interruption)",
        binding=_binding(
            operation_id=request.operation_id,
            command_type=request.command_type,
            idempotency_key=request.idempotency_key,
            fingerprint=fingerprint,
            expected_version=request.expected_version,
            current_version=current_version,
            operation_status=status,
            authority_keys=authority_keys,
        ),
        operation=cancelled.to_dict(),
    )


def _invalid_state(
    request: CancelCommand,
    fingerprint: str,
    current_version: int | None,
    authority_keys: list[str],
    status: Any,
    code: str,
    message: str,
) -> CancelDecision:
    """Build a fail-closed ``not_cancellable`` decision for a refused operation state."""
    return CancelDecision(
        status=_CODE_STATUS[code],
        reason_code=code,
        message=message,
        binding=_binding(
            operation_id=request.operation_id,
            command_type=request.command_type,
            idempotency_key=request.idempotency_key,
            fingerprint=fingerprint,
            expected_version=request.expected_version,
            current_version=current_version,
            operation_status=status,
            authority_keys=authority_keys,
        ),
    )


__all__ = [
    "CANCEL_COMMAND_TYPE",
    "MAX_OPERATION_ID_LENGTH",
    "MAX_REASON_LENGTH",
    "MAX_VERSION_DIGITS",
    "FORBIDDEN_AUTHORITY_FLAGS",
    "STATUS_CANCELLED",
    "STATUS_NOT_CANCELLABLE",
    "STATUS_VERSION_CONFLICT",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_CANCELLED",
    "CODE_ALREADY_CANCELLED",
    "CODE_ALREADY_TERMINAL",
    "CODE_UNSUPPORTED_STATE",
    "CODE_STALE_VERSION",
    "CODE_MALFORMED_OPERATION_ID",
    "CODE_MISSING_COMMAND_IDENTITY",
    "CODE_MALFORMED_IDEMPOTENCY_KEY",
    "CODE_MALFORMED_VERSION",
    "CODE_MISSING_EXPECTED_VERSION",
    "CODE_MISSING_OPERATION",
    "CODE_MALFORMED_OPERATION",
    "CODE_OPERATION_MISMATCH",
    "CODE_MALFORMED_REASON",
    "CODE_MALFORMED_AUTHORITY",
    "CODE_FORBIDDEN_AUTHORITY",
    "REASON_CODES",
    "CancelCommand",
    "CancelDecision",
    "evaluate_cancel_request",
]
