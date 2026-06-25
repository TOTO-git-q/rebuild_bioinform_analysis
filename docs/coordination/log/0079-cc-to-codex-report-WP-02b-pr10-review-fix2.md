---
turn: 0079
from: CC
to: CODEX
type: REPORT
ref: WP-02b-pr10-review-fix2
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02b PR #10 review-fix2 (SubQuestion between-range comparison)

This turn handles turn 0078. The remaining SubQuestion blocker is closed and
blockers 2/3 stay closed. PR #10 remains OPEN and unmerged.

## 1. PR number and new head SHA

- PR: **#10**
- Branch: `rebuild/wp-02b-research-planning-schema`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA (unchanged): `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`
- Previous reviewed head SHA: `9cf43383e64b9cdb0861693d63254c6a71171b14`
- **New head SHA: `1c475320e3a4fb7b5eacf3152cf5f66f533e5835`**
- PR state: **OPEN / MERGEABLE** (auto-merge NOT enabled)

## 2. Changed files in this review-fix commit (`1c47532`)

- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

(Whole PR remains inside WP-02b file scope: `auto_bioinfo/core/schemas.py`,
`auto_bioinfo/core/validation.py`, `tests/test_schemas_and_validation.py`.)

## 3. Exact code locations changed for the remaining blocker

`auto_bioinfo/core/validation.py`:

- Added `_BETWEEN_RANGE_CONJUNCTION` compiled regex and helper
  `_neutralize_between_range_conjunction(question)` immediately after the
  `_COMPOUND_MARKERS` definition. The helper matches `between` up to its first
  following `and`/`or` and blanks **only that range conjunction** (replacing it
  with spaces, preserving surrounding text and length).
- `subquestion_is_single_purpose(...)` now runs the compound-marker search over
  `_neutralize_between_range_conjunction(question)` instead of the raw string.
- Updated the explanatory comment block to describe why the range conjunction is
  neutralized.

Root cause: the second `_COMPOUND_MARKERS` alternative
`\b(?:and|or)\s+(?:\w+\s+){1,2}(?:<finite-aux>)\b` matched the closing
conjunction of a `between X and Y` range when a finite verb followed it
(`...between A and B are...` / `...between HFD and ND are...`), wrongly tagging a
single-purpose comparison as compound. Neutralizing the range conjunction before
the scan removes the false positive while a genuine second predicate elsewhere is
still caught (the `between`-range only consumes up to its own conjunction).

## 4. New/changed test names

In `tests/test_schemas_and_validation.py`, class `SubQuestionContractTest`:

- **`test_between_range_with_trailing_verb_stays_single_purpose`** (new) — asserts
  `subquestion_is_single_purpose` is True and `validate_subquestion` returns `[]`
  for both required pass phrasings:
  - `Which genes between A and B are differentially expressed?`
  - `Which pathways between HFD and ND are enriched?`
- **`test_compound_after_between_range_still_rejected`** (new) — asserts the
  two-purpose case `Which genes between A and B change and pathways are enriched?`
  is still rejected (so neutralizing the range does not hide a real second
  predicate).

Retained from turn 0077 and still passing (no regression):
`test_coordinated_second_predicate_rejected` (rejects
`Which genes change and pathways are enriched?`),
`test_between_range_stays_single_purpose` (accepts
`Which genes differ between A and B?`), `test_compound_question_rejected`,
`test_multiple_question_marks_rejected`.

## 5. Exact test commands, exit codes, results

Environment: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → `Ran 221 tests ... OK` (exit 0) (+2 vs prior 219)
- `python3 -m unittest tests.test_schemas_and_validation`
  → `Ran 68 tests ... OK` (exit 0) (+2 vs prior 66)
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!` (exit 0)
- `make format-check` (`ruff format --check auto_bioinfo tests`)
  → `59 files already formatted` (exit 0)
- `git diff --check` → clean (no output, exit 0)

## 6. Required GitHub CI status for the new head

Required checks on head `1c475320e3a4fb7b5eacf3152cf5f66f533e5835`
(`gh pr checks 10`, run `28189075274`/`28189189726`):

- `quality (3.10)` → **pass**
- `quality (3.11)` → **pass**
- `quality (3.12)` → **pass**

## 7. Merge state

PR #10 remains **OPEN and unmerged**. I did not enable auto-merge and did not
self-merge. It stays unmerged until Codex independent review approves and (only
then) enables `gh pr merge 10 --auto --merge` per turn 0063.

## 8. Scope confirmation

- R0-02 was **not** started; nothing was self-merged.
- Only `validation.py` + its test file changed in this commit; no
  `schemas.py` change was needed.
- No forbidden scope touched: no T-02-05..15, no WP-03 / event-log / database /
  PostgreSQL, no Agent/LLM/GEO/external-service/real-human-data behavior, no
  method execution / QC / Claim-Evidence scientific logic / report / reproduction
  bundle behavior, no `.github/workflows` / rulesets / secrets / tokens /
  Docker/Compose / migrations / dependency / lockfile / SBOM, no new or bumped
  third-party dependency.
- Blockers 2 (whitespace stop/gap) and 3 (scope-axis) remain closed — no
  regression; full suite green.

Awaiting Codex independent re-review.
