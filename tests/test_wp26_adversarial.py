"""WP-26 — adversarial / negative tests: every pre-set error hits the right gate.

Covers the required adversarial cases:
* off-topic question rejected,
* unauthorized egress blocked,
* method not applicable,
* unverifiable resource refused,
* insufficient-data legal exit (no fabricated claim),
* evidence refusal for a QC-failed / non-verified artifact,
* over-claim blocked (silent cap + alignment reject + claim-lint),
* conflicting-evidence retained,
* cycle / coverage replan,
* capability-layer materialization denied.
"""

from __future__ import annotations

import tempfile
import unittest

from auto_bioinfo.adapters.capability_registry import assert_no_executable_grants, resolve_decision
from auto_bioinfo.adapters.public_bio_tools import MaterializationRejected, PublicBioToolAdapter
from auto_bioinfo.core.validation import validate_workflow_plan
from auto_bioinfo.evidence.admission import admit_evidence
from auto_bioinfo.evidence.claim_synthesis import cap_by_min_evidence, synthesize_claims
from auto_bioinfo.evidence.question_alignment import audit_alignment, detect_overclaims
from auto_bioinfo.methods.compatibility import build_method_plan
from auto_bioinfo.methods.contract_registry import build_default_registry
from auto_bioinfo.reporting.claim_lint import lint_report_language
from auto_bioinfo.routes.bulk_rnaseq import run_bulk_rnaseq_route
from auto_bioinfo.routes.route_run import (
    TERMINAL_EGRESS_BLOCKED,
    TERMINAL_INSUFFICIENT_DATA,
    TERMINAL_METHOD_NOT_APPLICABLE,
    TERMINAL_NEEDS_CLARIFICATION,
    TERMINAL_UNVERIFIABLE_RESOURCE,
)
from auto_bioinfo.workflow.dag_compiler import DIAG_UNCOVERED_SUBQUESTION, compile_workflow


def _route(overrides=None, question=None):
    with tempfile.TemporaryDirectory() as d:
        kw = {"workspace": d}
        if overrides is not None:
            kw["overrides"] = overrides
        if question is not None:
            return run_bulk_rnaseq_route(question, **kw)
        return run_bulk_rnaseq_route(**kw)


class RouteLevelAdversarialTest(unittest.TestCase):
    def test_off_topic_question_rejected_no_claim(self):
        run = _route(question="What is the weather in Paris tomorrow?")
        self.assertEqual(run.terminal_status, TERMINAL_NEEDS_CLARIFICATION)
        self.assertEqual(run.claims, [])
        self.assertEqual(run.stage("intake_normalize").status, "stopped")

    def test_unauthorized_egress_blocked(self):
        run = _route(overrides={"force_egress": True})
        self.assertEqual(run.terminal_status, TERMINAL_EGRESS_BLOCKED)
        self.assertEqual(run.claims, [])
        self.assertEqual(run.stage("authorization").status, "stopped")

    def test_method_not_applicable(self):
        run = _route(overrides={"wrong_modality": True})
        self.assertEqual(run.terminal_status, TERMINAL_METHOD_NOT_APPLICABLE)
        self.assertEqual(run.claims, [])

    def test_unverifiable_resource_refused(self):
        run = _route(overrides={"break_verification": True})
        self.assertEqual(run.terminal_status, TERMINAL_UNVERIFIABLE_RESOURCE)
        self.assertEqual(run.claims, [])
        self.assertEqual(run.stage("verification").status, "stopped")

    def test_insufficient_data_legal_exit(self):
        run = _route(overrides={"limit_group_size": 1})
        self.assertEqual(run.terminal_status, TERMINAL_INSUFFICIENT_DATA)
        # a legal exit, never a fabricated claim
        self.assertEqual(run.claims, [])
        self.assertEqual(run.evidence_items, [])


class MethodPlanNotApplicableTest(unittest.TestCase):
    def test_bulk_deg_on_single_cell_unit_is_incompatible(self):
        reg = build_default_registry()
        # cell-level statistical unit -> pseudo-replication -> incompatible.
        profile = {
            "dataset_id": "ds",
            "modality": "bulk_expression_matrix",
            "statistical_unit": "cell",
            "group_sizes": {"a": 3, "b": 3},
            "present_metadata": ["sample_group_labels"],
        }
        sq = {"subquestion_id": "sq_1", "claim_ceiling": "association"}
        plan, _ = build_method_plan(reg, profile, sq, evidence_plan_id="ep", candidate_method_ids=["bulk_deg"])
        self.assertEqual(plan["status"], "method_not_applicable")
        self.assertEqual(plan["primary_method_id"], "")


class EvidenceRefusalTest(unittest.TestCase):
    def _inputs(self, qc_report):
        return {
            "result_table": [
                {"gene": f"G{i}", "log2_fold_change": 2.0 if i < 8 else 0.1, "fdr": 0.001 if i < 8 else 0.5, "significant": i < 8} for i in range(10)
            ],
            "method_result": {"status": "succeeded", "task_run_id": "tr_1", "group_a": "tumor", "group_b": "normal", "adequately_powered": True},
            "artifact_manifest": {"artifact_id": "art_1", "exists": True, "is_placeholder": False, "checksum_sha256": "abc"},
            "qc_report": qc_report,
            "dataset_profile": {"dataset_id": "ds_1", "known_limitations": []},
            "scope_bundle": {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]},
            "subquestion": {"subquestion_id": "sq_1", "claim_ceiling": "association", "expected_direction": "up"},
            "contract": {"claim_capability": "association", "parameters": {"significance_alpha": 0.05, "log2fc_threshold": 1.0}, "version": "v1"},
            "project_ceiling": "association",
        }

    def test_qc_failed_artifact_is_refused_even_with_many_significant(self):
        out = admit_evidence(**self._inputs({"qc_report_id": "qc_2", "decision": "REJECT", "overall_status": "fail"}))
        self.assertFalse(out.admitted)
        self.assertEqual(out.reason_code, "QC_NOT_PASSED")
        self.assertIsNotNone(out.non_admissible_marker)
        self.assertFalse(out.non_admissible_marker["is_formal_evidence"])

    def test_qc_passed_artifact_is_admitted(self):
        out = admit_evidence(**self._inputs({"qc_report_id": "qc_1", "decision": "PASS", "overall_status": "pass"}))
        self.assertTrue(out.admitted)


class OverClaimBlockedTest(unittest.TestCase):
    _SCOPE = {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]}

    def _evidence(self, allowed_level):
        return {
            "evidence_item_id": "ev_1",
            "artifact_id": "art_1",
            "review_status": "audited",
            "subquestion_ids": ["sq_1"],
            "source_dataset_ids": ["ds_1"],
            "source_task_run_ids": ["tr_1"],
            "observation": "genes differ",
            "effect_summary": {"n_genes": 10, "n_significant": 4, "top_significant_genes": ["G1"], "max_abs_log2_fold_change": 2.0},
            "uncertainty": {},
            "evidence_type": "bulk_rna_differential_expression",
            "scope": {"species": ["human"], "tissue": ["liver"], "condition": ["tumor", "normal"]},
            "qc_status": "pass",
            "allowed_claim_level": allowed_level,
            "supports_or_opposes": "supports",
            "evidence_relation": "supports",
            "replication_status": "single_dataset",
            "limitations": ["assoc only"],
        }

    def test_claim_silently_capped_to_project_ceiling(self):
        # Evidence *claims* a high level, but the project ceiling is association.
        res = synthesize_claims(
            evidence_items=[self._evidence("mechanistic_hypothesis")],
            subquestions=[{"subquestion_id": "sq_1", "claim_ceiling": "association"}],
            scope_bundle=self._SCOPE,
            project_ceiling="association",
        )
        self.assertTrue(res.claims)
        self.assertEqual(res.claims[0]["claim_level"], "association")

    def test_min_evidence_rule_caps_causal_without_intervention(self):
        # RNA-association evidence can never buy a causal-level claim.
        self.assertEqual(cap_by_min_evidence("causal_support", ["bulk_rna"]), "association")

    def test_alignment_rejects_causal_language_over_association_evidence(self):
        claim = {
            "claim_id": "claim_bad",
            "text": "Gene X causes tumor progression",
            "claim_level": "association",
            "evidence_item_refs": ["ev_1"],
            "supports_subquestion_ids": ["sq_1"],
            "scope": {"species": ["human"], "tissue": ["liver"], "condition": ["tumor"]},
            "limitations": ["assoc only"],
        }
        audit = audit_alignment(
            research_spec={"project_id": "p", "research_spec_id": "rs_1", "max_claim_level": "association"},
            subquestions=[{"subquestion_id": "sq_1", "claim_ceiling": "association"}],
            scope_bundle=self._SCOPE,
            evidence_items=[self._evidence("association")],
            claims=[claim],
            artifact_manifests=[{"artifact_id": "art_1", "exists": True, "is_placeholder": False, "qc_status": "pass", "expected_by_task_ids": []}],
            qc_reports=[],
            project_ceiling="association",
        )
        self.assertFalse(audit["report_ready"])
        self.assertEqual(audit["alignment_report"]["final_decision"], "reject")
        self.assertIn("overclaim", {b["kind"] for b in audit["report_blocking_issues"]})

    def test_claim_lint_flags_over_claim_language(self):
        claim = {"claim_id": "c1", "text": "This gene causes tumor growth", "claim_level": "association", "evidence_item_refs": ["ev_1"]}
        lint = lint_report_language([claim], [self._evidence("association")])
        self.assertTrue(lint["blocking"])
        self.assertTrue(lint["findings"])

    def test_detect_overclaims_finds_rna_to_protein(self):
        claim = {
            "claim_id": "c1",
            "text": "The protein is secreted at higher levels",
            "claim_level": "association",
            "evidence_item_refs": ["ev_1"],
            "supports_subquestion_ids": ["sq_1"],
        }
        corrections = detect_overclaims([claim], [self._evidence("association")])
        self.assertTrue(corrections)


class ConflictingEvidenceTest(unittest.TestCase):
    _SCOPE = {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]}

    def _ev(self, eid, direction):
        return {
            "evidence_item_id": eid,
            "artifact_id": f"art_{eid}",
            "review_status": "audited",
            "subquestion_ids": ["sq_1"],
            "source_dataset_ids": [f"ds_{eid}"],
            "source_task_run_ids": [f"tr_{eid}"],
            "observation": "genes differ",
            "effect_summary": {"n_genes": 10, "n_significant": 4, "top_significant_genes": ["G1"], "max_abs_log2_fold_change": 2.0},
            "uncertainty": {},
            "evidence_type": "bulk_rna_differential_expression",
            "scope": {"species": ["human"], "tissue": ["liver"], "condition": ["tumor", "normal"]},
            "qc_status": "pass",
            "allowed_claim_level": "association",
            "supports_or_opposes": direction,
            "evidence_relation": direction,
            "replication_status": "multi_dataset",
            "limitations": [],
        }

    def test_conflicting_evidence_is_kept_and_downgraded(self):
        res = synthesize_claims(
            evidence_items=[self._ev("a", "supports"), self._ev("b", "opposes")],
            subquestions=[{"subquestion_id": "sq_1", "claim_ceiling": "association"}],
            scope_bundle=self._SCOPE,
            project_ceiling="association",
        )
        self.assertTrue(res.claims)
        self.assertEqual(res.claims[0]["status"], "conflicting")


class CycleAndCoverageReplanTest(unittest.TestCase):
    def test_cyclic_plan_is_detected(self):
        plan = {
            "schema_version": "v5.canonical/0.1",
            "workflow_name": "cyclic",
            "task_ids": ["a", "b"],
            "dependencies": [["a", "b"], ["b", "a"]],
        }
        errors = validate_workflow_plan(plan)
        self.assertTrue(any("cycle" in e.lower() for e in errors))

    def test_uncovered_subquestion_forces_replan(self):
        from auto_bioinfo.methods.compatibility import build_method_plan as _bmp

        reg = build_default_registry()
        profile = {
            "dataset_id": "ds",
            "modality": "bulk_expression_matrix",
            "statistical_unit": "sample",
            "group_sizes": {"a": 3, "b": 3},
            "present_metadata": ["sample_group_labels"],
        }
        sq = {"subquestion_id": "sq_covered", "claim_ceiling": "association"}
        mp, _ = _bmp(reg, profile, sq, evidence_plan_id="ep", candidate_method_ids=["bulk_deg"])
        plans = [{"subquestion": sq, "method_plan": mp, "manifest_inputs": ["input_counts"]}]
        compiled = compile_workflow(reg, plans, project_id="proj", required_subquestion_ids=["sq_covered", "sq_missing"])
        self.assertFalse(compiled.compiled)
        self.assertIn(DIAG_UNCOVERED_SUBQUESTION, {d["code"] for d in compiled.diagnostics})


class CapabilityBoundaryTest(unittest.TestCase):
    def test_dataset_materialization_is_denied(self):
        decision = resolve_decision("grant_dataset_materialization")
        self.assertEqual(decision["decision"], "deny")
        self.assertFalse(decision["executable"])

    def test_no_executable_grants_exist(self):
        self.assertTrue(assert_no_executable_grants())

    def test_public_bio_tool_refuses_materialization(self):
        adapter = PublicBioToolAdapter()
        with self.assertRaises(MaterializationRejected):
            adapter.materialize("geo_dataset_search")

    def test_query_plan_drops_sensitive_local_path(self):
        adapter = PublicBioToolAdapter()
        plan = adapter.plan_query("geo_dataset_search", {"query": "tumor", "organism": "human", "local_path": "/etc/secret"})
        self.assertNotIn("local_path", plan["query"])
        self.assertFalse(plan["is_retrieved_data"])


if __name__ == "__main__":
    unittest.main()
