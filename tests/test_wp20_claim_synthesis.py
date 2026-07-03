"""WP-20: bounded claim synthesis + original-question alignment/over-claim audit."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_claim, validate_question_alignment_report
from auto_bioinfo.evidence.claim_synthesis import (
    cap_by_min_evidence,
    min_evidence_satisfied,
    pre_aggregate,
    scope_intersection,
    synthesize_claims,
)
from auto_bioinfo.evidence.question_alignment import audit_alignment, detect_overclaims


def _evidence(
    eid="evidence_item_1",
    relation="supports",
    allowed="association",
    sq="subq_1",
    etype="bulk_rna_differential_expression",
    scope=None,
    replication="single_dataset",
):
    return {
        "evidence_item_id": eid,
        "artifact_id": f"artifact_{eid}",
        "review_status": "negative" if relation in ("opposes", "inconclusive") else "audited",
        "subquestion_ids": [sq],
        "evidence_type": etype,
        "allowed_claim_level": allowed,
        "supports_or_opposes": "opposes" if relation == "opposes" else ("neutral" if relation in ("neutral", "inconclusive") else "supports"),
        "evidence_relation": relation,
        "replication_status": replication,
        "scope": scope or {"species": ["human"], "tissue": ["liver"], "condition": ["tumor", "normal"]},
    }


def _artifact(eid="evidence_item_1"):
    return {"artifact_id": f"artifact_{eid}", "exists": True, "is_placeholder": False, "qc_status": "pass", "expected_by_task_ids": ["task_1"]}


_SUBQ = [{"subquestion_id": "subq_1", "claim_ceiling": "association"}]
_SCOPE = {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]}
_SPEC = {"project_id": "proj_1", "research_spec_id": "spec_1", "max_claim_level": "association"}


class SynthesisTest(unittest.TestCase):
    def test_supporting_evidence_yields_valid_claim(self):
        result = synthesize_claims(evidence_items=[_evidence()], subquestions=_SUBQ, scope_bundle=_SCOPE, project_ceiling="association")
        self.assertEqual(len(result.claims), 1)
        claim = result.claims[0]
        self.assertEqual(claim["claim_level"], "association")
        self.assertEqual(claim["status"], "supports")
        self.assertEqual(validate_claim(claim, max_allowed="association"), [])
        self.assertEqual(claim["created_at"], "")

    def test_claim_capped_by_project_ceiling(self):
        ev = _evidence(allowed="mechanistic_hypothesis")
        result = synthesize_claims(
            evidence_items=[ev],
            subquestions=[{"subquestion_id": "subq_1", "claim_ceiling": "mechanistic_hypothesis"}],
            scope_bundle=_SCOPE,
            project_ceiling="association",
        )
        self.assertEqual(result.claims[0]["claim_level"], "association")

    def test_conflict_downgrades_and_flags(self):
        evs = [_evidence("evidence_item_1", "supports"), _evidence("evidence_item_2", "opposes")]
        result = synthesize_claims(evidence_items=evs, subquestions=_SUBQ, scope_bundle=_SCOPE, project_ceiling="association")
        self.assertEqual(result.claims[0]["status"], "conflicting")
        self.assertTrue(result.conflicts)
        self.assertIn("evidence_item_2", result.claims[0]["opposing_evidence_refs"])

    def test_unanswered_subquestion_recorded(self):
        subq = _SUBQ + [{"subquestion_id": "subq_2", "claim_ceiling": "association"}]
        result = synthesize_claims(evidence_items=[_evidence()], subquestions=subq, scope_bundle=_SCOPE, project_ceiling="association")
        self.assertEqual([u["subquestion_id"] for u in result.unanswered_questions], ["subq_2"])

    def test_null_result_claim_kept(self):
        result = synthesize_claims(evidence_items=[_evidence(relation="neutral")], subquestions=_SUBQ, scope_bundle=_SCOPE, project_ceiling="association")
        self.assertEqual(result.claims[0]["status"], "null_result")
        self.assertEqual(validate_claim(result.claims[0], max_allowed="association"), [])

    def test_min_evidence_gate(self):
        self.assertFalse(min_evidence_satisfied("causal_support", ["bulk_rna"]))
        self.assertTrue(min_evidence_satisfied("association", ["bulk_rna"]))
        self.assertEqual(cap_by_min_evidence("causal_support", ["bulk_rna"]), "association")
        self.assertEqual(cap_by_min_evidence("causal_support", ["intervention"]), "causal_support")

    def test_scope_intersection_forbids_extrapolation(self):
        a = _evidence("evidence_item_1", scope={"species": ["human"], "tissue": ["liver"], "condition": []})
        b = _evidence("evidence_item_2", scope={"species": ["human"], "tissue": ["brain"], "condition": []})
        intersection = scope_intersection([a, b])
        self.assertEqual(intersection["species"], ["human"])
        self.assertEqual(intersection["tissue"], [])  # disjoint tissue collapses

    def test_pre_aggregate_buckets(self):
        evs = [_evidence("e1", "supports"), _evidence("e2", "opposes"), _evidence("e3", "inconclusive")]
        agg = pre_aggregate(evs, ["subq_1"])["subq_1"]
        self.assertEqual(agg.supporting, ["e1"])
        self.assertEqual(agg.opposing, ["e2"])
        self.assertEqual(agg.inconclusive, ["e3"])
        self.assertTrue(agg.to_dict()["has_conflict"])


class OverclaimTest(unittest.TestCase):
    def _claim(self, text, refs=("evidence_item_1",), level="association"):
        return {"claim_id": "claim_1", "text": text, "claim_level": level, "evidence_item_refs": list(refs)}

    def test_causal_language_flagged(self):
        corr = detect_overclaims([self._claim("Gene X causes tumor progression")], [_evidence()])
        self.assertEqual(corr[0]["kind"], "correlation_to_causation")

    def test_protein_language_flagged(self):
        corr = detect_overclaims([self._claim("The gene is secreted into serum")], [_evidence()])
        self.assertEqual(corr[0]["kind"], "rna_to_protein_or_secretion")

    def test_universal_language_flagged(self):
        corr = detect_overclaims([self._claim("This holds universally across all tissues")], [_evidence()])
        self.assertEqual(corr[0]["kind"], "single_cohort_to_universal")

    def test_clean_association_claim_not_flagged(self):
        corr = detect_overclaims([self._claim("At the association level, expression differs between groups")], [_evidence()])
        self.assertEqual(corr, [])


class AlignmentAuditTest(unittest.TestCase):
    def _audit(self, claims):
        return audit_alignment(
            research_spec=_SPEC,
            subquestions=_SUBQ,
            scope_bundle=_SCOPE,
            evidence_items=[_evidence()],
            claims=claims,
            artifact_manifests=[_artifact()],
            qc_reports=[],
            project_ceiling="association",
        )

    def test_clean_claims_approve_and_report_ready(self):
        result = synthesize_claims(evidence_items=[_evidence()], subquestions=_SUBQ, scope_bundle=_SCOPE, project_ceiling="association")
        audit = self._audit(result.claims)
        self.assertEqual(audit["alignment_report"]["final_decision"], "approve")
        self.assertTrue(audit["report_ready"])
        self.assertEqual(validate_question_alignment_report(audit["alignment_report"]), [])

    def test_overclaim_blocks_report(self):
        claim = {
            "claim_id": "claim_bad",
            "text": "Gene X causes tumor progression",
            "claim_level": "association",
            "evidence_item_refs": ["evidence_item_1"],
            "supports_subquestion_ids": ["subq_1"],
            "scope": {"species": ["human"], "tissue": ["liver"], "condition": ["tumor"]},
            "limitations": ["assoc only"],
        }
        audit = self._audit([claim])
        self.assertFalse(audit["report_ready"])
        self.assertEqual(audit["alignment_report"]["final_decision"], "reject")
        kinds = {b["kind"] for b in audit["report_blocking_issues"]}
        self.assertIn("overclaim", kinds)
        self.assertEqual(validate_question_alignment_report(audit["alignment_report"]), [])

    def test_unanswered_subquestion_blocks(self):
        result = synthesize_claims(evidence_items=[_evidence()], subquestions=_SUBQ, scope_bundle=_SCOPE, project_ceiling="association")
        audit = audit_alignment(
            research_spec=_SPEC,
            subquestions=_SUBQ + [{"subquestion_id": "subq_2", "claim_ceiling": "association"}],
            scope_bundle=_SCOPE,
            evidence_items=[_evidence()],
            claims=result.claims,
            artifact_manifests=[_artifact()],
            qc_reports=[],
            project_ceiling="association",
        )
        self.assertFalse(audit["report_ready"])
        kinds = {b["kind"] for b in audit["report_blocking_issues"]}
        self.assertIn("unanswered_subquestion", kinds)

    def test_coverage_is_four_state(self):
        result = synthesize_claims(evidence_items=[_evidence(relation="neutral")], subquestions=_SUBQ, scope_bundle=_SCOPE, project_ceiling="association")
        audit = self._audit(result.claims)
        states = {c["state"] for c in audit["coverage"]}
        self.assertTrue(states <= {"answered", "answered_negative", "unresolved", "unanswered"})
        self.assertIn("answered_negative", states)


if __name__ == "__main__":
    unittest.main()
