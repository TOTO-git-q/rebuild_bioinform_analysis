"""Unit tests for the local offline Question Normalizer command (WP-06d / T-06-04).

Covers, for the bounded local/offline Question Normalizer command over synthetic
toy requests and policy facts only (no real user/research content, no real
human-derived data, no external LLM/provider/network call, no persistence, no
event, no granted approval):

- a supported toy bioinformatics request plus a usable policy → an inert
  ``draft_created`` outcome carrying a ``ResearchSpec`` *draft* (``status ==
  "draft"``) that preserves both the exact original text (with content hash) and a
  deterministic normalized text, and never guesses unknown facts,
- a missing policy or an inert approval-needed policy-builder result → a
  fail-closed ``approval_needed`` outcome with no draft and no granted approval,
- an unsupported / external / hard-stop-shaped request → a
  ``stopped_by_support_scope`` outcome with no draft,
- a multi-question or ambiguous/vague request → a human-review-oriented
  ``needs_clarification`` outcome with no draft and no child project,
- malformed truthy values (the bool ``True`` / the int ``1`` / the string
  ``"true"``) supplied where a policy is expected, and a forbidden truthy caller
  flag, fail closed,
- the offline adapter path is byte-deterministic and works with the network
  blocked (it never performs network/env/provider access),
- inputs (the request object and the constraints/policy) are never mutated,
- a malformed ``project_id``, a ``REAL`` execution-mode policy, and a tampered
  policy fail closed, with the bounded status + reason-code vocabulary and
  deterministic serialisation.
"""

import copy
import socket
import unittest

from auto_bioinfo.core.schemas import OriginalRequest, ProjectPolicy
from auto_bioinfo.intake.policy_builder import build_initial_policy
from auto_bioinfo.intake.question_normalizer import (
    CODE_DRAFT_CREATED,
    CODE_MULTI_QUESTION_REQUIRES_REVIEW,
    CODE_NEEDS_CLARIFICATION,
    CODE_POLICY_APPROVAL_NEEDED,
    CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED,
    CODE_POLICY_MALFORMED,
    CODE_POLICY_MISSING,
    CODE_PROJECT_ID_MALFORMED,
    CODE_STOPPED_BY_SUPPORT_SCOPE,
    DRAFT_STATUS,
    REASON_CODES,
    STATUS_APPROVAL_NEEDED,
    STATUS_DRAFT_CREATED,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_REJECTED_MALFORMED,
    STATUS_STOPPED_BY_SUPPORT_SCOPE,
    STATUSES,
    OfflineQuestionNormalizerAdapter,
    QuestionNormalizationResult,
    normalize_question,
)

PROJECT_ID = "proj_demo_01"
TOY_REQUEST = "Find differentially expressed genes between condition_a and condition_b in mouse RNA-seq data"


def _usable_policy(**overrides):
    """A built, usable initial policy from synthetic toy constraints."""
    base = {"data_sensitivity": "internal", "network": "local_only"}
    base.update(overrides)
    outcome = build_initial_policy(base, project_id=PROJECT_ID)
    assert outcome.built, outcome.reason_code
    return outcome


class DraftCreationHappyPathTests(unittest.TestCase):
    def test_supported_request_creates_inert_draft(self):
        result = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID)
        self.assertIsInstance(result, QuestionNormalizationResult)
        self.assertEqual(result.status, STATUS_DRAFT_CREATED)
        self.assertEqual(result.reason_code, CODE_DRAFT_CREATED)
        self.assertTrue(result.draft_created)
        self.assertFalse(result.needs_clarification)
        self.assertFalse(result.approval_needed)
        self.assertIsNotNone(result.research_spec)
        self.assertIsNone(result.approval_request)

    def test_draft_status_and_no_wall_clock_timestamp(self):
        spec = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID).research_spec
        self.assertEqual(spec["status"], DRAFT_STATUS)
        # Inert: the draft carries no wall-clock timestamp, keeping it deterministic.
        self.assertEqual(spec["created_at"], "")
        self.assertEqual(spec["project_id"], PROJECT_ID)

    def test_preserves_exact_original_and_normalized_text(self):
        spaced = "  Find   differentially expressed\tgenes between\ncondition_a and condition_b  "
        result = normalize_question(spaced, _usable_policy(), project_id=PROJECT_ID)
        original = result.original_request
        # Original is preserved verbatim (including its irregular whitespace)...
        self.assertEqual(original["original_text"], spaced)
        # ...the hash binds the original text...
        self.assertEqual(original["original_text_sha256"], OriginalRequest(project_id=PROJECT_ID, original_text=spaced).text_hash())
        # ...and a separate, whitespace-collapsed normalized view is recorded.
        expected_norm = "Find differentially expressed genes between condition_a and condition_b"
        self.assertEqual(original["normalized_text"], expected_norm)
        self.assertEqual(result.research_spec["research_question"], expected_norm)

    def test_unknown_facts_become_open_questions_not_guesses(self):
        # A request with no explicit organism/comparison must leave them empty and
        # surface open questions rather than inventing a biological preset.
        spec = normalize_question("Run an rna-seq differential expression analysis", _usable_policy(), project_id=PROJECT_ID).research_spec
        self.assertEqual(spec["organism"], "")
        self.assertEqual(spec["comparison_groups"], [])
        self.assertEqual(spec["condition_or_phenotype"], "")
        self.assertTrue(any("comparison" in q.lower() for q in spec["open_questions"]))
        self.assertTrue(any("organism" in q.lower() for q in spec["open_questions"]))

    def test_explicit_facts_are_extracted_not_invented(self):
        spec = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID).research_spec
        self.assertEqual(spec["organism"], "mouse")
        self.assertEqual(spec["comparison_groups"], ["condition_a", "condition_b"])
        # The claim ceiling stays conservative (association), never escalated.
        self.assertEqual(spec["claim_ceiling"], "association")
        self.assertEqual(spec["max_claim_level"], "association")

    def test_policy_recorded_for_audit_on_draft(self):
        policy = _usable_policy()
        result = normalize_question(TOY_REQUEST, policy, project_id=PROJECT_ID)
        self.assertEqual(result.policy["execution_mode"], "DEMO")
        self.assertEqual(result.binding["policy_data_sensitivity"], "internal")
        self.assertEqual(result.binding["research_spec_id"], result.research_spec["research_spec_id"])


class PolicyFailClosedTests(unittest.TestCase):
    def test_missing_policy_is_approval_needed_no_draft(self):
        result = normalize_question(TOY_REQUEST, None, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_APPROVAL_NEEDED)
        self.assertEqual(result.reason_code, CODE_POLICY_MISSING)
        self.assertTrue(result.approval_needed)
        self.assertIsNone(result.research_spec)

    def test_approval_needed_policy_stays_inert_no_draft(self):
        # A policy-builder result that itself needs approval (missing sensitivity)
        # must stay inert here — never become an approval, never a draft.
        approval_outcome = build_initial_policy({}, project_id=PROJECT_ID)
        self.assertTrue(approval_outcome.approval_needed)
        result = normalize_question(TOY_REQUEST, approval_outcome, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_APPROVAL_NEEDED)
        self.assertEqual(result.reason_code, CODE_POLICY_APPROVAL_NEEDED)
        self.assertIsNone(result.research_spec)
        self.assertIsNotNone(result.approval_request)
        # The carried approval projection is never granted.
        self.assertEqual(result.approval_request["state"], "requested")

    def test_malformed_truthy_policy_values_fail_closed(self):
        for bad in (True, 1, "true", [], "POLICY"):
            with self.subTest(bad=bad):
                result = normalize_question(TOY_REQUEST, bad, project_id=PROJECT_ID)
                self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
                self.assertEqual(result.reason_code, CODE_POLICY_MALFORMED)
                self.assertIsNone(result.research_spec)

    def test_real_execution_mode_policy_not_permitted(self):
        real = ProjectPolicy(project_id=PROJECT_ID, execution_mode="REAL").to_dict()
        result = normalize_question(TOY_REQUEST, real, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED)
        self.assertIsNone(result.research_spec)

    def test_tampered_policy_fails_closed(self):
        tampered = ProjectPolicy(project_id=PROJECT_ID, execution_mode="TEST").to_dict()
        tampered["content_hash"] = "deadbeef"
        result = normalize_question(TOY_REQUEST, tampered, project_id=PROJECT_ID)
        self.assertEqual(result.reason_code, CODE_POLICY_MALFORMED)
        self.assertIsNone(result.research_spec)

    def test_plain_policy_mapping_and_projectpolicy_are_accepted(self):
        for policy in (ProjectPolicy(project_id=PROJECT_ID, execution_mode="TEST"), ProjectPolicy(project_id=PROJECT_ID, execution_mode="TEST").to_dict()):
            with self.subTest(policy=type(policy).__name__):
                result = normalize_question(TOY_REQUEST, policy, project_id=PROJECT_ID)
                self.assertEqual(result.status, STATUS_DRAFT_CREATED)


class SupportScopeAndClarificationTests(unittest.TestCase):
    def test_destructive_request_is_stopped_no_draft(self):
        result = normalize_question("delete the production database", _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertEqual(result.reason_code, CODE_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.research_spec)
        self.assertIsNotNone(result.assessment)

    def test_external_llm_request_is_stopped(self):
        result = normalize_question("use an llm via the openai api to analyse rna-seq", _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.research_spec)

    def test_non_bioinformatics_request_is_stopped(self):
        result = normalize_question("please book me a flight to Paris", _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.research_spec)

    def test_forbidden_authority_caller_flag_is_stopped(self):
        result = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID, caller_facts={"authorizes_real_execution": True})
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.research_spec)

    def test_multi_question_request_requires_review_no_child_project(self):
        request = "Which genes are differentially expressed? Also, separately, assemble the genome?"
        result = normalize_question(request, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertEqual(result.reason_code, CODE_MULTI_QUESTION_REQUIRES_REVIEW)
        self.assertIsNone(result.research_spec)
        # The split suggestions are inert review snippets only — never sub-requests
        # or child projects.
        self.assertTrue(result.assessment["multi_question"])
        for suggestion in result.assessment["split_suggestions"]:
            self.assertNotIn("project_id", suggestion)
            self.assertNotIn("research_spec_id", suggestion)

    def test_vague_request_needs_clarification(self):
        result = normalize_question("do some rna-seq, whatever you find is fine", _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertEqual(result.reason_code, CODE_NEEDS_CLARIFICATION)
        self.assertIsNone(result.research_spec)

    def test_multi_topic_request_needs_clarification(self):
        # Two distinct analysis topics → clarification (never auto-split).
        request = "Run differential expression and also variant calling on this cohort"
        result = normalize_question(request, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertIsNone(result.research_spec)


class ProjectIdAndMalformedRequestTests(unittest.TestCase):
    def test_malformed_project_id_fails_closed(self):
        result = normalize_question(TOY_REQUEST, _usable_policy(), project_id="Bad ID!")
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_PROJECT_ID_MALFORMED)
        self.assertIsNone(result.research_spec)

    def test_blank_request_is_stopped_by_support_scope(self):
        result = normalize_question("   ", _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.research_spec)

    def test_non_string_request_is_stopped(self):
        result = normalize_question(12345, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.research_spec)


class DeterminismAndIsolationTests(unittest.TestCase):
    def test_repeated_command_is_byte_deterministic(self):
        first = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID)
        second = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_offline_adapter_is_deterministic(self):
        adapter = OfflineQuestionNormalizerAdapter()
        a = adapter.draft_research_spec(PROJECT_ID, "rna-seq deg analysis between a vs b")
        b = adapter.draft_research_spec(PROJECT_ID, "rna-seq deg analysis between a vs b")
        self.assertEqual(a, b)

    def test_offline_adapter_works_with_network_blocked(self):
        # Prove the offline "Agent call" never performs network access: break the
        # socket factory and confirm the adapter (and the full command) still work.
        original_socket = socket.socket
        socket.socket = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network access is blocked in this test"))
        try:
            spec = OfflineQuestionNormalizerAdapter().draft_research_spec(PROJECT_ID, "rna-seq deg analysis between a vs b")
            self.assertEqual(spec["status"], DRAFT_STATUS)
            result = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID)
            self.assertEqual(result.status, STATUS_DRAFT_CREATED)
        finally:
            socket.socket = original_socket

    def test_inputs_are_not_mutated(self):
        request = OriginalRequest(project_id=PROJECT_ID, original_text=TOY_REQUEST, submitted_at="2020-01-01T00:00:00+00:00")
        request_before = copy.deepcopy(request.to_dict())
        constraints = {"data_sensitivity": "internal", "network": "local_only"}
        constraints_before = copy.deepcopy(constraints)
        policy = build_initial_policy(constraints, project_id=PROJECT_ID)

        result = normalize_question(request, policy, project_id=PROJECT_ID)

        self.assertEqual(request.to_dict(), request_before)
        self.assertEqual(constraints, constraints_before)
        # A caller-supplied OriginalRequest keeps its own verbatim submitted_at.
        self.assertEqual(result.original_request["submitted_at"], "2020-01-01T00:00:00+00:00")
        # The preserved original text equals the input, byte for byte.
        self.assertEqual(result.original_request["original_text"], TOY_REQUEST)

    def test_result_to_dict_deepcopies_nested_data(self):
        result = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID)
        projection = result.to_dict()
        projection["research_spec"]["organism"] = "tampered"
        # Mutating the projection must not affect the result object.
        self.assertEqual(result.research_spec["organism"], "mouse")


class BoundedVocabularyTests(unittest.TestCase):
    def test_statuses_and_codes_are_bounded_and_consistent(self):
        self.assertEqual(len(STATUSES), len(set(STATUSES)))
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        # Every observed result uses the bounded vocabulary.
        observed = [
            normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID),
            normalize_question(TOY_REQUEST, None, project_id=PROJECT_ID),
            normalize_question(TOY_REQUEST, True, project_id=PROJECT_ID),
            normalize_question("delete everything", _usable_policy(), project_id=PROJECT_ID),
        ]
        for result in observed:
            self.assertIn(result.status, STATUSES)
            self.assertIn(result.reason_code, REASON_CODES)


if __name__ == "__main__":
    unittest.main()
