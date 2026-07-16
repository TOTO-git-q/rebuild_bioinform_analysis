"""Tests for the WP-28B1 unified biomedical action/connector registry.

Covers the acceptance evidence the work order requires: the exact recovered
connector inventory (ids / uniqueness / ordering / 19-4-1 transport split), the
12 existing planners mapping to real descriptors, inventory-only connectors
exposing nothing executable, deterministic JSON-safe round-trips, and — most
importantly — the adversarial boundaries: fail-closed rejection of malformed,
duplicate, contradictory and unknown references, and proof that a descriptor
carries no handler and no execution / network / claim authority.
"""

import inspect
import json
import unittest
from dataclasses import FrozenInstanceError, replace

from auto_bioinfo.adapters.public_bio_tools import PublicBioToolAdapter
from auto_bioinfo.agent_gateway.action_registry import (
    CATEGORY_LITERATURE,
    CONNECTOR_IDS,
    CONNECTOR_INVENTORY,
    EXECUTION_KIND_LIVE_RETRIEVAL,
    EXECUTION_KIND_OFFLINE_QUERY_PLAN,
    EXPECTED_TRANSPORT_COUNTS,
    IMPLEMENTATION_INVENTORY_ONLY,
    IMPLEMENTATION_PROJECT_NATIVE,
    LICENSE_UNREVIEWED,
    PURPOSE_DATASET_DISCOVERY,
    PURPOSE_LITERATURE_DISCOVERY,
    RISK_HIGH,
    RISK_MODERATE,
    TRANSPORT_HOSTED_HTTP,
    TRANSPORT_INLINE,
    TRANSPORT_LOCAL_STDIO,
    VERIFICATION_UNVERIFIED,
    ActionDescriptor,
    ActionParameter,
    ActionRegistry,
    ActionRegistryError,
    UnknownActionError,
    UnknownConnectorError,
    build_default_action_registry,
    registry_to_json,
    validate_action_descriptor,
)

# The exact 24 surfaces the source audit recorded, in the recorded order.
EXPECTED_CONNECTOR_IDS = (
    "biomart",
    "pubmed",
    "clinical-trials",
    "chembl",
    "biorxiv",
    "variants",
    "clinical-genomics",
    "expression",
    "regulation",
    "protein-annotation",
    "rna",
    "structures-interactions",
    "omics-archives",
    "genes-ontologies",
    "drug-regulatory",
    "research-resources",
    "cancer-models",
    "chemistry",
    "human-genetics",
    "literature",
    "genomes",
    "cellguide",
    "zinc",
    "ketcher-chemistry",
)


def _sample_descriptor(**overrides):
    """A minimal valid descriptor used to probe one invariant at a time."""
    base = dict(
        action_id="test.sample",
        version="1.0.0",
        title="Sample",
        description="Sample offline planner used only by tests.",
        category=CATEGORY_LITERATURE,
        connector_id="pubmed",
        parameters=(ActionParameter("query", "string", True, "Public search text."),),
        output_record_kind="literature_reference",
        execution_kind=EXECUTION_KIND_OFFLINE_QUERY_PLAN,
        risk_level="low",
        requires_approval=False,
        approval_gate="network.query_plan",
        requires_live_executor=False,
        network_egress=False,
        mutates_state=False,
        allowed_agent_ids=("resource_discovery_agent",),
        required_agent_tool="metadata_search",
        compatible_purposes=(PURPOSE_LITERATURE_DISCOVERY,),
        provenance_origin="project_native_cleanroom",
        provenance_notes=("test fixture",),
        license_status=LICENSE_UNREVIEWED,
        verification_status=VERIFICATION_UNVERIFIED,
        limitations=("test fixture; not a real action",),
        scientific_output_eligible=False,
        max_claim_level="descriptive",
    )
    base.update(overrides)
    return ActionDescriptor(**base)


class ConnectorInventoryTest(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_action_registry()

    def test_exact_connector_ids_and_order(self):
        self.assertEqual(CONNECTOR_IDS, EXPECTED_CONNECTOR_IDS)
        self.assertEqual(self.registry.list_connector_ids(), list(EXPECTED_CONNECTOR_IDS))

    def test_connector_ids_are_unique_and_count_24(self):
        self.assertEqual(len(CONNECTOR_IDS), 24)
        self.assertEqual(len(set(CONNECTOR_IDS)), 24)

    def test_transport_split_is_19_4_1(self):
        counts = self.registry.transport_counts()
        self.assertEqual(counts[TRANSPORT_LOCAL_STDIO], 19)
        self.assertEqual(counts[TRANSPORT_HOSTED_HTTP], 4)
        self.assertEqual(counts[TRANSPORT_INLINE], 1)
        self.assertEqual(counts, EXPECTED_TRANSPORT_COUNTS)
        self.assertEqual(sum(counts.values()), 24)

    def test_nineteen_unique_inert_mcp_aliases(self):
        aliases = [c.recovered_alias for c in CONNECTOR_INVENTORY if c.recovered_alias]
        self.assertEqual(len(aliases), 19)
        self.assertEqual(len(set(aliases)), 19)
        for alias in aliases:
            self.assertTrue(alias.startswith("mcp_"), alias)
        # Every alias belongs to a local_stdio surface, and none is a capability.
        aliased = [c for c in CONNECTOR_INVENTORY if c.recovered_alias]
        self.assertTrue(all(c.transport_class == TRANSPORT_LOCAL_STDIO for c in aliased))

    def test_connector_records_claim_no_capability(self):
        for connector_id in CONNECTOR_IDS:
            record = self.registry.describe_connector(connector_id)
            self.assertFalse(record["attached"], connector_id)
            self.assertFalse(record["endpoint_known"], connector_id)
            self.assertEqual(record["license_status"], LICENSE_UNREVIEWED, connector_id)
            self.assertNotIn("url", record)
            self.assertNotIn("endpoint", record)

    def test_no_endpoint_url_is_carried_over(self):
        import auto_bioinfo.agent_gateway.action_registry as mod

        source = inspect.getsource(mod)
        for forbidden in ("http://", "https://"):
            self.assertNotIn(forbidden, source, f"endpoint {forbidden!r} must not be carried over from the source pack")

    def test_unknown_connector_fails_closed(self):
        with self.assertRaises(UnknownConnectorError):
            self.registry.describe_connector("no-such-connector")
        with self.assertRaises(UnknownConnectorError):
            self.registry.connector_action_ids("no-such-connector")


class PlannerMappingTest(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_action_registry()

    def test_all_twelve_planners_map_to_descriptors(self):
        planner_ids = PublicBioToolAdapter().list_tools()
        self.assertEqual(len(planner_ids), 12)
        expected = sorted(f"public_bio.{tid}" for tid in planner_ids)
        self.assertEqual(self.registry.list_action_ids(), expected)

    def test_every_action_targets_a_known_connector(self):
        for action_id in self.registry.list_action_ids():
            descriptor = self.registry.get(action_id)
            self.assertIn(descriptor.connector_id, CONNECTOR_IDS)

    def test_implemented_connectors_are_project_native(self):
        implemented = [c for c in CONNECTOR_IDS if self.registry.connector_action_ids(c)]
        self.assertEqual(len(implemented), 7)
        for connector_id in implemented:
            record = self.registry.describe_connector(connector_id)
            self.assertEqual(record["implementation_status"], IMPLEMENTATION_PROJECT_NATIVE)
            self.assertTrue(record["action_ids"])

    def test_inventory_only_connectors_expose_no_action(self):
        # 24 surfaces, 7 implemented -> 17 stay inventory-only.  No parity is faked.
        inventory_only = [c for c in CONNECTOR_IDS if not self.registry.connector_action_ids(c)]
        self.assertEqual(len(inventory_only), 17)
        for connector_id in inventory_only:
            record = self.registry.describe_connector(connector_id)
            self.assertEqual(record["implementation_status"], IMPLEMENTATION_INVENTORY_ONLY)
            self.assertEqual(record["action_ids"], [])
            self.assertEqual(self.registry.filter(connector_id=connector_id), [])

    def test_typed_parameters_mirror_the_planner_allowlist(self):
        adapter = PublicBioToolAdapter()
        for tool_id in adapter.list_tools():
            descriptor = self.registry.get(f"public_bio.{tool_id}")
            spec = adapter.get_tool_spec(tool_id)
            self.assertEqual(tuple(p.name for p in descriptor.parameters), spec.query_fields, tool_id)

    def test_every_planner_action_is_conservative(self):
        for action_id in self.registry.list_action_ids():
            d = self.registry.get(action_id)
            self.assertEqual(d.execution_kind, EXECUTION_KIND_OFFLINE_QUERY_PLAN, action_id)
            self.assertEqual(d.verification_status, VERIFICATION_UNVERIFIED, action_id)
            self.assertEqual(d.license_status, LICENSE_UNREVIEWED, action_id)
            self.assertFalse(d.scientific_output_eligible, action_id)
            self.assertFalse(d.network_egress, action_id)
            self.assertFalse(d.mutates_state, action_id)
            self.assertFalse(d.requires_live_executor, action_id)
            self.assertEqual(d.max_claim_level, "descriptive", action_id)
            self.assertTrue(d.limitations, action_id)
            self.assertTrue(d.provenance_notes, action_id)


class RegistryLookupTest(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_action_registry()

    def test_list_is_sorted_and_stable(self):
        first = self.registry.list_action_ids()
        self.assertEqual(first, sorted(first))
        self.assertEqual(first, build_default_action_registry().list_action_ids())

    def test_get_unknown_action_fails_closed(self):
        with self.assertRaises(UnknownActionError):
            self.registry.get("public_bio.no_such_action")

    def test_filter_is_deterministic_and_sorted(self):
        result = [d.action_id for d in self.registry.filter(purpose=PURPOSE_DATASET_DISCOVERY)]
        self.assertEqual(result, sorted(result))
        self.assertEqual(
            result,
            ["public_bio.arrayexpress_search", "public_bio.geo_dataset_search", "public_bio.sra_run_search"],
        )

    def test_filter_by_agent_and_connector(self):
        by_agent = self.registry.filter(agent_id="resource_discovery_agent")
        self.assertEqual(len(by_agent), 12)
        # An agent without the metadata_search grant matches nothing.
        self.assertEqual(self.registry.filter(agent_id="result_auditor"), [])
        self.assertEqual(len(self.registry.filter(connector_id="omics-archives")), 3)

    def test_filter_rejects_unknown_values(self):
        with self.assertRaises(UnknownConnectorError):
            self.registry.filter(connector_id="nope")
        with self.assertRaises(ActionRegistryError):
            self.registry.filter(category="nope")
        with self.assertRaises(ActionRegistryError):
            self.registry.filter(purpose="nope")
        with self.assertRaises(ActionRegistryError):
            self.registry.filter(agent_id="nope")
        with self.assertRaises(ActionRegistryError):
            self.registry.filter(max_risk_level="nope")

    def test_round_trip_is_deterministic_and_json_safe(self):
        payload = registry_to_json(self.registry)
        self.assertEqual(payload, registry_to_json(build_default_action_registry()))
        parsed = json.loads(payload)
        self.assertEqual(parsed["connector_count"], 24)
        self.assertEqual(parsed["transport_counts"], EXPECTED_TRANSPORT_COUNTS)
        self.assertEqual(len(parsed["actions"]), 12)
        # Re-serializing the parsed structure must be byte-identical.
        self.assertEqual(json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(",", ":")), payload)


class FailClosedValidationTest(unittest.TestCase):
    def test_valid_sample_passes(self):
        self.assertIsInstance(validate_action_descriptor(_sample_descriptor()), ActionDescriptor)

    def test_non_descriptor_rejected(self):
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor({"action_id": "x"})

    def test_duplicate_action_ids_rejected(self):
        with self.assertRaises(ActionRegistryError) as ctx:
            ActionRegistry([_sample_descriptor(), _sample_descriptor()])
        self.assertIn("duplicate", str(ctx.exception))

    def test_unknown_connector_rejected(self):
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(connector_id="not-a-connector"))

    def test_unknown_agent_rejected(self):
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(allowed_agent_ids=("ghost_agent",)))

    def test_agent_without_the_required_tool_grant_rejected(self):
        # question_normalizer exists but holds no tools at all.
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(allowed_agent_ids=("question_normalizer",)))

    def test_empty_allowlists_rejected(self):
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(allowed_agent_ids=()))
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(compatible_purposes=()))

    def test_invalid_claim_level_rejected(self):
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(max_claim_level="totally_proven"))

    def test_claim_level_above_agent_ceiling_rejected(self):
        # resource_discovery_agent's ceiling is 'association'; go above it.
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(max_claim_level="causal_support"))

    def test_unsupported_parameter_shapes_rejected(self):
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(parameters=(ActionParameter("blob", "object", False, "nested"),)))
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(parameters=({"name": "query"},)))
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(
                _sample_descriptor(
                    parameters=(
                        ActionParameter("query", "string", True, "a"),
                        ActionParameter("query", "string", True, "duplicate name"),
                    )
                )
            )

    def test_malformed_fields_rejected(self):
        for override in (
            {"action_id": ""},
            {"action_id": "x" * 500},
            {"version": ""},
            {"title": ""},
            {"description": "  "},
            {"category": "nope"},
            {"execution_kind": "nope"},
            {"risk_level": "nope"},
            {"output_record_kind": "nope"},
            {"verification_status": "nope"},
            {"license_status": "nope"},
            {"provenance_origin": "nope"},
            {"requires_approval": "yes"},
            {"limitations": ()},
            {"provenance_notes": ()},
            {"limitations": "not a tuple"},
        ):
            with self.subTest(override=override):
                with self.assertRaises(ActionRegistryError):
                    validate_action_descriptor(_sample_descriptor(**override))

    def test_contradictory_risk_flags_rejected(self):
        # Egress without a live executor; egress at zero risk.
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(execution_kind=EXECUTION_KIND_LIVE_RETRIEVAL, network_egress=True, requires_live_executor=False))
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(
                _sample_descriptor(
                    execution_kind=EXECUTION_KIND_LIVE_RETRIEVAL,
                    network_egress=True,
                    requires_live_executor=True,
                    risk_level="none",
                )
            )
        # Moderate/high risk without approval.
        for level in (RISK_MODERATE, RISK_HIGH):
            with self.assertRaises(ActionRegistryError):
                validate_action_descriptor(_sample_descriptor(execution_kind=EXECUTION_KIND_LIVE_RETRIEVAL, risk_level=level, requires_approval=False))
        # requires_approval with no gate named.
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(execution_kind=EXECUTION_KIND_LIVE_RETRIEVAL, requires_approval=True, approval_gate=""))

    def test_offline_planner_may_not_set_effectful_flags(self):
        for override in (
            {"network_egress": True},
            {"mutates_state": True},
            {"requires_live_executor": True},
            {"requires_approval": True},
            {"scientific_output_eligible": True},
            {"risk_level": RISK_HIGH},
        ):
            with self.subTest(override=override):
                with self.assertRaises(ActionRegistryError):
                    validate_action_descriptor(_sample_descriptor(**override))

    def test_executable_action_eligible_without_required_facts_rejected(self):
        eligible = dict(
            execution_kind=EXECUTION_KIND_LIVE_RETRIEVAL,
            scientific_output_eligible=True,
            requires_live_executor=True,
            network_egress=True,
            risk_level=RISK_MODERATE,
            requires_approval=True,
            approval_gate="network.live_retrieval",
        )
        # Unverified -> rejected.
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(**eligible))
        # Verified but license unreviewed -> rejected.
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(**{**eligible, "verification_status": "contract_tested"}))
        # Verified + licensed but no approval requirement -> rejected.
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(
                _sample_descriptor(
                    **{
                        **eligible,
                        "verification_status": "contract_tested",
                        "license_status": "upstream_reviewed",
                        "requires_approval": False,
                        "risk_level": "low",
                    }
                )
            )

    def test_descriptor_carrying_a_callable_rejected(self):
        with self.assertRaises(ActionRegistryError):
            validate_action_descriptor(_sample_descriptor(limitations=(lambda: "x",)))


class NoExecutionAuthorityTest(unittest.TestCase):
    """Adversarial: possessing the registry must grant no capability at all."""

    def setUp(self):
        self.registry = build_default_action_registry()

    def test_descriptors_hold_no_handler_or_callable(self):
        for action_id in self.registry.list_action_ids():
            descriptor = self.registry.get(action_id)
            for name, value in vars(descriptor).items():
                items = value if isinstance(value, tuple) else (value,)
                for item in items:
                    self.assertFalse(callable(item), f"{action_id}.{name} carries a callable")
            for banned in ("handler", "callable", "client", "endpoint", "url", "token", "credential"):
                self.assertNotIn(banned, descriptor.to_dict(), f"{action_id} exposes {banned}")

    def test_registry_exposes_no_run_or_execute_surface(self):
        for banned in ("run", "execute", "call", "invoke", "fetch", "retrieve", "materialize", "download"):
            self.assertFalse(hasattr(self.registry, banned), f"registry exposes {banned}()")

    def test_module_imports_no_network_subprocess_mcp_or_llm(self):
        import auto_bioinfo.agent_gateway.action_registry as mod

        source = inspect.getsource(mod)
        for forbidden in (
            "import socket",
            "import requests",
            "import urllib",
            "import http",
            "import subprocess",
            "import os",
            "import pandas",
            "import numpy",
            "import mcp",
            "subprocess.",
            "os.environ",
            "open(",
            "eval(",
            "exec(",
            "datetime.now",
            "time.time",
        ):
            self.assertNotIn(forbidden, source, f"forbidden token {forbidden!r} present")

    def test_building_the_registry_opens_no_socket(self):
        import socket

        original = socket.socket

        def _boom(*_a, **_k):
            raise AssertionError("the action registry must not open sockets")

        socket.socket = _boom  # type: ignore[assignment]
        try:
            registry = build_default_action_registry()
            registry_to_json(registry)
        finally:
            socket.socket = original
        self.assertEqual(len(registry.list_action_ids()), 12)

    def test_descriptors_are_immutable(self):
        descriptor = self.registry.get("public_bio.pubmed_search")
        with self.assertRaises(FrozenInstanceError):
            descriptor.action_id = "hijacked"  # type: ignore[misc]
        # `replace` produces a copy; the registry's own copy is untouched.
        replace(descriptor, title="copy")
        self.assertEqual(self.registry.get("public_bio.pubmed_search").title, descriptor.title)

    def test_no_action_claims_verification_or_eligibility(self):
        for action_id in self.registry.list_action_ids():
            d = self.registry.get(action_id)
            self.assertFalse(d.scientific_output_eligible, action_id)
            self.assertNotIn(d.verification_status, ("public_docs_verified", "contract_tested"), action_id)


if __name__ == "__main__":
    unittest.main()
