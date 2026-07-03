"""Bounded failure taxonomy and retryability matrix (WP-25 / T-25-01, T-25-02).

The requirement spec demands that every internal/external failure map to an
explicit error class, and that the retry decision be *predictable*: transient
infrastructure failures may be retried under a budget, while **scientific and
design failures are never retried** (retrying them would only mask an
un-fixable-by-repetition problem).

This module is the single source of truth for those classes.  It is pure data +
pure predicates: exactly twelve failure classes, a stable error-code → class
mapping, and, per class, whether it is retryable and which *resolution path* it
is routed to (retry / replan / reconfirm / human / terminal).  No I/O, no clock,
no randomness.

Design constraints mirror the house style: bounded vocabulary, fail-closed
classification (an unknown/malformed error code maps to the conservative
non-retryable ``INTERNAL_ERROR`` class rather than being guessed retryable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Resolution paths (where a class routes when it cannot simply be retried) --
PATH_RETRY = "retry"  # a bounded automatic retry may resolve it
PATH_REPLAN = "replan"  # the plan/approach must change; not fixable by repetition
PATH_RECONFIRM = "reconfirm"  # a human must re-confirm a changed assumption first
PATH_HUMAN = "human"  # a human must investigate (bug / config / permission)
PATH_TERMINAL = "terminal"  # a legitimate scientific stop; no retry, no replan

RESOLUTION_PATHS = (PATH_RETRY, PATH_REPLAN, PATH_RECONFIRM, PATH_HUMAN, PATH_TERMINAL)


@dataclass(frozen=True)
class FailureClass:
    """One bounded failure class: its code, retryability, and resolution path.

    ``retryable`` means a bounded automatic retry is *permitted* (subject to the
    retry policy's budget); it never means "retry forever".  ``resolution_path`` is
    the route taken once retries are exhausted or when retry is not permitted.
    """

    code: str
    retryable: bool
    resolution_path: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "retryable": self.retryable,
            "resolution_path": self.resolution_path,
            "description": self.description,
        }


# --- The twelve failure classes (the whole bounded taxonomy) -----------------
CLASS_NETWORK_TRANSIENT = "NETWORK_TRANSIENT"
CLASS_RATE_LIMITED = "RATE_LIMITED"
CLASS_LOCK_CONTENTION = "LOCK_CONTENTION"
CLASS_WORKER_INTERRUPTED = "WORKER_INTERRUPTED"
CLASS_DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
CLASS_TIMEOUT = "TIMEOUT"
CLASS_RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
CLASS_INPUT_DATA_INVALID = "INPUT_DATA_INVALID"
CLASS_VALIDATION_FAILED = "VALIDATION_FAILED"
CLASS_METHOD_NOT_APPLICABLE = "METHOD_NOT_APPLICABLE"
CLASS_SCIENTIFIC_INFEASIBLE = "SCIENTIFIC_INFEASIBLE"
CLASS_INTERNAL_ERROR = "INTERNAL_ERROR"

FAILURE_CLASSES: dict[str, FailureClass] = {
    CLASS_NETWORK_TRANSIENT: FailureClass(
        CLASS_NETWORK_TRANSIENT, True, PATH_RETRY, "a transient network error (connection reset/DNS blip); a bounded retry may resolve it"
    ),
    CLASS_RATE_LIMITED: FailureClass(CLASS_RATE_LIMITED, True, PATH_RETRY, "an external provider rate limit; a backed-off retry may resolve it"),
    CLASS_LOCK_CONTENTION: FailureClass(CLASS_LOCK_CONTENTION, True, PATH_RETRY, "a contended lock/optimistic-concurrency conflict; a retry may acquire it"),
    CLASS_WORKER_INTERRUPTED: FailureClass(
        CLASS_WORKER_INTERRUPTED, True, PATH_RETRY, "a worker was preempted/killed mid-task; the idempotent task may be re-run"
    ),
    CLASS_DEPENDENCY_UNAVAILABLE: FailureClass(
        CLASS_DEPENDENCY_UNAVAILABLE, True, PATH_RETRY, "a backing dependency (object store/queue/DB) was briefly unavailable; a retry may resolve it"
    ),
    CLASS_TIMEOUT: FailureClass(CLASS_TIMEOUT, True, PATH_RETRY, "an operation exceeded its time budget; a bounded retry may resolve a transient stall"),
    CLASS_RESOURCE_EXHAUSTED: FailureClass(
        CLASS_RESOURCE_EXHAUSTED, False, PATH_REPLAN, "out of memory/disk/quota; retrying identically will not help — the plan/resources must change"
    ),
    CLASS_INPUT_DATA_INVALID: FailureClass(
        CLASS_INPUT_DATA_INVALID, False, PATH_RECONFIRM, "the input data does not match the assumed shape/schema; a human must re-confirm the data assumption"
    ),
    CLASS_VALIDATION_FAILED: FailureClass(
        CLASS_VALIDATION_FAILED, False, PATH_REPLAN, "a QC/contract/gate check failed; repetition cannot pass it — the method/plan must change"
    ),
    CLASS_METHOD_NOT_APPLICABLE: FailureClass(
        CLASS_METHOD_NOT_APPLICABLE, False, PATH_TERMINAL, "the chosen method is not applicable to this data/design; a legitimate non-success terminal"
    ),
    CLASS_SCIENTIFIC_INFEASIBLE: FailureClass(
        CLASS_SCIENTIFIC_INFEASIBLE, False, PATH_TERMINAL, "the question cannot be answered with the available evidence; a legitimate terminal (never retried)"
    ),
    CLASS_INTERNAL_ERROR: FailureClass(
        CLASS_INTERNAL_ERROR, False, PATH_HUMAN, "an unexpected internal/logic error; a human must investigate (never blindly retried)"
    ),
}

FAILURE_CLASS_CODES = tuple(FAILURE_CLASSES.keys())

# The retryable subset, derived so it can never drift from the class table.
RETRYABLE_CLASSES = frozenset(code for code, cls in FAILURE_CLASSES.items() if cls.retryable)
NON_RETRYABLE_CLASSES = frozenset(code for code, cls in FAILURE_CLASSES.items() if not cls.retryable)

# --- Error-code → class mapping ----------------------------------------------
# A small, stable mapping from concrete error-envelope codes (as a real adapter
# would emit) to a failure class.  An unknown code fails closed to the
# conservative non-retryable INTERNAL_ERROR class — never guessed retryable.
_ERROR_CODE_MAP: dict[str, str] = {
    "ECONNRESET": CLASS_NETWORK_TRANSIENT,
    "ECONNREFUSED": CLASS_NETWORK_TRANSIENT,
    "DNS_FAILURE": CLASS_NETWORK_TRANSIENT,
    "HTTP_429": CLASS_RATE_LIMITED,
    "RATE_LIMIT": CLASS_RATE_LIMITED,
    "LOCK_TIMEOUT": CLASS_LOCK_CONTENTION,
    "VERSION_CONFLICT": CLASS_LOCK_CONTENTION,
    "WORKER_KILLED": CLASS_WORKER_INTERRUPTED,
    "WORKER_PREEMPTED": CLASS_WORKER_INTERRUPTED,
    "LEASE_LOST": CLASS_WORKER_INTERRUPTED,
    "STORE_UNAVAILABLE": CLASS_DEPENDENCY_UNAVAILABLE,
    "QUEUE_UNAVAILABLE": CLASS_DEPENDENCY_UNAVAILABLE,
    "DB_UNAVAILABLE": CLASS_DEPENDENCY_UNAVAILABLE,
    "HTTP_503": CLASS_DEPENDENCY_UNAVAILABLE,
    "DEADLINE_EXCEEDED": CLASS_TIMEOUT,
    "TIMEOUT": CLASS_TIMEOUT,
    "OOM_KILLED": CLASS_RESOURCE_EXHAUSTED,
    "DISK_FULL": CLASS_RESOURCE_EXHAUSTED,
    "QUOTA_EXCEEDED": CLASS_RESOURCE_EXHAUSTED,
    "SCHEMA_MISMATCH": CLASS_INPUT_DATA_INVALID,
    "CHECKSUM_MISMATCH": CLASS_INPUT_DATA_INVALID,
    "MALFORMED_INPUT": CLASS_INPUT_DATA_INVALID,
    "QC_FAILED": CLASS_VALIDATION_FAILED,
    "GATE_REJECTED": CLASS_VALIDATION_FAILED,
    "CONTRACT_VIOLATION": CLASS_VALIDATION_FAILED,
    "METHOD_NOT_APPLICABLE": CLASS_METHOD_NOT_APPLICABLE,
    "INSUFFICIENT_DATA": CLASS_SCIENTIFIC_INFEASIBLE,
    "CONFLICTING_EVIDENCE": CLASS_SCIENTIFIC_INFEASIBLE,
    "INTERNAL": CLASS_INTERNAL_ERROR,
    "ASSERTION_FAILED": CLASS_INTERNAL_ERROR,
    "PERMISSION_DENIED": CLASS_INTERNAL_ERROR,
    "CONFIG_ERROR": CLASS_INTERNAL_ERROR,
}


def is_failure_class(value: Any) -> bool:
    return isinstance(value, str) and value in FAILURE_CLASSES


def classify_error_code(error_code: Any) -> FailureClass:
    """Map a concrete error code to its :class:`FailureClass`, fail-closed.

    A known code maps to its class; an unknown, blank, or non-string code maps to
    the conservative non-retryable :data:`CLASS_INTERNAL_ERROR` (a human must look)
    rather than being optimistically treated as a retryable transient error.
    """
    if isinstance(error_code, str):
        code = _ERROR_CODE_MAP.get(error_code.strip().upper())
        if code is not None:
            return FAILURE_CLASSES[code]
    return FAILURE_CLASSES[CLASS_INTERNAL_ERROR]


def is_retryable(failure_class: Any) -> bool:
    """True iff ``failure_class`` (a code) is a retryable class; unknown → False."""
    return isinstance(failure_class, str) and failure_class in RETRYABLE_CLASSES


def resolution_path_for(failure_class: Any) -> str:
    """The resolution path for a class code; unknown → the human path (fail closed)."""
    cls = FAILURE_CLASSES.get(failure_class) if isinstance(failure_class, str) else None
    return cls.resolution_path if cls is not None else PATH_HUMAN


def known_error_codes() -> tuple[str, ...]:
    """The concrete error codes with an explicit mapping (sorted, for adapters/tests)."""
    return tuple(sorted(_ERROR_CODE_MAP))


__all__ = [
    "PATH_RETRY",
    "PATH_REPLAN",
    "PATH_RECONFIRM",
    "PATH_HUMAN",
    "PATH_TERMINAL",
    "RESOLUTION_PATHS",
    "FailureClass",
    "CLASS_NETWORK_TRANSIENT",
    "CLASS_RATE_LIMITED",
    "CLASS_LOCK_CONTENTION",
    "CLASS_WORKER_INTERRUPTED",
    "CLASS_DEPENDENCY_UNAVAILABLE",
    "CLASS_TIMEOUT",
    "CLASS_RESOURCE_EXHAUSTED",
    "CLASS_INPUT_DATA_INVALID",
    "CLASS_VALIDATION_FAILED",
    "CLASS_METHOD_NOT_APPLICABLE",
    "CLASS_SCIENTIFIC_INFEASIBLE",
    "CLASS_INTERNAL_ERROR",
    "FAILURE_CLASSES",
    "FAILURE_CLASS_CODES",
    "RETRYABLE_CLASSES",
    "NON_RETRYABLE_CLASSES",
    "is_failure_class",
    "classify_error_code",
    "is_retryable",
    "resolution_path_for",
    "known_error_codes",
]
