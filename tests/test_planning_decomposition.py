"""Unit tests for the local offline sub-question decomposition command (WP-07 / T-07-01,03,05).

Covers, for the bounded local/offline decomposition command over synthetic toy
drafts only (no real user/research content, no external LLM/provider/search/
network call, no persistence, no event, no granted approval, no project stage
transition, no child project):

- a toy draft with an explicit two-group comparison → an inert ``decomposed``
  outcome carrying a single single-relationship ``SubQuestion`` draft
  (``status == "draft"``, ``created_at == ""``) derived from the explicit facts,
- a draft with several explicit primary_endpoints → several single-relationship
  sub-questions, one per explicitly stated endpoint (splitting only what the draft
  explicitly stated),
- claim-ceiling capping: a comparison sub-question whose implied claim exceeds the
  parent ceiling is capped to the parent ceiling, never above it,
- a compound candidate (a research_question expressing more than one relationship)
  → ``rejected_compound`` with no sub-question,
- a comparison scope that exceeds a supplied resolved ScopeBundle →
  ``scope_exceeds_parent`` with no sub-question,
- a draft with no explicitly decomposable fact → ``needs_clarification`` (never a
  fabricated sub-question),
- malformed inputs (non-spec value, missing research_question, locked spec,
  invalid claim level, malformed scope) fail closed,
- the decomposition is byte-deterministic (same input twice → identical
  ``.to_dict()``), inputs are never mutated, every produced object passes
  ``validate_subquestion``, and the status/reason-code vocabulary stays bounded.
"""

import copy
import dataclasses
import unittest

from auto_bioinfo.core.schemas import CLAIM_LEVELS, ResearchSpec, ScopeBundle
from auto_bioinfo.core.validation import subquestion_is_single_purpose, validate_subquestion
from auto_bioinfo.planning.decomposition import (
    CODE_CLAIM_LEVEL_MALFORMED,
    CODE_COMPOUND_SUBQUESTION,
    CODE_DECOMPOSED,
    CODE_NEEDS_CLARIFICATION,
    CODE_SCOPE_EXCEEDS_PARENT,
    CODE_SCOPE_MALFORMED,
    CODE_SPEC_MALFORMED,
    COVERAGE_COVERED,
    COVERAGE_PARTIAL,
    DRAFT_STATUS,
    REASON_CODES,
    STATUS_DECOMPOSED,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_REJECTED_COMPOUND,
    STATUS_REJECTED_MALFORMED,
    STATUS_SCOPE_EXCEEDS_PARENT,
    STATUSES,
    DecompositionResult,
    decompose_research_spec,
)

PROJECT_ID = "proj_demo_01"
TOY_REQUEST = "Find differentially expressed genes between tumor and normal in mouse rna-seq data"


def _draft_spec(**overrides):
    """A synthetic inert draft ResearchSpec object."""
    base = dict(project_id=PROJECT_ID, research_question=TOY_REQUEST, status=DRAFT_STATUS)
    base.update(overrides)
    return ResearchSpec(**base)


class DecomposedHappyPathTests(unittest.TestCase):
    def test_explicit_comparison_yields_one_single_relationship_subquestion(self):
        spec = _draft_spec(organism="mouse", comparison_groups=["tumor", "normal"])
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertEqual(result.reason_code, CODE_DECOMPOSED)
        self.assertTrue(result.decomposed)
        self.assertEqual(result.subquestion_count, 1)
        sq = result.subquestions[0]
        # Derived verbatim from the explicit research question; nothing invented.
        self.assertEqual(sq["question"], TOY_REQUEST)
        self.assertEqual(sq["status"], DRAFT_STATUS)
        self.assertEqual(sq["created_at"], "")  # inert + deterministic
        self.assertTrue(subquestion_is_single_purpose(sq["question"]))
        self.assertEqual(validate_subquestion(sq, research_spec_id=sq["research_spec_id"]), [])
        # Assignment: a comparison is fully anchored → covered, priority 1.
        assignment = result.assignments[0]
        self.assertEqual(assignment["priority"], 1)
        self.assertEqual(assignment["coverage"], COVERAGE_COVERED)
        self.assertEqual(result.coverage, COVERAGE_COVERED)

    def test_multiple_endpoints_split_into_one_subquestion_each(self):
        spec = _draft_spec(
            research_question="Characterize the toy dataset",
            comparison_groups=["tumor", "normal"],
            primary_endpoints=["differential expression", "pathway enrichment"],
        )
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertEqual(result.subquestion_count, 2)
        questions = [sq["question"] for sq in result.subquestions]
        self.assertEqual(
            questions,
            [
                "What is the differential expression between tumor and normal?",
                "What is the pathway enrichment between tumor and normal?",
            ],
        )
        # Deterministic priorities follow stable candidate order.
        self.assertEqual([a["priority"] for a in result.assignments], [1, 2])
        for sq in result.subquestions:
            self.assertTrue(subquestion_is_single_purpose(sq["question"]))
            self.assertEqual(validate_subquestion(sq, research_spec_id=sq["research_spec_id"]), [])

    def test_endpoint_without_comparison_is_partial_coverage(self):
        spec = _draft_spec(
            research_question="Describe the expression profile",
            primary_endpoints=["expression profile"],
        )
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertEqual(result.subquestions[0]["question"], "What is the expression profile?")
        self.assertEqual(result.assignments[0]["coverage"], COVERAGE_PARTIAL)
        self.assertEqual(result.coverage, COVERAGE_PARTIAL)

    def test_accepts_plain_dict_spec_projection(self):
        spec = {
            "project_id": PROJECT_ID,
            "research_question": TOY_REQUEST,
            "status": DRAFT_STATUS,
            "comparison_groups": ["tumor", "normal"],
        }
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertEqual(result.subquestion_count, 1)


class ClaimCeilingCappingTests(unittest.TestCase):
    def test_comparison_claim_capped_to_lower_parent_ceiling(self):
        # Parent ceiling descriptive < implied association → capped to descriptive.
        spec = _draft_spec(comparison_groups=["tumor", "normal"], claim_ceiling="descriptive")
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertTrue(result.capped)
        sq = result.subquestions[0]
        self.assertEqual(sq["claim_ceiling"], "descriptive")  # never above the parent ceiling
        assignment = result.assignments[0]
        self.assertEqual(assignment["implied_claim_level"], "association")
        self.assertEqual(assignment["allowed_claim_level"], "descriptive")
        self.assertTrue(assignment["capped"])
        # The recorded allowed level never exceeds the parent ceiling.
        self.assertLessEqual(CLAIM_LEVELS.index(sq["claim_ceiling"]), CLAIM_LEVELS.index("descriptive"))

    def test_high_parent_ceiling_leaves_implied_claim_uncapped(self):
        spec = _draft_spec(comparison_groups=["tumor", "normal"], claim_ceiling="causal_support")
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertFalse(result.capped)
        # The implied association claim stays, still well under the parent ceiling.
        self.assertEqual(result.subquestions[0]["claim_ceiling"], "association")
        self.assertFalse(result.assignments[0]["capped"])


class CompoundRejectionTests(unittest.TestCase):
    def test_compound_research_question_is_rejected_not_recorded(self):
        # A comparison-driven single sub-question uses the research_question verbatim;
        # a compound research_question is rejected rather than silently recorded.
        compound = "Find DEGs between tumor and normal and how are pathways enriched?"
        spec = _draft_spec(research_question=compound, comparison_groups=["tumor", "normal"])
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_REJECTED_COMPOUND)
        self.assertEqual(result.reason_code, CODE_COMPOUND_SUBQUESTION)
        self.assertEqual(result.subquestions, [])

    def test_compound_endpoint_is_rejected(self):
        spec = _draft_spec(
            comparison_groups=["tumor", "normal"],
            primary_endpoints=["expression change and how methylation shifts"],
        )
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_REJECTED_COMPOUND)
        self.assertEqual(result.reason_code, CODE_COMPOUND_SUBQUESTION)
        self.assertEqual(result.subquestions, [])


class ScopeExceedsParentTests(unittest.TestCase):
    def test_group_outside_resolved_scope_is_rejected(self):
        spec = _draft_spec(comparison_groups=["tumor", "normal", "treated"])
        scope = ScopeBundle(
            research_spec_id=spec.to_dict()["research_spec_id"],
            species=["mouse"],
            tissues=[],
            conditions=[],
            comparisons=["tumor", "normal"],  # resolved scope omits "treated"
        )
        result = decompose_research_spec(spec, scope)
        self.assertEqual(result.status, STATUS_SCOPE_EXCEEDS_PARENT)
        self.assertEqual(result.reason_code, CODE_SCOPE_EXCEEDS_PARENT)
        self.assertEqual(result.subquestions, [])

    def test_scope_matching_the_spec_is_accepted(self):
        spec = _draft_spec(comparison_groups=["tumor", "normal"])
        scope = ScopeBundle(
            research_spec_id=spec.to_dict()["research_spec_id"],
            species=["mouse"],
            tissues=[],
            conditions=[],
            comparisons=["tumor", "normal"],
        )
        result = decompose_research_spec(spec, scope)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertEqual(result.subquestion_count, 1)


class NeedsClarificationTests(unittest.TestCase):
    def test_no_endpoint_and_no_comparison_needs_clarification(self):
        spec = _draft_spec(research_question="Identify differentially expressed genes")
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertEqual(result.reason_code, CODE_NEEDS_CLARIFICATION)
        self.assertEqual(result.subquestions, [])

    def test_single_group_is_not_a_usable_comparison(self):
        spec = _draft_spec(comparison_groups=["tumor"])
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertEqual(result.subquestions, [])


class MalformedInputTests(unittest.TestCase):
    def test_non_spec_value_fails_closed(self):
        for bad in (None, True, 1, "spec", ["spec"]):
            result = decompose_research_spec(bad)
            self.assertEqual(result.status, STATUS_REJECTED_MALFORMED, bad)
            self.assertEqual(result.reason_code, CODE_SPEC_MALFORMED, bad)

    def test_missing_research_question_fails_closed(self):
        result = decompose_research_spec({"project_id": PROJECT_ID, "status": DRAFT_STATUS})
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_SPEC_MALFORMED)

    def test_locked_spec_is_not_decomposable(self):
        spec = _draft_spec(comparison_groups=["tumor", "normal"], status="locked")
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_SPEC_MALFORMED)

    def test_invalid_claim_level_fails_closed(self):
        spec = {
            "project_id": PROJECT_ID,
            "research_question": TOY_REQUEST,
            "status": DRAFT_STATUS,
            "comparison_groups": ["tumor", "normal"],
            "claim_ceiling": "not_a_level",
        }
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_CLAIM_LEVEL_MALFORMED)

    def test_malformed_scope_value_fails_closed(self):
        spec = _draft_spec(comparison_groups=["tumor", "normal"])
        for bad in (True, 1, "scope", ["scope"]):
            result = decompose_research_spec(spec, bad)
            self.assertEqual(result.status, STATUS_REJECTED_MALFORMED, bad)
            self.assertEqual(result.reason_code, CODE_SCOPE_MALFORMED, bad)


class DeterminismAndIsolationTests(unittest.TestCase):
    def test_decomposition_is_byte_deterministic(self):
        # Byte-identical input twice → byte-identical output.  A ResearchSpec
        # carries a live ``created_at`` timestamp, so the same input means the same
        # spec object (a fresh spec each call is not a byte-identical input); the
        # produced sub-question drafts themselves stay timestamp-free (created_at="").
        spec = _draft_spec(comparison_groups=["tumor", "normal"], primary_endpoints=["differential expression"])
        a = decompose_research_spec(spec).to_dict()
        b = decompose_research_spec(spec).to_dict()
        self.assertEqual(a, b)
        # The produced sub-question projections are inert and deterministic.
        for sq in a["subquestions"]:
            self.assertEqual(sq["created_at"], "")

    def test_inputs_are_not_mutated(self):
        spec = _draft_spec(comparison_groups=["tumor", "normal"])
        spec_before = copy.deepcopy(spec.to_dict())
        scope = ScopeBundle(
            research_spec_id=spec.to_dict()["research_spec_id"],
            species=["mouse"],
            tissues=[],
            conditions=[],
            comparisons=["tumor", "normal"],
        )
        scope_before = copy.deepcopy(scope.to_dict())
        decompose_research_spec(spec, scope)
        self.assertEqual(spec.to_dict(), spec_before)
        self.assertEqual(scope.to_dict(), scope_before)

    def test_dict_input_is_not_mutated(self):
        spec = {
            "project_id": PROJECT_ID,
            "research_question": TOY_REQUEST,
            "status": DRAFT_STATUS,
            "comparison_groups": ["tumor", "normal"],
        }
        before = copy.deepcopy(spec)
        decompose_research_spec(spec)
        self.assertEqual(spec, before)


class BoundedContractTests(unittest.TestCase):
    def test_status_and_reason_code_vocabularies_are_bounded(self):
        self.assertEqual(len(STATUSES), 5)
        self.assertEqual(len(set(STATUSES)), 5)
        self.assertEqual(len(set(REASON_CODES)), len(REASON_CODES))

    def test_every_produced_subquestion_passes_validate_subquestion(self):
        spec = _draft_spec(comparison_groups=["tumor", "normal"], primary_endpoints=["differential expression", "co-expression"])
        result = decompose_research_spec(spec)
        self.assertEqual(result.status, STATUS_DECOMPOSED)
        self.assertTrue(result.subquestions)
        for sq in result.subquestions:
            self.assertEqual(validate_subquestion(sq, research_spec_id=sq["research_spec_id"]), [])
            self.assertTrue(sq["subquestion_id"])  # id is minted, non-empty

    def test_result_projection_has_stable_keys(self):
        result = decompose_research_spec(_draft_spec(comparison_groups=["tumor", "normal"]))
        data = result.to_dict()
        self.assertEqual(data["status"], result.status)
        self.assertEqual(data["reason_code"], result.reason_code)
        self.assertIn("subquestions", data)
        self.assertIn("assignments", data)
        self.assertIn("coverage", data)
        self.assertIn("parent_claim_ceiling", data)

    def test_result_is_a_frozen_inert_dataclass(self):
        result = decompose_research_spec(_draft_spec(comparison_groups=["tumor", "normal"]))
        self.assertIsInstance(result, DecompositionResult)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.status = "tampered"  # frozen — the result cannot be mutated in place


if __name__ == "__main__":
    unittest.main()
