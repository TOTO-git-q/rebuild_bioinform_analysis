# Method & Asset Inventory — WP-00 / T-00-04

> Inventory of existing bioinformatics methods, scripts, workflow engines,
> environments and test data in the current `auto_bioinfo` repository. Read-only,
> from base commit `b3c1311c706e98f45eec9f962a55837a3b0a8095`.
>
> **Discipline (T-00-04 gate):** a script is only listed as an *available method*
> if it actually executes and is exercised by the test suite. Reserved ports,
> planned adapters, and predecessor (`targetcompass_lite`) modules are listed
> separately as **NOT-yet-available** so nothing un-run is mislabelled as usable.

## 1. Available registered analysis methods (really execute)

| Method | id/version | Location | Inputs | Output | Stats | Claim cap | Verified by |
|---|---|---|---|---|---|---|---|
| Bulk DEG | `bulk_deg` / `0.1.0` | `auto_bioinfo/methods/bulk_deg.py` | `counts` (bulk_expression_matrix TSV) + `samples` (sample→group TSV) | `deg_results.tsv` (logFC, t, df, p, FDR, direction, significant) | CPM→log2(CPM+1), Welch two-sample t-test, Benjamini-Hochberg FDR | **`association`** (hard cap in MethodContract) | `tests/test_methods_and_qc.py`, end-to-end run |

Method facts (read from source, not inferred):
- **Deterministic, numpy-only.** No randomness; `random_seed=0` param present.
  t-distribution tail via the regularized incomplete beta function
  (`auto_bioinfo/methods/_stats.py`), so no scipy dependency (ADR-0006).
- **MethodContract** (`bulk_deg.py:35-63`) declares `accepted_input_types`,
  `required_metadata`, `minimum_sample_design={groups:2, min_replicates_per_group:2}`,
  `statistical_unit="sample"`, `required_qc=[execution,data,statistical,biological]`,
  `forbidden_conditions`, and `claim_capability="association"`.
- **Hard precondition mirrors the contract** (`bulk_deg.py:75-88`): fewer than 2
  groups or <2 replicates/group → `status="precondition_failed"` → pipeline routes
  to `INSUFFICIENT_DATA` (conservative stop, not a fabricated result).
- **Registry** (`auto_bioinfo/methods/registry.py`) holds exactly one method today;
  `compatibility_decision()` enforces modality + minimum design before execution.

## 2. Supporting deterministic statistical utilities

| Asset | Location | Role | Verified |
|---|---|---|---|
| `welch_t_test`, `benjamini_hochberg`, regularized incomplete beta | `auto_bioinfo/methods/_stats.py` (118 LOC) | numpy-only stats backing bulk_deg; aligned to known t-critical values | `tests/test_methods_and_qc.py` |

## 3. Four-layer QC (deterministic, runs every slice)

`auto_bioinfo/quality/qc_engine.py` — Execution / Data / Statistical / Biological
checks, each a structured finding (`layer`, `status`, `detail`, `artifact_id`),
overall ∈ {pass, pass_with_warnings, fail} → decision PASS/PASS_WITH_WARNINGS/REJECT.
Statistical layer flags pseudo-replication (min replicates) and confirms
sample-level unit; biological layer caps RNA modality at `association`. Exercised
by `tests/test_methods_and_qc.py` (incl. a statistical-layer FAIL case).

## 4. Test data / fixtures (committed)

| Asset | Location | Nature | Honesty marking |
|---|---|---|---|
| Bulk DEG demo fixture | `auto_bioinfo/fixtures/bulk_deg_demo/` (`counts.tsv`, `samples.tsv`, `dataset_card.json`) | **Synthetic** bulk count matrix, 2 groups × 3 replicates | `source_class=SYNTHETIC_FIXTURE`, `license="fixture-only, not a real biological dataset"`; card explicitly forbids presenting it as a real verified dataset |

This is the only committed dataset. It is for pipeline validation, **not biological
discovery** (`known_limitations` in the card say so). The `validate_no_unknown_verified_dataset`
guard (`core/validation.py`) blocks any `AUTO_`/`MOCK_` accession from being marked verified.

## 5. Workflow engines / environments

| Concern | State | Evidence |
|---|---|---|
| Nextflow | **NOT available** — reserved as `AnalysisMethodPort` production adapter | `ports/__init__.py`, ADR-0006, DELIVERY_REPORT §8 |
| Snakemake | not present | repo scan |
| Container / conda environment files | not committed this stage (test env is external conda `bioinform`) | repo scan |
| Random seed / determinism policy | bulk_deg deterministic; seed param present | `bulk_deg.py:49` |

## 6. NOT-yet-available methods (must not be counted as capabilities)

Required by the requirement spec (stage 11 / §12 v1 scope) but **not implemented**
in the current rebuild — present only as predecessor modules to be reused via
adapters, or as future work packages (see `docs/audit/gap_matrix.csv`):

| Method | Status | Where it would land |
|---|---|---|
| scRNA/snRNA pseudobulk donor-level DEG | MISSING | future `AnalysisMethodPort` adapter (route WP-13 area) |
| differential abundance | MISSING | future method adapter |
| gene-set / SASP score | MISSING | future method adapter |
| enrichment (hypergeometric / GSEA) | MISSING | future method adapter |
| meta-analysis / cross-dataset consistency | MISSING | future method adapter |
| surface / secretome annotation | MISSING | future annotation adapter |
| homolog/ortholog mapping | MISSING | future adapter |
| limma/edgeR/scanpy real toolchains | MISSING (predecessor `deg.py`/`scrna.py` exist but depend on R/h5py, not offline-deterministic; reuse-via-adapter only) | `docs/rebuild/MIGRATION_MAP.md §3.1` |

## 7. Real data discovery / verification

**NOT available.** Real GEO / Europe PMC / annotation-source discovery and
verification is reserved behind `ResourceDiscoveryPort`; the only adapter today is
`FixtureResourceAdapter` serving the committed synthetic fixture. Any production
run must go through a real, audited discovery adapter (per dataset_card provenance
note and ADR-0001/0004). First use of real human-derived data is a hard stop
requiring CEO authorization (constitution §4; baseline hard_stops).

## 8. Summary

Exactly **one** registered analysis method (`bulk_deg`) genuinely runs today, with
its deterministic statistics, four-layer QC, and an `association` claim cap. One
committed synthetic fixture backs it. Every other method, real-data discovery,
and the Nextflow/container execution layer is **not yet available** and is honestly
marked as reserved/planned — never as a present capability.
