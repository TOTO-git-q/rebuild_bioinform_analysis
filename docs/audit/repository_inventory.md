# Repository Inventory — WP-00 / T-00-02

> Read-only inventory of the current `auto_bioinfo` repository: directories,
> language, dependencies, services, workflows and deployment files. Produced on
> branch `rebuild/wp-00-architecture-audit` from base commit
> `b3c1311c706e98f45eec9f962a55837a3b0a8095`. **No file was modified.** This
> describes the **current rebuild** (`auto_bioinfo/`), not the predecessor
> `targetcompass_lite` (which is audited separately in
> `docs/rebuild/EXISTING_SYSTEM_AUDIT.md`).

## 0. Status legend

`EXISTING` = present and exercised by tests · `PARTIAL` = present but limited /
offline-only / reserved · `MISSING` = required but absent · `RESERVED` = port
declared, production adapter intentionally not implemented this stage.

Mode classification: **GREENFIELD?** No. A working code repository exists; this is
an audit of an existing-but-young rebuild (one vertical slice through the loop).

## 1. Top-level layout

| Path | Purpose | Status |
|---|---|---|
| `auto_bioinfo/` | Python package — the system itself (hexagonal core + ports + adapters) | EXISTING |
| `tests/` | Offline deterministic test suite (8 files) | EXISTING |
| `ci/` | `ci.yml` GitHub Actions workflow held outside `.github/` (token lacks `workflow` scope) + `ci/README.md` | PARTIAL (not wired into `.github/workflows/`) |
| `docs/adr/` | 7 adopted ADRs (`0001`..`0007`) | EXISTING |
| `docs/rebuild/` | Predecessor audit, migration map, target architecture | EXISTING |
| `docs/coordination/` | CC↔Codex coordination bus (turns, BOARD, constitution) | EXISTING |
| `docs/baseline/`, `docs/audit/`, `docs/acceptance/` | **New** WP-00 audit/baseline artifacts (this work order) | NEW |
| `pyproject.toml` | Build + tooling config (setuptools, ruff, pytest) | EXISTING |
| `README.md`, `DELIVERY_REPORT.md` | Project overview + R0-01 delivery report | EXISTING |
| `自动生信系统核心闭环_详细需求规格_v0.1.md` | Requirement spec v0.1 (read-only source) | EXISTING |
| `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` | Implementation plan v1.0 (read-only source) | EXISTING |
| `完整科研智能平台_总体蓝图与扩展边界_v0.1（…不在本次搭建的计划内）.md` | Out-of-scope blueprint (read-only reference) | EXISTING (out of scope) |
| `codex-requirement-decomposition-confirmation-gate.zip` | Read-only source material (素材) | EXISTING (reference) |
| `素材/` | Source material directory | EXISTING (reference) |
| `.gitignore` | Ignores `__pycache__`, `_extract/`, `/runs/`, caches | EXISTING |

## 2. Language, runtime, dependencies

| Item | Value | Source |
|---|---|---|
| Language | Python | `pyproject.toml` |
| Python requirement | `>=3.10` (project), test env conda `bioinform` (py3.11) | `pyproject.toml`, observed |
| Build backend | setuptools `>=68` | `pyproject.toml` |
| Runtime dependency | **`numpy>=1.24` (only)** | `pyproject.toml` |
| Dev/optional deps | `pytest>=7`, `ruff>=0.4`, `mypy>=1.8` | `pyproject.toml [project.optional-dependencies].dev` |
| Console entry point | `bioauto = auto_bioinfo.interfaces.cli:main` | `pyproject.toml [project.scripts]` |
| Package data | `auto_bioinfo.fixtures/**/*.tsv`, `**/*.json` | `pyproject.toml` |
| Lint config | ruff: line-length 160, select E/F/I/B/UP, ignore E501/B008, target py310 | `pyproject.toml [tool.ruff]` |
| Test config | pytest `testpaths=["tests"]`; suite is stdlib `unittest`-compatible | `pyproject.toml`, README |

**Note (honest):** the runtime dependency surface is deliberately tiny (numpy
only). All heavier infrastructure (DB, object store, workflow engine, LLM) is
behind reserved ports, NOT a current dependency.

## 3. Package source tree (`auto_bioinfo/`)

| Module | LOC | Role | Status |
|---|---|---|---|
| `__init__.py` / `__main__.py` | 1 / 6 | package marker / `python -m auto_bioinfo` entry | EXISTING |
| `pipeline.py` | 380 | single production orchestrator (run==resume, guarded state machine) | EXISTING |
| `report.py` | 126 | constrained report builder (renders only synthesized claims) | EXISTING |
| `core/schemas.py` | 385 | dataclass domain schemas (~25 objects) + CLAIM_LEVELS | EXISTING |
| `core/state.py` | 121 | project state machine (15 main stages + safe terminals) | EXISTING |
| `core/store.py` | 120 | append-only event log + state projection (JSONL) | EXISTING |
| `core/events.py` | 56 | event records | EXISTING |
| `core/ids.py` | 20 | content-hash stable IDs | EXISTING |
| `core/validation.py` | 63 | mock/placeholder verified-dataset guard + field checks | EXISTING |
| `core/artifacts.py` | 195 | checksum-addressed artifact registry + evidence-admission gate | EXISTING |
| `core/task_packets.py` | 90 | Analysis/Engineering/Review task packets + validation | EXISTING |
| `core/workflow_compiler.py` | 59 | compiles task packets into a workflow plan | EXISTING |
| `core/handoff.py` | 79 | agent-to-agent handoff records | EXISTING |
| `core/agent_specs.py` | 140 | 7 typed agent specs (forbidden_actions, max_claim_level, handoff_contract) | EXISTING |
| `core/agent_protocol.py` | 123 | handoff validation (claim ceiling not loosened, dataset locking) | EXISTING |
| `core/alignment_auditor.py` | 285 | deterministic original-question alignment audit | EXISTING |
| `ports/__init__.py` | 117 | 5 hexagonal Protocol ports (Planner/ResourceDiscovery/AnalysisMethod/ObjectStore/EventStore) | EXISTING + RESERVED prod adapters |
| `adapters/offline_planner.py` | 128 | deterministic offline planner (PlannerPort default) | PARTIAL (offline only) |
| `adapters/fixture_resources.py` | 80 | committed offline fixture resource adapter (ResourceDiscoveryPort default) | PARTIAL (fixture only) |
| `methods/bulk_deg.py` | 211 | numpy-only bulk DEG method (AnalysisMethodPort default) | EXISTING |
| `methods/_stats.py` | 118 | Welch t-test + BH FDR + regularized incomplete beta (no scipy) | EXISTING |
| `methods/registry.py` | 63 | method registry + MethodContract compatibility decision | EXISTING |
| `quality/qc_engine.py` | 90 | four-layer QC (execution/data/statistical/biological) | EXISTING |
| `evidence/synthesis.py` | 150 | EvidenceItem build + Claim synthesis (ceiling-capped) | EXISTING |
| `execution/objects.py` | 45 | typed object read/write refs | EXISTING |
| `execution/runs.py` | 83 | append-only JSONL ledgers (task_runs/qc/evidence/claims) | EXISTING |
| `reproduction/bundle.py` | 172 | reproduction bundle build + bitwise/tolerance compare | EXISTING |
| `interfaces/cli.py` | 114 | thin CLI: run/resume/inspect/export/validate | EXISTING |
| `fixtures/bulk_deg_demo/` | data | committed synthetic fixture (counts.tsv, samples.tsv, dataset_card.json) | EXISTING (clearly labelled non-real) |

Total package source ≈ **3,628 LOC** across 28 substantive modules (`find ... | wc -l`).

## 4. Tests

| File | LOC | Covers |
|---|---|---|
| `tests/_helpers.py` | 53 | shared fixtures |
| `tests/test_state_machine.py` | 49 | stages, illegal transitions, event rebuild |
| `tests/test_schemas_and_validation.py` | 39 | schema + guard validation |
| `tests/test_methods_and_qc.py` | 75 | stat correctness + bulk_deg determinism + four-layer QC gate |
| `tests/test_evidence_and_cli.py` | 61 | evidence/claim ceiling + CLI |
| `tests/test_planner_resources_alignment.py` | 66 | offline planner, fixture resources, alignment audit |
| `tests/test_reproduction.py` | 38 | byte-for-byte bundle compare + tamper detection |
| `tests/test_failure_paths.py` | 48 | conservative terminals, mock-data rejection, missing question |
| `tests/test_pipeline_e2e.py` | 57 | one full end-to-end run + resume idempotency |

Real measured result (this branch, conda `bioinform`):
`python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 113 tests, OK**
(≈1.0s, fully offline). The README/DELIVERY_REPORT historical "43 tests" figure
predates the R0-01 truthful-mode remediation; the merged baseline now has 113.

## 5. Services, workflows, deployment

| Concern | State | Evidence |
|---|---|---|
| HTTP/API service | MISSING (CLI-only this stage) | only `interfaces/cli.py` |
| Worker/queue/broker | MISSING (in-process synchronous pipeline) | `pipeline.py` |
| Database | RESERVED — `EventStorePort`; current store is JSONL on disk | `ports/__init__.py`, `core/store.py`, ADR-0003 |
| Object store | RESERVED — `ObjectStorePort`; current is local filesystem | `ports/__init__.py`, ADR-0004 |
| Workflow engine (Nextflow) | RESERVED — `AnalysisMethodPort` prod adapter | `ports/__init__.py`, ADR-0006 |
| LLM gateway | RESERVED — `PlannerPort` prod adapter; current is offline deterministic | `ports/__init__.py`, ADR-0004 |
| CI | `ci/ci.yml` exists (install→ruff→mypy→offline unittest, py3.10/3.11/3.12 matrix) but is **NOT** in `.github/workflows/` (token lacks `workflow` scope) | `ci/README.md` |
| Containers / Compose | MISSING this stage (planned WP-01) | DELIVERY_REPORT §8 |
| Deployment files | MISSING this stage | — |

## 6. Honest boundary statement

The repository today is a **single offline, deterministic vertical slice**:
natural-language question → offline planner → committed fixture dataset → real
numpy bulk-DEG execution → four-layer QC → EvidenceItem → association-capped Claim
→ alignment audit → constrained report → reproduction bundle. Production
infrastructure (Postgres/MinIO/Nextflow/network-LLM/queue/Compose/API/observability/
multi-user) is reserved behind ports and **not** implemented. No claim of
production readiness is made.
