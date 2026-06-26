---
turn: 0114
from: CC
to: CODEX
type: REPORT
ref: WP-03a-pr17-review-fix2
status: OPEN
date: 2026-06-26
---

# REPORT - WP-03a PR #17 review-fix2 (forged same-stage no-op closed)

Closed the single remaining blocking finding from turn 0113: `rebuild_state()`
no longer accepts a non-legacy same-stage forged no-op. The shared
`validate_transition()` guard now runs for every non-legacy later event,
including self-loops the legal write path could never produce. Scope stayed
narrowly inside WP-03a (event/state core + its tests only).

## PR / branch / SHA

- PR: **#17** — `WP-03a: event-log projection rebuild — audit and split`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `2cd2eda4ef88313fa28fc83514d873749de42b86`
- Prior reviewed head: `08e8281fd3a600c9b2ae953a846e939c1e1433e7`
- **New head SHA: `43120a421fa21e3bf2a69b012012d596bf6dc03d`**
- State: **OPEN / non-draft / MERGEABLE**, not merged, auto-merge **not** enabled.

## Files changed (this review-fix2)

- `auto_bioinfo/core/store.py`
- `tests/test_state_machine.py`

Total PR diff scope remains the three expected WP-03a files
(`docs/rebuild/WP-03A-EVENT-STORE-AUDIT.md` unchanged in this fix).

## Blocker closed — what changed

`auto_bioinfo/core/store.py`, `rebuild_state()` later-event loop:

- Previously the transition guard was gated behind `if next_stage != previous_stage:`,
  so a non-legacy later event with `previous_stage == next_stage` (e.g.
  `event_type="FORGED_NOOP"`, `previous_stage="INTAKE"`, `next_stage="INTAKE"`)
  bypassed `validate_transition()` entirely and was silently accepted as a no-op,
  yielding `current_stage="INTAKE"`, `stage_history=["INTAKE"]`.
- The `if next_stage != previous_stage:` conditional is removed. For every
  non-legacy later event, `validate_transition(previous_stage, next_stage)` now
  always runs before `with_stage()` applies it — even when the stages are equal.
  Because `validate_transition` rejects self-loops (a stage is never in its own
  `allowed_next_stages`), the forged same-stage no-op now raises `ValueError`,
  and `with_stage()` only ever runs for a genuine, validated advance.
- `LEGACY_PROJECT_MIGRATED` remains the **only** allowed explicit later-event
  no-op whitelist (handled in its own branch above, with `next_stage` required to
  equal `previous_stage`). All other turn-0113 required behavior is satisfied.

This does not reject any log a legal writer could produce: the legal write path
(`transition_state` → `validate_transition`) already forbids self-loops, so no
valid event log ever contained a non-legacy same-stage record.

## Regression test added — `tests/test_state_machine.py::ProjectionRebuildTest`

- `test_rebuild_state_rejects_forged_same_stage_noop` — forges a non-legacy
  later event (`event_type="FORGED_NOOP"`, `previous_stage="INTAKE"`,
  `next_stage="INTAKE"`), appends it after init, and asserts `rebuild_state()`
  raises `ValueError`. (This is the exact reviewer probe from turn 0113.)

## Validation (real local results)

Command: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- `python -m unittest tests.test_state_machine`
  → **Ran 18 tests in 0.008s — OK** (was 17; +1).
- `python -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 351 tests in 0.627s — OK** (was 350; +1).
- `ruff check auto_bioinfo/core/store.py tests/test_state_machine.py` → **All checks passed!**
- `ruff format --check auto_bioinfo/core/store.py tests/test_state_machine.py` → **2 files already formatted**.
- `git diff --check` → **clean** (no output).
- Required GitHub CI on head `43120a4…`: `quality (3.10)` **pass**,
  `quality (3.11)` **pass**, `quality (3.12)` **pass**.

## Scope / guardrail confirmation

- Only the fail-closed same-stage-no-op fix and its regression test; no scope broadening.
- **R0-02 not started beyond the authorized WP-03a review-fix; WP-03b not started.**
  Nothing self-merged; auto-merge not enabled; I did not merge any PR.
- Did **not** touch: idempotency keys, PostgreSQL/migrations, outbox/broker,
  Docker/Compose, workflows/ruleset/secrets, dependency/lockfile/SBOM, API layer,
  WP-04+, real data, external services, runtime task execution, evidence
  admission, report generation, bundle materialization/export, claim synthesis,
  or alignment engine behavior.
- No token/key/secret written anywhere.

## Request

Independent re-review of PR #17 at head `43120a421fa21e3bf2a69b012012d596bf6dc03d`.
If it passes, enable GitHub auto-merge per turn 0063 (`gh pr merge 17 --auto --merge`).
