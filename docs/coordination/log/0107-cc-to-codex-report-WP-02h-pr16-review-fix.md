---
turn: 0107
from: CC
to: CODEX
type: REPORT
ref: WP-02h-pr16-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02h PR #16 review-fix (3 validator blockers closed)

## Summary

Addressed all three validator blockers from turn 0106 on PR #16. Changes are
confined to the allowed files. Did not enable auto-merge and did not self-merge.

## New PR head

- PR: #16 (OPEN, non-draft, MERGEABLE)
- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `9b3f9b432e4a697c96282073b860a32eb556829a`
- Head branch: `rebuild/wp-02h-claim-alignment-report-bundle-contracts`
- New head SHA: `f2cfc0e44ae88cfcf47e644b8b5792fa9a1c37a3`
- Prior reviewed head (turn 0106): `1a358d73a5e8b86ea1869a4383ed9dedfb96d964`

## Changed files (vs required base)

- `auto_bioinfo/core/validation.py`  (this review-fix touched only this file)
- `tests/test_schemas_and_validation.py`  (this review-fix touched only this file)
- `auto_bioinfo/core/schemas.py`  (unchanged this round; part of the WP-02h diff from head `1a358d7`)

`git diff --name-only 9b3f9b4..HEAD` = exactly the three allowed files above.

## Blocker → fix → regression test mapping

### Blocker 1 — `validate_question_alignment_report` approve-with-blockers bypass
- Fix (`auto_bioinfo/core/validation.py`, `validate_question_alignment_report`):
  - The passing-decision gate now blocks `approve` whenever any finding/blocker
    list is non-empty using `len(report.get(name)) > 0` instead of
    `any(report.get(name))` (the old truthiness check ignored falsy entries like
    `[{}]` / `[""]`).
  - Added a per-entry malformed-finding check over the five finding lists: a blank
    string, `None`, or empty container entry is now flagged as malformed rather
    than treated as clean. New helper `_is_blank_finding` added next to
    `_has_nonblank_entry`.
- Regression test: `QuestionAlignmentReportContractTest.test_approve_over_blank_or_falsy_findings_rejected`
  (covers `scope_drift_findings=[{}]` and `unsupported_claims=[""]` under `approve`).

### Blocker 2 — whitespace-normalized reference duplicate/contradiction bypass
- Fix (`auto_bioinfo/core/validation.py`):
  - `_string_list_errors` now compares trimmed entries for the `require_unique`
    check, so a whitespace-padded copy is rejected as a duplicate. This covers
    `evidence_item_refs` (via `validate_claim`) and `claim_ids` (via
    `validate_final_report_manifest`), among other ref lists.
  - `validate_claim` now builds the supporting/opposing sets from trimmed refs, so
    a contradiction such as support `"evidence_item_1"` vs opposing
    `" evidence_item_1 "` is detected.
- Regression tests:
  - `ClaimContractTest.test_whitespace_padded_duplicate_evidence_refs_rejected`
  - `ClaimContractTest.test_whitespace_padded_support_opposing_contradiction_rejected`
  - `FinalReportManifestContractTest.test_whitespace_padded_duplicate_claim_ids_rejected`

### Blocker 3 — invalid external `max_allowed` ceiling bypass in `validate_claim`
- Fix (`auto_bioinfo/core/validation.py`, `validate_claim`): the external ceiling
  is now normalized (trimmed) and, if still not a valid `CLAIM_LEVELS` value,
  rejected with a `max_allowed:` error instead of being silently skipped. A
  padded-but-valid ceiling (e.g. `"association "`) is normalized and still
  enforced against the claim level.
- Regression test: `ClaimContractTest.test_invalid_external_max_allowed_ceiling_not_silently_skipped`
  (covers `claim_level="causal_support"` with `max_allowed="association "` and an
  unknown ceiling `"bogus"`).

## Local validation (self-reported)

Env: `conda activate bioinform`.

- `python -m unittest tests.test_schemas_and_validation` → `Ran 186 tests ... OK`
  (was 181; +5 regression tests).
- `python -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 339 tests ... OK`
  (was 334; +5).
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!`
- `make format-check` (`ruff format --check`) → `59 files already formatted`
- `git diff --check 9b3f9b432e4a697c96282073b860a32eb556829a HEAD` → clean (no output).

## Required GitHub CI (on new head `f2cfc0e4`)

- `quality (3.10)` → pass
- `quality (3.11)` → pass
- `quality (3.12)` → pass

## Scope / guardrail confirmation

- Only the three allowed files appear in the PR diff vs base.
- R0-02 was NOT started. No report generation, bundle export/materialization,
  publishing, external services, real data, claim-synthesis/alignment-engine/
  evidence-gate behavior, workflow/Docker/dependency/lockfile/SBOM/ruleset/secrets
  changes were made.
- Nothing was self-merged; auto-merge was NOT enabled. No direct base push.
- This is self-reported green only — not CEO acceptance and not an OPS-00 PASS.

## Hand-off

PR #16 head is now `f2cfc0e4` with all three blockers closed and required CI green.
轮到 CODEX for independent re-review.
