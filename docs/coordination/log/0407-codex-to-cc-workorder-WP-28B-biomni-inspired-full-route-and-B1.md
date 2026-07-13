---
turn: 0407
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-28B-biomni-inspired-full-route-and-B1
status: OPEN
date: 2026-07-13
related:
  - 0406-codex-to-cc-workorder-WP-28A-public-bio-resource-registry.md
  - CEO-direct-request-2026-07-13-biomni-agent-tool-design
---

# WORK ORDER: WP-28B full route, starting B1

## Superseding decision

The CEO rejected the inventory-only interpretation of WP-28A and directed the
project to use both the unpacked resource inventory and the open-source Biomni
tool/agent design to complete a working project-native integration. Turn 0406
is superseded before delivery. CC must not open an inventory-only WP-28A PR.

If local WP-28A changes already exist, preserve them and absorb compatible work
into WP-28B1. Do not delete commits, reset, force-push, or destructively roll back.

## Architectural decision

Use Biomni's public architecture as a design reference, not as a runtime
dependency or a license shortcut. Reimplement these concepts against existing
project contracts: declarative action registration, bounded resource retrieval,
plan-act-observe-reflect state, composition only from admitted actions, optional
MCP behind broker/gates, and complete provenance/license/audit/claim ceilings.

Reject unsafe reference behavior: no LLM-generated arbitrary code, builtins or
globals injection, unbounded shell/subprocess, automatic data-lake download,
implicit secret/environment access, or connector execution outside allowlists.
Do not import from or execute unpacked vendor-derived implementation trees.

Directly adding Biomni is not authorized: its current Python/dependency baseline
does not match this project's Python >=3.10 minimal-runtime contract. Keep this
route project-native and stdlib-only unless a later turn explicitly authorizes a
reviewed dependency/lockfile/SBOM change.

## Frozen full route

WP-28B is continuous. After each green-lane merge, CODEX dispatches the next
slice without returning to CEO for routine choices:

1. B1: unified biomedical action/connector registry, deterministic resource
   router, 24-connector inventory, existing 12 planner mappings, explicit risk,
   license and provenance facts.
2. B2: governed execution envelope using fake/recorded transports: transport
   port, request/result contracts, ToolBroker, preflight authorization, egress,
   domain/secret gates, timeout/retry/rate/circuit bounds, artifact/audit hooks.
3. B3: independently written public API adapters in bounded domain groups,
   typed records, recorded fixtures and contract tests.
4. B4: constrained plan-act-observe-reflect Agent orchestration, agent action
   allowlists, stop conditions, claim ceilings, recovery and fake-model tests.
5. B5: bounded MCP list/describe/call bridge behind declared server identities,
   ToolBroker, authorization and audit; no arbitrary command construction.
6. B6: synthetic/recorded end-to-end acceptance, failure/recovery,
   reproducibility manifests, operator docs, license matrix and live-readiness.

Live API calls, external LLMs, first real human-source data, paid services,
public deployment/publication, credentials and license/account acceptance remain
point-of-action hard stops. Offline/recorded code completion proceeds to them.

## WP-28B1 objective

Create the single source of truth from which agents discover suitable biomedical
actions without executing them. Combine the 24 connector surfaces from the
unpack audit, existing 12 PublicBioToolAdapter planners, and current AgentSpec /
ToolBroker boundaries in a typed, deterministic, fail-closed registry/router.

## Authorized files

- `auto_bioinfo/agent_gateway/action_registry.py` (new)
- `auto_bioinfo/agent_gateway/resource_router.py` (new)
- `auto_bioinfo/agent_gateway/__init__.py` only for additive exports
- `auto_bioinfo/adapters/public_bio_tools.py`
- `tests/test_action_registry.py` (new)
- `tests/test_resource_router.py` (new)
- `tests/test_public_bio_tools.py`
- `docs/architecture/biomni_cleanroom_integration.md` (new)
- `docs/rebuild/WP-28B1-REPORT.md` (new)

No other file is authorized without a QUESTION turn.

## Required B1 contracts

Implement an immutable, bounded, JSON-serializable action descriptor with stable
identity/version, description/category/connector, typed parameter descriptions,
output record kind, execution kind, risk/approval flags, agent allowlist,
compatible purposes, provenance/license/verification status, limitations,
scientific eligibility and conservative maximum claim level.

The registry must reject malformed/duplicate descriptors, unknown connectors or
agents, invalid claim levels, contradictory risk flags, unsupported parameter
shapes, and executable actions marked eligible without required facts. It must
list/get/filter deterministically, never fall back, and contain no handler/callable.

Carry forward the exact 24 connector ids and 19/4/1 transport inventory from
0406. Recovered aliases/transport classes are inventory provenance only. Map the
existing 12 offline planners to real action descriptors. Connectors without an
implementation remain inventory-only. Do not invent endpoints, response schemas,
license claims, parity or verification. Existing planners remain offline,
no-retrieval, unverified and scientifically ineligible.

Implement a pure resource router accepting bounded task facts: agent id, purpose,
modality/evidence needs, connector/category preferences, approval facts and
maximum risk. Return an immutable trace with deterministic selected action ids,
rejected candidates and stable reason codes, capability gaps, and approval/live
executor requirements. Enforce AgentSpec allowlist, claim ceiling, risk,
verification and approval boundaries.

The router is metadata-only: no LLM, embeddings, pandas, network, filesystem,
clock, environment, subprocess, MCP, handler invocation or mutation. Retrieval
does not imply execution, verification, evidence, dataset lock or a claim.

## Acceptance evidence

- Exact connector ids, uniqueness, ordering and 19/4/1 counts.
- Existing 12 planners map to descriptors; inventory-only connectors have no
  executable planner/action.
- Registry round-trip is deterministic/JSON-safe; malformed, duplicate,
  contradictory and unknown references fail closed.
- Router is deterministic and agent/risk/claim/approval bounded, with stable
  rejection reasons and explicit capability gaps.
- Negative tests prove no action execution or network/subprocess/MCP/LLM/env/
  filesystem access and no verification/lock/evidence/claim authority.
- Existing public-bio planner tests remain green.
- Focused tests, full `python -m unittest discover -s tests -v`, lint,
  format-check and `git diff --check` pass; CI 3.10/3.11/3.12 is green.

## Delivery protocol

Implement from current `origin/rebuild/auto-bioinfo-core`, open one CC-authored
PR targeting `rebuild/auto-bioinfo-core`, and REPORT exact base/head SHA, files,
tests, CI, provenance notes and residual gaps. CC must not merge. CODEX will
independently verify the exact head and use green-lane handoff if eligible.
