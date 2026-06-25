import tempfile
import unittest

from auto_bioinfo.methods._stats import benjamini_hochberg, student_t_two_sided_p, welch_t_test
from auto_bioinfo.methods.bulk_deg import BulkDegMethod
from auto_bioinfo.methods.registry import compatibility_decision, get_method
from auto_bioinfo.quality.qc_engine import run_four_layer_qc
from tests._helpers import tiny_fixture


class StatsTest(unittest.TestCase):
    def test_t_distribution_matches_known_critical_values(self):
        self.assertAlmostEqual(student_t_two_sided_p(2.776, 4), 0.05, places=3)
        self.assertAlmostEqual(student_t_two_sided_p(0.0, 10), 1.0, places=6)

    def test_welch_requires_two_per_group(self):
        with self.assertRaises(ValueError):
            welch_t_test([1.0], [2.0, 3.0])

    def test_bh_monotone_and_bounded(self):
        adj = benjamini_hochberg([0.01, 0.02, 0.03, 0.5])
        self.assertTrue(all(0.0 <= v <= 1.0 for v in adj))


class BulkDegTest(unittest.TestCase):
    def setUp(self):
        self.fx = tiny_fixture(3, 3)
        self.method = BulkDegMethod()

    def test_runs_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            inp = {"counts": str(self.fx / "counts.tsv"), "samples": str(self.fx / "samples.tsv")}
            r1 = self.method.run(inputs=inp, params={}, out_dir=d1)
            r2 = self.method.run(inputs=inp, params={}, out_dir=d2)
            self.assertEqual(r1["status"], "succeeded")
            self.assertGreaterEqual(r1["n_significant"], 1)
            self.assertEqual(open(r1["output_path"]).read(), open(r2["output_path"]).read())

    def test_precondition_failed_on_single_replicate(self):
        fx = tiny_fixture(1, 1)
        with tempfile.TemporaryDirectory() as d:
            r = self.method.run(inputs={"counts": str(fx / "counts.tsv"), "samples": str(fx / "samples.tsv")}, params={}, out_dir=d)
            self.assertEqual(r["status"], "precondition_failed")

    def test_contract_caps_claim_at_association(self):
        self.assertEqual(self.method.contract()["claim_capability"], "association")

    def test_compatibility_rejects_underpowered_dataset(self):
        bad_profile = {"dataset_id": "x", "modality": "bulk_expression_matrix", "group_sizes": {"condition_a": 1, "condition_b": 1}}
        self.assertFalse(compatibility_decision("bulk_deg", bad_profile)["compatible"])


class QcGateTest(unittest.TestCase):
    def _good(self):
        return (
            {"status": "succeeded", "n_genes": 10, "group_sizes": {"condition_a": 3, "condition_b": 3}, "outputs": {"deg_results_table": "x"}},
            {"modality": "bulk_expression_matrix", "group_sizes": {"condition_a": 3, "condition_b": 3}},
            {"artifact_id": "a1", "exists": True, "size_bytes": 100, "checksum_sha256": "abc"},
            get_method("bulk_deg").contract(),
        )

    def test_passes_on_good_run(self):
        mr, dp, art, ct = self._good()
        self.assertEqual(run_four_layer_qc(method_result=mr, dataset_profile=dp, artifact_manifest=art, contract=ct)["overall_status"], "pass")

    def test_statistical_layer_fails_on_pseudo_replication(self):
        mr, dp, art, ct = self._good()
        mr["group_sizes"] = {"condition_a": 1, "condition_b": 1}
        report = run_four_layer_qc(method_result=mr, dataset_profile=dp, artifact_manifest=art, contract=ct)
        self.assertEqual(report["overall_status"], "fail")
        self.assertTrue(any(c["layer"] == "statistical" and c["status"] == "fail" for c in report["checks"]))


if __name__ == "__main__":
    unittest.main()
