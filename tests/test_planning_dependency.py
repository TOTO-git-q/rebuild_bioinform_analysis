"""Unit tests for the local offline sub-question dependency-graph + coverage command (WP-07 / T-07-04, T-07-09).

Covers, for the bounded local/offline planning commands over synthetic toy draft
sub-questions and evidence-plan references only (no real research content, no
external LLM/provider/search/network call, no persistence, no event, no granted
approval, no project stage transition):

- a valid DAG of explicit parent/relation dependencies → an inert ``graph_built``
  outcome carrying a ``DependencyGraph`` *draft* (``status == "draft"``,
  ``created_at == ""``) and the correct deterministic topological order,
- a cyclic dependency (including a self-dependency) → ``cycle_detected`` with no
  topological order,
- an edge whose endpoint was never declared → ``dangling_node``,
- full coverage (every sub-question referenced by an evidence plan or explicitly
  not-answered) → ``coverage_complete``,
- a sub-question with neither a plan nor a not-answered decision →
  ``coverage_incomplete`` with the uncovered ids blocking advancement,
- byte-determinism, non-mutation of inputs, the produced graph passing
  ``validate_dependency_graph``, and the bounded status/reason-code vocabulary.
"""

import copy
import dataclasses
import unittest

from auto_bioinfo.core.schemas import EvidencePlan, SubQuestion
from auto_bioinfo.core.validation import validate_dependency_graph
from auto_bioinfo.planning.dependency import (
    CODE_COVERAGE_COMPLETE,
    CODE_COVERAGE_INCOMPLETE,
    CODE_CYCLE_DETECTED,
    CODE_DANGLING_ENDPOINT,
    CODE_GRAPH_BUILT,
    CODE_INPUT_MALFORMED,
    DRAFT_STATUS,
    REASON_CODES,
    STATUS_COVERAGE_COMPLETE,
    STATUS_COVERAGE_INCOMPLETE,
    STATUS_CYCLE_DETECTED,
    STATUS_DANGLING_NODE,
    STATUS_GRAPH_BUILT,
    STATUS_REJECTED_MALFORMED,
    STATUSES,
    CoverageReport,
    CoverageResult,
    DependencyResult,
    assess_coverage,
    build_dependency_graph,
)

RSID = "research_spec_demo"


def _sq(subquestion_id, parent="", *, research_spec_id=RSID, question=None):
    """A synthetic inert draft SubQuestion with an explicit stable id."""
    return SubQuestion(
        research_spec_id=research_spec_id,
        question=question or f"what is {subquestion_id}",
        subquestion_id=subquestion_id,
        parent_subquestion_id=parent,
    )


def _plan(*subquestion_ids, research_spec_id=RSID):
    """A synthetic inert draft EvidencePlan referencing the given sub-questions."""
    return EvidencePlan(research_spec_id=research_spec_id, evidence_axes=["expression"], subquestion_ids=list(subquestion_ids))


class BuildDependencyGraphTests(unittest.TestCase):
    def test_valid_dag_from_parent_links_proceeds_with_topological_order(self):
        # c depends on b, b depends on a  →  order a, b, c (prerequisites first).
        subs = [_sq("sq_c", parent="sq_b"), _sq("sq_b", parent="sq_a"), _sq("sq_a")]
        result = build_dependency_graph(subs)
        self.assertEqual(result.status, STATUS_GRAPH_BUILT)
        self.assertEqual(result.reason_code, CODE_GRAPH_BUILT)
        self.assertTrue(result.graph_built)
        self.assertEqual(result.topological_order, ["sq_a", "sq_b", "sq_c"])
        graph = result.dependency_graph
        self.assertIsNotNone(graph)
        self.assertEqual(graph["status"], DRAFT_STATUS)
        self.assertEqual(graph["created_at"], "")
        self.assertEqual(sorted(graph["nodes"]), ["sq_a", "sq_b", "sq_c"])
        # Edge convention: [from, to] = "from depends on to".
        self.assertIn(["sq_b", "sq_a"], graph["edges"])
        self.assertIn(["sq_c", "sq_b"], graph["edges"])

    def test_produced_graph_passes_validate_dependency_graph(self):
        subs = [_sq("sq_a"), _sq("sq_b", parent="sq_a")]
        result = build_dependency_graph(subs)
        self.assertEqual(result.status, STATUS_GRAPH_BUILT)
        self.assertEqual(validate_dependency_graph(result.dependency_graph), [])

    def test_explicit_relation_pairs_create_edges(self):
        subs = ["sq_a", "sq_b"]  # bare-id nodes, no parent links
        result = build_dependency_graph(subs, relations=[["sq_b", "sq_a"]], research_spec_id=RSID)
        self.assertEqual(result.status, STATUS_GRAPH_BUILT)
        self.assertIn(["sq_b", "sq_a"], result.dependency_graph["edges"])
        self.assertEqual(result.topological_order, ["sq_a", "sq_b"])

    def test_relation_as_mapping_is_accepted(self):
        result = build_dependency_graph(["sq_a", "sq_b"], relations=[{"from": "sq_b", "to": "sq_a"}], research_spec_id=RSID)
        self.assertEqual(result.status, STATUS_GRAPH_BUILT)
        self.assertIn(["sq_b", "sq_a"], result.dependency_graph["edges"])

    def test_no_dependencies_is_a_valid_independent_dag(self):
        result = build_dependency_graph([_sq("sq_a"), _sq("sq_b")])
        self.assertEqual(result.status, STATUS_GRAPH_BUILT)
        self.assertEqual(result.dependency_graph["edges"], [])
        self.assertEqual(result.topological_order, ["sq_a", "sq_b"])


class CycleTests(unittest.TestCase):
    def test_two_node_cycle_is_detected(self):
        subs = [_sq("sq_a", parent="sq_b"), _sq("sq_b", parent="sq_a")]
        result = build_dependency_graph(subs)
        self.assertEqual(result.status, STATUS_CYCLE_DETECTED)
        self.assertEqual(result.reason_code, CODE_CYCLE_DETECTED)
        self.assertTrue(result.has_cycle)
        self.assertEqual(result.topological_order, [])
        # The failing draft is still carried for review.
        self.assertIsNotNone(result.dependency_graph)

    def test_self_dependency_is_a_cycle(self):
        result = build_dependency_graph([_sq("sq_a", parent="sq_a")])
        self.assertEqual(result.status, STATUS_CYCLE_DETECTED)
        self.assertEqual(result.reason_code, CODE_CYCLE_DETECTED)

    def test_longer_cycle_via_relations_is_detected(self):
        result = build_dependency_graph(
            ["sq_a", "sq_b", "sq_c"],
            relations=[["sq_a", "sq_b"], ["sq_b", "sq_c"], ["sq_c", "sq_a"]],
            research_spec_id=RSID,
        )
        self.assertEqual(result.status, STATUS_CYCLE_DETECTED)


class DanglingEndpointTests(unittest.TestCase):
    def test_parent_link_to_undeclared_node_is_dangling(self):
        # sq_b names a parent that is not one of the declared sub-questions.
        result = build_dependency_graph([_sq("sq_a"), _sq("sq_b", parent="sq_missing")])
        self.assertEqual(result.status, STATUS_DANGLING_NODE)
        self.assertEqual(result.reason_code, CODE_DANGLING_ENDPOINT)
        self.assertEqual(result.dangling_endpoints, ["sq_missing"])
        self.assertEqual(result.topological_order, [])

    def test_relation_to_undeclared_node_is_dangling(self):
        result = build_dependency_graph(["sq_a"], relations=[["sq_a", "sq_ghost"]], research_spec_id=RSID)
        self.assertEqual(result.status, STATUS_DANGLING_NODE)
        self.assertIn("sq_ghost", result.dangling_endpoints)


class BuildMalformedInputTests(unittest.TestCase):
    def test_non_sequence_subquestions_fail_closed(self):
        for bad in (None, "sq_a", 5, {"subquestion_id": "sq_a"}):
            result = build_dependency_graph(bad)
            self.assertEqual(result.status, STATUS_REJECTED_MALFORMED, bad)
            self.assertEqual(result.reason_code, CODE_INPUT_MALFORMED, bad)

    def test_empty_subquestions_fail_closed(self):
        result = build_dependency_graph([])
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_INPUT_MALFORMED)

    def test_unrecognised_subquestion_shape_fails_closed(self):
        result = build_dependency_graph([_sq("sq_a"), 123])
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)

    def test_duplicate_node_ids_fail_closed(self):
        result = build_dependency_graph([_sq("sq_a"), _sq("sq_a")])
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_INPUT_MALFORMED)

    def test_subquestions_spanning_multiple_specs_fail_closed(self):
        subs = [_sq("sq_a", research_spec_id="research_spec_one"), _sq("sq_b", research_spec_id="research_spec_two")]
        result = build_dependency_graph(subs)
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)

    def test_invalid_research_spec_id_fails_closed(self):
        result = build_dependency_graph(["sq_a"], research_spec_id="Not An Id")
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)

    def test_bare_ids_without_research_spec_id_fail_closed(self):
        result = build_dependency_graph(["sq_a", "sq_b"])
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)

    def test_malformed_relation_fails_closed(self):
        for bad in ([["sq_a"]], [["sq_a", "sq_b", "sq_c"]], [42], "sq_a"):
            result = build_dependency_graph(["sq_a", "sq_b"], relations=bad, research_spec_id=RSID)
            self.assertEqual(result.status, STATUS_REJECTED_MALFORMED, bad)


class AssessCoverageTests(unittest.TestCase):
    def test_full_coverage_by_evidence_plans_is_complete(self):
        subs = [_sq("sq_a"), _sq("sq_b")]
        result = assess_coverage(subs, evidence_plans=[_plan("sq_a"), _plan("sq_b")])
        self.assertEqual(result.status, STATUS_COVERAGE_COMPLETE)
        self.assertEqual(result.reason_code, CODE_COVERAGE_COMPLETE)
        self.assertTrue(result.coverage_complete)
        self.assertEqual(result.uncovered, [])
        report = result.coverage_report
        self.assertEqual(report["covered"], ["sq_a", "sq_b"])
        self.assertTrue(report["complete"])
        self.assertEqual(report["status"], DRAFT_STATUS)
        self.assertEqual(report["created_at"], "")

    def test_not_answered_decision_counts_as_covered(self):
        subs = [_sq("sq_a"), _sq("sq_b")]
        result = assess_coverage(subs, evidence_plans=[_plan("sq_a")], not_answered=["sq_b"])
        self.assertEqual(result.status, STATUS_COVERAGE_COMPLETE)
        self.assertEqual(result.coverage_report["not_answered"], ["sq_b"])
        self.assertEqual(result.coverage_report["covered"], ["sq_a"])

    def test_uncovered_subquestion_blocks_advancement(self):
        subs = [_sq("sq_a"), _sq("sq_b"), _sq("sq_c")]
        result = assess_coverage(subs, evidence_plans=[_plan("sq_a")], not_answered=["sq_b"])
        self.assertEqual(result.status, STATUS_COVERAGE_INCOMPLETE)
        self.assertEqual(result.reason_code, CODE_COVERAGE_INCOMPLETE)
        self.assertFalse(result.coverage_complete)
        self.assertEqual(result.uncovered, ["sq_c"])
        self.assertEqual(result.coverage_report["uncovered"], ["sq_c"])
        self.assertFalse(result.coverage_report["complete"])

    def test_no_plans_and_no_decisions_are_all_uncovered(self):
        result = assess_coverage([_sq("sq_a"), _sq("sq_b")])
        self.assertEqual(result.status, STATUS_COVERAGE_INCOMPLETE)
        self.assertEqual(result.uncovered, ["sq_a", "sq_b"])

    def test_plan_reference_shapes_are_tolerated(self):
        subs = [_sq("sq_a"), _sq("sq_b"), _sq("sq_c"), _sq("sq_d")]
        plans = [
            _plan("sq_a"),  # EvidencePlan instance
            {"subquestion_ids": ["sq_b"]},  # mapping projection
            ["sq_c"],  # plain id list
            "sq_d",  # single id string
        ]
        result = assess_coverage(subs, evidence_plans=plans)
        self.assertEqual(result.status, STATUS_COVERAGE_COMPLETE)

    def test_not_answered_as_mapping_is_tolerated(self):
        subs = [_sq("sq_a")]
        result = assess_coverage(subs, not_answered=[{"subquestion_id": "sq_a"}])
        self.assertEqual(result.status, STATUS_COVERAGE_COMPLETE)

    def test_plan_precedence_over_not_answered_for_same_id(self):
        subs = [_sq("sq_a")]
        result = assess_coverage(subs, evidence_plans=[_plan("sq_a")], not_answered=["sq_a"])
        self.assertEqual(result.coverage_report["covered"], ["sq_a"])
        self.assertEqual(result.coverage_report["not_answered"], [])


class CoverageMalformedInputTests(unittest.TestCase):
    def test_empty_subquestions_fail_closed(self):
        result = assess_coverage([])
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)
        self.assertEqual(result.reason_code, CODE_INPUT_MALFORMED)

    def test_non_sequence_plans_fail_closed(self):
        result = assess_coverage([_sq("sq_a")], evidence_plans="sq_a")
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)

    def test_malformed_plan_element_fails_closed(self):
        result = assess_coverage([_sq("sq_a")], evidence_plans=[42])
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)

    def test_malformed_not_answered_element_fails_closed(self):
        result = assess_coverage([_sq("sq_a")], not_answered=[42])
        self.assertEqual(result.status, STATUS_REJECTED_MALFORMED)


class DeterminismAndIsolationTests(unittest.TestCase):
    def test_build_is_byte_deterministic(self):
        subs = [_sq("sq_c", parent="sq_b"), _sq("sq_b", parent="sq_a"), _sq("sq_a")]
        a = build_dependency_graph(subs).to_dict()
        b = build_dependency_graph(subs).to_dict()
        self.assertEqual(a, b)

    def test_coverage_is_byte_deterministic(self):
        subs = [_sq("sq_a"), _sq("sq_b")]
        a = assess_coverage(subs, evidence_plans=[_plan("sq_a")]).to_dict()
        b = assess_coverage(subs, evidence_plans=[_plan("sq_a")]).to_dict()
        self.assertEqual(a, b)

    def test_inputs_are_not_mutated(self):
        subs = [_sq("sq_a"), _sq("sq_b", parent="sq_a")]
        before = [copy.deepcopy(s.to_dict()) for s in subs]
        plans = [_plan("sq_a", "sq_b")]
        plans_before = [copy.deepcopy(p.to_dict()) for p in plans]
        na = ["sq_a"]
        na_before = list(na)
        build_dependency_graph(subs)
        assess_coverage(subs, evidence_plans=plans, not_answered=na)
        self.assertEqual([s.to_dict() for s in subs], before)
        self.assertEqual([p.to_dict() for p in plans], plans_before)
        self.assertEqual(na, na_before)


class BoundedContractTests(unittest.TestCase):
    def test_status_and_reason_code_vocabularies_are_bounded(self):
        self.assertEqual(len(STATUSES), 6)
        self.assertEqual(len(set(STATUSES)), 6)
        self.assertEqual(len(set(REASON_CODES)), len(REASON_CODES))

    def test_results_are_frozen_inert_dataclasses(self):
        dep = build_dependency_graph([_sq("sq_a")])
        cov = assess_coverage([_sq("sq_a")], evidence_plans=[_plan("sq_a")])
        self.assertIsInstance(dep, DependencyResult)
        self.assertIsInstance(cov, CoverageResult)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            dep.status = "tampered"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            cov.status = "tampered"

    def test_coverage_report_is_a_frozen_inert_dataclass(self):
        report = CoverageReport(research_spec_id=RSID)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            report.complete = True


if __name__ == "__main__":
    unittest.main()
