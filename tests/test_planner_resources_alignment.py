import unittest

from auto_bioinfo.adapters.offline_planner import OfflineDeterministicPlanner
from auto_bioinfo.core.alignment_auditor import audit_question_alignment
from tests._helpers import fixture_adapter


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.planner = OfflineDeterministicPlanner()

    def test_extracts_comparison_groups(self):
        spec = self.planner.normalize_question("p", "genes between condition_a and condition_b in tissue_x")
        self.assertEqual(spec["comparison_groups"], ["condition_a", "condition_b"])
        self.assertEqual(spec["tissue"], "tissue_x")

    def test_does_not_invent_unstated_organism(self):
        spec = self.planner.normalize_question("p", "genes between condition_a and condition_b")
        self.assertEqual(spec["organism"], "")
        self.assertTrue(any("rganism" in q for q in spec["open_questions"]))

    def test_deterministic(self):
        a = self.planner.normalize_question("p", "condition_a vs condition_b")
        b = self.planner.normalize_question("p", "condition_a vs condition_b")
        self.assertEqual(a["research_spec_id"], b["research_spec_id"])


class ResourceAdapterTest(unittest.TestCase):
    def test_discovers_a_verified_non_mock_dataset(self):
        adapter = fixture_adapter()
        candidates = adapter.discover({"project_id": "p"}, {"evidence_plan_id": "ep"})
        self.assertTrue(candidates[0]["verified"])
        self.assertNotIn(candidates[0]["source_status"], {"mock", "mock_placeholder", "placeholder"})
        profile = adapter.profile(candidates[0])
        self.assertEqual(profile["modality"], "bulk_expression_matrix")


class AlignmentTest(unittest.TestCase):
    def _ctx(self, claim_level="association", scope=None):
        scope = scope or {"species": [], "tissue": ["tissue_x"], "condition": ["condition_a", "condition_b"]}
        rs = {"project_id": "p", "research_spec_id": "rs1", "max_claim_level": "association"}
        sub = {"subquestion_id": "sq1", "question": "?"}
        ev = {"evidence_item_id": "ev1", "artifact_id": "art1", "review_status": "audited"}
        art = {"artifact_id": "art1", "exists": True, "is_placeholder": False, "qc_status": "pass", "expected_by_task_ids": ["t1"]}
        claim = {
            "claim_id": "c1",
            "claim_level": claim_level,
            "scope": scope,
            "supports_subquestion_ids": ["sq1"],
            "evidence_item_refs": ["ev1"],
            "limitations": [],
        }
        return rs, [sub], {"species": [], "tissues": ["tissue_x"], "conditions": ["condition_a", "condition_b"]}, [ev], [claim], [art]

    def test_approves_well_formed_claim(self):
        rs, subs, scope, ev, claims, art = self._ctx()
        rep = audit_question_alignment(
            research_spec=rs,
            subquestions=subs,
            scope_bundle=scope,
            evidence_item_refs=ev,
            claims=claims,
            artifact_manifests=art,
            qc_reports=[],
            max_claim_level="association",
        )
        self.assertEqual(rep["final_decision"], "approve")

    def test_rejects_overclaim(self):
        rs, subs, scope, ev, claims, art = self._ctx(claim_level="causal_support")
        rep = audit_question_alignment(
            research_spec=rs,
            subquestions=subs,
            scope_bundle=scope,
            evidence_item_refs=ev,
            claims=claims,
            artifact_manifests=art,
            qc_reports=[],
            max_claim_level="association",
        )
        self.assertEqual(rep["final_decision"], "reject")
        self.assertTrue(rep["claim_ceiling_violations"])

    def test_rejects_scope_drift(self):
        rs, subs, scope, ev, claims, art = self._ctx(scope={"species": ["mouse"], "tissue": ["tissue_z"], "condition": ["condition_a"]})
        rep = audit_question_alignment(
            research_spec=rs,
            subquestions=subs,
            scope_bundle=scope,
            evidence_item_refs=ev,
            claims=claims,
            artifact_manifests=art,
            qc_reports=[],
            max_claim_level="association",
        )
        self.assertEqual(rep["final_decision"], "reject")


if __name__ == "__main__":
    unittest.main()
