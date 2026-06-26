"""Operation-resource state/result contract (WP-04h / T-04-08).

The smallest deterministic, *local* contract layer the control plane needs so a
future polling API can represent a long-running command's progress as an
**operation resource** — without yet running anything asynchronously.  An
operation here is a pure value: it binds the originating command's identity to a
bounded lifecycle status and an optional terminal result/error, and it knows how
to project itself for a transport adapter.  "Async operation" is modelled as a
deterministic *state/result contract only*, never as actual asynchronous
execution.

This sits beside the WP-04g command API: where
:func:`auto_bioinfo.control_plane.command_api.evaluate_command_request` decides
*whether* a mutating command may be applied, this module models *what the caller
tracks afterwards* — the operation the accepted command spawns, the bounded set
of states it can move through, and the immutable terminal outcome it eventually
reaches.

Design constraints (WP-04h), mirroring the WP-04c state-machine and WP-04g
command-API style:

- **Pure and deterministic.** Every function here is a total function of its
  explicit in-memory inputs.  There is no I/O whatsoever: no file access, no
  network, no environment inspection, **no real clock**, no threads, async
  worker, scheduler, broker, queue, DB, outbox, lock, or command execution side
  effect.  Timestamps are recorded only when the *caller* supplies them; this
  module never reads the wall clock.  Inputs are never mutated in place.
- **Fail closed.** Every uncertainty resolves to a refusal.  A malformed
  operation id, a malformed/unknown status, an illegal transition, a mutation of
  an already-terminal operation (a duplicate terminal update), missing command
  identity facts, and a status/payload mismatch all raise a bounded
  :class:`OperationError` carrying a stable code, or — for the projection path —
  yield a ``malformed`` projection.  Nothing is silently normalised into
  success.
- **Bounded vocabulary.** The status is one of exactly five values
  (:data:`OPERATION_STATUSES`); the allowed transitions are an explicit, small
  table (:data:`ALLOWED_TRANSITIONS`); error/projection codes are a small, stable
  set.  A future HTTP adapter maps these categories to transport responses;
  callers branch on the machine-readable code, never the human message.
- **Exact binding.** Every operation records the exact originating command
  identity (command type plus a command fingerprint and/or idempotency key) so a
  later request can be tied back to the command that produced it.

This module defines a *contract* only.  It does not open a socket, register a
route, run a real HTTP server, persist an operation, execute a command, poll, or
expose any CLI/OpenAPI surface — persistence and scheduling are the caller's
responsibility; this layer only computes, purely, from the facts it is handed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .command_api import MAX_IDEMPOTENCY_KEY_LENGTH, CommandApiResult

# --- Bounded operation status vocabulary ------------------------------------
# A small, stable lifecycle: an operation is accepted (``pending``), may be
# observed in progress (``running``), and ends in exactly one terminal outcome
# (``succeeded`` / ``failed`` / ``cancelled``).  These strings are part of the
# contract — callers and a future polling API switch on them, so they must stay
# stable.
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

OPERATION_STATUSES = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CANCELLED,
)

# Terminal states are immutable: once an operation reaches one, no further
# transition (including a repeated terminal update) is allowed.
TERMINAL_STATUSES = frozenset({STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED})
# A fresh operation may only start in a non-terminal state (it has not run yet).
NON_TERMINAL_STATUSES = frozenset({STATUS_PENDING, STATUS_RUNNING})

# --- Explicit, bounded transition table -------------------------------------
# The only legal moves.  Terminal states have no outgoing edges, which is what
# makes a terminal operation immutable and a duplicate terminal update illegal.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_PENDING: frozenset({STATUS_RUNNING, STATUS_FAILED, STATUS_CANCELLED}),
    STATUS_RUNNING: frozenset({STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED}),
    STATUS_SUCCEEDED: frozenset(),
    STATUS_FAILED: frozenset(),
    STATUS_CANCELLED: frozenset(),
}

# --- Bounded projection categories ------------------------------------------
# What a transport adapter renders: a clear distinction between an operation that
# is accepted-but-not-terminal, one that finished successfully, one that failed,
# one that was cancelled, and a malformed operation whose facts cannot be
# trusted.  These are derived deterministically from the status (or from a
# validation failure for ``malformed``).
PROJECTION_ACCEPTED = "accepted"
PROJECTION_SUCCEEDED = "succeeded"
PROJECTION_FAILED = "failed"
PROJECTION_CANCELLED = "cancelled"
PROJECTION_MALFORMED = "malformed"

PROJECTION_CATEGORIES = (
    PROJECTION_ACCEPTED,
    PROJECTION_SUCCEEDED,
    PROJECTION_FAILED,
    PROJECTION_CANCELLED,
    PROJECTION_MALFORMED,
)

_STATUS_PROJECTION = {
    STATUS_PENDING: PROJECTION_ACCEPTED,
    STATUS_RUNNING: PROJECTION_ACCEPTED,
    STATUS_SUCCEEDED: PROJECTION_SUCCEEDED,
    STATUS_FAILED: PROJECTION_FAILED,
    STATUS_CANCELLED: PROJECTION_CANCELLED,
}

# --- Stable error / reason codes --------------------------------------------
# Callers branch on these, so they must stay stable.
CODE_MALFORMED_OPERATION_ID = "OPERATION_MALFORMED_ID"
CODE_MALFORMED_STATUS = "OPERATION_MALFORMED_STATUS"
CODE_MISSING_COMMAND_IDENTITY = "OPERATION_MISSING_COMMAND_IDENTITY"
CODE_MALFORMED_FINGERPRINT = "OPERATION_MALFORMED_FINGERPRINT"
CODE_MALFORMED_IDEMPOTENCY_KEY = "OPERATION_MALFORMED_IDEMPOTENCY_KEY"
CODE_MALFORMED_TIMESTAMP = "OPERATION_MALFORMED_TIMESTAMP"
CODE_MALFORMED_PAYLOAD = "OPERATION_MALFORMED_PAYLOAD"
CODE_INVALID_INITIAL_STATUS = "OPERATION_INVALID_INITIAL_STATUS"
CODE_INVALID_TRANSITION = "OPERATION_INVALID_TRANSITION"
CODE_TERMINAL_IMMUTABLE = "OPERATION_TERMINAL_IMMUTABLE"
CODE_UNEXPECTED_PAYLOAD = "OPERATION_UNEXPECTED_PAYLOAD"
CODE_COMMAND_NOT_ADMITTED = "OPERATION_COMMAND_NOT_ADMITTED"

ERROR_CODES = (
    CODE_MALFORMED_OPERATION_ID,
    CODE_MALFORMED_STATUS,
    CODE_MISSING_COMMAND_IDENTITY,
    CODE_MALFORMED_FINGERPRINT,
    CODE_MALFORMED_IDEMPOTENCY_KEY,
    CODE_MALFORMED_TIMESTAMP,
    CODE_MALFORMED_PAYLOAD,
    CODE_INVALID_INITIAL_STATUS,
    CODE_INVALID_TRANSITION,
    CODE_TERMINAL_IMMUTABLE,
    CODE_UNEXPECTED_PAYLOAD,
    CODE_COMMAND_NOT_ADMITTED,
)

# Bounds: an operation id and idempotency key are non-blank single-line tokens of
# visible ASCII, capped so an unbounded value cannot exhaust a downstream store.
MAX_OPERATION_ID_LENGTH = 200
# A caller-supplied timestamp is an opaque, bounded, printable-ASCII string (this
# module never parses it into a real time, so it stays clock-free).
MAX_TIMESTAMP_LENGTH = 64
# A SHA-256 command fingerprint (see ``core.ids.hash_payload``) is 64 lowercase
# hex characters.
_FINGERPRINT_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


# --- Typed error with a stable code -----------------------------------------


class OperationError(Exception):
    """A fail-closed operation-contract failure carrying a stable :attr:`code`.

    Every malformed construction, illegal transition, terminal-immutability
    violation, or missing-identity condition raises one of these so the failure
    is classified by a stable code (one of :data:`ERROR_CODES`) rather than only
    a prose message.
    """

    code: str = ""

    def __init__(self, message: str, *, code: str = "", operation_id: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.operation_id = operation_id


# --- Small, pure predicates --------------------------------------------------


def is_operation_status(value: Any) -> bool:
    """True iff ``value`` is one of the bounded operation statuses."""
    return isinstance(value, str) and value in OPERATION_STATUSES


def is_terminal_status(value: Any) -> bool:
    """True iff ``value`` is a terminal operation status."""
    return isinstance(value, str) and value in TERMINAL_STATUSES


def can_transition(source: Any, target: Any) -> bool:
    """True iff ``source -> target`` is an allowed operation transition.

    A pure lookup against :data:`ALLOWED_TRANSITIONS`; unknown endpoints and
    terminal sources (which have no outgoing edges) return ``False``.
    """
    if not (is_operation_status(source) and is_operation_status(target)):
        return False
    return target in ALLOWED_TRANSITIONS[source]


def _is_visible_ascii_token(value: str) -> bool:
    """True iff every character is visible ASCII (no spaces/controls, 0x21–0x7e)."""
    return bool(value) and all("\x21" <= ch <= "\x7e" for ch in value)


def _is_printable_ascii_line(value: str) -> bool:
    """True iff every character is printable ASCII incl. space (0x20–0x7e)."""
    return bool(value) and all("\x20" <= ch <= "\x7e" for ch in value)


# --- Field validators (fail-closed constructors) ----------------------------


def _validate_operation_id(operation_id: Any) -> str:
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise OperationError("operation id must be a non-blank string", code=CODE_MALFORMED_OPERATION_ID)
    token = operation_id.strip()
    if len(token) > MAX_OPERATION_ID_LENGTH:
        raise OperationError(
            f"operation id length {len(token)} exceeds the maximum of {MAX_OPERATION_ID_LENGTH}",
            code=CODE_MALFORMED_OPERATION_ID,
            operation_id=token,
        )
    if not _is_visible_ascii_token(token):
        raise OperationError(
            "operation id must be a single-line token of visible ASCII (no spaces or control characters)",
            code=CODE_MALFORMED_OPERATION_ID,
            operation_id=token,
        )
    return token


def _validate_command_identity(command_type: Any, command_fingerprint: Any, idempotency_key: Any, operation_id: str) -> tuple[str, str, str]:
    """Validate and normalise the originating command identity facts.

    An operation must name its originating command (a non-blank ``command_type``)
    and bind at least one durable identity fact — a command fingerprint and/or an
    idempotency key — so it can be tied back to the command that produced it.
    """
    if not isinstance(command_type, str) or not command_type.strip():
        raise OperationError(
            "an operation requires a non-blank originating command_type",
            code=CODE_MISSING_COMMAND_IDENTITY,
            operation_id=operation_id,
        )
    ctype = command_type.strip()

    fingerprint = _validate_fingerprint(command_fingerprint, operation_id)
    key = _validate_idempotency_key(idempotency_key, operation_id)
    if not fingerprint and not key:
        raise OperationError(
            "an operation requires at least one of command_fingerprint or idempotency_key",
            code=CODE_MISSING_COMMAND_IDENTITY,
            operation_id=operation_id,
        )
    return ctype, fingerprint, key


def _validate_fingerprint(command_fingerprint: Any, operation_id: str) -> str:
    """Validate an optional SHA-256 command fingerprint; ``""`` means absent."""
    if command_fingerprint is None or command_fingerprint == "":
        return ""
    if not isinstance(command_fingerprint, str):
        raise OperationError(
            "command_fingerprint, when supplied, must be a 64-character lowercase hex string",
            code=CODE_MALFORMED_FINGERPRINT,
            operation_id=operation_id,
        )
    if len(command_fingerprint) != _FINGERPRINT_LENGTH or any(ch not in _HEX_DIGITS for ch in command_fingerprint):
        raise OperationError(
            "command_fingerprint, when supplied, must be a 64-character lowercase hex string",
            code=CODE_MALFORMED_FINGERPRINT,
            operation_id=operation_id,
        )
    return command_fingerprint


def _validate_idempotency_key(idempotency_key: Any, operation_id: str) -> str:
    """Validate an optional idempotency key; ``""`` means absent."""
    if idempotency_key is None or idempotency_key == "":
        return ""
    if not isinstance(idempotency_key, str):
        raise OperationError(
            "idempotency_key, when supplied, must be a visible-ASCII token",
            code=CODE_MALFORMED_IDEMPOTENCY_KEY,
            operation_id=operation_id,
        )
    if len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH or not _is_visible_ascii_token(idempotency_key):
        raise OperationError(
            "idempotency_key, when supplied, must be a single-line visible-ASCII token within the length bound",
            code=CODE_MALFORMED_IDEMPOTENCY_KEY,
            operation_id=operation_id,
        )
    return idempotency_key


def _validate_timestamp(value: Any, label: str, operation_id: str) -> str | None:
    """Validate an optional caller-supplied timestamp string; ``None`` if absent.

    The timestamp is opaque and never parsed into a real time — this module is
    clock-free.  It only checks the value is a non-blank, bounded, printable-ASCII
    single line so a malformed marker fails closed rather than being stored.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise OperationError(
            f"{label}, when supplied, must be a non-blank caller-supplied timestamp string",
            code=CODE_MALFORMED_TIMESTAMP,
            operation_id=operation_id,
        )
    if len(value) > MAX_TIMESTAMP_LENGTH or not _is_printable_ascii_line(value):
        raise OperationError(
            f"{label}, when supplied, must be a printable single-line string within the length bound",
            code=CODE_MALFORMED_TIMESTAMP,
            operation_id=operation_id,
        )
    return value


def _validate_payload(value: Any, label: str, operation_id: str) -> dict[str, Any] | None:
    """Validate an optional terminal result/error payload; ``None`` if absent.

    A payload must be a plain mapping; it is shallow-copied into a new ``dict`` so
    the stored value is never an alias of the caller's mutable object.
    """
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise OperationError(
            f"{label}, when supplied, must be a mapping",
            code=CODE_MALFORMED_PAYLOAD,
            operation_id=operation_id,
        )
    return dict(value)


# --- The operation resource record ------------------------------------------


@dataclass(frozen=True)
class OperationRecord:
    """A long-running command's operation, as a pure in-memory contract value.

    Fields:

    - ``operation_id`` — the stable identity of this operation;
    - ``command_type`` / ``command_fingerprint`` / ``idempotency_key`` — the
      originating command identity (at least one of fingerprint/key is present);
    - ``status`` — the current bounded lifecycle status;
    - ``result`` / ``error`` — the optional terminal outcome payload (a success
      ``result`` or a failure/cancel ``error``); both are absent while
      non-terminal;
    - ``created_at`` / ``updated_at`` — optional caller-supplied timestamps (this
      module never reads a real clock).

    Construct via :func:`new_operation` and evolve via :func:`apply_transition`;
    both validate fail-closed.  The dataclass itself is an immutable value and
    carries no transport, connection, or execution state.
    """

    operation_id: str
    command_type: str
    status: str
    command_fingerprint: str = ""
    idempotency_key: str = ""
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def projection_category(self) -> str:
        return _STATUS_PROJECTION[self.status]

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the record (stable key order)."""
        return {
            "operation_id": self.operation_id,
            "command_type": self.command_type,
            "command_fingerprint": self.command_fingerprint,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "is_terminal": self.is_terminal,
            "result": dict(self.result) if self.result is not None else None,
            "error": dict(self.error) if self.error is not None else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _check_payload_for_status(status: str, result: dict[str, Any] | None, error: dict[str, Any] | None, operation_id: str) -> None:
    """Enforce which payloads a status may carry (fail-closed).

    - Non-terminal (``pending`` / ``running``): neither ``result`` nor ``error``.
    - ``succeeded``: an optional ``result``, never an ``error``.
    - ``failed`` / ``cancelled``: an optional ``error``, never a ``result``.
    """
    if status in NON_TERMINAL_STATUSES:
        if result is not None or error is not None:
            raise OperationError(
                f"a non-terminal operation ({status}) must not carry a result or error payload",
                code=CODE_UNEXPECTED_PAYLOAD,
                operation_id=operation_id,
            )
        return
    if status == STATUS_SUCCEEDED and error is not None:
        raise OperationError(
            "a succeeded operation must not carry an error payload",
            code=CODE_UNEXPECTED_PAYLOAD,
            operation_id=operation_id,
        )
    if status in (STATUS_FAILED, STATUS_CANCELLED) and result is not None:
        raise OperationError(
            f"a {status} operation must not carry a result payload",
            code=CODE_UNEXPECTED_PAYLOAD,
            operation_id=operation_id,
        )


def new_operation(
    *,
    operation_id: Any,
    command_type: Any,
    command_fingerprint: Any = "",
    idempotency_key: Any = "",
    status: Any = STATUS_PENDING,
    created_at: Any = None,
) -> OperationRecord:
    """Construct a fresh, validated operation, fail-closed.

    A new operation must start in a *non-terminal* status (it has not run yet):
    ``pending`` (the default) or ``running``.  Its originating command identity is
    required (a non-blank ``command_type`` plus at least one of
    ``command_fingerprint`` / ``idempotency_key``).  A terminal initial status, a
    malformed id/status/identity, or a malformed caller timestamp all raise
    :class:`OperationError` with a stable code.
    """
    op_id = _validate_operation_id(operation_id)
    if not is_operation_status(status):
        raise OperationError(
            f"status must be one of {OPERATION_STATUSES!r}, got {status!r}",
            code=CODE_MALFORMED_STATUS,
            operation_id=op_id,
        )
    if status not in NON_TERMINAL_STATUSES:
        raise OperationError(
            f"a new operation must start in a non-terminal status ({sorted(NON_TERMINAL_STATUSES)}), got {status!r}",
            code=CODE_INVALID_INITIAL_STATUS,
            operation_id=op_id,
        )
    ctype, fingerprint, key = _validate_command_identity(command_type, command_fingerprint, idempotency_key, op_id)
    created = _validate_timestamp(created_at, "created_at", op_id)
    return OperationRecord(
        operation_id=op_id,
        command_type=ctype,
        status=status,
        command_fingerprint=fingerprint,
        idempotency_key=key,
        result=None,
        error=None,
        created_at=created,
        updated_at=None,
    )


def apply_transition(
    record: OperationRecord,
    new_status: Any,
    *,
    result: Any = None,
    error: Any = None,
    updated_at: Any = None,
) -> OperationRecord:
    """Return a new operation advanced to ``new_status``, fail-closed.

    Never mutates ``record`` — returns a fresh :class:`OperationRecord`.  Refuses,
    with a stable code, to:

    - mutate an already-terminal operation, including a repeated terminal update
      (:data:`CODE_TERMINAL_IMMUTABLE`);
    - move to an unknown status (:data:`CODE_MALFORMED_STATUS`) or along an edge
      not in :data:`ALLOWED_TRANSITIONS` (:data:`CODE_INVALID_TRANSITION`);
    - attach a payload the target status may not carry
      (:data:`CODE_UNEXPECTED_PAYLOAD`).

    A success ``result`` or a failure/cancel ``error`` payload may be attached
    only on the matching terminal transition.  ``updated_at`` is an optional
    caller-supplied timestamp (the clock is never read here).
    """
    if not isinstance(record, OperationRecord):
        raise OperationError("record must be an OperationRecord", code=CODE_MALFORMED_PAYLOAD)
    if not is_operation_status(new_status):
        raise OperationError(
            f"new_status must be one of {OPERATION_STATUSES!r}, got {new_status!r}",
            code=CODE_MALFORMED_STATUS,
            operation_id=record.operation_id,
        )
    # Terminal immutability comes first: an already-terminal operation accepts no
    # further transition, so a duplicate terminal update fails closed here rather
    # than being re-applied.
    if record.is_terminal:
        raise OperationError(
            f"operation {record.operation_id!r} is already terminal ({record.status}); it is immutable",
            code=CODE_TERMINAL_IMMUTABLE,
            operation_id=record.operation_id,
        )
    if not can_transition(record.status, new_status):
        raise OperationError(
            f"illegal operation transition {record.status!r} -> {new_status!r}",
            code=CODE_INVALID_TRANSITION,
            operation_id=record.operation_id,
        )
    new_result = _validate_payload(result, "result", record.operation_id)
    new_error = _validate_payload(error, "error", record.operation_id)
    _check_payload_for_status(new_status, new_result, new_error, record.operation_id)
    updated = _validate_timestamp(updated_at, "updated_at", record.operation_id)
    return OperationRecord(
        operation_id=record.operation_id,
        command_type=record.command_type,
        status=new_status,
        command_fingerprint=record.command_fingerprint,
        idempotency_key=record.idempotency_key,
        result=new_result,
        error=new_error,
        created_at=record.created_at,
        updated_at=updated,
    )


# --- Deterministic projection for a future transport adapter ----------------


@dataclass(frozen=True)
class OperationProjection:
    """A transport-facing projection of an operation, deterministic and bounded.

    ``category`` is one of :data:`PROJECTION_CATEGORIES` — the clear distinction a
    future HTTP adapter needs between an accepted-but-not-terminal operation, a
    terminal success, a terminal failure, a terminal cancellation, and a
    ``malformed`` operation whose facts could not be validated.  ``terminal``
    flags a finished operation; ``operation`` is the validated record projection
    (or the raw facts for a malformed one); ``error_code`` carries the stable
    classification of *why* a malformed operation was rejected.
    """

    category: str
    terminal: bool
    operation: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    message: str = ""

    @property
    def is_malformed(self) -> bool:
        return self.category == PROJECTION_MALFORMED

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "terminal": self.terminal,
            "operation": dict(self.operation),
            "error_code": self.error_code,
            "message": self.message,
        }


def _raw_record_facts(record: OperationRecord) -> dict[str, Any]:
    """Best-effort raw projection of a *possibly malformed* record; never raises.

    Mirrors :meth:`OperationRecord.to_dict` for rendering a ``malformed``
    projection, but tolerates the bad facts a hand-built record can carry: where
    :meth:`OperationRecord.to_dict` unconditionally coerces a payload with
    ``dict(...)`` (correct for a validated record, but raising on a non-mapping
    ``result``/``error``), this passes a non-mapping payload through unchanged as a
    raw fact instead of coercing it, and computes ``is_terminal`` without a
    frozenset lookup that an unhashable status could break.  The result is the same
    bounded shape, computed defensively so the malformed projection path is total.
    """

    def _payload(value: Any) -> Any:
        if value is None:
            return None
        return dict(value) if isinstance(value, Mapping) else value

    return {
        "operation_id": record.operation_id,
        "command_type": record.command_type,
        "command_fingerprint": record.command_fingerprint,
        "idempotency_key": record.idempotency_key,
        "status": record.status,
        "is_terminal": isinstance(record.status, str) and record.status in TERMINAL_STATUSES,
        "result": _payload(record.result),
        "error": _payload(record.error),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def project_operation(record: Any) -> OperationProjection:
    """Project an operation for a transport adapter, never raising.

    For a well-formed :class:`OperationRecord` (re-validated here so a
    hand-built record cannot smuggle malformed facts past the projection), returns
    a projection whose ``category`` is derived from the status.  For anything that
    fails validation — a non-record, or a record with a malformed id/status/
    identity/payload — returns a ``malformed`` projection carrying the stable
    ``error_code`` instead of raising, so a malformed operation is still a
    bounded, renderable outcome.  The malformed branch builds its raw facts via
    :func:`_raw_record_facts` (not :meth:`OperationRecord.to_dict`, which can raise
    when coercing a non-mapping ``result``/``error``) so the promise of a
    never-raising projection holds even for a record carrying un-coercible
    payloads.
    """
    errors = validate_operation_record(record)
    if errors:
        code, message = errors[0]
        facts = _raw_record_facts(record) if isinstance(record, OperationRecord) else {}
        return OperationProjection(
            category=PROJECTION_MALFORMED,
            terminal=False,
            operation=facts,
            error_code=code,
            message=message,
        )
    assert isinstance(record, OperationRecord)  # guaranteed by an empty error list
    return OperationProjection(
        category=_STATUS_PROJECTION[record.status],
        terminal=record.is_terminal,
        operation=record.to_dict(),
    )


def validate_operation_record(record: Any) -> list[tuple[str, str]]:
    """Return ``[(code, message), ...]`` for every way ``record`` is malformed.

    An empty list means the record is a well-formed operation.  Mirrors the
    fail-closed checks of :func:`new_operation` / :func:`apply_transition` but as
    a non-raising audit so the projection path (and callers) can classify a record
    without a ``try``/``except``.  Each entry pairs a stable :data:`ERROR_CODES`
    code with a human-readable message.
    """
    if not isinstance(record, OperationRecord):
        return [(CODE_MALFORMED_PAYLOAD, "value is not an OperationRecord")]
    errors: list[tuple[str, str]] = []
    try:
        _validate_operation_id(record.operation_id)
    except OperationError as exc:
        errors.append((exc.code, str(exc)))
    if not is_operation_status(record.status):
        errors.append((CODE_MALFORMED_STATUS, f"status {record.status!r} is not a known operation status"))
    try:
        _validate_command_identity(record.command_type, record.command_fingerprint, record.idempotency_key, str(record.operation_id))
    except OperationError as exc:
        errors.append((exc.code, str(exc)))
    for label, value in (("result", record.result), ("error", record.error)):
        try:
            _validate_payload(value, label, str(record.operation_id))
        except OperationError as exc:
            errors.append((exc.code, str(exc)))
    for label, value in (("created_at", record.created_at), ("updated_at", record.updated_at)):
        try:
            _validate_timestamp(value, label, str(record.operation_id))
        except OperationError as exc:
            errors.append((exc.code, str(exc)))
    # Status/payload coherence — only meaningful once the status itself is known.
    if is_operation_status(record.status):
        try:
            _check_payload_for_status(
                record.status,
                record.result if isinstance(record.result, dict) else None,
                record.error if isinstance(record.error, dict) else None,
                str(record.operation_id),
            )
        except OperationError as exc:
            errors.append((exc.code, str(exc)))
    return errors


# --- Explicit, local command-decision -> operation adapter ------------------


def operation_from_command_result(
    result: Any,
    *,
    operation_id: Any,
    created_at: Any = None,
) -> OperationRecord:
    """Spawn a fresh ``pending`` operation from an *accepted* command decision.

    The small, explicit adapter the WO authorises: it takes a caller-supplied
    command decision (a :class:`~auto_bioinfo.control_plane.command_api.CommandApiResult`
    from :func:`~auto_bioinfo.control_plane.command_api.evaluate_command_request`)
    and a caller-supplied operation id, and binds them into a new ``pending``
    operation — carrying the command's type, fingerprint, and idempotency key from
    the decision's ``binding``.  It performs no execution, scheduling, or
    persistence.

    Only an *accepted* command decision may spawn an operation: a non-accepted
    decision (invalid, conflict, stale version, or even a recognised replay —
    whose operation the caller should look up rather than recreate) fails closed
    with :data:`CODE_COMMAND_NOT_ADMITTED`.
    """
    if not isinstance(result, CommandApiResult):
        raise OperationError(
            "result must be a CommandApiResult command decision",
            code=CODE_MALFORMED_PAYLOAD,
        )
    if not result.accepted:
        raise OperationError(
            f"command was not admitted (status {result.status!r}); only an accepted command spawns an operation",
            code=CODE_COMMAND_NOT_ADMITTED,
        )
    binding = result.binding or {}
    return new_operation(
        operation_id=operation_id,
        command_type=binding.get("command_type"),
        command_fingerprint=binding.get("command_fingerprint") or "",
        idempotency_key=binding.get("idempotency_key") or "",
        status=STATUS_PENDING,
        created_at=created_at,
    )


__all__ = [
    "STATUS_PENDING",
    "STATUS_RUNNING",
    "STATUS_SUCCEEDED",
    "STATUS_FAILED",
    "STATUS_CANCELLED",
    "OPERATION_STATUSES",
    "TERMINAL_STATUSES",
    "NON_TERMINAL_STATUSES",
    "ALLOWED_TRANSITIONS",
    "PROJECTION_ACCEPTED",
    "PROJECTION_SUCCEEDED",
    "PROJECTION_FAILED",
    "PROJECTION_CANCELLED",
    "PROJECTION_MALFORMED",
    "PROJECTION_CATEGORIES",
    "CODE_MALFORMED_OPERATION_ID",
    "CODE_MALFORMED_STATUS",
    "CODE_MISSING_COMMAND_IDENTITY",
    "CODE_MALFORMED_FINGERPRINT",
    "CODE_MALFORMED_IDEMPOTENCY_KEY",
    "CODE_MALFORMED_TIMESTAMP",
    "CODE_MALFORMED_PAYLOAD",
    "CODE_INVALID_INITIAL_STATUS",
    "CODE_INVALID_TRANSITION",
    "CODE_TERMINAL_IMMUTABLE",
    "CODE_UNEXPECTED_PAYLOAD",
    "CODE_COMMAND_NOT_ADMITTED",
    "ERROR_CODES",
    "MAX_OPERATION_ID_LENGTH",
    "MAX_TIMESTAMP_LENGTH",
    "OperationError",
    "OperationRecord",
    "OperationProjection",
    "is_operation_status",
    "is_terminal_status",
    "can_transition",
    "new_operation",
    "apply_transition",
    "project_operation",
    "validate_operation_record",
    "operation_from_command_result",
]
