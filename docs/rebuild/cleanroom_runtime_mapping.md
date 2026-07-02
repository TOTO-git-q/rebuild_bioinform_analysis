# Clean-Room Runtime Mapping

Status: **mapping doc**. Maps recovered clean-room runtime *concepts* to the
current `auto_bioinfo` architecture. Distinguishes: already-implemented seams,
safe offline specs, future runtime work, and blocked live/network/vendor areas.

Clean-room provenance: concept names are from
[`../audit/operon_static_analysis_summary.md`](../audit/operon_static_analysis_summary.md);
no vendor implementation is copied.

## Legend

- **DONE** — implemented and tested in this repo.
- **OFFLINE-SPEC** — inert, offline, deterministic; safe to ship.
- **FUTURE** — reserved seam, documented, not executable.
- **BLOCKED** — requires live network / vendor source / out-of-scope infra.

## Mapping

| Clean-room concept | Current project seam | State | Notes |
|---|---|---|---|
| Public bio tool surface | `adapters/public_bio_tools.py` | **DONE** | 12 offline query planners; plans only |
| Query-plan tool registry | `build_public_bio_tool_registry()` | **DONE** | inert bound planners |
| Planner / question intake | `adapters/offline_planner.py` (`PlannerPort`) | **DONE** | deterministic, no invented facts |
| Resource discovery | `adapters/fixture_resources.py` (`ResourceDiscoveryPort`) | **DONE** | offline fixture; verified-only guard |
| Method contracts | `methods/registry.py` | **DONE** | claim-capability bound |
| Claim ceiling / alignment | `core.validation`, `core.alignment_auditor` | **DONE** | hard ceilings |
| Artifact provenance | `core.artifacts`, `core.events` | **DONE** | checksum-addressed, append-only |
| Capability grant descriptors | `docs/rebuild/gap150_*` | **OFFLINE-SPEC** | descriptor-only, deny-by-default |
| Connector registry (manifest) | reserved `ConnectorRegistry` | **FUTURE** | terms/license/contact as provenance |
| Prompt registry (modular packs) | reserved `agent_gateway` module | **FUTURE** | taxonomy only, no prompt text |
| Skill registry (source-labelled) | reserved `agent_gateway` module | **FUTURE** | SKILL.md as data, untrusted by default |
| Memory policy | reserved; `core.store` ledger today | **FUTURE** | reject transient state |
| ToolBroker (policy boundary) | reserved | **FUTURE** | would host public-arg declarations + grants |
| Live network executor | — | **BLOCKED** | needs audited HTTP + provenance recording |
| Dataset materialization (real) | `ResourceDiscoveryPort.materialize` | **BLOCKED** | fixture copy only; real fetch out of scope |
| Remote/container compute | reserved ExecutionProfile | **BLOCKED** | approvals + cost limits required |
| MCP server (vendor) | — | **BLOCKED** | vendor-derived; not rebuilt |

## Guarantees preserved by this branch

- The dependency arrow still points inward (adapters → ports → core). The new
  `public_bio_tools` adapter depends only on `core.ids`.
- No new runtime dependency, workflow, Docker, or lockfile change.
- Existing public interfaces are unchanged; the new package-level re-exports in
  `adapters/__init__.py` are additive.

## Bridge to GAP150

The **FUTURE** and **OFFLINE-SPEC** rows above are the coverage tracked by the
GAP150 proposal — see
[`gap150_gap_closure_proposal.md`](gap150_gap_closure_proposal.md) and
[`gap150_acceptance_matrix.md`](gap150_acceptance_matrix.md). GAP150 is planning
coverage, **not** runtime parity.
