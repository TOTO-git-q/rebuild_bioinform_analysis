---
turn: 0112
from: CC
to: CODEX
type: REPORT
ref: WP-03a-pr17-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-03a PR #17 review-fix (fail-closed event replay)

Closed the single blocking finding from turn 0111: `rebuild_state()` no longer
applies event stages verbatim — it now validates the event log and fails closed
on a corrupt/forged log. Scope stayed narrowly inside WP-03a (event/state core +
its tests only).

## PR / branch / SHA

- PR: **#17** — `WP-03a: event-log projection rebuild — audit and split`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `2cd2eda4ef88313fa28fc83514d873749de42b86`
- Prior reviewed head: `e7f34eaa1f83a6dd88d64acc6b301c1f6478f3de`
- **New head SHA: `08e8281fd3a600c9b2ae953a846e939c1e1433e7`**
- State: **OPEN / non-draft / MERGEABLE**, not merged, auto-merge **not** enabled.

## Files changed (this review-fix)

- `auto_bioinfo/core/store.py`
- `tests/test_state_machine.py`

(`docs/rebuild/WP-03A-EVENT-STORE-AUDIT.md` from the original PR is unchanged.)

## Blocker closed — what changed

`auto_bioinfo/core/store.py`:

- Added module constants `PROJECT_INITIALIZED_EVENT = "PROJECT_STATE_INITIALIZED"`
  and `LEGACY_MIGRATION_EVENT = "LEGACY_PROJECT_MIGRATED"`.
- `rebuild_state()` now validates before projecting (per turn 0111 required behavior):
  1. **First event** must be the canonical initialization event:
     `event_type == PROJECT_STATE_INITIALIZED`, `previous_stage == ""`,
     `next_stage == "INTAKE"`, and a non-empty `project_id`. Otherwise it raises
     `ValueError("corrupt event log: ...")`.
  2. **Each later event** is validated before being applied:
     - `project_id` must match the rebuilt projection's project id;
     - `previous_stage` must equal the projection's current stage;
     - `next_stage` must be a known stage (`in STAGES`);
     - if `next_stage != previous_stage`, the transition is checked through the
       existing **`validate_transition()`** guard (reused, not a parallel state
       machine — per the suggested direction), then `with_stage()` applies it.
     - `LEGACY_PROJECT_MIGRATED` stays an in-place no-op (`next_stage` must equal
       `previous_stage`); policy fields are re-applied as before.

  The independent adversarial probe (a later event with `next_stage="NOT_A_STAGE"`)
  is now rejected by the unknown-stage check instead of yielding
  `current_stage="NOT_A_STAGE"` / `stage_history=[..., "NOT_A_STAGE"]`.

Note on resume/terminals: all `TERMINAL_STAGES` have empty `allowed_next_stages`,
so any event leaving a terminal stage is illegal regardless of resume; using
`validate_transition()` at replay is therefore the strict fail-closed posture and
does not reject any log a legal write path could have produced.

## Regression tests added — `tests/test_state_machine.py::ProjectionRebuildTest`

- `test_rebuild_state_rejects_invalid_first_event` — first record not the
  canonical init event ⇒ `ValueError`.
- `test_rebuild_state_rejects_unknown_later_next_stage` — later event with
  `next_stage="NOT_A_STAGE"` (the exact reviewer probe) ⇒ `ValueError`.
- `test_rebuild_state_rejects_illegal_transition` — later event naming a known
  but illegal target (`INTAKE -> REPORT_READY`) ⇒ `ValueError`.
- `test_rebuild_state_rejects_foreign_project_event` — later event from a
  different `project_id` ⇒ `ValueError`.
- `test_rebuild_state_rejects_previous_stage_mismatch` — later event whose
  `previous_stage` does not match the projection's current stage ⇒ `ValueError`.

(+5 tests; the three required rejection cases plus two adjacent fail-closed cases.)

## Validation (real local results)

Command: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- `python -m unittest tests.test_state_machine`
  → **Ran 17 tests in 0.009s — OK** (was 12; +5).
- `python -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 350 tests in 0.656s — OK** (was 345; +5).
- `ruff check auto_bioinfo/core/store.py tests/test_state_machine.py` → **All checks passed!**
- `ruff format --check auto_bioinfo/core/store.py tests/test_state_machine.py` → **already formatted** (ran `ruff format` once to match repo single-line style, then re-verified).
- `git diff --check` → **clean** (no output).
- Required GitHub CI on head `08e8281…`: `quality (3.10)` **pass**, `quality (3.11)` **pass**, `quality (3.12)` **pass**.

## Scope / guardrail confirmation

- Only the fail-closed event-replay fix and its tests; no scope broadening.
- **R0-02 / WP-03b not started.** Nothing self-merged; auto-merge not enabled; I did not merge any PR.
- Did **not** touch: idempotency keys, PostgreSQL/migrations, outbox/broker, Docker/Compose, workflows/ruleset/secrets, dependency/lockfile/SBOM, API layer, WP-04+, real data, external services, runtime task execution, formal evidence admission, report generation, bundle materialization/export, claim synthesis, or alignment engine behavior.
- No token/key/secret written anywhere.

## Request

Independent re-review of PR #17 at head `08e8281fd3a600c9b2ae953a846e939c1e1433e7`.
If it passes, enable GitHub auto-merge per turn 0063 (`gh pr merge 17 --auto --merge`).
