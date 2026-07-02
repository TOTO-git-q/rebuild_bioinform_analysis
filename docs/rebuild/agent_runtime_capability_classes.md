# Agent-Runtime Capability Classes (clean-room)

Status: **design reference**. Derived (clean-room) from the static-analysis
taxonomy in [`../audit/operon_static_analysis_summary.md`](../audit/operon_static_analysis_summary.md).
No vendor code or prompt text is reproduced.

This document names the *capability classes* an agent runtime needs and maps each
to its **current status in this repository**. It is deliberately conservative:
every risky class is **deny-by-default** and most are **reserved** (documented,
not executable).

## Capability class table

| Class | Risk | Recovered pattern (evidence) | Project status | Seam |
|---|---|---|---|---|
| **Query planning** | low | offline plan ≠ evidence | **Implemented** | `adapters/public_bio_tools.py` |
| **Prompt registry** | low | modular rule packs | Reserved (doc) | future `agent_gateway` |
| **Skill registry** | med | source-labelled, untrusted-by-default | Reserved (doc) | future `agent_gateway` |
| **Memory policy** | med | reject transient state; ledger lookup | Reserved (doc) | `core.store` / event ledger |
| **Local method exec** | med | contract-bound | **Implemented** | `methods.registry` + MethodContract |
| **Dataset materialization** | high | verified-only | Guarded | `ports.ResourceDiscoveryPort` (offline fixture only) |
| **Network query exec** | high | scoped `network` grant | **Blocked / reserved** | reserved `ToolBroker` |
| **Container exec** | high | image-digest pinned | Reserved (doc) | reserved ExecutionProfile |
| **Remote compute** | high | explicit approval + cost limit | Reserved (doc) | reserved compute port |
| **Connector attach/detach** | high | manifest + terms required | Reserved (doc) | reserved ConnectorRegistry |
| **Capability grant** | control | deny-over-allow | Descriptor-only | `docs/rebuild/gap150_*` |

## Deny-by-default principles (carried into code)

1. **Offline plans are not evidence.** The public-bio adapter stamps every plan
   `verified=False`, `verification_level="unverified"`,
   `scientific_output_eligible=False`.
2. **Materialization is refused**, not silently no-op'd
   (`MaterializationRejected`).
3. **Allow-listed public fields only.** A planner echoes only its declared
   `query_fields`; secrets/local paths/injected instructions are dropped.
4. **Deny-list wins.** Any future capability-grant table must let a deny beat a
   later allow (recovered pattern; enforced by tests when a live grant table is
   built).
5. **Claim ceilings are hard.** The existing `core.validation.validate_claim_ceiling`
   and `alignment_auditor` remain the authority; no new class may raise a claim
   ceiling.

## What is intentionally *not* built here

- No live public-resource executors, remote compute, or browser/native runtime.
- No memory subsystem, no production DB migrations.
- No vendor-derived MCP server implementation.

These remain planning coverage (see the GAP150 proposal docs), not runtime.
