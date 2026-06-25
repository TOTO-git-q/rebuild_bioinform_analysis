import unittest

from auto_bioinfo.core import common, validation
from auto_bioinfo.core.common import Actor, ExternalIdentifier, SchemaValidationError, dataclass_json_schema
from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.core.schemas import (
    CLAIM_LEVELS,
    FEASIBILITY_DECISIONS,
    AmbiguityReport,
    ApprovalDecision,
    ApprovalRequest,
    DatasetFeasibilityReport,
    DatasetProfile,
    DependencyGraph,
    EvidenceGap,
    EvidencePlan,
    OntologyMapping,
    OriginalRequest,
    Project,
    ProjectPolicy,
    ResearchSpec,
    ResourceCandidate,
    ScopeBundle,
    SubQuestion,
)


class SchemaTest(unittest.TestCase):
    def test_stable_id_is_deterministic_and_content_addressed(self):
        a = make_stable_id("x", {"k": 1, "j": 2})
        b = make_stable_id("x", {"j": 2, "k": 1})  # key order must not matter
        self.assertEqual(a, b)
        self.assertNotEqual(a, make_stable_id("x", {"k": 1, "j": 3}))

    def test_research_spec_roundtrip_and_id(self):
        spec = ResearchSpec(research_question="q", project_id="p", organism="human").to_dict()
        self.assertTrue(spec["research_spec_id"].startswith("research_spec_"))
        self.assertEqual(spec["organism"], "human")
        self.assertEqual(spec["claim_ceiling"], "association")


class ValidationGuardrailTest(unittest.TestCase):
    def test_verified_dataset_cannot_be_mock(self):
        bad = {"verified": True, "source_status": "mock_placeholder", "accession": "AUTO_X"}
        self.assertTrue(validation.validate_no_unknown_verified_dataset(bad))
        good = {"verified": True, "source_status": "committed_fixture", "accession": "FIXTURE-1"}
        self.assertEqual(validation.validate_no_unknown_verified_dataset(good), [])

    def test_claim_ceiling_blocks_overclaim(self):
        self.assertTrue(validation.validate_claim_ceiling({"claim_level": "causal_support"}, "association"))
        self.assertEqual(validation.validate_claim_ceiling({"claim_level": "association"}, "association"), [])

    def test_claim_levels_are_ordered(self):
        self.assertEqual(CLAIM_LEVELS[0], "descriptive")
        self.assertLess(CLAIM_LEVELS.index("association"), CLAIM_LEVELS.index("causal_support"))


# --- WP-02a / T-02-01: common cross-cutting contract types -------------------


class CommonContractTypesTest(unittest.TestCase):
    """T-02-01: deterministic serialisation + explicit failure for IDs, schema
    versions, actors, timestamps, hashes, and external identifiers."""

    def test_canonical_json_is_deterministic_and_key_order_independent(self):
        self.assertEqual(common.canonical_json({"b": 1, "a": 2}), common.canonical_json({"a": 2, "b": 1}))
        self.assertEqual(common.canonical_json({"a": 2, "b": 1}), '{"a":2,"b":1}')
        self.assertEqual(common.content_hash({"a": 1}), common.content_hash({"a": 1}))

    def test_identifier_validation_positive_and_negative(self):
        self.assertEqual(common.validate_identifier("research_spec_ab12cd34"), [])
        self.assertEqual(common.validate_identifier("project.v1-2"), [])
        self.assertTrue(common.validate_identifier(""))  # empty
        self.assertTrue(common.validate_identifier("has space"))  # whitespace
        self.assertTrue(common.validate_identifier("UPPER"))  # not lowercase token
        self.assertTrue(common.validate_identifier(123))  # not a string

    def test_schema_version_validation(self):
        self.assertEqual(common.validate_schema_version("v5.canonical/0.1"), [])
        self.assertTrue(common.validate_schema_version("5.canonical.0.1"))  # malformed
        self.assertTrue(common.validate_schema_version(""))

    def test_hash_validation_requires_64_lowercase_hex(self):
        good = common.content_hash({"x": 1})
        self.assertEqual(common.validate_hash(good), [])
        self.assertTrue(common.validate_hash("ABC"))  # too short / uppercase
        self.assertTrue(common.validate_hash(good.upper()))  # uppercase rejected
        self.assertTrue(common.validate_hash(""))

    def test_timestamp_validation_requires_timezone(self):
        self.assertEqual(common.validate_timestamp("2026-06-26T12:00:00+00:00"), [])
        self.assertTrue(common.validate_timestamp("2026-06-26T12:00:00"))  # naive, no offset
        self.assertTrue(common.validate_timestamp("not-a-time"))
        self.assertTrue(common.validate_timestamp(""))

    def test_actor_validation_and_explicit_raise(self):
        ok = Actor(actor_type="human", actor_id="alice")
        self.assertEqual(ok.errors(), [])
        ok.validate()  # does not raise
        self.assertTrue(Actor(actor_type="robot", actor_id="x").errors())  # bad type
        self.assertTrue(Actor(actor_type="human", actor_id="").errors())  # empty id
        with self.assertRaises(SchemaValidationError):
            Actor(actor_type="robot", actor_id="").validate()

    def test_external_identifier_format_verifiability(self):
        self.assertEqual(ExternalIdentifier(scheme="PMID", value="123456").errors(), [])
        self.assertEqual(ExternalIdentifier(scheme="GEO", value="GSE12345").errors(), [])
        self.assertEqual(ExternalIdentifier(scheme="DOI", value="10.1000/xyz123").errors(), [])
        # boundary: shortest valid PMID
        self.assertEqual(ExternalIdentifier(scheme="PMID", value="1").errors(), [])
        # negative: value does not match scheme -> unverifiable
        self.assertTrue(ExternalIdentifier(scheme="PMID", value="GSE1").errors())
        self.assertTrue(ExternalIdentifier(scheme="UNKNOWN", value="x").errors())

    def test_external_identifier_verified_requires_source(self):
        self.assertTrue(ExternalIdentifier(scheme="PMID", value="123", verified=True).errors())
        self.assertEqual(
            ExternalIdentifier(scheme="PMID", value="123", verified=True, verification_source="eutils").errors(),
            [],
        )


# --- WP-02a / T-02-02: Project & Policy and Approval contracts ---------------


class OriginalRequestContractTest(unittest.TestCase):
    def _req(self, **kw):
        base = dict(project_id="proj_1", original_text="Find DEGs in GSE12345 between treated and control.")
        base.update(kw)
        return OriginalRequest(**base)

    def test_original_text_is_hash_bound_and_id_stable(self):
        data = self._req().to_dict()
        self.assertTrue(data["request_id"].startswith("original_request_"))
        self.assertEqual(data["original_text_sha256"], common.content_hash(data["original_text"]))
        self.assertEqual(validation.validate_original_request(data), [])

    def test_normalization_does_not_overwrite_original(self):
        req = self._req()
        normalized = req.with_normalized_text("normalized question")
        self.assertEqual(normalized["original_text"], req.original_text)
        self.assertEqual(normalized["normalized_text"], "normalized question")
        # the hash still tracks the original, and validation still passes
        self.assertEqual(normalized["original_text_sha256"], common.content_hash(req.original_text))
        self.assertEqual(validation.validate_original_request(normalized), [])

    def test_tampered_original_text_is_detected(self):
        data = self._req().to_dict()
        data["original_text"] = "SOMETHING ELSE"  # edit the original, leave the hash stale
        errors = validation.validate_original_request(data)
        self.assertTrue(any("does not match original_text" in e for e in errors))

    def test_empty_original_text_fails(self):
        data = self._req(original_text="").to_dict()
        self.assertTrue(validation.validate_original_request(data))


class ProjectPolicyContractTest(unittest.TestCase):
    def _policy(self, **kw):
        base = dict(project_id="proj_1", execution_mode="DEMO", automation_level="A1")
        base.update(kw)
        return ProjectPolicy(**base)

    def test_policy_is_content_hashable_and_stable_id(self):
        a = self._policy().to_dict()
        b = self._policy().to_dict()
        self.assertEqual(a["project_policy_id"], b["project_policy_id"])
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertTrue(a["project_policy_id"].startswith("project_policy_"))
        self.assertEqual(validation.validate_project_policy(a), [])

    def test_policy_validates_binding_mode_and_version(self):
        self.assertTrue(validation.validate_project_policy(self._policy(execution_mode="BOGUS").to_dict()))
        self.assertTrue(validation.validate_project_policy(self._policy(automation_level="A9").to_dict()))
        self.assertTrue(validation.validate_project_policy(self._policy(policy_version=0).to_dict()))
        self.assertTrue(validation.validate_project_policy(self._policy(project_id="").to_dict()))

    def test_tampered_policy_breaks_hash_and_id(self):
        data = self._policy().to_dict()
        data["execution_mode"] = "REAL"  # flip mode, leave hash/id stale
        errors = validation.validate_project_policy(data)
        self.assertTrue(any("content_hash" in e for e in errors))
        self.assertTrue(any("project_policy_id" in e for e in errors))

    def test_boundary_lowest_and_highest_automation_levels(self):
        self.assertEqual(validation.validate_project_policy(self._policy(automation_level="A0").to_dict()), [])
        self.assertEqual(validation.validate_project_policy(self._policy(automation_level="A3").to_dict()), [])


class ApprovalContractTest(unittest.TestCase):
    def _request(self, **kw):
        base = dict(project_id="proj_1", subject_type="ResearchSpec", subject_id="rs_1", subject_version=2, gate="G-Q")
        base.update(kw)
        return ApprovalRequest(**base)

    def _decision(self, request_dict, **kw):
        base = dict(
            approval_request_id=request_dict["approval_request_id"],
            project_id=request_dict["project_id"],
            subject_type=request_dict["subject_type"],
            subject_id=request_dict["subject_id"],
            subject_version=request_dict["subject_version"],
            decision="approved",
        )
        base.update(kw)
        return ApprovalDecision(**base)

    def test_request_binds_subject_version(self):
        data = self._request().to_dict()
        self.assertTrue(data["approval_request_id"].startswith("approval_request_"))
        self.assertEqual(validation.validate_approval_request(data), [])
        self.assertTrue(validation.validate_approval_request(self._request(subject_version=0).to_dict()))
        self.assertTrue(validation.validate_approval_request(self._request(state="bogus").to_dict()))

    def test_decision_must_bind_exact_subject(self):
        req = self._request().to_dict()
        good = self._decision(req).to_dict()
        self.assertEqual(validation.validate_approval_decision(good, request=req), [])
        # decision pointing at a different version is rejected against the request
        bad = self._decision(req, subject_version=1).to_dict()
        errors = validation.validate_approval_decision(bad, request=req)
        self.assertTrue(any("same subject" in e for e in errors))

    def test_decision_enum_and_version_validation(self):
        req = self._request().to_dict()
        self.assertTrue(validation.validate_approval_decision(self._decision(req, decision="maybe").to_dict()))
        self.assertTrue(validation.validate_approval_decision(self._decision(req, subject_version=0).to_dict()))

    def test_cannot_approve_superseded_version_as_current(self):
        req = self._request(subject_version=2).to_dict()
        decision = self._decision(req).to_dict()  # approves version 2
        # current is version 3 -> approving the superseded v2 as current is blocked
        errors = validation.validate_approval_decision(decision, request=req, current_version=3)
        self.assertTrue(any("superseded" in e for e in errors))
        # approving the current version is fine
        self.assertEqual(validation.validate_approval_decision(decision, request=req, current_version=2), [])


class SchemaSnapshotTest(unittest.TestCase):
    """JSON-schema snapshot coverage for the WP-02a slice using the stdlib-only
    project helper (no new dependency)."""

    def test_required_fields_snapshot_is_stable(self):
        expected_required = {
            Project: ["project_id", "title"],
            OriginalRequest: ["project_id", "original_text"],
            ProjectPolicy: ["project_id", "execution_mode"],
            ApprovalRequest: ["project_id", "subject_type", "subject_id", "subject_version", "gate"],
            ApprovalDecision: ["approval_request_id", "project_id", "subject_type", "subject_id", "subject_version", "decision"],
        }
        for cls, required in expected_required.items():
            schema = dataclass_json_schema(cls)
            self.assertEqual(schema["type"], "object")
            self.assertEqual(schema["title"], cls.__name__)
            self.assertEqual(schema["required"], required)
            for name in required:
                self.assertIn(name, schema["properties"])

    def test_property_types_are_derived(self):
        schema = dataclass_json_schema(ProjectPolicy)
        self.assertEqual(schema["properties"]["policy_version"]["type"], "integer")
        self.assertEqual(schema["properties"]["network_policy"]["type"], "object")
        self.assertEqual(schema["properties"]["project_id"]["type"], "string")

    def test_non_dataclass_raises(self):
        with self.assertRaises(SchemaValidationError):
            dataclass_json_schema(int)


# --- WP-02b / T-02-03: ResearchSpec, AmbiguityReport, ScopeBundle, Ontology --


class ResearchSpecContractTest(unittest.TestCase):
    def _spec(self, **kw):
        base = dict(research_question="Which genes change?", project_id="proj_1")
        base.update(kw)
        return ResearchSpec(**base)

    def test_valid_spec_passes_and_unknowns_are_explicit(self):
        data = self._spec(open_questions=["Organism not stated; left empty rather than assumed."]).to_dict()
        self.assertEqual(validation.validate_research_spec(data), [])

    def test_blank_open_question_is_rejected(self):
        # an unknown must be *stated*, never an empty placeholder
        data = self._spec(open_questions=["  "]).to_dict()
        errors = validation.validate_research_spec(data)
        self.assertTrue(any("open_questions" in e for e in errors))

    def test_invalid_claim_ceiling_rejected(self):
        data = self._spec(claim_ceiling="telepathy").to_dict()
        self.assertTrue(any("claim_ceiling" in e for e in validation.validate_research_spec(data)))

    def test_missing_question_or_bad_project_id_rejected(self):
        self.assertTrue(validation.validate_research_spec(self._spec(research_question="").to_dict()))
        self.assertTrue(validation.validate_research_spec(self._spec(project_id="Has Space").to_dict()))


class AmbiguityReportContractTest(unittest.TestCase):
    def _report(self, items, **kw):
        return AmbiguityReport(research_spec_id="rs_1", items=items, **kw)

    def test_open_ambiguity_is_surfaced_not_guessed(self):
        report = self._report([{"subject": "organism", "impact": "scope unconstrained", "status": "open"}]).to_dict()
        self.assertEqual(validation.validate_ambiguity_report(report), [])
        self.assertTrue(report["ambiguity_report_id"].startswith("ambiguity_report_"))

    def test_assumed_item_requires_explicit_default(self):
        bad = self._report([{"subject": "tissue", "impact": "narrows scope", "status": "assumed"}]).to_dict()
        errors = validation.validate_ambiguity_report(bad)
        self.assertTrue(any("default_value" in e for e in errors))
        good = self._report([{"subject": "tissue", "impact": "narrows scope", "status": "assumed", "default_value": "whole_blood"}]).to_dict()
        self.assertEqual(validation.validate_ambiguity_report(good), [])

    def test_item_missing_subject_or_bad_status_rejected(self):
        self.assertTrue(validation.validate_ambiguity_report(self._report([{"impact": "x", "status": "open"}]).to_dict()))
        self.assertTrue(validation.validate_ambiguity_report(self._report([{"subject": "x", "impact": "y", "status": "bogus"}]).to_dict()))

    def test_open_items_helper(self):
        report = AmbiguityReport(
            research_spec_id="rs_1",
            items=[{"subject": "a", "impact": "b", "status": "open"}, {"subject": "c", "impact": "d", "status": "resolved"}],
        )
        self.assertEqual(len(report.open_items()), 1)


class ScopeBundleContractTest(unittest.TestCase):
    def _scope(self, **kw):
        base = dict(research_spec_id="rs_1", species=["human"], tissues=["tissue_x"], conditions=["condition_a"], comparisons=["condition_a", "condition_b"])
        base.update(kw)
        return ScopeBundle(**base)

    def test_well_formed_scope_passes(self):
        self.assertEqual(validation.validate_scope_bundle(self._scope().to_dict()), [])

    def test_empty_critical_scope_rejected(self):
        data = self._scope(species=[], tissues=[], conditions=[], comparisons=[]).to_dict()
        errors = validation.validate_scope_bundle(data)
        self.assertTrue(any("scope is empty" in e for e in errors))

    def test_contradictory_scope_rejected(self):
        # the same value listed twice in one axis is contradictory
        data = self._scope(species=["human", "human"]).to_dict()
        self.assertTrue(any("contradictory" in e for e in validation.validate_scope_bundle(data)))

    def test_self_comparison_rejected(self):
        data = self._scope(comparisons=["condition_a", "condition_a"]).to_dict()
        errors = validation.validate_scope_bundle(data)
        self.assertTrue(any("two distinct groups" in e for e in errors))

    def test_blank_only_axis_is_not_populated_scope(self):
        data = self._scope(species=["  "], tissues=[], conditions=[], comparisons=[]).to_dict()
        errors = validation.validate_scope_bundle(data)
        self.assertTrue(any("non-empty" in e for e in errors))
        self.assertTrue(any("scope is empty" in e for e in errors))

    def test_blank_entry_mixed_with_real_value_rejected(self):
        data = self._scope(species=["human", "  "]).to_dict()
        self.assertTrue(any("non-empty" in e for e in validation.validate_scope_bundle(data)))

    def test_require_comparison_flag(self):
        data = self._scope(comparisons=[]).to_dict()
        self.assertEqual(validation.validate_scope_bundle(data), [])  # tissue/species still populated
        self.assertTrue(validation.validate_scope_bundle(data, require_comparison=True))


class OntologyMappingContractTest(unittest.TestCase):
    def _mapping(self, **kw):
        base = dict(research_spec_id="rs_1", source_term="liver", mapping_source="UBERON")
        base.update(kw)
        return OntologyMapping(**base)

    def test_resolved_mapping_requires_id_and_confidence(self):
        good = self._mapping(status="mapped", mapped_id="UBERON:0002107", confidence=0.95).to_dict()
        self.assertEqual(validation.validate_ontology_mapping(good), [])
        self.assertTrue(good["ontology_mapping_id"].startswith("ontology_mapping_"))

    def test_low_confidence_cannot_be_recorded_as_fact(self):
        bad = self._mapping(status="mapped", mapped_id="UBERON:0002107", confidence=0.2).to_dict()
        errors = validation.validate_ontology_mapping(bad)
        self.assertTrue(any("low-confidence" in e for e in errors))

    def test_unresolved_must_not_invent_id(self):
        bad = self._mapping(status="unresolved", mapped_id="UBERON:9999999").to_dict()
        self.assertTrue(any("invent an identifier" in e for e in validation.validate_ontology_mapping(bad)))
        good = self._mapping(status="unresolved", candidates=[{"id": "UBERON:1", "score": 0.3}]).to_dict()
        self.assertEqual(validation.validate_ontology_mapping(good), [])

    def test_bad_status_and_confidence_range(self):
        self.assertTrue(validation.validate_ontology_mapping(self._mapping(status="totally_sure").to_dict()))
        self.assertTrue(validation.validate_ontology_mapping(self._mapping(status="mapped", mapped_id="x", confidence=1.7).to_dict()))


# --- WP-02b / T-02-04: SubQuestion, DependencyGraph, EvidencePlan, Gap --------


class SubQuestionContractTest(unittest.TestCase):
    def _sub(self, question, **kw):
        return SubQuestion(research_spec_id="rs_1", question=question, **kw).to_dict()

    def test_single_purpose_question_passes(self):
        data = self._sub("Which genes are differentially expressed between condition_a and condition_b?")
        self.assertEqual(validation.validate_subquestion(data), [])

    def test_compound_question_rejected(self):
        data = self._sub("Which genes change and how are the pathways enriched?")
        errors = validation.validate_subquestion(data)
        self.assertTrue(any("single purpose" in e for e in errors))

    def test_coordinated_second_predicate_rejected(self):
        # a fresh subject taking its own verb is a second purpose, even without an
        # interrogative immediately after the conjunction
        self.assertFalse(validation.subquestion_is_single_purpose("Which genes change and pathways are enriched?"))
        data = self._sub("Which genes change and pathways are enriched?")
        self.assertTrue(any("single purpose" in e for e in validation.validate_subquestion(data)))

    def test_multiple_question_marks_rejected(self):
        self.assertFalse(validation.subquestion_is_single_purpose("Which genes change? Are they enriched?"))
        self.assertFalse(validation.subquestion_is_single_purpose("A; B?"))

    def test_between_range_stays_single_purpose(self):
        self.assertTrue(validation.subquestion_is_single_purpose("Which genes differ between A and B?"))

    def test_between_range_with_trailing_verb_stays_single_purpose(self):
        # the range conjunction closes "between X and Y" — a finite verb after the
        # range is the question's own predicate, not a second purpose
        for question in (
            "Which genes between A and B are differentially expressed?",
            "Which pathways between HFD and ND are enriched?",
        ):
            self.assertTrue(validation.subquestion_is_single_purpose(question), question)
            self.assertEqual(validation.validate_subquestion(self._sub(question)), [])

    def test_compound_after_between_range_still_rejected(self):
        # a genuine second predicate is caught even when a between-range precedes it
        question = "Which genes between A and B change and pathways are enriched?"
        self.assertFalse(validation.subquestion_is_single_purpose(question))
        self.assertTrue(any("single purpose" in e for e in validation.validate_subquestion(self._sub(question))))

    def test_binding_to_research_spec_enforced(self):
        data = self._sub("Which genes change between A and B?")
        self.assertEqual(validation.validate_subquestion(data, research_spec_id="rs_1"), [])
        self.assertTrue(validation.validate_subquestion(data, research_spec_id="rs_other"))

    def test_bad_claim_ceiling_rejected(self):
        data = self._sub("Which genes change between A and B?", claim_ceiling="omniscient")
        self.assertTrue(any("claim_ceiling" in e for e in validation.validate_subquestion(data)))


class DependencyGraphContractTest(unittest.TestCase):
    def test_acyclic_graph_passes_and_orders_deterministically(self):
        graph = DependencyGraph(research_spec_id="rs_1", nodes=["a", "b", "c"], edges=[["b", "a"], ["c", "b"]])
        self.assertFalse(graph.has_cycle())
        self.assertEqual(validation.validate_dependency_graph(graph.to_dict()), [])
        # b depends on a, c depends on b -> a before b before c
        self.assertEqual(graph.topological_order(), ["a", "b", "c"])

    def test_cycle_is_detected_and_rejected(self):
        graph = DependencyGraph(research_spec_id="rs_1", nodes=["a", "b", "c"], edges=[["a", "b"], ["b", "c"], ["c", "a"]])
        self.assertTrue(graph.has_cycle())
        errors = validation.validate_dependency_graph(graph.to_dict())
        self.assertTrue(any("cycle" in e for e in errors))
        with self.assertRaises(ValueError):
            graph.topological_order()

    def test_self_loop_and_dangling_edge_rejected(self):
        self.assertTrue(validation.validate_dependency_graph(DependencyGraph(research_spec_id="rs_1", nodes=["a"], edges=[["a", "a"]]).to_dict()))
        self.assertTrue(validation.validate_dependency_graph(DependencyGraph(research_spec_id="rs_1", nodes=["a"], edges=[["a", "z"]]).to_dict()))

    def test_serialization_is_deterministic_regardless_of_input_order(self):
        g1 = DependencyGraph(research_spec_id="rs_1", nodes=["b", "a"], edges=[["b", "a"]])
        g2 = DependencyGraph(research_spec_id="rs_1", nodes=["a", "b"], edges=[["b", "a"]])
        self.assertEqual(g1.to_dict()["nodes"], g2.to_dict()["nodes"])
        self.assertEqual(g1.to_dict()["dependency_graph_id"], g2.to_dict()["dependency_graph_id"])


class EvidencePlanContractTest(unittest.TestCase):
    def _plan(self, **kw):
        base = dict(research_spec_id="rs_1", evidence_axes=["bulk_rna_differential_expression"])
        base.update(kw)
        return EvidencePlan(**base).to_dict()

    def test_valid_plan_passes(self):
        self.assertEqual(validation.validate_evidence_plan(self._plan()), [])

    def test_plan_with_no_axis_needs_stop_reason(self):
        bare = self._plan(evidence_axes=[])
        self.assertTrue(any("evidence axis" in e for e in validation.validate_evidence_plan(bare)))
        # an explicit stop reason makes a no-axis plan acceptable
        stopped = self._plan(evidence_axes=[], stop_conditions=["No verifiable dataset available"])
        self.assertEqual(validation.validate_evidence_plan(stopped), [])

    def test_blank_stop_or_gap_does_not_excuse_missing_axis(self):
        # whitespace-only stop/gap reasons are not a meaningful explicit reason
        blank_stop = self._plan(evidence_axes=[], stop_conditions=["  "])
        self.assertTrue(any("evidence axis" in e for e in validation.validate_evidence_plan(blank_stop)))
        blank_gap = self._plan(evidence_axes=[], planned_gaps=["", "   "])
        self.assertTrue(any("evidence axis" in e for e in validation.validate_evidence_plan(blank_gap)))

    def test_bad_claim_level_rejected(self):
        self.assertTrue(validation.validate_evidence_plan(self._plan(max_claim_level="causal_certainty")))

    def test_planned_gaps_are_explicit_list(self):
        self.assertTrue(validation.validate_evidence_plan(self._plan(planned_gaps="not-a-list")))


class EvidenceGapContractTest(unittest.TestCase):
    def _gap(self, **kw):
        base = dict(research_spec_id="rs_1", subquestion_id="sq_1", description="No replication across datasets", gap_type="insufficient")
        base.update(kw)
        return EvidenceGap(**base)

    def test_valid_gap_passes_and_caps_claim(self):
        gap = self._gap(imposed_claim_ceiling="descriptive")
        self.assertEqual(validation.validate_evidence_gap(gap.to_dict()), [])
        # a gap can only pull a claim down, never up
        self.assertEqual(gap.caps_claim_level("causal_support"), "descriptive")
        self.assertEqual(gap.caps_claim_level("descriptive"), "descriptive")

    def test_gap_cannot_raise_claim(self):
        data = self._gap(imposed_claim_ceiling="causal_support").to_dict()
        data["prior_claim_level"] = "association"
        errors = validation.validate_evidence_gap(data)
        self.assertTrue(any("only cap a claim" in e for e in errors))

    def test_bad_type_status_and_ceiling_rejected(self):
        self.assertTrue(validation.validate_evidence_gap(self._gap(gap_type="vibes").to_dict()))
        self.assertTrue(validation.validate_evidence_gap(self._gap(status="ignored").to_dict()))
        self.assertTrue(validation.validate_evidence_gap(self._gap(imposed_claim_ceiling="omniscient").to_dict()))


# --- WP-02c / T-02-05: ResourceCandidate & DatasetProfile factual coverage ---


class ResourceCandidateContractTest(unittest.TestCase):
    def _candidate(self, **kw):
        base = dict(resource_name="GSE12345", resource_type="dataset_candidate", verified=False, source_status="committed_fixture")
        base.update(kw)
        return ResourceCandidate(**base)

    def test_legacy_unverified_candidate_still_constructs_and_validates(self):
        # backward compatibility: the original four-field candidate is still valid
        from dataclasses import asdict

        data = asdict(self._candidate())
        self.assertEqual(data["source_class"], "LEGACY_UNKNOWN")
        self.assertEqual(data["verification_level"], "UNVERIFIED")
        self.assertEqual(validation.validate_resource_candidate(data), [])

    def test_verified_without_provenance_facts_is_rejected(self):
        # a bare verified=True with no real accession / verification level is demoted
        from dataclasses import asdict

        bad = asdict(self._candidate(verified=True, accession="AUTO_X", source_status="mock_placeholder"))
        errors = validation.validate_resource_candidate(bad)
        self.assertTrue(errors)
        # even a non-mock candidate cannot claim verified while UNVERIFIED
        bad2 = asdict(self._candidate(verified=True, accession="GSE12345", source_status="public", verification_level="UNVERIFIED"))
        self.assertTrue(any("verified assertion" in e for e in validation.validate_resource_candidate(bad2)))

    def test_verified_with_metadata_verification_passes(self):
        from dataclasses import asdict

        good = asdict(
            self._candidate(
                verified=True,
                accession="GSE12345",
                source_status="public_database",
                source_class="PUBLIC_DATABASE",
                retrieval_mode="RECORDED_REPLAY",
                verification_level="METADATA_VERIFIED",
            )
        )
        self.assertEqual(validation.validate_resource_candidate(good), [])

    def test_bad_provenance_marker_rejected(self):
        from dataclasses import asdict

        bad = asdict(self._candidate(source_class="MADE_UP"))
        self.assertTrue(any("source_class" in e for e in validation.validate_resource_candidate(bad)))


class DatasetProfileContractTest(unittest.TestCase):
    def _profile(self, **kw):
        base = dict(dataset_id="ds_gse12345", modality="bulk_expression_matrix", organism="human", tissue="liver")
        base.update(kw)
        return DatasetProfile(**base)

    def test_legacy_minimal_profile_still_constructs_and_validates(self):
        # backward compatibility: the original four-field profile remains valid and
        # stays explicitly non-authoritative (UNVERIFIED), never rejected for being
        # merely unverified
        data = self._profile().to_dict()
        self.assertTrue(data["dataset_profile_id"].startswith("dataset_profile_"))
        self.assertEqual(data["verification_level"], "UNVERIFIED")
        self.assertEqual(validation.validate_dataset_profile(data), [])

    def test_populated_factual_profile_validates(self):
        data = self._profile(
            accession="GSE12345",
            platform="Illumina NovaSeq 6000",
            species=["Homo sapiens"],
            sample_count=4,
            samples=[
                {"sample_id": "GSM1", "group": "condition_a"},
                {"sample_id": "GSM2", "group": "condition_a"},
                {"sample_id": "GSM3", "group": "condition_b"},
                {"sample_id": "GSM4", "group": "condition_b"},
            ],
            grouping={"condition_a": ["GSM1", "GSM2"], "condition_b": ["GSM3", "GSM4"]},
            files=[{"name": "counts.tsv", "sha256": "a" * 64}],
            license="CC-BY-4.0",
            metadata_facts={"library_strategy": "RNA-Seq"},
            source_class="PUBLIC_DATABASE",
            retrieval_mode="RECORDED_REPLAY",
            verification_level="METADATA_VERIFIED",
        ).to_dict()
        self.assertEqual(validation.validate_dataset_profile(data), [])

    def test_blank_critical_fact_is_rejected(self):
        # a present-but-blank species fact is not a fact
        data = self._profile(species=["  "]).to_dict()
        self.assertTrue(any("species" in e for e in validation.validate_dataset_profile(data)))
        # a sample without an id is rejected
        data2 = self._profile(samples=[{"group": "condition_a"}]).to_dict()
        self.assertTrue(any("sample_id" in e for e in validation.validate_dataset_profile(data2)))

    def test_contradictory_facts_are_rejected(self):
        # sample_count disagreeing with the recorded samples is contradictory
        data = self._profile(sample_count=10, samples=[{"sample_id": "GSM1"}]).to_dict()
        self.assertTrue(any("contradicts" in e for e in validation.validate_dataset_profile(data)))
        # a grouping referencing an unknown sample id is contradictory
        data2 = self._profile(samples=[{"sample_id": "GSM1"}], grouping={"g": ["GSM_MISSING"]}).to_dict()
        self.assertTrue(any("unknown sample_id" in e for e in validation.validate_dataset_profile(data2)))
        # a duplicated species value is contradictory
        data3 = self._profile(species=["human", "human"]).to_dict()
        self.assertTrue(any("contradictory" in e for e in validation.validate_dataset_profile(data3)))

    def test_legacy_verified_assertion_without_facts_is_demoted(self):
        # a True legacy_verified_assertion is not authorisation while UNVERIFIED
        data = self._profile(legacy_verified_assertion=True, verification_level="UNVERIFIED").to_dict()
        self.assertTrue(any("verified assertion" in e for e in validation.validate_dataset_profile(data)))

    def test_duplicate_sample_id_is_rejected(self):
        # two sample records sharing one id are contradictory sample facts
        data = self._profile(
            sample_count=2,
            samples=[{"sample_id": "GSM1"}, {"sample_id": "GSM1"}],
        ).to_dict()
        self.assertTrue(any("duplicate sample_id" in e for e in validation.validate_dataset_profile(data)))

    def test_positive_sample_count_without_records_is_rejected(self):
        # a positive sample_count with no sample records is an unbound fact
        data = self._profile(sample_count=3).to_dict()  # samples defaults to []
        self.assertTrue(any("records none" in e for e in validation.validate_dataset_profile(data)))
        # the legacy/minimal path stays valid precisely because it claims no count
        legacy = self._profile().to_dict()
        self.assertEqual(legacy["sample_count"], 0)
        self.assertEqual(validation.validate_dataset_profile(legacy), [])

    def test_grouping_referencing_undeclared_samples_is_rejected(self):
        # a grouping that names sample ids while none are declared is not a fact basis
        data = self._profile(grouping={"case": ["s1"]}).to_dict()  # no samples declared
        self.assertTrue(any("unknown sample_id" in e for e in validation.validate_dataset_profile(data)))
        # normal populated sample facts (count == samples, grouping over declared ids) still pass
        ok = self._profile(
            sample_count=2,
            samples=[{"sample_id": "s1"}, {"sample_id": "s2"}],
            grouping={"case": ["s1"], "control": ["s2"]},
        ).to_dict()
        self.assertEqual(validation.validate_dataset_profile(ok), [])


# --- WP-02c / T-02-06: DatasetFeasibilityReport ------------------------------


class DatasetFeasibilityReportContractTest(unittest.TestCase):
    def _report(self, **kw):
        base = dict(
            research_spec_id="rs_1",
            subquestion_id="sq_1",
            dataset_profile_id="dataset_profile_abc",
            decision="usable",
            evidence_plan_id="ep_1",
            reasons=["Design matches the requested two-group contrast"],
            required_facts_checked=["sample_count", "grouping", "platform"],
        )
        base.update(kw)
        return DatasetFeasibilityReport(**base)

    def test_well_formed_usable_report_validates(self):
        data = self._report().to_dict()
        self.assertTrue(data["feasibility_report_id"].startswith("dataset_feasibility_report_"))
        self.assertEqual(validation.validate_dataset_feasibility_report(data), [])

    def test_decision_vocabulary_is_bounded(self):
        self.assertEqual(set(FEASIBILITY_DECISIONS), {"usable", "conditionally_usable", "not_usable", "insufficient"})
        data = self._report(decision="definitely").to_dict()
        self.assertTrue(any("decision" in e for e in validation.validate_dataset_feasibility_report(data)))

    def test_accepted_decision_requires_bindings_and_reasons(self):
        # missing evidence-plan binding
        no_plan = self._report(evidence_plan_id="").to_dict()
        self.assertTrue(any("evidence_plan_id" in e for e in validation.validate_dataset_feasibility_report(no_plan)))
        # blank reasons
        no_reason = self._report(reasons=["  "]).to_dict()
        self.assertTrue(any("reason" in e for e in validation.validate_dataset_feasibility_report(no_reason)))
        # missing fact basis
        no_facts = self._report(required_facts_checked=[]).to_dict()
        self.assertTrue(any("required_facts_checked" in e for e in validation.validate_dataset_feasibility_report(no_facts)))
        # missing subquestion binding
        no_sub = self._report(subquestion_id="").to_dict()
        self.assertTrue(any("subquestion_id" in e for e in validation.validate_dataset_feasibility_report(no_sub)))

    def test_conditionally_usable_requires_conditions_and_ceiling(self):
        good = self._report(
            decision="conditionally_usable",
            conditional_use_notes=["Only the bulk contrast; single-cell resolution not available"],
            imposed_claim_ceiling="association",
        ).to_dict()
        self.assertEqual(validation.validate_dataset_feasibility_report(good), [])
        # no conditions recorded
        no_notes = self._report(decision="conditionally_usable", imposed_claim_ceiling="association").to_dict()
        self.assertTrue(any("conditional_use_notes" in e for e in validation.validate_dataset_feasibility_report(no_notes)))
        # conditional verdict without a conservative ceiling
        no_ceiling = self._report(
            decision="conditionally_usable",
            conditional_use_notes=["bulk only"],
            imposed_claim_ceiling="",
        ).to_dict()
        self.assertTrue(any("imposed_claim_ceiling" in e for e in validation.validate_dataset_feasibility_report(no_ceiling)))

    def test_negative_decision_preserves_reasons_and_missing_facts(self):
        not_usable = self._report(
            decision="not_usable",
            evidence_plan_id="",
            reasons=["No control group present"],
            required_facts_checked=["grouping"],
            missing_facts=["control_group_samples"],
        ).to_dict()
        self.assertEqual(validation.validate_dataset_feasibility_report(not_usable), [])
        # a negative verdict that records nothing missing is pretending success
        empty_negative = self._report(
            decision="not_usable",
            evidence_plan_id="",
            reasons=["unusable"],
            missing_facts=[],
            blocking_gaps=[],
        ).to_dict()
        self.assertTrue(any("missing facts" in e for e in validation.validate_dataset_feasibility_report(empty_negative)))

    def test_insufficient_decision_requires_conservative_ceiling(self):
        good = self._report(
            decision="insufficient",
            evidence_plan_id="",
            reasons=["Too few replicates to be conclusive"],
            missing_facts=["additional_replicates"],
            imposed_claim_ceiling="descriptive",
        ).to_dict()
        self.assertEqual(validation.validate_dataset_feasibility_report(good), [])
        no_ceiling = self._report(
            decision="insufficient",
            evidence_plan_id="",
            reasons=["Too few replicates"],
            missing_facts=["additional_replicates"],
            imposed_claim_ceiling="",
        ).to_dict()
        self.assertTrue(any("imposed_claim_ceiling" in e for e in validation.validate_dataset_feasibility_report(no_ceiling)))

    def test_report_carries_no_locking_or_real_authority(self):
        for flag in ("locks_dataset", "authorizes_real_execution", "authorizes_formal_evidence"):
            data = self._report().to_dict()
            data[flag] = True
            errors = validation.validate_dataset_feasibility_report(data)
            self.assertTrue(any(flag in e for e in errors), flag)

    def test_report_rejects_nonboolean_truthy_authority_flags(self):
        # every authority flag — including bypasses_gates — must reject any truthy
        # value, not only the literal True (1, "true", a non-empty list, ...)
        flags = ("locks_dataset", "authorizes_real_execution", "authorizes_formal_evidence", "bypasses_gates")
        for flag in flags:
            for truthy in (1, "true", ["yes"]):
                data = self._report().to_dict()
                data[flag] = truthy
                errors = validation.validate_dataset_feasibility_report(data)
                self.assertTrue(any(flag in e for e in errors), f"{flag}={truthy!r} should be rejected")
        # valid false / absent flags stay accepted
        clean = self._report().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_dataset_feasibility_report(clean), [])
        absent = self._report().to_dict()
        for flag in flags:
            absent.pop(flag, None)
        self.assertEqual(validation.validate_dataset_feasibility_report(absent), [])


if __name__ == "__main__":
    unittest.main()
