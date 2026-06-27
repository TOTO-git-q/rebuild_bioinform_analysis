"""Local gateway reliability policy contract (WP-05i / T-05-09).

The smallest *local* contract the future Agent Gateway (WP-05) needs so that —
before any real provider/tool call, rate-limit store, budget ledger, circuit
breaker, retry loop, or clock exists — it can decide whether a *synthetic*
provider / tool request is **allowed**, **denied**, or requires
**human review** purely from explicitly supplied, in-memory reliability facts
evaluated against policy-shaped limits.

A single :func:`evaluate_reliability` call takes an inert :class:`ReliabilityPolicy`
(or a policy-shaped mapping) of limit facts — a timeout duration, a rate-limit
request ceiling, a cost budget, and a circuit-breaker failure threshold — and an
inert :class:`ReliabilityRequest` of explicitly-supplied observed / estimated facts
about *one* call, and returns a deterministic :class:`ReliabilityDecision`.  The
decision carries only bounded, non-content facts: a status, a stable reason code, a
content-address-like ``decision_id``, the trace binding, and the bounded set of
``engaged_dimensions``.  It never carries prompt content, raw input, raw output,
tool arguments, credentials, or private operational telemetry — those are not even
fields.

Everything here is local, deterministic, and offline.  There is **no** real
provider / tool call, network call, HTTP client, SDK, credential / environment
access, real clock read, ``sleep``, retry / backoff / scheduler, subprocess,
file / DB / queue write, rate-limit counter, budget ledger, circuit-state store,
event, ordinary log, report, metric, or global mutable registry.
:func:`evaluate_reliability` is a pure total function of its explicit in-memory
inputs that mutates neither of them and returns inert *data* to the caller.

Design constraints (mirroring the WP-05a..h style):

- **Pure, deterministic, offline.**  No I/O whatsoever; a decision is a total
  function of its explicit in-memory inputs, and the evaluator mutates nothing.
- **Fail closed, no fallback.**  Every uncertainty resolves to a bounded,
  reason-coded ``rejected`` decision (:data:`VALIDATION_CODES` /
  :data:`LIMIT_FACT_CODES`): a malformed / unshaped policy or request, a missing /
  malformed project-or-correlation binding, a missing / malformed call identity, a
  malformed optional reference, a negative / non-finite / oversized limit or fact,
  an unknown cost unit or ambiguous unit pairing, an unknown circuit state, an
  inconsistent circuit, a fact supplied without the limit needed to judge it (or a
  limit with no fact), an engaged rate-limit dimension whose policy / request windows
  are unpaired or mismatched, an empty policy, and any authority flag claiming to
  authorize real execution or bypass gates all fail closed and yield **no allow**.
- **Over-budget escalates, never auto-allows.**  An over-budget condition yields a
  bounded ``need_human_review`` decision (:data:`CODE_BUDGET_EXCEEDED`), never an
  automatic allow.  Timeout / rate-limit / open-circuit conditions are **denied**;
  none of them is ever silently allowed.
- **No content, ever.**  The decision exposes only ids, a status, a reason code, and
  the engaged dimensions; prompt content, raw input / output, tool arguments, and
  credentials are never fields, so a decision cannot become a side channel.
- **Data only.**  The evaluator returns *data* to the caller — an inert decision.
  It writes no project state, business object, event, artifact, queue/outbox record,
  domain table, report, rate-limit store, budget ledger, circuit store, metric, or
  full-content log.

Out of scope for T-05-09 (and deliberately *not* implemented here): any real
provider / tool call, HTTP / SDK integration, credential / env handling, network or
content egress; reading a real clock, sleeping, retries / backoff / jitter, timers,
schedulers, queues, leases, or background workers; durable rate-limit counters,
budget ledgers, circuit state, audit logs, events, metrics, or persistence; the
fake-model fixture expansion (T-05-10), the eval framework (T-05-11), prompt
approval / rollback (T-05-12), and any integration that actually gates production
execution.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from auto_bioinfo.core.ids import make_stable_id

# --- Bounds (so an unbounded input cannot exhaust a downstream limiter) --------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated or clamped.
MAX_ID_LENGTH = 200
MAX_LABEL_LENGTH = 64
MAX_DURATION_MS = 86_400_000  # one day, in ms — a generous upper bound, not a real clock
MAX_COST_UNITS = 1_000_000_000
MAX_COUNT = 1_000_000_000
MAX_AUTHORITY_FLAGS = 16

# --- Bounded cost-unit vocabulary --------------------------------------------
# A budget limit and an estimated/consumed cost fact must agree on units; an unknown
# unit or a policy/fact unit mismatch is ambiguous and fails closed.
COST_UNIT_CREDITS = "credits"
COST_UNIT_USD_MICROS = "usd_micros"
COST_UNIT_TOKENS = "tokens"

COST_UNITS = (COST_UNIT_CREDITS, COST_UNIT_USD_MICROS, COST_UNIT_TOKENS)

# --- Bounded circuit-state vocabulary ----------------------------------------
CIRCUIT_CLOSED = "closed"
CIRCUIT_OPEN = "open"
CIRCUIT_HALF_OPEN = "half_open"

CIRCUIT_STATES = (CIRCUIT_CLOSED, CIRCUIT_OPEN, CIRCUIT_HALF_OPEN)

# --- Bounded reliability-dimension vocabulary --------------------------------
DIMENSION_TIMEOUT = "timeout"
DIMENSION_RATE = "rate_limit"
DIMENSION_BUDGET = "budget"
DIMENSION_CIRCUIT = "circuit"

DIMENSIONS = (DIMENSION_TIMEOUT, DIMENSION_RATE, DIMENSION_BUDGET, DIMENSION_CIRCUIT)

# --- Bounded decision-status vocabulary --------------------------------------
# ``allowed`` — every engaged dimension is within its policy limit.
# ``denied`` — a deterministic timeout / rate-limit / open-circuit breach.
# ``need_human_review`` — a conservative escalation (over-budget); never an auto-allow.
# ``rejected`` — the fail-closed outcome for malformed / ambiguous / missing inputs.
STATUS_ALLOWED = "allowed"
STATUS_DENIED = "denied"
STATUS_NEED_HUMAN_REVIEW = "need_human_review"
STATUS_REJECTED = "rejected"

STATUSES = (STATUS_ALLOWED, STATUS_DENIED, STATUS_NEED_HUMAN_REVIEW, STATUS_REJECTED)

# --- Stable reason codes -----------------------------------------------------
# Callers / a future gateway branch on these machine-readable codes, never the
# human message, so they must stay stable.
CODE_MALFORMED_POLICY = "RELIABILITY_MALFORMED_POLICY"
CODE_MALFORMED_REQUEST = "RELIABILITY_MALFORMED_REQUEST"
CODE_MISSING_BINDING = "RELIABILITY_MISSING_BINDING"
CODE_MALFORMED_BINDING = "RELIABILITY_MALFORMED_BINDING"
CODE_MISSING_CALL_IDENTITY = "RELIABILITY_MISSING_CALL_IDENTITY"
CODE_MALFORMED_CALL_IDENTITY = "RELIABILITY_MALFORMED_CALL_IDENTITY"
CODE_MALFORMED_REFERENCE = "RELIABILITY_MALFORMED_REFERENCE"
CODE_FORBIDDEN_AUTHORITY = "RELIABILITY_FORBIDDEN_AUTHORITY"

CODE_MALFORMED_LIMIT = "RELIABILITY_MALFORMED_LIMIT"
CODE_MALFORMED_FACT = "RELIABILITY_MALFORMED_FACT"
CODE_UNKNOWN_UNIT = "RELIABILITY_UNKNOWN_UNIT"
CODE_UNKNOWN_STATE = "RELIABILITY_UNKNOWN_STATE"
CODE_MISSING_LIMIT = "RELIABILITY_MISSING_LIMIT"
CODE_AMBIGUOUS_RATE_WINDOW = "RELIABILITY_AMBIGUOUS_RATE_WINDOW"
CODE_INCONSISTENT_CIRCUIT = "RELIABILITY_INCONSISTENT_CIRCUIT"

CODE_TIMEOUT_EXCEEDED = "RELIABILITY_TIMEOUT_EXCEEDED"
CODE_RATE_LIMIT_EXCEEDED = "RELIABILITY_RATE_LIMIT_EXCEEDED"
CODE_CIRCUIT_OPEN = "RELIABILITY_CIRCUIT_OPEN"
CODE_BUDGET_EXCEEDED = "RELIABILITY_BUDGET_EXCEEDED"

VALIDATION_CODES = (
    CODE_MALFORMED_POLICY,
    CODE_MALFORMED_REQUEST,
    CODE_MISSING_BINDING,
    CODE_MALFORMED_BINDING,
    CODE_MISSING_CALL_IDENTITY,
    CODE_MALFORMED_CALL_IDENTITY,
    CODE_MALFORMED_REFERENCE,
    CODE_FORBIDDEN_AUTHORITY,
)

LIMIT_FACT_CODES = (
    CODE_MALFORMED_LIMIT,
    CODE_MALFORMED_FACT,
    CODE_UNKNOWN_UNIT,
    CODE_UNKNOWN_STATE,
    CODE_MISSING_LIMIT,
    CODE_AMBIGUOUS_RATE_WINDOW,
    CODE_INCONSISTENT_CIRCUIT,
)

DECISION_CODES = (
    CODE_TIMEOUT_EXCEEDED,
    CODE_RATE_LIMIT_EXCEEDED,
    CODE_CIRCUIT_OPEN,
    CODE_BUDGET_EXCEEDED,
)

REASON_CODES = VALIDATION_CODES + LIMIT_FACT_CODES + DECISION_CODES


# --- Small, pure predicates --------------------------------------------------


def _is_bounded_token(value: Any, max_length: int) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII token."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length and all("\x20" <= ch <= "\x7e" for ch in value)


def _is_nonneg_int(value: Any, max_value: int) -> bool:
    """True iff ``value`` is a real (non-bool) non-negative bounded ``int``."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= max_value


def _is_finite_nonneg_number(value: Any, max_value: int) -> bool:
    """True iff ``value`` is a real (non-bool) non-negative finite, bounded number."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= max_value
    if isinstance(value, float):
        return math.isfinite(value) and 0.0 <= value <= max_value
    return False


# --- The policy value (limit facts) ------------------------------------------

# The known fields a policy-shaped mapping may carry; an unknown key fails closed.
_POLICY_FIELDS = (
    "max_duration_ms",
    "max_requests",
    "rate_window",
    "max_cost_units",
    "cost_unit",
    "failure_threshold",
    "allow_recovery_probe",
)


@dataclass(frozen=True)
class ReliabilityPolicy:
    """An inert set of bounded reliability *limit* facts.

    Every field is optional; a dimension is only evaluated when its limit is present
    (and the matching observed fact is supplied).  An empty policy carries no limit
    and therefore fails closed — it can authorize nothing.

    Fields:

    - ``max_duration_ms`` — the allowed call duration ceiling (timeout limit);
    - ``max_requests`` / ``rate_window`` — the request-count ceiling within a bounded,
      named window;
    - ``max_cost_units`` / ``cost_unit`` — the cost budget ceiling and its unit;
    - ``failure_threshold`` — the circuit-breaker failure count that trips the circuit;
    - ``allow_recovery_probe`` — whether a single half-open recovery probe is permitted.
    """

    max_duration_ms: int | float | None = None
    max_requests: int | None = None
    rate_window: str | None = None
    max_cost_units: int | float | None = None
    cost_unit: str | None = None
    failure_threshold: int | None = None
    allow_recovery_probe: bool = False

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the policy (stable key order)."""
        return {
            "max_duration_ms": self.max_duration_ms,
            "max_requests": self.max_requests,
            "rate_window": self.rate_window,
            "max_cost_units": self.max_cost_units,
            "cost_unit": self.cost_unit,
            "failure_threshold": self.failure_threshold,
            "allow_recovery_probe": self.allow_recovery_probe,
        }


# --- The request value (observed / estimated facts) --------------------------

_REQUEST_FIELDS = (
    "project_id",
    "correlation_id",
    "call_id",
    "provider",
    "tool_name",
    "prompt_id",
    "elapsed_ms",
    "estimated_duration_ms",
    "request_count",
    "window",
    "estimated_cost_units",
    "consumed_cost_units",
    "cost_unit",
    "circuit_state",
    "recent_failure_count",
    "authority_flags",
)


@dataclass(frozen=True)
class ReliabilityRequest:
    """The explicitly-supplied, inert observed / estimated facts about one call.

    Carries only **non-content facts**: a trace binding, optional bounded provider /
    tool / prompt *references* (never content), and the synthetic timeout / rate /
    budget / circuit facts the evaluator judges against a :class:`ReliabilityPolicy`.

    Fields:

    - ``project_id`` / ``correlation_id`` / ``call_id`` — the trace binding;
    - ``provider`` / ``tool_name`` / ``prompt_id`` — optional bounded references;
    - ``elapsed_ms`` / ``estimated_duration_ms`` — observed / estimated call duration;
    - ``request_count`` / ``window`` — the observed request count within a window;
    - ``estimated_cost_units`` / ``consumed_cost_units`` / ``cost_unit`` — cost facts;
    - ``circuit_state`` / ``recent_failure_count`` — circuit-breaker facts;
    - ``authority_flags`` — an optional mapping that must carry no truthy flag (any
      flag claiming to authorize real execution or bypass gates fails closed).
    """

    project_id: str
    correlation_id: str
    call_id: str
    provider: str | None = None
    tool_name: str | None = None
    prompt_id: str | None = None
    elapsed_ms: int | float | None = None
    estimated_duration_ms: int | float | None = None
    request_count: int | None = None
    window: str | None = None
    estimated_cost_units: int | float | None = None
    consumed_cost_units: int | float | None = None
    cost_unit: str | None = None
    circuit_state: str | None = None
    recent_failure_count: int | None = None
    authority_flags: Mapping[str, Any] | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the request facts (stable key order).

        Carries only the bounded facts above; prompt content, raw input / output,
        and tool arguments are not fields.  The optional ``authority_flags`` mapping
        is projected as the bounded sorted key list only (a request that reaches a
        decision never carries a truthy authority flag).
        """
        return {
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "call_id": self.call_id,
            "provider": self.provider,
            "tool_name": self.tool_name,
            "prompt_id": self.prompt_id,
            "elapsed_ms": self.elapsed_ms,
            "estimated_duration_ms": self.estimated_duration_ms,
            "request_count": self.request_count,
            "window": self.window,
            "estimated_cost_units": self.estimated_cost_units,
            "consumed_cost_units": self.consumed_cost_units,
            "cost_unit": self.cost_unit,
            "circuit_state": self.circuit_state,
            "recent_failure_count": self.recent_failure_count,
            "authority_flags": sorted(self.authority_flags) if isinstance(self.authority_flags, Mapping) else None,
        }


# --- The decision value ------------------------------------------------------


@dataclass(frozen=True)
class ReliabilityDecision:
    """The inert result of an evaluation: a status plus a fail-closed reason.

    Fields:

    - ``status`` — one of :data:`STATUSES`;
    - ``reason_code`` — ``None`` when ``allowed``, else the bounded code
      (:data:`REASON_CODES`) for the deny / review / rejection;
    - ``decision_id`` — a content-address-like id over the binding + status + reason
      + engaged dimensions, or ``None`` when the binding itself is malformed;
    - ``project_id`` / ``correlation_id`` / ``call_id`` — the trace binding echoed for
      audit linkage (``None`` when the corresponding input was malformed / missing);
    - ``engaged_dimensions`` — the bounded tuple of :data:`DIMENSIONS` actually judged.

    The value is inert data; its projections never expose prompt content, raw input /
    output, tool arguments, credentials, or secrets — none are fields.
    """

    status: str
    reason_code: str | None
    decision_id: str | None = None
    project_id: str | None = None
    correlation_id: str | None = None
    call_id: str | None = None
    engaged_dimensions: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        """True iff the request is allowed within every engaged policy limit."""
        return self.status == STATUS_ALLOWED

    @property
    def needs_human_review(self) -> bool:
        """True iff the decision escalated to conservative human review."""
        return self.status == STATUS_NEED_HUMAN_REVIEW

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order; no content)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "call_id": self.call_id,
            "engaged_dimensions": list(self.engaged_dimensions),
        }

    def audit_projection(self) -> dict[str, Any]:
        """A bounded audit projection — traceable by ids, never any content."""
        projection = self.to_dict()
        projection["traceable"] = True
        return projection


def _rejected(
    reason_code: str,
    *,
    project_id: Any = None,
    correlation_id: Any = None,
    call_id: Any = None,
) -> ReliabilityDecision:
    """Build a fail-closed ``rejected`` decision that allows nothing.

    Only echoes bindings that are themselves bounded tokens, so a malformed binding
    never leaks back through the projection.
    """
    return ReliabilityDecision(
        status=STATUS_REJECTED,
        reason_code=reason_code,
        decision_id=None,
        project_id=project_id if _is_bounded_token(project_id, MAX_ID_LENGTH) else None,
        correlation_id=correlation_id if _is_bounded_token(correlation_id, MAX_ID_LENGTH) else None,
        call_id=call_id if _is_bounded_token(call_id, MAX_ID_LENGTH) else None,
    )


def _coerce_policy(policy: Any) -> ReliabilityPolicy | None:
    """Coerce ``policy`` to a :class:`ReliabilityPolicy`, or ``None`` if unshaped.

    Accepts a :class:`ReliabilityPolicy` directly, or a policy-shaped mapping whose
    keys are all known policy fields (an unknown key fails closed).  Pure; mutates
    nothing.
    """
    if isinstance(policy, ReliabilityPolicy):
        return policy
    if isinstance(policy, Mapping):
        if any(key not in _POLICY_FIELDS for key in policy):
            return None
        return ReliabilityPolicy(**{key: policy[key] for key in policy})
    return None


def _coerce_request(request: Any) -> ReliabilityRequest | None:
    """Coerce ``request`` to a :class:`ReliabilityRequest`, or ``None`` if unshaped.

    Accepts a :class:`ReliabilityRequest` directly, or a mapping whose keys are all
    known request fields and which supplies the required binding / identity fields (an
    unknown / missing-required key fails closed).  Pure; mutates nothing.
    """
    if isinstance(request, ReliabilityRequest):
        return request
    if isinstance(request, Mapping):
        if any(key not in _REQUEST_FIELDS for key in request):
            return None
        if not all(key in request for key in ("project_id", "correlation_id", "call_id")):
            return None
        return ReliabilityRequest(**{key: request[key] for key in request})
    return None


def evaluate_reliability(policy: Any, request: Any) -> ReliabilityDecision:
    """Evaluate explicit synthetic reliability facts against policy-shaped limits.

    Accepts an inert :class:`ReliabilityPolicy` (or a policy-shaped mapping) of limit
    facts and an inert :class:`ReliabilityRequest` (or a request-shaped mapping) of
    explicitly-supplied observed / estimated facts, and returns a deterministic
    :class:`ReliabilityDecision`.

    Resolution is fail-closed, in order: policy / request shape, trace binding, call
    identity, optional references, authority flags, numeric limit / fact validity,
    cost-unit agreement, circuit vocabulary, engaged-dimension pairing (a fact without
    its limit, a limit without its fact, an unpaired / mismatched rate-limit window, or
    an empty policy fails closed), circuit consistency, and then the bounded dimension
    judgements.  An over-budget condition
    yields ``need_human_review``; a timeout / rate-limit / open-circuit breach yields
    ``denied``; only a request within every engaged limit is ``allowed``.

    Pure: writes nothing, performs no I/O, reads no clock, and mutates neither input.
    """
    # 1. policy / request shape ----------------------------------------------
    coerced_policy = _coerce_policy(policy)
    if coerced_policy is None:
        return _rejected(CODE_MALFORMED_POLICY)
    coerced_request = _coerce_request(request)
    if coerced_request is None:
        return _rejected(CODE_MALFORMED_REQUEST)

    p = coerced_policy
    r = coerced_request

    # 2. trace binding --------------------------------------------------------
    if r.project_id is None or r.correlation_id is None:
        return _rejected(CODE_MISSING_BINDING)
    if not _is_bounded_token(r.project_id, MAX_ID_LENGTH) or not _is_bounded_token(r.correlation_id, MAX_ID_LENGTH):
        return _rejected(CODE_MALFORMED_BINDING, project_id=r.project_id, correlation_id=r.correlation_id)

    # 3. call identity --------------------------------------------------------
    if r.call_id is None:
        return _rejected(CODE_MISSING_CALL_IDENTITY, project_id=r.project_id, correlation_id=r.correlation_id)
    if not _is_bounded_token(r.call_id, MAX_ID_LENGTH):
        return _rejected(CODE_MALFORMED_CALL_IDENTITY, project_id=r.project_id, correlation_id=r.correlation_id)

    def reject(code: str) -> ReliabilityDecision:
        return _rejected(code, project_id=r.project_id, correlation_id=r.correlation_id, call_id=r.call_id)

    # 4. optional bounded references -----------------------------------------
    for value in (r.provider, r.tool_name, r.prompt_id, r.window, p.rate_window):
        if value is not None and not _is_bounded_token(value, MAX_ID_LENGTH):
            return reject(CODE_MALFORMED_REFERENCE)

    # 5. authority flags: any truthy flag claims forbidden authority ----------
    if r.authority_flags is not None:
        if not isinstance(r.authority_flags, Mapping):
            return reject(CODE_MALFORMED_REQUEST)
        if len(r.authority_flags) > MAX_AUTHORITY_FLAGS:
            return reject(CODE_FORBIDDEN_AUTHORITY)
        for key, value in r.authority_flags.items():
            if not _is_bounded_token(key, MAX_LABEL_LENGTH):
                return reject(CODE_MALFORMED_REQUEST)
            if value:
                return reject(CODE_FORBIDDEN_AUTHORITY)

    # 6. allow_recovery_probe must be a real bool ----------------------------
    if not isinstance(p.allow_recovery_probe, bool):
        return reject(CODE_MALFORMED_LIMIT)

    # 7. numeric limit validity ----------------------------------------------
    if p.max_duration_ms is not None and not _is_finite_nonneg_number(p.max_duration_ms, MAX_DURATION_MS):
        return reject(CODE_MALFORMED_LIMIT)
    if p.max_cost_units is not None and not _is_finite_nonneg_number(p.max_cost_units, MAX_COST_UNITS):
        return reject(CODE_MALFORMED_LIMIT)
    if p.max_requests is not None and not _is_nonneg_int(p.max_requests, MAX_COUNT):
        return reject(CODE_MALFORMED_LIMIT)
    if p.failure_threshold is not None and not _is_nonneg_int(p.failure_threshold, MAX_COUNT):
        return reject(CODE_MALFORMED_LIMIT)

    # 8. numeric fact validity ------------------------------------------------
    for value in (r.elapsed_ms, r.estimated_duration_ms):
        if value is not None and not _is_finite_nonneg_number(value, MAX_DURATION_MS):
            return reject(CODE_MALFORMED_FACT)
    for value in (r.estimated_cost_units, r.consumed_cost_units):
        if value is not None and not _is_finite_nonneg_number(value, MAX_COST_UNITS):
            return reject(CODE_MALFORMED_FACT)
    for value in (r.request_count, r.recent_failure_count):
        if value is not None and not _is_nonneg_int(value, MAX_COUNT):
            return reject(CODE_MALFORMED_FACT)

    # 9. cost-unit vocabulary + agreement ------------------------------------
    for unit in (p.cost_unit, r.cost_unit):
        if unit is not None and unit not in COST_UNITS:
            return reject(CODE_UNKNOWN_UNIT)
    if p.cost_unit is not None and r.cost_unit is not None and p.cost_unit != r.cost_unit:
        return reject(CODE_UNKNOWN_UNIT)

    # 10. circuit-state vocabulary -------------------------------------------
    if r.circuit_state is not None and r.circuit_state not in CIRCUIT_STATES:
        return reject(CODE_UNKNOWN_STATE)

    # 11. engaged-dimension pairing ------------------------------------------
    # A dimension is *referenced* when its limit or any of its facts is present; a
    # referenced dimension missing its counterpart fails closed (no silent skip).
    timeout_fact = r.elapsed_ms if r.elapsed_ms is not None else r.estimated_duration_ms
    timeout_referenced = p.max_duration_ms is not None or r.elapsed_ms is not None or r.estimated_duration_ms is not None
    rate_referenced = p.max_requests is not None or r.request_count is not None
    budget_referenced = p.max_cost_units is not None or r.estimated_cost_units is not None or r.consumed_cost_units is not None
    circuit_referenced = p.failure_threshold is not None or r.circuit_state is not None or r.recent_failure_count is not None

    engaged: list[str] = []
    if timeout_referenced:
        if p.max_duration_ms is None or timeout_fact is None:
            return reject(CODE_MISSING_LIMIT)
        engaged.append(DIMENSION_TIMEOUT)
    if rate_referenced:
        if p.max_requests is None or r.request_count is None:
            return reject(CODE_MISSING_LIMIT)
        # A request count is only meaningful relative to the bounded window it was
        # counted in: when the rate dimension is engaged, the policy window and the
        # request window must both be present and identical.  A missing window on
        # either side, or two different windows, is ambiguous and fails closed —
        # never a silent allow against an unpaired or mismatched window.
        if p.rate_window is None or r.window is None or p.rate_window != r.window:
            return reject(CODE_AMBIGUOUS_RATE_WINDOW)
        engaged.append(DIMENSION_RATE)
    if budget_referenced:
        if p.max_cost_units is None or (r.estimated_cost_units is None and r.consumed_cost_units is None):
            return reject(CODE_MISSING_LIMIT)
        engaged.append(DIMENSION_BUDGET)
    if circuit_referenced:
        if p.failure_threshold is None or r.circuit_state is None or r.recent_failure_count is None:
            return reject(CODE_MISSING_LIMIT)
        engaged.append(DIMENSION_CIRCUIT)

    # An empty policy can authorize nothing.
    if not engaged:
        return reject(CODE_MISSING_LIMIT)

    # 12. circuit consistency -------------------------------------------------
    # A closed circuit cannot truthfully carry a tripped failure count.
    if DIMENSION_CIRCUIT in engaged and r.circuit_state == CIRCUIT_CLOSED and r.recent_failure_count >= p.failure_threshold:
        return reject(CODE_INCONSISTENT_CIRCUIT)

    engaged_dimensions = tuple(engaged)

    def _decide(status: str, reason_code: str | None) -> ReliabilityDecision:
        decision_id = make_stable_id(
            "reliability",
            {
                "project_id": r.project_id,
                "correlation_id": r.correlation_id,
                "call_id": r.call_id,
                "status": status,
                "reason_code": reason_code,
                "engaged_dimensions": list(engaged_dimensions),
            },
        )
        return ReliabilityDecision(
            status=status,
            reason_code=reason_code,
            decision_id=decision_id,
            project_id=r.project_id,
            correlation_id=r.correlation_id,
            call_id=r.call_id,
            engaged_dimensions=engaged_dimensions,
        )

    # 13. dimension judgements -----------------------------------------------
    # Deterministic precedence: hard denies (timeout, rate, circuit) before the
    # conservative over-budget escalation; only a fully-clean request is allowed.
    if DIMENSION_TIMEOUT in engaged and timeout_fact > p.max_duration_ms:
        return _decide(STATUS_DENIED, CODE_TIMEOUT_EXCEEDED)
    if DIMENSION_RATE in engaged and r.request_count > p.max_requests:
        return _decide(STATUS_DENIED, CODE_RATE_LIMIT_EXCEEDED)
    if DIMENSION_CIRCUIT in engaged:
        if r.circuit_state == CIRCUIT_OPEN:
            return _decide(STATUS_DENIED, CODE_CIRCUIT_OPEN)
        if r.recent_failure_count >= p.failure_threshold:
            # half_open at/over threshold: only a permitted probe avoids a deny.
            if not (r.circuit_state == CIRCUIT_HALF_OPEN and p.allow_recovery_probe):
                return _decide(STATUS_DENIED, CODE_CIRCUIT_OPEN)
        elif r.circuit_state == CIRCUIT_HALF_OPEN and not p.allow_recovery_probe:
            return _decide(STATUS_DENIED, CODE_CIRCUIT_OPEN)

    if DIMENSION_BUDGET in engaged:
        projected = (r.consumed_cost_units or 0) + (r.estimated_cost_units or 0)
        if projected > p.max_cost_units:
            return _decide(STATUS_NEED_HUMAN_REVIEW, CODE_BUDGET_EXCEEDED)

    return _decide(STATUS_ALLOWED, None)


__all__ = [
    "MAX_ID_LENGTH",
    "MAX_LABEL_LENGTH",
    "MAX_DURATION_MS",
    "MAX_COST_UNITS",
    "MAX_COUNT",
    "MAX_AUTHORITY_FLAGS",
    "COST_UNIT_CREDITS",
    "COST_UNIT_USD_MICROS",
    "COST_UNIT_TOKENS",
    "COST_UNITS",
    "CIRCUIT_CLOSED",
    "CIRCUIT_OPEN",
    "CIRCUIT_HALF_OPEN",
    "CIRCUIT_STATES",
    "DIMENSION_TIMEOUT",
    "DIMENSION_RATE",
    "DIMENSION_BUDGET",
    "DIMENSION_CIRCUIT",
    "DIMENSIONS",
    "STATUS_ALLOWED",
    "STATUS_DENIED",
    "STATUS_NEED_HUMAN_REVIEW",
    "STATUS_REJECTED",
    "STATUSES",
    "CODE_MALFORMED_POLICY",
    "CODE_MALFORMED_REQUEST",
    "CODE_MISSING_BINDING",
    "CODE_MALFORMED_BINDING",
    "CODE_MISSING_CALL_IDENTITY",
    "CODE_MALFORMED_CALL_IDENTITY",
    "CODE_MALFORMED_REFERENCE",
    "CODE_FORBIDDEN_AUTHORITY",
    "CODE_MALFORMED_LIMIT",
    "CODE_MALFORMED_FACT",
    "CODE_UNKNOWN_UNIT",
    "CODE_UNKNOWN_STATE",
    "CODE_MISSING_LIMIT",
    "CODE_AMBIGUOUS_RATE_WINDOW",
    "CODE_INCONSISTENT_CIRCUIT",
    "CODE_TIMEOUT_EXCEEDED",
    "CODE_RATE_LIMIT_EXCEEDED",
    "CODE_CIRCUIT_OPEN",
    "CODE_BUDGET_EXCEEDED",
    "VALIDATION_CODES",
    "LIMIT_FACT_CODES",
    "DECISION_CODES",
    "REASON_CODES",
    "ReliabilityPolicy",
    "ReliabilityRequest",
    "ReliabilityDecision",
    "evaluate_reliability",
]
