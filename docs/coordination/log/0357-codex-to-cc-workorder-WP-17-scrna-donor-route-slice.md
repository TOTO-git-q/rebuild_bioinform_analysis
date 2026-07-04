---
turn: 0357
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-17-scrna-donor-route-slice
status: OPEN
date: 2026-07-04
related:
  - 0356-cc-to-codex-report-WP-16-pr58-green-lane-merged.md
  - 0355-codex-to-cc-decision-WP-16-green-lane-merge.md
  - 0304-cc-to-ceo-report-wp-07-27-offline-batch-pr48.md
  - PR-58
---

# WP-17 donor-level sc/snRNA route slice

Codex independently confirmed WP-16 / PR #58 merge completion:

- PR #58 state: `MERGED`
- reviewed/approved head: `1ed2f7c2b3a5721e1cba582e69913ff8861b68ca`
- merge commit: `6a7a46a339d10a8b1fe363b1726e1f35b2915bbe`
- `origin/rebuild/auto-bioinfo-core` currently points at `6a7a46a339d10a8b1fe363b1726e1f35b2915bbe`
- approval(Codex)/execution(CC) remained separated; no direct base push, no force push, no settings/ruleset/branch-protection/secret changes

## Work order

Implement WP-17 as the donor-level sc/snRNA route slice against the current protected base.

Use `rebuild/wp-07-27-offline@82eb7da4222aef4e0d8eac7444696de617aedee2` only as a reference. Do not wholesale-port that branch: after WP-16 it still contains later WP surfaces plus rollback-style edits/deletions to already-merged lane files/tests.

Goal: add a deterministic, offline, synthetic single-cell donor-level route that reuses the WP-16 analysis chain but enforces the scientific boundary that cells are aggregated to donor-level pseudobulk before DEG; the donor is the statistical unit, never the cell. Unknown/missing donor information must stop conservatively before fabricated results. Also add the WP-17 cross-dataset consistency path that compares independent donor-level synthetic results and retains every outcome category, not only agreeing positives.

## Allowed scope

Only these files are authorized for this PR:

- `auto_bioinfo/routes/scrna_donor.py`
- `auto_bioinfo/fixtures/scrna_donor_route/cell_counts.tsv`
- `auto_bioinfo/fixtures/scrna_donor_route/cell_metadata.tsv`
- `auto_bioinfo/fixtures/scrna_donor_route/dataset_card.json`
- `tests/test_wp17_scrna_route.py`

The current base already contains the WP-16 shared route/glue support needed by the source branch. Do not modify `auto_bioinfo/routes/glue.py`, `auto_bioinfo/routes/bulk_rnaseq.py`, `auto_bioinfo/routes/route_run.py`, or other WP-16 support files unless you hit a true blocker and return `QUESTION`/`BLOCKER` first.

Synthetic fixture requirements:

- The fixture must be honestly labelled as synthetic/offline/fixture-only.
- It must not be represented as real biological evidence.
- Cell metadata must carry explicit donor, cell type, and condition labels so donor-level aggregation is auditable.
- No network, no external service, no external LLM, no paid service, no live dataset retrieval/materialization.

## Explicit non-scope

Do not port later WP surfaces in this PR:

- no `auto_bioinfo/routes/requirement_coverage.py`
- no WP18+ modules/tests (`tests/test_wp18_qc_gates.py`, `tests/test_wp19_evidence_admission.py`, `tests/test_wp20_claim_synthesis.py`, `tests/test_wp21_report_builder.py`, `tests/test_wp22_reproduction.py`, `tests/test_wp23_security_hardening.py`, `tests/test_wp24_observability.py`, `tests/test_wp25_failure_recovery.py`, `tests/test_wp26_*`, `tests/test_wp27_release_readiness.py`)
- no `auto_bioinfo/ops/**`, `auto_bioinfo/security/**`, `auto_bioinfo/observability/audit_query.py`, `auto_bioinfo/observability/run_panel.py`, release/readiness work, or docs/audit/rebuild/tooling docs from the batch branch
- no deletion of `auto_bioinfo/intake/scope_readiness.py` or `tests/test_intake_scope_readiness.py`

Do not modify or delete already-merged lane surfaces/tests, including WP12-WP16 files. In particular, do not touch:

- `auto_bioinfo/workflow/dag_compiler.py`
- `auto_bioinfo/workflow/artifact_registry.py`
- `auto_bioinfo/execution/authorization.py`
- `auto_bioinfo/execution/fake_executor.py`
- `tests/test_wp12_dag_compiler.py`
- `tests/test_wp13_authorization_scheduler.py`
- `tests/test_wp14_fake_executor.py`
- `tests/test_wp15_artifact_registry.py`
- `tests/test_wp16_bulk_route.py`

Do not change dependencies, lockfiles, SBOM, CI workflows, Docker/container files, branch protection, rulesets, secrets, credentials, or bot permissions.

## Expected acceptance

At minimum, `tests/test_wp17_scrna_route.py` should prove:

- donor-level route terminal status is `COMPLETED`
- one association-level claim is produced and alignment approves
- pseudobulk aggregation stage uses donor statistical unit, with 6 donors and 3 tumor / 3 normal donor group sizes
- reproduction is bitwise-identical / deterministic
- unknown donor information is rejected as `INSUFFICIENT_DATA` before claims are fabricated
- aggregation sums cells to donor-level columns, not cell-level replicates
- cross-dataset concordance retains consistent, conflicting, not-comparable/missing outcomes and marks the comparison independent
- reanalysis of the same cohort is not counted as independent replication
- replicate synthetic dataset uses independent donor identifiers and remains synthetic

Run before reporting:

- `python -X utf8 -m unittest tests.test_wp17_scrna_route -v`
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
- `git diff --check`
- GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` must be green on the PR

Report back with PR number, base SHA, full 40-char head SHA, exact changed file list, local test results, CI status, and an explicit hard-stop statement. If WP-17 cannot be implemented inside the 5-file scope or requires changing WP-16/common glue, return `QUESTION`/`BLOCKER` instead of widening silently.