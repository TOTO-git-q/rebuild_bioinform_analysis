"""WP-26 — the requirement-coverage matrix is present, honest and consistent."""

from __future__ import annotations

import unittest

from auto_bioinfo.routes.requirement_coverage import (
    COVERAGE_STATUSES,
    build_requirement_coverage_matrix,
    coverage_for,
    coverage_gaps,
)


class CoverageMatrixTest(unittest.TestCase):
    def setUp(self):
        self.matrix = build_requirement_coverage_matrix()

    def test_matrix_is_deterministic(self):
        self.assertEqual(build_requirement_coverage_matrix(), build_requirement_coverage_matrix())
        self.assertEqual(self.matrix["created_at"], "")

    def test_every_entry_has_a_bounded_status_and_evidence(self):
        for entry in self.matrix["entries"]:
            self.assertIn(entry["status"], COVERAGE_STATUSES)
            self.assertTrue(entry["covered_by"], entry)
            self.assertTrue(entry["wp_id"])
            self.assertTrue(entry["task_id"])

    def test_summary_counts_are_consistent(self):
        s = self.matrix["summary"]
        self.assertEqual(s["total"], len(self.matrix["entries"]))
        self.assertEqual(s["covered"] + s["partial"] + s["gap"], s["total"])

    def test_gaps_are_explicit_not_hidden(self):
        # WP-26 forbids a silent "N/A"; gaps must be listed with a reason.
        gaps = coverage_gaps()
        self.assertEqual(len(gaps), self.matrix["summary"]["gap"])
        for g in gaps:
            self.assertIn(":", g)  # "WP-16 T-16-07: <requirement>"

    def test_capstone_wps_are_all_represented(self):
        for wp in ("WP-16", "WP-17", "WP-26"):
            self.assertTrue(coverage_for(wp), f"no coverage entries for {wp}")

    def test_full_bulk_and_scrna_loops_are_covered(self):
        by_task = {(e["wp_id"], e["task_id"]): e for e in self.matrix["entries"]}
        self.assertEqual(by_task[("WP-26", "T-26-05")]["status"], "covered")
        self.assertEqual(by_task[("WP-26", "T-26-06")]["status"], "covered")

    def test_bridges_document_the_offline_seams(self):
        bridges = self.matrix["bridges"]
        self.assertTrue(bridges)
        names = {b["bridge"] for b in bridges}
        self.assertIn("routes.glue.pseudobulk_aggregate", names)
        self.assertIn("routes.glue.cross_dataset_concordance", names)
        # PR #46 offline tool/capability reuse is documented as a bridge.
        self.assertIn("routes.glue.select_discovery_tool_plan", names)
        self.assertIn("routes.glue.capability_gate", names)

    def test_known_gaps_are_documented(self):
        # e.g. plotting / enrichment / differential-abundance runners are out of scope.
        gap_ids = {g.split(":")[0] for g in coverage_gaps()}
        self.assertIn("WP-16 T-16-07", gap_ids)


if __name__ == "__main__":
    unittest.main()
