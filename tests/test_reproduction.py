import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.pipeline import Pipeline
from auto_bioinfo.reproduction.bundle import compare_bundle
from tests._helpers import DEMO_QUESTION, fixture_adapter


class ReproductionTest(unittest.TestCase):
    def _run(self, d):
        p = Path(d) / "proj"
        Pipeline(resources=fixture_adapter()).run(p, DEMO_QUESTION)
        return p

    def test_bundle_has_required_contents(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = self._run(d) / "reproduction_bundle"
            for required in [
                "checksums.sha256",
                "run_order.md",
                "comparison_spec.json",
                "research_spec.json",
                "dataset_manifest.json",
                "parameters.json",
                "environment.json",
                "claims.json",
            ]:
                self.assertTrue((bundle / required).exists(), required)
            self.assertTrue((bundle / "inputs" / "counts.tsv").exists())
            self.assertTrue(any((bundle / "outputs").iterdir()))

    def test_clean_bundle_reproduces_bitwise(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = self._run(d) / "reproduction_bundle"
            self.assertEqual(compare_bundle(bundle)["overall_level"], "BITWISE_IDENTICAL")

    def test_tampered_bundle_detected(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = self._run(d) / "reproduction_bundle"
            target = bundle / "outputs" / "deg_results.tsv"
            target.write_text(target.read_text() + "\nTAMPERED\t0\t0\t0\t0\t0\t1\t1\tup_in_a\tFalse\n", encoding="utf-8")
            self.assertEqual(compare_bundle(bundle)["overall_level"], "NOT_REPRODUCED")


if __name__ == "__main__":
    unittest.main()
