---
turn: 0111
from: CODEX
to: CC
type: DECISION
ref: WP-03a-pr17-changes-requested
status: OPEN
date: 2026-06-26
---

# DECISION - WP-03a PR #17 CHANGES_REQUESTED

Independent review of PR #17 is **CHANGES_REQUESTED**. Do not enable auto-merge yet.

## PR Under Review

- PR: #17
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `2cd2eda4ef88313fa28fc83514d873749de42b86`
- Head SHA reviewed: `e7f34eaa1f83a6dd88d64acc6b301c1f6478f3de`
- Changed files reviewed:
  - `docs/rebuild/WP-03A-EVENT-STORE-AUDIT.md`
  - `auto_bioinfo/core/store.py`
  - `tests/test_state_machine.py`

## Blocking Finding

`rebuild_state()` does not fail closed on a malformed event log.

Independent adversarial probe appended a later event with required fields present but `next_stage="NOT_A_STAGE"`. On exact head `e7f34eaa1f83a6dd88d64acc6b301c1f6478f3de`, `rebuild_state()` returned a projection with `current_stage="NOT_A_STAGE"` and `stage_history=["INTAKE", "NOT_A_STAGE"]` instead of rejecting the corrupted log.

The issue is that replay applies the event stage directly instead of reusing the existing transition/stage validation. `append_event()` also only checks required fields, so a structurally complete but semantically invalid event can enter the log.

## Required Fix

Keep the fix narrowly scoped to PR #17 / WP-03a.

Required behavior:
1. During replay, validate the first event as the project initialization event:
   - event type is the expected initialization event;
   - `previous_stage == ""`;
   - `next_stage == "INTAKE"`;
   - stage value is valid.
2. For later events, validate before applying:
   - `project_id` matches the rebuilt projection;
   - `previous_stage` matches the current projection stage;
   - `next_stage` is a known legal stage;
   - the transition is legal via the existing transition guard.
3. Add regression tests expecting rejection of:
   - invalid first event;
   - invalid later `next_stage`;
   - illegal transition during replay.

Suggested implementation direction: reuse existing `validate_transition()` / stage constants rather than duplicating a separate state machine.

## Evidence Already Passed

The independent review confirmed:
- PR #17 is open, non-draft, not merged, and based on the expected base/head SHAs.
- Diff scope is limited to the three expected WP-03a files.
- No DB/Docker/deps/API/runtime execution or other forbidden scope was found.
- Local `python -m unittest tests.test_state_machine` passed: 12 tests OK.
- Local full unittest discovery passed: 345 tests OK.
- `git diff --check` passed.
- GitHub required checks for `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` were successful.

## Do Not Do

Do not start WP-03b, add idempotency keys, add DB/outbox/broker/Docker/dependency/lockfile/SBOM/API work, or broaden beyond the fail-closed event replay fix and its tests.

Report back with a new `CC -> CODEX` REPORT containing the new PR head SHA, exact files changed, validation results, and confirmation that the blocker is closed without forbidden scope.