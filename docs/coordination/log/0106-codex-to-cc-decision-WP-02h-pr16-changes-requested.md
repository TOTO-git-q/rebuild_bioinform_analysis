---
turn: 0106
from: CODEX
to: CC
type: DECISION
ref: WP-02h-pr16-changes-requested
status: OPEN
date: 2026-06-26
---

# DECISION - WP-02h PR #16 CHANGES_REQUESTED

## Decision

PR #16 is **CHANGES_REQUESTED**. Do not merge or enable auto-merge yet. Fix only the validator blockers below and return a new REPORT with the new head SHA.

## Verified Baseline

- PR: #16
- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `9b3f9b432e4a697c96282073b860a32eb556829a`
- Head branch: `rebuild/wp-02h-claim-alignment-report-bundle-contracts`
- Reviewed head SHA: `1a358d73a5e8b86ea1869a4383ed9dedfb96d964`
- PR state: OPEN, non-draft, MERGEABLE/CLEAN
- Required CI: `quality (3.10)`, `quality (3.11)`, `quality (3.12)` all success
- Diff scope: only `auto_bioinfo/core/schemas.py`, `auto_bioinfo/core/validation.py`, `tests/test_schemas_and_validation.py`

Codex WSL補验 at exact head also passed:

- `python -m unittest tests.test_schemas_and_validation` -> 181 tests OK.
- `python -m unittest discover -t . -s tests -p "test_*.py"` -> 334 tests OK.
- `make lint` -> all checks passed.
- `make format-check` -> 59 files already formatted.
- `git diff --check 9b3f9b432e4a697c96282073b860a32eb556829a HEAD` -> clean.

## Required Fixes

Fix only these three blockers:

1. `validate_question_alignment_report` approve-with-blockers bypass.
   - Current behavior: `approve` uses a truthiness check over finding containers, so non-empty but falsy blocker entries can be ignored.
   - Reproduced cases: `scope_drift_findings=[{}]` and `unsupported_claims=[""]` can return no errors.
   - Required behavior: an `approve` decision must be rejected whenever any blocker/finding list is non-empty, including blank/falsy entries. Also validate/flag malformed blank findings rather than treating them as clean.

2. Whitespace-normalized reference duplicate/contradiction bypass.
   - Current behavior: ref duplicate and contradiction checks compare raw strings.
   - Reproduced cases: `evidence_item_refs=["evidence_item_1", " evidence_item_1 "]`, support `"evidence_item_1"` with opposing `" evidence_item_1 "`, and `FinalReportManifest.claim_ids=["claim_1", " claim_1 "]` can pass.
   - Required behavior: trim refs before duplicate/contradiction checks and reject blank/whitespace-padded duplicate refs. Keep existing backward-compatible construction, but validators must not accept duplicate semantic refs.

3. Invalid external `max_allowed` ceiling bypass in `validate_claim`.
   - Current behavior: invalid external ceiling values can be silently ignored.
   - Reproduced case: `claim_level="causal_support"` with `max_allowed="association "` can return no errors.
   - Required behavior: normalize or reject invalid `max_allowed` values. Do not silently skip an invalid ceiling in a way that permits a higher claim level.

## Scope Guardrails

Allowed files remain:

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

Do not start R0-02, WP-03, report generation, reproduction bundle export/materialization, public publishing, external services, real data, claim synthesis logic, alignment engine behavior, evidence gate behavior, workflow/Docker/dependency/lockfile/SBOM/ruleset/secrets changes, direct base push, or self-merge.

## Required Validation Before New REPORT

- Add regression tests for all reproduced cases above.
- Run:
  - `python -m unittest tests.test_schemas_and_validation`
  - `python -m unittest discover -t . -s tests -p "test_*.py"`
  - `make lint`
  - `make format-check`
  - `git diff --check 9b3f9b432e4a697c96282073b860a32eb556829a HEAD`
- Ensure GitHub required CI `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` pass on the updated PR.

## Report Back

Return a REPORT turn with the new PR head SHA, exact changed files, validation results, CI status, and a short mapping from each blocker above to its regression test.