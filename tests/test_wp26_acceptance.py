"""WP-26 — end-to-end acceptance: prove the system answers the original request.

These tests drive the WP-16/17 routes and assert on *acceptance-level* facts
(planning, resource lock, DAG execution, trace, reproduction) rather than only
that modules exist.
"""

from __future__ import annotations

import tempfile
import unittest

from auto_bioinfo.routes.bulk_rnaseq import run_bulk_rnaseq_route
from auto_bioinfo.routes.route_run import TERMINAL_COMPLETED


class AcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.route = run_bulk_rnaseq_route(workspace=cls._dir.name)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    # T-26-02 — planning-only projection is real and versioned.
    def test_planning_projection_present(self):
        self.assertTrue(self.route.research_spec.get("research_spec_id"))
        self.assertTrue(self.route.subquestions)
        self.assertTrue(self.route.evidence_plans)
        self.assertEqual(self.route.evidence_plans[0]["max_claim_level"], "association")

    # T-26-03 — real resource discovery/verification/feasibility/lock.
    def test_resource_lock_has_verified_checksums(self):
        self.assertTrue(self.route.dataset_manifest["locked"])
        self.assertTrue(self.route.dataset_manifest["accession"])
        self.assertTrue(self.route.dataset_manifest["file_checksums"])
        # every checksum is a 64-hex sha-256
        for digest in self.route.dataset_manifest["file_checksums"].values():
            self.assertEqual(len(digest), 64)

    # T-26-04 — general DAG / worker / artifact / lineage.
    def test_dag_executed_with_recorded_task_runs(self):
        self.assertTrue(self.route.workflow_plan["task_ids"])
        self.assertTrue(self.route.task_runs)
        self.assertTrue(self.route.artifacts)
        self.assertEqual(self.route.artifacts[0]["state"], "VALID")

    # T-26-05 — full bulk closed loop.
    def test_full_closed_loop(self):
        self.assertEqual(self.route.terminal_status, TERMINAL_COMPLETED)

    # T-26-11 — reproduction bundle clean-room reproducible.
    def test_reproduction_clean_room(self):
        self.assertEqual(self.route.reproduction["verify"], "VALID")
        self.assertEqual(self.route.reproduction["consistency_level"], "BITWISE_IDENTICAL")

    # T-26-12 — reverse trace from claim to original request/data/params/run.
    def test_reverse_trace_is_complete(self):
        self.assertTrue(self.route.report["trace_complete"])
        # the claim references evidence -> which references an artifact and a task run
        claim = self.route.claims[0]
        self.assertTrue(claim["evidence_item_refs"])
        ev = self.route.evidence_items[0]
        self.assertTrue(ev["source_task_run_ids"])
        self.assertTrue(ev["artifact_id"])
        # original request is preserved in the research spec
        self.assertTrue(self.route.research_spec.get("research_question"))


if __name__ == "__main__":
    unittest.main()
