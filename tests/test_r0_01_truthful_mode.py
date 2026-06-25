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
    LEGACY_MIGRATION_MARKER,
    authoritative_release,
    classify_project_policy_state,
    decision_is_authoritatively_eligible,
    describe_dataset_origin,
    evaluate_scientific_eligibility,
    is_formally_exportable,
    migrate_legacy_project_policy,
    normalize_legacy_provenance,
    recompute_eligibility_for,
    validate_policy_state_consistency,
    validate_provenance,
    validate_real_mode_lock,
    verify_decision_integrity,
    verify_project_policy_integrity,
)
from auto_bioinfo.core.provenance import build_project_policy
from auto_bioinfo.interfaces.cli import main
from auto_bioinfo.pipeline import LegacyMigrationRequired, Pipeline, PipelineError
from auto_bioinfo.report import build_final_report
from auto_bioinfo.reproduction.bundle import (
    FormalExportRefused,
    build_reproduction_bundle,
    compute_project_release,
)
from tests._helpers import DEMO_QUESTION, fixture_adapter, real_like_fixture_adapter


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


class RealModeLockGateBypassTest(unittest.TestCase):
    """Gate 5 (R0-01 review-fix): a REAL run may only *lock* a dataset that is
    genuinely checksum-verified. Identifier/metadata-only verification, a
    RECORDED_REPLAY retrieval, an empty/tampered checksum set, or a missing
    file must all block the lock with a POLICY_FAILURE. The locked manifest
    must persist source_class/retrieval_mode/verification_level/file_checksums.
    Non-REAL locks are unaffected."""

    def _real_profile(self, **over):
        prof = {
            "dataset_id": "GSE_REAL",
            "source_class": "PUBLIC_DATABASE",
            "retrieval_mode": "LIVE",
            "verification_level": "FILES_CHECKSUM_VERIFIED",
        }
        prof.update(over)
        return prof

    def test_real_lock_requires_files_checksum_verified(self):
        prof = self._real_profile(verification_level="METADATA_VERIFIED")
        errs = validate_real_mode_lock(prof, "REAL", file_checksums={"counts": "abc"}, recomputed_checksums={"counts": "abc"})
        self.assertTrue(any("verification_level" in e for e in errs))

    def test_real_lock_rejects_recorded_replay(self):
        prof = self._real_profile(retrieval_mode="RECORDED_REPLAY")
        errs = validate_real_mode_lock(prof, "REAL", file_checksums={"counts": "abc"}, recomputed_checksums={"counts": "abc"})
        self.assertTrue(any("RECORDED_REPLAY" in e for e in errs))

    def test_real_lock_requires_nonempty_checksums(self):
        prof = self._real_profile()
        errs = validate_real_mode_lock(prof, "REAL", file_checksums={}, recomputed_checksums={})
        self.assertTrue(any("non-empty file_checksums" in e for e in errs))
        # also: a recorded entry whose digest is empty is rejected
        errs2 = validate_real_mode_lock(prof, "REAL", file_checksums={"counts": ""}, recomputed_checksums={"counts": ""})
        self.assertTrue(any("non-empty checksum" in e for e in errs2))

    def test_real_lock_detects_checksum_mismatch(self):
        prof = self._real_profile()
        errs = validate_real_mode_lock(prof, "REAL", file_checksums={"counts": "abc"}, recomputed_checksums={"counts": "DIFFERENT"})
        self.assertTrue(any("mismatch" in e for e in errs))

    def test_real_lock_detects_missing_or_extra_file(self):
        prof = self._real_profile()
        # recorded checksum has no materialized file to verify
        errs = validate_real_mode_lock(prof, "REAL", file_checksums={"counts": "abc"}, recomputed_checksums={})
        self.assertTrue(any("no materialized file" in e for e in errs))
        # an extra materialized file with no recorded checksum
        errs2 = validate_real_mode_lock(prof, "REAL", file_checksums={"counts": "abc"}, recomputed_checksums={"counts": "abc", "meta": "xyz"})
        self.assertTrue(any("no recorded checksum" in e for e in errs2))

    def test_genuine_real_lock_passes(self):
        prof = self._real_profile()
        errs = validate_real_mode_lock(prof, "REAL", file_checksums={"counts": "abc"}, recomputed_checksums={"counts": "abc"})
        self.assertEqual(errs, [])

    def test_demo_lock_unaffected_and_manifest_records_four_elements(self):
        # Non-REAL gate is a no-op even with a weak/empty profile.
        self.assertEqual(validate_real_mode_lock({"verification_level": "UNVERIFIED"}, "DEMO", file_checksums={}), [])
        # A real DEMO run still locks, and the manifest persists the four elements.
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            manifest = json.loads((proj / "state" / "objects" / "dataset_manifest.json").read_text())
            for field in ("source_class", "retrieval_mode", "verification_level", "file_checksums"):
                self.assertIn(field, manifest)
            self.assertTrue(manifest["file_checksums"])


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


class LegacyProjectGateBypassTest(unittest.TestCase):
    """Gate 6 (R0-01 review-fix): a project that predates the ProjectPolicy gets
    *explicit* behavior — a one-time conservative migration to DEMO, or a named
    MIGRATION_REQUIRED — never a bare PipelineError, and never auto-promoted to
    REAL."""

    def test_classify_current_when_policy_present(self):
        self.assertEqual(classify_project_policy_state({"execution_mode": "DEMO"}, {}), "CURRENT")

    def test_classify_legacy_migratable_when_no_policy_no_binding(self):
        self.assertEqual(classify_project_policy_state({}, {"project_id": "p"}), "LEGACY_MIGRATABLE")

    def test_classify_migration_required_when_ref_is_dangling(self):
        self.assertEqual(classify_project_policy_state({}, {"project_policy_ref": "pp_old"}), "MIGRATION_REQUIRED")

    def test_migrate_builds_demo_policy(self):
        policy = migrate_legacy_project_policy("legacy_proj")
        self.assertEqual(policy["execution_mode"], "DEMO")
        self.assertEqual(policy["project_id"], "legacy_proj")
        # The migrated policy is a normal immutable policy (passes integrity once bound).
        state = {"project_id": "legacy_proj", "execution_mode": "DEMO", "project_policy_ref": policy["project_policy_id"]}
        self.assertEqual(verify_project_policy_integrity(policy, state), [])

    def test_legacy_project_migrated_to_demo_without_raising(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            policy_path = proj / "state" / "objects" / "project_policy.json"
            state_path = proj / "state" / "project_state.json"
            # Simulate a pre-R0-01 project: no policy file, no policy binding, and
            # (worst case) the legacy state even claimed to be REAL.
            policy_path.unlink()
            state = json.loads(state_path.read_text())
            state["execution_mode"] = "REAL"
            state.pop("project_policy_ref", None)
            state_path.write_text(json.dumps(state))

            result = Pipeline(resources=fixture_adapter()).run(proj)

            # Migrated, not raised: a DEMO policy was recreated and bound.
            self.assertTrue(policy_path.exists())
            migrated_policy = json.loads(policy_path.read_text())
            self.assertEqual(migrated_policy["execution_mode"], "DEMO")
            migrated_state = json.loads(state_path.read_text())
            # Never promoted: the once-"REAL" legacy state is forced to DEMO.
            self.assertEqual(migrated_state["execution_mode"], "DEMO")
            self.assertTrue(migrated_state.get(LEGACY_MIGRATION_MARKER))
            self.assertEqual(migrated_state["project_policy_ref"], migrated_policy["project_policy_id"])
            # Output is demonstration-only and the integrity gate passes (no raise).
            self.assertEqual(result["release_status"], "DEMONSTRATION_ONLY")
            self.assertEqual(result["execution_mode"], "DEMO")
            # The migration is audited, never silent.
            self.assertIn("LEGACY_PROJECT_MIGRATED", (proj / "state" / "events.jsonl").read_text())

    def test_missing_policy_with_dangling_ref_requires_explicit_migration(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            policy_path = proj / "state" / "objects" / "project_policy.json"
            # The policy file is gone but the state still references it: a lost
            # binding must NOT be silently relabeled to DEMO.
            policy_path.unlink()
            with self.assertRaises(LegacyMigrationRequired) as ctx:
                Pipeline(resources=fixture_adapter()).run(proj)
            self.assertEqual(ctx.exception.reason, "MIGRATION_REQUIRED")
            # Not silently migrated: no policy was recreated.
            self.assertFalse(policy_path.exists())

    def test_migration_is_one_time_and_resumes_clean(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            policy_path = proj / "state" / "objects" / "project_policy.json"
            state_path = proj / "state" / "project_state.json"
            policy_path.unlink()
            state = json.loads(state_path.read_text())
            state.pop("project_policy_ref", None)
            state_path.write_text(json.dumps(state))

            Pipeline(resources=fixture_adapter()).run(proj)  # one-time migration
            first_policy = json.loads(policy_path.read_text())
            # The migrated project is now CURRENT, not migratable again.
            self.assertEqual(
                classify_project_policy_state(first_policy, json.loads(state_path.read_text())),
                "CURRENT",
            )
            result = Pipeline(resources=fixture_adapter()).run(proj)
            self.assertEqual(result["release_status"], "DEMONSTRATION_ONLY")
            # No re-migration churn: the policy id is stable across the resume.
            self.assertEqual(
                json.loads(policy_path.read_text())["project_policy_id"],
                first_policy["project_policy_id"],
            )


class EligibilityRuleTest(unittest.TestCase):
    def test_real_verified_public_data_is_eligible(self):
        decision = evaluate_scientific_eligibility(
            execution_mode="REAL", source_class="PUBLIC_DATABASE", retrieval_mode="LIVE",
            verification_level="FILES_CHECKSUM_VERIFIED", qc_status="pass",
            evaluated_input_refs=["a"], evaluated_input_hashes=["h"], policy_id="p", policy_version=1,
        )
        self.assertEqual(decision["decision"], "ELIGIBLE")
        self.assertEqual(decision["release_status"], "RESEARCH_PRELIMINARY")


class StructuredProvenanceConsistencyBypassTest(unittest.TestCase):
    """Gate 7 (R0-01 review-fix): ``validate_provenance`` must audit the
    structured provenance triple (source_class / retrieval_mode /
    verification_level) for internal consistency, instead of leaning on the
    accession-string prefix as a stand-in for a real provenance review."""

    def _ok(self, **over):
        cand = {
            "source_class": "PUBLIC_DATABASE",
            "retrieval_mode": "LIVE",
            "verification_level": "METADATA_VERIFIED",
            "accession": "GSE12345",
        }
        cand.update(over)
        return cand

    def test_genuine_combinations_pass(self):
        # A real public-DB candidate and a committed fixture are both coherent.
        self.assertEqual(validate_provenance(self._ok()), [])
        self.assertEqual(
            validate_provenance({
                "source_class": "SYNTHETIC_FIXTURE",
                "retrieval_mode": "LOCAL_CACHE",
                "verification_level": "FILES_CHECKSUM_VERIFIED",
                "accession": "FIXTURE-DEMO",
            }),
            [],
        )

    def test_fixture_cannot_be_fetched_live(self):
        # Structural: a committed fixture is never obtained by a live fetch,
        # and the accession here is honestly a FIXTURE one (no prefix trick).
        errs = validate_provenance({
            "source_class": "SYNTHETIC_FIXTURE",
            "retrieval_mode": "LIVE",
            "verification_level": "UNVERIFIED",
            "accession": "FIXTURE-DEMO",
        })
        self.assertTrue(any("inconsistent with source_class" in e for e in errs))

    def test_local_data_cannot_be_fetched_live(self):
        # On-disk local data has no live retrieval path — caught by structure,
        # not by any accession spelling (accession is a plausible local id).
        errs = validate_provenance({
            "source_class": "LOCAL_DATA",
            "retrieval_mode": "LIVE",
            "verification_level": "FILES_CHECKSUM_VERIFIED",
            "accession": "LOCAL-RUN-7",
        })
        self.assertTrue(any("inconsistent with source_class" in e for e in errs))

    def test_legacy_unknown_cannot_claim_verification(self):
        # Unknown provenance cannot honestly assert any verification level.
        errs = validate_provenance({
            "source_class": "LEGACY_UNKNOWN",
            "retrieval_mode": "LOCAL_CACHE",
            "verification_level": "FILES_CHECKSUM_VERIFIED",
            "accession": "OLD-DATASET",
        })
        self.assertTrue(any("cannot honestly claim verification_level" in e for e in errs))

    def test_recorded_replay_cannot_ground_checksum_verification(self):
        # A self-recorded replay verifies its own recording, not real files —
        # so it can never reach FILES_CHECKSUM_VERIFIED, whatever the source.
        errs = validate_provenance({
            "source_class": "PUBLIC_DATABASE",
            "retrieval_mode": "RECORDED_REPLAY",
            "verification_level": "FILES_CHECKSUM_VERIFIED",
            "accession": "GSE99999",
        })
        self.assertTrue(any("RECORDED_REPLAY" in e for e in errs))

    def test_consistency_holds_even_with_innocent_accession(self):
        # The decisive failure is structural: a PUBLIC_DATABASE claiming a
        # USER_UPLOAD-only retrieval path is rejected even though the accession
        # string looks like a perfectly real public accession.
        errs = validate_provenance({
            "source_class": "USER_UPLOAD",
            "retrieval_mode": "LIVE",
            "verification_level": "METADATA_VERIFIED",
            "accession": "GSE12345",  # innocent-looking, but irrelevant here
        })
        self.assertTrue(any("inconsistent with source_class" in e for e in errs))


class BundleReadmeSourceClassTest(unittest.TestCase):
    """Gate 8 (R0-01 review-fix): the reproduction-bundle README must describe
    its inputs from the *actual* ``source_class`` of the locked dataset.  A run
    backed by real data must never be described as a "committed fixture", and
    only a SYNTHETIC_FIXTURE may be."""

    def test_describe_each_source_class_is_honest(self):
        # Only the synthetic fixture is ever called a fixture; every real data
        # source and the unknown-provenance class avoid the word entirely.
        self.assertIn("fixture", describe_dataset_origin("SYNTHETIC_FIXTURE").lower())
        for sc in ("PUBLIC_DATABASE", "USER_UPLOAD", "LOCAL_DATA", "LEGACY_UNKNOWN"):
            text = describe_dataset_origin(sc)
            self.assertNotIn("fixture", text.lower(), f"{sc} must not be called a fixture")
            self.assertTrue(text.strip())

    def test_unknown_source_class_defaults_to_unknown_not_fixture(self):
        # A missing/garbage source_class is treated conservatively as unknown
        # provenance — never silently presented as a committed fixture.
        text = describe_dataset_origin("NOT_A_REAL_CLASS")
        self.assertNotIn("fixture", text.lower())
        self.assertIn("unknown", text.lower())

    def test_public_database_weaves_in_accession(self):
        text = describe_dataset_origin("PUBLIC_DATABASE", accession="GSE12345")
        self.assertIn("GSE12345", text)
        self.assertIn("public database", text.lower())

    def test_demo_bundle_readme_says_synthetic_fixture(self):
        # The demo main path is unchanged: its inputs really ARE a committed
        # fixture, so the README honestly says so (and keeps the demo watermark).
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            build_reproduction_bundle(proj)
            readme = (proj / "reproduction_bundle" / "README.md").read_text()
            self.assertIn("synthetic fixture", readme.lower())
            self.assertIn("DEMONSTRATION_ONLY", readme)

    def test_real_source_bundle_readme_is_not_a_fixture(self):
        # Critical: drive the README off the persisted manifest's source_class.
        # Re-label the locked dataset as real public-database data and rebuild —
        # the README must drop the "committed fixture" prose entirely and instead
        # describe a real source, proving the text tracks the actual source_class
        # rather than a hard-coded string.
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
            manifest_path = proj / "state" / "objects" / "dataset_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["source_class"] = "PUBLIC_DATABASE"
            manifest["accession"] = "GSE45678"
            manifest_path.write_text(json.dumps(manifest))
            build_reproduction_bundle(proj)
            readme = (proj / "reproduction_bundle" / "README.md").read_text()
            self.assertNotIn("fixture", readme.lower())
            self.assertIn("public database", readme.lower())
            self.assertIn("GSE45678", readme)


def _eligible_real_decision():
    """A genuinely-eligible decision whose policy binding matches ``_policy('REAL')``."""
    return evaluate_scientific_eligibility(
        execution_mode="REAL", source_class="PUBLIC_DATABASE", retrieval_mode="LIVE",
        verification_level="FILES_CHECKSUM_VERIFIED", qc_status="pass",
        evaluated_input_refs=["ev1"], evaluated_input_hashes=["h1"],
        policy_id="pp1", policy_version=1,
    )


def _rewrite_jsonl(path: Path, mutate) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for row in rows:
        mutate(row)
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")


class AuthoritativeGateUncachedBindingBypassTest(unittest.TestCase):
    """Blocker 1 (R0-01 review-fix): under an eligible/formal release EVERY Claim
    and EvidenceItem must reference the one authoritative ScientificEligibility
    decision — checked independently of the cached ``scientific_output_eligible``
    flag.  A missing or foreign decision id forces a DEMONSTRATION_ONLY release
    even when the cached flag is false/absent, and the check runs through the real
    downstream entry (``export --formal`` / ``compute_project_release``), not a
    helper in isolation."""

    def _run_eligible_real_project(self, d: str) -> Path:
        proj = Path(d) / "p"
        res = Pipeline(resources=real_like_fixture_adapter()).run(proj, DEMO_QUESTION, execution_mode="REAL")
        # Sanity: the genuine REAL run really is eligible before we tamper it.
        self.assertTrue(res["scientific_output_eligible"])
        self.assertEqual(res["release_status"], "RESEARCH_PRELIMINARY")
        return proj

    def test_formal_export_succeeds_for_genuine_eligible_real_project(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_eligible_real_project(d)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["export", "--project", str(proj), "--formal"])
            self.assertEqual(code, 0)
            self.assertIn("FORMAL export", buf.getvalue())

    def test_formal_export_refused_when_claim_missing_decision_id(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_eligible_real_project(d)
            _rewrite_jsonl(proj / "state" / "claims.jsonl", lambda r: r.pop("scientific_eligibility_decision_id", None))
            self.assertFalse(compute_project_release(proj)["scientific_output_eligible"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["export", "--project", str(proj), "--formal"])
            self.assertEqual(code, 1)
            self.assertIn("FORMAL EXPORT REFUSED", buf.getvalue())

    def test_formal_export_refused_when_evidence_missing_decision_id(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_eligible_real_project(d)
            _rewrite_jsonl(proj / "state" / "evidence_items.jsonl", lambda r: r.update({"scientific_eligibility_decision_id": ""}))
            self.assertFalse(compute_project_release(proj)["scientific_output_eligible"])
            with redirect_stdout(io.StringIO()):
                code = main(["export", "--project", str(proj), "--formal"])
            self.assertEqual(code, 1)

    def test_formal_export_refused_when_claim_references_foreign_decision(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_eligible_real_project(d)
            _rewrite_jsonl(proj / "state" / "claims.jsonl", lambda r: r.update({"scientific_eligibility_decision_id": "scientific_eligibility_decision_forged"}))
            release = compute_project_release(proj)
            self.assertFalse(release["scientific_output_eligible"])
            self.assertIn("OBJECT_REFERENCES_FOREIGN_DECISION", release["reasons"])
            with redirect_stdout(io.StringIO()):
                code = main(["export", "--project", str(proj), "--formal"])
            self.assertEqual(code, 1)

    def test_release_demotes_on_missing_binding_regardless_of_cached_flag(self):
        # The old short-circuit only checked binding when the cached flag was true.
        # Here the cached flag is FALSE and the decision id is absent — the release
        # must still demote (the flag is never trusted for authorisation).
        decision = _eligible_real_decision()
        unbound = {"scientific_output_eligible": False}  # no decision id at all
        release = authoritative_release(decision, policy=_policy("REAL"), evidence_items=[unbound])
        self.assertFalse(release["scientific_output_eligible"])
        self.assertEqual(release["release_status"], "DEMONSTRATION_ONLY")
        self.assertIn("OBJECT_MISSING_DECISION_ID", release["reasons"])


class DecisionIntegrityDownstreamRefusalTest(unittest.TestCase):
    """Blocker 2 (R0-01 review-fix): tampering the persisted ScientificEligibility
    decision's content, id, or evaluated_input_hashes must make the *real*
    downstream formal export refuse (non-zero exit, no artifact) — proven through
    ``export --formal``, not only at the helper layer."""

    def _run_eligible_real_project(self, d: str) -> Path:
        proj = Path(d) / "p"
        res = Pipeline(resources=real_like_fixture_adapter()).run(proj, DEMO_QUESTION, execution_mode="REAL")
        self.assertTrue(res["scientific_output_eligible"])
        return proj

    def _tamper_decision(self, proj: Path, mutate) -> None:
        path = proj / "state" / "objects" / "scientific_eligibility_decision.json"
        decision = json.loads(path.read_text())
        mutate(decision)
        path.write_text(json.dumps(decision))

    def _assert_formal_export_refused(self, proj: Path) -> None:
        self.assertFalse(compute_project_release(proj)["scientific_output_eligible"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["export", "--project", str(proj), "--formal"])
        self.assertEqual(code, 1)
        self.assertIn("FORMAL EXPORT REFUSED", buf.getvalue())

    def test_formal_export_nonzero_when_decision_content_tampered(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_eligible_real_project(d)
            # Flip a fact (source_class) without re-deriving the id — caught by the
            # decision-id recomputation in the downstream authoritative gate.
            self._tamper_decision(proj, lambda dec: dec.update({"source_class": "SYNTHETIC_FIXTURE"}))
            self._assert_formal_export_refused(proj)

    def test_formal_export_nonzero_when_decision_id_tampered(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_eligible_real_project(d)
            self._tamper_decision(proj, lambda dec: dec.update({"scientific_eligibility_decision_id": "scientific_eligibility_decision_deadbeef"}))
            self._assert_formal_export_refused(proj)

    def test_formal_export_refused_when_evaluated_input_hashes_tampered(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_eligible_real_project(d)
            self._tamper_decision(proj, lambda dec: dec.update({"evaluated_input_hashes": ["forged_hash"]}))
            self._assert_formal_export_refused(proj)


class LockedManifestResumeChecksumGateTest(unittest.TestCase):
    """Blocker 3 (R0-01 review-fix): once a dataset is locked, a resume must
    re-verify the DatasetManifest before compile/execution.  Emptying or altering
    a checksum, deleting a materialized file, or adding an unexpected extra file
    must make ``Pipeline.run()`` (resume) fail — for every execution mode — rather
    than continue to COMPLETED off an unverified manifest."""

    _MANIFEST = ("state", "objects", "dataset_manifest.json")

    def _run_demo(self, d: str) -> Path:
        proj = Path(d) / "p"
        Pipeline(resources=fixture_adapter()).run(proj, DEMO_QUESTION)
        return proj

    def _edit_manifest(self, proj: Path, mutate) -> None:
        path = proj.joinpath(*self._MANIFEST)
        manifest = json.loads(path.read_text())
        mutate(manifest)
        path.write_text(json.dumps(manifest))

    def test_untampered_resume_still_completes(self):
        # Regression: a clean NON-REAL (DEMO) resume must still pass the new gate,
        # because a legitimately-locked DEMO manifest always carries non-empty
        # checksums (see _lock_datasets / test_demo_lock_unaffected...).
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_demo(d)
            res = Pipeline(resources=fixture_adapter()).run(proj)  # resume, no tamper
            self.assertEqual(res["current_stage"], "COMPLETED")

    def test_resume_fails_when_manifest_checksums_emptied(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_demo(d)
            self._edit_manifest(proj, lambda m: m.update({"file_checksums": {}}))
            with self.assertRaises(PipelineError):
                Pipeline(resources=fixture_adapter()).run(proj)

    def test_resume_fails_when_a_checksum_is_tampered(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_demo(d)

            def _bend(m):
                name = next(iter(m["file_checksums"]))
                m["file_checksums"][name] = "0" * 64

            self._edit_manifest(proj, _bend)
            with self.assertRaises(PipelineError):
                Pipeline(resources=fixture_adapter()).run(proj)

    def test_resume_fails_when_materialized_file_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_demo(d)
            manifest = json.loads(proj.joinpath(*self._MANIFEST).read_text())
            rel = next(iter(manifest["materialized_files"].values()))
            (proj / rel).unlink()
            with self.assertRaises(PipelineError):
                Pipeline(resources=fixture_adapter()).run(proj)

    def test_resume_rejects_unexpected_extra_file(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._run_demo(d)
            extra_rel = "state/inputs/_unexpected_extra.tsv"
            (proj / extra_rel).parent.mkdir(parents=True, exist_ok=True)
            (proj / extra_rel).write_text("gene\tvalue\nX\t1\n", encoding="utf-8")
            # Register it as materialized but leave it OUT of file_checksums.
            self._edit_manifest(proj, lambda m: m["materialized_files"].update({"extra": extra_rel}))
            with self.assertRaises(PipelineError):
                Pipeline(resources=fixture_adapter()).run(proj)

    def test_real_project_resume_revalidates_locked_manifest(self):
        # REAL is the critical case: a genuine eligible REAL project, once locked,
        # must re-verify its manifest on resume and refuse a tampered checksum.
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "p"
            res = Pipeline(resources=real_like_fixture_adapter()).run(proj, DEMO_QUESTION, execution_mode="REAL")
            self.assertTrue(res["scientific_output_eligible"])

            def _bend(m):
                name = next(iter(m["file_checksums"]))
                m["file_checksums"][name] = "f" * 64

            self._edit_manifest(proj, _bend)
            with self.assertRaises(PipelineError):
                Pipeline(resources=real_like_fixture_adapter()).run(proj)


if __name__ == "__main__":
    unittest.main()
