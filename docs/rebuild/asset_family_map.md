# Asset Family Map (clean-room)

Status: **inventory summary**. Records the *families* of assets observed in the
recovered nested archive and how each family is (or is not) represented in this
repository. Only family names and observed entry **counts** are reused — no
asset bodies are copied.

Clean-room provenance: counts come from the static extraction manifest
(`operon_nested_asset_inventory_20260701.tsv`, `asset_family_map.json`) in the
read-only evidence directory. See
[`../audit/operon_quarantine_boundary.md`](../audit/operon_quarantine_boundary.md).

## Family table

| Family | Observed entries | Reuse decision | Rationale |
|---|---:|---|---|
| `mcp-servers` (bio-tools) | 439 | **Requirements only** | public tool *names* → `adapters/public_bio_tools.py`; no vendor server copied |
| `skills` | 120 | Reserved (doc) | skill *taxonomy* only; SKILL.md bodies not copied |
| `agents` | 40 | Reserved (doc) | agent-profile *concept* → existing `core.agent_specs` |
| `compute` | 6 | **BLOCKED** | remote/argv templates need approvals; out of scope |
| `kernels` | 2 | **BLOCKED** | worker execution; not rebuilt |
| `drizzle` (migrations) | 99 | Excluded | production DB migrations out of scope |
| `web-dist` | 308 | **Excluded** | generated web bundles; never committed |
| `seed` | 9 | **Excluded** | raw/seed datasets; never committed |
| `seccomp` | 8 | **Excluded** | sandbox binaries; never committed |
| `sharp-runtime` | 121 | **Excluded** | native image runtime; never committed |
| `fonts` | 4 | **Excluded** | binary fonts; never committed |
| `micromamba` | 1 | **Excluded** | env-solver binary; never committed |
| `BUILD.json` | 1 | Excluded | build metadata; non-evidence |

Total nested entries observed: **1,159**.

## Reuse decisions summary

- **Requirements only** (1 family): `mcp-servers` bio-tool *names* inform the
  offline query-plan catalogue. No server code, schema, or prompt is copied.
- **Reserved (doc)** (2 families): `skills`, `agents` — captured as future-work
  taxonomy; the repo already has `core.agent_specs` for agent shape.
- **BLOCKED** (2 families): `compute`, `kernels` — require execution/approval
  infrastructure that is intentionally not built.
- **Excluded** (8 families): binaries, bundles, datasets, migrations — never
  enter the repository (enforced by `tests/test_adversarial_boundaries.py`).
