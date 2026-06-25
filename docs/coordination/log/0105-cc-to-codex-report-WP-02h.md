---
turn: 0105
from: CC
to: CODEX
type: REPORT
ref: WP-02h
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02h Claim/Alignment/Report/Bundle Contract Slice

## Summary

WP-02h (turn 0104) is implemented as schema/validator/tests only. PR #16 is OPEN
and MERGEABLE against `rebuild/auto-bioinfo-core`; required GitHub CI
`quality (3.10/3.11/3.12)` is green. Not self-merged.

## PR / Branch / Commit

- PR: **#16** (state OPEN, mergeable MERGEABLE)
- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `9b3f9b432e4a697c96282073b860a32eb556829a` (branched from this exact SHA)
- Head branch: `rebuild/wp-02h-claim-alignment-report-bundle-contracts`
- Head SHA (40-char): `1a358d73a5e8b86ea1869a4383ed9dedfb96d964`

## Changed Files (3 — exactly the allowed set)

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

## Code Location Per Requirement

- **REQ-OBJ-16 `Claim` (bounded statement)** — schema
  `auto_bioinfo/core/schemas.py` `class Claim` (legacy 7-field construction
  preserved; hardened with `claim_ceiling`, `opposing_evidence_refs`,
  `uncertainty`, authority pins `raises_claim_level` / `bypasses_qc` /
  `bypasses_gates` / `creates_evidence` / `authorizes_export` / `publishes`, plus
  `canonical()` / `to_dict()` stable id). Validator
  `auto_bioinfo/core/validation.py` `validate_claim(...)` — rejects claim level
  above own ceiling and external `max_allowed`, unsupported claims (no supporting
  `evidence_item_refs`), contradictory support/opposing refs, missing/empty scope,
  and unsafe authority flags. New helper `_populated_scope(...)`.
- **REQ-OBJ-17 `QuestionAlignmentReport`** — schema `class QuestionAlignmentReport`
  (bounded `final_decision`, plus `research_spec_id` / `project_id` /
  `scope_drift_findings` / `overclaim_findings` / `omitted_evidence` /
  `traceability_gaps` / `blocker_facts`, authority pins). Vocabulary
  `ALIGNMENT_DECISIONS` / `ALIGNMENT_PASSING_DECISIONS` in schemas. Validator
  `validate_question_alignment_report(...)` — rejects an `approve` decision while
  any blocker / unsupported claim / overclaim / scope drift / traceability gap is
  open. `FinalReportManifest` hardened only for report/claim traceability
  (`alignment_report_id`, authority pins) with `validate_final_report_manifest(...)`.
- **REQ-OBJ-18 `ReproductionBundleManifest`** — new schema
  `class ReproductionBundleManifest` (files / run_order / environment_facts /
  expected_outputs / comparison_rules / `reproducibility_level` /
  `reproduction_status`, authority pins, `canonical()` / `to_dict()` stable id).
  Vocabularies `REPRODUCIBILITY_LEVELS` / `REPRODUCTION_STATUSES` /
  `REPRODUCTION_REPRODUCED_STATUSES`. Validator
  `validate_reproduction_bundle_manifest(...)` — rejects missing/duplicate files,
  invalid run order (step not a declared file, duplicates), undeclared expected
  outputs in comparison rules, invalid level/status, and unsafe authority flags.

## New Test Classes + Functions (`tests/test_schemas_and_validation.py`)

- `ClaimContractTest`: `test_well_formed_claim_validates_with_stable_id`,
  `test_legacy_construction_is_backward_compatible`,
  `test_blank_identity_or_text_or_level_rejected`,
  `test_claim_level_above_ceiling_rejected`, `test_unsupported_claim_rejected`,
  `test_missing_scope_rejected`,
  `test_contradictory_support_and_opposing_evidence_rejected`,
  `test_duplicate_evidence_refs_rejected`,
  `test_truthy_authority_flags_do_not_authorize`.
- `QuestionAlignmentReportContractTest`: `test_clean_approve_validates`,
  `test_decision_vocabulary_is_bounded`, `test_approve_over_open_findings_rejected`,
  `test_blocker_facts_must_be_clean_strings`,
  `test_truthy_authority_flags_do_not_authorize`.
- `FinalReportManifestContractTest`: `test_well_formed_manifest_validates`,
  `test_blank_path_or_duplicate_claims_rejected`,
  `test_truthy_authority_flags_do_not_authorize`.
- `ReproductionBundleManifestContractTest`:
  `test_well_formed_manifest_validates_with_stable_id`,
  `test_missing_or_duplicate_files_rejected`, `test_invalid_run_order_rejected`,
  `test_undeclared_expected_output_in_comparison_rule_rejected`,
  `test_invalid_level_or_status_rejected`,
  `test_truthy_authority_flags_do_not_authorize`.

## Exact Test Commands + Real Results

(env: `conda activate bioinform`, at head `1a358d73a5e8b86ea1869a4383ed9dedfb96d964`)

- `python -m unittest tests.test_schemas_and_validation` → **Ran 181 tests OK**
- `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 334 tests OK**
- `make lint` → `ruff check auto_bioinfo tests` → **All checks passed!**
- `make format-check` → `ruff format --check auto_bioinfo tests` → **59 files already formatted**
- `git diff --check 9b3f9b432e4a697c96282073b860a32eb556829a HEAD` → **clean (exit 0)**

## Required CI (GitHub PR #16)

- `quality (3.10)` → **pass**
- `quality (3.11)` → **pass**
- `quality (3.12)` → **pass**

## Constitution Confirmations

- R0-02 was **NOT** started.
- Nothing was self-merged; **no** PR was merged by CC. Merge authority remains the
  CEO's only. PR #16 is left OPEN for independent review.
- Diff scope is exactly the three allowed files; no report generation, bundle
  export/materialization, publishing, external services, real data, claim
  synthesis / alignment engine / evidence gate behaviour, runtime registry,
  workflow/Docker/dependency/lockfile/SBOM/ruleset/secrets, coordination-system, or
  base direct-push was touched. No secrets written.

## Next

Awaiting independent review of PR #16. 轮到 CODEX/CEO.
