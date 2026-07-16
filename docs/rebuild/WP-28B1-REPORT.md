# WP-28B1 REPORT — unified biomedical action/connector registry & resource router

> Work order: coordination turn `0407` (CODEX → CC, WORK_ORDER, ref
> WP-28B-biomni-inspired-full-route-and-B1), which supersedes the inventory-only
> turn `0406` (WP-28A) before delivery.
> Branch: `rebuild/wp-28b1-action-registry-resource-router`
> (from base `rebuild/auto-bioinfo-core` @ `d428659dc2edbede2b7a5e8acb8ee00d07e02a58`).
> Mode: **offline, stdlib-only, metadata-only. No execution capability added.**

## 1. Supersession handling

No WP-28A branch, commit, or working-tree change existed at the start of this
slice (`git status` clean on the protected base), so there was nothing to
preserve or absorb. Nothing was deleted, reset, force-pushed, or rolled back.
No inventory-only WP-28A PR was opened.

## 2. Requirement → code location

| WP-28B1 requirement | Location |
|---|---|
| Immutable, bounded, JSON-serializable action descriptor | `auto_bioinfo/agent_gateway/action_registry.py` — `ActionDescriptor`, `ActionParameter`, `.to_dict()` |
| Stable identity/version, category/connector, typed params, output kind, execution kind, risk/approval flags, agent allowlist, purposes, provenance/license/verification, limitations, eligibility, claim ceiling | `ActionDescriptor` fields (23 fields, all inert data) |
| Registry rejects malformed/duplicate/unknown/invalid/contradictory/unsupported | `validate_action_descriptor`, `_validate_contradictory_flags`, `_validate_parameters`, `ActionRegistry.__init__` |
| Executable action marked eligible without required facts rejected | `_validate_contradictory_flags` (verification + license + approval all required) |
| List/get/filter deterministically, never fall back, no handler/callable | `ActionRegistry.list_action_ids/get/filter`, `_validate_no_callable`, `UnknownActionError`/`UnknownConnectorError` |
| Exact 24 connector ids + 19/4/1 transport inventory | `CONNECTOR_INVENTORY`, `CONNECTOR_IDS`, `EXPECTED_TRANSPORT_COUNTS`, `_validate_connector_inventory` |
| Recovered aliases/transport classes are inventory provenance only | `ConnectorDescriptor.recovered_alias`, `provenance_origin="recovered_inventory_only"`, `to_dict()` stamps `attached=False`, `endpoint_known=False` |
| Existing 12 planners → real action descriptors | `_PLANNER_BINDINGS`, `_descriptor_for`, `build_default_action_registry` |
| Connectors without an implementation remain inventory-only | derived in `ActionRegistry.describe_connector` (17 of 24, empty action list) |
| Pure resource router over bounded task facts | `auto_bioinfo/agent_gateway/resource_router.py` — `RouteRequest`, `ResourceRouter.route` |
| Immutable trace: selected ids, rejected + stable reasons, capability gaps, approval/live-executor requirements | `RouteTrace`, `RejectedCandidate`, `REASON_CODES`, `CAPABILITY_GAP_CODES`, `_capability_gaps` |
| Enforce AgentSpec allowlist, claim ceiling, risk, verification, approval | `ResourceRouter._reject_reason` (5 grouped checks) |
| Retrieval implies no execution/verification/evidence/lock/claim | `RouteTrace.is_retrieval/is_execution/is_evidence/grants_dataset_lock/grants_claim/grants_export_authority` — all constant `False` |
| Additive exports | `auto_bioinfo/agent_gateway/__init__.py` (prefixed aliases; no existing export changed) |
| Replace the broken `docs/audit/operon_static_analysis_summary.md` reference | `auto_bioinfo/adapters/public_bio_tools.py` docstring → `docs/architecture/biomni_cleanroom_integration.md` |
| Architecture/provenance/route documentation | `docs/architecture/biomni_cleanroom_integration.md` |

## 3. Changed files

| File | Change |
|---|---|
| `auto_bioinfo/agent_gateway/action_registry.py` | **new** — connector inventory + action registry |
| `auto_bioinfo/agent_gateway/resource_router.py` | **new** — deterministic metadata router |
| `auto_bioinfo/agent_gateway/__init__.py` | additive re-exports only |
| `auto_bioinfo/adapters/public_bio_tools.py` | additive read-only `get_tool_spec()`; docstring reference repointed. **No planner behavior changed.** |
| `tests/test_action_registry.py` | **new** — 40 tests |
| `tests/test_resource_router.py` | **new** — 25 tests |
| `tests/test_public_bio_tools.py` | additive: 12-planner count lock, `get_tool_spec` coverage |
| `docs/architecture/biomni_cleanroom_integration.md` | **new** |
| `docs/rebuild/WP-28B1-REPORT.md` | **new** — this file |

## 4. Acceptance evidence

| Required evidence | Test |
|---|---|
| Exact connector ids, uniqueness, ordering | `ConnectorInventoryTest.test_exact_connector_ids_and_order`, `test_connector_ids_are_unique_and_count_24` |
| 19/4/1 transport counts | `ConnectorInventoryTest.test_transport_split_is_19_4_1` |
| 19 inert `mcp_*` aliases | `ConnectorInventoryTest.test_nineteen_unique_inert_mcp_aliases`, `test_connector_records_claim_no_capability` |
| No endpoint URL carried over | `ConnectorInventoryTest.test_no_endpoint_url_is_carried_over` |
| 12 planners map to descriptors | `PlannerMappingTest.test_all_twelve_planners_map_to_descriptors`, `test_typed_parameters_mirror_the_planner_allowlist` |
| Inventory-only connectors have no executable planner/action | `PlannerMappingTest.test_inventory_only_connectors_expose_no_action` (17 of 24) |
| Registry round-trip deterministic/JSON-safe | `RegistryLookupTest.test_round_trip_is_deterministic_and_json_safe` |
| Malformed/duplicate/contradictory/unknown fail closed | `FailClosedValidationTest` (13 tests) |
| Executable+eligible without required facts rejected | `FailClosedValidationTest.test_executable_action_eligible_without_required_facts_rejected` |
| Router deterministic | `RouterDeterminismTest` (6 tests) |
| Agent/risk/claim/approval/verification bounded, stable reasons | `BoundaryEnforcementTest` (9 tests) |
| Explicit capability gaps | `BoundaryEnforcementTest.test_preferring_an_inventory_only_connector_is_an_explicit_gap`, `test_verification_requirement_cannot_be_met_today` |
| No execution / network / subprocess / MCP / LLM / env / filesystem | `NoExecutionAuthorityTest` (7 tests), `NoAuthorityTest` (6 tests) |
| No verification/lock/evidence/claim authority | `NoAuthorityTest.test_trace_confers_no_execution_evidence_lock_or_claim`, `NoExecutionAuthorityTest.test_no_action_claims_verification_or_eligibility` |
| Existing public-bio planner tests remain green | `tests/test_public_bio_tools.py` — unchanged tests all pass |

## 5. Delivered facts

- **24** connector surfaces; **19** `local_stdio_bio_runner` + **4**
  `hosted_streamable_http` + **1** `inline_connector`; **19** unique `mcp_*`
  aliases, all inert.
- **12** action descriptors (one per existing offline planner), mapped onto
  **7** connector surfaces. **17** surfaces remain `inventory_only`.
- Every action: `execution_kind=offline_query_plan`,
  `verification_status=unverified`, `license_status=unreviewed`,
  `scientific_output_eligible=False`, `max_claim_level=descriptive`,
  `network_egress=False`, `requires_live_executor=False`, `mutates_state=False`.
- Only `resource_discovery_agent` may be routed to any of them: it is the only
  agent holding the `metadata_search` grant in `AgentSpec`. This is re-derived
  from `build_agent_specs()` and validated per descriptor, so a descriptor can
  never quietly widen an agent's authority.

## 6. Residual gaps

- No endpoint, schema, license, or terms fact is verified for any connector;
  all 24 remain `needs_public_docs_verification`.
- No action is executable: the registry holds no handler, and no transport
  exists (reserved for WP-28B2).
- The planner → connector mapping is a project-native **domain categorization**,
  not an upstream parity or verification claim.
- `output_record_kind` on an offline planner names the record a *future* audited
  executor would return; the action itself returns a query plan only. Recorded
  in every descriptor's `limitations`.
- B2–B6 remain pending; live API calls, external LLMs, real human-source data,
  paid services, public deployment and credential/license acceptance remain
  point-of-action hard stops.
