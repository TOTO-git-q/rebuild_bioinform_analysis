"""WP-20 (stages 15-16): bounded claim synthesis + original-question alignment audit.

These tests lock the already-merged evidence-synthesis surfaces against the current
protected base.  They exercise, end to end:

* bounded claim synthesis with the lowest-of-every-ceiling rule (project /
  sub-question / evidence) and the per-level minimum-evidence cap (T-20-01);
* deterministic pre-aggregation into support / oppose / neutral / inconclusive
  buckets and the exposed conflict state (T-20-03);
* conflict downgrade + opposing-ref recording (T-20-08);
* scope intersection that collapses disjoint axes instead of extrapolating (T-20-06);
* unanswered sub-questions kept, never dropped (T-20-07);
* the language over-claim audit (T-20-13) and the four-state coverage /
  report-ready gating (T-20-10, T-20-15).

Test-only slice: no production module is imported for mutation; every assertion
runs against the merged implementation as-is.
"""

from __future__ import annotations

import unittest

from auto_bioinfo.core.schemas import CLAIM_LEVELS
from auto_bioinfo.core.validation import validate_claim, validate_question_alignment_report
from auto_bioinfo.evidence.claim_synthesis import (
    CLAIM_STATUSES,
    cap_by_min_evidence,
    min_evidence_satisfied,
    pre_aggregate,
    scope_intersection,
    synthesize_claims,
)
from auto_bioinfo.evidence.question_alignment import (
    COVERAGE_STATES,
    OVERCLAIM_KINDS,
    audit_alignment,
    detect_overclaims,
)


def make_evidence(
    eid="evidence_item_1",
    relation="supports",
    allowed="association",
    sq="subq_1",
    etype="bulk_rna_differential_expression",
    scope=None,
    replication="single_dataset",
):
    """A single admitted EvidenceItem-shaped dict for the synthesiser/auditor."""
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


def make_artifact(eid="evidence_item_1"):
    return {
        "artifact_id": f"artifact_{eid}",
        "exists": True,
        "is_placeholder": False,
        "qc_status": "pass",
        "expected_by_task_ids": ["task_1"],
    }


SUBQ = [{"subquestion_id": "subq_1", "claim_ceiling": "association"}]
SCOPE = {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]}
SPEC = {"project_id": "proj_1", "research_spec_id": "spec_1", "max_claim_level": "association"}


class ClaimSynthesisTest(unittest.TestCase):
    def test_supporting_evidence_yields_valid_association_claim(self):
        result = synthesize_claims(evidence_items=[make_evidence()], subquestions=SUBQ, scope_bundle=SCOPE, project_ceiling="association")
        self.assertEqual(len(result.claims), 1)
        claim = result.claims[0]
        self.assertEqual(claim["claim_level"], "association")
        self.assertEqual(claim["status"], "supports")
        self.assertIn(claim["status"], CLAIM_STATUSES)
        # Determinism: synthesised claims carry an empty timestamp.
        self.assertEqual(claim["created_at"], "")
        self.assertEqual(claim["evidence_item_refs"], ["evidence_item_1"])
        self.assertEqual(validate_claim(claim, max_allowed="association"), [])

    def test_project_ceiling_caps_claim_level(self):
        # Evidence and sub-question both permit a higher level; the project ceiling wins.
        ev = make_evidence(allowed="mechanistic_hypothesis")
        result = synthesize_claims(
            evidence_items=[ev],
            subquestions=[{"subquestion_id": "subq_1", "claim_ceiling": "mechanistic_hypothesis"}],
            scope_bundle=SCOPE,
            project_ceiling="association",
        )
        self.assertEqual(result.claims[0]["claim_level"], "association")

    def test_subquestion_ceiling_caps_claim_level(self):
        # Project ceiling is high, but the sub-question ceiling is the binding one.
        ev = make_evidence(allowed="mechanistic_hypothesis")
        result = synthesize_claims(
            evidence_items=[ev],
            subquestions=[{"subquestion_id": "subq_1", "claim_ceiling": "descriptive"}],
            scope_bundle=SCOPE,
            project_ceiling="mechanistic_hypothesis",
        )
        self.assertEqual(result.claims[0]["claim_level"], "descriptive")

    def test_evidence_ceiling_caps_claim_level(self):
        # The evidence's own allowed_claim_level is the lowest ceiling -> it binds.
        ev = make_evidence(allowed="descriptive")
        result = synthesize_claims(
            evidence_items=[ev],
            subquestions=[{"subquestion_id": "subq_1", "claim_ceiling": "mechanistic_hypothesis"}],
            scope_bundle=SCOPE,
            project_ceiling="mechanistic_hypothesis",
        )
        self.assertEqual(result.claims[0]["claim_level"], "descriptive")

    def test_min_evidence_gate_blocks_causal_from_rna(self):
        # RNA differential expression can never satisfy the causal-support requirement.
        self.assertFalse(min_evidence_satisfied("causal_support", ["bulk_rna_differential_expression"]))
        self.assertTrue(min_evidence_satisfied("association", ["bulk_rna_differential_expression"]))
        self.assertTrue(min_evidence_satisfied("causal_support", ["intervention"]))
        self.assertEqual(cap_by_min_evidence("causal_support", ["bulk_rna_differential_expression"]), "association")
        self.assertEqual(cap_by_min_evidence("causal_support", ["intervention"]), "causal_support")

    def test_min_evidence_gate_caps_synthesised_claim(self):
        # Every ceiling permits causal_support, but the RNA evidence type cannot, so the
        # minimum-evidence rule caps the synthesised claim down to association.
        ev = make_evidence(allowed="causal_support", etype="bulk_rna_differential_expression")
        result = synthesize_claims(
            evidence_items=[ev],
            subquestions=[{"subquestion_id": "subq_1", "claim_ceiling": "causal_support"}],
            scope_bundle=SCOPE,
            project_ceiling="causal_support",
        )
        claim = result.claims[0]
        self.assertEqual(claim["claim_level"], "association")
        self.assertEqual(validate_claim(claim, max_allowed="causal_support"), [])

    def test_conflict_downgrades_status_and_records_opposing(self):
        evs = [make_evidence("evidence_item_1", "supports"), make_evidence("evidence_item_2", "opposes")]
        result = synthesize_claims(evidence_items=evs, subquestions=SUBQ, scope_bundle=SCOPE, project_ceiling="association")
        claim = result.claims[0]
        self.assertEqual(claim["status"], "conflicting")
        self.assertIn("evidence_item_2", claim["opposing_evidence_refs"])
        self.assertNotIn("evidence_item_2", claim["evidence_item_refs"])
        self.assertTrue(result.conflicts)
        self.assertEqual(result.conflicts[0]["subquestion_id"], "subq_1")
        self.assertTrue(claim["uncertainty"]["has_conflict"])
        # Downgrade never lifts a claim above association here.
        self.assertLessEqual(CLAIM_LEVELS.index(claim["claim_level"]), CLAIM_LEVELS.index("association"))

    def test_unanswered_subquestion_recorded_not_dropped(self):
        subq = SUBQ + [{"subquestion_id": "subq_2", "claim_ceiling": "association"}]
        result = synthesize_claims(evidence_items=[make_evidence()], subquestions=subq, scope_bundle=SCOPE, project_ceiling="association")
        self.assertEqual(len(result.claims), 1)
        self.assertEqual([u["subquestion_id"] for u in result.unanswered_questions], ["subq_2"])
        self.assertTrue(result.unanswered_questions[0]["reason"])

    def test_neutral_evidence_yields_valid_null_result_claim(self):
        result = synthesize_claims(
            evidence_items=[make_evidence(relation="neutral")],
            subquestions=SUBQ,
            scope_bundle=SCOPE,
            project_ceiling="association",
        )
        claim = result.claims[0]
        self.assertEqual(claim["status"], "null_result")
        self.assertEqual(validate_claim(claim, max_allowed="association"), [])

    def test_scope_intersection_collapses_disjoint_axes(self):
        a = make_evidence("evidence_item_1", scope={"species": ["human"], "tissue": ["liver"], "condition": ["tumor"]})
        b = make_evidence("evidence_item_2", scope={"species": ["human"], "tissue": ["brain"], "condition": ["tumor"]})
        intersection = scope_intersection([a, b])
        self.assertEqual(intersection["species"], ["human"])  # shared axis retained
        self.assertEqual(intersection["condition"], ["tumor"])  # shared axis retained
        self.assertEqual(intersection["tissue"], [])  # disjoint tissue collapses, no extrapolation

    def test_pre_aggregate_buckets_and_conflict_state(self):
        evs = [
            make_evidence("e1", "supports"),
            make_evidence("e2", "opposes"),
            make_evidence("e3", "inconclusive"),
            make_evidence("e4", "neutral"),
        ]
        agg = pre_aggregate(evs, ["subq_1"])["subq_1"]
        self.assertEqual(agg.supporting, ["e1"])
        self.assertEqual(agg.opposing, ["e2"])
        self.assertEqual(agg.inconclusive, ["e3"])
        self.assertEqual(agg.neutral, ["e4"])
        self.assertTrue(agg.to_dict()["has_conflict"])

    def test_pre_aggregate_no_conflict_when_only_supporting(self):
        agg = pre_aggregate([make_evidence("e1", "supports")], ["subq_1"])["subq_1"]
        self.assertFalse(agg.to_dict()["has_conflict"])


class OverclaimDetectionTest(unittest.TestCase):
    def _claim(self, text, refs=("evidence_item_1",), level="association"):
        return {"claim_id": "claim_1", "text": text, "claim_level": level, "evidence_item_refs": list(refs)}

    def test_correlation_to_causation_flagged(self):
        corr = detect_overclaims([self._claim("Gene X causes tumor progression")], [make_evidence()])
        self.assertEqual(len(corr), 1)
        self.assertEqual(corr[0]["kind"], "correlation_to_causation")
        self.assertIn(corr[0]["kind"], OVERCLAIM_KINDS)

    def test_rna_to_protein_or_secretion_flagged(self):
        corr = detect_overclaims([self._claim("The gene product is secreted into serum")], [make_evidence()])
        self.assertEqual(corr[0]["kind"], "rna_to_protein_or_secretion")

    def test_single_cohort_to_universal_flagged(self):
        corr = detect_overclaims([self._claim("This holds universally across all tissues")], [make_evidence()])
        self.assertEqual(corr[0]["kind"], "single_cohort_to_universal")

    def test_clean_association_language_not_flagged(self):
        corr = detect_overclaims([self._claim("At the association level, expression differs between the two groups")], [make_evidence()])
        self.assertEqual(corr, [])


class AlignmentAuditTest(unittest.TestCase):
    def _audit(self, claims, subquestions=None):
        return audit_alignment(
            research_spec=SPEC,
            subquestions=subquestions or SUBQ,
            scope_bundle=SCOPE,
            evidence_items=[make_evidence()],
            claims=claims,
            artifact_manifests=[make_artifact()],
            qc_reports=[],
            project_ceiling="association",
        )

    def test_clean_claims_approve_and_report_ready(self):
        result = synthesize_claims(evidence_items=[make_evidence()], subquestions=SUBQ, scope_bundle=SCOPE, project_ceiling="association")
        audit = self._audit(result.claims)
        self.assertEqual(audit["alignment_report"]["final_decision"], "approve")
        self.assertTrue(audit["report_ready"])
        self.assertEqual(audit["report_blocking_issues"], [])
        self.assertEqual(validate_question_alignment_report(audit["alignment_report"]), [])

    def test_overclaim_blocks_report_readiness(self):
        claim = {
            "claim_id": "claim_bad",
            "text": "Gene X causes tumor progression",
            "claim_level": "association",
            "evidence_item_refs": ["evidence_item_1"],
            "supports_subquestion_ids": ["subq_1"],
            "scope": {"species": ["human"], "tissue": ["liver"], "condition": ["tumor"]},
            "limitations": ["association-level evidence only"],
        }
        audit = self._audit([claim])
        self.assertFalse(audit["report_ready"])
        self.assertEqual(audit["alignment_report"]["final_decision"], "reject")
        kinds = {b["kind"] for b in audit["report_blocking_issues"]}
        self.assertIn("overclaim", kinds)
        self.assertEqual(validate_question_alignment_report(audit["alignment_report"]), [])

    def test_unanswered_subquestion_blocks_report_readiness(self):
        result = synthesize_claims(evidence_items=[make_evidence()], subquestions=SUBQ, scope_bundle=SCOPE, project_ceiling="association")
        audit = self._audit(result.claims, subquestions=SUBQ + [{"subquestion_id": "subq_2", "claim_ceiling": "association"}])
        self.assertFalse(audit["report_ready"])
        kinds = {b["kind"] for b in audit["report_blocking_issues"]}
        self.assertIn("unanswered_subquestion", kinds)

    def test_coverage_states_are_bounded_four_state(self):
        result = synthesize_claims(
            evidence_items=[make_evidence(relation="neutral")],
            subquestions=SUBQ,
            scope_bundle=SCOPE,
            project_ceiling="association",
        )
        audit = self._audit(result.claims)
        states = {c["state"] for c in audit["coverage"]}
        self.assertTrue(states <= set(COVERAGE_STATES))
        self.assertEqual(set(COVERAGE_STATES), {"answered", "answered_negative", "unresolved", "unanswered"})
        # A kept null-result claim is answered_negative, not silently dropped.
        self.assertIn("answered_negative", states)

    def test_answered_state_for_supporting_claim(self):
        result = synthesize_claims(evidence_items=[make_evidence()], subquestions=SUBQ, scope_bundle=SCOPE, project_ceiling="association")
        audit = self._audit(result.claims)
        states = {c["state"] for c in audit["coverage"]}
        self.assertEqual(states, {"answered"})


if __name__ == "__main__":
    unittest.main()
