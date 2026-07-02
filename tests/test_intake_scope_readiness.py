"""Unit tests for the local offline scope-readiness preflight (WP-06f / T-06-06).

Covers, for the bounded local/offline scope-readiness preflight over synthetic toy
drafts and the already-inert WP-06e scope-resolution output only (no real
user/research content, no real human-derived data, no external LLM/provider/
ontology/search/network call, no persistence, no event, no granted approval, no
project stage transition, no child project):

- a consistent ``scope_draft_created`` resolution over an explicit toy draft →
  ``ready_for_review`` (inert; never a grant to execute), with a mapping-projection
  input reaching the same verdict,
- a ``needs_clarification`` / unsupported scope resolution → ``clarification_required``
  and never ready,
- a support-scope stop → ``stopped_by_upstream_gate``; a missing / approval-needed
  policy → ``approval_needed``; an upstream malformed reject → ``rejected_inconsistent``,
- an invalid project id, a non-resolution input, and a missing bundle/report fail
  closed,
- a mismatched research-spec/bundle/report identifier (and a mismatched or non-draft
  ``source``) fail closed,
- an authoritative-looking projection (a real ontology id or a truthy authority
  flag) and a non-``draft`` projection fail closed,
- a fabricated / untraceable axis value (not stated by the draft) fails closed,
- a silently dropped explicit fact (stated by the draft, on no axis, and not kept as
  an open ambiguity) fails closed,
- an empty scope can never be ready,
- the verdict is byte-deterministic, works with the network blocked, never mutates
  its inputs, is a frozen inert dataclass, and uses the bounded status + reason-code
  vocabulary.
"""

import copy
import dataclasses
import socket
import unittest

from auto_bioinfo.core.schemas import ResearchSpec
from auto_bioinfo.intake.policy_builder import build_initial_policy
from auto_bioinfo.intake.question_normalizer import normalize_question
from auto_bioinfo.intake.scope_readiness import (
    CODE_APPROVAL_NEEDED,
    CODE_AUTHORITATIVE_PROJECTION,
    CODE_DROPPED_UNKNOWN_AXIS,
    CODE_EMPTY_SCOPE,
    CODE_IDENTIFIER_MISMATCH,
    CODE_MISSING_PROJECTION,
    CODE_NON_DRAFT_PROJECTION,
    CODE_OPEN_AMBIGUITY,
    CODE_PROJECT_ID_MALFORMED,
    CODE_READY_FOR_REVIEW,
    CODE_RESOLUTION_MALFORMED,
    CODE_SOURCE_MISMATCH,
    CODE_STOPPED_BY_UPSTREAM_GATE,
    CODE_UNSUPPORTED_SCOPE,
    CODE_UNTRACEABLE_SCOPE,
    CODE_UPSTREAM_REJECTED,
    REASON_CODES,
    STATUS_APPROVAL_NEEDED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_READY_FOR_REVIEW,
    STATUS_REJECTED_INCONSISTENT,
    STATUS_STOPPED_BY_UPSTREAM_GATE,
    STATUSES,
    ScopeReadinessResult,
    assess_scope_readiness,
)
from auto_bioinfo.intake.scope_resolver import DRAFT_STATUS, resolve_scope

PROJECT_ID = "proj_demo_01"
TOY_REQUEST = "Find differentially expressed genes between tumor and normal in mouse RNA-seq data"
VAGUE_REQUEST = "Identify differentially expressed genes in the rna-seq expression dataset"


def _usable_policy(**overrides):
    base = {"data_sensitivity": "internal", "network": "local_only"}
    base.update(overrides)
    outcome = build_initial_policy(base, project_id=PROJECT_ID)
    assert outcome.built, outcome.reason_code
    return outcome


def _draft_spec(**overrides):
    base = dict(project_id=PROJECT_ID, research_question=VAGUE_REQUEST, status=DRAFT_STATUS)
    base.update(overrides)
    return ResearchSpec(**base)


def _ready_resolution():
    """A real WP-06e ``scope_draft_created`` resolution over an explicit toy draft."""
    spec = _draft_spec(research_question=TOY_REQUEST, organism="mouse", tissue="liver", comparison_groups=["tumor", "normal"])
    resolution = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
    assert resolution.scope_draft_created, resolution.reason_code
    return spec, resolution


class ReadyForReviewTests(unittest.TestCase):
    def test_consistent_scope_draft_is_ready_for_review(self):
        spec, resolution = _ready_resolution()
        result = assess_scope_readiness(resolution, spec, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_READY_FOR_REVIEW)
        self.assertEqual(result.reason_code, CODE_READY_FOR_REVIEW)
        self.assertTrue(result.ready)
        self.assertIsNotNone(result.scope_bundle)
        self.assertEqual(result.scope_bundle["status"], DRAFT_STATUS)
        # Ready is a review signal, never a grant to execute — the projection stays inert.
        self.assertNotIn("ontology_id", result.scope_bundle)
        self.assertTrue(result.findings)

    def test_ready_without_source_still_holds(self):
        _spec, resolution = _ready_resolution()
        result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_READY_FOR_REVIEW)

    def test_ready_from_mapping_projection_input(self):
        _spec, resolution = _ready_resolution()
        result = assess_scope_readiness(resolution.to_dict(), project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_READY_FOR_REVIEW)
        self.assertEqual(result.reason_code, CODE_READY_FOR_REVIEW)

    def test_ready_from_normalizer_source(self):
        norm = normalize_question(TOY_REQUEST, _usable_policy(), project_id=PROJECT_ID)
        self.assertTrue(norm.draft_created)
        resolution = resolve_scope(norm, project_id=PROJECT_ID)
        self.assertTrue(resolution.scope_draft_created)
        result = assess_scope_readiness(resolution, norm, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_READY_FOR_REVIEW)
        # The unknown tissue is still surfaced as an open ambiguity, not dropped.
        self.assertIn("tissue", result.open_questions)


class UpstreamGatePassThroughTests(unittest.TestCase):
    def test_needs_clarification_is_not_ready(self):
        resolution = resolve_scope(_draft_spec(), _usable_policy(), project_id=PROJECT_ID)
        self.assertTrue(resolution.needs_clarification)
        result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_CLARIFICATION_REQUIRED)
        self.assertEqual(result.reason_code, CODE_OPEN_AMBIGUITY)

    def test_unsupported_scope_stays_clarification(self):
        spec = _draft_spec(research_question="dragon rna-seq between groupa and groupb", organism="dragon", comparison_groups=["groupa", "groupb"])
        resolution = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        self.assertTrue(resolution.unsupported_scope)
        result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_CLARIFICATION_REQUIRED)
        self.assertEqual(result.reason_code, CODE_UNSUPPORTED_SCOPE)

    def test_support_scope_stop_is_carried_through(self):
        spec = _draft_spec(
            research_question="deploy the model and call the external OpenAI provider api", organism="human", comparison_groups=["tumor", "normal"]
        )
        resolution = resolve_scope(spec, _usable_policy(), project_id=PROJECT_ID)
        result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_STOPPED_BY_UPSTREAM_GATE)
        self.assertEqual(result.reason_code, CODE_STOPPED_BY_UPSTREAM_GATE)

    def test_missing_policy_is_approval_needed(self):
        resolution = resolve_scope(_draft_spec(), None, project_id=PROJECT_ID)
        self.assertTrue(resolution.approval_needed)
        result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_APPROVAL_NEEDED)
        self.assertEqual(result.reason_code, CODE_APPROVAL_NEEDED)

    def test_upstream_malformed_reject_stays_rejected(self):
        resolution = resolve_scope(_draft_spec(research_question=TOY_REQUEST, organism="mouse", status="locked"), _usable_policy(), project_id=PROJECT_ID)
        self.assertEqual(resolution.status, "rejected_malformed")
        result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_UPSTREAM_REJECTED)


class MalformedInputTests(unittest.TestCase):
    def test_invalid_project_id_fails_closed(self):
        _spec, resolution = _ready_resolution()
        result = assess_scope_readiness(resolution, project_id="Not An Id")
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_PROJECT_ID_MALFORMED)

    def test_non_resolution_input_fails_closed(self):
        for bad in (None, True, 1, "ready", ["resolution"], {"status": "not_a_scope_status"}):
            result = assess_scope_readiness(bad, project_id=PROJECT_ID)
            self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT, bad)
            self.assertEqual(result.reason_code, CODE_RESOLUTION_MALFORMED, bad)

    def test_scope_draft_without_projections_fails_closed(self):
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        data["scope_bundle"] = None
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_MISSING_PROJECTION)


class ConsistencyTests(unittest.TestCase):
    def test_identifier_mismatch_fails_closed(self):
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        data["scope_bundle"]["research_spec_id"] = "research_spec_tampered"
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_IDENTIFIER_MISMATCH)

    def test_source_id_mismatch_fails_closed(self):
        _spec, resolution = _ready_resolution()
        other_spec = _draft_spec(research_question="a different toy question about human liver", organism="human")
        result = assess_scope_readiness(resolution, other_spec, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_SOURCE_MISMATCH)

    def test_locked_source_fails_closed(self):
        spec, resolution = _ready_resolution()
        locked = _draft_spec(research_question=TOY_REQUEST, organism="mouse", tissue="liver", comparison_groups=["tumor", "normal"], status="locked")
        result = assess_scope_readiness(resolution, locked, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_SOURCE_MISMATCH)

    def test_authoritative_ontology_id_fails_closed(self):
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        data["scope_bundle"]["ontology_id"] = "NCBITaxon:10090"  # a real-looking identifier
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_AUTHORITATIVE_PROJECTION)

    def test_authority_flag_fails_closed(self):
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        data["scope_bundle"]["authoritative"] = True
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_AUTHORITATIVE_PROJECTION)

    def test_non_draft_projection_fails_closed(self):
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        data["scope_bundle"]["status"] = "resolved"
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_NON_DRAFT_PROJECTION)

    def test_fabricated_untraceable_axis_value_fails_closed(self):
        # A species value the draft never stated (and that is only vocab-known) must
        # not appear on a ready scope — it is not traceable to the WP-06e path.
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        data["scope_bundle"]["tissues"] = ["brain"]  # draft stated liver, not brain
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_UNTRACEABLE_SCOPE)

    def test_silently_dropped_fact_fails_closed(self):
        # The draft states an organism, but the bundle neither lists it on the
        # species axis nor keeps it as an open ambiguity → a silent drop.
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        data["scope_bundle"]["species"] = []
        data["ambiguity_report"]["items"] = [it for it in data["ambiguity_report"]["items"] if it.get("subject") != "organism"]
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_DROPPED_UNKNOWN_AXIS)

    def test_empty_scope_can_never_be_ready(self):
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        for axis in ("species", "tissues", "conditions", "comparisons"):
            data["scope_bundle"][axis] = []
        result = assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(result.status, STATUS_REJECTED_INCONSISTENT)
        self.assertEqual(result.reason_code, CODE_EMPTY_SCOPE)


class DeterminismAndIsolationTests(unittest.TestCase):
    def test_verdict_is_byte_deterministic(self):
        _spec, resolution = _ready_resolution()
        a = assess_scope_readiness(resolution, project_id=PROJECT_ID).to_dict()
        b = assess_scope_readiness(resolution, project_id=PROJECT_ID).to_dict()
        self.assertEqual(a, b)

    def test_works_with_network_blocked(self):
        original_socket = socket.socket
        socket.socket = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network access is blocked in this test"))
        try:
            _spec, resolution = _ready_resolution()
            result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
            self.assertEqual(result.status, STATUS_READY_FOR_REVIEW)
        finally:
            socket.socket = original_socket

    def test_inputs_are_not_mutated(self):
        spec, resolution = _ready_resolution()
        spec_before = copy.deepcopy(spec.to_dict())
        resolution_before = copy.deepcopy(resolution.to_dict())
        assess_scope_readiness(resolution, spec, project_id=PROJECT_ID)
        self.assertEqual(spec.to_dict(), spec_before)
        self.assertEqual(resolution.to_dict(), resolution_before)

    def test_mapping_input_is_not_mutated(self):
        _spec, resolution = _ready_resolution()
        data = resolution.to_dict()
        before = copy.deepcopy(data)
        assess_scope_readiness(data, project_id=PROJECT_ID)
        self.assertEqual(data, before)


class BoundedContractTests(unittest.TestCase):
    def test_status_and_reason_code_vocabularies_are_bounded(self):
        self.assertEqual(len(STATUSES), 5)
        self.assertEqual(len(set(STATUSES)), 5)
        self.assertEqual(len(set(REASON_CODES)), len(REASON_CODES))

    def test_result_is_a_frozen_inert_dataclass(self):
        _spec, resolution = _ready_resolution()
        result = assess_scope_readiness(resolution, project_id=PROJECT_ID)
        self.assertIsInstance(result, ScopeReadinessResult)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.status = "tampered"

    def test_to_dict_has_stable_readiness_flags(self):
        _spec, resolution = _ready_resolution()
        data = assess_scope_readiness(resolution, project_id=PROJECT_ID).to_dict()
        self.assertTrue(data["ready"])
        self.assertFalse(data["rejected"])
        self.assertEqual(data["upstream_status"], "scope_draft_created")


if __name__ == "__main__":
    unittest.main()
