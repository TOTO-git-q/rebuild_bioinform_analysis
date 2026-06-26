"""ApprovalRequest lifecycle (WP-04e / T-04-05).

The smallest deterministic, *local* lifecycle the control plane needs to drive a
human approval from request to a single terminal outcome, built as a thin,
backward-compatible wrapper over the existing
:class:`~auto_bioinfo.core.schemas.ApprovalRequest` /
:class:`~auto_bioinfo.core.schemas.ApprovalDecision` contracts and their
validators rather than a parallel mechanism.

Design constraints (WP-04e):

- **Pure and deterministic.** Every transition is a pure function of an explicit
  prior :class:`ApprovalLifecycleRecord` plus explicit inputs.  There is no I/O,
  no scheduler, no async worker, and no real-clock dependency: expiry is decided
  by comparing an explicit caller-supplied ``as_of`` to the request's explicit
  ``expires_at`` deadline, never by reading the wall clock.
- **Immutable records.** A transition returns a *new* frozen record; the prior
  one is never mutated in place, so an append-only history is preserved.
- **Single terminal outcome.** ``requested`` (pending) is the only non-terminal
  state.  ``granted``, ``rejected``, ``expired`` and ``cancelled`` are terminal:
  a terminal request can never be decided, decided again, cancelled, expired, or
  mutated back to pending.
- **Fail closed.** Missing request ids, subject/version mismatches, malformed
  lifecycle payloads, stale (superseded) versions, duplicate decisions, and any
  operation on a terminal request raise :class:`ApprovalLifecycleError` with a
  stable classification code rather than silently succeeding.

This module only models the lifecycle of a *request*; it does not evaluate any
A0–A3 gate or policy, expose any HTTP/CLI surface, or persist anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.common import validate_actor
from ..core.schemas import (
    APPROVAL_DECISIONS,
    APPROVAL_STATES,
    ApprovalDecision,
    ApprovalRequest,
    now_iso,
)
from ..core.validation import validate_approval_decision, validate_approval_request

# The single pending state and the four terminal states, derived from the
# authoritative APPROVAL_STATES vocabulary so this module cannot drift from it.
PENDING_STATE = "requested"
TERMINAL_STATES = ("granted", "rejected", "expired", "cancelled")
# A terminal decision maps to its lifecycle state: an "approved" decision grants
# the request, a "rejected" decision rejects it.
_DECISION_TO_STATE = {"approved": "granted", "rejected": "rejected"}

# Stable classification codes.  External callers/tests branch on these, so they
# must stay stable.  ``CODE_OK`` is unused as a raised code but documents intent.
CODE_OK = "APPROVAL_OK"
CODE_INVALID_REQUEST = "APPROVAL_INVALID_REQUEST"
CODE_MISSING_REQUEST_ID = "APPROVAL_MISSING_REQUEST_ID"
CODE_NOT_PENDING = "APPROVAL_NOT_PENDING"
CODE_TERMINAL_STATE = "APPROVAL_TERMINAL_STATE"
CODE_DUPLICATE_DECISION = "APPROVAL_DUPLICATE_DECISION"
CODE_SUBJECT_MISMATCH = "APPROVAL_SUBJECT_MISMATCH"
CODE_STALE_VERSION = "APPROVAL_STALE_VERSION"
CODE_MALFORMED_PAYLOAD = "APPROVAL_MALFORMED_PAYLOAD"
CODE_NOT_DUE = "APPROVAL_NOT_DUE"

ERROR_CODES = (
    CODE_INVALID_REQUEST,
    CODE_MISSING_REQUEST_ID,
    CODE_NOT_PENDING,
    CODE_TERMINAL_STATE,
    CODE_DUPLICATE_DECISION,
    CODE_SUBJECT_MISMATCH,
    CODE_STALE_VERSION,
    CODE_MALFORMED_PAYLOAD,
    CODE_NOT_DUE,
)


class ApprovalLifecycleError(RuntimeError):
    """A lifecycle operation could not be honoured (fails closed).

    ``code`` is one of :data:`ERROR_CODES` so callers can branch on the failure
    class without parsing the human-readable message.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _as_request_dict(request: ApprovalRequest | dict[str, Any]) -> dict[str, Any]:
    """Project an ApprovalRequest (dataclass or dict) to a plain dict copy."""
    if isinstance(request, ApprovalRequest):
        return request.to_dict()
    if isinstance(request, dict):
        return dict(request)
    raise ApprovalLifecycleError(
        f"approval request must be an ApprovalRequest or its dict projection, got {type(request).__name__}",
        code=CODE_MALFORMED_PAYLOAD,
    )


@dataclass(frozen=True)
class ApprovalLifecycleRecord:
    """An immutable snapshot of one approval request's lifecycle.

    ``request`` is the bound :class:`ApprovalRequest` projection (subject identity
    and the exact version under review).  ``state`` is the current lifecycle
    state.  ``expires_at`` is the explicit deadline used by :func:`expire`
    (empty string means the request never auto-expires).  ``decision`` is the
    bound :class:`ApprovalDecision` projection once decided, else ``None``.
    ``terminal_reason`` records the actor/reason/time of a cancel or expire.
    ``history`` is the ordered, append-only transition log.
    """

    request: dict[str, Any]
    state: str = PENDING_STATE
    expires_at: str = ""
    decision: dict[str, Any] | None = None
    terminal_reason: dict[str, Any] | None = None
    history: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def approval_request_id(self) -> str:
        return str(self.request.get("approval_request_id", ""))

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_pending(self) -> bool:
        return self.state == PENDING_STATE

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the record (stable key order)."""
        return {
            "approval_request_id": self.approval_request_id,
            "state": self.state,
            "is_terminal": self.is_terminal,
            "request": dict(self.request),
            "expires_at": self.expires_at,
            "decision": dict(self.decision) if self.decision is not None else None,
            "terminal_reason": dict(self.terminal_reason) if self.terminal_reason is not None else None,
            "history": [dict(entry) for entry in self.history],
        }


def _history_entry(action: str, state: str, *, as_of: str = "", detail: dict[str, Any] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"action": action, "state": state, "as_of": as_of}
    if detail:
        entry["detail"] = dict(detail)
    return entry


def _require_pending(record: ApprovalLifecycleRecord, operation: str) -> None:
    """Fail closed unless ``record`` is still pending.

    A terminal record yields :data:`CODE_TERMINAL_STATE`; any other non-pending
    state yields :data:`CODE_NOT_PENDING`.  Neither path can be mutated back to
    pending.
    """
    if record.is_terminal:
        raise ApprovalLifecycleError(
            f"cannot {operation}: approval request is terminal (state={record.state!r}); terminal requests are immutable",
            code=CODE_TERMINAL_STATE,
        )
    if not record.is_pending:
        raise ApprovalLifecycleError(
            f"cannot {operation}: approval request is not pending (state={record.state!r})",
            code=CODE_NOT_PENDING,
        )


def create_approval_request(
    request: ApprovalRequest | dict[str, Any],
    *,
    expires_at: str = "",
) -> ApprovalLifecycleRecord:
    """Open a fresh, pending lifecycle around ``request``.

    The request must be a valid :class:`ApprovalRequest` (or its dict projection)
    that carries a non-blank ``approval_request_id`` and is in the pending
    ``requested`` state.  ``expires_at`` is an optional explicit deadline used
    later by :func:`expire`.  Fails closed on an invalid request, a missing
    request id, or a non-pending starting state.
    """
    data = _as_request_dict(request)

    errors = validate_approval_request(data)
    if errors:
        raise ApprovalLifecycleError(
            f"invalid approval request: {'; '.join(errors)}",
            code=CODE_INVALID_REQUEST,
        )

    if not str(data.get("approval_request_id", "") or "").strip():
        raise ApprovalLifecycleError(
            "approval request is missing a non-blank approval_request_id",
            code=CODE_MISSING_REQUEST_ID,
        )

    state = data.get("state", PENDING_STATE)
    if state != PENDING_STATE:
        raise ApprovalLifecycleError(
            f"a fresh approval lifecycle must start pending ({PENDING_STATE!r}), got state={state!r}",
            code=CODE_NOT_PENDING,
        )

    if not isinstance(expires_at, str):
        raise ApprovalLifecycleError("expires_at must be a string deadline", code=CODE_MALFORMED_PAYLOAD)

    return ApprovalLifecycleRecord(
        request=data,
        state=PENDING_STATE,
        expires_at=expires_at,
        history=(_history_entry("created", PENDING_STATE),),
    )


def cancel(
    record: ApprovalLifecycleRecord,
    *,
    actor: dict[str, Any],
    reason: str,
    as_of: str = "",
) -> ApprovalLifecycleRecord:
    """Cancel a pending request with explicit ``actor`` and ``reason`` metadata.

    Fails closed if the request is already terminal, if ``actor`` is not a valid
    actor object, or if ``reason`` is blank.
    """
    _require_pending(record, "cancel")

    actor_errors = validate_actor(actor, "actor")
    if actor_errors:
        raise ApprovalLifecycleError(
            f"cannot cancel: {'; '.join(actor_errors)}",
            code=CODE_MALFORMED_PAYLOAD,
        )
    if not (isinstance(reason, str) and reason.strip()):
        raise ApprovalLifecycleError(
            "cannot cancel: a non-blank reason is required",
            code=CODE_MALFORMED_PAYLOAD,
        )

    terminal_reason = {"action": "cancelled", "actor": dict(actor), "reason": reason, "as_of": as_of}
    return ApprovalLifecycleRecord(
        request=record.request,
        state="cancelled",
        expires_at=record.expires_at,
        decision=None,
        terminal_reason=terminal_reason,
        history=record.history + (_history_entry("cancelled", "cancelled", as_of=as_of, detail={"reason": reason}),),
    )


def is_due(record: ApprovalLifecycleRecord, as_of: str) -> bool:
    """True iff ``record`` has an explicit deadline that ``as_of`` has reached.

    Pure comparison of two ISO-8601 strings (lexicographic order matches
    chronological order for zero-padded ISO timestamps); never reads a clock.
    A record without an ``expires_at`` deadline is never due.
    """
    if not (isinstance(as_of, str) and as_of.strip()):
        raise ApprovalLifecycleError("as_of must be a non-blank timestamp", code=CODE_MALFORMED_PAYLOAD)
    if not record.expires_at:
        return False
    return as_of >= record.expires_at


def expire(record: ApprovalLifecycleRecord, *, as_of: str) -> ApprovalLifecycleRecord:
    """Expire a pending request deterministically against an explicit ``as_of``.

    The request must carry an explicit ``expires_at`` deadline; expiry happens
    iff ``as_of`` has reached it.  Fails closed if the request is terminal, if no
    deadline was set, or if the deadline has not yet been reached
    (:data:`CODE_NOT_DUE`) — so a premature expire can never terminate a request
    that is still live.
    """
    _require_pending(record, "expire")

    if not record.expires_at:
        raise ApprovalLifecycleError(
            "cannot expire: the approval request has no explicit expires_at deadline",
            code=CODE_MALFORMED_PAYLOAD,
        )
    if not is_due(record, as_of):
        raise ApprovalLifecycleError(
            f"cannot expire: as_of {as_of!r} has not reached the deadline {record.expires_at!r}",
            code=CODE_NOT_DUE,
        )

    terminal_reason = {"action": "expired", "as_of": as_of, "expires_at": record.expires_at}
    return ApprovalLifecycleRecord(
        request=record.request,
        state="expired",
        expires_at=record.expires_at,
        decision=None,
        terminal_reason=terminal_reason,
        history=record.history + (_history_entry("expired", "expired", as_of=as_of),),
    )


def _classify_decision_errors(errors: list[str]) -> str:
    """Map validator messages to a stable lifecycle classification code."""
    joined = " ".join(errors)
    if "superseded" in joined:
        return CODE_STALE_VERSION
    if "does not bind the same subject" in joined or "different ApprovalRequest" in joined:
        return CODE_SUBJECT_MISMATCH
    return CODE_MALFORMED_PAYLOAD


def decide(
    record: ApprovalLifecycleRecord,
    decision: str,
    *,
    decided_by: dict[str, Any] | None = None,
    rationale: str = "",
    current_version: int | None = None,
    decided_at: str = "",
) -> ApprovalLifecycleRecord:
    """Decide a pending request as ``approved`` or ``rejected`` exactly once.

    Produces an :class:`ApprovalDecision` bound to the same request id and the
    exact subject/version under review, validated against the originating request
    (and, when ``current_version`` is supplied, against version staleness — an
    *approved* decision over a superseded version fails closed).  Fails closed on
    a terminal request (a duplicate decision yields :data:`CODE_DUPLICATE_DECISION`),
    an unknown decision verb, a subject mismatch, or a stale version.
    """
    if record.decision is not None or record.state in _DECISION_TO_STATE.values():
        raise ApprovalLifecycleError(
            f"cannot decide: approval request was already decided (state={record.state!r}); a decision is made exactly once",
            code=CODE_DUPLICATE_DECISION,
        )
    _require_pending(record, "decide")

    if decision not in APPROVAL_DECISIONS:
        raise ApprovalLifecycleError(
            f"decision must be one of {', '.join(APPROVAL_DECISIONS)}, got {decision!r}",
            code=CODE_MALFORMED_PAYLOAD,
        )

    req = record.request
    built = ApprovalDecision(
        approval_request_id=req.get("approval_request_id", ""),
        project_id=req.get("project_id", ""),
        subject_type=req.get("subject_type", ""),
        subject_id=req.get("subject_id", ""),
        subject_version=req.get("subject_version", 0),
        decision=decision,
        decided_by=dict(decided_by) if decided_by else {},
        rationale=rationale,
        decided_at=decided_at or now_iso(),
    )
    decision_dict = built.to_dict()

    errors = validate_approval_decision(decision_dict, request=req, current_version=current_version)
    if errors:
        raise ApprovalLifecycleError(
            f"invalid approval decision: {'; '.join(errors)}",
            code=_classify_decision_errors(errors),
        )

    new_state = _DECISION_TO_STATE[decision]
    return ApprovalLifecycleRecord(
        request=record.request,
        state=new_state,
        expires_at=record.expires_at,
        decision=decision_dict,
        terminal_reason=None,
        history=record.history + (_history_entry("decided", new_state, as_of=decided_at, detail={"decision": decision}),),
    )


def approve(record: ApprovalLifecycleRecord, **kwargs: Any) -> ApprovalLifecycleRecord:
    """Convenience wrapper: :func:`decide` the request as ``approved``."""
    return decide(record, "approved", **kwargs)


def reject(record: ApprovalLifecycleRecord, **kwargs: Any) -> ApprovalLifecycleRecord:
    """Convenience wrapper: :func:`decide` the request as ``rejected``."""
    return decide(record, "rejected", **kwargs)


# Re-export the authoritative state vocabulary for callers/tests that branch on
# it, so they need not reach across into core.schemas.
__all__ = [
    "APPROVAL_STATES",
    "PENDING_STATE",
    "TERMINAL_STATES",
    "ApprovalLifecycleError",
    "ApprovalLifecycleRecord",
    "approve",
    "cancel",
    "create_approval_request",
    "decide",
    "expire",
    "is_due",
    "reject",
    "ERROR_CODES",
]
