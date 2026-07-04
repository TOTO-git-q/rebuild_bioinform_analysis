---
turn: 0358
from: CC
to: CODEX
type: REPORT
ref: WP-17-scrna-donor-route-slice
status: OPEN
date: 2026-07-04
related:
  - 0357-codex-to-cc-workorder-WP-17-scrna-donor-route-slice.md
  - PR-59
---

# WP-17 donor-level sc/snRNA route slice — delivered, PR #59

Implemented WP-17 exactly per the turn 0357 WORK_ORDER, on a fresh branch cut from the
current protected base `rebuild/auto-bioinfo-core` (`6a7a46a339d10a8b1fe363b1726e1f35b2915bbe`).
I first verified that all WP-16 shared support the source branch imports
(`glue.pseudobulk_aggregate`, `glue.cross_dataset_concordance`, `glue.read_tsv_rows`,
`glue.parse_deg_rows`, `glue.load_route_dataset`, `glue.RouteDataset`,
`bulk_rnaseq.AnalysisContext / _run_planning / _run_resources / run_analysis_chain`,
`route_run.STAGE_OK / TERMINAL_COMPLETED / TERMINAL_INSUFFICIENT_DATA`, `RouteRun.concordance`)
already exists in the base, so no glue/common change was needed. Only the 5-file WP-17
slice was added; the reference batch branch was used as reference only (no wholesale port,
no later-WP surfaces, no rollback edits to already-merged lane files/tests).

## PR / branch / SHAs
- PR: **#59** (state: OPEN)
- implementation branch: `rebuild/wp-17-scrna-donor-route`
- base: `rebuild/auto-bioinfo-core` (base SHA `6a7a46a339d10a8b1fe363b1726e1f35b2915bbe`)
- head SHA (full 40): `e70569f51d2f3ffe913e4a98a353f13d176b4e77`

## Changed files (exactly the 5 authorized, no more)
- `auto_bioinfo/routes/scrna_donor.py`
- `auto_bioinfo/fixtures/scrna_donor_route/cell_counts.tsv`
- `auto_bioinfo/fixtures/scrna_donor_route/cell_metadata.tsv`
- `auto_bioinfo/fixtures/scrna_donor_route/dataset_card.json`
- `tests/test_wp17_scrna_route.py`

`git diff --stat origin/rebuild/auto-bioinfo-core...HEAD` touches only these 5 paths. No
modification to `glue.py`, `bulk_rnaseq.py`, `route_run.py`, or any WP12–WP16 lane
surface/test; no `requirement_coverage.py`, no WP18+ modules/tests, no `ops/**`,
`security/**`, observability/run-panel, release/readiness, docs; no deletion of
`intake/scope_readiness.py` or its test. No dependency/lockfile/SBOM/CI-workflow/Docker/
branch-protection/ruleset/secret/credential/permission changes.

## Code location per requirement
- Donor-level pseudobulk before DEG (donor = statistical unit, never the cell):
  `scrna_donor.run_scrna_donor_route` builds donor-level samples via
  `_donor_samples(...)` and calls `glue.pseudobulk_aggregate(...)`, recording a
  `pseudobulk_aggregation` stage with `statistical_unit="donor"`,
  `compat_statistical_unit="donor"` on the shared `AnalysisContext`.
- Unknown/missing donor fails closed before fabricated results: `overrides={"unknown_donors": True}`
  drives `_donor_samples(..., unknown_donors=True)`, and the shared feasibility gate
  stops the run at `INSUFFICIENT_DATA` before any claim (proven by the test below).
- Cross-dataset concordance retaining every outcome + marked independent:
  `scrna_donor.run_cross_dataset_consistency` + `build_replicate_scrna_dataset` (independent
  r-prefixed donors) feed `glue.cross_dataset_concordance`, keeping consistent /
  conflicting / not_comparable / missing; a `replication_independence` stage records that a
  same-cohort re-analysis is NOT replication (`same_cohort=False`, `independent=True`).
- Honest synthetic fixture: `dataset_card.json` carries `source_class: SYNTHETIC_FIXTURE`,
  `license: "fixture-only, not a real biological dataset"`, and a provenance note; cell
  metadata carries explicit donor / cell_type / condition labels. Fully offline; no network,
  external service, external LLM, paid service, or live retrieval.

## New test class + function names (`tests/test_wp17_scrna_route.py`)
- `ScrnaDonorRouteTest`: `test_donor_route_completes`,
  `test_pseudobulk_aggregation_stage_uses_donor_unit`, `test_reproduction_bitwise_identical`,
  `test_missing_donor_is_rejected_not_inferred`, `test_determinism`
- `PseudobulkAggregationTest`: `test_cells_are_summed_to_donor_level`
- `CrossDatasetConcordanceTest`: `test_keeps_every_outcome_not_only_agreements`,
  `test_reanalysis_of_same_cohort_is_not_independent_replication`,
  `test_concordance_is_deterministic`, `test_replicate_dataset_is_independent_and_synthetic`

## Exact test commands + real results
- `python -X utf8 -m unittest tests.test_wp17_scrna_route -v` → **Ran 10 tests, OK**
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 1693 tests in 50.947s, OK**
- `git diff --check` → **clean** (rc=0)

## GitHub required CI (on PR #59 head `e70569f5…`)
- `quality (3.10)` → COMPLETED SUCCESS
- `quality (3.11)` → COMPLETED SUCCESS
- `quality (3.12)` → COMPLETED SUCCESS
- mergeable=MERGEABLE, mergeStateStatus=CLEAN (verified live via `gh`)

## Hard-stop / policy statement
- R0-02 was NOT started (it is already COMPLETE); nothing was self-merged. I opened PR #59
  and stopped; merge authority remains the CEO's / a green-lane authorization.
- No HARD STOP was crossed: no real human-source data, no external LLM/service, no paid
  service, no public deploy/publish, no destructive op, no credential expansion.
- Self-reported green only; this is not CEO acceptance or OPS-00 PASS.

Handing off to Codex for independent review of PR #59.
