"""WP-17 — donor-level sc/snRNA route + cross-dataset consistency tests."""

from __future__ import annotations

import dataclasses
import tempfile
import unittest

from auto_bioinfo.routes import glue
from auto_bioinfo.routes.route_run import TERMINAL_COMPLETED, TERMINAL_INSUFFICIENT_DATA
from auto_bioinfo.routes.scrna_donor import (
    build_replicate_scrna_dataset,
    run_cross_dataset_consistency,
    run_scrna_donor_route,
)


class ScrnaDonorRouteTest(unittest.TestCase):
    def test_donor_route_completes(self):
        with tempfile.TemporaryDirectory() as d:
            run = run_scrna_donor_route(workspace=d)
        self.assertEqual(run.terminal_status, TERMINAL_COMPLETED)
        self.assertEqual(len(run.claims), 1)
        self.assertEqual(run.claims[0]["claim_level"], "association")
        self.assertEqual(run.alignment["final_decision"], "approve")

    def test_pseudobulk_aggregation_stage_uses_donor_unit(self):
        with tempfile.TemporaryDirectory() as d:
            run = run_scrna_donor_route(workspace=d)
        stage = run.stage("pseudobulk_aggregation")
        self.assertIsNotNone(stage)
        self.assertEqual(stage.payload["statistical_unit"], "donor")
        self.assertEqual(stage.payload["n_donors"], 6)
        self.assertEqual(stage.payload["donor_group_sizes"], {"normal": 3, "tumor": 3})

    def test_reproduction_bitwise_identical(self):
        with tempfile.TemporaryDirectory() as d:
            run = run_scrna_donor_route(workspace=d)
        self.assertEqual(run.reproduction["consistency_level"], "BITWISE_IDENTICAL")

    def test_missing_donor_is_rejected_not_inferred(self):
        with tempfile.TemporaryDirectory() as d:
            run = run_scrna_donor_route(workspace=d, overrides={"unknown_donors": True})
        self.assertEqual(run.terminal_status, TERMINAL_INSUFFICIENT_DATA)
        self.assertEqual(run.claims, [])
        # It stopped at feasibility (before any fabricated result).
        self.assertEqual(run.stage("feasibility").status, "stopped")

    def test_real_blank_donor_label_fails_closed_before_claims(self):
        # A genuinely partially missing donor label in the selected metadata (not
        # the synthetic ``unknown_donors`` shortcut) must fail closed before any
        # pseudobulk / DEG / claim / alignment / report / reproduction output.
        base = glue.load_route_dataset("scrna_donor_route")
        rows = base.files["cell_metadata"].splitlines()
        # Blank the donor field on exactly one selected (Tcell) cell row: "c07".
        patched = []
        for line in rows:
            parts = line.split("\t")
            if parts and parts[0] == "c07":
                parts[1] = ""  # donor column blanked
            patched.append("\t".join(parts))
        blank_donor_metadata = "\n".join(patched) + "\n"
        files = dict(base.files)
        files["cell_metadata"] = blank_donor_metadata
        dataset = dataclasses.replace(base, files=files)

        with tempfile.TemporaryDirectory() as d:
            run = run_scrna_donor_route(workspace=d, dataset=dataset)

        self.assertEqual(run.terminal_status, TERMINAL_INSUFFICIENT_DATA)
        self.assertEqual(run.claims, [])
        gate = run.stage("donor_identity_check")
        self.assertIsNotNone(gate)
        self.assertEqual(gate.status, "stopped")
        self.assertEqual(gate.payload["n_missing_donor"], 1)
        # Fail-closed happened before any fabricated downstream stage/object.
        self.assertIsNone(run.stage("pseudobulk_aggregation"))
        self.assertEqual(run.report, {})
        self.assertEqual(run.reproduction, {})

    def test_healthy_dataset_passes_donor_identity_check(self):
        with tempfile.TemporaryDirectory() as d:
            run = run_scrna_donor_route(workspace=d)
        gate = run.stage("donor_identity_check")
        self.assertIsNotNone(gate)
        self.assertEqual(gate.status, "ok")
        self.assertEqual(gate.payload["n_missing_donor"], 0)
        self.assertEqual(gate.payload["n_selected_cells"], 18)

    def test_determinism(self):
        out = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                run = run_scrna_donor_route(workspace=d)
                out.append((run.claims[0]["claim_id"], run.report["markdown_sha256"]))
        self.assertEqual(out[0], out[1])


class PseudobulkAggregationTest(unittest.TestCase):
    def test_cells_are_summed_to_donor_level(self):
        dataset = glue.load_route_dataset("scrna_donor_route")
        agg = glue.pseudobulk_aggregate(dataset.files["cell_counts"], dataset.files["cell_metadata"], cell_type="Tcell")
        self.assertEqual(len(agg["donors"]), 6)
        # every donor has 3 cells aggregated
        self.assertTrue(all(v == 3 for v in agg["cells_per_donor"].values()))
        # counts table has one column per donor
        header = agg["counts_tsv"].splitlines()[0].split("\t")
        self.assertEqual(header[0], "gene")
        self.assertEqual(len(header) - 1, 6)


class CrossDatasetConcordanceTest(unittest.TestCase):
    def test_keeps_every_outcome_not_only_agreements(self):
        with tempfile.TemporaryDirectory() as d:
            run = run_cross_dataset_consistency(workspace=d)
        c = run.concordance
        self.assertEqual(run.terminal_status, TERMINAL_COMPLETED)
        # consistent, conflicting, not_comparable and missing are ALL retained.
        self.assertGreaterEqual(c["n_consistent"], 1)
        self.assertGreaterEqual(c["n_conflicting"], 1)
        self.assertGreaterEqual(c["n_missing"], 1)
        states = {e["state"] for e in c["entries"]}
        self.assertIn("conflicting", states)
        self.assertIn("missing", states)

    def test_reanalysis_of_same_cohort_is_not_independent_replication(self):
        with tempfile.TemporaryDirectory() as d:
            run = run_cross_dataset_consistency(workspace=d)
        self.assertFalse(run.concordance["same_cohort"])
        self.assertIsNotNone(run.stage("replication_independence"))

    def test_concordance_is_deterministic(self):
        results = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                run = run_cross_dataset_consistency(workspace=d)
                results.append(run.concordance["counts"])
        self.assertEqual(results[0], results[1])

    def test_replicate_dataset_is_independent_and_synthetic(self):
        rep = build_replicate_scrna_dataset()
        # independent donor ids (r-prefixed), never the primary's donors
        self.assertIn("\trdonor_01\t", rep["cell_metadata"])
        self.assertNotIn("\tdonor_01\t", rep["cell_metadata"])


if __name__ == "__main__":
    unittest.main()
