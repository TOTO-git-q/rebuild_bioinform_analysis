"""Tests for the WP-28B1 deterministic biomedical resource router.

Covers the acceptance evidence the work order requires: determinism, the
AgentSpec / risk / claim / approval / verification boundaries, stable rejection
reason codes, explicit capability gaps, and the adversarial proof that routing
performs no execution, no network / subprocess / MCP / LLM / env / filesystem
access, and confers no verification, dataset lock, evidence or claim authority.
"""

import inspect
import json
import unittest

from auto_bioinfo.agent_gateway.action_registry import (
    CATEGORY_LITERATURE,
    PURPOSE_DATASET_DISCOVERY,
    PURPOSE_LITERATURE_DISCOVERY,
    PURPOSE_STRUCTURE_LOOKUP,
    build_default_action_registry,
)
from auto_bioinfo.agent_gateway.resource_router import (
    CODE_AGENT_NOT_ALLOWED,
    CODE_CATEGORY_NOT_PREFERRED,
    CODE_CLAIM_LEVEL_UNSUPPORTED,
    CODE_CONNECTOR_NOT_PREFERRED,
    CODE_NOT_SCIENTIFIC_OUTPUT_ELIGIBLE,
    CODE_OUTPUT_KIND_MISMATCH,
    CODE_PURPOSE_MISMATCH,
    CODE_RISK_ABOVE_MAX,
    CODE_VERIFICATION_INSUFFICIENT,
    GAP_CONNECTOR_INVENTORY_ONLY,
    GAP_NO_ADMISSIBLE_ACTION,
    GAP_NO_SCIENTIFICALLY_ELIGIBLE_ACTION,
    GAP_NO_VERIFIED_ACTION,
    REASON_CODES,
    ResourceRouter,
    RouteRequest,
    RouteRequestError,
    RouteTrace,
    build_default_resource_router,
    route_actions,
)

DISCOVERY_AGENT = "resource_discovery_agent"


def _request(**overrides) -> RouteRequest:
    base = dict(agent_id=DISCOVERY_AGENT, purpose=PURPOSE_DATASET_DISCOVERY)
    base.update(overrides)
    return RouteRequest(**base)


def _reason_for(trace: RouteTrace, action_id: str) -> str:
    for rejected in trace.rejected:
        if rejected.action_id == action_id:
            return rejected.reason_code
    raise AssertionError(f"{action_id} was not rejected")


class RouterDeterminismTest(unittest.TestCase):
    def setUp(self):
        self.router = build_default_resource_router()

    def test_same_request_yields_identical_trace(self):
        a = self.router.route(_request())
        b = self.router.route(_request())
        self.assertEqual(a.trace_id, b.trace_id)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_trace_is_json_serializable_and_stable(self):
        trace = self.router.route(_request())
        payload = json.dumps(trace.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(json.loads(payload)["agent_id"], DISCOVERY_AGENT)

    def test_selection_and_rejection_ordering_is_stable_and_sorted(self):
        trace = self.router.route(_request())
        self.assertEqual(list(trace.selected_action_ids), sorted(trace.selected_action_ids))
        rejected_ids = [r.action_id for r in trace.rejected]
        self.assertEqual(rejected_ids, sorted(rejected_ids))
        # Every registered action is accounted for exactly once.
        self.assertEqual(
            sorted([*trace.selected_action_ids, *rejected_ids]),
            build_default_action_registry().list_action_ids(),
        )

    def test_dataset_discovery_selects_the_three_archive_planners(self):
        trace = self.router.route(_request())
        self.assertEqual(
            list(trace.selected_action_ids),
            ["public_bio.arrayexpress_search", "public_bio.geo_dataset_search", "public_bio.sra_run_search"],
        )
        self.assertEqual(trace.capability_gaps, ())

    def test_route_actions_helper_matches_router(self):
        registry = build_default_action_registry()
        self.assertEqual(route_actions(registry, _request()).trace_id, self.router.route(_request()).trace_id)

    def test_every_rejection_uses_a_declared_reason_code(self):
        for purpose in (PURPOSE_DATASET_DISCOVERY, PURPOSE_LITERATURE_DISCOVERY, PURPOSE_STRUCTURE_LOOKUP):
            trace = self.router.route(_request(purpose=purpose))
            for rejected in trace.rejected:
                self.assertIn(rejected.reason_code, REASON_CODES)
                self.assertTrue(rejected.detail)


class BoundaryEnforcementTest(unittest.TestCase):
    def setUp(self):
        self.router = build_default_resource_router()

    def test_agent_outside_the_allowlist_selects_nothing(self):
        trace = self.router.route(_request(agent_id="result_auditor"))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertIn(GAP_NO_ADMISSIBLE_ACTION, trace.capability_gaps)
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_AGENT_NOT_ALLOWED)

    def test_purpose_mismatch_is_reason_coded(self):
        trace = self.router.route(_request(purpose=PURPOSE_LITERATURE_DISCOVERY))
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_PURPOSE_MISMATCH)
        self.assertEqual(
            list(trace.selected_action_ids),
            ["public_bio.europe_pmc_search", "public_bio.pubmed_search"],
        )

    def test_claim_ceiling_above_action_capability_is_refused(self):
        # The planners top out at 'descriptive'; ask for more.
        trace = self.router.route(_request(required_claim_level="association"))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_CLAIM_LEVEL_UNSUPPORTED)

    def test_risk_ceiling_is_enforced(self):
        trace = self.router.route(_request(max_risk_level="none"))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_RISK_ABOVE_MAX)
        # Raising the ceiling admits them again — the boundary, not a fallback.
        self.assertTrue(self.router.route(_request(max_risk_level="moderate")).selected_action_ids)

    def test_verification_requirement_cannot_be_met_today(self):
        trace = self.router.route(_request(requires_verified_source=True))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_VERIFICATION_INSUFFICIENT)
        self.assertIn(GAP_NO_VERIFIED_ACTION, trace.capability_gaps)

    def test_scientific_eligibility_requirement_cannot_be_met_today(self):
        trace = self.router.route(_request(requires_scientific_output_eligible=True))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_NOT_SCIENTIFIC_OUTPUT_ELIGIBLE)
        self.assertIn(GAP_NO_SCIENTIFICALLY_ELIGIBLE_ACTION, trace.capability_gaps)

    def test_connector_and_category_preferences_filter(self):
        trace = self.router.route(_request(preferred_connector_ids=("omics-archives",)))
        self.assertEqual(len(trace.selected_action_ids), 3)
        trace = self.router.route(_request(purpose=PURPOSE_LITERATURE_DISCOVERY, preferred_connector_ids=("pubmed",)))
        self.assertEqual(list(trace.selected_action_ids), ["public_bio.pubmed_search"])
        self.assertEqual(_reason_for(trace, "public_bio.europe_pmc_search"), CODE_CONNECTOR_NOT_PREFERRED)
        trace = self.router.route(_request(preferred_categories=(CATEGORY_LITERATURE,)))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_CATEGORY_NOT_PREFERRED)

    def test_output_record_kind_modality_need_filters(self):
        trace = self.router.route(_request(required_output_record_kinds=("literature_reference",)))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertEqual(_reason_for(trace, "public_bio.geo_dataset_search"), CODE_OUTPUT_KIND_MISMATCH)
        trace = self.router.route(_request(required_output_record_kinds=("dataset_reference",)))
        self.assertEqual(len(trace.selected_action_ids), 3)

    def test_reserved_approval_gate_is_reported_not_granted(self):
        trace = self.router.route(_request())
        self.assertEqual(trace.reserved_approval_gates, ("network.query_plan",))
        self.assertFalse(trace.requires_live_executor)
        # Reporting a reserved gate is not granting it.
        self.assertFalse(trace.grants_claim)
        self.assertFalse(trace.grants_export_authority)

    def test_preferring_an_inventory_only_connector_is_an_explicit_gap(self):
        trace = self.router.route(_request(preferred_connector_ids=("zinc",)))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertIn(GAP_CONNECTOR_INVENTORY_ONLY, trace.capability_gaps)
        self.assertIn(GAP_NO_ADMISSIBLE_ACTION, trace.capability_gaps)


class FailClosedRequestTest(unittest.TestCase):
    def setUp(self):
        self.router = build_default_resource_router()

    def test_unknown_references_raise_rather_than_guess(self):
        for override in (
            {"agent_id": "ghost_agent"},
            {"agent_id": ""},
            {"purpose": "world_domination"},
            {"max_risk_level": "extreme"},
            {"required_claim_level": "totally_proven"},
            {"preferred_connector_ids": ("no-such-connector",)},
            {"preferred_categories": ("no-such-category",)},
            {"required_output_record_kinds": ("no-such-kind",)},
            {"live_executor_available": "yes"},
            {"requires_verified_source": 1},
            {"preferred_connector_ids": ["omics-archives"]},
            {"approved_gates": ("",)},
            {"approved_gates": ("x" * 500,)},
            {"preferred_connector_ids": tuple(f"c{i}" for i in range(100))},
        ):
            with self.subTest(override=override):
                with self.assertRaises(RouteRequestError):
                    self.router.route(_request(**override))

    def test_non_request_and_non_registry_rejected(self):
        with self.assertRaises(RouteRequestError):
            self.router.route({"agent_id": DISCOVERY_AGENT})  # type: ignore[arg-type]
        with self.assertRaises(RouteRequestError):
            ResourceRouter({"not": "a registry"})  # type: ignore[arg-type]

    def test_empty_selection_is_honest_not_a_fallback(self):
        trace = self.router.route(_request(agent_id="result_auditor"))
        self.assertEqual(trace.selected_action_ids, ())
        self.assertTrue(trace.rejected)
        self.assertIn(GAP_NO_ADMISSIBLE_ACTION, trace.capability_gaps)


class NoAuthorityTest(unittest.TestCase):
    """Adversarial: a route is discovery metadata and nothing more."""

    def setUp(self):
        self.router = build_default_resource_router()

    def test_trace_confers_no_execution_evidence_lock_or_claim(self):
        for request in (_request(), _request(purpose=PURPOSE_LITERATURE_DISCOVERY), _request(agent_id="result_auditor")):
            trace = self.router.route(request)
            self.assertFalse(trace.is_retrieval)
            self.assertFalse(trace.is_execution)
            self.assertFalse(trace.is_evidence)
            self.assertFalse(trace.grants_dataset_lock)
            self.assertFalse(trace.grants_claim)
            self.assertFalse(trace.grants_export_authority)

    def test_selected_actions_stay_unverified_and_ineligible(self):
        registry = build_default_action_registry()
        trace = self.router.route(_request())
        self.assertTrue(trace.selected_action_ids)
        for action_id in trace.selected_action_ids:
            descriptor = registry.get(action_id)
            self.assertEqual(descriptor.verification_status, "unverified", action_id)
            self.assertFalse(descriptor.scientific_output_eligible, action_id)

    def test_router_exposes_no_execution_surface(self):
        for banned in ("run", "execute", "call", "invoke", "fetch", "retrieve", "materialize", "download", "plan_query"):
            self.assertFalse(hasattr(self.router, banned), f"router exposes {banned}()")

    def test_routing_never_mutates_the_request_or_the_registry(self):
        registry = build_default_action_registry()
        before = registry.to_dict()
        request = _request(preferred_connector_ids=("omics-archives",))
        trace = route_actions(registry, request)
        self.assertEqual(registry.to_dict(), before)
        self.assertEqual(trace.request, request)
        self.assertEqual(request.preferred_connector_ids, ("omics-archives",))

    def test_module_imports_no_network_subprocess_mcp_llm_env_or_fs(self):
        import auto_bioinfo.agent_gateway.resource_router as mod

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
            "os.getenv",
            "open(",
            "eval(",
            "exec(",
            "datetime.now",
            "time.time",
            "random.",
            # No LLM / embedding / vector-retrieval machinery may sneak in: this
            # router ranks nothing, it only applies declared boundaries.
            "import openai",
            "import anthropic",
            "sentence_transformers",
            "import faiss",
            ".embed(",
            "llm_provider",
        ):
            self.assertNotIn(forbidden, source, f"forbidden token {forbidden!r} present")

    def test_routing_works_with_sockets_disabled(self):
        import socket

        original = socket.socket

        def _boom(*_a, **_k):
            raise AssertionError("the resource router must not open sockets")

        socket.socket = _boom  # type: ignore[assignment]
        try:
            trace = self.router.route(_request())
        finally:
            socket.socket = original
        self.assertEqual(len(trace.selected_action_ids), 3)


if __name__ == "__main__":
    unittest.main()
