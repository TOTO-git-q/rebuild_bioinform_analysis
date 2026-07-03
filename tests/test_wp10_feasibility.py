"""WP-10 data feasibility + DatasetManifest lock tests (T-10-01..15)."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_dataset_feasibility_report
from auto_bioinfo.resources.feasibility import (
    ACCEPT,
    CONDITIONAL,
    DESIGN_BULK,
    DESIGN_SINGLE_CELL,
    FEASIBILITY_RULES,
    NEED_MORE_INFORMATION,
    REJECT,
    TERMINAL_INSUFFICIENT_DATA,
    TERMINAL_NEED_MORE_INFORMATION,
    LockedDatasetManifest,
    ManifestLockError,
    assess_feasibility,
    build_approval_package,
    build_coverage_matrix,
    build_dataset_manifest,
    build_sample_manifest,
    classify_design,
    decide_terminal_path,
    evaluate_rules,
    register_file_checksums,
    suitability_score,
    validate_dataset_manifest_lock,
    verify_file_checksums,
)

SPEC = {"research_spec_id": "rs_demo", "tissue": "liver"}
PLAN = {"evidence_plan_id": "evidence_plan_abc", "evidence_axes": ["transcriptomic_differential"], "minimum_replication": {"minimum_independent_sources": 2}}


def _bulk_profile(**overrides):
    profile = {
        "dataset_profile_id": "dataset_profile_demo",
        "dataset_id": "dataset_demo",
        "research_spec_id": "rs_demo",
        "source_status": "committed_fixture",
        "modality": "bulk RNA-seq",
        "organism": "human",
        "tissue": "liver",
        "platform": "GPL11154",
        "accession": "GSE111111",
        "source_class": "PUBLIC_DATABASE",
        "samples": [
            {"sample_id": "S1", "group": "tumor", "donor_id": "D1"},
            {"sample_id": "S2", "group": "tumor", "donor_id": "D2"},
            {"sample_id": "S3", "group": "normal", "donor_id": "D3"},
            {"sample_id": "S4", "group": "normal", "donor_id": "D4"},
        ],
        "grouping": {"tumor": ["S1", "S2"], "normal": ["S3", "S4"]},
        "files": [{"name": "counts.tsv", "file_type": "counts", "downloadable": True, "size_bytes": 2048}],
        "metadata_facts": {"parsed_fields": {"age": {}, "sex": {}}},
    }
    profile.update(overrides)
    return profile


class RuleRegistryTests(unittest.TestCase):
    def test_every_rule_has_id_version_severity_rationale(self):
        for rule in FEASIBILITY_RULES:
            self.assertTrue(rule.rule_id and rule.version and rule.rationale)
            self.assertIn(rule.severity, ("hard", "soft"))

    def test_rule_ids_unique(self):
        ids = [r.rule_id for r in FEASIBILITY_RULES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_classify_design(self):
        self.assertEqual(classify_design({"modality": "bulk RNA-seq"}), DESIGN_BULK)
        self.assertEqual(classify_design({"modality": "scRNA-seq"}), DESIGN_SINGLE_CELL)
        self.assertEqual(classify_design({"modality": "snRNA"}), DESIGN_SINGLE_CELL)


class FeasibilityVerdictTests(unittest.TestCase):
    def test_accept_when_all_hard_rules_pass(self):
        report = assess_feasibility(_bulk_profile(), SPEC, PLAN, subquestion_id="sq_1")
        self.assertEqual(report["decision"], ACCEPT)
        self.assertEqual(validate_dataset_feasibility_report(report), [])
        self.assertEqual(report["evidence_plan_id"], "evidence_plan_abc")

    def test_reject_when_single_group(self):
        prof = _bulk_profile(
            grouping={"tumor": ["S1", "S2", "S3", "S4"]}, samples=[{"sample_id": f"S{i}", "group": "tumor", "donor_id": f"D{i}"} for i in range(1, 5)]
        )
        report = assess_feasibility(prof, SPEC, PLAN, subquestion_id="sq_1")
        self.assertEqual(report["decision"], REJECT)
        self.assertTrue(report["blocking_gaps"])
        self.assertEqual(validate_dataset_feasibility_report(report), [])

    def test_reject_when_unknown_donor(self):
        prof = _bulk_profile(
            samples=[{"sample_id": "S1", "group": "tumor", "donor_id": "unknown"}, {"sample_id": "S2", "group": "normal", "donor_id": "unknown"}],
            grouping={"tumor": ["S1"], "normal": ["S2"]},
        )
        report = assess_feasibility(prof, SPEC, PLAN, subquestion_id="sq_1")
        self.assertEqual(report["decision"], REJECT)

    def test_conditional_on_soft_warning(self):
        prof = _bulk_profile(tissue="blood")  # tissue mismatch is soft
        report = assess_feasibility(prof, SPEC, PLAN, subquestion_id="sq_1")
        self.assertEqual(report["decision"], CONDITIONAL)
        self.assertTrue(report["conditional_use_notes"])
        self.assertTrue(report["preconditions"])
        self.assertEqual(validate_dataset_feasibility_report(report), [])

    def test_need_more_information_when_files_not_downloadable(self):
        prof = _bulk_profile(files=[{"name": "counts.tsv", "file_type": "counts", "downloadable": False}])
        report = assess_feasibility(prof, SPEC, PLAN, subquestion_id="sq_1")
        self.assertEqual(report["decision"], NEED_MORE_INFORMATION)
        self.assertTrue(report["missing_facts"])
        self.assertEqual(validate_dataset_feasibility_report(report), [])

    def test_need_more_information_when_no_evidence_plan(self):
        report = assess_feasibility(_bulk_profile(), SPEC, None, subquestion_id="sq_1")
        self.assertEqual(report["decision"], NEED_MORE_INFORMATION)

    def test_sc_missing_donor_hard_fails(self):
        prof = _bulk_profile(
            modality="scRNA-seq",
            samples=[{"sample_id": "S1", "group": "tumor", "donor_id": "unknown"}, {"sample_id": "S2", "group": "normal", "donor_id": "unknown"}],
            grouping={"tumor": ["S1"], "normal": ["S2"]},
        )
        report = assess_feasibility(prof, SPEC, PLAN, subquestion_id="sq_1")
        self.assertEqual(report["decision"], REJECT)
        findings = {f["rule_id"]: f for f in report["findings"]}
        self.assertEqual(findings["FEAS-SC-001"]["status"], "fail")

    def test_suitability_score_advisory_only(self):
        score = suitability_score(_bulk_profile(), PLAN)
        self.assertFalse(score["authoritative"])
        self.assertIn("met", score)

    def test_findings_recorded(self):
        findings = evaluate_rules(_bulk_profile(), SPEC)
        self.assertTrue(any(f.rule_id == "FEAS-GEN-001" for f in findings))


class CoverageTests(unittest.TestCase):
    def test_covered_and_gap(self):
        good = assess_feasibility(_bulk_profile(), SPEC, PLAN, subquestion_id="sq_1")
        cov = build_coverage_matrix(["sq_1", "sq_2"], [good])
        self.assertTrue(cov["matrix"]["sq_1"]["has_data_path"])
        self.assertFalse(cov["matrix"]["sq_2"]["has_data_path"])
        self.assertFalse(cov["all_covered"])
        self.assertEqual(cov["gaps"][0]["subquestion_id"], "sq_2")

    def test_conditional_only_flagged(self):
        cond = assess_feasibility(_bulk_profile(tissue="blood"), SPEC, PLAN, subquestion_id="sq_1")
        cov = build_coverage_matrix(["sq_1"], [cond])
        self.assertTrue(cov["matrix"]["sq_1"]["conditional_only"])


class ChecksumTests(unittest.TestCase):
    def test_register_and_verify_match(self):
        recorded = register_file_checksums({"counts.tsv": "col\n1\n"})
        self.assertEqual(verify_file_checksums(recorded, dict(recorded)), [])

    def test_mismatch_stops(self):
        recorded = register_file_checksums({"counts.tsv": "col\n1\n"})
        errors = verify_file_checksums(recorded, {"counts.tsv": "0" * 64})
        self.assertTrue(errors)

    def test_missing_file_flagged(self):
        recorded = register_file_checksums({"counts.tsv": "x"})
        self.assertTrue(verify_file_checksums(recorded, {}))


class SampleManifestTests(unittest.TestCase):
    def test_every_exclusion_needs_reason(self):
        prof = _bulk_profile()
        sm = build_sample_manifest(prof, exclusions={"S4": "failed QC"}, covariates=["age"])
        self.assertEqual(len(sm["included_samples"]), 3)
        self.assertEqual(sm["excluded_samples"][0]["reason"], "failed QC")

    def test_blank_exclusion_reason_raises(self):
        with self.assertRaises(ValueError):
            build_sample_manifest(_bulk_profile(), exclusions={"S4": ""})


class DatasetManifestLockTests(unittest.TestCase):
    def _manifest(self):
        prof = _bulk_profile()
        sm = build_sample_manifest(prof)
        checks = register_file_checksums({"counts.tsv": "col\n1\n"})
        return build_dataset_manifest(
            profile=prof, sample_manifest=sm, file_checksums=checks, supports_subquestion_ids=["sq_1"], known_limitations=["synthetic"]
        )

    def test_locked_manifest_valid(self):
        man = self._manifest()
        self.assertTrue(man["locked"])
        self.assertEqual(validate_dataset_manifest_lock(man), [])

    def test_manifest_missing_reference_rejected(self):
        prof = _bulk_profile()
        sm = build_sample_manifest(prof)
        checks = register_file_checksums({"counts.tsv": "x"})
        with self.assertRaises(ValueError):
            build_dataset_manifest(profile=prof, sample_manifest=sm, file_checksums=checks, supports_subquestion_ids=[])

    def test_no_checksums_rejected(self):
        prof = _bulk_profile()
        sm = build_sample_manifest(prof)
        with self.assertRaises(ValueError):
            build_dataset_manifest(profile=prof, sample_manifest=sm, file_checksums={}, supports_subquestion_ids=["sq_1"])

    def test_in_place_update_fails(self):
        locked = LockedDatasetManifest(self._manifest())
        with self.assertRaises(ManifestLockError):
            locked.update(samples=[])

    def test_supersede_creates_new_version(self):
        locked = LockedDatasetManifest(self._manifest())
        new = locked.supersede(reason="add sample", changes={"known_limitations": ["updated"]})
        self.assertEqual(new.version, 2)
        self.assertNotEqual(new.manifest["dataset_manifest_id"], locked.manifest["dataset_manifest_id"])
        self.assertEqual(new.manifest["supersede_reason"], "add sample")
        self.assertEqual(locked.version, 1)  # original untouched

    def test_supersede_requires_reason(self):
        locked = LockedDatasetManifest(self._manifest())
        with self.assertRaises(ValueError):
            locked.supersede(reason="")

    def test_approval_package_is_inert(self):
        man = self._manifest()
        report = assess_feasibility(_bulk_profile(), SPEC, PLAN, subquestion_id="sq_1")
        cov = build_coverage_matrix(["sq_1"], [report])
        pkg = build_approval_package(man, [report], cov)
        self.assertFalse(pkg["authoritative"])
        self.assertEqual(pkg["dataset_manifest_id"], man["dataset_manifest_id"])


class TerminalPathTests(unittest.TestCase):
    def test_no_terminal_when_covered(self):
        good = assess_feasibility(_bulk_profile(), SPEC, PLAN, subquestion_id="sq_1")
        cov = build_coverage_matrix(["sq_1"], [good])
        self.assertIsNone(decide_terminal_path(cov, [good]))

    def test_insufficient_data_when_all_rejected(self):
        prof = _bulk_profile(grouping={"tumor": ["S1", "S2", "S3", "S4"]})
        rej = assess_feasibility(prof, SPEC, PLAN, subquestion_id="sq_1")
        self.assertEqual(rej["decision"], REJECT)
        cov = build_coverage_matrix(["sq_1"], [rej])
        terminal = decide_terminal_path(cov, [rej])
        self.assertEqual(terminal["terminal_state"], TERMINAL_INSUFFICIENT_DATA)
        self.assertFalse(terminal["compiles_analysis"])

    def test_need_more_information_terminal(self):
        prof = _bulk_profile(files=[{"name": "counts.tsv", "file_type": "counts", "downloadable": False}])
        nmi = assess_feasibility(prof, SPEC, PLAN, subquestion_id="sq_1")
        cov = build_coverage_matrix(["sq_1"], [nmi])
        terminal = decide_terminal_path(cov, [nmi])
        self.assertEqual(terminal["terminal_state"], TERMINAL_NEED_MORE_INFORMATION)


if __name__ == "__main__":
    unittest.main()
