"""Deterministic retry policy: bounded backoff + budgets (WP-25 / T-25-03, T-25-04).

The requirement spec forbids infinite retries and unbounded full re-runs.  A
retryable failure may be retried, but only under an explicit ceiling: a maximum
attempt count, a total elapsed-time budget, and a per-scope retry budget
(per project / tool / task type).  Once any ceiling is hit, the failure is
*escalated* to a human / re-plan path rather than retried again.

This module computes those decisions **purely and deterministically**.  Backoff
uses exponential growth with a *deterministic* jitter derived from an explicit
seed (never a wall-clock or RNG read), so the same failure always yields the same
delay — reproducible and testable offline.  "Elapsed time" is an explicit
caller-supplied value, never read from a clock here.

Design constraints mirror the house style: pure, deterministic, fail-closed,
bounded status + reason-code vocabulary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from . import failure_taxonomy as ft

# --- Bounds ------------------------------------------------------------------
MAX_ATTEMPTS_CEILING = 100  # a policy may never permit more than this many attempts

# --- Bounded status vocabulary -----------------------------------------------
STATUS_RETRY = "retry"  # schedule another attempt after the computed delay
STATUS_ESCALATE = "escalate"  # do not retry; route to the class's resolution path
STATUS_EXHAUSTED = "exhausted"  # retryable but a ceiling/budget was reached; escalate
STATUS_INVALID = "invalid"  # malformed inputs; fail closed

STATUSES = (STATUS_RETRY, STATUS_ESCALATE, STATUS_EXHAUSTED, STATUS_INVALID)

# --- Stable reason codes -----------------------------------------------------
CODE_RETRY_SCHEDULED = "RETRY_SCHEDULED"
CODE_NON_RETRYABLE = "RETRY_NON_RETRYABLE_CLASS"
CODE_MAX_ATTEMPTS = "RETRY_MAX_ATTEMPTS_REACHED"
CODE_TIME_BUDGET = "RETRY_TIME_BUDGET_EXHAUSTED"
CODE_SCOPE_BUDGET = "RETRY_SCOPE_BUDGET_EXHAUSTED"
CODE_MALFORMED_POLICY = "RETRY_MALFORMED_POLICY"
CODE_MALFORMED_REQUEST = "RETRY_MALFORMED_REQUEST"

REASON_CODES = (
    CODE_RETRY_SCHEDULED,
    CODE_NON_RETRYABLE,
    CODE_MAX_ATTEMPTS,
    CODE_TIME_BUDGET,
    CODE_SCOPE_BUDGET,
    CODE_MALFORMED_POLICY,
    CODE_MALFORMED_REQUEST,
)

_CODE_STATUS = {
    CODE_RETRY_SCHEDULED: STATUS_RETRY,
    CODE_NON_RETRYABLE: STATUS_ESCALATE,
    CODE_MAX_ATTEMPTS: STATUS_EXHAUSTED,
    CODE_TIME_BUDGET: STATUS_EXHAUSTED,
    CODE_SCOPE_BUDGET: STATUS_EXHAUSTED,
    CODE_MALFORMED_POLICY: STATUS_INVALID,
    CODE_MALFORMED_REQUEST: STATUS_INVALID,
}


def _is_non_negative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


@dataclass(frozen=True)
class RetryPolicy:
    """The bounded retry envelope for a failure.

    - ``base_delay_seconds`` — the first retry's base delay;
    - ``multiplier`` — the exponential growth factor per attempt (>= 1);
    - ``max_delay_seconds`` — the cap a single backoff delay may reach;
    - ``jitter_fraction`` — the deterministic jitter magnitude as a fraction of the
      (capped) base delay, in ``[0, 1]``; jitter is derived from an explicit seed,
      never random;
    - ``max_attempts`` — the hard attempt ceiling (<= :data:`MAX_ATTEMPTS_CEILING`);
    - ``total_time_budget_seconds`` — the total elapsed-time budget across attempts.
    """

    base_delay_seconds: float = 1.0
    multiplier: float = 2.0
    max_delay_seconds: float = 300.0
    jitter_fraction: float = 0.1
    max_attempts: int = 5
    total_time_budget_seconds: float = 3600.0

    def validate(self) -> str | None:
        if not _is_non_negative_number(self.base_delay_seconds):
            return "base_delay_seconds must be a non-negative number"
        if not isinstance(self.multiplier, (int, float)) or isinstance(self.multiplier, bool) or self.multiplier < 1:
            return "multiplier must be a number >= 1"
        if not _is_non_negative_number(self.max_delay_seconds):
            return "max_delay_seconds must be a non-negative number"
        if not isinstance(self.jitter_fraction, (int, float)) or isinstance(self.jitter_fraction, bool) or not (0 <= self.jitter_fraction <= 1):
            return "jitter_fraction must be a number in [0, 1]"
        if not _is_positive_int(self.max_attempts) or self.max_attempts > MAX_ATTEMPTS_CEILING:
            return f"max_attempts must be a positive int <= {MAX_ATTEMPTS_CEILING}"
        if not _is_non_negative_number(self.total_time_budget_seconds):
            return "total_time_budget_seconds must be a non-negative number"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_delay_seconds": self.base_delay_seconds,
            "multiplier": self.multiplier,
            "max_delay_seconds": self.max_delay_seconds,
            "jitter_fraction": self.jitter_fraction,
            "max_attempts": self.max_attempts,
            "total_time_budget_seconds": self.total_time_budget_seconds,
        }


def _deterministic_unit(seed: str) -> float:
    """A deterministic value in ``[0, 1)`` derived from ``seed`` (no RNG, no clock)."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    # Use the first 8 hex chars as a 32-bit integer, normalised to [0, 1).
    return int(digest[:8], 16) / 0x100000000


def compute_backoff(policy: RetryPolicy, attempt: int, *, seed: str = "") -> float:
    """Return the deterministic backoff delay (seconds) for ``attempt`` (1-based).

    ``delay = min(base * multiplier**(attempt-1), max_delay)`` plus a deterministic
    jitter in ``[0, jitter_fraction * capped_delay]`` derived from ``seed`` and the
    attempt number.  Pure: identical arguments always yield the identical delay.
    A non-positive attempt yields ``0.0``.
    """
    if not _is_positive_int(attempt):
        return 0.0
    raw = policy.base_delay_seconds * (policy.multiplier ** (attempt - 1))
    capped = min(raw, policy.max_delay_seconds)
    jitter_span = policy.jitter_fraction * capped
    jitter = jitter_span * _deterministic_unit(f"{seed}:{attempt}")
    return capped + jitter


@dataclass(frozen=True)
class RetryBudget:
    """Per-scope retry ceilings and the retries already spent per scope.

    ``per_project`` / ``per_tool`` / ``per_task_type`` are the ceilings; ``spent``
    maps a scope key (e.g. ``"project:p1"``) to retries already consumed.  A scope
    with no ceiling entry is unconstrained by that dimension.
    """

    per_project: int | None = None
    per_tool: int | None = None
    per_task_type: int | None = None
    spent: dict[str, int] = field(default_factory=dict)

    def spent_for(self, key: str) -> int:
        value = self.spent.get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_project": self.per_project,
            "per_tool": self.per_tool,
            "per_task_type": self.per_task_type,
            "spent": dict(self.spent),
        }


@dataclass(frozen=True)
class RetryRequest:
    """The facts a retry decision needs (all explicit — no clock is read).

    ``failure_class`` is a :mod:`failure_taxonomy` class code; ``attempt`` is the
    number of the attempt that just failed (1-based); ``elapsed_seconds`` is the
    total time already spent on this task's attempts; the scope ids identify the
    per-scope budget keys.
    """

    failure_class: str
    attempt: int
    elapsed_seconds: float = 0.0
    project_id: str = ""
    tool: str = ""
    task_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class,
            "attempt": self.attempt,
            "elapsed_seconds": self.elapsed_seconds,
            "project_id": self.project_id,
            "tool": self.tool,
            "task_type": self.task_type,
        }


@dataclass(frozen=True)
class RetryDecision:
    """The deterministic, reason-coded retry decision.

    ``delay_seconds`` is the scheduled backoff when ``status == retry`` (0 otherwise).
    ``resolution_path`` names the escalation route from the failure taxonomy when
    the failure is not retried.  ``binding`` records the facts considered.
    """

    status: str
    reason_code: str
    message: str
    delay_seconds: float = 0.0
    resolution_path: str = ""
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def should_retry(self) -> bool:
        return self.status == STATUS_RETRY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "delay_seconds": self.delay_seconds,
            "resolution_path": self.resolution_path,
            "should_retry": self.should_retry,
            "binding": dict(self.binding),
        }


def _scope_exhausted(request: RetryRequest, budget: RetryBudget) -> tuple[str, str] | None:
    """Return ``(scope_key, dimension)`` for the first exhausted scope budget, else ``None``."""
    checks = (
        (budget.per_project, f"project:{request.project_id}", "project", request.project_id),
        (budget.per_tool, f"tool:{request.tool}", "tool", request.tool),
        (budget.per_task_type, f"task_type:{request.task_type}", "task_type", request.task_type),
    )
    for ceiling, key, dimension, ident in checks:
        if ceiling is None or not ident:
            continue
        if budget.spent_for(key) >= ceiling:
            return (key, dimension)
    return None


def decide_retry(request: Any, *, policy: RetryPolicy, budget: RetryBudget | None = None) -> RetryDecision:
    """Decide whether a failed attempt may be retried, fail-closed.

    Precedence:

    1. Malformed request/policy → ``invalid``.
    2. A non-retryable failure class → ``escalate`` immediately (route to the
       class's resolution path; scientific/design failures are never retried).
    3. Attempt ceiling reached (``attempt >= max_attempts``) → ``exhausted``.
    4. Total time budget reached (``elapsed_seconds >= total_time_budget``) →
       ``exhausted``.
    5. A per-scope retry budget exhausted → ``exhausted``.
    6. Otherwise → ``retry`` with the deterministic backoff delay.
    """
    active_budget = budget if isinstance(budget, RetryBudget) else RetryBudget()

    def _decide(code: str, message: str, *, delay: float = 0.0, resolution_path: str = "", extra: dict[str, Any] | None = None) -> RetryDecision:
        binding: dict[str, Any] = {
            "failure_class": request.failure_class if isinstance(request, RetryRequest) else None,
            "attempt": request.attempt if isinstance(request, RetryRequest) else None,
            "max_attempts": policy.max_attempts if isinstance(policy, RetryPolicy) else None,
            "elapsed_seconds": request.elapsed_seconds if isinstance(request, RetryRequest) else None,
            "total_time_budget_seconds": policy.total_time_budget_seconds if isinstance(policy, RetryPolicy) else None,
        }
        if extra:
            binding.update(extra)
        return RetryDecision(
            status=_CODE_STATUS[code], reason_code=code, message=message, delay_seconds=delay, resolution_path=resolution_path, binding=binding
        )

    if not isinstance(policy, RetryPolicy):
        return _decide(CODE_MALFORMED_POLICY, "policy must be a RetryPolicy")
    policy_error = policy.validate()
    if policy_error is not None:
        return _decide(CODE_MALFORMED_POLICY, policy_error)
    if not isinstance(request, RetryRequest):
        return _decide(CODE_MALFORMED_REQUEST, "request must be a RetryRequest")
    if not _is_positive_int(request.attempt):
        return _decide(CODE_MALFORMED_REQUEST, "attempt must be a positive integer (1-based)")
    if not _is_non_negative_number(request.elapsed_seconds):
        return _decide(CODE_MALFORMED_REQUEST, "elapsed_seconds must be a non-negative number")
    if not ft.is_failure_class(request.failure_class):
        return _decide(CODE_MALFORMED_REQUEST, f"failure_class {request.failure_class!r} is not a known failure class")

    failure = ft.FAILURE_CLASSES[request.failure_class]

    # 2. Non-retryable class escalates immediately.
    if not failure.retryable:
        return _decide(
            CODE_NON_RETRYABLE,
            f"failure class {failure.code!r} is non-retryable; escalate to the {failure.resolution_path!r} path",
            resolution_path=failure.resolution_path,
        )

    # 3. Attempt ceiling.
    if request.attempt >= policy.max_attempts:
        return _decide(
            CODE_MAX_ATTEMPTS,
            f"attempt {request.attempt} reached the max of {policy.max_attempts}; no further retry (escalate to {failure.resolution_path!r})",
            resolution_path=failure.resolution_path,
        )

    # 4. Total time budget.
    if request.elapsed_seconds >= policy.total_time_budget_seconds:
        return _decide(
            CODE_TIME_BUDGET,
            f"elapsed {request.elapsed_seconds}s reached the total budget {policy.total_time_budget_seconds}s; escalate to {failure.resolution_path!r}",
            resolution_path=failure.resolution_path,
        )

    # 5. Per-scope budget.
    exhausted = _scope_exhausted(request, active_budget)
    if exhausted is not None:
        key, dimension = exhausted
        return _decide(
            CODE_SCOPE_BUDGET,
            f"per-{dimension} retry budget for {key!r} is exhausted; escalate to {failure.resolution_path!r}",
            resolution_path=failure.resolution_path,
            extra={"exhausted_scope": key},
        )

    # 6. Retry with a deterministic backoff for the *next* attempt.
    seed = f"{request.project_id}:{request.tool}:{request.task_type}:{request.failure_class}"
    delay = compute_backoff(policy, request.attempt + 1, seed=seed)
    return _decide(
        CODE_RETRY_SCHEDULED,
        f"failure class {failure.code!r} is retryable and within all budgets; schedule attempt {request.attempt + 1} after backoff",
        delay=delay,
        extra={"next_attempt": request.attempt + 1},
    )


__all__ = [
    "MAX_ATTEMPTS_CEILING",
    "STATUS_RETRY",
    "STATUS_ESCALATE",
    "STATUS_EXHAUSTED",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_RETRY_SCHEDULED",
    "CODE_NON_RETRYABLE",
    "CODE_MAX_ATTEMPTS",
    "CODE_TIME_BUDGET",
    "CODE_SCOPE_BUDGET",
    "CODE_MALFORMED_POLICY",
    "CODE_MALFORMED_REQUEST",
    "REASON_CODES",
    "RetryPolicy",
    "compute_backoff",
    "RetryBudget",
    "RetryRequest",
    "RetryDecision",
    "decide_retry",
]
