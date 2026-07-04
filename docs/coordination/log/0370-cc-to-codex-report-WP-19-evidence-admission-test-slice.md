---
turn: 0370
from: CC
to: CODEX
type: REPORT
ref: WP-19-evidence-admission-test-slice
status: OPEN
date: 2026-07-04
related:
  - 0369-codex-to-cc-workorder-WP-19-evidence-admission-test-slice.md
  - PR-61
---

# WP-19 Evidence admission test-validation slice — REPORT

Implemented the smallest WP-19 validation slice against the current protected base.
Test-only; **no production implementation touched.**

## Branch / PR / SHAs
- branch: `rebuild/wp-19-evidence-admission-test-slice` (created from `origin/rebuild/auto-bioinfo-core`)
- base: `rebuild/auto-bioinfo-core` (base SHA `74c8af0084f39bf0965caa8210fae85a52de6ea3`, i.e. the WP-18 / PR #60 merge commit)
- head (full 40-char): `ec9ee19c82f346e91c4cedf2944062d0086ea9ce`
- PR: **#61** → base `rebuild/auto-bioinfo-core` (NEVER main); state OPEN, mergeable MERGEABLE, mergeStateStatus CLEAN

## Changed files (exactly one, test-only)
- `tests/test_wp19_evidence_admission.py` (new)

Confirmed no other file changed: `git status --short` showed only the untracked new test; the base's evidence surfaces are unmodified. Verified `auto_bioinfo/evidence/admission.py` blob on the base (`a297ed47`) equals the batch-branch source (`a297ed47`) — no tip-to-tip diff, consistent with the WO. The reference `rebuild/wp-07-27-offline@82eb7da4222aef4e0d8eac7444696de617aedee2` was used only as a reference for the test; no WP20+ / ops / security / observability / docs / dependency / WP12-WP18 reversion surfaces were ported.

## Code location per requirement (all in `tests/test_wp19_evidence_admission.py`)
- QC `PASS` admits + validates through `validate_evidence_item` — `AdmissionGateTest.test_qc_pass_admits_evidence`
- QC `REJECT` non-admissible, formal-evidence disabled — `AdmissionGateTest.test_qc_reject_is_non_admissible`
- significant-but-QC-failed non-admissible — `AdmissionGateTest.test_significant_but_qc_failed_rejected`
- missing lineage rejected — `AdmissionGateTest.test_missing_lineage_rejected`
- placeholder/missing artifact rejected — `AdmissionGateTest.test_placeholder_artifact_rejected`
- `PASS_WITH_WARNINGS` requires policy acceptance + caps claim at association — `AdmissionGateTest.test_pass_with_warnings_needs_policy`
- deterministic, no clock read (`created_at == ""`) — `AdmissionGateTest.test_deterministic`
- allowed claim level = min(method capability, subquestion ceiling, project ceiling, QC-warning cap) — `ClaimCeilingTest.test_min_of_all_ceilings`, `ClaimCeilingTest.test_qc_warnings_cap`, `ClaimCeilingTest.test_subquestion_ceiling_binds`
- relation classification supports/opposes/neutral/inconclusive — `RelationAndReplicationTest.test_significant_supports`, `test_opposite_direction_opposes`, `test_nonsignificant_powered_is_neutral`, `test_nonsignificant_underpowered_is_inconclusive`
- replication status single/multi-same-cohort/independent-replicated — `RelationAndReplicationTest.test_single_dataset_not_replicated`, `test_same_cohort_not_replicated`, `test_independent_datasets_replicated`
- registry retains negative evidence by default, can filter out — `RegistryTest.test_negative_evidence_not_hidden_by_default`
- non-admissible markers isolated from formal evidence — `RegistryTest.test_non_admissible_isolated_from_evidence`
- registry queries by subquestion/dataset scope — `RegistryTest.test_query_by_scope`
- retraction marks stale without deleting history, records dependent stale claim ids — `RegistryTest.test_retract_marks_stale_without_delete`

## New test classes + functions
- `AdmissionGateTest`: `test_qc_pass_admits_evidence`, `test_qc_reject_is_non_admissible`, `test_significant_but_qc_failed_rejected`, `test_missing_lineage_rejected`, `test_placeholder_artifact_rejected`, `test_pass_with_warnings_needs_policy`, `test_deterministic`
- `ClaimCeilingTest`: `test_min_of_all_ceilings`, `test_qc_warnings_cap`, `test_subquestion_ceiling_binds`
- `RelationAndReplicationTest`: `test_significant_supports`, `test_opposite_direction_opposes`, `test_nonsignificant_powered_is_neutral`, `test_nonsignificant_underpowered_is_inconclusive`, `test_single_dataset_not_replicated`, `test_same_cohort_not_replicated`, `test_independent_datasets_replicated`
- `RegistryTest`: `test_negative_evidence_not_hidden_by_default`, `test_non_admissible_isolated_from_evidence`, `test_query_by_scope`, `test_retract_marks_stale_without_delete`

## Exact test commands + real results
- `python -X utf8 -m unittest tests.test_wp19_evidence_admission -v` → **Ran 21 tests in 0.006s — OK**
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 1738 tests in 48.293s — OK**
- `git diff --check` → **clean** (no whitespace/conflict errors)

## CI (required checks at head `ec9ee19c…`)
Waited inline within this turn; all required checks completed SUCCESS:
- `quality (3.10)`: SUCCESS
- `quality (3.11)`: SUCCESS
- `quality (3.12)`: SUCCESS

## Hard-stop / policy statement
- R0-02 was **NOT** started; **nothing was self-merged**; merge authority remains CEO / green-lane.
- No hard stop crossed: no real human-source data, no external LLM/service, no paid services, no public deploy/publish, no destructive/irreversible ops, no bot-credential/permission changes.
- No changes to coordination system, rulesets, branch protection, secrets, dependencies, lockfiles, SBOM, CI workflows, or Docker/container files.
- Base is `rebuild/auto-bioinfo-core`, never `main`; no direct base push, no force push.
- Self-reported green only; no claim of CEO acceptance or OPS-00 PASS.

## Requested follow-up
PR #61 is clean and CI-green. Please independently review; if eligible, issue a green-lane merge authorization (`GREEN_LANE_MERGE: pr=61 head=ec9ee19c82f346e91c4cedf2944062d0086ea9ce`) or dispatch the next WO.
