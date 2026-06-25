import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from auto_bioinfo.evidence.synthesis import synthesize_claims
from auto_bioinfo.core.provenance import evaluate_scientific_eligibility
from auto_bioinfo.interfaces.cli import main
from tests._helpers import DEMO_QUESTION


def _demo_decision():
    return evaluate_scientific_eligibility(
        execution_mode="DEMO", source_class="SYNTHETIC_FIXTURE", retrieval_mode="LOCAL_CACHE",
        verification_level="FILES_CHECKSUM_VERIFIED", qc_status="pass",
        evaluated_input_refs=["a"], evaluated_input_hashes=["h"], policy_id="p", policy_version=1,
    )


class ClaimCeilingTest(unittest.TestCase):
    def _evidence(self, allowed):
        return {
            "evidence_item_id": "ev1",
            "allowed_claim_level": allowed,
            "subquestion_ids": ["sq1"],
            "effect_summary": {"n_significant": 2, "top_significant_genes": ["G1", "G2"]},
            "limitations": ["RNA only"],
        }

    def test_synthesized_claim_respects_ceiling(self):
        claims = synthesize_claims(evidence_items=[self._evidence("association")], research_spec={}, scope_bundle={}, project_ceiling="association", eligibility_decision=_demo_decision())
        self.assertEqual(claims[0]["claim_level"], "association")

    def test_ceiling_clamps_below_method_capability(self):
        # even if evidence allows more, the project ceiling wins
        claims = synthesize_claims(evidence_items=[self._evidence("causal_support")], research_spec={}, scope_bundle={}, project_ceiling="association", eligibility_decision=_demo_decision())
        self.assertEqual(claims[0]["claim_level"], "association")

    def test_null_result_is_represented(self):
        ev = self._evidence("association")
        ev["effect_summary"]["n_significant"] = 0
        claims = synthesize_claims(evidence_items=[ev], research_spec={}, scope_bundle={}, project_ceiling="association", eligibility_decision=_demo_decision())
        self.assertEqual(claims[0]["status"], "null_result")

    def test_demo_claim_is_never_eligible(self):
        claims = synthesize_claims(evidence_items=[self._evidence("association")], research_spec={}, scope_bundle={}, project_ceiling="association", eligibility_decision=_demo_decision())
        self.assertFalse(claims[0]["scientific_output_eligible"])
        self.assertEqual(claims[0]["release_status"], "DEMONSTRATION_ONLY")


class CliTest(unittest.TestCase):
    def test_run_then_validate(self):
        with tempfile.TemporaryDirectory() as d:
            proj = str(Path(d) / "proj")
            rc = main(["run", "--project", proj, "--question", DEMO_QUESTION])
            self.assertEqual(rc, 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["validate", "--project", proj])
            self.assertEqual(rc, 0)
            self.assertIn("BITWISE_IDENTICAL", buf.getvalue())

    def test_inspect_json(self):
        with tempfile.TemporaryDirectory() as d:
            proj = str(Path(d) / "proj")
            main(["run", "--project", proj, "--question", DEMO_QUESTION])
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["inspect", "--project", proj, "--json"])
            self.assertIn("COMPLETED", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
