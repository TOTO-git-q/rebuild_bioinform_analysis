"""Unit tests for the local offline Evidence Planning command (WP-07 / T-07-06..08).

Covers, for the bounded local/offline Evidence Planning command over synthetic toy
sub-questions and specs only (no real user/research content, no real dataset /
accession / PMID / DOI, no external LLM/provider/ontology/search/network call, no
persistence, no event, no granted approval, no project stage transition):

- a toy sub-question with an explicit ``evidence_type`` → an inert
  ``evidence_plan_drafted`` outcome carrying an ``EvidencePlan`` *draft*
  (``status == "draft"``, ``created_at == ""``) with derived generic evidence axes,
  a negative + conflicting strategy, a minimum-replication descriptor, stop
  conditions + a legal fallback exit, and the sub-question linked back (T-07-06..08),
- the max claim level is capped at the most restrictive of the sub-question and
  parent-spec claim ceilings (T-07-06),
- a directive defining only positive evidence (missing the negative and/or the
  conflicting strategy) → ``positive_only_rejected`` (T-07-07),
- a sub-question stating no evidence intent → ``missing_required_field`` (T-07-06),
- a directive with no stop condition and no fallback route → ``no_stop_condition``
  (T-07-08),
- malformed inputs (a non-mapping sub-question, a missing research_spec_id, an
  invalid claim level, a non-mapping directive, a bad spec) fail closed,
- the planner path is byte-deterministic and works with the network blocked (it
  never performs network/env/provider/ontology/search access),
- inputs (the sub-question, the spec, the directive) are never mutated,
- the produced ``EvidencePlan`` draft passes :func:`validate_evidence_plan`, with the
  bounded status + reason-code vocabulary and deterministic serialisation.
"""

import copy
import socket
import unittest

from auto_bioinfo.core.schemas import CLAIM_LEVELS, EvidencePlan, ResearchSpec, SubQuestion
from auto_bioinfo.core.validation import validate_evidence_plan
from auto_bioinfo.planning.evidence_planning import (
    CODE_CLAIM_LEVEL_MALFORMED,
    CODE_DIRECTIVE_MALFORMED,
    CODE_EVIDENCE_PLAN_DRAFTED,
    CODE_MISSING_EVIDENCE_AXIS,
    CODE_MISSING_REQUIRED_FIELD,
    CODE_NO_STOP_CONDITION,
    CODE_POSITIVE_ONLY_REJECTED,
    CODE_SPEC_MALFORMED,
    CODE_SUBQUESTION_MALFORMED,
    DRAFT_STATUS,
    REASON_CODES,
    STATUS_EVIDENCE_PLAN_DRAFTED,
    STATUS_MISSING_REQUIRED_FIELD,
    STATUS_NO_STOP_CONDITION,
    STATUS_POSITIVE_ONLY_REJECTED,
    STATUS_REJECTED_MALFORMED,
    STATUSES,
    EvidencePlanResult,
    plan_evidence,
)

RESEARCH_SPEC_ID = "rs_demo_01"


def _subquestion(**overrides):
    """A synthetic inert draft SubQuestion object."""
    base = dict(
        research_spec_id=RESEARCH_SPEC_ID,
        question="Are gene set A markers differentially expressed between the two synthetic groups?",
        evidence_type="transcriptomic",
        purpose="differential_expression",
        claim_ceiling="association",
        status=DRAFT_STATUS,
    )
    base.update(overrides)
    return SubQuestion(**base)


def _spec(**overrides):
    """A synthetic inert draft ResearchSpec object supplying a claim ceiling."""
    base = dict(project_id="proj_demo_01", research_question="A synthetic toy research question", status=DRAFT_STATUS)
    base.update(overrides)
    return ResearchSpec(**base)


class EvidencePlanDraftedTests(unittest.TestCase):
    def test_explicit_evidence_type_yields_inert_plan(self):
        result = plan_evidence(_subquestion())
        self.assertEqual(result.status, STATUS_EVIDENCE_PLAN_DRAFTED)
        self.assertEqual(result.reason_code, CODE_EVIDENCE_PLAN_DRAFTED)
        self.assertTrue(result.plan_drafted)
        plan = result.evidence_plan
        self.assertIsNotNone(plan)
        # Axes are generic evidence-type descriptors derived from the explicit intent.
        self.assertIn("transcriptomic_differential", plan["evidence_axes"])
        self.assertTrue(all("dataset" not in a.lower() for a in plan["evidence_axes"]))
        # T-07-07: a negative AND a conflicting strategy are present.
        self.assertTrue(plan["negative_evidence_strategy"].strip())
        self.assertTrue(result.negative_evidence_strategy.strip())
        self.assertTrue(result.conflicting_evidence_strategy.strip())
        self.assertTrue(any("conflicting_evidence_strategy" in g for g in plan["planned_gaps"]))
        # T-07-08: stop conditions + a legal fallback exit are present.
        self.assertTrue(plan["stop_conditions"])
        self.assertTrue(result.fallback_route.strip())
        self.assertTrue(any("fallback_route" in s for s in plan["stop_conditions"]))
        # T-07-06: a minimum-replication descriptor and the back-link are present.
        self.assertTrue(plan["minimum_replication"])
        self.assertEqual(plan["subquestion_ids"], [_subquestion().to_dict()["subquestion_id"]])
        self.assertEqual(plan["research_spec_id"], RESEARCH_SPEC_ID)
        # Inert + deterministic: a draft with no wall-clock timestamp.
        self.assertEqual(plan["status"], DRAFT_STATUS)
        self.assertEqual(plan["created_at"], "")
        # The produced plan is internally valid.
        self.assertEqual(validate_evidence_plan(plan), [])

    def test_unknown_evidence_type_normalised_to_generic_axis(self):
        result = plan_evidence(_subquestion(evidence_type="Some Novel Assay", purpose=""))
        self.assertEqual(result.reason_code, CODE_EVIDENCE_PLAN_DRAFTED)
        self.assertEqual(result.evidence_plan["evidence_axes"], ["some_novel_assay_evidence"])

    def test_axes_fall_back_to_purpose_when_no_evidence_type(self):
        result = plan_evidence(_subquestion(evidence_type="", purpose="coexpression"))
        self.assertEqual(result.reason_code, CODE_EVIDENCE_PLAN_DRAFTED)
        self.assertIn("coexpression_network", result.evidence_plan["evidence_axes"])

    def test_accepts_plain_dict_subquestion(self):
        result = plan_evidence(_subquestion().to_dict())
        self.assertTrue(result.plan_drafted)


class ClaimCeilingCappingTests(unittest.TestCase):
    def test_capped_at_parent_spec_ceiling(self):
        # Sub-question wants a high ceiling, but the parent spec caps it low.
        subq = _subquestion(claim_ceiling="causal_support")
        spec = _spec(claim_ceiling="association")
        result = plan_evidence(subq, spec)
        self.assertTrue(result.plan_drafted)
        self.assertEqual(result.evidence_plan["max_claim_level"], "association")

    def test_capped_at_subquestion_ceiling_when_lower(self):
        subq = _subquestion(claim_ceiling="descriptive")
        spec = _spec(claim_ceiling="mechanistic_hypothesis")
        result = plan_evidence(subq, spec)
        self.assertEqual(result.evidence_plan["max_claim_level"], "descriptive")

    def test_spec_max_claim_level_used_when_no_claim_ceiling(self):
        subq = _subquestion(claim_ceiling="causal_support")
        spec = _spec(claim_ceiling="", max_claim_level="co_expression")
        result = plan_evidence(subq, spec)
        self.assertEqual(result.evidence_plan["max_claim_level"], "co_expression")

    def test_ceiling_never_exceeds_a_valid_level(self):
        result = plan_evidence(_subquestion(claim_ceiling="association"))
        self.assertIn(result.evidence_plan["max_claim_level"], CLAIM_LEVELS)


class PositiveOnlyRejectedTests(unittest.TestCase):
    def test_missing_negative_strategy_rejected(self):
        directive = {"negative_evidence_strategy": ""}
        result = plan_evidence(_subquestion(), directive=directive)
        self.assertEqual(result.status, STATUS_POSITIVE_ONLY_REJECTED)
        self.assertEqual(result.reason_code, CODE_POSITIVE_ONLY_REJECTED)
        self.assertIsNone(result.evidence_plan)

    def test_missing_conflicting_strategy_rejected(self):
        directive = {"conflicting_evidence_strategy": "   "}
        result = plan_evidence(_subquestion(), directive=directive)
        self.assertEqual(result.reason_code, CODE_POSITIVE_ONLY_REJECTED)
        self.assertIsNone(result.evidence_plan)


class MissingRequiredFieldTests(unittest.TestCase):
    def test_no_evidence_intent_fails_closed(self):
        result = plan_evidence(_subquestion(evidence_type="", purpose=""))
        self.assertEqual(result.status, STATUS_MISSING_REQUIRED_FIELD)
        self.assertEqual(result.reason_code, CODE_MISSING_EVIDENCE_AXIS)
        self.assertIsNone(result.evidence_plan)

    def test_blank_minimum_replication_fails_closed(self):
        directive = {"minimum_replication": {}}
        result = plan_evidence(_subquestion(), directive=directive)
        self.assertEqual(result.status, STATUS_MISSING_REQUIRED_FIELD)
        self.assertEqual(result.reason_code, CODE_MISSING_REQUIRED_FIELD)
        self.assertIsNone(result.evidence_plan)


class NoStopConditionTests(unittest.TestCase):
    def test_no_stop_condition_and_no_fallback_fails_closed(self):
        directive = {"stop_conditions": [], "fallback_route": ""}
        result = plan_evidence(_subquestion(), directive=directive)
        self.assertEqual(result.status, STATUS_NO_STOP_CONDITION)
        self.assertEqual(result.reason_code, CODE_NO_STOP_CONDITION)
        self.assertIsNone(result.evidence_plan)

    def test_fallback_alone_is_a_legal_exit(self):
        directive = {"stop_conditions": [], "fallback_route": "insufficient_evidence -> mark_not_answerable"}
        result = plan_evidence(_subquestion(), directive=directive)
        self.assertTrue(result.plan_drafted)


class MalformedInputTests(unittest.TestCase):
    def test_non_mapping_subquestion_rejected(self):
        result = plan_evidence(42)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_SUBQUESTION_MALFORMED)

    def test_missing_research_spec_id_rejected(self):
        result = plan_evidence({"question": "q?", "subquestion_id": "subq_x", "evidence_type": "transcriptomic"})
        self.assertEqual(result.reason_code, CODE_SUBQUESTION_MALFORMED)

    def test_missing_subquestion_id_rejected(self):
        result = plan_evidence({"research_spec_id": RESEARCH_SPEC_ID, "evidence_type": "transcriptomic"})
        self.assertEqual(result.reason_code, CODE_SUBQUESTION_MALFORMED)

    def test_invalid_subquestion_claim_ceiling_rejected(self):
        result = plan_evidence(_subquestion(claim_ceiling="not_a_level"))
        self.assertEqual(result.reason_code, CODE_CLAIM_LEVEL_MALFORMED)

    def test_invalid_spec_claim_ceiling_rejected(self):
        result = plan_evidence(_subquestion(), _spec(claim_ceiling="bogus"))
        self.assertEqual(result.reason_code, CODE_CLAIM_LEVEL_MALFORMED)

    def test_non_mapping_spec_rejected(self):
        result = plan_evidence(_subquestion(), spec=object())
        self.assertEqual(result.reason_code, CODE_SPEC_MALFORMED)

    def test_non_mapping_directive_rejected(self):
        result = plan_evidence(_subquestion(), directive=["not", "a", "mapping"])
        self.assertEqual(result.reason_code, CODE_DIRECTIVE_MALFORMED)


class DeterminismAndInertnessTests(unittest.TestCase):
    def test_same_input_twice_identical_projection(self):
        # Byte-identical inputs must yield a byte-identical result; use one shared
        # sub-question/spec so the inputs (including their timestamps) are identical.
        subq = _subquestion()
        spec = _spec(claim_ceiling="co_expression")
        first = plan_evidence(subq, spec).to_dict()
        second = plan_evidence(subq, spec).to_dict()
        self.assertEqual(first, second)
        # The produced plan itself carries no wall-clock timestamp.
        self.assertEqual(first["evidence_plan"]["created_at"], "")

    def test_inputs_not_mutated(self):
        subq = _subquestion()
        spec = _spec()
        directive = {"planned_gaps": ["a_synthetic_gap"]}
        subq_before = subq.to_dict()
        spec_before = spec.to_dict()
        directive_before = copy.deepcopy(directive)
        plan_evidence(subq, spec, directive=directive)
        self.assertEqual(subq.to_dict(), subq_before)
        self.assertEqual(spec.to_dict(), spec_before)
        self.assertEqual(directive, directive_before)

    def test_result_is_offline_no_network(self):
        real_socket = socket.socket

        def _blocked(*args, **kwargs):
            raise AssertionError("evidence planning must not open a socket")

        socket.socket = _blocked
        try:
            result = plan_evidence(_subquestion())
        finally:
            socket.socket = real_socket
        self.assertTrue(result.plan_drafted)

    def test_bounded_vocabulary(self):
        self.assertEqual(len(STATUSES), 5)
        self.assertIn(STATUS_EVIDENCE_PLAN_DRAFTED, STATUSES)
        for code in REASON_CODES:
            self.assertIsInstance(code, str)
        # Every result status is drawn from the bounded status set.
        for status in STATUSES:
            self.assertIsInstance(status, str)

    def test_result_dataclass_shape(self):
        result = plan_evidence(_subquestion())
        self.assertIsInstance(result, EvidencePlanResult)
        projection = result.to_dict()
        for key in ("status", "reason_code", "message", "plan_drafted", "evidence_plan", "fallback_route", "binding"):
            self.assertIn(key, projection)

    def test_produced_plan_reconstructs_as_evidence_plan(self):
        plan = plan_evidence(_subquestion()).evidence_plan
        # The projection can round-trip through the canonical dataclass unchanged.
        rebuilt = EvidencePlan(
            research_spec_id=plan["research_spec_id"],
            evidence_axes=plan["evidence_axes"],
            max_claim_level=plan["max_claim_level"],
            subquestion_ids=plan["subquestion_ids"],
            planned_gaps=plan["planned_gaps"],
            stop_conditions=plan["stop_conditions"],
            minimum_replication=plan["minimum_replication"],
            negative_evidence_strategy=plan["negative_evidence_strategy"],
            status=DRAFT_STATUS,
            created_at="",
        ).to_dict()
        self.assertEqual(validate_evidence_plan(rebuilt), [])


if __name__ == "__main__":
    unittest.main()
