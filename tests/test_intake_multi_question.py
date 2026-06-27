"""Unit tests for the local intake multi-question assessment (WP-06b / T-06-02).

Covers, for the bounded multi-question assessment over synthetic toy request text
only (no real user/research content, no real human-derived data, no external
call):

- a single supported toy bioinformatics request produces no split suggestion,
- a mixed request with two bioinformatics topics is detected as multi-question,
- a request with multiple question marks is detected as multi-question,
- a vague/ambiguous request stays clarification-oriented and is not auto-split,
- an unsupported / external / hard-stop-shaped request produces no split
  artifacts (the support-scope stop is preserved, assessment not generated),
- split suggestions are bounded, deterministic, inert text only (no project ids,
  no sub-request objects, no executable plan),
- inputs are not mutated and repeated calls are stable,
- request-shape flexibility (OriginalRequest / str / mapping),
- bounded assessment + reason-code vocabulary and exact audit binding.
"""

import copy
import unittest

from auto_bioinfo.core.schemas import OriginalRequest
from auto_bioinfo.intake.multi_question import (
    ASSESS_MULTI_QUESTION,
    ASSESS_NEEDS_CLARIFICATION,
    ASSESS_NOT_GENERATED,
    ASSESS_SINGLE_QUESTION,
    ASSESSMENT_REASON_CODES,
    ASSESSMENTS,
    CODE_MULTI_QUESTION,
    CODE_NEEDS_CLARIFICATION,
    CODE_SINGLE_QUESTION,
    CODE_STOPPED_BY_SUPPORT_SCOPE,
    MAX_SNIPPET_LENGTH,
    MAX_SPLIT_SUGGESTIONS,
    IntakeAssessment,
    SplitSuggestion,
    assess_intake,
)
from auto_bioinfo.intake.support_scope import (
    CLASS_OUT_OF_SCOPE,
    CLASS_UNSUPPORTED_EXTERNAL_ACTION,
    CODE_DESTRUCTIVE_OPERATION,
    CODE_NON_BIOINFORMATICS,
    CODE_REAL_HUMAN_DATA_BEFORE_LOCK,
    CODE_SUPPORTED,
)

# --- Synthetic toy fixtures (no real user/research content) ------------------
SINGLE_REQUEST = "Run a bulk RNA-seq differential expression analysis between the treated and control groups using the provided synthetic count matrix."
TWO_TOPIC_REQUEST = "Please do a gene expression analysis and also a de novo genome assembly for these synthetic reads."
TWO_QUESTION_MARKS_REQUEST = (
    "Which genes are differentially expressed in the treated group? And what does the differential expression look like in the second synthetic batch?"
)
SEPARATOR_REQUEST = "Run the differential expression analysis on batch one; as well as run the differential expression analysis on batch two."
AMBIGUOUS_REQUEST = "Look at my RNA-seq count matrix and tell me whatever you find interesting."
NON_BIOINFORMATICS_REQUEST = "Write a catchy marketing email for my new coffee shop opening next week."
EXTERNAL_LLM_REQUEST = "Call the OpenAI API to summarise my gene list and explain the differential expression."
REAL_HUMAN_DATA_REQUEST = "Analyse the real patient genomic records from our hospital cohort to find expression markers."
DESTRUCTIVE_REQUEST = "Delete the production database that holds the old RNA-seq results, then re-run everything."


class _AssertAssessmentMixin(unittest.TestCase):
    def assert_assessment(self, assessment: IntakeAssessment, value: str, code: str) -> None:
        self.assertIsInstance(assessment, IntakeAssessment)
        self.assertEqual(assessment.assessment, value)
        self.assertEqual(assessment.reason_code, code)
        self.assertIn(assessment.assessment, ASSESSMENTS)
        self.assertIn(assessment.reason_code, ASSESSMENT_REASON_CODES)
        self.assertTrue(assessment.message)
        self.assertEqual(assessment.multi_question, value == ASSESS_MULTI_QUESTION)
        self.assertEqual(assessment.needs_clarification, value == ASSESS_NEEDS_CLARIFICATION)
        self.assertEqual(assessment.generated, value != ASSESS_NOT_GENERATED)
        # The upstream support-scope decision is always preserved verbatim.
        self.assertIn("classification", assessment.support_scope)
        self.assertIn("reason_code", assessment.support_scope)


class SingleQuestionTest(_AssertAssessmentMixin):
    def test_single_supported_request_has_no_split(self) -> None:
        assessment = assess_intake(SINGLE_REQUEST)
        self.assert_assessment(assessment, ASSESS_SINGLE_QUESTION, CODE_SINGLE_QUESTION)
        self.assertEqual(assessment.split_suggestions, ())
        self.assertEqual(assessment.support_scope["reason_code"], CODE_SUPPORTED)
        # Single topic, no extra question marks, no strong separator.
        self.assertFalse(assessment.binding["signals"]["multiple_topics"])
        self.assertFalse(assessment.binding["signals"]["multiple_question_marks"])
        self.assertFalse(assessment.binding["signals"]["has_strong_separator"])

    def test_single_request_via_original_request_object(self) -> None:
        request = OriginalRequest(project_id="proj-1", original_text=SINGLE_REQUEST)
        assessment = assess_intake(request)
        self.assert_assessment(assessment, ASSESS_SINGLE_QUESTION, CODE_SINGLE_QUESTION)
        self.assertEqual(assessment.binding["input_kind"], "original_request")

    def test_single_request_via_mapping_projection(self) -> None:
        request = OriginalRequest(project_id="proj-1", original_text=SINGLE_REQUEST).to_dict()
        assessment = assess_intake(request)
        self.assert_assessment(assessment, ASSESS_SINGLE_QUESTION, CODE_SINGLE_QUESTION)
        self.assertEqual(assessment.binding["input_kind"], "mapping")


class MultiQuestionDetectionTest(_AssertAssessmentMixin):
    def test_two_topic_request_is_detected(self) -> None:
        assessment = assess_intake(TWO_TOPIC_REQUEST)
        self.assert_assessment(assessment, ASSESS_MULTI_QUESTION, CODE_MULTI_QUESTION)
        self.assertTrue(assessment.multi_question)
        self.assertGreaterEqual(len(assessment.binding["detected_topics"]), 2)
        self.assertTrue(assessment.binding["signals"]["multiple_topics"])
        # "and also" carves the text into inert candidate snippets.
        self.assertGreaterEqual(len(assessment.split_suggestions), 2)

    def test_multiple_question_marks_are_detected(self) -> None:
        assessment = assess_intake(TWO_QUESTION_MARKS_REQUEST)
        self.assert_assessment(assessment, ASSESS_MULTI_QUESTION, CODE_MULTI_QUESTION)
        self.assertTrue(assessment.binding["signals"]["multiple_question_marks"])
        self.assertGreaterEqual(assessment.binding["signals"]["question_mark_count"], 2)
        self.assertGreaterEqual(len(assessment.split_suggestions), 2)

    def test_strong_separator_is_detected(self) -> None:
        assessment = assess_intake(SEPARATOR_REQUEST)
        self.assert_assessment(assessment, ASSESS_MULTI_QUESTION, CODE_MULTI_QUESTION)
        self.assertTrue(assessment.binding["signals"]["has_strong_separator"])
        self.assertIn("as well as", assessment.binding["signals"]["strong_separators"])


class NeedsClarificationTest(_AssertAssessmentMixin):
    def test_vague_request_stays_clarification_and_is_not_auto_split(self) -> None:
        assessment = assess_intake(AMBIGUOUS_REQUEST)
        self.assert_assessment(assessment, ASSESS_NEEDS_CLARIFICATION, CODE_NEEDS_CLARIFICATION)
        self.assertTrue(assessment.needs_clarification)
        # Clarification is never an automatic split.
        self.assertEqual(assessment.split_suggestions, ())
        self.assertNotIn("sub_requests", assessment.to_dict())


class SupportScopeStopPreservedTest(_AssertAssessmentMixin):
    def test_non_bioinformatics_stop_produces_no_assessment(self) -> None:
        assessment = assess_intake(NON_BIOINFORMATICS_REQUEST)
        self.assert_assessment(assessment, ASSESS_NOT_GENERATED, CODE_STOPPED_BY_SUPPORT_SCOPE)
        self.assertEqual(assessment.split_suggestions, ())
        self.assertFalse(assessment.generated)
        self.assertEqual(assessment.support_scope["reason_code"], CODE_NON_BIOINFORMATICS)

    def test_external_action_stop_produces_no_split_artifacts(self) -> None:
        assessment = assess_intake(EXTERNAL_LLM_REQUEST)
        self.assert_assessment(assessment, ASSESS_NOT_GENERATED, CODE_STOPPED_BY_SUPPORT_SCOPE)
        self.assertEqual(assessment.split_suggestions, ())
        self.assertEqual(assessment.support_scope["classification"], CLASS_UNSUPPORTED_EXTERNAL_ACTION)

    def test_real_human_data_hard_stop_produces_no_split_artifacts(self) -> None:
        assessment = assess_intake(REAL_HUMAN_DATA_REQUEST)
        self.assert_assessment(assessment, ASSESS_NOT_GENERATED, CODE_STOPPED_BY_SUPPORT_SCOPE)
        self.assertEqual(assessment.split_suggestions, ())
        self.assertEqual(assessment.support_scope["classification"], CLASS_OUT_OF_SCOPE)
        self.assertEqual(assessment.support_scope["reason_code"], CODE_REAL_HUMAN_DATA_BEFORE_LOCK)

    def test_destructive_hard_stop_produces_no_split_artifacts(self) -> None:
        assessment = assess_intake(DESTRUCTIVE_REQUEST)
        self.assert_assessment(assessment, ASSESS_NOT_GENERATED, CODE_STOPPED_BY_SUPPORT_SCOPE)
        self.assertEqual(assessment.split_suggestions, ())
        self.assertEqual(assessment.support_scope["reason_code"], CODE_DESTRUCTIVE_OPERATION)


class SplitSuggestionShapeTest(_AssertAssessmentMixin):
    def test_split_suggestions_are_inert_bounded_text_only(self) -> None:
        assessment = assess_intake(TWO_TOPIC_REQUEST)
        self.assertTrue(assessment.split_suggestions)
        self.assertLessEqual(len(assessment.split_suggestions), MAX_SPLIT_SUGGESTIONS)
        for index, suggestion in enumerate(assessment.split_suggestions):
            self.assertIsInstance(suggestion, SplitSuggestion)
            self.assertEqual(suggestion.index, index)
            self.assertTrue(suggestion.label)
            self.assertTrue(suggestion.snippet)
            self.assertTrue(suggestion.reason)
            self.assertLessEqual(len(suggestion.snippet), MAX_SNIPPET_LENGTH)
            # Inert: a suggestion is only text, never an executable / id-bearing object.
            projected = suggestion.to_dict()
            self.assertEqual(set(projected), {"index", "label", "snippet", "reason"})
            for forbidden in ("project_id", "request_id", "sub_request", "research_spec", "sub_question", "task_id", "event_id"):
                self.assertNotIn(forbidden, projected)

    def test_suggestion_snippets_are_substrings_of_the_original_text(self) -> None:
        assessment = assess_intake(TWO_TOPIC_REQUEST)
        for suggestion in assessment.split_suggestions:
            # Verbatim slice of the original (modulo trimming) — not rewritten.
            self.assertIn(suggestion.snippet, TWO_TOPIC_REQUEST)

    def test_long_snippet_is_truncated_to_bound(self) -> None:
        topic_a = "gene expression analysis " + "x" * 600
        topic_b = "de novo genome assembly " + "y" * 600
        request = f"Please do a {topic_a} and also a {topic_b}."
        assessment = assess_intake(request)
        self.assert_assessment(assessment, ASSESS_MULTI_QUESTION, CODE_MULTI_QUESTION)
        for suggestion in assessment.split_suggestions:
            self.assertLessEqual(len(suggestion.snippet), MAX_SNIPPET_LENGTH)


class PurityAndDeterminismTest(_AssertAssessmentMixin):
    def test_original_request_object_is_not_mutated(self) -> None:
        request = OriginalRequest(project_id="proj-1", original_text=TWO_TOPIC_REQUEST)
        before = copy.deepcopy(request.to_dict())
        assess_intake(request)
        self.assertEqual(request.original_text, TWO_TOPIC_REQUEST)
        self.assertEqual(request.to_dict(), before)

    def test_mapping_input_is_not_mutated(self) -> None:
        request = {"original_text": TWO_TOPIC_REQUEST}
        before = copy.deepcopy(request)
        assess_intake(request)
        self.assertEqual(request, before)

    def test_caller_facts_are_not_mutated(self) -> None:
        facts = {"data_lock_approved": True}
        before = copy.deepcopy(facts)
        assess_intake(REAL_HUMAN_DATA_REQUEST, caller_facts=facts)
        self.assertEqual(facts, before)

    def test_repeated_calls_are_deterministic(self) -> None:
        first = assess_intake(TWO_TOPIC_REQUEST).to_dict()
        second = assess_intake(TWO_TOPIC_REQUEST).to_dict()
        self.assertEqual(first, second)


class VocabularyTest(unittest.TestCase):
    def test_assessment_and_code_sets_are_consistent(self) -> None:
        self.assertEqual(len(ASSESSMENTS), len(set(ASSESSMENTS)))
        self.assertEqual(len(ASSESSMENT_REASON_CODES), len(set(ASSESSMENT_REASON_CODES)))
        self.assertEqual(len(ASSESSMENTS), len(ASSESSMENT_REASON_CODES))


if __name__ == "__main__":
    unittest.main()
