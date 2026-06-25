# Directory Skeleton — WP-01a / T-01-01

> Authoritative map of the modular repository skeleton and the **preserved
> compatible entry points**. WP-01a confirms and documents the existing
> hexagonal layout (per ADR-001 / D-01 "preserve and extend, not greenfield");
> it does **not** rewrite business logic and deletes **no** preserved module.
> Directories required only by later WP-01 slices (config, deploy/compose,
> migrations, logging, container image) are intentionally **NOT** created here —
> they belong to their own out-of-scope tasks (T-01-03..T-01-12).

## 1. Top-level layout

| Path | Role | Status (WP-01a) |
|---|---|---|
| `auto_bioinfo/` | The system itself — hexagonal core + ports + adapters (Python package) | PRESERVED |
| `tests/` | Offline deterministic test suite | PRESERVED |
| `ci/` | Held GitHub Actions workflow (`ci.yml`) kept outside `.github/workflows/` | PRESERVED (untouched; CI is a later WO) |
| `docs/adr/` | Adopted (`0001..0007`) + WP-00 draft (`ADR-001..010`) decision records | PRESERVED |
| `docs/rebuild/` | Predecessor audit, migration map, target architecture, **this skeleton map** | PRESERVED + this file |
| `docs/audit/`, `docs/baseline/`, `docs/acceptance/` | WP-00 audit / baseline artifacts | PRESERVED |
| `docs/coordination/` | CC↔Codex coordination bus (out of WP scope — never modified by a WP) | DO_NOT_TOUCH |
| `pyproject.toml` | Build + tooling + dependency groups (setuptools / ruff / pytest) | UPDATED (T-01-02) |
| `pylock.toml` | PEP 751 runtime dependency lockfile | NEW (T-01-02) |
| `README.md`, `DELIVERY_REPORT.md` | Project overview + delivery report | PRESERVED |

## 2. Package modular skeleton (`auto_bioinfo/`)

Hexagonal layers; the dependency rule points **inward** (`interfaces → pipeline →
application → core`; `adapters → ports → core`). The core imports no concrete
database / LLM / execution environment.

| Package | Layer | Responsibility |
|---|---|---|
| `auto_bioinfo/` (`__init__`, `__main__`) | package / entry | package marker + `python -m auto_bioinfo` entry |
| `interfaces/` | inbound | thin CLI (`cli.py`) — no business logic |
| `pipeline.py` | orchestration | single guarded, idempotent run==resume orchestrator |
| `core/` | domain core | schemas, state machine, event store, ids, validation, artifacts, task packets, workflow compiler, handoff, agent specs/protocol, alignment auditor |
| `quality/` | application | four-layer QC engine |
| `evidence/` | application | EvidenceItem build + claim synthesis (ceiling-capped) |
| `report.py` | application | constrained report builder |
| `reproduction/` | application | reproduction bundle build + compare |
| `execution/` | application | typed object refs + append-only run ledgers |
| `methods/` | adapter (default) | numpy-only `bulk_deg` method + stats + registry |
| `ports/` | outbound seam | 5 hexagonal `Protocol` ports (reserved prod adapters) |
| `adapters/` | adapter (default) | offline planner + fixture resource adapter |
| `fixtures/` | data | committed, clearly-labelled non-real demo fixture |

Reserved production adapters (PostgreSQL event store, S3/MinIO object store,
Nextflow/containerized method, real GEO/EuropePMC discovery, network-LLM planner)
slot in behind the existing ports without touching the core. They are **not**
implemented in WP-01a (see `docs/audit/preserve_replace_retire.yaml`).

## 3. Preserved compatible entry points (must keep working)

| Entry point | Definition | WP-01a status |
|---|---|---|
| Library import | `import auto_bioinfo` | preserved |
| Console script | `bioauto = auto_bioinfo.interfaces.cli:main` (`[project.scripts]`) | preserved |
| Module entry | `python -m auto_bioinfo` → CLI `main()` | preserved |
| Test entry | `python -m unittest discover -t . -s tests -p "test_*.py"` | preserved |

## 4. Out of scope for WP-01a (created by their own later tasks)

`config/` (T-01-03), `deploy/compose/` (T-01-04), `migrations/` (T-01-05),
structured logging config (T-01-06), lint/type/coverage task runner (T-01-07),
`.github/workflows/` CI (T-01-08, later independent WO), fixture-lifecycle
framework (T-01-09), `Dockerfile` / container image (T-01-10), `docs/compliance/`
+ SBOM (T-01-11), PR/change template (T-01-12). None are stubbed here; creating
empty placeholders would falsely imply those tasks are underway.
