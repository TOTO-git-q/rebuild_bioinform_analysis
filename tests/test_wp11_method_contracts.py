"""WP-11 tests: MethodContract registry, compatibility, and method plan."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_method_contract
from auto_bioinfo.methods.compatibility import (
    COMPAT_INSUFFICIENT_INFORMATION,
    COMPAT_MISSING_GENE_UNIVERSE,
    COMPAT_NOT_INDEPENDENT,
    COMPAT_PSEUDOREPLICATION,
    PLAN_DRAFTED,
    PLAN_METHOD_NOT_APPLICABLE,
    build_method_plan,
    decision_is_valid,
    evaluate_compatibility,
)
from auto_bioinfo.methods.contract_catalog import CATALOG_METHOD_IDS, build_contract_catalog
from auto_bioinfo.methods.contract_registry import (
    ADMIT_OK,
    ADMIT_REJECTED_FLOATING_REF,
    ADMIT_REJECTED_INCOMPLETE,
    ADMIT_REJECTED_SIGNATURE,
    ImplementationReference,
    MethodRegistry,
    build_default_registry,
    sign_contract,
)


def _bulk_profile(**overrides):
    profile = {
        "dataset_id": "ds_bulk",
        "modality": "bulk_expression_matrix",
        "statistical_unit": "sample",
        "group_sizes": {"a": 3, "b": 3},
        "present_metadata": ["sample_group_labels"],
    }
    profile.update(overrides)
    return profile


def _sq(claim_ceiling="association", subquestion_id="subquestion_abc"):
    return {"subquestion_id": subquestion_id, "claim_ceiling": claim_ceiling}


class CatalogTest(unittest.TestCase):
    def test_all_seven_methods_present_and_contracts_valid(self):
        catalog = build_contract_catalog()
        self.assertEqual(set(catalog), set(CATALOG_METHOD_IDS))
        for method_id, entry in catalog.items():
            self.assertEqual(validate_method_contract(entry.contract_dict()), [], method_id)

    def test_catalog_is_deterministic(self):
        a = build_contract_catalog()
        b = build_contract_catalog()
        self.assertEqual(
            {m: e.contract_dict() for m, e in a.items()},
            {m: e.contract_dict() for m, e in b.items()},
        )

    def test_gene_set_score_capability_capped_below_mechanism(self):
        catalog = build_contract_catalog()
        contract = catalog["gene_set_score"].contract_dict()
        self.assertEqual(contract["claim_capability"], "descriptive")


class RegistryAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.catalog = build_contract_catalog()
        self.entry = self.catalog["bulk_deg"]
        self.contract = self.entry.contract_dict()
        self.impl = ImplementationReference(
            code_commit="abc123",
            container_digest="sha256:deadbeef",
            entrypoint="auto_bioinfo.methods.bulk_deg",
            environment="conda:bulk_deg",
            license="mit",
        )

    def test_admits_complete_signed_active_contract(self):
        reg = MethodRegistry()
        result = reg.register(self.contract, self.entry.rule, self.impl)
        self.assertEqual(result.code, ADMIT_OK)
        self.assertTrue(result.admitted)
        self.assertIsNotNone(reg.active_contract("bulk_deg"))

    def test_floating_latest_reference_rejected(self):
        reg = MethodRegistry()
        bad_impl = ImplementationReference("abc", "latest", "x", "y", "mit")
        result = reg.register(self.contract, self.entry.rule, bad_impl)
        self.assertEqual(result.code, ADMIT_REJECTED_FLOATING_REF)
        self.assertIsNone(reg.active_contract("bulk_deg"))

    def test_incomplete_contract_rejected(self):
        reg = MethodRegistry()
        broken = dict(self.contract)
        broken["supported_modalities"] = []
        result = reg.register(broken, self.entry.rule, self.impl)
        self.assertEqual(result.code, ADMIT_REJECTED_INCOMPLETE)

    def test_tampered_signature_rejected(self):
        reg = MethodRegistry()
        wrong = sign_contract(self.contract, self.impl) + "_tamper"
        result = reg.register(self.contract, self.entry.rule, self.impl, signature=wrong)
        self.assertEqual(result.code, ADMIT_REJECTED_SIGNATURE)

    def test_disabled_version_not_selectable(self):
        reg = build_default_registry()
        self.assertIsNotNone(reg.active_contract("bulk_deg"))
        reg.disable("bulk_deg", self.contract["version"])
        self.assertIsNone(reg.active_contract("bulk_deg"))

    def test_default_registry_has_all_methods(self):
        reg = build_default_registry()
        self.assertEqual(set(reg.active_method_ids()), set(CATALOG_METHOD_IDS))


class CompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.reg = build_default_registry()

    def test_bulk_deg_compatible_on_valid_profile(self):
        d = evaluate_compatibility(self.reg, "bulk_deg", _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "compatible")
        self.assertTrue(decision_is_valid(d))

    def test_cell_level_pseudoreplication_incompatible(self):
        profile = {
            "dataset_id": "ds_sc",
            "modality": "single_cell_expression_matrix",
            "statistical_unit": "cell",
            "group_sizes": {"a": 500, "b": 500},
            "present_metadata": ["donor_labels", "cell_type_labels", "condition_labels"],
        }
        d = evaluate_compatibility(self.reg, "scrna_pseudobulk_deg", profile, _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "incompatible")
        self.assertEqual(d["reason_code"], COMPAT_PSEUDOREPLICATION)
        self.assertTrue(d["blocking_facts"])
        self.assertTrue(decision_is_valid(d))

    def test_scrna_incompatible_without_donor_fixture(self):
        # No donor unit → not compatible (T-11-07 negative path).
        profile = {
            "dataset_id": "ds_sc",
            "modality": "single_cell_expression_matrix",
            "statistical_unit": "sample",
            "group_sizes": {"a": 3, "b": 3},
            "present_metadata": ["donor_labels", "cell_type_labels", "condition_labels"],
        }
        d = evaluate_compatibility(self.reg, "scrna_pseudobulk_deg", profile, _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "incompatible")

    def test_enrichment_without_universe_incompatible(self):
        profile = {
            "dataset_id": "ds_list",
            "modality": "gene_list",
            "statistical_unit": "sample",
            "group_sizes": {"a": 1},
            "present_metadata": ["annotation_database_version"],
            "has_gene_universe": False,
        }
        d = evaluate_compatibility(self.reg, "enrichment", profile, _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "incompatible")
        self.assertEqual(d["reason_code"], COMPAT_MISSING_GENE_UNIVERSE)

    def test_cross_dataset_same_data_not_replication(self):
        profile = {
            "dataset_id": "ds_deg",
            "modality": "deg_results_table",
            "statistical_unit": "sample",
            "group_sizes": {"a": 1},
            "present_metadata": ["dataset_independence", "id_mapping"],
            "independent_datasets": False,
        }
        d = evaluate_compatibility(self.reg, "cross_dataset_concordance", profile, _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "incompatible")
        self.assertEqual(d["reason_code"], COMPAT_NOT_INDEPENDENT)

    def test_unknown_facts_are_insufficient_information(self):
        profile = {"dataset_id": "ds_x", "modality": "", "statistical_unit": ""}
        d = evaluate_compatibility(self.reg, "bulk_deg", profile, _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "insufficient_information")
        self.assertEqual(d["reason_code"], COMPAT_INSUFFICIENT_INFORMATION)
        self.assertTrue(d["missing_facts"])
        self.assertTrue(decision_is_valid(d))

    def test_claim_capability_caps_score_below_mechanism(self):
        profile = _bulk_profile()
        d = evaluate_compatibility(self.reg, "gene_set_score", profile, _sq(claim_ceiling="mechanistic_hypothesis"), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "conditionally_compatible")
        self.assertEqual(d["imposed_claim_ceiling"], "descriptive")
        self.assertTrue(decision_is_valid(d))

    def test_decision_is_deterministic(self):
        d1 = evaluate_compatibility(self.reg, "bulk_deg", _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        d2 = evaluate_compatibility(self.reg, "bulk_deg", _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d1, d2)

    def test_unregistered_method_incompatible(self):
        d = evaluate_compatibility(self.reg, "no_such_method", _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(d["decision"], "incompatible")


class MethodPlanTest(unittest.TestCase):
    def setUp(self):
        self.reg = build_default_registry()

    def test_plan_drafts_over_compatible_only(self):
        plan, decisions = build_method_plan(self.reg, _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(plan["status"], PLAN_DRAFTED)
        self.assertTrue(plan["primary_method_id"])
        # Every candidate produced a decision.
        self.assertEqual(len(decisions), len(self.reg.active_method_ids()))
        # The primary must be in the accepted (compatible) set.
        primary_decision = next(d for d in decisions if d["method_id"] == plan["primary_method_id"])
        self.assertIn(primary_decision["decision"], ("compatible", "conditionally_compatible"))

    def test_no_compatible_method_is_not_applicable(self):
        profile = {
            "dataset_id": "ds_weird",
            "modality": "proteomics_matrix",
            "statistical_unit": "sample",
            "group_sizes": {"a": 3, "b": 3},
            "present_metadata": [],
        }
        plan, decisions = build_method_plan(self.reg, profile, _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(plan["status"], PLAN_METHOD_NOT_APPLICABLE)
        self.assertEqual(plan["primary_method_id"], "")
        self.assertTrue(all(d["decision"] not in ("compatible", "conditionally_compatible") for d in decisions))

    def test_ranking_does_not_change_compatibility(self):
        plan, decisions = build_method_plan(self.reg, _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        # Re-evaluating the primary directly yields the same verdict recorded.
        recorded = next(d for d in decisions if d["method_id"] == plan["primary_method_id"])
        fresh = evaluate_compatibility(self.reg, plan["primary_method_id"], _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(recorded["decision"], fresh["decision"])

    def test_plan_is_deterministic(self):
        p1, _ = build_method_plan(self.reg, _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        p2, _ = build_method_plan(self.reg, _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        self.assertEqual(p1, p2)

    def test_all_decisions_valid(self):
        _, decisions = build_method_plan(self.reg, _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x")
        for d in decisions:
            self.assertTrue(decision_is_valid(d), d.get("reason_code"))


if __name__ == "__main__":
    unittest.main()
