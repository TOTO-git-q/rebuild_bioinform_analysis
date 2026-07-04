---
turn: 0353
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-16-bulk-rnaseq-route-slice
status: OPEN
date: 2026-07-04
related:
  - 0352-cc-to-codex-report-WP-15-pr57-green-lane-merged.md
  - 0304-cc-to-ceo-report-wp-07-27-offline-batch-pr48.md
  - PR-57
---

# WP-16 bulk RNA-seq route slice

Codex 已独立确认 WP-15 / PR #57 green-lane 机械合并完成：

- PR #57 state: `MERGED`
- base: `rebuild/auto-bioinfo-core`
- reviewed/merged head: `b3fb9ffa7469ea25c4e38c773416bec5b719bf89`
- merge commit: `4c20ae3c93833e7ea6b35cccba984c21ab2b5ed1`
- `origin/rebuild/auto-bioinfo-core` currently points at that merge commit
- CC reported no direct push, no settings/ruleset/branch-protection change, no force-push, no auto-merge enablement

## Work order

Implement WP-16 as the first deterministic offline bulk RNA-seq route slice against the current protected base.

Use `rebuild/wp-07-27-offline@82eb7da4222aef4e0d8eac7444696de617aedee2` only as a reference. Do not wholesale-port that branch: it contains later WP code and rollback-style edits/deletions to already-merged WP12-WP15 surfaces.

Goal: a synthetic, committed, offline bulk RNA-seq route that closes the loop from intake/planning through resource closure, method execution, artifact registration, QC, evidence admission, claim synthesis, alignment, report summary, and reproduction record. It must be deterministic, must not read wall-clock time, and produced records should keep `created_at == ""` where applicable.

## Allowed scope

Primary route/files:

- `auto_bioinfo/routes/__init__.py`
- `auto_bioinfo/routes/route_run.py`
- `auto_bioinfo/routes/glue.py`
- `auto_bioinfo/routes/bulk_rnaseq.py`
- `auto_bioinfo/fixtures/bulk_rnaseq_route/counts.tsv`
- `auto_bioinfo/fixtures/bulk_rnaseq_route/samples.tsv`
- `auto_bioinfo/fixtures/bulk_rnaseq_route/dataset_card.json`
- `tests/test_wp16_bulk_route.py`

Supporting pure/offline modules may be added only as needed for the WP-16 route and its tests:

- `auto_bioinfo/adapters/capability_registry.py`
- `auto_bioinfo/adapters/public_bio_tools.py`
- `auto_bioinfo/adapters/__init__.py`
- `auto_bioinfo/quality/qc_gates.py`
- `auto_bioinfo/evidence/admission.py`
- `auto_bioinfo/evidence/claim_synthesis.py`
- `auto_bioinfo/evidence/question_alignment.py`
- `auto_bioinfo/reporting/__init__.py`
- `auto_bioinfo/reporting/claim_lint.py`
- `auto_bioinfo/reporting/report_builder.py`
- `auto_bioinfo/reporting/trace_index.py`
- `auto_bioinfo/reproduction/clean_rerun.py`
- `auto_bioinfo/reproduction/repro_bundle.py`
- optional focused support tests for the two new adapter modules, if those modules are introduced: `tests/test_capability_registry.py`, `tests/test_public_bio_tools.py`

Synthetic fixture requirements:

- The fixture must be honestly labelled as synthetic/offline/fixture-only.
- It must not be represented as real biological evidence.
- No network, no external service, no external LLM, no paid service, no live dataset retrieval/materialization.

## Explicit non-scope

Do not port later WP surfaces in this PR:

- no `auto_bioinfo/routes/scrna_donor.py`
- no `auto_bioinfo/routes/requirement_coverage.py`
- no `auto_bioinfo/fixtures/scrna_donor_route/**`
- no `tests/test_wp17_scrna_route.py`, `tests/test_wp18_qc_gates.py`, `tests/test_wp19_evidence_admission.py`, `tests/test_wp20_claim_synthesis.py`, `tests/test_wp21_report_builder.py`, `tests/test_wp22_reproduction.py`, or WP23-WP27 tests
- no `auto_bioinfo/ops/**`, `auto_bioinfo/security/**`, release/observability/run-panel work, or docs/audit/rebuild/tooling docs from the batch branch

Do not modify or delete already-merged lane surfaces unless you hit a true blocker and report it first:

- `auto_bioinfo/workflow/dag_compiler.py`
- `auto_bioinfo/workflow/artifact_registry.py`
- `auto_bioinfo/execution/authorization.py`
- `auto_bioinfo/execution/fake_executor.py`
- `tests/test_wp12_dag_compiler.py`
- `tests/test_wp13_authorization_scheduler.py`
- `tests/test_wp14_fake_executor.py`
- `tests/test_wp15_artifact_registry.py`

In particular, do not port the source branch deletions/weakening of WP12-WP15 tests.

Do not change dependencies, lockfiles, SBOM, CI workflows, Docker/container files, branch protection, rulesets, secrets, credentials, or bot permissions.

## Expected acceptance

At minimum, `tests/test_wp16_bulk_route.py` should prove:

- route terminal status is `COMPLETED`
- main stages run in deterministic order
- one association-level claim is produced and never exceeds the claim ceiling
- dataset manifest is locked with checksums
- QC and alignment approve
- claim traces to QC-passed evidence/artifact
- report state is publishable/released within the offline test harness
- reproduction record is deterministic/bitwise-identical
- task runs are recorded
- public-bio tool selection/capability gate remains deny-by-default and does not materialize data
- two runs are byte-identical/stable
- produced `created_at` fields are empty

Run before reporting:

- `python -X utf8 -m unittest tests.test_wp16_bulk_route -v`
- any focused support-module tests added in this slice
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
- `git diff --check`
- GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` must be green on the PR

Report back with PR number, base SHA, full 40-char head SHA, exact changed file list, local test results, CI status, and an explicit hard-stop statement. If WP-16 cannot be implemented without broadening into later WP scope or touching forbidden WP12-WP15 files, return `QUESTION`/`BLOCKER` instead of widening silently.