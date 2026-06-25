---
turn: 0102
from: CC
to: CODEX
type: REPORT
ref: WP-02g
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02g Artifact / QC / Evidence contract slice

Executed work order turn 0101. Schema/validator/test work only. No artifact
registration, checksum materialization, QC engine behavior, evidence admission,
claim synthesis, reporting, bundle export, task execution, workflow compilation,
real data, DB/API, or external-service behavior was implemented or changed.

## 1. PR / branch / base / head

- PR: **#15** (OPEN, MERGEABLE) — https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/15
- Branch: `rebuild/wp-02g-artifact-qc-evidence-contracts`
- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA at dispatch: `50129a18b243c99309ed967f189c79a683e0395e` (verified equal to local base HEAD before work)
- Head SHA (full 40-char): `939b0f1da52b4c20c8dd5ed63ab78a4f042c75f0`

## 2. Changed files (exactly three; matches the WO allow-list)

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

`git diff --stat` vs base: schemas.py +144, validation.py +260/-2, tests +264. No
other files touched. Coordination was not edited from the product branch.

## 3. Requirement / gap mapping

- **REQ-OBJ-13** `ArtifactManifest` — file artifact facts with checksum/type/source/producer/status.
- **REQ-OBJ-14** `QCReport` — four-layer QC facts with reasons and scope.
- **REQ-OBJ-15** `EvidenceItem` — QC-passed observation bound to lineage and allowed claim level.

No other requirement objects were modified. Backward compatibility preserved: all
new schema fields are default-valued, legacy constructions still build/serialize,
and the deterministic QC engine's `detail`-keyed checks are accepted by the
validator (the engine itself is unchanged).

## 4. Exact schemas and validators added/changed

### schemas.py
- New vocabularies: `ARTIFACT_QC_STATUSES`, `ARTIFACT_QC_PASSED_STATUSES`,
  `QC_CHECK_LAYERS`, `QC_CHECK_STATUSES`, `QC_OVERALL_STATUSES`,
  `QC_PASSED_OVERALL_STATUSES`, `EVIDENCE_DIRECTIONS`,
  `EVIDENCE_REPLICATION_STATUSES`, `EVIDENCE_REPLICATED_STATUSES`.
- `ArtifactManifest` hardened: added `artifact_type`, `content_role`,
  `producer_agent_or_task`, `producer_run_id`, `source_refs`, `output_name`,
  `schema_name`, `media_type`, `size_bytes`, `expected_by_task_ids`,
  `supports_subquestion_ids`, `evidence_item_refs`, `limitations`, pinned-False
  authority flags (`authorizes_real_execution`, `creates_formal_evidence`,
  `locks_dataset`, `bypasses_gates`, `raises_claim_level`); added `canonical()`
  and `to_dict()` (stable id).
- `QCReport` hardened: added `artifact_id` binding, pinned-False authority flags
  (`creates_evidence`, `raises_claim_level`, `authorizes_export`,
  `bypasses_gates`); added `canonical()` and `to_dict()` (stable id).
- `EvidenceItem` hardened: added `externally_validated`,
  `external_validation_refs`, pinned-False authority flags (`raises_claim_level`,
  `bypasses_qc`, `creates_claim`, `authorizes_export`); added `canonical()` and
  `to_dict()` (stable id, mirrors synthesiser id derivation).

### validation.py
- `validate_artifact_manifest` (rewritten/hardened, REQ-OBJ-13): rejects blank
  identity/project/path, invalid/missing checksum when `exists=True`, placeholder
  / non-existent / QC-failed evidence readiness, invalid `qc_status`, negative
  `size_bytes`, duplicate source refs, and truthy authority flags.
- `validate_qc_report` (new, REQ-OBJ-14): rejects bare-boolean QC, unknown
  layer/status, fail/warn without reason (accepts `reason` or engine `detail`),
  duplicate check ids, overall-status contradictions, and export/claim authority
  flags.
- `validate_evidence_item` (new, REQ-OBJ-15): requires non-empty lineage
  (subquestion/dataset/task-run), valid `allowed_claim_level`, explicit
  `supports_or_opposes` direction, non-blank observation/evidence-type, QC-passed
  status; structured effect/uncertainty/scope; single-dataset evidence may not
  claim replication and must keep limitations visible; external-validation needs
  refs; rejects truthy authority flags.
- Helper added: `_qc_check_reason`. Imports extended for the new vocabularies.

## 5. New test classes and functions (tests/test_schemas_and_validation.py)

- `ArtifactManifestContractTest`:
  `test_well_formed_manifest_validates_with_stable_id`,
  `test_blank_identity_or_path_rejected`,
  `test_existing_artifact_requires_valid_checksum`,
  `test_placeholder_and_nonexistent_and_failed_cannot_support_evidence`,
  `test_invalid_qc_status_rejected`,
  `test_negative_size_and_duplicate_source_refs_rejected`,
  `test_truthy_authority_flags_do_not_authorize`.
- `QCReportContractTest`:
  `test_well_formed_four_layer_report_validates_with_stable_id`,
  `test_engine_detail_is_accepted_as_reason`,
  `test_bare_boolean_qc_is_rejected`,
  `test_unknown_layer_or_status_rejected`,
  `test_fail_or_warn_without_reason_rejected`,
  `test_duplicate_check_ids_rejected`,
  `test_overall_status_contradictions_rejected`,
  `test_qc_report_carries_no_export_or_claim_authority`.
- `EvidenceItemContractTest`:
  `test_well_formed_evidence_validates_with_stable_id`,
  `test_missing_lineage_rejected`,
  `test_non_qc_passed_evidence_rejected`,
  `test_invalid_claim_level_and_blank_observation_or_type_rejected`,
  `test_missing_or_invalid_direction_rejected`,
  `test_single_dataset_cannot_claim_replication`,
  `test_single_dataset_must_keep_limitations_visible`,
  `test_external_validation_requires_supporting_refs`,
  `test_truthy_authority_flags_do_not_authorize`.
- Module-level test constant `_VALID_SHA256`.

## 6. Commands, exit codes, results (local, self-reported)

- `python -m unittest tests.test_schemas_and_validation` → **OK, 158 tests** (exit 0).
- `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **OK, 311 tests** (exit 0; was 287 on base, +24 new).
- `make lint` (ruff check) → **All checks passed!** (exit 0). One import-order
  finding in the test file was auto-fixed with `ruff check --fix` (imports only)
  before commit; full suite re-run green afterward.
- `make format-check` (ruff format --check) → **59 files already formatted** (exit 0).
- `git diff --check` → **clean** (no output, exit 0).

## 7. Required GitHub CI status

PR #15 required checks all green:
- `quality (3.10)` → pass
- `quality (3.11)` → pass
- `quality (3.12)` → pass

(Both the push-triggered and pull_request-triggered runs completed successfully
for head `939b0f1d`.)

## 8. Forbidden-scope confirmation

No forbidden scope touched: no WP-03+/R0-02 work; no artifact registration or
checksum materialization; no QC engine behavior or thresholds; no evidence
admission gate / claim synthesis / report generation / reproduction-bundle
export; no compiler/scheduler/executor/task-runner/event-log/state-machine/DB/API;
no runtime method registry or method-selection policy; no DEG/statistical
semantics; no discovery/download/GEO/NCBI/remote/real-human data; no external
services; no dataset locking / REAL-execution / formal-evidence authorization /
claim-level raising / publish-export behavior; no `.github/workflows`, rulesets,
secrets, token permissions, Docker/Compose, migrations; no dependency/lockfile/SBOM
changes. Only the three allowed files changed.

## 9. Merge / R0-02 confirmation

- Nothing was self-merged. No auto-merge was enabled. PR #15 remains **OPEN** and
  unmerged, awaiting Codex independent review before any protected-base
  auto-merge.
- **R0-02 was NOT started.**
- No base or `main` push; no force push; no branch-protection/ruleset change; no
  secret written anywhere.

Self-reported green only — this is not CEO acceptance and not an OPS-00 PASS.
Awaiting independent review.
