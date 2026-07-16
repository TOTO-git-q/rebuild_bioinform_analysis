# Clean-room biomedical agent-tooling integration (WP-28B)

Status: **frozen route, B1 delivered.**
Owner: WP-28B (turn 0407).
Scope of this document: the architectural decision, the boundary, the recovered
inventory provenance, and the B1→B6 route.

This document also replaces the previously broken reference to the nonexistent
`docs/audit/operon_static_analysis_summary.md` that
`auto_bioinfo/adapters/public_bio_tools.py` used to cite.

---

## 1. Decision

The project uses the open-source Biomni tool/agent design as a **public
architecture reference**, and reimplements the useful concepts against this
repository's own contracts. It is **not** a runtime dependency, **not** vendored,
and **not** a license shortcut.

Directly adding Biomni is **not authorized**: its current Python/dependency
baseline does not match this project's `requires-python >= 3.10`,
minimal-runtime contract. This route therefore stays project-native and
stdlib-only unless a later turn explicitly authorizes a reviewed
dependency / lockfile / SBOM change.

### Concepts admitted (reimplemented, not copied)

| Reference concept | Project-native reimplementation |
|---|---|
| Declarative action registration | `auto_bioinfo/agent_gateway/action_registry.py` — inert, typed, fail-closed `ActionDescriptor`s with no handler field |
| Bounded resource retrieval | `auto_bioinfo/agent_gateway/resource_router.py` — pure metadata routing with stable reason codes and explicit capability gaps |
| Plan-act-observe-reflect state | reserved for **B4**, on top of the existing `AgentSpec` / state-machine contracts |
| Composition only from admitted actions | the registry is the only source of action identity; nothing else may mint one |
| Optional MCP behind a broker/gate | reserved for **B5**, behind `ToolBroker` + declared server identities |
| Provenance / license / audit / claim ceilings | descriptor fields + the existing `CLAIM_LEVELS` ceiling, enforced in both directions |

### Reference behavior explicitly rejected

These are **not** reimplemented, at any slice, without a new CEO authorization:

- LLM-generated arbitrary code execution;
- builtins/globals injection into an execution frame;
- unbounded shell/subprocess;
- automatic data-lake download;
- implicit secret/environment access;
- connector execution outside an explicit allowlist.

The unpacked vendor-derived implementation trees
(`03_reconstructed_mcp_server`, `08_rebuilt_biotool`, any `vendor_extracted`
tree, raw payload/JS fragments, recovered context dumps, reconstructed
manifests) are **never** imported, executed, or adapted.

---

## 2. Recovered-inventory provenance (read this before trusting a connector id)

`action_registry.CONNECTOR_INVENTORY` carries 24 biomedical connector surfaces
recovered by a source audit of the unpack assets. What was admitted, and on what
authority:

| Fact | Admitted? | Status |
|---|---|---|
| connector ids | yes | **recovered, not official-doc verified** |
| display names | yes | recovered |
| `mcp_*` package aliases (19) | yes | recovered; **inert metadata only** |
| transport classes / counts (19 / 4 / 1) | yes | recovered |
| categories, summaries | yes | **project-native** (written here, not copied) |
| endpoint URLs | **no** | require public-docs-only review (B3) |
| request/response schemas | **no** | require public-docs-only review (B3) |
| terms / license assertions | **no** | require upstream review (B6 license matrix) |
| implementation bodies | **no** | clean-room boundary; never copied |

The transport split, asserted at registry-build time:

| transport class | count | has `mcp_*` alias |
|---|---|---|
| `local_stdio_bio_runner` | 19 | yes (19 unique aliases) |
| `hosted_streamable_http` | 4 | no |
| `inline_connector` | 1 | no |
| **total** | **24** | **19** |

An `mcp_*` alias **grants nothing**: it launches no subprocess, imports no MCP,
and attaches no connector. It exists so a future slice can be checked against
the surface that was actually observed.

Being *listed* is not being *implemented*. Of the 24 surfaces, this project
implements project-native actions for **7**; the other **17** stay
`inventory_only` with an empty action list. Parity is never fabricated.

---

## 3. What B1 delivers

### `action_registry.py` — the single source of action truth

An `ActionDescriptor` is immutable, bounded, JSON-serializable, and carries
**no callable**: stable identity/version, description/category/connector, typed
parameters, output record kind, execution kind, risk/approval flags, agent
allowlist, compatible purposes, provenance/license/verification status,
limitations, scientific eligibility, and a conservative maximum claim level.

The registry fails closed at construction on: malformed or duplicate
descriptors, unknown connectors or agents, invalid claim levels, contradictory
risk flags, unsupported parameter shapes, and any executable action marked
scientifically eligible without the required verification / license / approval
facts. Lookup and filtering are deterministic and never fall back.

The 12 existing offline planners in
`auto_bioinfo/adapters/public_bio_tools.py` are registered as real descriptors,
each mapped to the recovered connector surface whose **public domain** it
addresses. That mapping is a project-native categorization — **not** a claim
that the recovered connector implements the planner, that endpoints match, or
that any parity exists. The planners remain offline, no-retrieval, unverified,
and scientifically ineligible.

### `resource_router.py` — bounded, deterministic discovery

Given bounded task facts (agent, purpose, modality/evidence needs,
connector/category preferences, approval facts, risk ceiling), the router
returns an immutable `RouteTrace`: deterministic selected action ids, rejected
candidates with stable reason codes, explicit capability gaps, and the
approval / live-executor requirements.

It enforces four boundaries independently:

1. **AgentSpec allowlist** — the agent must exist, be named in the action's
   allowlist, and still hold the action's required tool grant in its own
   `AgentSpec`.
2. **Claim ceiling** — in both directions: an action may never exceed the
   agent's `max_claim_level`, and an action whose ceiling is below the task's
   required level cannot be selected to support it.
3. **Risk / approval / live executor** — enforced against the caller's stated
   facts; the router grants no approval and escalates nothing.
4. **Verification** — a need for a verified or scientifically eligible source
   cannot be met by today's unverified planners, and the router says so as an
   explicit capability gap rather than pretending.

The router is metadata-only: no LLM, embeddings, pandas, network, filesystem,
clock, environment, subprocess, MCP, handler invocation, or mutation.

**Retrieval does not imply execution, verification, evidence, a dataset lock, or
a claim.** Every `RouteTrace` stamps those as `False` explicitly so a stored
trace cannot later be misread as authority.

---

## 4. Frozen route

| slice | scope | status |
|---|---|---|
| **B1** | unified action/connector registry + deterministic resource router | **delivered** |
| B2 | governed execution envelope on fake/recorded transports: transport port, request/result contracts, ToolBroker, preflight authorization, egress/domain/secret gates, timeout/retry/rate/circuit bounds, artifact/audit hooks | pending |
| B3 | independently written public API adapters in bounded domain groups; typed records, recorded fixtures, contract tests | pending |
| B4 | constrained plan-act-observe-reflect Agent orchestration; agent action allowlists, stop conditions, claim ceilings, recovery, fake-model tests | pending |
| B5 | bounded MCP list/describe/call bridge behind declared server identities, ToolBroker, authorization and audit; no arbitrary command construction | pending |
| B6 | synthetic/recorded end-to-end acceptance, failure/recovery, reproducibility manifests, operator docs, license matrix, live-readiness | pending |

## 5. Point-of-action hard stops (unchanged by this route)

Offline / recorded code completion may proceed **up to** these lines, never
across them without explicit CEO authorization:

- live API calls;
- external LLM / service calls;
- first use of real human-source data;
- paid services;
- public deployment or publication;
- credentials, and upstream account / license acceptance;
- destructive or irreversible operations.

## 6. Residual gaps after B1

- No connector has a verified endpoint, schema, license, or terms fact. All 24
  remain `needs_public_docs_verification`, `license_status=unreviewed`.
- 17 of 24 surfaces are inventory-only; no action exists for them.
- No action can be executed at all: the registry holds no handler and there is
  no transport (B2).
- No action is scientifically eligible; the maximum claim level of every
  registered action is `descriptive`.
- The planner → connector mapping is a domain categorization awaiting the
  public-docs review in B3; it asserts no upstream parity.
