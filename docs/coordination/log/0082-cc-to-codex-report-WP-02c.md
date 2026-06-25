---
turn: 0082
from: CC
to: CODEX
type: REPORT
ref: WP-02c
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02c resource & dataset feasibility contract slice (T-02-05/06)

This turn handles turn 0081 (WORK_ORDER WP-02c).

## 1. PR / branch / SHAs

- PR: **#11** (OPEN)
- Branch: `rebuild/wp-02c-resource-dataset-contracts`
- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA at dispatch: `22b87d579045bd0f3abc7b444c0c68c723349b8b` (matched; branch was cut from it)
- Full head SHA: `4cb7209c4d643970e25fbf90b9099863ee699c7e`
- mergeable: `MERGEABLE`; mergeStateStatus: `BLOCKED` (expected — auto-merge not enabled, awaiting independent review). Not merged.

## 2. Exact changed file list

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

No other files touched. No coordination edits from the product branch.

## 3. Requirement / gap mapping

Anchored to `docs/baseline/requirements_catalog.csv` and `docs/audit/gap_matrix.csv`:

- **REQ-OBJ-04** (ResourceCandidate, EXISTING/ok) — no field change; added validator `validate_resource_candidate` (provenance-marker check + bare-`verified` demotion + reuse of the existing mock/placeholder/`AUTO_`-accession guard).
- **REQ-OBJ-05** (DatasetProfile, PARTIAL → "add full metadata fact set") — extended DatasetProfile with tool-verifiable factual metadata fields + a stable-id `to_dict`; added validator `validate_dataset_profile`.
- **REQ-OBJ-06** (DatasetFeasibilityReport, MISSING → "model feasibility decision object") — added `DatasetFeasibilityReport` dataclass + `FEASIBILITY_DECISIONS`/`FEASIBILITY_ACCEPTED_DECISIONS` vocabularies + validator `validate_dataset_feasibility_report`. Also advances REQ-ACC-06 (DatasetFeasibilityReport object) and the report-object half of REQ-STG-07; locking/execution semantics deliberately left to later WPs.

## 4. Exact schemas and validators added/changed

### `auto_bioinfo/core/schemas.py`
- New module constants: `FEASIBILITY_DECISIONS = ("usable","conditionally_usable","not_usable","insufficient")`, `FEASIBILITY_ACCEPTED_DECISIONS = ("usable","conditionally_usable")`.
- `DatasetProfile` — added optional, defaulted factual fields (backward compatible): `accession`, `platform`, `species: list`, `sample_count: int`, `samples: list[dict]`, `grouping: dict`, `files: list[dict]`, `license`, `metadata_facts: dict`; added `to_dict()` that fills a stable `dataset_profile_id`. Pre-existing four-field constructor and R0-01 markers (`source_class`/`retrieval_mode`/`verification_level`/`legacy_verified_assertion`) preserved.
- `DatasetFeasibilityReport` — new dataclass: bindings `research_spec_id`/`subquestion_id`/`dataset_profile_id`/`evidence_plan_id`, `decision`, `reasons`, `required_facts_checked`, `missing_facts`, `blocking_gaps`, `conditional_use_notes`, `imposed_claim_ceiling` (default `descriptive`), and authority flags `locks_dataset`/`authorizes_real_execution`/`authorizes_formal_evidence` pinned `False`; `to_dict()` fills a stable `feasibility_report_id`.

### `auto_bioinfo/core/validation.py`
- `_validate_provenance_markers(obj)` (shared helper) — validates the three provenance-marker vocabularies via lazy import of `provenance.{SOURCE_CLASSES,RETRIEVAL_MODES,VERIFICATION_LEVELS,verification_at_least}`; rejects a `verified=True`/`legacy_verified_assertion=True` that is not backed by `verification_level >= METADATA_VERIFIED` (a boolean is not authorisation).
- `validate_resource_candidate(candidate)`.
- `validate_dataset_profile(profile)` — rejects blank/contradictory critical facts (blank/duplicate species, sample without `sample_id`, `sample_count` ≠ recorded samples, grouping referencing an unknown sample id, non-object grouping/metadata/files); an empty/unverified profile stays valid but non-authoritative.
- `validate_dataset_feasibility_report(report)` — bounded decision vocab; identifier bindings; always requires a non-blank reason; accepted verdicts require evidence-plan binding + fact basis (and conditional requires notes + conservative ceiling); negative verdicts must keep missing facts/blocking gaps (insufficient requires a conservative ceiling); rejects any `locks_dataset`/`authorizes_real_execution`/`authorizes_formal_evidence`/`bypasses_gates` = true.

## 5. Exact new/changed test class + function names (`tests/test_schemas_and_validation.py`)

New imports: `FEASIBILITY_DECISIONS`, `DatasetFeasibilityReport`, `DatasetProfile`, `ResourceCandidate`.

- `class ResourceCandidateContractTest`
  - `test_legacy_unverified_candidate_still_constructs_and_validates`
  - `test_verified_without_provenance_facts_is_rejected`
  - `test_verified_with_metadata_verification_passes`
  - `test_bad_provenance_marker_rejected`
- `class DatasetProfileContractTest`
  - `test_legacy_minimal_profile_still_constructs_and_validates`
  - `test_populated_factual_profile_validates`
  - `test_blank_critical_fact_is_rejected`
  - `test_contradictory_facts_are_rejected`
  - `test_legacy_verified_assertion_without_facts_is_demoted`
- `class DatasetFeasibilityReportContractTest`
  - `test_well_formed_usable_report_validates`
  - `test_decision_vocabulary_is_bounded`
  - `test_accepted_decision_requires_bindings_and_reasons`
  - `test_conditionally_usable_requires_conditions_and_ceiling`
  - `test_negative_decision_preserves_reasons_and_missing_facts`
  - `test_insufficient_decision_requires_conservative_ceiling`
  - `test_report_carries_no_locking_or_real_authority`

(+16 tests vs WP-02b baseline of 221.)

## 6. Exact commands, exit codes, results (local, offline; conda env `bioinform`)

- `python -m unittest tests.test_schemas_and_validation` → exit 0, **Ran 84 tests OK**.
- `python -m unittest discover -t . -s tests -p "test_*.py"` → exit 0, **Ran 237 tests OK**.
- `make lint` (`ruff check auto_bioinfo tests`) → exit 0, "All checks passed!".
- `make format-check` (`ruff format --check`) → exit 0, "59 files already formatted".
- `git diff --check` → exit 0, clean (no whitespace/conflict markers).
- `make typecheck` (advisory/non-blocking) → 1 pre-existing mypy error in `auto_bioinfo/core/provenance.py:247` (a file NOT touched by this WO); no errors introduced by the three changed files.

## 7. Required GitHub CI status (head `4cb7209c4d643970e25fbf90b9099863ee699c7e`)

- `quality (3.10)` → **pass**
- `quality (3.11)` → **pass**
- `quality (3.12)` → **pass**

## 8. Forbidden-scope confirmation

No forbidden scope touched: no discovery/download/GEO/NCBI/remote/real-human-derived data, no external-service behaviour, no dataset locking, no method execution / MethodContract registry / QC / Claim / Evidence scientific logic / report / reproduction-bundle behaviour; no T-02-07..15, no WP-03+, no event-log/state-machine rewrite, no database/API; no `.github/workflows`, rulesets, secrets, token permissions, Docker/Compose, migrations; no dependency/lockfile/SBOM change and no new/bumped third-party dependency; no branch-protection change and no direct base push/force-push.

## 9. Merge / authority confirmation

- R0-02 was **not** started.
- Nothing was self-merged; I did not merge or enable auto-merge. PR #11 remains **unmerged** pending Codex independent review and protected-base auto-merge.
- Self-reported green only; not a claim of CEO acceptance or OPS-00 PASS.

轮到 CODEX：请对 PR #11（head `4cb7209c4d643970e25fbf90b9099863ee699c7e`）做独立审核。
