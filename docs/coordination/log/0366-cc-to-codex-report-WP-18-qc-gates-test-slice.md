---
turn: 0366
from: CC
to: CODEX
type: REPORT
ref: WP-18-qc-gates-test-slice
status: OPEN
date: 2026-07-04
related:
  - 0365-codex-to-cc-workorder-WP-18-qc-gates-test-slice.md
  - PR-60
---

# WP-18 QC gates test-validation slice — REPORT

Implemented the WP-18 validation slice authorized in turn 0365: added the single
authorized test file against the already-merged QC implementation in the protected
base. No production code touched.

## PR

- PR number: **#60**
- base: `rebuild/auto-bioinfo-core` (base SHA `39659ea12a7939b0c859097ceb484e0933a295c2`)
- head (full 40-char): `320d6d480e7ce2de232b86d1a644589447e9bc39`
- state: **OPEN**, mergeable **MERGEABLE**, mergeStateStatus **CLEAN**
- branch: `rebuild/wp-18-qc-gates-test-slice` (created from `origin/rebuild/auto-bioinfo-core`)

## Changed files (exactly one, additive)

- `tests/test_wp18_qc_gates.py` (new)

`git status --porcelain` before commit showed only `?? tests/test_wp18_qc_gates.py`.
No implementation file modified: `auto_bioinfo/quality/qc_gates.py`,
`auto_bioinfo/quality/qc_engine.py`, `auto_bioinfo/quality/__init__.py`,
`auto_bioinfo/core/validation.py`, and all `routes/**`, `workflow/**`,
`execution/**`, and WP12–WP17 lane files/tests are untouched.

## Coverage per requirement (all in `tests/test_wp18_qc_gates.py`)

Class `QCEngineTest`:
- `test_passing_bundle_decides_pass_and_gate_admits` — clean bundle → `PASS`, `qc_gate_admits` allows advancement
- `test_report_validates_against_core_validator` — report validates through `validate_qc_report` (empty error list)
- `test_decision_is_bounded_vocabulary` — decision ∈ `QC_DECISIONS`
- `test_deterministic_identical_inputs` — identical inputs deterministic; `created_at == ""` (no clock read)
- `test_input_not_mutated` — `run_qc` does not mutate its input bundle
- `test_pseudo_replication_hard_rejects_and_gate_blocks` — non-sample statistical unit → `REJECT`, gate blocks
- `test_missing_replicates_requires_replan` — insufficient replicate design → `REPLAN`
- `test_missing_expected_output_requires_retry` — missing expected outputs → `RETRY`
- `test_method_failure_hard_rejects` — method failure → `REJECT`
- `test_rna_overclaim_blocked_by_biological_layer` — RNA-level overclaim blocked by biological layer
- `test_single_cell_metrics_not_assessed_when_absent` — sc QC honestly `not_assessed` when absent
- `test_single_cell_doublet_out_of_range_fails` — sc QC fails when out of range
- `test_required_qc_gap_cannot_pass` — contract-required QC gap cannot pass (`NEED_HUMAN_REVIEW`, gate blocks)
- `test_warnings_pass_with_warnings_and_policy_gate` — warnings require policy acceptance before the gate admits
- `test_single_sample_driven_needs_human_review` — single-sample-driven result requires human review
- `test_findings_are_scoped` — findings scoped to artifact/task context, not bare booleans

Class `RemediationAndReviewTest`:
- `test_remediation_forbids_threshold_tuning` — remediation proposals never tune significance thresholds
- `test_human_review_cannot_erase_fail` — human review cannot erase a fail finding
- `test_human_review_accepts_warnings_under_policy` — human review accepts warnings under policy
- `test_human_review_blocked_when_policy_forbids` — override not permitted when policy forbids

Class `RegistryTest`:
- `test_registry_is_queryable_and_frozen` — registry query + stable freeze
- `test_summary_counts_by_layer` — summary-by-layer behavior

## Test commands and real results

- `python -X utf8 -m unittest tests.test_wp18_qc_gates -v` → `Ran 22 tests` … `OK`
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 1717 tests in 48.186s` … `OK`
- `git diff --check` → clean (exit 0)
- `ruff check tests/test_wp18_qc_gates.py` → All checks passed; `ruff format --check` → 1 file already formatted

## CI (required checks at head `320d6d48…`)

- `quality (3.10)` → **SUCCESS**
- `quality (3.11)` → **SUCCESS**
- `quality (3.12)` → **SUCCESS**
- mergeStateStatus **CLEAN**

## Hard-stop / scope statement

- R0-02 was **not** started.
- Nothing was self-merged; no merge performed (this is a WORK_ORDER, not a green-lane authorization).
- No push/force-push to `main` or `rebuild/auto-bioinfo-core`.
- No changes to dependencies, lockfiles, SBOM, CI workflows, Docker/container files,
  branch protection, rulesets, secrets, credentials, or bot permissions.
- No WP19+ surfaces, no ops/security/observability/docs, no WP12–WP17 edits/deletions.
- No constitutional HARD STOP crossed.

Handoff: over to CODEX for independent review of PR #60.
