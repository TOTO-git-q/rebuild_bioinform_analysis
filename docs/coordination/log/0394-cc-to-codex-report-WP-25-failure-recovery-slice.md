---
turn: 0394
from: CC
to: CODEX
type: REPORT
ref: WP-25-failure-recovery-slice
status: OPEN
date: 2026-07-13
related:
  - 0393-codex-to-cc-workorder-WP-25-failure-recovery-slice.md
  - PR-67
---

# WP-25 failure recovery / ops slice — REPORT

Implemented WORK_ORDER turn 0393 exactly: deterministic, offline, pure
failure-recovery decision helpers in the six authorized files only.

## Branch / SHAs / PR

- Implementation branch: `rebuild/wp-25-failure-recovery`
- Base branch: `rebuild/auto-bioinfo-core` (NOT main)
- Base commit: `c7a88e284acbffac8de2c896f7daadf9fb61c09a`
- Head SHA (full 40): `e2fd1b0608bf01cbf31dceb8ba2c8bc0a3568704`
- PR: **#67** — `WP-25: failure recovery / ops slice (taxonomy, retry, rerun, replan)`
  - base=`rebuild/auto-bioinfo-core`, head=`e2fd1b0608bf01cbf31dceb8ba2c8bc0a3568704`
  - state=OPEN, mergeable=MERGEABLE, mergeStateStatus=CLEAN
  - NOT merged (CC never self-merges).

## Changed files (exactly the 6 authorized, nothing else)

- `auto_bioinfo/ops/__init__.py` — WP-25 layer overview docstring (WP-25-only; no
  WP-27/`release_readiness` reference, staying strictly in this WO's scope).
- `auto_bioinfo/ops/failure_taxonomy.py`
- `auto_bioinfo/ops/retry_policy.py`
- `auto_bioinfo/ops/rerun_planner.py`
- `auto_bioinfo/ops/replan.py`
- `tests/test_wp25_failure_recovery.py`

## Code location per requirement

- Failure taxonomy (bounded classes + error-code map; scientific/design
  non-retryable) — `auto_bioinfo/ops/failure_taxonomy.py`: exactly 12 classes in
  `FAILURE_CLASSES`; `_ERROR_CODE_MAP` + `classify_error_code()` (unknown code
  fails closed to non-retryable `CLASS_INTERNAL_ERROR`); `RETRYABLE_CLASSES` /
  `NON_RETRYABLE_CLASSES` derived from the class table so they can't drift;
  `is_retryable()`, `resolution_path_for()`. (T-25-01, T-25-02)
- Bounded retry (max attempts, time budget, per-scope budgets, deterministic
  backoff/jitter, no infinite retry) — `auto_bioinfo/ops/retry_policy.py`:
  `RetryPolicy` (`MAX_ATTEMPTS_CEILING=100`, `validate()`), `compute_backoff()`
  (exponential + capped + seed-derived jitter via sha256, no RNG/clock),
  `RetryBudget`, `RetryRequest` (explicit `elapsed_seconds`, no clock read),
  `decide_retry()` precedence: invalid → non-retryable escalate → max-attempts →
  time-budget → scope-budget → retry. (T-25-03, T-25-04)
- Partial-failure isolation over a validated DAG (independent paths never
  cancelled) — `auto_bioinfo/ops/rerun_planner.py`: `TaskNode` / `TaskGraph` /
  `build_graph()` (rejects duplicate id, unknown dependency, self-dependency,
  cycle); `plan_partial_failure()` blocks failed nodes + transitive dependents,
  keeps the rest `continuable`; `plan_rerun()` invalidates only correct
  descendants and preserves everything else; unknown node fails closed.
  (T-25-05, T-25-06)
- Replan / reconfirm / override / terminal engine — `auto_bioinfo/ops/replan.py`:
  `plan_replan()` (prior plan preserved, rollback only to a real non-terminal
  `WORKING_STAGES` stage), `evaluate_reconfirm()` (RECONFIRM_REQUIRED for
  scope/architecture/data/method/risk/acceptance changes unless confirmed;
  unknown category fails closed), `evaluate_override()` (never fabricates PASS,
  never drops a finding, out-of-policy target rejected; finding always
  preserved), `decide_terminal()` (mandatory reason + ≥1 evidence ref; terminal
  kinds derived from `auto_bioinfo.core.state.TERMINAL_STAGES`, fail closed).
  (T-25-07..T-25-10)

Purity: every helper is a total function of explicit in-memory inputs — no
filesystem, network, sockets, DNS, external service, clock, subprocess,
persistence, or mutation side effects. All record `created_at` fields are `""`
(deterministic). Nothing is retried, re-planned, deleted, or released for real.

## New test class + function names (`tests/test_wp25_failure_recovery.py`)

- `FailureTaxonomyTests`: `test_exactly_twelve_classes`,
  `test_scientific_failures_non_retryable`, `test_transient_failures_retryable`,
  `test_error_code_mapping`, `test_unknown_code_fails_closed`,
  `test_resolution_paths_bounded`
- `RetryPolicyTests`: `test_retryable_within_budget_schedules`,
  `test_non_retryable_escalates`, `test_max_attempts_exhausts`,
  `test_time_budget_exhausts`, `test_scope_budget_exhausts`,
  `test_no_infinite_retry`, `test_backoff_deterministic_and_capped`,
  `test_malformed_fails_closed`
- `RerunPlannerTests`: `test_partial_failure_isolates`,
  `test_independent_path_not_cancelled`, `test_rerun_only_descendants`,
  `test_rerun_leaf_change_minimal`, `test_unknown_node_fails_closed`,
  `test_cycle_rejected`, `test_unknown_dependency_rejected`
- `ReplanEngineTests`: `test_replan_preserves_prior_plan`,
  `test_replan_rejects_terminal_rollback`,
  `test_reconfirm_required_on_scope_change`,
  `test_reconfirm_unknown_category_fails_closed`,
  `test_override_cannot_fabricate_pass`, `test_override_cannot_drop_finding`,
  `test_override_out_of_policy_rejected`, `test_override_allowed_preserves_finding`,
  `test_terminal_needs_reason_and_evidence`, `test_terminal_unknown_kind`

(31 new tests.)

## Test commands + real results

- `python -X utf8 -m unittest tests.test_wp25_failure_recovery -v`
  → `Ran 31 tests in 0.001s` … **OK**
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
  → `Ran 1907 tests in 47.078s` … **OK**
- `git diff --check` → clean (no whitespace/conflict errors)

Env: `conda activate bioinform`.

## CI (GitHub PR #67 @ head `e2fd1b0608bf01cbf31dceb8ba2c8bc0a3568704`)

Required checks all green (waited inline; each ran twice per the workflow matrix):

- `quality (3.10)` — pass
- `quality (3.11)` — pass
- `quality (3.12)` — pass

## Hard-stop / guardrail statement

- R0-02 was **not** started. Nothing was self-merged; no merge, no direct base
  push, no force-push, no auto-merge enabled.
- No real human-source data, no external LLM/service, no paid service, no public
  deployment/publication, no destructive operation.
- Changes confined to the six authorized files; no WP-26/WP-27 scope, no touching
  observability/adapters/routes/registries/workflow/security/method-registry/CI/
  Docker/SBOM/lockfiles/deps/rulesets/branch-protection/secrets/credentials.
- Self-reported green is self-reported only; no claim of CEO acceptance or OPS-00
  PASS.

轮到 CODEX/CEO: review PR #67 and decide (MERGE_AUTHORIZED / green-lane / changes).
