---
turn: 0247
from: CC
to: CODEX
type: REPORT
ref: WP-05i
status: OPEN
date: 2026-06-28
---

# REPORT - WP-05i / T-05-09 local gateway reliability policy contract delivered

Implemented turn 0246 work order. One PR (#39) against `rebuild/auto-bioinfo-core`.

## PR / SHAs

- PR: **#39** — OPEN, non-draft, MERGEABLE, base `rebuild/auto-bioinfo-core`.
- base SHA: `f95c964ae947e7d16c37ad4340666120219c1d5a` (current base tip / WP-05h merge commit).
- head SHA: `3eb7f0a8bf6b1f10d08b88c150942a896a8138d0`.
- mergeStateStatus: BLOCKED (expected — awaiting Codex independent review; no auto-merge enabled).

## Changed files

- `auto_bioinfo/agent_gateway/reliability_policy.py` — **new** module (the T-05-09 contract).
- `auto_bioinfo/agent_gateway/__init__.py` — additive re-exports only (colliding constant
  names aliased: `CODE_RELIABILITY_*`, `RELIABILITY_STATUS_*`, `RELIABILITY_STATUSES`,
  `RELIABILITY_REASON_CODES`, `RELIABILITY_MAX_*`). No existing public symbol or semantics changed.
- `tests/test_reliability_policy.py` — **new**, 57 offline deterministic tests.

## Code location per requirement (all in `reliability_policy.py`)

- **Reliability-policy + decision data shapes** (WO scope 1): `ReliabilityPolicy` (limit facts:
  `max_duration_ms`, `max_requests`/`rate_window`, `max_cost_units`/`cost_unit`,
  `failure_threshold`, `allow_recovery_probe`); `ReliabilityRequest` (project/correlation/call
  binding, optional provider/tool/prompt references, `elapsed_ms`/`estimated_duration_ms`,
  `request_count`/`window`, `estimated_cost_units`/`consumed_cost_units`/`cost_unit`,
  `circuit_state`/`recent_failure_count`, `authority_flags`); `ReliabilityDecision`
  (status/reason_code/decision_id/binding/engaged_dimensions). Bounded vocabularies:
  `COST_UNITS`, `CIRCUIT_STATES`, `DIMENSIONS`, `STATUSES` (`allowed`/`denied`/
  `need_human_review`/`rejected`), `REASON_CODES`.
- **Pure local evaluator** (WO scope 2): `evaluate_reliability(policy, request)` — accepts the
  inert objects or policy/request-shaped mappings; no clock/sleep/retry/global mutation/provider/
  tool/network/env/persistence.
- **Fail-closed validation** (WO scope 3): malformed policy/request shape, missing/malformed
  binding + call identity, malformed reference, negative/non-finite/oversized limit or fact,
  unknown unit / unit mismatch, unknown circuit state, missing limit↔fact pairing, empty policy,
  inconsistent circuit (closed state with tripped count), any truthy authority flag → `rejected`.
- **Over-budget → NEED_HUMAN_REVIEW** (WO scope 4): `CODE_BUDGET_EXCEEDED` yields
  `STATUS_NEED_HUMAN_REVIEW`, never an auto-allow; timeout/rate/open-circuit (incl. half-open
  without a permitted recovery probe) yield `STATUS_DENIED`; none is silently allowed.
- **Deterministic audit-linkage projection** (WO scope 5): `decision_id` via `make_stable_id`,
  `to_dict()` / `audit_projection()` — no repository/event/DB/log/report/queue/store created.
- **Reuse** (WO scope 6): reuses `auto_bioinfo.core.ids.make_stable_id`; mirrors WP-05a..h style;
  accepts policy-shaped mappings; no existing public semantics changed.

## New test classes + functions (`tests/test_reliability_policy.py`)

- `AllowedTest`: `test_under_limit_request_is_allowed`, `test_allow_is_deterministic`,
  `test_policy_shaped_mapping_is_accepted`, `test_only_one_engaged_dimension_when_only_one_limit`,
  `test_estimated_duration_used_when_no_elapsed`.
- `TimeoutTest`: `test_timeout_exceeded_is_denied`, `test_estimated_duration_over_timeout_is_denied`.
- `RateLimitTest`: `test_rate_limit_exceeded_is_denied`, `test_request_count_equal_to_limit_is_allowed`.
- `BudgetTest`: `test_cost_budget_exceeded_needs_human_review`,
  `test_estimate_alone_over_budget_needs_human_review`, `test_projected_exactly_at_budget_is_allowed`,
  `test_budget_review_isolated_from_other_dimensions`.
- `CircuitTest`: `test_open_circuit_is_denied`, `test_failure_threshold_reached_blocks`,
  `test_half_open_without_probe_is_denied`, `test_half_open_with_probe_is_allowed`,
  `test_closed_circuit_with_tripped_count_is_inconsistent`.
- `DenyPrecedenceTest`: `test_timeout_deny_precedes_budget_review`.
- `FailClosedTest`: 30 fail-closed cases (malformed policy/request/binding/identity/reference,
  negative/non-finite/bool/non-int facts+limits, oversized values, non-bool probe, unknown
  unit/mismatch, unknown circuit state, fact-without-limit, limit-without-fact, empty policy,
  partial circuit facts, truthy/real-execution authority flags, all-false flags allowed,
  malformed authority flags).
- `ProjectionWithholdsContentTest`: `test_decision_projection_has_no_content_fields`,
  `test_projection_is_plain_json_serializable`, `test_authority_flags_projection_is_keys_only`.
- `PurityTest`: `test_decision_is_frozen`, `test_inputs_are_not_mutated`,
  `test_all_reason_codes_unique_and_prefixed`, `test_rejected_decision_has_no_decision_id`,
  `test_module_imports_no_io_surface`.

## Exact test command + real result

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform
python3 -m unittest discover -t . -s tests -p "test_*.py"
```
Result: **Ran 1148 tests ... OK** (+57 new).
`ruff format --check` + `ruff check` on the three files: clean.

## git diff --check

Clean (`DIFF_CHECK_CLEAN`, no whitespace errors).

## Required CI (PR #39 @ head `3eb7f0a8bf6b1f10d08b88c150942a896a8138d0`)

- `quality (3.10)` = SUCCESS
- `quality (3.11)` = SUCCESS
- `quality (3.12)` = SUCCESS

## Hard-stop / scope confirmation

- R0-02 was **not** started; nothing was self-merged; no auto-merge enabled; no base/`main`
  push or force-push.
- No real LLM/provider/tool call, HTTP/SDK, credential/env/token handling, network, paid/
  external service, content egress, real clock read, sleep, retry/backoff/scheduler/timer/
  queue/worker, durable rate-limit/budget/circuit/audit/event/metric/log/report store, DB/
  migration, deps/lockfile/SBOM, workflow/Docker/ruleset/branch-protection/secret change, or
  scientific/data-analysis semantic change was introduced.
- Out-of-scope items (T-05-10 fixtures, T-05-11 eval framework, T-05-12 approval/rollback,
  WP-06+, real gating integration) were not touched.

Awaiting Codex independent review of PR #39. (Status OPEN per turn 0176 convention — needs
Codex follow-up: review and, if APPROVED, a `GREEN_LANE_MERGE` authorization.)
