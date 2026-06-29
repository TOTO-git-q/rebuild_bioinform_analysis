"""Unit tests for the local offline Scope Resolver preflight command (WP-06e / T-06-05).

Covers, for the bounded local/offline Scope Resolver preflight command over
synthetic toy drafts and policy facts only (no real user/research content, no real
human-derived data, no external LLM/provider/ontology/search/network call, no
persistence, no event, no granted approval, no project stage transition, no child
project):

- a supported toy draft with explicit organism + comparison facts → an inert
  ``scope_draft_created`` outcome carrying a ``ScopeBundle`` *draft*
  (``status == "draft"``, ``created_at == ""``) populated only from the explicit
  facts, plus an open ``AmbiguityReport`` for the unknown tissue,
- a draft with missing/ambiguous organism/tissue/condition/comparison facts →
  ``needs_clarification`` with no bundle and the unknowns kept open (never guessed),
- an unsupported organism (a well-formed draft outside the synthetic supported
  vocabulary) → ``unsupported_scope`` with no bundle,
- an external / hard-stop-shaped draft → ``stopped_by_support_scope`` with no
  bundle (the WP-06a gate is preserved as defence in depth),
- a missing policy or an inert approval-needed policy-builder result →
  ``approval_needed`` with no bundle and no granted approval,
- malformed truthy values (the bool ``True`` / the int ``1`` / the string
  ``"true"``) supplied where a policy is expected, and a forbidden truthy caller
  authority flag, fail closed,
- a non-``draft_created`` :class:`QuestionNormalizationResult` is carried through
  verbatim as the corresponding scope stop / pause / approval outcome,
- the offline resolver path is byte-deterministic and works with the network
  blocked (it never performs network/env/provider/ontology/search access),
- inputs (the draft spec, the normalizer result, the policy) are never mutated,
- the produced projections are inert in-memory drafts (no real ontology id, never
  marked authoritative), with the bounded status + reason-code vocabulary and
  deterministic serialisation.
"""

import copy
import dataclasses
import socket
import unittest

from auto_bioinfo.core.schemas import ProjectPolicy, ResearchSpec
from auto_bioinfo.core.validation import validate_ambiguity_report, validate_scope_bundle
from auto_bioinfo.intake.policy_builder import build_initial_policy
from auto_bioinfo.intake.question_normalizer import normalize_question
from auto_bioinfo.intake.scope_resolver import (
    CODE_MULTI_QUESTION_REQUIRES_REVIEW,
    CODE_NEEDS_CLARIFICATION,
    CODE_POLICY_APPROVAL_NEEDED,
    CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED,
    CODE_POLICY_MALFORMED,
    CODE_POLICY_MISSING,
    CODE_PROJECT_ID_MALFORMED,
    CODE_SCOPE_DRAFT_CREATED,
    CODE_SPEC_MALFORMED,
    CODE_STOPPED_BY_SUPPORT_SCOPE,
    CODE_UNSUPPORTED_SCOPE,
    DRAFT_STATUS,
    REASON_CODES,
    STATUS_APPROVAL_NEEDED,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_REJECTED_MALFORMED,
    STATUS_SCOPE_DRAFT_CREATED,
    STATUS_STOPPED_BY_SUPPORT_SCOPE,
    STATUS_UNSUPPORTED_SCOPE,
    STATUSES,
    OfflineScopeResolverAdapter,
    ScopeResolutionResult,
    ScopeVocabulary,
    _ResolverFacts,
    resolve_scope,
)

PROJECT_ID = "proj_demo_01"
# Synthetic toy request with an explicit organism + an explicit two-group contrast.
TOY_REQUEST = "Find differentially expressed genes between tumor and normal in mouse RNA-seq data"
# Synthetic toy request that is in-scope but states no organism / comparison fact.
VAGUE_REQUEST = "Identify differentially expressed genes in the rna-seq expression dataset"


def _usable_policy(**overrides):
    """A built, usable initial policy from synthetic toy constraints."""
    base = {"data_sensitivity": "internal", "network": "local_only"}
    base.update(overrides)
    outcome = build_initial_policy(base, project_id=PROJECT_ID)
    assert outcome.built, outcome.reason_code
    return outcome


def _draft_spec(**overrides):
    """A synthetic inert draft ResearchSpec object."""
    base = dict(project_id=PROJECT_ID, research_question=VAGUE_REQUEST, status=DRAFT_STATUS)
    base.update(overrides)
    return ResearchSpec(**base)


def _normalizer_draft():
    """A real WP-06d ``draft_created`` normalizer result for the toy request."""
    result = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID)
    assert result.draft_created, result.reason_code
    return result


class ScopeDraftCreatedTests(unittest.TestCase):
    def test_normalizer_draft_yields_inert_scope_bundle_from_explicit_facts(self):
        result = resolve_scope(_normalizer_draft(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_SCOPE_DRAFT_CREATED)
        self.assertEqual(result.reason_code, CODE_SCOPE_DRAFT_CREATED)
        self.assertTrue(result.scope_draft_created)
        bundle = result.scope_bundle
        self.assertIsNotNone(bundle)
        # Only the explicit facts populate axes; nothing is invented.
        self.assertEqual(bundle["species"], ["mouse"])
        self.assertEqual(bundle["comparisons"], ["tumor", "normal"])
        self.assertEqual(bundle["conditions"], ["tumor", "normal"])
        self.assertEqual(bundle["tissues"], [])  # tissue never stated → empty, never guessed
        # Inert + deterministic: a draft with no wall-clock timestamp.
        self.assertEqual(bundle["status"], DRAFT_STATUS)
        self.assertEqual(bundle["created_at"], "")
        self.assertEqual(validate_scope_bundle(bundle), [])
        # The unknown tissue is kept as an explicit open ambiguity, not dropped.
        self.assertIn("tissue", result.open_questions)
        self.assertEqual(validate_ambiguity_report(result.ambiguity_report), [])
        self.assertTrue(all(it["status"] == "open" for it in result.ambiguity_report["items"]))

    def test_bare_draft_spec_with_explicit_facts_creates_scope_bundle(self):
        spec = _draft_spec(
            research_question=TOY_REQUEST,
            organism="human",
            tissue="liver",
            comparison_groups=["tumor", "normal"],
        )
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_SCOPE_DRAFT_CREATED)
        bundle = result.scope_bundle
        self.assertEqual(bundle["species"], ["human"])
        self.assertEqual(bundle["tissues"], ["liver"])  # explicit + in synthetic vocab
        self.assertEqual(bundle["comparisons"], ["tumor", "normal"])
        self.assertEqual(result.open_questions, [])  # every axis explicitly resolved

    def test_unknown_comparison_groups_stay_open_not_guessed(self):
        spec = _draft_spec(
            research_question=TOY_REQUEST,
            organism="mouse",
            comparison_groups=["cohorta", "cohortb"],  # not in synthetic condition vocab
        )
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_SCOPE_DRAFT_CREATED)
        bundle = result.scope_bundle
        # Explicit comparison labels are kept; they are NOT promoted to confirmed
        # conditions, and the unconfirmed groups surface as open ambiguities.
        self.assertEqual(bundle["comparisons"], ["cohorta", "cohortb"])
        self.assertEqual(bundle["conditions"], [])
        self.assertIn("condition", result.open_questions)


class ExplicitConditionTests(unittest.TestCase):
    """An explicit ``condition_or_phenotype`` fact is never silently dropped."""

    def test_recognized_explicit_condition_populates_conditions_axis(self):
        # A recognised explicit condition is projected onto the conditions axis,
        # even with no comparison groups stated; it is never dropped.
        spec = _draft_spec(
            research_question="Identify differential expression in tumor samples",
            organism="mouse",
            condition_or_phenotype="tumor",
        )
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_SCOPE_DRAFT_CREATED)
        bundle = result.scope_bundle
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["conditions"], ["tumor"])
        self.assertEqual(bundle["species"], ["mouse"])
        # The fact is projected, so it is NOT also an open condition ambiguity.
        self.assertNotIn("condition", result.open_questions)
        self.assertEqual(validate_scope_bundle(bundle), [])

    def test_unrecognized_explicit_condition_stays_open_not_dropped(self):
        # An unrecognised explicit condition is kept as an open ambiguity rather
        # than being silently discarded or guessed onto the conditions axis.
        spec = _draft_spec(
            research_question="Identify differential expression in cachexia samples",
            organism="mouse",
            condition_or_phenotype="cachexia",  # not in synthetic condition vocab
        )
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_SCOPE_DRAFT_CREATED)
        bundle = result.scope_bundle
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["conditions"], [])  # never guessed
        self.assertIn("condition", result.open_questions)  # surfaced, not dropped
        self.assertEqual(validate_ambiguity_report(result.ambiguity_report), [])

    def test_explicit_condition_not_duplicated_when_also_a_comparison_group(self):
        # When the same recognised term appears as both an explicit condition and a
        # comparison group, the conditions axis stays de-duplicated.
        spec = _draft_spec(
            research_question=TOY_REQUEST,
            organism="mouse",
            condition_or_phenotype="tumor",
            comparison_groups=["tumor", "normal"],
        )
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_SCOPE_DRAFT_CREATED)
        self.assertEqual(result.scope_bundle["conditions"], ["tumor", "normal"])


class NeedsClarificationTests(unittest.TestCase):
    def test_no_explicit_scope_fact_stays_open_no_bundle(self):
        result = resolve_scope(_draft_spec(), _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertEqual(result.reason_code, CODE_NEEDS_CLARIFICATION)
        self.assertIsNone(result.scope_bundle)
        # The organism / comparison / tissue unknowns are all kept open.
        for subject in ("organism", "comparison", "tissue"):
            self.assertIn(subject, result.open_questions)
        self.assertEqual(validate_ambiguity_report(result.ambiguity_report), [])

    def test_single_comparison_group_is_not_a_usable_comparison(self):
        # One group (or a self-comparison) is not a two-group contrast → stays open.
        spec = _draft_spec(comparison_groups=["tumor", "tumor"])
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertIsNone(result.scope_bundle)
        self.assertIn("comparison", result.open_questions)


class UnsupportedScopeTests(unittest.TestCase):
    def test_organism_outside_synthetic_vocabulary_fails_closed(self):
        spec = _draft_spec(
            research_question="differential expression analysis in dragon rna-seq between groupa and groupb",
            organism="dragon",
            comparison_groups=["groupa", "groupb"],
        )
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_UNSUPPORTED_SCOPE)
        self.assertEqual(result.reason_code, CODE_UNSUPPORTED_SCOPE)
        self.assertIsNone(result.scope_bundle)
        # The unsupported organism is recorded as an open ambiguity, never resolved.
        self.assertIn("organism", result.open_questions)


class SupportScopeStopPreservedTests(unittest.TestCase):
    def test_hard_stop_shaped_draft_is_stopped_by_support_scope(self):
        spec = _draft_spec(
            research_question="deploy the trained model to production and call the external OpenAI provider api",
            organism="human",
            comparison_groups=["tumor", "normal"],
        )
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertEqual(result.reason_code, CODE_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.scope_bundle)

    def test_forbidden_authority_caller_flag_fails_closed(self):
        # A truthy forbidden authority fact must not buy scope resolution.
        spec = _draft_spec(research_question=TOY_REQUEST, organism="mouse", comparison_groups=["tumor", "normal"])
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID, caller_facts={"bypasses_gates": True})
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.scope_bundle)


class PolicyGateTests(unittest.TestCase):
    def test_missing_policy_is_approval_needed_no_scope(self):
        result = resolve_scope(_draft_spec(), None, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_APPROVAL_NEEDED)
        self.assertEqual(result.reason_code, CODE_POLICY_MISSING)
        self.assertIsNone(result.scope_bundle)

    def test_approval_needed_policy_builder_result_stays_inert(self):
        # A policy build that requires human approval (missing data sensitivity).
        outcome = build_initial_policy({"network": "local_only"}, project_id=PROJECT_ID)
        self.assertTrue(outcome.approval_needed)
        result = resolve_scope(_draft_spec(), outcome, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_APPROVAL_NEEDED)
        self.assertEqual(result.reason_code, CODE_POLICY_APPROVAL_NEEDED)
        self.assertIsNone(result.scope_bundle)
        # The inert approval projection is carried but never granted.
        self.assertIsNotNone(result.approval_request)

    def test_malformed_truthy_policy_values_fail_closed(self):
        for bad in (True, 1, "true"):
            result = resolve_scope(_draft_spec(), bad, project_id=PROJECT_ID)
            self.assertEqual(result.status, STATUS_REJECTED_MALFORMED, bad)
            self.assertEqual(result.reason_code, CODE_POLICY_MALFORMED, bad)
            self.assertIsNone(result.scope_bundle)

    def test_real_execution_mode_policy_not_permitted(self):
        real_policy = ProjectPolicy(project_id=PROJECT_ID, execution_mode="REAL").to_dict()
        result = resolve_scope(_draft_spec(), real_policy, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED)
        self.assertIsNone(result.scope_bundle)


class MalformedInputTests(unittest.TestCase):
    def test_invalid_project_id_fails_closed(self):
        result = resolve_scope(_normalizer_draft(), project_id="Not An Id")
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_PROJECT_ID_MALFORMED)

    def test_non_spec_source_fails_closed(self):
        for bad in (None, True, 1, "draft", ["spec"]):
            result = resolve_scope(bad, _usable_policy(), project_id=PROJECT_ID)
            self.assertEqual(result.status, STATUS_REJECTED_MALFORMED, bad)
            self.assertEqual(result.reason_code, CODE_SPEC_MALFORMED, bad)

    def test_locked_spec_is_not_resolvable(self):
        spec = _draft_spec(research_question=TOY_REQUEST, organism="mouse", status="locked")
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_SPEC_MALFORMED)

    def test_spec_without_research_question_fails_closed(self):
        result = resolve_scope({"project_id": PROJECT_ID, "status": DRAFT_STATUS}, _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_SPEC_MALFORMED)


class NormalizerStopPassThroughTests(unittest.TestCase):
    def test_support_scope_stop_is_carried_through(self):
        stopped = normalize_question("deploy the model and call the external OpenAI api", _usable_policy(), project_id=PROJECT_ID)
        self.assertFalse(stopped.draft_created)
        result = resolve_scope(stopped, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_SUPPORT_SCOPE)
        self.assertEqual(result.reason_code, CODE_STOPPED_BY_SUPPORT_SCOPE)
        self.assertIsNone(result.scope_bundle)

    def test_multi_question_normalizer_result_needs_clarification(self):
        multi = normalize_question(
            "Find DEGs between tumor and normal in mouse. Also which pathways are enriched in human liver?",
            _usable_policy(),
            project_id=PROJECT_ID,
        )
        result = resolve_scope(multi, project_id=PROJECT_ID)
        # Either a multi-question or a needs-clarification upstream pause maps to the
        # paused scope status; both are no-bundle outcomes.
        self.assertEqual(result.status, STATUS_NEEDS_CLARIFICATION)
        self.assertIn(result.reason_code, (CODE_MULTI_QUESTION_REQUIRES_REVIEW, CODE_NEEDS_CLARIFICATION))
        self.assertIsNone(result.scope_bundle)

    def test_approval_needed_normalizer_result_is_carried_through(self):
        approval = normalize_question(TOY_REQUEST, None, project_id=PROJECT_ID)
        self.assertTrue(approval.approval_needed)
        result = resolve_scope(approval, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_APPROVAL_NEEDED)
        self.assertEqual(result.reason_code, CODE_POLICY_MISSING)
        self.assertIsNone(result.scope_bundle)


class DeterminismAndIsolationTests(unittest.TestCase):
    def test_resolution_is_byte_deterministic(self):
        a = resolve_scope(_normalizer_draft(), project_id=PROJECT_ID).to_dict()
        b = resolve_scope(_normalizer_draft(), project_id=PROJECT_ID).to_dict()
        self.assertEqual(a, b)

    def test_offline_resolver_works_with_network_blocked(self):
        # Prove the offline resolver never performs network access: break the socket
        # factory and confirm the adapter (and the full command) still work.
        original_socket = socket.socket
        socket.socket = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network access is blocked in this test"))
        try:
            facts = _ResolverFacts(
                research_spec_id="research_spec_demo",
                organism="mouse",
                tissue="",
                condition="tumor vs normal",
                comparison_groups=("tumor", "normal"),
            )
            code, bundle, _report = OfflineScopeResolverAdapter().resolve(facts)
            self.assertEqual(code, CODE_SCOPE_DRAFT_CREATED)
            self.assertEqual(bundle["status"], DRAFT_STATUS)
            result = resolve_scope(_normalizer_draft(), project_id=PROJECT_ID)
            self.assertEqual(result.status, STATUS_SCOPE_DRAFT_CREATED)
        finally:
            socket.socket = original_socket

    def test_inputs_are_not_mutated(self):
        spec = _draft_spec(research_question=TOY_REQUEST, organism="mouse", comparison_groups=["tumor", "normal"])
        spec_before = copy.deepcopy(spec.to_dict())
        policy = _usable_policy()
        policy_before = copy.deepcopy(policy.to_dict())
        caller_facts = {"context": "synthetic"}
        caller_before = copy.deepcopy(caller_facts)
        resolve_scope(spec, policy, project_id=PROJECT_ID, caller_facts=caller_facts)
        self.assertEqual(spec.to_dict(), spec_before)
        self.assertEqual(policy.to_dict(), policy_before)
        self.assertEqual(caller_facts, caller_before)

    def test_normalizer_result_input_is_not_mutated(self):
        nr = _normalizer_draft()
        before = copy.deepcopy(nr.to_dict())
        resolve_scope(nr, project_id=PROJECT_ID)
        self.assertEqual(nr.to_dict(), before)


class BoundedContractTests(unittest.TestCase):
    def test_status_and_reason_code_vocabularies_are_bounded(self):
        self.assertEqual(len(STATUSES), 6)
        self.assertEqual(len(set(STATUSES)), 6)
        self.assertEqual(len(set(REASON_CODES)), len(REASON_CODES))

    def test_result_projection_has_stable_keys_and_no_ontology_id(self):
        result = resolve_scope(_normalizer_draft(), project_id=PROJECT_ID)
        data = result.to_dict()
        self.assertEqual(data["status"], result.status)
        # The bundle is a bare scope projection — it carries no real ontology id and
        # is not marked authoritative.
        bundle = data["scope_bundle"]
        self.assertNotIn("ontology_id", bundle)
        self.assertNotIn("mapped_id", bundle)
        self.assertEqual(bundle["status"], DRAFT_STATUS)

    def test_custom_synthetic_vocabulary_is_honoured(self):
        # A caller-supplied synthetic vocabulary that does not know "mouse" makes
        # the same explicit organism unsupported — proving the vocab is the only
        # recognition authority and nothing is hard-coded as a real fact.
        narrow = ScopeVocabulary(species=("human",), tissues=(), conditions=())
        spec = _draft_spec(research_question=TOY_REQUEST, organism="mouse", comparison_groups=["tumor", "normal"])
        result = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID, vocabulary=narrow)
        self.assertEqual(result.status, STATUS_UNSUPPORTED_SCOPE)

    def test_result_is_a_frozen_inert_dataclass(self):
        result = resolve_scope(_normalizer_draft(), project_id=PROJECT_ID)
        self.assertIsInstance(result, ScopeResolutionResult)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.status = "tampered"  # frozen — the result cannot be mutated in place


if __name__ == "__main__":
    unittest.main()
