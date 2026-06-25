import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.pipeline import Pipeline, PipelineError
from tests._helpers import DEMO_QUESTION, fixture_adapter


class _MockUnverifiedAdapter:
    """A resource adapter that (wrongly) returns a verified mock dataset."""

    def discover(self, research_spec, evidence_plan):
        return [{"resource_name": "x", "verified": True, "source_status": "mock_placeholder", "accession": "AUTO_X", "resource_candidate_id": "rc1"}]

    def profile(self, candidate):
        return {"dataset_id": "AUTO_X"}

    def materialize(self, profile, dest):
        return {}


class FailurePathTest(unittest.TestCase):
    def test_underpowered_dataset_stops_without_a_claim(self):
        with tempfile.TemporaryDirectory() as d:
            res = Pipeline(resources=fixture_adapter(1, 1)).run(Path(d) / "proj", DEMO_QUESTION)
            self.assertIn(res["current_stage"], {"METHOD_NOT_APPLICABLE", "INSUFFICIENT_DATA"})
            self.assertEqual(len(res["claims"]), 0)

    def test_mock_dataset_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PipelineError):
                Pipeline(resources=_MockUnverifiedAdapter()).run(Path(d) / "proj", DEMO_QUESTION)

    def test_no_question_for_new_project_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PipelineError):
                Pipeline().run(Path(d) / "proj")  # no prior state, no question

    def test_terminal_is_a_legal_end_state(self):
        from auto_bioinfo.core import state

        with tempfile.TemporaryDirectory() as d:
            res = Pipeline(resources=fixture_adapter(1, 1)).run(Path(d) / "proj", DEMO_QUESTION)
            self.assertIn(res["current_stage"], state.TERMINAL_STAGES)


if __name__ == "__main__":
    unittest.main()
