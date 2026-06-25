import unittest

from auto_bioinfo.core import common, validation
from auto_bioinfo.core.common import Actor, ExternalIdentifier, SchemaValidationError, dataclass_json_schema
from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.core.schemas import (
    ALIGNMENT_DECISIONS,
    CLAIM_LEVELS,
    COMPATIBILITY_DECISIONS,
    FEASIBILITY_DECISIONS,
    REPRODUCIBILITY_LEVELS,
    REPRODUCTION_STATUSES,
    AmbiguityReport,
    AnalysisTaskPacket,
    ApprovalDecision,
    ApprovalRequest,
    ArtifactManifest,
    Claim,
    CompatibilityDecision,
    DataPreparationTaskPacket,
    DatasetFeasibilityReport,
    DatasetProfile,
    DependencyGraph,
    EngineeringTaskPacket,
    EvidenceGap,
    EvidenceItem,
    EvidencePlan,
    FinalReportManifest,
    MethodContract,
    MethodContractRef,
    OntologyMapping,
    OriginalRequest,
    Project,
    ProjectPolicy,
    QCReport,
    QuestionAlignmentReport,
    ReproductionBundleManifest,
    ResearchSpec,
    ResourceCandidate,
    ReviewTaskPacket,
    ScopeBundle,
    SubQuestion,
    TaskRun,
    WorkflowPlan,
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


# --- WP-02d / T-02-07: MethodContract standalone object ----------------------


class MethodContractContractTest(unittest.TestCase):
    def _contract(self, **kw):
        base = dict(
            method_id="bulk_deg",
            method_name="Bulk differential expression",
            version="0.1.0",
            scientific_purpose="Identify genes whose bulk RNA expression differs between two groups.",
            supported_modalities=["bulk_expression_matrix"],
            required_inputs=["counts_matrix", "sample_group_labels"],
            required_metadata=["sample_group_labels"],
            minimum_design_facts=["two groups", "min 2 replicates per group"],
            outputs=["deg_results_table"],
            statistical_assumptions=["independent samples", "approximately log-normal expression"],
            required_qc=["execution", "data", "statistical", "biological"],
            claim_capability="association",
            claim_ceiling="association",
            applicable_conditions=["two sample groups with replicates"],
            forbidden_conditions=["fewer than 2 replicates in any group", "interpreting results as causal evidence"],
        )
        base.update(kw)
        return MethodContract(**base)

    def test_legacy_method_contract_ref_still_works(self):
        # backward compatibility: the lightweight reference can point at a contract id
        contract = self._contract().to_dict()
        self.assertTrue(contract["method_contract_id"].startswith("method_contract_"))
        ref = MethodContractRef(method_contract_id=contract["method_contract_id"], method_name="Bulk differential expression")
        self.assertEqual(ref.method_contract_id, contract["method_contract_id"])
        self.assertEqual(ref.status, "active")

    def test_well_formed_contract_validates_and_is_stable(self):
        a = self._contract().to_dict()
        b = self._contract().to_dict()
        self.assertEqual(validation.validate_method_contract(a), [])
        # stable id is content-addressed over method identity (method_id + version)
        self.assertEqual(a["method_contract_id"], b["method_contract_id"])

    def test_blank_identity_is_rejected(self):
        self.assertTrue(validation.validate_method_contract(self._contract(method_id="").to_dict()))
        self.assertTrue(validation.validate_method_contract(self._contract(method_name="").to_dict()))
        self.assertTrue(validation.validate_method_contract(self._contract(version="").to_dict()))
        # a non-identifier method_id is rejected too
        self.assertTrue(any("method_id" in e for e in validation.validate_method_contract(self._contract(method_id="Bulk DEG").to_dict())))

    def test_invalid_claim_capability_or_ceiling_rejected(self):
        self.assertTrue(any("claim_capability" in e for e in validation.validate_method_contract(self._contract(claim_capability="telepathy").to_dict())))
        self.assertTrue(any("claim_ceiling" in e for e in validation.validate_method_contract(self._contract(claim_ceiling="omniscient").to_dict())))
        # capability may never exceed the ceiling
        over = self._contract(claim_capability="causal_support", claim_ceiling="association").to_dict()
        self.assertTrue(any("exceeds claim_ceiling" in e for e in validation.validate_method_contract(over)))

    def test_active_contract_requires_input_and_output_facts(self):
        no_inputs = self._contract(required_inputs=[]).to_dict()
        self.assertTrue(any("required_inputs" in e for e in validation.validate_method_contract(no_inputs)))
        no_outputs = self._contract(outputs=[]).to_dict()
        self.assertTrue(any("outputs" in e for e in validation.validate_method_contract(no_outputs)))
        no_modality = self._contract(supported_modalities=[]).to_dict()
        self.assertTrue(any("supported_modalities" in e for e in validation.validate_method_contract(no_modality)))

    def test_duplicate_requirements_are_rejected(self):
        dup = self._contract(required_inputs=["counts_matrix", "counts_matrix"]).to_dict()
        self.assertTrue(any("duplicate requirement" in e for e in validation.validate_method_contract(dup)))
        blank = self._contract(outputs=["deg_results_table", "  "]).to_dict()
        self.assertTrue(any("outputs" in e for e in validation.validate_method_contract(blank)))

    def test_contradictory_applicable_and_forbidden_conditions_rejected(self):
        data = self._contract(
            applicable_conditions=["two sample groups with replicates"],
            forbidden_conditions=["Two Sample Groups With Replicates"],  # same condition, different case
        ).to_dict()
        self.assertTrue(any("contradictory conditions" in e for e in validation.validate_method_contract(data)))


# --- WP-02d / T-02-08: CompatibilityDecision hardening -----------------------


class CompatibilityDecisionContractTest(unittest.TestCase):
    def _decision(self, **kw):
        base = dict(
            dataset_id="ds_gse12345",
            method_contract_id="method_contract_bulk_deg",
            compatible=True,
            reason="modality and two-group design match the contract",
            decision="compatible",
            method_id="bulk_deg",
            dataset_profile_id="dataset_profile_abc",
            subquestion_id="sq_1",
            evidence_plan_id="ep_1",
            reasons=["modality bulk_expression_matrix matches", "two groups with >=2 replicates each"],
            checked_facts=["modality", "sample_count", "grouping"],
        )
        base.update(kw)
        return CompatibilityDecision(**base)

    def test_legacy_four_field_decision_still_constructs(self):
        # backward compatibility: the original positional form still works, and
        # to_dict derives a bounded decision + mirrors the singular reason
        legacy = CompatibilityDecision("ds_x", "method_contract_bulk_deg", True, "looks fine").to_dict()
        self.assertEqual(legacy["decision"], "compatible")
        self.assertEqual(legacy["reasons"], ["looks fine"])
        self.assertTrue(legacy["compatibility_decision_id"].startswith("compatibility_decision_"))
        incompatible = CompatibilityDecision("ds_x", "method_contract_bulk_deg", False, "no control group").to_dict()
        self.assertEqual(incompatible["decision"], "incompatible")

    def test_well_formed_compatible_decision_validates(self):
        data = self._decision().to_dict()
        self.assertEqual(validation.validate_compatibility_decision(data), [])

    def test_decision_vocabulary_is_bounded(self):
        self.assertEqual(set(COMPATIBILITY_DECISIONS), {"compatible", "conditionally_compatible", "incompatible", "insufficient_information"})
        data = self._decision(decision="definitely").to_dict()
        self.assertTrue(any("decision" in e for e in validation.validate_compatibility_decision(data)))

    def test_accepted_decision_requires_bindings_and_reasons(self):
        no_sub = self._decision(subquestion_id="").to_dict()
        self.assertTrue(any("subquestion_id" in e for e in validation.validate_compatibility_decision(no_sub)))
        no_plan = self._decision(evidence_plan_id="").to_dict()
        self.assertTrue(any("evidence_plan_id" in e for e in validation.validate_compatibility_decision(no_plan)))
        no_facts = self._decision(checked_facts=[]).to_dict()
        self.assertTrue(any("checked_facts" in e for e in validation.validate_compatibility_decision(no_facts)))
        no_reason = self._decision(reason="", reasons=["  "]).to_dict()
        self.assertTrue(any("reason" in e for e in validation.validate_compatibility_decision(no_reason)))

    def test_conditionally_compatible_requires_conservative_ceiling(self):
        good = self._decision(decision="conditionally_compatible", imposed_claim_ceiling="association").to_dict()
        self.assertEqual(validation.validate_compatibility_decision(good), [])
        no_ceiling = self._decision(decision="conditionally_compatible", imposed_claim_ceiling="").to_dict()
        self.assertTrue(any("imposed_claim_ceiling" in e for e in validation.validate_compatibility_decision(no_ceiling)))

    def test_incompatible_decision_preserves_reasons_and_blocking_facts(self):
        not_compatible = self._decision(
            compatible=False,
            decision="incompatible",
            evidence_plan_id="",
            subquestion_id="",
            checked_facts=[],
            reasons=["single comparison group; method needs two"],
            blocking_facts=["only one sample group present"],
        ).to_dict()
        self.assertEqual(validation.validate_compatibility_decision(not_compatible), [])
        # a negative verdict that records nothing blocking is pretending compatibility
        empty_negative = self._decision(
            compatible=False,
            decision="incompatible",
            evidence_plan_id="",
            subquestion_id="",
            checked_facts=[],
            reasons=["unusable"],
            blocking_facts=[],
            missing_facts=[],
        ).to_dict()
        self.assertTrue(any("blocking facts" in e for e in validation.validate_compatibility_decision(empty_negative)))

    def test_insufficient_information_requires_conservative_ceiling(self):
        good = self._decision(
            compatible=False,
            decision="insufficient_information",
            evidence_plan_id="",
            subquestion_id="",
            checked_facts=[],
            reasons=["grouping metadata missing"],
            missing_facts=["sample_group_labels"],
            imposed_claim_ceiling="descriptive",
        ).to_dict()
        self.assertEqual(validation.validate_compatibility_decision(good), [])
        no_ceiling = self._decision(
            compatible=False,
            decision="insufficient_information",
            evidence_plan_id="",
            subquestion_id="",
            checked_facts=[],
            reasons=["grouping metadata missing"],
            missing_facts=["sample_group_labels"],
            imposed_claim_ceiling="",
        ).to_dict()
        self.assertTrue(any("imposed_claim_ceiling" in e for e in validation.validate_compatibility_decision(no_ceiling)))

    def test_contradictory_legacy_boolean_and_decision_are_rejected(self):
        # compatible=False but the hardened verdict claims (conditional) compatibility
        for accepted in ("compatible", "conditionally_compatible"):
            data = self._decision(
                compatible=False,
                decision=accepted,
                imposed_claim_ceiling="association",
            ).to_dict()
            errors = validation.validate_compatibility_decision(data)
            self.assertTrue(
                any("contradicts the hardened decision" in e for e in errors),
                f"compatible=False with decision={accepted!r} should be rejected",
            )
        # compatible=True but the hardened verdict is a negative one
        for negative in ("incompatible", "insufficient_information"):
            data = self._decision(
                compatible=True,
                decision=negative,
                evidence_plan_id="",
                subquestion_id="",
                checked_facts=[],
                reasons=["records a blocking fact"],
                blocking_facts=["only one sample group present"],
                missing_facts=["sample_group_labels"],
                imposed_claim_ceiling="descriptive",
            ).to_dict()
            errors = validation.validate_compatibility_decision(data)
            self.assertTrue(
                any("contradicts the hardened decision" in e for e in errors),
                f"compatible=True with decision={negative!r} should be rejected",
            )

    def test_legacy_derived_decision_stays_consistent(self):
        # when ``decision`` is absent it is derived from ``compatible`` by to_dict;
        # such an object is consistent by construction and the validator accepts it
        # without any contradiction error.
        derived = CompatibilityDecision(
            "ds_gse12345",
            "method_contract_bulk_deg",
            False,
            "no control group",
            decision="",  # forces to_dict to derive "incompatible" from compatible=False
            reasons=["single comparison group; method needs two"],
            blocking_facts=["only one sample group present"],
        ).to_dict()
        self.assertEqual(derived["decision"], "incompatible")
        errors = validation.validate_compatibility_decision(derived)
        self.assertFalse(
            any("contradicts the hardened decision" in e for e in errors),
            f"legacy-derived decision should not be flagged contradictory: {errors}",
        )
        self.assertEqual(errors, [])

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = ("authorizes_execution", "locks_dataset", "creates_evidence", "raises_claim_level")
        for flag in flags:
            for truthy in (True, 1, "true", ["yes"]):
                data = self._decision().to_dict()
                data[flag] = truthy
                errors = validation.validate_compatibility_decision(data)
                self.assertTrue(any(flag in e for e in errors), f"{flag}={truthy!r} should be rejected")
        # explicit false / absent flags stay accepted
        clean = self._decision().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_compatibility_decision(clean), [])
        absent = self._decision().to_dict()
        for flag in flags:
            absent.pop(flag, None)
        self.assertEqual(validation.validate_compatibility_decision(absent), [])


# --- WP-02e / T-02-09: WorkflowPlan explicit acyclic DAG ---------------------


class WorkflowPlanContractTest(unittest.TestCase):
    def _plan(self, **kw):
        base = dict(
            workflow_name="canonical_two_stage_workflow",
            task_ids=["prep_1", "analysis_1", "review_1"],
            dependencies=[["analysis_1", "prep_1"], ["review_1", "analysis_1"]],
            expected_inputs={"analysis_1": ["counts_matrix"], "review_1": ["analysis_results"]},
            expected_outputs={"prep_1": ["counts_matrix"], "analysis_1": ["analysis_results"]},
            gates=[{"gate": "qc_gate", "task_id": "analysis_1"}],
        )
        base.update(kw)
        return WorkflowPlan(**base)

    def test_legacy_minimal_workflow_plan_still_valid(self):
        # backward compatibility: the original (workflow_name, task_ids) form with
        # no explicit dependencies remains constructible and valid
        legacy = WorkflowPlan(workflow_name="legacy_linear", task_ids=["t1", "t2"]).to_dict()
        self.assertTrue(legacy["workflow_plan_id"].startswith("workflow_plan_"))
        self.assertEqual(legacy["dependencies"], [])
        self.assertEqual(validation.validate_workflow_plan(legacy), [])

    def test_well_formed_dag_validates_and_orders_deterministically(self):
        plan = self._plan()
        data = plan.to_dict()
        self.assertEqual(validation.validate_workflow_plan(data), [])
        self.assertFalse(plan.has_cycle())
        # prep before analysis before review
        self.assertEqual(plan.topological_order(), ["prep_1", "analysis_1", "review_1"])

    def test_serialization_is_deterministic_regardless_of_dependency_order(self):
        a = self._plan(dependencies=[["analysis_1", "prep_1"], ["review_1", "analysis_1"]]).to_dict()
        b = self._plan(dependencies=[["review_1", "analysis_1"], ["analysis_1", "prep_1"]]).to_dict()
        self.assertEqual(a["dependencies"], b["dependencies"])
        self.assertEqual(a["workflow_plan_id"], b["workflow_plan_id"])

    def test_stable_id_is_independent_of_task_ids_declaration_order(self):
        # Two equivalent DAGs — same tasks, same dependency (b depends on a) —
        # declared with task_ids in a different order must share a stable id;
        # the declaration order is harmless and must not affect content identity.
        dag_a = WorkflowPlan(workflow_name="equiv", task_ids=["a", "b"], dependencies=[["b", "a"]]).to_dict()
        dag_b = WorkflowPlan(workflow_name="equiv", task_ids=["b", "a"], dependencies=[["b", "a"]]).to_dict()
        self.assertEqual(dag_a["workflow_plan_id"], dag_b["workflow_plan_id"])
        # but a genuinely different dependency set still yields a different id
        dag_c = WorkflowPlan(workflow_name="equiv", task_ids=["a", "b"], dependencies=[["a", "b"]]).to_dict()
        self.assertNotEqual(dag_a["workflow_plan_id"], dag_c["workflow_plan_id"])

    def test_blank_or_duplicate_task_ids_rejected(self):
        blank = self._plan(task_ids=["prep_1", "  ", "review_1"], dependencies=[], expected_inputs={}, expected_outputs={}, gates=[]).to_dict()
        self.assertTrue(any("non-blank string" in e for e in validation.validate_workflow_plan(blank)))
        dup = self._plan(task_ids=["prep_1", "prep_1"], dependencies=[], expected_inputs={}, expected_outputs={}, gates=[]).to_dict()
        self.assertTrue(any("duplicate task id" in e for e in validation.validate_workflow_plan(dup)))

    def test_dangling_self_loop_and_cycle_rejected(self):
        dangling = self._plan(dependencies=[["analysis_1", "ghost"]], expected_inputs={}, expected_outputs={}, gates=[]).to_dict()
        self.assertTrue(any("not a declared task" in e for e in validation.validate_workflow_plan(dangling)))
        self_loop = self._plan(dependencies=[["analysis_1", "analysis_1"]], expected_inputs={}, expected_outputs={}, gates=[]).to_dict()
        self.assertTrue(any("self-loop" in e for e in validation.validate_workflow_plan(self_loop)))
        cycle = self._plan(
            dependencies=[["prep_1", "analysis_1"], ["analysis_1", "review_1"], ["review_1", "prep_1"]],
            expected_inputs={},
            expected_outputs={},
            gates=[],
        ).to_dict()
        errors = validation.validate_workflow_plan(cycle)
        self.assertTrue(any("cycle" in e for e in errors))
        with self.assertRaises(ValueError):
            self._plan(
                dependencies=[["prep_1", "analysis_1"], ["analysis_1", "review_1"], ["review_1", "prep_1"]],
            ).topological_order()

    def test_inputs_outputs_and_gates_must_reference_declared_tasks(self):
        bad_inputs = self._plan(expected_inputs={"ghost_task": ["x"]}, gates=[]).to_dict()
        self.assertTrue(any("expected_inputs" in e and "undeclared" in e for e in validation.validate_workflow_plan(bad_inputs)))
        bad_outputs = self._plan(expected_outputs={"ghost_task": ["x"]}, gates=[]).to_dict()
        self.assertTrue(any("expected_outputs" in e and "undeclared" in e for e in validation.validate_workflow_plan(bad_outputs)))
        bad_gate = self._plan(gates=[{"gate": "qc_gate", "task_id": "ghost_task"}]).to_dict()
        self.assertTrue(any("gates" in e and "undeclared" in e for e in validation.validate_workflow_plan(bad_gate)))

    def test_duplicate_io_facts_rejected(self):
        dup_io = self._plan(expected_inputs={"analysis_1": ["counts_matrix", "counts_matrix"]}, gates=[]).to_dict()
        self.assertTrue(any("duplicate entries" in e for e in validation.validate_workflow_plan(dup_io)))


# --- WP-02e / T-02-10: TaskPacket subtype coverage ---------------------------


class DataPreparationTaskPacketContractTest(unittest.TestCase):
    def _packet(self, **kw):
        base = dict(
            task_id="data_preparation_task_abc",
            subquestion_id="sq_1",
            planned_inputs=["resource_candidate_gse12345", "scope_bundle"],
            expected_outputs=["normalized_counts_matrix", "sample_sheet"],
            planned_resource_ids=["resource_candidate_gse12345"],
            planned_dataset_profile_ids=["dataset_profile_abc"],
            preparation_steps=["align reads", "build count matrix"],
            failure_conditions=["no verifiable dataset available"],
        )
        base.update(kw)
        return DataPreparationTaskPacket(**base)

    def test_well_formed_prep_packet_validates_and_id_is_stable(self):
        data = self._packet(task_id="").to_dict()
        self.assertTrue(data["task_id"].startswith("data_preparation_task_"))
        self.assertEqual(data["packet_type"], "DataPreparationTaskPacket")
        self.assertEqual(validation.validate_data_preparation_task_packet(data), [])

    def test_blank_identity_rejected(self):
        self.assertTrue(any("subquestion_id" in e for e in validation.validate_data_preparation_task_packet(self._packet(subquestion_id="").to_dict())))
        # a non-identifier task id is rejected too
        self.assertTrue(any("task_id" in e for e in validation.validate_data_preparation_task_packet(self._packet(task_id="Not An Id").to_dict())))

    def test_missing_planned_input_or_output_facts_rejected(self):
        self.assertTrue(any("planned_inputs" in e for e in validation.validate_data_preparation_task_packet(self._packet(planned_inputs=[]).to_dict())))
        self.assertTrue(any("expected_outputs" in e for e in validation.validate_data_preparation_task_packet(self._packet(expected_outputs=[]).to_dict())))

    def test_duplicate_facts_rejected(self):
        dup = self._packet(planned_inputs=["scope_bundle", "scope_bundle"]).to_dict()
        self.assertTrue(any("duplicate entries" in e for e in validation.validate_data_preparation_task_packet(dup)))

    def test_truthy_authority_flags_do_not_authorize(self):
        # both the original authority flags and the alias / alternative spellings
        # that express the same forbidden powers must be rejected when truthy
        flags = (
            "downloads_data",
            "locks_dataset",
            "authorizes_real_execution",
            "creates_formal_evidence",
            "authorizes_execution",
            "creates_evidence",
            "authorizes_formal_evidence",
            "bypasses_gates",
            "dataset_locked",
            "real_execution_authorized",
        )
        for flag in flags:
            for truthy in (True, 1, "true", ["yes"]):
                data = self._packet().to_dict()
                data[flag] = truthy
                errors = validation.validate_data_preparation_task_packet(data)
                self.assertTrue(any(flag in e for e in errors), f"{flag}={truthy!r} should be rejected")
        clean = self._packet().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_data_preparation_task_packet(clean), [])


class TaskPacketSubtypeBoundaryTest(unittest.TestCase):
    def test_analysis_packet_validator_preserves_boundary(self):
        from dataclasses import asdict

        packet = asdict(
            AnalysisTaskPacket(
                task_id="analysis_task_1",
                subquestion_id="sq_1",
                expected_inputs=["counts_matrix"],
                expected_outputs=["deg_results_table"],
                qc_requirements=["statistical"],
                failure_conditions=["missing_grouping"],
            )
        )
        self.assertEqual(validation.validate_analysis_task_packet(packet), [])
        # an analysis packet may never carry code-change authority
        packet["code_change_instructions"] = ["edit module.py"]
        self.assertTrue(any("code-change" in e for e in validation.validate_analysis_task_packet(packet)))
        # duplicate expected outputs are rejected
        dup = asdict(
            AnalysisTaskPacket(
                task_id="analysis_task_1",
                subquestion_id="sq_1",
                expected_inputs=["counts_matrix"],
                expected_outputs=["deg_results_table", "deg_results_table"],
                qc_requirements=["statistical"],
                failure_conditions=["missing_grouping"],
            )
        )
        self.assertTrue(any("duplicate entries" in e for e in validation.validate_analysis_task_packet(dup)))

    def test_engineering_packet_validator_rejects_path_escape_and_overlap(self):
        from dataclasses import asdict

        good = asdict(
            EngineeringTaskPacket(
                task_id="engineering_task_1",
                allowed_paths=["auto_bioinfo/core/schemas.py"],
                forbidden_paths=["docs/coordination"],
                expected_patch_summary="add a field",
                test_commands=["python -m unittest"],
            )
        )
        self.assertEqual(validation.validate_engineering_task_packet(good), [])
        # an allowed path that escapes scope (absolute / parent traversal) is rejected
        escape = asdict(
            EngineeringTaskPacket(
                task_id="engineering_task_1",
                allowed_paths=["../outside", "/etc/passwd"],
                forbidden_paths=["docs"],
                expected_patch_summary="x",
                test_commands=["python -m unittest"],
            )
        )
        self.assertTrue(any("escapes the packet's declared scope" in e for e in validation.validate_engineering_task_packet(escape)))
        # a path declared both allowed and forbidden is contradictory path authority
        overlap = asdict(
            EngineeringTaskPacket(
                task_id="engineering_task_1",
                allowed_paths=["auto_bioinfo/core"],
                forbidden_paths=["auto_bioinfo/core"],
                expected_patch_summary="x",
                test_commands=["python -m unittest"],
            )
        )
        self.assertTrue(any("both allowed and forbidden" in e for e in validation.validate_engineering_task_packet(overlap)))

    def test_engineering_packet_rejects_windows_path_escapes(self):
        from dataclasses import asdict

        # Windows-style escapes must be caught regardless of slash style: a
        # backslash parent traversal, a drive-letter absolute path, and a mixed
        # backslash traversal inside an otherwise in-scope prefix.
        for escape_path in ("..\\outside", "C:\\secret\\file.txt", "auto_bioinfo\\..\\secret"):
            packet = asdict(
                EngineeringTaskPacket(
                    task_id="engineering_task_1",
                    allowed_paths=[escape_path],
                    forbidden_paths=["docs"],
                    expected_patch_summary="x",
                    test_commands=["python -m unittest"],
                )
            )
            errors = validation.validate_engineering_task_packet(packet)
            self.assertTrue(
                any("escapes the packet's declared scope" in e for e in errors),
                f"{escape_path!r} should be rejected as a path escape",
            )
        # a valid relative path that stays inside the declared scope is accepted
        good = asdict(
            EngineeringTaskPacket(
                task_id="engineering_task_1",
                allowed_paths=["auto_bioinfo\\core\\schemas.py"],
                forbidden_paths=["docs"],
                expected_patch_summary="x",
                test_commands=["python -m unittest"],
            )
        )
        self.assertEqual(validation.validate_engineering_task_packet(good), [])

    def test_review_packet_validator_requires_criteria_and_valid_ceiling(self):
        from dataclasses import asdict

        good = asdict(
            ReviewTaskPacket(
                task_id="review_task_1",
                audit_scope=["workflow_plan"],
                claim_ceiling="association",
                required_checks=["claim_ceiling_not_loosened"],
            )
        )
        self.assertEqual(validation.validate_review_task_packet(good), [])
        bad_ceiling = asdict(
            ReviewTaskPacket(
                task_id="review_task_1",
                audit_scope=["workflow_plan"],
                claim_ceiling="omniscient",
                required_checks=["claim_ceiling_not_loosened"],
            )
        )
        self.assertTrue(any("claim_ceiling" in e for e in validation.validate_review_task_packet(bad_ceiling)))
        # a review with no required checks is not a review
        no_checks = asdict(
            ReviewTaskPacket(
                task_id="review_task_1",
                audit_scope=["workflow_plan"],
                claim_ceiling="association",
                required_checks=[],
            )
        )
        self.assertTrue(any("required_checks" in e for e in validation.validate_review_task_packet(no_checks)))


class TaskRunContractTest(unittest.TestCase):
    def _completed(self, **kw):
        base = dict(
            task_run_id="task_run_abc",
            task_id="analysis_task_1",
            result_status="completed",
            artifact_refs=["artifact_deg_table"],
            environment={"python": "3.11", "container": "none"},
            tool_identity="bulk_rnaseq_deg@1.0",
            parameters={"alpha": 0.05},
            log_refs=["log_run_abc"],
            output_refs=["output_deg_table"],
            exit_code=0,
            resource_usage={"wall_seconds": 12.5, "max_rss_mb": 512},
        )
        base.update(kw)
        return TaskRun(**base)

    def test_legacy_minimal_construction_is_backward_compatible(self):
        # The legacy four-field positional construction still builds and serialises,
        # and a minimal completed record validates once it carries the documented
        # minimum auditable facts (tool identity + an output/artifact ref).
        legacy = TaskRun("task_run_1", "analysis_task_1", "completed", ["artifact_deg_table"])
        data = legacy.to_dict()
        self.assertEqual(data["task_run_id"], "task_run_1")
        self.assertEqual(data["result_status"], "completed")
        self.assertEqual(data["artifact_refs"], ["artifact_deg_table"])
        # a bare legacy record with no environment/tool identity is not auditable
        self.assertTrue(any("auditable" in e for e in validation.validate_task_run(data)))
        # adding the minimum tool identity + the explicit completed exit code 0
        # makes the minimal record valid
        data["tool_identity"] = "bulk_rnaseq_deg@1.0"
        data["exit_code"] = 0
        self.assertEqual(validation.validate_task_run(data), [])

    def test_well_formed_completed_run_validates_with_stable_id(self):
        data = self._completed(task_run_id="").to_dict()
        self.assertTrue(data["task_run_id"].startswith("task_run_"))
        self.assertEqual(validation.validate_task_run(data), [])
        # the id is content-addressed: same facts, different created_at -> same id
        again = self._completed(task_run_id="").to_dict()
        self.assertEqual(data["task_run_id"], again["task_run_id"])
        # a different fact changes the id
        changed = self._completed(task_run_id="", exit_code=0, artifact_refs=["artifact_other"]).to_dict()
        self.assertNotEqual(data["task_run_id"], changed["task_run_id"])

    def test_failed_run_requires_explicit_error_or_log_facts(self):
        # a failed run with no error summary and no log refs is not auditable
        bare = self._completed(result_status="failed", exit_code=1, error_summary="", log_refs=[], artifact_refs=[], output_refs=[]).to_dict()
        self.assertTrue(any("error_summary or log ref" in e for e in validation.validate_task_run(bare)))
        # with an explicit error summary it validates
        with_error = self._completed(result_status="failed", exit_code=1, error_summary="segfault in step 2", artifact_refs=[], output_refs=[]).to_dict()
        self.assertEqual(validation.validate_task_run(with_error), [])

    def test_incomplete_run_requires_explicit_reason(self):
        for status in ("pending", "skipped", "running"):
            missing = self._completed(result_status=status, exit_code=None, artifact_refs=[], output_refs=[], log_refs=[], reason="").to_dict()
            self.assertTrue(
                any("requires an explicit reason" in e for e in validation.validate_task_run(missing)),
                f"{status} without reason should be rejected",
            )
            ok = self._completed(
                result_status=status,
                exit_code=None,
                artifact_refs=[],
                output_refs=[],
                log_refs=[],
                reason="awaiting upstream dataset",
            ).to_dict()
            self.assertEqual(validation.validate_task_run(ok), [], f"{status} with reason should validate")

    def test_invalid_result_status_rejected(self):
        bad = self._completed(result_status="omniscient").to_dict()
        self.assertTrue(any("result_status" in e for e in validation.validate_task_run(bad)))

    def test_exit_code_and_status_contradictions_rejected(self):
        # completed but non-zero exit
        c1 = self._completed(exit_code=3).to_dict()
        self.assertTrue(any("must exit 0" in e for e in validation.validate_task_run(c1)))
        # failed but success exit 0
        c2 = self._completed(result_status="failed", exit_code=0, error_summary="boom").to_dict()
        self.assertTrue(any("must not record a success exit code 0" in e for e in validation.validate_task_run(c2)))
        # incomplete record claiming an exit code it could not have produced
        c3 = self._completed(result_status="pending", exit_code=0, artifact_refs=[], output_refs=[], log_refs=[], reason="queued").to_dict()
        self.assertTrue(any("must not record an exit code" in e for e in validation.validate_task_run(c3)))
        # a non-integer exit code is malformed
        c4 = self._completed().to_dict()
        c4["exit_code"] = "0"
        self.assertTrue(any("exit_code" in e for e in validation.validate_task_run(c4)))

    def test_completed_run_requires_explicit_exit_code_zero(self):
        # a completed run with no exit code at all is rejected: the contract
        # requires completed runs to carry an explicit exit_code == 0.
        missing = self._completed(exit_code=None).to_dict()
        self.assertTrue(
            any("must record an explicit exit code 0" in e for e in validation.validate_task_run(missing)),
            "completed run with exit_code=None must be rejected",
        )
        # the explicit success exit code makes it valid
        ok = self._completed(exit_code=0).to_dict()
        self.assertEqual(validation.validate_task_run(ok), [])

    def test_duplicate_or_blank_refs_rejected(self):
        dup = self._completed(artifact_refs=["a", "a"]).to_dict()
        self.assertTrue(any("artifact_refs" in e and "duplicate" in e for e in validation.validate_task_run(dup)))
        blank = self._completed(log_refs=["", "ok"]).to_dict()
        self.assertTrue(any("log_refs" in e for e in validation.validate_task_run(blank)))
        dup_out = self._completed(output_refs=["o", "o"]).to_dict()
        self.assertTrue(any("output_refs" in e and "duplicate" in e for e in validation.validate_task_run(dup_out)))

    def test_cross_list_duplicate_refs_rejected(self):
        # the same ref must not be claimed across two different ref lists.
        artifact_log = self._completed(artifact_refs=["ref_shared"], output_refs=["output_deg_table"], log_refs=["ref_shared"]).to_dict()
        errors = validation.validate_task_run(artifact_log)
        self.assertTrue(
            any("globally unique" in e and "ref_shared" in e for e in errors),
            "a ref shared between artifact_refs and log_refs must be rejected",
        )
        # the same ref in artifact_refs and output_refs is rejected too
        artifact_output = self._completed(artifact_refs=["ref_dup"], output_refs=["ref_dup"], log_refs=["log_run_abc"]).to_dict()
        self.assertTrue(
            any("globally unique" in e and "ref_dup" in e for e in validation.validate_task_run(artifact_output)),
            "a ref shared between artifact_refs and output_refs must be rejected",
        )
        # distinct refs across the three lists remain valid
        distinct = self._completed(artifact_refs=["artifact_deg_table"], output_refs=["output_deg_table"], log_refs=["log_run_abc"]).to_dict()
        self.assertEqual(validation.validate_task_run(distinct), [])

    def test_malformed_resource_usage_rejected(self):
        neg = self._completed(resource_usage={"wall_seconds": -1}).to_dict()
        self.assertTrue(any("non-negative" in e for e in validation.validate_task_run(neg)))
        non_numeric = self._completed(resource_usage={"wall_seconds": "fast"}).to_dict()
        self.assertTrue(any("resource_usage" in e for e in validation.validate_task_run(non_numeric)))
        # a boolean is not a measured quantity
        boolean = self._completed(resource_usage={"wall_seconds": True}).to_dict()
        self.assertTrue(any("resource_usage" in e for e in validation.validate_task_run(boolean)))
        not_a_map = self._completed().to_dict()
        not_a_map["resource_usage"] = [1, 2]
        self.assertTrue(any("resource_usage" in e for e in validation.validate_task_run(not_a_map)))

    def test_retry_lineage_self_reference_and_numbering_rejected(self):
        # a run may not be a retry of itself
        self_retry = self._completed(task_run_id="task_run_x", retry_of="task_run_x", attempt=2).to_dict()
        self.assertTrue(any("retry of itself" in e for e in validation.validate_task_run(self_retry)))
        # a retry must record attempt >= 2
        bad_attempt = self._completed(retry_of="task_run_prev", attempt=1).to_dict()
        self.assertTrue(any("attempt >= 2" in e for e in validation.validate_task_run(bad_attempt)))
        # attempt > 1 with no retry lineage is inconsistent
        orphan = self._completed(attempt=2, retry_of="").to_dict()
        self.assertTrue(any("must reference the prior run via retry_of" in e for e in validation.validate_task_run(orphan)))
        # a zero / negative attempt is rejected
        zero = self._completed(attempt=0).to_dict()
        self.assertTrue(any("positive integer" in e for e in validation.validate_task_run(zero)))
        # a well-formed retry validates
        good_retry = self._completed(task_run_id="task_run_2", retry_of="task_run_1", attempt=2).to_dict()
        self.assertEqual(validation.validate_task_run(good_retry), [])

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = (
            "authorizes_execution",
            "authorizes_real_execution",
            "real_execution_authorized",
            "locks_dataset",
            "dataset_locked",
            "creates_formal_evidence",
            "creates_evidence",
            "authorizes_formal_evidence",
            "bypasses_gates",
            "raises_claim_level",
            "raises_claim",
            "claim_level_raised",
            "mutates_workflow_state",
            "workflow_state_mutated",
        )
        for flag in flags:
            for truthy in (True, 1, "true", ["yes"]):
                data = self._completed().to_dict()
                data[flag] = truthy
                errors = validation.validate_task_run(data)
                self.assertTrue(any(flag in e for e in errors), f"{flag}={truthy!r} should be rejected")
        # false / absent authority flags pass
        clean = self._completed().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_task_run(clean), [])


_VALID_SHA256 = "a" * 64


class ArtifactManifestContractTest(unittest.TestCase):
    """WP-02g / T-02-12: ArtifactManifest structured fact record (REQ-OBJ-13)."""

    def _manifest(self, **kw):
        base = dict(
            artifact_id="artifact_deg_table",
            project_id="proj_demo",
            path="state/deg_results.csv",
            exists=True,
            checksum_sha256=_VALID_SHA256,
            is_placeholder=False,
            qc_status="pass",
            artifact_type="deg_results_table",
            producer_agent_or_task="analysis_task_1",
            producer_run_id="task_run_1",
            source_refs=["dataset_profile_1"],
            output_name="deg_results.csv",
            size_bytes=2048,
        )
        base.update(kw)
        return ArtifactManifest(**base)

    def test_well_formed_manifest_validates_with_stable_id(self):
        data = self._manifest(artifact_id="").to_dict()
        self.assertTrue(data["artifact_id"].startswith("artifact_"))
        self.assertEqual(validation.validate_artifact_manifest(data), [])
        # content-addressed: same facts -> same id, a different path -> a new id
        again = self._manifest(artifact_id="").to_dict()
        self.assertEqual(data["artifact_id"], again["artifact_id"])
        changed = self._manifest(artifact_id="", path="state/other.csv").to_dict()
        self.assertNotEqual(data["artifact_id"], changed["artifact_id"])

    def test_blank_identity_or_path_rejected(self):
        blank_proj = self._manifest(project_id="").to_dict()
        self.assertTrue(any("project_id" in e for e in validation.validate_artifact_manifest(blank_proj)))
        blank_path = self._manifest(path="   ").to_dict()
        self.assertTrue(any("path" in e for e in validation.validate_artifact_manifest(blank_path)))

    def test_existing_artifact_requires_valid_checksum(self):
        missing = self._manifest(checksum_sha256="").to_dict()
        self.assertTrue(any("checksum_sha256" in e for e in validation.validate_artifact_manifest(missing)))
        invalid = self._manifest(checksum_sha256="not-a-hash").to_dict()
        self.assertTrue(any("checksum_sha256" in e for e in validation.validate_artifact_manifest(invalid)))

    def test_placeholder_and_nonexistent_and_failed_cannot_support_evidence(self):
        placeholder = self._manifest(is_placeholder=True).to_dict()
        self.assertTrue(any("is_placeholder=true" in e for e in validation.validate_artifact_manifest(placeholder)))
        nonexistent = self._manifest(exists=False, checksum_sha256="").to_dict()
        self.assertTrue(any("exists=false" in e for e in validation.validate_artifact_manifest(nonexistent)))
        failed = self._manifest(qc_status="fail").to_dict()
        self.assertTrue(any("qc_status=fail" in e for e in validation.validate_artifact_manifest(failed)))

    def test_invalid_qc_status_rejected(self):
        bad = self._manifest(qc_status="omniscient").to_dict()
        self.assertTrue(any("qc_status: must be one of" in e for e in validation.validate_artifact_manifest(bad)))

    def test_negative_size_and_duplicate_source_refs_rejected(self):
        neg = self._manifest(size_bytes=-1).to_dict()
        self.assertTrue(any("size_bytes" in e and "negative" in e for e in validation.validate_artifact_manifest(neg)))
        dup = self._manifest(source_refs=["dataset_profile_1", "dataset_profile_1"]).to_dict()
        self.assertTrue(any("source_refs" in e and "duplicate" in e for e in validation.validate_artifact_manifest(dup)))

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = (
            "authorizes_real_execution",
            "real_execution_authorized",
            "creates_formal_evidence",
            "creates_evidence",
            "authorizes_formal_evidence",
            "locks_dataset",
            "dataset_locked",
            "bypasses_gates",
            "raises_claim_level",
            "claim_level_raised",
            "authorizes_export",
            "publishes",
        )
        for flag in flags:
            for truthy in (True, 1, "yes", ["x"]):
                data = self._manifest().to_dict()
                data[flag] = truthy
                self.assertTrue(any(flag in e for e in validation.validate_artifact_manifest(data)), f"{flag}={truthy!r} should be rejected")
        clean = self._manifest().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_artifact_manifest(clean), [])


class QCReportContractTest(unittest.TestCase):
    """WP-02g / T-02-13: QCReport four-layer fact record (REQ-OBJ-14)."""

    def _checks(self):
        return [
            {"check_id": "execution.method_succeeded", "layer": "execution", "status": "pass", "reason": "method succeeded"},
            {"check_id": "data.nonempty_matrix", "layer": "data", "status": "pass", "reason": "n_genes>0"},
            {"check_id": "statistical.min_replicates", "layer": "statistical", "status": "pass", "reason": "all groups >= 2"},
            {"check_id": "biological.claim_capability", "layer": "biological", "status": "pass", "reason": "RNA capped at association"},
        ]

    def _report(self, **kw):
        base = dict(qc_report_id="qc_report_1", overall_status="pass", checks=self._checks(), artifact_id="artifact_deg_table")
        base.update(kw)
        return QCReport(**base)

    def test_well_formed_four_layer_report_validates_with_stable_id(self):
        data = self._report(qc_report_id="").to_dict()
        self.assertTrue(data["qc_report_id"].startswith("qc_report_"))
        self.assertEqual(validation.validate_qc_report(data), [])

    def test_engine_detail_is_accepted_as_reason(self):
        # the deterministic QC engine records its reason under ``detail``.
        checks = [{"check_id": "execution.output_exists", "layer": "execution", "status": "fail", "detail": "size_bytes=0"}]
        data = self._report(overall_status="fail", checks=checks).to_dict()
        self.assertEqual(validation.validate_qc_report(data), [])

    def test_bare_boolean_qc_is_rejected(self):
        bare = self._report(checks=True).to_dict()
        self.assertTrue(any("bare boolean" in e for e in validation.validate_qc_report(bare)))
        bare_item = self._report(checks=[True, False]).to_dict()
        self.assertTrue(any("bare boolean" in e for e in validation.validate_qc_report(bare_item)))

    def test_unknown_layer_or_status_rejected(self):
        bad_layer = self._report(checks=[{"check_id": "x", "layer": "spiritual", "status": "pass", "reason": "r"}]).to_dict()
        self.assertTrue(any("layer: must be one of" in e for e in validation.validate_qc_report(bad_layer)))
        bad_status = self._report(checks=[{"check_id": "x", "layer": "data", "status": "maybe", "reason": "r"}]).to_dict()
        self.assertTrue(any("status: must be one of" in e for e in validation.validate_qc_report(bad_status)))

    def test_fail_or_warn_without_reason_rejected(self):
        no_reason_fail = self._report(overall_status="fail", checks=[{"check_id": "x", "layer": "data", "status": "fail"}]).to_dict()
        self.assertTrue(any("must record an explicit reason" in e for e in validation.validate_qc_report(no_reason_fail)))
        no_reason_warn = self._report(overall_status="pass_with_warnings", checks=[{"check_id": "x", "layer": "data", "status": "warn"}]).to_dict()
        self.assertTrue(any("must record an explicit reason" in e for e in validation.validate_qc_report(no_reason_warn)))

    def test_duplicate_check_ids_rejected(self):
        dup = [
            {"check_id": "data.same", "layer": "data", "status": "pass", "reason": "r"},
            {"check_id": "data.same", "layer": "data", "status": "pass", "reason": "r"},
        ]
        data = self._report(checks=dup).to_dict()
        self.assertTrue(any("duplicate check id" in e for e in validation.validate_qc_report(data)))

    def test_overall_status_contradictions_rejected(self):
        # overall pass but a check failed
        fail_check = self._checks()
        fail_check[0] = {"check_id": "execution.method_succeeded", "layer": "execution", "status": "fail", "reason": "crash"}
        contradiction = self._report(overall_status="pass", checks=fail_check).to_dict()
        self.assertTrue(any("contradicts a failing check" in e for e in validation.validate_qc_report(contradiction)))
        # overall pass but a check warned
        warn_check = self._checks()
        warn_check[1] = {"check_id": "data.nonempty_matrix", "layer": "data", "status": "warn", "reason": "low"}
        warn_contradiction = self._report(overall_status="pass", checks=warn_check).to_dict()
        self.assertTrue(any("contradicts a warning check" in e for e in validation.validate_qc_report(warn_contradiction)))
        # overall fail but every check passed
        clean_fail = self._report(overall_status="fail").to_dict()
        self.assertTrue(any("contradicts all-passing checks" in e for e in validation.validate_qc_report(clean_fail)))

    def test_qc_report_carries_no_export_or_claim_authority(self):
        for flag in ("creates_evidence", "raises_claim_level", "authorizes_export", "authorizes_publishing", "publishes", "bypasses_gates"):
            data = self._report().to_dict()
            data[flag] = True
            self.assertTrue(any(flag in e for e in validation.validate_qc_report(data)), f"{flag} should be rejected")


class EvidenceItemContractTest(unittest.TestCase):
    """WP-02g / T-02-14: EvidenceItem evidence-fact record (REQ-OBJ-15)."""

    def _item(self, **kw):
        base = dict(
            evidence_item_id="evidence_item_1",
            artifact_id="artifact_deg_table",
            review_status="audited",
            subquestion_ids=["subquestion_1"],
            source_dataset_ids=["dataset_1"],
            source_task_run_ids=["task_run_1"],
            observation="120 of 18000 genes are significantly differentially expressed between A and B.",
            effect_summary={"n_significant": 120, "max_abs_log2_fold_change": 3.1},
            uncertainty={"statistical_test": "welch_t_test", "fdr_method": "benjamini_hochberg"},
            evidence_type="bulk_rna_differential_expression",
            scope={"species": ["human"], "tissue": ["liver"]},
            qc_status="pass",
            allowed_claim_level="association",
            supports_or_opposes="supports",
            replication_status="single_dataset",
            limitations=["Single dataset; results are not independently replicated."],
        )
        base.update(kw)
        return EvidenceItem(**base)

    def test_well_formed_evidence_validates_with_stable_id(self):
        data = self._item(evidence_item_id="").to_dict()
        self.assertTrue(data["evidence_item_id"].startswith("evidence_item_"))
        self.assertEqual(validation.validate_evidence_item(data), [])

    def test_missing_lineage_rejected(self):
        for list_field in ("subquestion_ids", "source_dataset_ids", "source_task_run_ids"):
            data = self._item(**{list_field: []}).to_dict()
            self.assertTrue(
                any(list_field in e for e in validation.validate_evidence_item(data)),
                f"empty {list_field} should be rejected",
            )

    def test_non_qc_passed_evidence_rejected(self):
        for bad_status in ("fail", "pending", "warn"):
            data = self._item(qc_status=bad_status).to_dict()
            self.assertTrue(any("QC-passed status" in e for e in validation.validate_evidence_item(data)), f"qc_status={bad_status} should be rejected")

    def test_invalid_claim_level_and_blank_observation_or_type_rejected(self):
        bad_level = self._item(allowed_claim_level="omniscient").to_dict()
        self.assertTrue(any("allowed_claim_level" in e for e in validation.validate_evidence_item(bad_level)))
        blank_obs = self._item(observation="   ").to_dict()
        self.assertTrue(any("observation" in e for e in validation.validate_evidence_item(blank_obs)))
        blank_type = self._item(evidence_type="").to_dict()
        self.assertTrue(any("evidence_type" in e for e in validation.validate_evidence_item(blank_type)))

    def test_missing_or_invalid_direction_rejected(self):
        bad_dir = self._item(supports_or_opposes="vibes").to_dict()
        self.assertTrue(any("supports_or_opposes" in e for e in validation.validate_evidence_item(bad_dir)))

    def test_single_dataset_cannot_claim_replication(self):
        replicated = self._item(replication_status="replicated").to_dict()
        self.assertTrue(any("independent replication" in e for e in validation.validate_evidence_item(replicated)))
        # multi-dataset evidence may legitimately claim replication
        multi = self._item(source_dataset_ids=["dataset_1", "dataset_2"], replication_status="multi_dataset").to_dict()
        self.assertEqual(validation.validate_evidence_item(multi), [])

    def test_single_dataset_must_keep_limitations_visible(self):
        no_limits = self._item(limitations=[]).to_dict()
        self.assertTrue(any("limitations" in e for e in validation.validate_evidence_item(no_limits)))

    def test_external_validation_requires_supporting_refs(self):
        unsupported = self._item(externally_validated=True, external_validation_refs=[]).to_dict()
        self.assertTrue(any("external_validation_refs" in e for e in validation.validate_evidence_item(unsupported)))
        supported = self._item(externally_validated=True, external_validation_refs=["pmid:12345678"]).to_dict()
        self.assertEqual(validation.validate_evidence_item(supported), [])

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = (
            "raises_claim_level",
            "claim_level_raised",
            "bypasses_qc",
            "bypasses_gates",
            "creates_claim",
            "creates_formal_evidence",
            "authorizes_export",
            "authorizes_publishing",
            "publishes",
        )
        for flag in flags:
            for truthy in (True, 1, "yes", ["x"]):
                data = self._item().to_dict()
                data[flag] = truthy
                self.assertTrue(any(flag in e for e in validation.validate_evidence_item(data)), f"{flag}={truthy!r} should be rejected")
        clean = self._item().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_evidence_item(clean), [])


# --- WP-02h / T-02-15: Claim bounded statement contract ----------------------


class ClaimContractTest(unittest.TestCase):
    """WP-02h / T-02-15: Claim bounded statement record (REQ-OBJ-16)."""

    def _claim(self, **kw):
        base = dict(
            claim_id="claim_1",
            text="At the RNA level, 120 genes show association-level differential expression for the contrast.",
            claim_level="association",
            evidence_item_refs=["evidence_item_1"],
            supports_subquestion_ids=["subquestion_1"],
            scope={"species": ["human"], "tissue": ["liver"], "condition": ["A_vs_B"]},
            limitations=["Single dataset; not independently replicated."],
            claim_ceiling="association",
        )
        base.update(kw)
        return Claim(**base)

    def test_well_formed_claim_validates_with_stable_id(self):
        data = self._claim(claim_id="").to_dict()
        self.assertTrue(data["claim_id"].startswith("claim_"))
        self.assertEqual(validation.validate_claim(data), [])
        # content-addressed: same statement facts -> same id, a different statement -> a new id
        again = self._claim(claim_id="").to_dict()
        self.assertEqual(data["claim_id"], again["claim_id"])
        changed = self._claim(claim_id="", text="A different statement entirely.").to_dict()
        self.assertNotEqual(data["claim_id"], changed["claim_id"])

    def test_legacy_construction_is_backward_compatible(self):
        # the original seven-field positional construction still builds and the
        # hardened defaults are filled in (ceiling defaults to association).
        legacy = Claim("claim_x", "text", "association", ["evidence_item_1"], ["subquestion_1"], {"species": ["human"]}, [])
        data = legacy.to_dict()
        self.assertEqual(data["claim_ceiling"], "association")
        self.assertEqual(data["opposing_evidence_refs"], [])
        self.assertEqual(validation.validate_claim(data), [])

    def test_blank_identity_or_text_or_level_rejected(self):
        self.assertTrue(any("text" in e for e in validation.validate_claim(self._claim(text="   ").to_dict())))
        self.assertTrue(any("claim_level" in e for e in validation.validate_claim(self._claim(claim_level="omniscient").to_dict())))
        # a non-identifier claim id is rejected
        self.assertTrue(any("claim_id" in e for e in validation.validate_claim(self._claim(claim_id="Not An Id").to_dict())))

    def test_claim_level_above_ceiling_rejected(self):
        over = self._claim(claim_level="causal_support", claim_ceiling="association").to_dict()
        self.assertTrue(any("exceeds claim_ceiling" in e for e in validation.validate_claim(over)))
        # an external max_allowed ceiling is also enforced
        ok_self = self._claim(claim_level="association", claim_ceiling="causal_support").to_dict()
        self.assertTrue(any("exceeds allowed ceiling" in e for e in validation.validate_claim(ok_self, max_allowed="descriptive")))
        self.assertEqual(validation.validate_claim(ok_self, max_allowed="causal_support"), [])

    def test_unsupported_claim_rejected(self):
        # a claim with no supporting evidence refs is unsupported
        no_evidence = self._claim(evidence_item_refs=[]).to_dict()
        self.assertTrue(any("supporting evidence" in e for e in validation.validate_claim(no_evidence)))

    def test_missing_scope_rejected(self):
        empty_scope = self._claim(scope={}).to_dict()
        self.assertTrue(any("scope" in e for e in validation.validate_claim(empty_scope)))
        blank_axes = self._claim(scope={"species": [], "tissue": ["  "]}).to_dict()
        self.assertTrue(any("scope" in e for e in validation.validate_claim(blank_axes)))

    def test_contradictory_support_and_opposing_evidence_rejected(self):
        contradictory = self._claim(
            evidence_item_refs=["evidence_item_1"],
            opposing_evidence_refs=["evidence_item_1"],
        ).to_dict()
        self.assertTrue(any("both supporting and opposing" in e for e in validation.validate_claim(contradictory)))
        # distinct supporting/opposing refs are fine
        ok = self._claim(
            evidence_item_refs=["evidence_item_1"],
            opposing_evidence_refs=["evidence_item_2"],
        ).to_dict()
        self.assertEqual(validation.validate_claim(ok), [])

    def test_duplicate_evidence_refs_rejected(self):
        dup = self._claim(evidence_item_refs=["evidence_item_1", "evidence_item_1"]).to_dict()
        self.assertTrue(any("evidence_item_refs" in e and "duplicate" in e for e in validation.validate_claim(dup)))

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = (
            "raises_claim_level",
            "claim_level_raised",
            "bypasses_qc",
            "bypasses_gates",
            "creates_evidence",
            "creates_formal_evidence",
            "authorizes_export",
            "authorizes_publishing",
            "publishes",
            "authorizes_real_execution",
        )
        for flag in flags:
            for truthy in (True, 1, "yes", ["x"]):
                data = self._claim().to_dict()
                data[flag] = truthy
                self.assertTrue(any(flag in e for e in validation.validate_claim(data)), f"{flag}={truthy!r} should be rejected")
        clean = self._claim().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_claim(clean), [])


# --- WP-02h / T-02-16: QuestionAlignmentReport & FinalReportManifest ----------


class QuestionAlignmentReportContractTest(unittest.TestCase):
    """WP-02h / T-02-16: QuestionAlignmentReport alignment record (REQ-OBJ-17)."""

    def _report(self, **kw):
        base = dict(
            report_id="question_alignment_report_1",
            final_decision="approve",
            unsupported_claims=[],
            research_spec_id="research_spec_1",
            project_id="proj_demo",
        )
        base.update(kw)
        return QuestionAlignmentReport(**base)

    def test_clean_approve_validates(self):
        data = self._report().to_dict()
        self.assertEqual(validation.validate_question_alignment_report(data), [])

    def test_decision_vocabulary_is_bounded(self):
        self.assertEqual(set(ALIGNMENT_DECISIONS), {"approve", "needs_review", "reject"})
        bad = self._report(final_decision="definitely").to_dict()
        self.assertTrue(any("final_decision" in e for e in validation.validate_question_alignment_report(bad)))

    def test_approve_over_open_findings_rejected(self):
        # an approve decision may not stand while any alignment finding is open
        for field_name, value in (
            ("unsupported_claims", [{"claim_id": "claim_1", "reason": "no evidence"}]),
            ("scope_drift_findings", [{"claim_id": "claim_1", "reason": "tissue drift"}]),
            ("overclaim_findings", [{"claim_id": "claim_1", "reason": "above ceiling"}]),
            ("omitted_evidence", [{"evidence_item_id": "evidence_item_1", "reason": "negative result dropped"}]),
            ("traceability_gaps", [{"claim_id": "claim_1", "reason": "no sub-question"}]),
            ("blocker_facts", ["QC failed on the only supporting artifact"]),
        ):
            data = self._report(final_decision="approve", **{field_name: value}).to_dict()
            errors = validation.validate_question_alignment_report(data)
            self.assertTrue(any("cannot approve while alignment findings remain open" in e for e in errors), f"{field_name} should block approve")
            # the same findings under a non-passing decision are fine
            non_pass = self._report(final_decision="reject", **{field_name: value}).to_dict()
            self.assertEqual(validation.validate_question_alignment_report(non_pass), [])

    def test_blocker_facts_must_be_clean_strings(self):
        blank = self._report(final_decision="reject", blocker_facts=["  "]).to_dict()
        self.assertTrue(any("blocker_facts" in e for e in validation.validate_question_alignment_report(blank)))

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = ("authorizes_export", "authorizes_publishing", "publishes", "raises_claim_level", "claim_level_raised", "bypasses_gates")
        for flag in flags:
            for truthy in (True, 1, "yes", ["x"]):
                data = self._report().to_dict()
                data[flag] = truthy
                self.assertTrue(any(flag in e for e in validation.validate_question_alignment_report(data)), f"{flag}={truthy!r} should be rejected")
        clean = self._report().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_question_alignment_report(clean), [])


class FinalReportManifestContractTest(unittest.TestCase):
    """WP-02h / T-02-16: FinalReportManifest report/claim traceability."""

    def _manifest(self, **kw):
        base = dict(
            final_report_id="final_report_1",
            report_path="state/final_report.md",
            claim_ids=["claim_1", "claim_2"],
            alignment_report_id="question_alignment_report_1",
        )
        base.update(kw)
        return FinalReportManifest(**base)

    def test_well_formed_manifest_validates(self):
        self.assertEqual(validation.validate_final_report_manifest(self._manifest().to_dict()), [])

    def test_blank_path_or_duplicate_claims_rejected(self):
        blank_path = self._manifest(report_path="  ").to_dict()
        self.assertTrue(any("report_path" in e for e in validation.validate_final_report_manifest(blank_path)))
        dup = self._manifest(claim_ids=["claim_1", "claim_1"]).to_dict()
        self.assertTrue(any("claim_ids" in e and "duplicate" in e for e in validation.validate_final_report_manifest(dup)))

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = ("generates_report", "authorizes_export", "authorizes_publishing", "publishes", "bypasses_gates")
        for flag in flags:
            for truthy in (True, 1, "yes", ["x"]):
                data = self._manifest().to_dict()
                data[flag] = truthy
                self.assertTrue(any(flag in e for e in validation.validate_final_report_manifest(data)), f"{flag}={truthy!r} should be rejected")
        clean = self._manifest().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_final_report_manifest(clean), [])


# --- WP-02h / T-02-17: ReproductionBundleManifest ----------------------------


class ReproductionBundleManifestContractTest(unittest.TestCase):
    """WP-02h / T-02-17: ReproductionBundleManifest manifest contract (REQ-OBJ-18)."""

    def _manifest(self, **kw):
        base = dict(
            bundle_id="reproduction_bundle_1",
            project_id="proj_demo",
            files=[
                {"path": "scripts/run.py", "checksum_sha256": _VALID_SHA256, "role": "entrypoint"},
                {"path": "data/counts.tsv", "role": "input"},
            ],
            run_order=["scripts/run.py"],
            environment_facts={"python": "3.11", "container": "none"},
            expected_outputs=[{"name": "deg_results.csv"}],
            comparison_rules=[{"expected_output": "deg_results.csv", "rule": "exact_checksum"}],
            reproducibility_level="numerical",
            reproduction_status="pending",
        )
        base.update(kw)
        return ReproductionBundleManifest(**base)

    def test_well_formed_manifest_validates_with_stable_id(self):
        data = self._manifest(bundle_id="").to_dict()
        self.assertTrue(data["bundle_id"].startswith("reproduction_bundle_"))
        self.assertEqual(validation.validate_reproduction_bundle_manifest(data), [])
        # content-addressed over project + files + run order
        again = self._manifest(bundle_id="").to_dict()
        self.assertEqual(data["bundle_id"], again["bundle_id"])

    def test_missing_or_duplicate_files_rejected(self):
        no_files = self._manifest(files=[], run_order=[]).to_dict()
        self.assertTrue(any("at least one file fact" in e for e in validation.validate_reproduction_bundle_manifest(no_files)))
        blank_path = self._manifest(files=[{"role": "input"}], run_order=[]).to_dict()
        self.assertTrue(any("missing required file path" in e for e in validation.validate_reproduction_bundle_manifest(blank_path)))
        dup = self._manifest(
            files=[{"path": "scripts/run.py"}, {"path": "scripts/run.py"}],
            run_order=["scripts/run.py"],
        ).to_dict()
        self.assertTrue(any("duplicate file path" in e for e in validation.validate_reproduction_bundle_manifest(dup)))

    def test_invalid_run_order_rejected(self):
        # a run-order step that is not a declared file is an invalid run order
        unknown = self._manifest(run_order=["scripts/ghost.py"]).to_dict()
        self.assertTrue(any("invalid run order" in e for e in validation.validate_reproduction_bundle_manifest(unknown)))
        dup = self._manifest(run_order=["scripts/run.py", "scripts/run.py"]).to_dict()
        self.assertTrue(any("run_order" in e and "duplicate" in e for e in validation.validate_reproduction_bundle_manifest(dup)))

    def test_undeclared_expected_output_in_comparison_rule_rejected(self):
        undeclared = self._manifest(comparison_rules=[{"expected_output": "ghost.csv", "rule": "exact"}]).to_dict()
        self.assertTrue(any("undeclared expected output" in e for e in validation.validate_reproduction_bundle_manifest(undeclared)))
        # a comparison rule that names no output at all is rejected
        no_target = self._manifest(comparison_rules=[{"rule": "exact"}]).to_dict()
        self.assertTrue(any("must name the expected output" in e for e in validation.validate_reproduction_bundle_manifest(no_target)))
        # a blank-named expected output is rejected
        blank_output = self._manifest(expected_outputs=[{"name": "  "}], comparison_rules=[]).to_dict()
        self.assertTrue(any("non-blank name" in e for e in validation.validate_reproduction_bundle_manifest(blank_output)))

    def test_invalid_level_or_status_rejected(self):
        self.assertEqual(set(REPRODUCIBILITY_LEVELS), {"bitwise", "numerical", "statistical", "qualitative", "unspecified"})
        self.assertEqual(set(REPRODUCTION_STATUSES), {"pending", "reproduced", "partially_reproduced", "not_reproduced", "failed"})
        bad_level = self._manifest(reproducibility_level="telepathic").to_dict()
        self.assertTrue(any("reproducibility_level" in e for e in validation.validate_reproduction_bundle_manifest(bad_level)))
        bad_status = self._manifest(reproduction_status="magic").to_dict()
        self.assertTrue(any("reproduction_status" in e for e in validation.validate_reproduction_bundle_manifest(bad_status)))

    def test_truthy_authority_flags_do_not_authorize(self):
        flags = (
            "materializes_bundle",
            "materializes",
            "exports_bundle",
            "exports",
            "publishes",
            "authorizes_publishing",
            "authorizes_real_execution",
            "real_execution_authorized",
            "locks_dataset",
            "dataset_locked",
            "creates_formal_evidence",
            "creates_evidence",
            "bypasses_gates",
        )
        for flag in flags:
            for truthy in (True, 1, "yes", ["x"]):
                data = self._manifest().to_dict()
                data[flag] = truthy
                self.assertTrue(any(flag in e for e in validation.validate_reproduction_bundle_manifest(data)), f"{flag}={truthy!r} should be rejected")
        clean = self._manifest().to_dict()
        for flag in flags:
            clean[flag] = False
        self.assertEqual(validation.validate_reproduction_bundle_manifest(clean), [])


if __name__ == "__main__":
    unittest.main()
