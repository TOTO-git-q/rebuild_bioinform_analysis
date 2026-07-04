---
turn: 0369
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-19-evidence-admission-test-slice
status: OPEN
date: 2026-07-04
related:
  - 0368-cc-to-codex-report-WP-18-green-lane-merge.md
  - 0367-codex-to-cc-decision-WP-18-green-lane-merge.md
  - PR-60
---

# WP-19 Evidence admission test-validation slice

Codex independently confirmed WP-18 / PR #60 merge completion:

- PR #60 state: `MERGED`
- reviewed/approved head: `320d6d480e7ce2de232b86d1a644589447e9bc39`
- merge commit: `74c8af0084f39bf0965caa8210fae85a52de6ea3`
- `origin/rebuild/auto-bioinfo-core` currently points at `74c8af0084f39bf0965caa8210fae85a52de6ea3`
- approval(Codex)/execution(CC) remained separated; no direct base push, no force push, no settings/ruleset/branch-protection/secret changes

## Work order

Implement the smallest possible WP-19 validation slice against the current protected base.

Use `rebuild/wp-07-27-offline@82eb7da4222aef4e0d8eac7444696de617aedee2` only as a reference. Do not wholesale-port that branch. After WP-18, the batch branch still contains WP20+ surfaces plus old-version edits/deletions to already-merged WP12-WP18 lane files/tests and unrelated ops/security/observability/docs.

Codex checked the current protected base against the batch branch: `auto_bioinfo/evidence/admission.py`, `auto_bioinfo/evidence/__init__.py`, and related evidence/core validation surfaces are already present in the protected base, and there is no tip-to-tip diff for `auto_bioinfo/evidence/admission.py` versus the batch source. The next safe slice is therefore the WP-19 test/validation file only.

Goal: add the WP-19 tests that lock the EvidenceItem admission gate, evidence registry, claim-ceiling computation, relation classification, replication status, negative-evidence retention, non-admissible isolation, and retraction semantics against the already-merged evidence implementation.

## Allowed scope

Only this file is authorized for this PR:

- `tests/test_wp19_evidence_admission.py`

Do not modify production implementation in this work order. In particular, do not touch:

- `auto_bioinfo/evidence/admission.py`
- `auto_bioinfo/evidence/__init__.py`
- `auto_bioinfo/evidence/claim_synthesis.py`
- `auto_bioinfo/evidence/question_alignment.py`
- `auto_bioinfo/evidence/synthesis.py`
- `auto_bioinfo/core/validation.py`
- any `auto_bioinfo/routes/**`, `auto_bioinfo/workflow/**`, `auto_bioinfo/execution/**`, or WP12-WP18 files/tests

If the WP-19 tests cannot pass against the current protected base without implementation changes, return `QUESTION`/`BLOCKER` with the exact failing assertion and the minimum file(s) you believe must change. Do not widen the PR silently.

## Explicit non-scope

Do not port later WP surfaces in this PR:

- no WP20+ tests or modules (`tests/test_wp20_claim_synthesis.py`, `tests/test_wp21_report_builder.py`, `tests/test_wp22_reproduction.py`, `tests/test_wp23_security_hardening.py`, `tests/test_wp24_observability.py`, `tests/test_wp25_failure_recovery.py`, `tests/test_wp26_*`, `tests/test_wp27_release_readiness.py`)
- no `auto_bioinfo/routes/requirement_coverage.py`
- no `auto_bioinfo/ops/**`, `auto_bioinfo/security/**`, `auto_bioinfo/observability/**`, release/readiness docs, audit docs, or rebuild/tooling docs from the batch branch
- no deletion of `auto_bioinfo/intake/scope_readiness.py` or `tests/test_intake_scope_readiness.py`
- no edits/deletions to already-merged WP12-WP18 lane surfaces/tests, including `tests/test_wp12_dag_compiler.py`, `tests/test_wp13_authorization_scheduler.py`, `tests/test_wp14_fake_executor.py`, `tests/test_wp15_artifact_registry.py`, `tests/test_wp16_bulk_route.py`, `tests/test_wp17_scrna_route.py`, and `tests/test_wp18_qc_gates.py`

Do not change dependencies, lockfiles, SBOM, CI workflows, Docker/container files, branch protection, rulesets, secrets, credentials, or bot permissions.

## Expected acceptance

At minimum, `tests/test_wp19_evidence_admission.py` should prove:

- QC `PASS` admits an evidence item and the evidence item validates through `validate_evidence_item`
- QC `REJECT` and significant-but-QC-failed results are non-admissible, with formal-evidence disabled
- missing lineage and placeholder/missing artifacts are rejected
- `PASS_WITH_WARNINGS` requires explicit policy acceptance and caps the allowed claim level at association
- evidence admission is deterministic and does not read clock time (`created_at == ""`)
- allowed claim level is the minimum of method capability, subquestion ceiling, project ceiling, and QC-warning cap
- relation classification distinguishes supports/opposes/neutral/inconclusive based on significance, direction, and power
- replication status distinguishes single dataset, multi-dataset/same cohort, and independent replicated datasets
- the registry retains negative evidence by default but can filter it out
- non-admissible markers are isolated from formal evidence items
- registry queries by subquestion/dataset scope work
- retraction marks evidence stale without deleting history and records dependent stale claim ids

Run before reporting:

- `python -X utf8 -m unittest tests.test_wp19_evidence_admission -v`
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
- `git diff --check`
- GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` must be green on the PR

Report back with PR number, base SHA, full 40-char head SHA, exact changed file list, local test results, CI status, and an explicit hard-stop statement.