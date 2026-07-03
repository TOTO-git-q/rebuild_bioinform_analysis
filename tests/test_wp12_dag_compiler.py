"""WP-12 tests: WorkflowPlan + Artifact DAG compiler."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_workflow_plan
from auto_bioinfo.methods.compatibility import build_method_plan
from auto_bioinfo.methods.contract_registry import build_default_registry
from auto_bioinfo.workflow.dag_compiler import (
    COMPILE_OK,
    COMPILE_REPLAN,
    DIAG_UNCOVERED_SUBQUESTION,
    NODE_ANALYSIS,
    NODE_DATA_PREPARATION,
    NODE_REVIEW,
    ExecutionDefaults,
    affected_subgraph,
    compile_workflow,
)


def _bulk_profile(dataset_id="ds_bulk"):
    return {
        "dataset_id": dataset_id,
        "modality": "bulk_expression_matrix",
        "statistical_unit": "sample",
        "group_sizes": {"a": 3, "b": 3},
        "present_metadata": ["sample_group_labels"],
    }


def _sq(sqid="subquestion_a", ceiling="association"):
    return {"subquestion_id": sqid, "claim_ceiling": ceiling}


class CompileHappyPathTest(unittest.TestCase):
    def setUp(self):
        self.reg = build_default_registry()
        method_plan, _ = build_method_plan(self.reg, _bulk_profile(), _sq(), evidence_plan_id="evidence_plan_x", candidate_method_ids=["bulk_deg"])
        self.plans = [{"subquestion": _sq(), "method_plan": method_plan, "manifest_inputs": ["artifact_manifest_counts"]}]

    def test_compiles_acyclic_plan(self):
        result = compile_workflow(self.reg, self.plans, project_id="proj1")
        self.assertEqual(result.status, COMPILE_OK)
        self.assertIsNotNone(result.workflow_plan)
        self.assertEqual(validate_workflow_plan(result.workflow_plan), [])
        self.assertEqual(result.workflow_plan["status"], "draft")

    def test_three_node_types_present_and_separate(self):
        result = compile_workflow(self.reg, self.plans, project_id="proj1")
        types = {n["node_type"] for n in result.nodes}
        self.assertEqual(types, {NODE_DATA_PREPARATION, NODE_ANALYSIS, NODE_REVIEW})
        # Analysis and review never share a task id (separation of duties).
        analysis = [n for n in result.nodes if n["node_type"] == NODE_ANALYSIS]
        review = [n for n in result.nodes if n["node_type"] == NODE_REVIEW]
        self.assertTrue(set(n["task_id"] for n in analysis).isdisjoint(n["task_id"] for n in review))

    def test_edges_bind_by_artifact_id(self):
        result = compile_workflow(self.reg, self.plans, project_id="proj1")
        prep = next(n for n in result.nodes if n["node_type"] == NODE_DATA_PREPARATION)
        analysis = next(n for n in result.nodes if n["node_type"] == NODE_ANALYSIS)
        # Analysis consumes exactly the prep output artifact id.
        self.assertEqual(analysis["input_artifact_ids"], prep["output_artifact_ids"])

    def test_deterministic_plan_hash(self):
        r1 = compile_workflow(self.reg, self.plans, project_id="proj1")
        r2 = compile_workflow(self.reg, self.plans, project_id="proj1")
        self.assertEqual(r1.plan_hash, r2.plan_hash)
        self.assertEqual(r1.to_dict(), r2.to_dict())

    def test_markdown_and_json_node_counts_match(self):
        result = compile_workflow(self.reg, self.plans, project_id="proj1")
        self.assertEqual(result.dag_json["node_count"], len(result.nodes))
        self.assertIn("Workflow DAG", result.dag_markdown)

    def test_coverage_full(self):
        result = compile_workflow(self.reg, self.plans, project_id="proj1")
        self.assertTrue(result.coverage["fully_covered"])
        self.assertEqual(result.coverage["uncovered_subquestion_ids"], [])

    def test_every_output_has_expectation(self):
        result = compile_workflow(self.reg, self.plans, project_id="proj1")
        produced = {aid for n in result.nodes for aid in n["output_artifact_ids"]}
        expected = {e["artifact_id"] for e in result.artifact_expectations}
        self.assertEqual(produced, expected)


class CompileFailurePathTest(unittest.TestCase):
    def setUp(self):
        self.reg = build_default_registry()

    def test_method_not_applicable_blocks_compile(self):
        profile = {"dataset_id": "ds", "modality": "proteomics", "statistical_unit": "sample", "group_sizes": {"a": 3, "b": 3}}
        method_plan, _ = build_method_plan(self.reg, profile, _sq(), evidence_plan_id="evidence_plan_x")
        plans = [{"subquestion": _sq(), "method_plan": method_plan, "manifest_inputs": ["m1"]}]
        result = compile_workflow(self.reg, plans, project_id="proj1")
        self.assertEqual(result.status, COMPILE_REPLAN)
        self.assertIsNone(result.workflow_plan)
        self.assertEqual(result.task_packets, [])

    def test_uncovered_required_subquestion_blocks(self):
        method_plan, _ = build_method_plan(self.reg, _bulk_profile(), _sq("subquestion_a"), evidence_plan_id="ep", candidate_method_ids=["bulk_deg"])
        plans = [{"subquestion": _sq("subquestion_a"), "method_plan": method_plan, "manifest_inputs": ["m1"]}]
        result = compile_workflow(self.reg, plans, project_id="proj1", required_subquestion_ids=["subquestion_a", "subquestion_missing"])
        self.assertEqual(result.status, COMPILE_REPLAN)
        codes = {d["code"] for d in result.diagnostics}
        self.assertIn(DIAG_UNCOVERED_SUBQUESTION, codes)

    def test_missing_execution_field_blocks(self):
        method_plan, _ = build_method_plan(self.reg, _bulk_profile(), _sq(), evidence_plan_id="ep", candidate_method_ids=["bulk_deg"])
        plans = [{"subquestion": _sq(), "method_plan": method_plan, "manifest_inputs": ["m1"]}]
        # Blank out a required execution field.
        defaults = ExecutionDefaults(write_scope="")
        result = compile_workflow(self.reg, plans, project_id="proj1", execution_defaults=defaults)
        self.assertEqual(result.status, COMPILE_REPLAN)

    def test_injected_cycle_detected_by_validator(self):
        # A hand-built plan with a cycle must fail the workflow-plan validator.
        plan = {
            "schema_version": "v5.canonical/0.1",
            "workflow_name": "cyclic",
            "task_ids": ["a", "b"],
            "dependencies": [["a", "b"], ["b", "a"]],
        }
        errors = validate_workflow_plan(plan)
        self.assertTrue(any("cycle" in e for e in errors))


class AffectedSubgraphTest(unittest.TestCase):
    def test_downstream_only(self):
        reg = build_default_registry()
        method_plan, _ = build_method_plan(reg, _bulk_profile(), _sq(), evidence_plan_id="ep", candidate_method_ids=["bulk_deg"])
        plans = [{"subquestion": _sq(), "method_plan": method_plan, "manifest_inputs": ["m1"]}]
        result = compile_workflow(reg, plans, project_id="proj1")
        plan = result.workflow_plan
        prep = next(n for n in result.nodes if n["node_type"] == NODE_DATA_PREPARATION)
        review = next(n for n in result.nodes if n["node_type"] == NODE_REVIEW)
        # Changing prep invalidates its descendants (analysis + review), including itself.
        affected = affected_subgraph(plan, [prep["task_id"]])
        self.assertIn(prep["task_id"], affected)
        self.assertIn(review["task_id"], affected)
        # Changing the review (terminal) invalidates only itself.
        self.assertEqual(affected_subgraph(plan, [review["task_id"]]), [review["task_id"]])


if __name__ == "__main__":
    unittest.main()
