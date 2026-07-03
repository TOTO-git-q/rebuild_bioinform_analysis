# Project Interface Map

Status: **interface inventory**. Lists the real ports/adapters/registries in
this repository and how the clean-room additions plug into them, so a reviewer
can confirm nothing forks a parallel architecture.

## Existing seams (verified in-repo)

| Interface | File | Kind |
|---|---|---|
| `PlannerPort` | `auto_bioinfo/ports/__init__.py` | Protocol |
| `ResourceDiscoveryPort` | `auto_bioinfo/ports/__init__.py` | Protocol |
| `AnalysisMethodPort` | `auto_bioinfo/ports/__init__.py` | Protocol |
| `ObjectStorePort` | `auto_bioinfo/ports/__init__.py` | Protocol |
| `EventStorePort` | `auto_bioinfo/ports/__init__.py` | Protocol |
| `OfflineDeterministicPlanner` | `auto_bioinfo/adapters/offline_planner.py` | adapter (`PlannerPort`) |
| `FixtureResourceAdapter` | `auto_bioinfo/adapters/fixture_resources.py` | adapter (`ResourceDiscoveryPort`) |
| method registry | `auto_bioinfo/methods/registry.py` | registry |
| provenance/artifacts | `auto_bioinfo/core/artifacts.py`, `core/events.py` | services |
| validation / claim ceiling | `auto_bioinfo/core/validation.py` | service |
| alignment auditor | `auto_bioinfo/core/alignment_auditor.py` | service |

> Note: the prompt materials assumed `agent_gateway/tool_broker.py`,
> `agent_gateway/prompt_registry.py`, `control_plane/*`, and
> `core/provenance.py`. **These do not exist** on the current base
> (`agent_gateway/` has only `context_builder.py`; there is no `control_plane/`
> or `mcp/`). The additions below adapt to the *actual* repo, and the missing
> seams are recorded as **reserved / future** rather than scaffolded.

## Additions on this branch

| Addition | File | Plugs into | Guarantee |
|---|---|---|---|
| Public-bio query-plan adapter | `auto_bioinfo/adapters/public_bio_tools.py` | standalone offline adapter; reserved `ToolBroker` seam | offline, deterministic, plan-only |
| Query-plan tool registry | `build_public_bio_tool_registry()` | same module | inert bound planners |
| Package re-exports | `auto_bioinfo/adapters/__init__.py` | import convenience | additive, no side effects |
| Capability-grant descriptors | (see GAP150 proposal docs) | descriptor-only | deny-by-default, non-executable |

## Provenance vocabulary reused

The public-bio adapter preserves the **semantics** of the landing plan's
provenance requirements using the repo's *existing* conservative shape rather
than a new enum framework:

- repo uses a `provenance` list of `{source_type, source_id, note}` records
  (`core.schemas`) and a `verified: bool` / `source_status: str` pair
  (`ResourceCandidate`, guarded by `core.validation.validate_no_unknown_verified_dataset`);
- the adapter emits `verified=False`, `verification_level="unverified"`,
  `retrieval_mode="offline_no_retrieval"`, `source_status="offline_query_plan"`,
  `scientific_output_eligible=False`, plus a `clean_room_spec` provenance record.

This keeps a single provenance model across the codebase.

## Import-stability contract

- `import auto_bioinfo.adapters` and `import auto_bioinfo.adapters.public_bio_tools`
  have no side effects and pull in no network/subprocess libraries
  (asserted in `tests/test_public_bio_tools.py` and
  `tests/test_adversarial_boundaries.py`).
- No existing import path changed; all additions are additive.
