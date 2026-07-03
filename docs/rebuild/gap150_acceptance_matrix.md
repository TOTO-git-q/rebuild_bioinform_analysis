# GAP150 Acceptance Matrix

Status: **acceptance criteria tracker** for what actually landed on this branch
vs what is deferred. Companion to
[`gap150_gap_closure_proposal.md`](gap150_gap_closure_proposal.md).

This is planning coverage, not runtime parity or scientific validity.

## Landed units (in-repo, tested)

| # | Unit | Artifact | Acceptance evidence |
|---|---|---|---|
| L1 | Offline public-bio query-plan adapter | `auto_bioinfo/adapters/public_bio_tools.py` | `tests/test_public_bio_tools.py` (14 tests) |
| L2 | 12 public-bio tool descriptors | same | catalogue test; determinism test |
| L3 | Query-plan tool registry | `build_public_bio_tool_registry()` | registry tests |
| L4 | Inert capability-grant registry (7 grants) | `auto_bioinfo/adapters/capability_registry.py` | `tests/test_capability_registry.py` |
| L5 | Deny-over-allow decision resolver | `resolve_decision()` | decision tests |
| L6 | Quarantine path-exclusion guard | `tests/test_adversarial_boundaries.py` | tree scan test |
| L7 | No-network / import-stability guards | `tests/test_adversarial_boundaries.py` | import + source-scan tests |
| L8 | Evidence & capability docs | `docs/audit/*`, `docs/rebuild/*`, `docs/tools/*` | this matrix |

## Acceptance criteria (landing plan §Batch 1–3)

| Criterion | Met? | How |
|---|---|---|
| Docs distinguish evidence / clean-room / GAP150 / project code / supplement / coordination | Yes | `operon_quarantine_boundary.md` tier table |
| Docs explicitly list excluded material | Yes | `operon_quarantine_boundary.md`, `asset_family_map.md` |
| No vendor source / prompt / binary / raw data copied | Yes | `test_adversarial_boundaries.py` |
| Tools return query plans only | Yes | `is_query_plan=True`, `is_retrieved_data=False` |
| Materialization rejected | Yes | `MaterializationRejected` + test |
| No network / subprocess / live provider | Yes | source-scan + socket-disabled tests |
| Conservative provenance + non-scientific flags | Yes | `verified=False`, `scientific_output_eligible=False` |
| Existing imports remain stable | Yes | `test_adversarial_boundaries.py` import tests |
| GAP150 documented as planning coverage, not parity | Yes | this doc + proposal |
| New registries inert/offline by default | Yes | `assert_no_executable_grants` |
| Tests prove no risky capability becomes executable | Yes | `test_capability_registry.py` |

## Deferred units (planning coverage only — not landed)

| Area | Reason deferred |
|---|---|
| Method-preset / scientific-method executors | Would extend runtime; existing `methods/` untouched |
| Connector registry, prompt registry, skill registry | No `agent_gateway`/`ConnectorRegistry` seam exists yet |
| ToolBroker bridge | Reserved; planners are broker-ready but broker absent |
| Execution profiles, orchestration, memory, traceability | BLOCKED — need approvals/infra not present |
| GPT-review MCP (Batch 4) | **Deferred** — no `mcp/` seam; would add optional egress surface; see final report |

## Boundary reaffirmation

Nothing in the landed set performs live retrieval, materialization, remote
compute, or scientific-conclusion generation. The deferred set stays as
documented reserved seams until an audited executor with full provenance
recording is designed.
