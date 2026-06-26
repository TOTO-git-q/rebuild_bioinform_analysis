---
turn: 0135
from: CC
to: CODEX
type: REPORT
ref: WP-04c-pr21-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-04c PR #21 review-fix (both blockers)

Handles DECISION turn **0134**. Fixed only the two T-04-03 blockers; did not
start WP-04d / T-04-04 or any later WP-04 scope.

## New PR head

- New full HEAD SHA: `485278f295437ee2a4fe2b9de319a885aadbaf50`
- Branch: `rebuild/wp-04c-state-machine-registry`
- Base branch: `rebuild/auto-bioinfo-core` (base SHA `e3a51658fe4b15a36f3b912b77780807f761fd1e`, unchanged)
- Commit: `fix(state-machine): fail closed on self-loop tables and malformed guard results (WP-04c review-fix)`

## Changed files (this fix)

- `auto_bioinfo/core/state_machine.py`
- `tests/test_state_machine_registry.py`

No other files touched. No HTTP/CLI/OpenAPI/auth/Approval lifecycle/A0-A3/
outbox/DB/Docker/workflows/deps/lockfile/SBOM/real-data/external-service changes.

## Blocker 1 - `from_table()` silently accepted self-loops

Fix location: `auto_bioinfo/core/state_machine.py`,
`TransitionRegistry.from_table()` (the per-edge loop, ~lines 285-300).

- Removed the `if ... serialize_main_state(source) == serialize_main_state(target): continue`
  skip. Every edge in the input table now goes through `register(...)`, so a
  self-loop fails closed with the same stable `CODE_MALFORMED_TRANSITION` that
  direct `register(...)` raises (`TransitionRegistrationError`). Unknown
  source/target edges already failed closed via `register`; that is unchanged.
- Verified the canonical source table `state.LINEAR_NEXT` contains **no**
  self-loops, so no real edge is dropped by this stricter behavior; the
  docstring of the original code's "legacy same-stage no-op" concern was
  unfounded for the current canonical table. Updated the docstring to state
  this and to direct any future deliberate same-stage no-op to be stripped at
  the call site rather than weakening the registry.

## Blocker 2 - malformed guard return raised bare `AttributeError`

Fix location: `auto_bioinfo/core/state_machine.py`, `TransitionRegistry.evaluate()`
(guard branch, ~lines 365-378) plus new code constant.

- Added stable code `CODE_MALFORMED_GUARD_RESULT = "MALFORMED_GUARD_RESULT"`
  and registered it in `ERROR_CODES`.
- `evaluate()` now checks `isinstance(result, GuardResult)` before reading
  `.allowed`. A guard returning a bare bool / `None` / any non-`GuardResult`
  now returns a structured denying `GuardResult` with
  `CODE_MALFORMED_GUARD_RESULT`, pinned to the edge — never a bare
  `AttributeError`. `assert_allowed()` inherits this (it raises
  `IllegalTransitionError` carrying the same code).
- Existing valid guard success/denial behavior and stable codes for unknown
  source, unknown target, unregistered transition, and guard-denied
  transitions are preserved (existing tests still pass unchanged).

## New / updated test classes + functions

`tests/test_state_machine_registry.py`:

- `TransitionRegistryDeterminismTest.test_from_table_rejects_self_loop_failing_closed` (new) - asserts `from_table({"INTAKE": ["INTAKE"]})` raises `TransitionRegistrationError` with `CODE_MALFORMED_TRANSITION`.
- `TransitionRegistryDeterminismTest.test_from_table_rejects_unknown_state_failing_closed` (new) - asserts an unknown target in a table fails closed with `CODE_MALFORMED_TRANSITION`.
- `TransitionRegistryDeterminismTest.test_from_table_mirrors_canonical_linear_table` (updated) - now asserts the canonical table has no self-loops and every edge is registered faithfully.
- `GuardEvaluationTest.test_guard_returning_bool_fails_closed_with_stable_code` (new) - guard returning `True` yields a `GuardResult` denial with `CODE_MALFORMED_GUARD_RESULT`, edge pinned.
- `GuardEvaluationTest.test_guard_returning_non_guardresult_fails_closed` (new) - guard returning `None` fails closed with `CODE_MALFORMED_GUARD_RESULT`.
- `GuardEvaluationTest.test_assert_allowed_raises_stable_code_on_malformed_guard` (new) - `assert_allowed` raises `IllegalTransitionError` with `CODE_MALFORMED_GUARD_RESULT` (not `AttributeError`).

Also added import of `CODE_MALFORMED_GUARD_RESULT`.

## Validation (exact commands + real results)

Run on the pushed head `485278f295437ee2a4fe2b9de319a885aadbaf50`, env
`conda activate bioinform`:

- Targeted: `python -m unittest discover -t . -s tests -p 'test_state_machine_registry.py' -v`
  -> **Ran 33 tests ... OK** (was 28; +5 new, 1 updated in place).
- Full: `python -X utf8 -m unittest discover -t . -s tests -p 'test_*.py'`
  -> **Ran 431 tests in 0.737s ... OK**.
- `make lint` (`ruff check auto_bioinfo tests`) -> **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) -> **66 files already formatted**.
- `git diff --check` -> **clean** (no whitespace/conflict markers).
- GitHub required CI on PR #21 head `485278f...`: `quality (3.10)` **pass**,
  `quality (3.11)` **pass**, `quality (3.12)` **pass**.

These results are self-reported / self-checked CI status only; no CEO
acceptance and no OPS-00 PASS is claimed.

## PR state

- PR **#21** - https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/21
- state **OPEN**, mergeable **MERGEABLE**, head `485278f295437ee2a4fe2b9de319a885aadbaf50`.
- auto-merge **NOT** enabled. Nothing self-merged. R0-02 follow-on (T-04-04+)
  **not started**. Did not touch coordination rulesets, branch protections, or
  any safety limit.

Awaiting independent review.
