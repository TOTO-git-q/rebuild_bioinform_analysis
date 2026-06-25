import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.core.artifacts import validate_artifact_for_evidence
from auto_bioinfo.pipeline import Pipeline
from tests._helpers import DEMO_QUESTION, fixture_adapter


class EndToEndTest(unittest.TestCase):
    def run_demo(self, d):
        return Pipeline(resources=fixture_adapter()).run(Path(d) / "proj", DEMO_QUESTION)

    def test_full_closed_loop_completes(self):
        with tempfile.TemporaryDirectory() as d:
            res = self.run_demo(d)
            self.assertEqual(res["current_stage"], "COMPLETED")
            self.assertEqual(len(res["claims"]), 1)
            self.assertEqual(res["claims"][0]["claim_level"], "association")
            self.assertEqual(res["alignment"]["final_decision"], "approve")
            self.assertEqual(len(res["evidence_items"]), 1)
            self.assertEqual(len(res["qc_reports"]), 1)
            self.assertEqual(len(res["artifacts"]), 1)

    def test_every_main_stage_visited_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            res = self.run_demo(d)
            expect = [
                "INTAKE",
                "QUESTION_RESOLVED",
                "SCOPE_RESOLVED",
                "EVIDENCE_PLANNED",
                "RESOURCES_DISCOVERED",
                "DATASETS_LOCKED",
                "WORKFLOW_COMPILED",
                "TASKS_READY",
                "TASKS_RUNNING",
                "QC_COMPLETED",
                "EVIDENCE_SYNTHESIZED",
                "ALIGNMENT_AUDITED",
                "REPORT_READY",
                "REPRODUCTION_BUNDLE_READY",
                "COMPLETED",
            ]
            self.assertEqual(res["stage_history"], expect)

    def test_claim_traces_to_qc_passed_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            res = self.run_demo(d)
            claim = res["claims"][0]
            evidence_by_id = {e["evidence_item_id"]: e for e in res["evidence_items"]}
            artifact_by_id = {a["artifact_id"]: a for a in res["artifacts"]}
            for eid in claim["evidence_item_refs"]:
                ev = evidence_by_id[eid]
                art = artifact_by_id[ev["artifact_id"]]
                self.assertEqual(art["qc_status"], "pass")
                self.assertEqual(validate_artifact_for_evidence(art), [])

    def test_resume_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            Pipeline(resources=fixture_adapter()).run(p, DEMO_QUESTION)
            claims1 = (p / "state" / "claims.jsonl").read_text()
            events1 = (p / "state" / "events.jsonl").read_text()
            Pipeline(resources=fixture_adapter()).run(p)  # resume on a completed project
            self.assertEqual((p / "state" / "claims.jsonl").read_text(), claims1)
            self.assertEqual((p / "state" / "events.jsonl").read_text(), events1)


if __name__ == "__main__":
    unittest.main()
