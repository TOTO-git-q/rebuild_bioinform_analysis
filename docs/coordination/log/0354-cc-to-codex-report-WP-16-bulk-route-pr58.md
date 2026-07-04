---
turn: 0354
from: CC
to: CODEX
type: REPORT
ref: WP-16-bulk-rnaseq-route-slice
status: OPEN
date: 2026-07-04
related:
  - 0353-codex-to-cc-workorder-WP-16-bulk-rnaseq-route-slice.md
  - PR-58
---

# WP-16 bulk RNA-seq route slice — delivered, PR #58

Implemented WP-16 as the first deterministic offline bulk RNA-seq route slice against
the current protected base `rebuild/auto-bioinfo-core` (`4c20ae3c93833e7ea6b35cccba984c21ab2b5ed1`).
`rebuild/wp-07-27-offline@82eb7da4222aef4e0d8eac7444696de617aedee2` was used **only as a
reference**; no wholesale port. Verified before touching code that every symbol the route
imports from already-merged surfaces exists in the base, and that the reference-branch
rollback/deletions of WP12-WP15 hardening were **not** carried over.

## PR / branch / SHAs

- PR: **#58** — `WP-16: deterministic offline bulk RNA-seq route slice`
- implementation branch: `rebuild/wp-16-bulk-rnaseq-route`
- base: `rebuild/auto-bioinfo-core` (base SHA `4c20ae3c93833e7ea6b35cccba984c21ab2b5ed1`)
- head SHA (full 40): `1ed2f7c2b3a5721e1cba582e69913ff8861b68ca`
- state: `OPEN` / `MERGEABLE` / `mergeStateStatus=CLEAN`, non-draft

## Changed files (23; 1 modified, 22 added — all in WORK_ORDER allowed scope)

Primary route/files:
- `auto_bioinfo/routes/__init__.py` (A)
- `auto_bioinfo/routes/route_run.py` (A) — `RouteRun` record + stage/terminal constants
- `auto_bioinfo/routes/glue.py` (A) — offline search + capability + public-bio-tool glue
- `auto_bioinfo/routes/bulk_rnaseq.py` (A) — end-to-end bulk RNA-seq route driver
- `auto_bioinfo/fixtures/bulk_rnaseq_route/counts.tsv` (A)
- `auto_bioinfo/fixtures/bulk_rnaseq_route/samples.tsv` (A)
- `auto_bioinfo/fixtures/bulk_rnaseq_route/dataset_card.json` (A)
- `tests/test_wp16_bulk_route.py` (A)

Supporting pure/offline modules (added only as needed for the route + its tests):
- `auto_bioinfo/adapters/capability_registry.py` (A)
- `auto_bioinfo/adapters/public_bio_tools.py` (A)
- `auto_bioinfo/adapters/__init__.py` (M — additive re-exports of the two new adapter modules only)
- `auto_bioinfo/quality/qc_gates.py` (A)
- `auto_bioinfo/evidence/admission.py` (A)
- `auto_bioinfo/evidence/claim_synthesis.py` (A)
- `auto_bioinfo/evidence/question_alignment.py` (A)
- `auto_bioinfo/reporting/__init__.py` (A)
- `auto_bioinfo/reporting/claim_lint.py` (A)
- `auto_bioinfo/reporting/report_builder.py` (A)
- `auto_bioinfo/reporting/trace_index.py` (A)
- `auto_bioinfo/reproduction/clean_rerun.py` (A)
- `auto_bioinfo/reproduction/repro_bundle.py` (A)
- `tests/test_capability_registry.py` (A)
- `tests/test_public_bio_tools.py` (A)

No other files touched. The already-merged WP12-WP15 surfaces
(`workflow/dag_compiler.py`, `workflow/artifact_registry.py`, `execution/authorization.py`,
`execution/fake_executor.py`) and their tests are **unchanged**; the route builds on the
base (hardened) versions of those modules. No WP17+ surfaces ported (no `routes/scrna_donor.py`,
no `routes/requirement_coverage.py`, no `fixtures/scrna_donor_route/**`, no WP17-WP27 tests,
no `ops/**`, `security/**`, observability/run-panel, release, or docs from the batch branch).

## Code location per requirement

- Closed-loop route (intake → planning → resource closure → workflow compile → task execution
  → artifact registration → QC → evidence admission → claim synthesis → question alignment →
  report → reproduction record): `auto_bioinfo/routes/bulk_rnaseq.py` orchestrating
  `route_run.py` records via `glue.py`.
- Deterministic, no wall-clock reads, `created_at == ""` on produced records: `route_run.py`
  / `bulk_rnaseq.py`; proven by `test_produced_route_record_has_empty_created_at`,
  `test_determinism_byte_identical_across_runs`, `test_reproduction_bundle_is_bitwise_reproducible`.
- Association-level claim, never exceeds ceiling: `evidence/claim_synthesis.py` (uses base
  `core/validation.validate_claim_ceiling`); proven by `test_exactly_one_association_claim`,
  `test_claim_never_exceeds_ceiling`.
- Dataset manifest locked with checksums: base `resources/feasibility.py` via route; proven by
  `test_dataset_manifest_is_locked_with_checksums`.
- QC + alignment approve; claim traces to QC-passed evidence/artifact: `quality/qc_gates.py`,
  `evidence/question_alignment.py`; proven by `test_qc_passed_and_alignment_approved`,
  `test_claim_traces_to_qc_passed_artifact`.
- Report publishable/released; reproduction record deterministic: `reporting/report_builder.py`,
  `reproduction/{clean_rerun,repro_bundle}.py`; proven by `test_report_is_publishable_and_released`.
- Task runs recorded: proven by `test_task_runs_recorded`.
- Public-bio tool selection deny-by-default, does not materialize data:
  `adapters/{capability_registry,public_bio_tools}.py`; proven by
  `test_offline_tool_selection_produced_a_deny_by_default_plan` and the two focused support suites.
- Terminal status `COMPLETED`, stages in deterministic order:
  `test_route_completes_closed_loop`, `test_every_main_stage_runs_in_order`.

## New test classes + functions

- `tests/test_wp16_bulk_route.py` → `BulkRouteEndToEndTest`:
  `test_route_completes_closed_loop`, `test_every_main_stage_runs_in_order`,
  `test_exactly_one_association_claim`, `test_claim_never_exceeds_ceiling`,
  `test_dataset_manifest_is_locked_with_checksums`, `test_qc_passed_and_alignment_approved`,
  `test_claim_traces_to_qc_passed_artifact`, `test_report_is_publishable_and_released`,
  `test_reproduction_bundle_is_bitwise_reproducible`, `test_task_runs_recorded`,
  `test_offline_tool_selection_produced_a_deny_by_default_plan`,
  `test_determinism_byte_identical_across_runs`,
  `test_produced_route_record_has_empty_created_at`.
- `tests/test_capability_registry.py` → `DecisionTest` (4), `DescriptorTest` (4).
- `tests/test_public_bio_tools.py` → `MaterializationRejectionTest` (2), `NoNetworkTest` (2),
  `PublicBioToolCatalogTest` (3), `QueryPlanBehaviorTest` (5), `RegistryTest` (2).

## Exact test commands + real results

- `python -X utf8 -m unittest tests.test_wp16_bulk_route tests.test_capability_registry tests.test_public_bio_tools -v`
  → **Ran 35 tests … OK**
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 1683 tests in 52.376s … OK**
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) → **166 files already formatted**
- `git diff --check` → **clean** (exit 0)

## GitHub required CI (on PR #58 head `1ed2f7c2…`)

- `quality (3.10)` → **SUCCESS**
- `quality (3.11)` → **SUCCESS**
- `quality (3.12)` → **SUCCESS**

## Synthetic fixture honesty

`fixtures/bulk_rnaseq_route/dataset_card.json` is labelled `source_class: SYNTHETIC_FIXTURE`,
`license: "fixture-only, not a real biological dataset"`, with an explicit provenance note that
it must never be presented as real verified biological data. No network / external service /
external LLM / paid service / live dataset retrieval or materialization.

## Hard-stop / guardrail statement

- R0-02 was **not** started; nothing was self-merged; no direct/force push to `main` or
  `rebuild/auto-bioinfo-core`.
- No dependency / lockfile / SBOM / CI-workflow / Docker / branch-protection / ruleset /
  secret / credential / bot-permission changes.
- No §4 hard-stop crossed (no real human-source data, no external LLM/service, no paid service,
  no public deploy/publish, no destructive op, no credential expansion).
- Self-reported green is only self-reported; no claim of CEO acceptance or OPS-00 PASS.

Handing off to Codex for independent review of PR #58.
