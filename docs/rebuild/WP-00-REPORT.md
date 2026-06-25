# WP-00 REPORT — 需求冻结、现状审计与差距矩阵

> Work order: coordination turn `0040` (CODEX → CC, WORK_ORDER, ref WP-00).
> Mode: **audit and documentation only — no business code changed.**
> Branch: `rebuild/wp-00-architecture-audit` (from base `rebuild/auto-bioinfo-core`).
> Base SHA: `b3c1311c706e98f45eec9f962a55837a3b0a8095`.

## 1. Scope and method

Read-only audit of the **current** `auto_bioinfo` rebuild (the R0-01 merged
baseline), against the two requirement documents and the implementation plan.
Every statement is grounded in a real file read (paths/line numbers cited in the
artifacts); nothing is asserted from memory. No business code, test logic, runtime
semantics, ruleset, secret, workflow permission, or robot credential was touched.
The audit added only documentation under `docs/`.

Note on the existing `docs/rebuild/EXISTING_SYSTEM_AUDIT.md`: it audits the
**predecessor** `targetcompass_lite`, not the current rebuild. WP-00's audit
target is the current `auto_bioinfo/` package; the two are kept distinct.

## 2. Leaf tasks T-00-01 … T-00-10 → produced artifacts

| Task | Artifact | Path |
|---|---|---|
| T-00-01 | source manifest + spec_id + recomputable hashes | `docs/baseline/source_manifest.yaml` |
| T-00-02 | repository inventory (dirs/lang/deps/services/workflows/deploy) | `docs/audit/repository_inventory.md` |
| T-00-03 | component inventory (EXISTING/PARTIAL/MISSING/RESERVED) | `docs/audit/component_inventory.csv` |
| T-00-04 | method & asset inventory (only run methods = available) | `docs/audit/method_asset_inventory.md` |
| T-00-05 | preserve / extend / replace / retire / do-not-touch | `docs/audit/preserve_replace_retire.yaml` |
| T-00-06 | requirements catalog (77 Requirement IDs) | `docs/baseline/requirements_catalog.csv` |
| T-00-07 | gap matrix (requirement → capability → gap → WP) | `docs/audit/gap_matrix.csv` |
| T-00-08 | project-side architecture baseline, D-01..D-06 CONFIRMED | `docs/baseline/architecture_baseline.yaml` |
| T-00-09 | ADR-001 … ADR-010 drafts (cross-checked, no conflict) | `docs/adr/ADR-001.md` … `docs/adr/ADR-010.md` |
| T-00-10 | requirement–task–evidence traceability matrix | `docs/acceptance/traceability_matrix.csv` |
| (report) | this report | `docs/rebuild/WP-00-REPORT.md` |

### Path deviations from the work order's suggested paths (stated reasons)

The work order allowed path adjustments if explained:
- `architecture_baseline.yaml` → placed at **`docs/baseline/architecture_baseline.yaml`**
  (not repo root) to keep audit/baseline artifacts together and to avoid a name
  clash with the governance copy at `docs/coordination/architecture_baseline.yaml`.
  It mirrors and references that coordination copy (which stays the record of record).
- ADRs use the filename pattern **`ADR-001.md`..`ADR-010.md`** exactly as the work
  order specified; these coexist with the already-adopted `docs/adr/0001..0007.md`
  without overwriting them (numbering coexistence resolved in ADR-010 / OPEN-01).
- `component_inventory.csv`, `method_asset_inventory.md`, `preserve_replace_retire.yaml`,
  `gap_matrix.csv` placed under `docs/audit/`; `requirements_catalog.csv` under
  `docs/baseline/`; `traceability_matrix.csv` under `docs/acceptance/` — following the
  plan file's suggested directory roots.

## 3. Reuse / Replace / Retire / Do-not-touch summary

(Full detail in `docs/audit/preserve_replace_retire.yaml`.)

- **Preserve (reuse as-is):** `auto_bioinfo/core/*` (event-sourced domain core),
  the 5 hexagonal ports, `pipeline.py`, `quality/qc_engine.py`,
  `methods/bulk_deg.py` + `_stats.py`, `reproduction/bundle.py`, the 113-test suite,
  and the 7 adopted ADRs. The clean core is reused, **not** rewritten (honors D-01).
- **Extend:** SubQuestion/EvidencePlan/DatasetProfile/TaskRun schemas (missing
  required fields), WorkflowPlan → true DAG, state-machine stage set, report formats,
  and new objects (OriginalRequest/ProjectPolicy, AmbiguityReport, OntologyMapping,
  QuestionDependencyGraph, DatasetFeasibilityReport).
- **Replace (offline default → production adapter behind same port):** offline
  planner → network LLM; fixture resources → real GEO/Europe PMC; JSONL store →
  PostgreSQL; local FS → S3/MinIO; in-process method → Nextflow/containerized worker.
- **Retire (predecessor anti-patterns — keep out; nothing deleted in WP-00):**
  webapp God class, duplicate state machines, "file-exists == done", path-derived
  artifact identity, synthetic/forged data points.
- **Do-not-touch (frozen rails):** claim ceiling, un-bypassable gate chain,
  event-sourcing append-only + locked-manifest immutability, mock/placeholder
  rejection, conservative-failure terminals, and the coordination/ruleset/secret/
  workflow surfaces.

## 4. Gap findings (highlights)

- 77 requirements catalogued from the requirement spec; **every MUST maps to at
  least one work package** in `gap_matrix.csv` (verified: no unmapped MUST).
- Largest gaps to MUSTs: real data discovery+verification (WP-08/09, reserved),
  DatasetFeasibilityReport object (WP-10, MISSING), true acyclic DAG (WP-12, PARTIAL),
  isolated worker/TaskRun (WP-14, PARTIAL), security/policy layer (WP-23, MISSING),
  intake objects OriginalRequest/ProjectPolicy (WP-06, MISSING).
- Strong/EXISTING areas: event-sourced state, checksummed artifacts, four-layer QC,
  evidence-admission gate, claim ceiling, alignment audit, reproduction bundle.

## 5. D-01..D-06 confirmation

All six decisions pinned `CONFIRMED` on the project side
(`docs/baseline/architecture_baseline.yaml`), mirroring CEO confirmation in
coordination turn 0039. Mode recorded as `REBUILD_ON_CLEANED_CORE`,
`business_code_changes_in_wp00: false`.

## 6. WP-01 entry condition

WP-01 entry condition is *"WP-00 accepted; directory structure and compatibility
strategy confirmed."* This report **prepares** that condition (the audit, baseline,
preserve/replace/retire strategy and gap matrix are produced) but does **not**
satisfy it autonomously: acceptance is the CEO/Codex review's call. **WP-01 was NOT
started** and must not start until an authorizing turn is issued.

Open items that should be acknowledged before WP-01 (none block WP-00):
OPEN-01 ADR numbering coexistence, OPEN-02 state-machine stage reconciliation,
OPEN-03 WorkflowPlan→DAG, OPEN-04 baseline file path choice
(`docs/baseline/architecture_baseline.yaml`).

## 7. Tests and checks (real results)

Command (full offline suite, conda env `bioinform`):

```
python3 -m unittest discover -t . -s tests -p "test_*.py"
```

Result: **`Ran 113 tests` … `OK`**, exit code 0, fully offline. (The "43 tests"
figure in README/DELIVERY_REPORT predates the R0-01 truthful-mode remediation; the
merged baseline now has 113.) WP-00 changed no code, so this is the unchanged base
behavior — the suite was run to confirm a green baseline, not because audit docs
affect it.

`git diff --check`: **clean (no whitespace/conflict errors).**

## 8. Constitution / safety confirmations

- **R0-02 was NOT started.** Only WP-00 (audit/docs/ADR) was performed.
- **WP-01 was NOT started.**
- **Nothing was self-merged.** No PR was merged; CC holds no merge authority.
- No business code, test logic, runtime semantics, ruleset, secret, workflow
  permission, or robot credential was modified.
- No `.github/workflows/` added; no push/force-push to `main` or
  `rebuild/auto-bioinfo-core`.
- No hard stop touched (no real human data, no external LLM/service call, no paid
  service, no public deploy/publish, no destructive deletion, no credential change).
- No token/key/secret written into any artifact, log, or the repo.

## 9. Branch / commit / PR state

- Branch: `rebuild/wp-00-architecture-audit` (pushed to origin).
- Base SHA: `b3c1311c706e98f45eec9f962a55837a3b0a8095`.
- Head SHA: see the accompanying REPORT turn on the `coordination` branch (recorded
  there as the authoritative 40-char SHA after push).
- PR: none opened by CC in WP-00 (audit/docs only). Opening/merging a PR is the
  CEO/Codex decision per constitution G1; CC awaits the next independent review.
