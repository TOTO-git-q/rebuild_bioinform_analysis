"""Work Order R0-01 bypass tests: a test fixture can never be passed off as a
real scientific result.  These are the eight adversarial cases the frozen R0-01
baseline requires."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from auto_bioinfo.core.provenance import (
    evaluate_scientific_eligibility,
    is_formally_exportable,
    normalize_legacy_provenance,
    recompute_eligibility_for,
    validate_policy_state_consistency,
    validate_provenance,
)
from auto_bioinfo.interfaces.cli import main
from auto_bioinfo.pipeline import Pipeline, PipelineError
from tests._helpers import DEMO_QUESTION, fixture_adapter


def _policy(mode="DEMO"):
    return {"execution_mode": mode, "project_policy_id": "pp1", "policy_version": 1}


class TruthfulModeBypassTest(unittest.TestCase):
    # 1. A manually-set eligible=true is ignored; the gate recomputes from facts.
    def test_tampered_eligible_flag_is_ignored(self):
        tampered = {"evidence_item_id": "ev", "source_class": "SYNTHETIC_FIXTURE", "verification_level": "FILES_CHECKSUM_VERIFIED", "scientific_output_eligible": True}
        decision = recompute_eligibility_for(tampered, qc_status="pass", policy=_policy("DEMO"))
        self.assertEqual(decision["decision"], "INELIGIBLE")
        self.assertIn("EXECUTION_MODE_NOT_REAL", decision["reason_codes"])

    # 2. A DEMO/fixture artifact dressed as REAL is rejected by recomputation.
    def test_demo_artifact_cannot_masquerade_as_real_evidence(self):
        obj = {"source_class": "SYNTHETIC_FIXTURE", "verification_level": "FILES_CHECKSUM_VERIFIED"}
        decision = recompute_eligibility_for(obj, qc_status="pass", policy=_policy("REAL"))
        self.assertEqual(decision["decision"], "INELIGIBLE")
        self.assertIn("SOURCE_CLASS_NOT_REAL_DATA", decision["reason_codes"])

    # 3. REAL + SYNTHETIC_FIXTURE stops at POLICY_FAILURE before any lock.
    def test_real_mode_with_fixture_is_policy_failure(self):
        with tempfile.TemporaryDirectory() as d:
            res = Pipeline(resources=fixture_adapter()).run(Path(d) / "p", DEMO_QUESTION, execution_mode="REAL")
            self.assertEqual(res["current_stage"], "FAILED")
            self.assertEqual(len(res["claims"]), 0)
            self.assertNotIn("DATASETS_LOCKED", res["stage_history"])

    # 4. source_class inconsistent with provenance is rejected.
    def test_inconsistent_provenance_rejected(self):
        bad = {"source_class": "PUBLIC_DATABASE", "retrieval_mode": "LIVE", "verification_level": "METADATA_VERIFIED", "accession": "FIXTURE-X"}
        self.assertTrue(validate_provenance(bad))  # PUBLIC_DATABASE may not use a FIXTURE accession

    # 5. Legacy verified=true is not auto-promoted to a verification level.
    def test_legacy_verified_not_promoted(self):
        out = normalize_legacy_provenance({"verified": True})
        self.assertEqual(out["verification_level"], "UNVERIFIED")
        self.assertEqual(out["source_class"], "LEGACY_UNKNOWN")
        self.assertTrue(out["legacy_verified_assertion"])
        self.assertFalse(out["scientific_output_eligible"])

    # 6. DEMO reports and CLI output carry a visible watermark.
    def test_demo_watermark_everywhere(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["run", "--project", str(proj), "--question", DEMO_QUESTION])
            self.assertIn("DEMONSTRATION_ONLY", buf.getvalue())
            report = (proj / "state" / "reports" / "report.md").read_text()
            self.assertIn("DEMONSTRATION_ONLY", report)
            bundle_readme = (proj / "reproduction_bundle" / "README.md").read_text()
            self.assertIn("DEMONSTRATION_ONLY", bundle_readme)

    # 7. A Demo Claim exists but is not formally exportable.
    def test_demo_claim_not_formally_exportable(self):
        with tempfile.TemporaryDirectory() as d:
            res = Pipeline(resources=fixture_adapter()).run(Path(d) / "p", DEMO_QUESTION)
            self.assertEqual(len(res["claims"]), 1)  # demo claim kept for E2E value
            self.assertFalse(any(is_formally_exportable(c) for c in res["claims"]))

    # 8. ProjectPolicy vs ProjectState mode mismatch is refused.
    def test_policy_state_mismatch_refused(self):
        errors = validate_policy_state_consistency(_policy("REAL"), {"execution_mode": "DEMO", "project_policy_ref": "pp1"})
        self.assertTrue(errors)
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            state_path = proj / "state" / "project_state.json"
            state = json.loads(state_path.read_text())
            state["execution_mode"] = "REAL"  # tamper the projection
            state_path.write_text(json.dumps(state))
            with self.assertRaises(PipelineError):
                Pipeline(resources=fixture_adapter()).run(proj)


class EligibilityRuleTest(unittest.TestCase):
    def test_real_verified_public_data_is_eligible(self):
        decision = evaluate_scientific_eligibility(
            execution_mode="REAL", source_class="PUBLIC_DATABASE", retrieval_mode="LIVE",
            verification_level="FILES_CHECKSUM_VERIFIED", qc_status="pass",
            evaluated_input_refs=["a"], evaluated_input_hashes=["h"], policy_id="p", policy_version=1,
        )
        self.assertEqual(decision["decision"], "ELIGIBLE")
        self.assertEqual(decision["release_status"], "RESEARCH_PRELIMINARY")


if __name__ == "__main__":
    unittest.main()
