"""Unit tests for the local intake support-scope classifier (WP-06a / T-06-01).

Covers, for the bounded support-scope decision over synthetic toy request text
only (no real user/research content, no real human-derived data, no external
call):

- a supported toy bioinformatics request,
- an ambiguous request (vague goal) and a multi-topic request, both
  ``needs_clarification`` and never auto-split,
- a clearly non-bioinformatics request,
- an external LLM/provider request and a network/content-egress request,
- a real human-derived-data hard-stop-shaped request (and that an approved
  data-lock fact lifts that one hard stop),
- a destructive request and a credential/ruleset request,
- malformed input (non-string, blank, oversized, non-printable, malformed caller
  facts),
- a forbidden caller authority fact,
- request-shape flexibility (OriginalRequest / str / mapping),
- bounded classification + reason-code vocabulary, exact audit binding,
  deterministic serialisation, and purity (no mutation of inputs, stable repeated
  output).
"""

import unittest

from auto_bioinfo.core.schemas import OriginalRequest
from auto_bioinfo.intake.support_scope import (
    CLASS_MALFORMED_REQUEST,
    CLASS_NEEDS_CLARIFICATION,
    CLASS_OUT_OF_SCOPE,
    CLASS_SUPPORTED,
    CLASS_UNSUPPORTED_EXTERNAL_ACTION,
    CLASS_UNSUPPORTED_NON_BIOINFORMATICS,
    CLASSIFICATIONS,
    CODE_AMBIGUOUS,
    CODE_BLANK_REQUEST,
    CODE_CREDENTIAL_OR_RULESET_CHANGE,
    CODE_DESTRUCTIVE_OPERATION,
    CODE_EXTERNAL_LLM_OR_PROVIDER,
    CODE_FORBIDDEN_AUTHORITY_FACT,
    CODE_MALFORMED_CALLER_FACTS,
    CODE_MALFORMED_TEXT,
    CODE_MULTI_TOPIC,
    CODE_NETWORK_OR_CONTENT_EGRESS,
    CODE_NON_BIOINFORMATICS,
    CODE_NON_STRING_REQUEST,
    CODE_OVERSIZED_REQUEST,
    CODE_PAID_SERVICE,
    CODE_PUBLIC_DEPLOY_OR_PUBLISH,
    CODE_REAL_HUMAN_DATA_BEFORE_LOCK,
    CODE_SUPPORTED,
    MAX_REQUEST_LENGTH,
    REASON_CODES,
    IntakeDecision,
    classify_support_scope,
)

# --- Synthetic toy fixtures (no real user/research content) ------------------
SUPPORTED_REQUEST = "Run a bulk RNA-seq differential expression analysis between the treated and control groups using the provided synthetic count matrix."
AMBIGUOUS_REQUEST = "Look at my RNA-seq count matrix and tell me whatever you find interesting."
MULTI_TOPIC_REQUEST = "Please do a gene expression analysis and also a de novo genome assembly for these reads."
NON_BIOINFORMATICS_REQUEST = "Write a catchy marketing email for my new coffee shop opening next week."
EXTERNAL_LLM_REQUEST = "Call the OpenAI API to summarise my gene list and explain the differential expression."
NETWORK_EGRESS_REQUEST = "Run the RNA-seq analysis and then upload to our public dashboard and email the results."
REAL_HUMAN_DATA_REQUEST = "Analyse the real patient genomic records from our hospital cohort to find expression markers."
DESTRUCTIVE_REQUEST = "Delete the production database that holds the old RNA-seq results, then re-run everything."
CREDENTIAL_REQUEST = "Rotate the api key and change the branch protection ruleset before the gene expression run."
PAID_SERVICE_REQUEST = "Buy a license for the paid api and run the differential expression analysis on it."
PUBLIC_DEPLOY_REQUEST = "Deploy the differential expression pipeline to a public website so anyone can use it."


class _AssertDecisionMixin(unittest.TestCase):
    def assert_decision(self, decision: IntakeDecision, classification: str, code: str) -> None:
        self.assertIsInstance(decision, IntakeDecision)
        self.assertEqual(decision.classification, classification)
        self.assertEqual(decision.reason_code, code)
        self.assertIn(decision.classification, CLASSIFICATIONS)
        self.assertIn(decision.reason_code, REASON_CODES)
        self.assertTrue(decision.message)
        # supported is the *only* proceed outcome.
        self.assertEqual(decision.supported, classification == CLASS_SUPPORTED)
        self.assertEqual(decision.needs_clarification, classification == CLASS_NEEDS_CLARIFICATION)


class SupportedRequestTest(_AssertDecisionMixin):
    def test_supported_toy_bioinformatics_request(self) -> None:
        decision = classify_support_scope(SUPPORTED_REQUEST)
        self.assert_decision(decision, CLASS_SUPPORTED, CODE_SUPPORTED)
        self.assertTrue(decision.supported)
        # The binding records the bioinformatics signal it matched.
        self.assertTrue(decision.binding["matched_markers"]["bioinformatics"])

    def test_supported_via_original_request_object(self) -> None:
        request = OriginalRequest(project_id="proj-1", original_text=SUPPORTED_REQUEST)
        decision = classify_support_scope(request)
        self.assert_decision(decision, CLASS_SUPPORTED, CODE_SUPPORTED)
        self.assertEqual(decision.binding["input_kind"], "original_request")

    def test_supported_via_mapping_projection(self) -> None:
        request = OriginalRequest(project_id="proj-1", original_text=SUPPORTED_REQUEST).to_dict()
        decision = classify_support_scope(request)
        self.assert_decision(decision, CLASS_SUPPORTED, CODE_SUPPORTED)
        self.assertEqual(decision.binding["input_kind"], "mapping")


class NeedsClarificationTest(_AssertDecisionMixin):
    def test_ambiguous_vague_request(self) -> None:
        decision = classify_support_scope(AMBIGUOUS_REQUEST)
        self.assert_decision(decision, CLASS_NEEDS_CLARIFICATION, CODE_AMBIGUOUS)
        self.assertTrue(decision.needs_clarification)

    def test_multi_topic_request_is_not_auto_split(self) -> None:
        decision = classify_support_scope(MULTI_TOPIC_REQUEST)
        self.assert_decision(decision, CLASS_NEEDS_CLARIFICATION, CODE_MULTI_TOPIC)
        # Two or more distinct topics were detected, but the decision holds no
        # split sub-requests — clarification, never an automatic project split.
        self.assertGreaterEqual(len(decision.binding["detected_topics"]), 2)
        self.assertNotIn("sub_requests", decision.to_dict())
        self.assertNotIn("split", decision.to_dict())


class NonBioinformaticsTest(_AssertDecisionMixin):
    def test_non_bioinformatics_request(self) -> None:
        decision = classify_support_scope(NON_BIOINFORMATICS_REQUEST)
        self.assert_decision(decision, CLASS_UNSUPPORTED_NON_BIOINFORMATICS, CODE_NON_BIOINFORMATICS)
        self.assertFalse(decision.binding["matched_markers"]["bioinformatics"])


class ExternalActionTest(_AssertDecisionMixin):
    def test_external_llm_request(self) -> None:
        decision = classify_support_scope(EXTERNAL_LLM_REQUEST)
        self.assert_decision(decision, CLASS_UNSUPPORTED_EXTERNAL_ACTION, CODE_EXTERNAL_LLM_OR_PROVIDER)

    def test_network_or_content_egress_request(self) -> None:
        decision = classify_support_scope(NETWORK_EGRESS_REQUEST)
        self.assert_decision(decision, CLASS_UNSUPPORTED_EXTERNAL_ACTION, CODE_NETWORK_OR_CONTENT_EGRESS)


class HardStopRequestTest(_AssertDecisionMixin):
    def test_real_human_data_request_is_hard_stopped(self) -> None:
        decision = classify_support_scope(REAL_HUMAN_DATA_REQUEST)
        self.assert_decision(decision, CLASS_OUT_OF_SCOPE, CODE_REAL_HUMAN_DATA_BEFORE_LOCK)

    def test_real_human_data_allowed_only_with_data_lock_fact(self) -> None:
        # The hard stop is lifted once the caller asserts an approved data-lock
        # workflow exists; later stages still govern the actual lock.
        decision = classify_support_scope(REAL_HUMAN_DATA_REQUEST, caller_facts={"data_lock_approved": True})
        self.assertNotEqual(decision.reason_code, CODE_REAL_HUMAN_DATA_BEFORE_LOCK)
        self.assertTrue(decision.binding["data_lock_approved"])

    def test_destructive_request(self) -> None:
        decision = classify_support_scope(DESTRUCTIVE_REQUEST)
        self.assert_decision(decision, CLASS_OUT_OF_SCOPE, CODE_DESTRUCTIVE_OPERATION)

    def test_credential_or_ruleset_request(self) -> None:
        decision = classify_support_scope(CREDENTIAL_REQUEST)
        self.assert_decision(decision, CLASS_OUT_OF_SCOPE, CODE_CREDENTIAL_OR_RULESET_CHANGE)

    def test_paid_service_request(self) -> None:
        decision = classify_support_scope(PAID_SERVICE_REQUEST)
        self.assert_decision(decision, CLASS_OUT_OF_SCOPE, CODE_PAID_SERVICE)

    def test_public_deploy_request(self) -> None:
        decision = classify_support_scope(PUBLIC_DEPLOY_REQUEST)
        self.assert_decision(decision, CLASS_OUT_OF_SCOPE, CODE_PUBLIC_DEPLOY_OR_PUBLISH)


class ForbiddenAuthorityFactTest(_AssertDecisionMixin):
    def test_forbidden_authority_fact_fails_closed(self) -> None:
        decision = classify_support_scope(SUPPORTED_REQUEST, caller_facts={"bypasses_gates": True})
        self.assert_decision(decision, CLASS_OUT_OF_SCOPE, CODE_FORBIDDEN_AUTHORITY_FACT)

    def test_falsey_forbidden_fact_is_ignored(self) -> None:
        decision = classify_support_scope(SUPPORTED_REQUEST, caller_facts={"bypasses_gates": False})
        self.assert_decision(decision, CLASS_SUPPORTED, CODE_SUPPORTED)


class MalformedInputTest(_AssertDecisionMixin):
    def test_non_string_request(self) -> None:
        self.assert_decision(classify_support_scope(123), CLASS_MALFORMED_REQUEST, CODE_NON_STRING_REQUEST)
        self.assert_decision(classify_support_scope(None), CLASS_MALFORMED_REQUEST, CODE_NON_STRING_REQUEST)

    def test_mapping_with_non_string_text(self) -> None:
        self.assert_decision(classify_support_scope({"original_text": 5}), CLASS_MALFORMED_REQUEST, CODE_NON_STRING_REQUEST)

    def test_blank_request(self) -> None:
        self.assert_decision(classify_support_scope("    \n\t "), CLASS_MALFORMED_REQUEST, CODE_BLANK_REQUEST)

    def test_oversized_request(self) -> None:
        big = "a" * (MAX_REQUEST_LENGTH + 1)
        self.assert_decision(classify_support_scope(big), CLASS_MALFORMED_REQUEST, CODE_OVERSIZED_REQUEST)

    def test_non_printable_request(self) -> None:
        self.assert_decision(classify_support_scope("rna-seq\x00analysis"), CLASS_MALFORMED_REQUEST, CODE_MALFORMED_TEXT)

    def test_malformed_caller_facts_mapping(self) -> None:
        self.assert_decision(
            classify_support_scope(SUPPORTED_REQUEST, caller_facts=["not", "a", "mapping"]), CLASS_MALFORMED_REQUEST, CODE_MALFORMED_CALLER_FACTS
        )

    def test_malformed_caller_facts_non_string_key(self) -> None:
        self.assert_decision(classify_support_scope(SUPPORTED_REQUEST, caller_facts={1: "x"}), CLASS_MALFORMED_REQUEST, CODE_MALFORMED_CALLER_FACTS)


class BindingAndSerialisationTest(_AssertDecisionMixin):
    def test_binding_records_inspected_facts(self) -> None:
        decision = classify_support_scope(SUPPORTED_REQUEST, caller_facts={"data_lock_approved": False, "note": "x"})
        binding = decision.binding
        self.assertEqual(binding["input_kind"], "str")
        self.assertEqual(binding["text_length"], len(SUPPORTED_REQUEST))
        self.assertEqual(binding["caller_fact_keys"], ["data_lock_approved", "note"])
        self.assertFalse(binding["data_lock_approved"])
        self.assertIn("matched_markers", binding)

    def test_to_dict_is_deterministic_and_complete(self) -> None:
        decision = classify_support_scope(SUPPORTED_REQUEST)
        d1 = decision.to_dict()
        d2 = decision.to_dict()
        self.assertEqual(d1, d2)
        self.assertEqual(
            set(d1),
            {"classification", "reason_code", "message", "supported", "needs_clarification", "binding"},
        )

    def test_every_reason_code_maps_to_a_valid_classification(self) -> None:
        # Exercise a representative request per code and confirm the bounded sets.
        for decision in (
            classify_support_scope(SUPPORTED_REQUEST),
            classify_support_scope(AMBIGUOUS_REQUEST),
            classify_support_scope(MULTI_TOPIC_REQUEST),
            classify_support_scope(NON_BIOINFORMATICS_REQUEST),
            classify_support_scope(EXTERNAL_LLM_REQUEST),
            classify_support_scope(NETWORK_EGRESS_REQUEST),
            classify_support_scope(REAL_HUMAN_DATA_REQUEST),
            classify_support_scope(DESTRUCTIVE_REQUEST),
            classify_support_scope(CREDENTIAL_REQUEST),
            classify_support_scope(PAID_SERVICE_REQUEST),
            classify_support_scope(PUBLIC_DEPLOY_REQUEST),
        ):
            self.assertIn(decision.classification, CLASSIFICATIONS)
            self.assertIn(decision.reason_code, REASON_CODES)


class PurityAndDeterminismTest(_AssertDecisionMixin):
    def test_repeated_classification_is_stable(self) -> None:
        first = classify_support_scope(SUPPORTED_REQUEST).to_dict()
        second = classify_support_scope(SUPPORTED_REQUEST).to_dict()
        self.assertEqual(first, second)

    def test_inputs_are_not_mutated(self) -> None:
        request = OriginalRequest(project_id="proj-1", original_text=MULTI_TOPIC_REQUEST)
        original_text = request.original_text
        caller_facts = {"data_lock_approved": False}
        facts_snapshot = dict(caller_facts)
        classify_support_scope(request, caller_facts=caller_facts)
        self.assertEqual(request.original_text, original_text)
        self.assertEqual(caller_facts, facts_snapshot)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
