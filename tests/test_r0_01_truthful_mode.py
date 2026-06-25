"""Work Order R0-01 bypass tests: a test fixture can never be passed off as a
real scientific result.  These are the eight adversarial cases the frozen R0-01
baseline requires."""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from auto_bioinfo.core.provenance import (
    authoritative_release,
    decision_is_authoritatively_eligible,
    evaluate_scientific_eligibility,
    is_formally_exportable,
    normalize_legacy_provenance,
    recompute_eligibility_for,
    validate_policy_state_consistency,
    validate_provenance,
    verify_decision_integrity,
    verify_project_policy_integrity,
)
from auto_bioinfo.core.provenance import build_project_policy
from auto_bioinfo.interfaces.cli import main
from auto_bioinfo.pipeline import Pipeline, PipelineError
from auto_bioinfo.report import build_final_report
from auto_bioinfo.reproduction.bundle import (
    FormalExportRefused,
    build_reproduction_bundle,
    compute_project_release,
)
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


class DecisionIntegrityBypassTest(unittest.TestCase):
    """Gate 2 (R0-01 review-fix): tampering a ScientificEligibilityDecision's
    content or id must make formal output refuse it."""

    def _eligible_decision(self):
        return evaluate_scientific_eligibility(
            execution_mode="REAL", source_class="PUBLIC_DATABASE", retrieval_mode="LIVE",
            verification_level="FILES_CHECKSUM_VERIFIED", qc_status="pass",
            evaluated_input_refs=["ev1"], evaluated_input_hashes=["h1"],
            policy_id="pp1", policy_version=1,
        )

    def test_untampered_decision_passes_integrity(self):
        d = self._eligible_decision()
        self.assertEqual(verify_decision_integrity(d, policy=_policy("REAL")), [])
        self.assertTrue(decision_is_authoritatively_eligible(d, policy=_policy("REAL")))

    def test_flipped_verdict_is_rejected(self):
        # Facts say INELIGIBLE (DEMO/fixture); attacker flips only the verdict +
        # release_status, leaving the id (a hash of the *facts*) unchanged.
        d = evaluate_scientific_eligibility(
            execution_mode="DEMO", source_class="SYNTHETIC_FIXTURE", retrieval_mode="LOCAL_CACHE",
            verification_level="UNVERIFIED", qc_status="pass",
            evaluated_input_refs=["ev1"], evaluated_input_hashes=[], policy_id="pp1", policy_version=1,
        )
        d["decision"] = "ELIGIBLE"
        d["release_status"] = "RESEARCH_PRELIMINARY"
        errors = verify_decision_integrity(d)
        self.assertTrue(any("verdict" in e for e in errors))
        self.assertFalse(decision_is_authoritatively_eligible(d))

    def test_tampered_fact_breaks_decision_id(self):
        # Editing a fact without recomputing the id is caught by the id mismatch.
        d = self._eligible_decision()
        d["source_class"] = "SYNTHETIC_FIXTURE"
        errors = verify_decision_integrity(d)
        self.assertTrue(any("does not match recomputed id" in e for e in errors))
        self.assertFalse(decision_is_authoritatively_eligible(d))

    def test_tampered_decision_id_is_rejected(self):
        d = self._eligible_decision()
        d["scientific_eligibility_decision_id"] = "scientific_eligibility_decision_deadbeefdeadbeef"
        self.assertTrue(verify_decision_integrity(d))
        self.assertFalse(decision_is_authoritatively_eligible(d))

    def test_policy_binding_mismatch_is_rejected(self):
        d = self._eligible_decision()
        # active policy is a different object than the one bound into the decision
        errors = verify_decision_integrity(d, policy={"project_policy_id": "pp2", "policy_version": 2})
        self.assertTrue(any("policy_id" in e for e in errors))
        self.assertFalse(decision_is_authoritatively_eligible(d, policy={"project_policy_id": "pp2", "policy_version": 2}))

    def test_wrong_back_reference_is_rejected(self):
        d = self._eligible_decision()
        errors = verify_decision_integrity(d, referencing_decision_id="some_other_decision_id")
        self.assertTrue(any("references decision" in e for e in errors))


class AuthoritativeEligibilityGateBypassTest(unittest.TestCase):
    """Gate 1 (R0-01 review-fix): inspect / report / bundle / CLI all release
    through the *same* authoritative gate, which recomputes eligibility from the
    persisted ScientificEligibilityDecision + active ProjectPolicy.  The cached
    ``scientific_output_eligible`` flag on a Claim/EvidenceItem is a display cache
    only and can never authorise a formal release."""

    @staticmethod
    def _set_flag_true(path: Path) -> None:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for row in rows:
            row["scientific_output_eligible"] = True
            row["release_status"] = "RESEARCH_PRELIMINARY"
        path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")

    def test_tampered_claim_flag_does_not_release_inspect_report_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            res = Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            self.assertEqual(len(res["claims"]), 1)
            # Attacker flips the cached eligibility flag on every Claim + EvidenceItem.
            self._set_flag_true(proj / "state" / "claims.jsonl")
            self._set_flag_true(proj / "state" / "evidence_items.jsonl")

            # inspect — still demonstration-only.
            summary = Pipeline(resources=fixture_adapter()).inspect(proj)
            self.assertFalse(summary["scientific_output_eligible"])
            self.assertEqual(summary["release_status"], "DEMONSTRATION_ONLY")

            # report — still demonstration-only, watermark intact.
            report = build_final_report(proj)
            self.assertFalse(report["scientific_output_eligible"])
            self.assertEqual(report["release_status"], "DEMONSTRATION_ONLY")
            self.assertIn("DEMONSTRATION_ONLY", (proj / "state" / "reports" / "report.md").read_text())

            # bundle — still demonstration-only, banner intact.
            manifest = build_reproduction_bundle(proj)
            self.assertFalse(manifest["scientific_output_eligible"])
            self.assertEqual(manifest["release_status"], "DEMONSTRATION_ONLY")
            self.assertIn("DEMONSTRATION_ONLY", (proj / "reproduction_bundle" / "README.md").read_text())

    def test_no_persisted_decision_is_demonstration_only(self):
        release = authoritative_release({}, policy=_policy("REAL"))
        self.assertFalse(release["scientific_output_eligible"])
        self.assertEqual(release["release_status"], "DEMONSTRATION_ONLY")
        self.assertIn("NO_ELIGIBILITY_DECISION", release["reasons"])

    def test_claim_referencing_foreign_decision_forces_demo(self):
        # A genuinely-eligible decision, but a Claim claims eligibility while
        # pointing at a *different* decision id — the gate refuses the release.
        decision = evaluate_scientific_eligibility(
            execution_mode="REAL", source_class="PUBLIC_DATABASE", retrieval_mode="LIVE",
            verification_level="FILES_CHECKSUM_VERIFIED", qc_status="pass",
            evaluated_input_refs=["ev1"], evaluated_input_hashes=["h1"],
            policy_id="pp1", policy_version=1,
        )
        foreign_claim = {"scientific_output_eligible": True, "scientific_eligibility_decision_id": "some_other_decision"}
        release = authoritative_release(decision, policy=_policy("REAL"), claims=[foreign_claim])
        self.assertFalse(release["scientific_output_eligible"])
        self.assertEqual(release["release_status"], "DEMONSTRATION_ONLY")
        self.assertIn("OBJECT_REFERENCES_FOREIGN_DECISION", release["reasons"])

    def test_authoritative_release_passes_for_genuine_eligible_decision(self):
        decision = evaluate_scientific_eligibility(
            execution_mode="REAL", source_class="PUBLIC_DATABASE", retrieval_mode="LIVE",
            verification_level="FILES_CHECKSUM_VERIFIED", qc_status="pass",
            evaluated_input_refs=["ev1"], evaluated_input_hashes=["h1"],
            policy_id="pp1", policy_version=1,
        )
        good_claim = {"scientific_output_eligible": True, "scientific_eligibility_decision_id": decision["scientific_eligibility_decision_id"]}
        release = authoritative_release(decision, policy=_policy("REAL"), claims=[good_claim])
        self.assertTrue(release["scientific_output_eligible"])
        self.assertEqual(release["release_status"], "RESEARCH_PRELIMINARY")
        self.assertEqual(release["reasons"], [])


class FormalExportGateBypassTest(unittest.TestCase):
    """Gate 4 (R0-01 review-fix): ``export --formal`` is the formal-output door.
    For a DEMONSTRATION_ONLY project it must refuse with a non-zero exit and
    produce *no* formal export artifact — not merely print a warning and succeed.
    A plain ``export`` still emits the watermarked demonstration bundle."""

    def test_formal_export_refused_for_demo_returns_nonzero_and_no_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            # Remove the demonstration bundle the run already wrote, so any
            # artifact present afterwards could only come from the formal export.
            shutil.rmtree(proj / "reproduction_bundle")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["export", "--project", str(proj), "--formal"])
            # Non-zero exit, explicit refusal, and NO bundle artifact written.
            self.assertEqual(code, 1)
            self.assertIn("FORMAL EXPORT REFUSED", buf.getvalue())
            self.assertFalse((proj / "reproduction_bundle").exists())

    def test_build_formal_bundle_raises_before_writing_for_demo(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            shutil.rmtree(proj / "reproduction_bundle")
            with self.assertRaises(FormalExportRefused):
                build_reproduction_bundle(proj, formal=True)
            # The guard fires before any directory is recreated.
            self.assertFalse((proj / "reproduction_bundle").exists())
            self.assertFalse(compute_project_release(proj)["scientific_output_eligible"])

    def test_plain_export_still_emits_demonstration_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["export", "--project", str(proj)])
            self.assertEqual(code, 0)
            self.assertIn("DEMONSTRATION_ONLY", buf.getvalue())
            manifest = build_reproduction_bundle(proj)
            self.assertEqual(manifest["export_type"], "DEMONSTRATION")
            self.assertFalse(manifest["scientific_output_eligible"])


class ProjectPolicyIntegrityBypassTest(unittest.TestCase):
    """Gate 3 (R0-01 review-fix): the ProjectPolicy is immutable. Editing it —
    even with ProjectState edited to match — must be detected by hash/id
    recomputation."""

    def _genuine(self, mode="DEMO"):
        policy = build_project_policy("proj1", mode)
        state = {"project_id": "proj1", "execution_mode": mode, "project_policy_ref": policy["project_policy_id"]}
        return policy, state

    def test_untampered_policy_passes_integrity(self):
        policy, state = self._genuine("DEMO")
        self.assertEqual(verify_project_policy_integrity(policy, state), [])

    def test_tampered_execution_mode_breaks_hash_and_id(self):
        # Flip DEMO->REAL in the policy only, leaving its hash/id stale.
        policy, state = self._genuine("DEMO")
        policy["execution_mode"] = "REAL"
        errors = verify_project_policy_integrity(policy, state)
        self.assertTrue(any("content_hash" in e for e in errors))
        self.assertTrue(any("project_policy_id" in e for e in errors))

    def test_both_policy_and_state_tampered_still_detected(self):
        # Attacker flips the mode in BOTH files (and re-points the ref to the
        # unchanged id) but cannot re-derive the policy's hash/id -> detected.
        policy, state = self._genuine("DEMO")
        policy["execution_mode"] = "REAL"
        state["execution_mode"] = "REAL"  # state now agrees with the tampered policy
        state["project_policy_ref"] = policy["project_policy_id"]
        errors = verify_project_policy_integrity(policy, state)
        self.assertTrue(errors)
        self.assertTrue(any("content_hash" in e or "project_policy_id" in e for e in errors))

    def test_missing_policy_ref_is_rejected(self):
        policy, state = self._genuine("DEMO")
        state["project_policy_ref"] = ""
        errors = verify_project_policy_integrity(policy, state)
        self.assertTrue(any("project_policy_ref is missing" in e for e in errors))

    def test_project_id_mismatch_is_rejected(self):
        policy, state = self._genuine("DEMO")
        state["project_id"] = "other_project"
        errors = verify_project_policy_integrity(policy, state)
        self.assertTrue(any("project_id" in e for e in errors))

    def test_pipeline_rejects_tampered_policy_on_resume(self):
        # End-to-end: tamper the persisted ProjectPolicy + ProjectState together;
        # resume must refuse with a PipelineError rather than run as REAL.
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            policy_path = proj / "state" / "objects" / "project_policy.json"
            state_path = proj / "state" / "project_state.json"
            policy = json.loads(policy_path.read_text())
            state = json.loads(state_path.read_text())
            policy["execution_mode"] = "REAL"
            state["execution_mode"] = "REAL"
            policy_path.write_text(json.dumps(policy))
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
