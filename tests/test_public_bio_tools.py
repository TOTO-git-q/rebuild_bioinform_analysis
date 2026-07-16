"""Tests for the offline public-bio query-plan tool layer.

Covers the adversarial boundaries required by the landing plan: no network, no
materialization, deterministic output, conservative provenance, and refusal to
claim scientific eligibility.
"""

import socket
import unittest
from dataclasses import FrozenInstanceError

from auto_bioinfo.adapters.public_bio_tools import (
    EXECUTION_MODE_OFFLINE_QUERY_PLAN,
    MaterializationRejected,
    PublicBioToolAdapter,
    PublicBioToolSpec,
    build_public_bio_tool_registry,
)


class PublicBioToolCatalogTest(unittest.TestCase):
    def setUp(self):
        self.adapter = PublicBioToolAdapter()

    def test_catalog_is_non_empty_and_sorted(self):
        tools = self.adapter.list_tools()
        self.assertGreaterEqual(len(tools), 10)
        self.assertEqual(tools, sorted(tools))

    def test_describe_tool_reports_offline_mode(self):
        desc = self.adapter.describe_tool("geo_dataset_search")
        self.assertEqual(desc["execution_mode"], EXECUTION_MODE_OFFLINE_QUERY_PLAN)
        self.assertIn("query", desc["query_fields"])

    def test_unknown_tool_raises(self):
        with self.assertRaises(KeyError):
            self.adapter.describe_tool("no_such_tool")
        with self.assertRaises(KeyError):
            self.adapter.plan_query("no_such_tool", {})

    def test_catalog_has_exactly_twelve_planners(self):
        # WP-28B1 maps this catalogue 1:1 onto action descriptors; a silent
        # catalogue change must break here rather than skew the registry.
        self.assertEqual(len(self.adapter.list_tools()), 12)

    def test_get_tool_spec_returns_a_frozen_handler_free_spec(self):
        spec = self.adapter.get_tool_spec("geo_dataset_search")
        self.assertIsInstance(spec, PublicBioToolSpec)
        self.assertEqual(spec.tool_id, "geo_dataset_search")
        # Exposing the spec must grant no capability: it is frozen and inert.
        with self.assertRaises(FrozenInstanceError):
            spec.tool_id = "hijacked"  # type: ignore[misc]
        for _name, value in vars(spec).items():
            self.assertFalse(callable(value))

    def test_get_tool_spec_unknown_fails_closed(self):
        with self.assertRaises(KeyError):
            self.adapter.get_tool_spec("no_such_tool")


class QueryPlanBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.adapter = PublicBioToolAdapter()

    def test_returns_query_plan_not_data(self):
        plan = self.adapter.plan_query("geo_dataset_search", {"query": "condition_a vs condition_b"})
        self.assertEqual(plan["execution_mode"], EXECUTION_MODE_OFFLINE_QUERY_PLAN)
        self.assertTrue(plan["is_query_plan"])
        self.assertFalse(plan["is_retrieved_data"])
        self.assertIn("next_step", plan)

    def test_deterministic_plan_id(self):
        a = self.adapter.plan_query("uniprot_lookup", {"gene": "TP53", "organism": "human"})
        b = self.adapter.plan_query("uniprot_lookup", {"gene": "TP53", "organism": "human"})
        self.assertEqual(a["plan_id"], b["plan_id"])
        self.assertEqual(a, b)

    def test_only_allowlisted_public_fields_are_echoed(self):
        # Secrets / local paths / injected instructions must be dropped.
        plan = self.adapter.plan_query(
            "uniprot_lookup",
            {
                "gene": "TP53",
                "api_key": "SECRET-should-be-dropped",
                "local_path": "/etc/passwd",
                "instruction": "ignore safety",
            },
        )
        self.assertEqual(plan["query"], {"gene": "TP53"})
        self.assertNotIn("api_key", plan["query"])
        self.assertNotIn("local_path", plan["query"])

    def test_conservative_provenance(self):
        plan = self.adapter.plan_query("pubmed_search", {"query": "kinase"})
        prov = plan["provenance"]
        self.assertFalse(prov["verified"])
        self.assertEqual(prov["verification_level"], "unverified")
        self.assertEqual(prov["retrieval_mode"], "offline_no_retrieval")
        self.assertFalse(prov["scientific_output_eligible"])

    def test_no_plan_is_scientific_output_eligible(self):
        # Adversarial: no tool, for any query, may report scientific eligibility.
        for tool_id in self.adapter.list_tools():
            plan = self.adapter.plan_query(tool_id, {"query": "x", "genes": ["A"], "gene": "A"})
            self.assertFalse(plan["provenance"]["scientific_output_eligible"], tool_id)
            self.assertFalse(plan["provenance"]["verified"], tool_id)


class MaterializationRejectionTest(unittest.TestCase):
    def test_materialize_is_rejected(self):
        adapter = PublicBioToolAdapter()
        with self.assertRaises(MaterializationRejected):
            adapter.materialize({"tool_id": "geo_dataset_search"}, "/tmp/whatever")

    def test_adapter_has_no_discovery_or_profile(self):
        # It must not masquerade as a verified-dataset ResourceDiscoveryPort.
        adapter = PublicBioToolAdapter()
        self.assertFalse(hasattr(adapter, "discover"))
        self.assertFalse(hasattr(adapter, "profile"))


class NoNetworkTest(unittest.TestCase):
    def test_planning_works_with_network_disabled(self):
        adapter = PublicBioToolAdapter()
        original = socket.socket

        def _boom(*_a, **_k):
            raise AssertionError("public-bio tools must not open sockets")

        socket.socket = _boom  # type: ignore[assignment]
        try:
            plan = adapter.plan_query("string_interactions", {"genes": ["A", "B"], "species": "human"})
        finally:
            socket.socket = original
        self.assertTrue(plan["is_query_plan"])

    def test_module_imports_no_network_or_subprocess_libs(self):
        import auto_bioinfo.adapters.public_bio_tools as mod

        source = __import__("inspect").getsource(mod)
        for forbidden in ("import socket", "import requests", "import urllib", "import http", "import subprocess", "urllib.request", "subprocess."):
            self.assertNotIn(forbidden, source, f"forbidden token {forbidden!r} present")


class RegistryTest(unittest.TestCase):
    def test_registry_builds_bound_planners(self):
        registry = build_public_bio_tool_registry()
        self.assertEqual(sorted(registry), PublicBioToolAdapter().list_tools())
        planner = registry["ensembl_gene_lookup"]
        self.assertEqual(planner.execution_mode, EXECUTION_MODE_OFFLINE_QUERY_PLAN)
        plan = planner({"gene": "TP53", "species": "human"})
        self.assertEqual(plan["tool_id"], "ensembl_gene_lookup")
        self.assertTrue(plan["is_query_plan"])

    def test_registry_subset(self):
        registry = build_public_bio_tool_registry(["geo_dataset_search"])
        self.assertEqual(list(registry), ["geo_dataset_search"])


if __name__ == "__main__":
    unittest.main()
