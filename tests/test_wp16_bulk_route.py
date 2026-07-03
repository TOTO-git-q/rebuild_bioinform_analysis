"""WP-16 — offline bulk RNA-seq route: end-to-end acceptance tests."""

from __future__ import annotations

import tempfile
import unittest

from auto_bioinfo.routes.bulk_rnaseq import run_bulk_rnaseq_route
from auto_bioinfo.routes.route_run import TERMINAL_COMPLETED


class BulkRouteEndToEndTest(unittest.TestCase):
    def _run(self, workspace: str, **kw):
        return run_bulk_rnaseq_route(workspace=workspace, **kw)

    def test_route_completes_closed_loop(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertEqual(run.terminal_status, TERMINAL_COMPLETED)
        self.assertTrue(run.completed)

    def test_every_main_stage_runs_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        expected = [
            "intake_policy",
            "intake_normalize",
            "scope_resolve",
            "decompose",
            "dependency",
            "evidence_plan",
            "tool_capability_gate",
            "discovery",
            "verification",
            "feasibility",
            "dataset_lock",
            "method_plan",
            "workflow_compile",
            "artifact_registry",
            "authorization",
            "execute",
            "qc",
            "evidence_admission",
            "claim_synthesis",
            "alignment",
            "report",
            "reproduction",
        ]
        self.assertEqual(run.stage_names, expected)
        self.assertTrue(all(s.ok for s in run.stages))

    def test_exactly_one_association_claim(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertEqual(len(run.claims), 1)
        self.assertEqual(run.claims[0]["claim_level"], "association")
        self.assertEqual(run.claims[0]["status"], "supports")

    def test_claim_never_exceeds_ceiling(self):
        # The whole chain caps at 'association'; nothing may be higher.
        order = [
            "descriptive",
            "association",
            "co_expression",
            "candidate_biomarker",
            "mechanistic_hypothesis",
            "causal_support",
            "experimentally_validated_target",
        ]
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        ceiling_idx = order.index("association")
        for claim in run.claims:
            self.assertLessEqual(order.index(claim["claim_level"]), ceiling_idx)
        self.assertEqual(run.evidence_items[0]["allowed_claim_level"], "association")

    def test_dataset_manifest_is_locked_with_checksums(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertTrue(run.dataset_manifest["locked"])
        self.assertTrue(run.dataset_manifest["file_checksums"])

    def test_qc_passed_and_alignment_approved(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertEqual(run.qc_reports[0]["decision"], "PASS")
        self.assertEqual(run.alignment["final_decision"], "approve")

    def test_claim_traces_to_qc_passed_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        claim = run.claims[0]
        evidence_by_id = {e["evidence_item_id"]: e for e in run.evidence_items}
        for eid in claim["evidence_item_refs"]:
            ev = evidence_by_id[eid]
            self.assertEqual(ev["qc_status"], "pass")
        self.assertTrue(run.report["trace_complete"])

    def test_report_is_publishable_and_released(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertTrue(run.report["publishable"])
        self.assertEqual(run.report["status"], "RELEASED")
        self.assertEqual(run.report["blocking_reasons"], [])

    def test_reproduction_bundle_is_bitwise_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertEqual(run.reproduction["verify"], "VALID")
        self.assertTrue(run.reproduction["reproduced"])
        self.assertEqual(run.reproduction["consistency_level"], "BITWISE_IDENTICAL")

    def test_task_runs_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertTrue(run.task_runs)
        self.assertTrue(all(t.get("result_status") == "completed" for t in run.task_runs))

    def test_offline_tool_selection_produced_a_deny_by_default_plan(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        gate = run.stage("tool_capability_gate")
        self.assertIsNotNone(gate)
        self.assertEqual(gate.payload["materialization_decision"], "deny")
        self.assertEqual(gate.payload["tool_id"], "geo_dataset_search")

    def test_determinism_byte_identical_across_runs(self):
        results = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                run = self._run(d)
                results.append(
                    (
                        run.claims[0]["claim_id"],
                        run.dataset_manifest["dataset_manifest_id"],
                        run.report["markdown_sha256"],
                        run.evidence_items[0]["evidence_item_id"],
                    )
                )
        self.assertEqual(results[0], results[1])

    def test_produced_route_record_has_empty_created_at(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(d)
        self.assertEqual(run.created_at, "")
        self.assertEqual(run.claims[0]["created_at"], "")
        self.assertEqual(run.evidence_items[0]["created_at"], "")


if __name__ == "__main__":
    unittest.main()
