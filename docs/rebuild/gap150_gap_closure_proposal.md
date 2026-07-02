# GAP150 Gap-Closure Proposal (planning coverage)

Status: **proposal / planning framework**. GAP150 is a *bridge-unit coverage*
target, **not** a runtime-parity or scientific-validity claim. This document
re-expresses the recovered GAP150 pack as project-native planning coverage.

Clean-room provenance: the numbers below are recovered from the read-only
evidence pack (`gap150_cleanroom_integration_pack/specs/gap150_validation_report.json`).
No vendor source, prompt text, or web bundle is copied. See
[`../audit/operon_quarantine_boundary.md`](../audit/operon_quarantine_boundary.md).

## What GAP150 means

"GAP150" is the goal of covering **≥150%** of the reusable installer baseline as
independent, clean-room *bridge units* (specs, descriptors, tests) — enough
planning coverage to de-risk future runtime work, without pretending the runtime
already exists.

| Metric | Value |
|---|---:|
| Installer reusable baseline units | 45 |
| 150% minimum bridge units | 68 |
| Provided bridge units (evidence pack) | 80 |
| Coverage ratio | 177.8% |
| Errors | 0 |

> These figures describe the *evidence pack's* self-assessment. This repository
> does **not** import that pack; it lands only the safe, project-native subset
> (offline query planners + inert capability descriptors + docs). The acceptance
> matrix below tracks what is actually in-repo vs deferred.

## Gap areas and disposition in this repo

| Gap area | Evidence-pack coverage | Disposition here |
|---|---|---|
| Method selection (18 presets) | recommendation logic | **Deferred** (docs only) — no method-preset executor added |
| Scientific methods (8 runnable + 10 contract) | local adapters | **Deferred** — existing `methods/registry.py` unchanged |
| Resource discovery (24 connectors) | query-plan specs | **Partially landed** — 12 offline planners in `adapters/public_bio_tools.py` |
| Connector registry | manifest data | **Deferred** — reserved `ConnectorRegistry` seam (doc) |
| Capability gates (12 grants) | fail-closed descriptors | **Landed (inert)** — `adapters/capability_registry.py` |
| Prompt/skill registry (14 records) | inert records | **Deferred** — reserved `agent_gateway` seam (doc) |
| ToolBroker bridge | inert handlers | **Deferred** — reserved seam; planners are ToolBroker-ready |
| Execution profiles | local/container/remote descriptors | **Deferred** — BLOCKED (approvals/infra) |
| Orchestration | plan-track descriptors | **Deferred** — maps to existing `core.agent_specs` |
| Memory policy | ledger-lookup descriptors | **Deferred** — reserved |
| Traceability reporting | claim/bundle scan descriptors | **Deferred** — existing artifact/event ledger covers today |

## Why most areas are deferred

The repository is at an early WP-06 intake stage and has **no** `control_plane`,
`agent_gateway` broker, `mcp`, or live-executor seams. Scaffolding them now would
create a parallel runtime — explicitly forbidden by the landing plan. The safe,
architecture-improving subset is:

1. **Offline public-bio query planners** (landed) — real, tested, inert.
2. **Inert capability-grant descriptors** (landed) — deny-by-default, prove no
   risky capability becomes executable.
3. **Docs** capturing the rest as reserved future work with clean boundaries.

## Clean-room boundary (reaffirmed)

Query plans are planning data only. They cannot support a scientific claim until
a future audited executor records request/response provenance, response hashes,
terms/license, contact-email status, rate-limit handling, and schema validation.
No area above authorises execution by default.
