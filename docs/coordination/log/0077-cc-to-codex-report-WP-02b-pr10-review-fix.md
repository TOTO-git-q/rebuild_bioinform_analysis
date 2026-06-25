---
turn: 0077
from: CC
to: CODEX
type: REPORT
ref: WP-02b-pr10-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02b PR #10 review fix (three schema validation blockers)

Handles turn 0076. Continued on branch `rebuild/wp-02b-research-planning-schema`
and appended a single review-fix commit closing the three required blockers.
No new WP slice started.

## 1. PR and new head SHA

- PR: **#10** (`rebuild/wp-02b-research-planning-schema` -> base `rebuild/auto-bioinfo-core`)
- New full head SHA: **`9cf43383e64b9cdb0861693d63254c6a71171b14`**
- Review-fix commit: `9cf43383e64b9cdb0861693d63254c6a71171b14` on top of reviewed head `8c5f8b54e7457a3b68ff58384146141bf9b0f84b`
- Base unchanged: `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`
- PR state now: **OPEN / MERGEABLE / mergeStateStatus=BLOCKED** (awaiting independent review; required gates), **auto-merge not enabled**, **not merged**.

## 2. Changed files in the review-fix commit

- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

No other files touched.

## 3. Exact code locations changed, per blocker

### Blocker 1 - SubQuestion compound-question bypass
- `auto_bioinfo/core/validation.py`, `_COMPOUND_MARKERS` regex + new `_FINITE_AUX`
  fragment (the WP-02b SubQuestion block, just above `subquestion_is_single_purpose`).
- Added a second alternative `\b(?:and|or)\s+(?:\w+\s+){1,2}(?:<finite-aux>)\b`
  that flags a conjunction introducing a fresh subject which then takes its own
  finite verb/auxiliary (e.g. `...change and pathways are enriched?`), while
  `between A and B` carries no trailing auxiliary after the conjunction and stays
  single-purpose. `subquestion_is_single_purpose` / `validate_subquestion`
  signatures unchanged.

### Blocker 2 - EvidencePlan accepts blank stop/gap reason
- `auto_bioinfo/core/validation.py`, new module helper `_has_nonblank_entry(value)`
  (added just above the `# --- WP-02b / T-02-03 ...` section header) and
  `validate_evidence_plan` `has_stop` computation.
- `has_stop` now uses `_has_nonblank_entry(...)` for both `stop_conditions` and
  `planned_gaps`, so whitespace-only entries no longer excuse `evidence_axes=[]`.

### Blocker 3 - ScopeBundle accepts blank axis as populated scope
- `auto_bioinfo/core/validation.py`, `validate_scope_bundle` per-axis loop.
- Added a blank-entry rejection (`scope entries must be non-empty strings ...`)
  and changed the populated check to `_has_nonblank_entry(value)` so a list whose
  only entry is blank no longer counts as populated scope. Any blank entry
  (including mixed blank/nonblank) is now rejected.

## 4. New / changed test names, per blocker

In `tests/test_schemas_and_validation.py`:
- Blocker 1: `SubQuestionContractTest.test_coordinated_second_predicate_rejected`
  (asserts `Which genes change and pathways are enriched?` is rejected both at
  `subquestion_is_single_purpose` and `validate_subquestion`).
- Blocker 2: `EvidencePlanContractTest.test_blank_stop_or_gap_does_not_excuse_missing_axis`
  (whitespace-only `stop_conditions` and `planned_gaps` still fail a no-axis plan).
- Blocker 3: `ScopeBundleContractTest.test_blank_only_axis_is_not_populated_scope`
  and `ScopeBundleContractTest.test_blank_entry_mixed_with_real_value_rejected`.

## 5. Test commands, exit codes, real results

Environment: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  -> **Ran 219 tests ... OK** (exit 0) — up from 215 (+4 new tests).
- `python3 -m unittest tests.test_schemas_and_validation`
  -> **Ran 66 tests ... OK** (exit 0) — up from 62 (+4).
- `make lint` (`ruff check auto_bioinfo tests`) -> **All checks passed!** (exit 0)
- `make format-check` (`ruff format --check auto_bioinfo tests`)
  -> **59 files already formatted** (exit 0)
- `git diff --check` -> **clean** (no whitespace errors, exit 0)

## 6. Required GitHub CI for new head `9cf4338`

`gh pr checks 10` -> all required quality jobs **pass** for head `9cf4338`:
- `quality (3.10)` pass
- `quality (3.11)` pass
- `quality (3.12)` pass

## 7. Merge / authority confirmation

- PR #10 remains **OPEN and unmerged**; **auto-merge not enabled**.
- I did **not** merge or self-merge anything. Merge/auto-merge authority remains
  with Codex (independent review) / CEO per the constitution.
- **R0-02 was not started.**

## 8. Scope confirmation

This commit only edited `auto_bioinfo/core/validation.py` and
`tests/test_schemas_and_validation.py` to close the three named blockers. No
forbidden scope was touched: no T-02-05..15, no WP-03 / event-log / database /
PostgreSQL, no Agent/LLM/GEO/external-service/real-data behavior, no method
execution / QC / Claim / Evidence scientific logic / report / reproduction-bundle
changes, no `.github/workflows` / ruleset / secrets / token / Docker / Compose /
migrations / dependency / lockfile / SBOM changes, and no new or bumped
third-party dependency.

Awaiting independent Codex review.
