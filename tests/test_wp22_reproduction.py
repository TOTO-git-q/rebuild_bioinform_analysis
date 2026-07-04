"""WP-22: reproduction bundle export, verification, and clean-rerun comparison.

Validation slice locking the already-merged ``auto_bioinfo.reproduction`` package
(``repro_bundle`` / ``clean_rerun``) against the requirement-spec stage-18 contract:
in-memory bundle construction with a fixed directory layout, a ``checksums.sha256``
over every file, deterministic checksums and bundle IDs, a per-artifact ComparisonSpec
covering the bounded strategies, sensitive-information scanning (absolute paths,
secrets, internal URIs, emails) with formal-export refusal, manifest assembly that
validates through ``validate_reproduction_bundle_manifest``, tamper detection on
verification, supersede semantics that never mutate the prior bundle, a clean isolated
re-run that reproduces outputs bitwise, the seven bounded comparison levels with
numeric/set/direction/claim/not-comparable classification, and five bounded failure
classes.  These tests never mutate production implementation; they exercise the merged
builders against fixtures shaped exactly as the builders expect and assert their
fail-closed behaviour.
"""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_reproduction_bundle_manifest
from auto_bioinfo.reproduction.clean_rerun import (
    COMPARISON_LEVELS,
    FAILURE_CLASSES,
    classify_failure,
    compare_results,
    render_deg_tsv,
    run_clean_rerun,
)
from auto_bioinfo.reproduction.repro_bundle import (
    BUNDLE_STATUSES,
    COMPARISON_STRATEGIES,
    SENSITIVE_SCAN_KINDS,
    BundleBuildResult,
    SensitiveExportRefused,
    build_bundle,
    scan_sensitive,
    supersede_bundle,
    verify_bundle,
)

_DEG_ROWS = [
    {"gene": "BRCA1", "log2_fold_change": 2.4, "fdr": 0.001, "significant": True},
    {"gene": "TP53", "log2_fold_change": -1.8, "fdr": 0.004, "significant": True},
    {"gene": "ACTB", "log2_fold_change": 0.05, "fdr": 0.72, "significant": False},
]


def _clean_objects() -> dict:
    """A minimal but complete, sensitive-info-free set of exportable objects."""
    return {
        "research_spec": {"research_spec_id": "spec_wp22", "research_question": "tumor vs normal?"},
        "scope_bundle": {"species": ["human"], "tissues": ["liver"]},
        "subquestions": [{"subquestion_id": "subq_1", "claim_ceiling": "association"}],
        "evidence_plan": {"evidence_plan_id": "ep_wp22"},
        "dataset_manifest": {"dataset_manifest_id": "dm_wp22", "accession": "GSE00000"},
        "workflow_plan": {"workflow_plan_id": "wf_wp22"},
        "task_packets": [{"task_id": "t1"}],
        "parameters": {"fdr_threshold": 0.05},
        "environment": {"python": "3.11", "numpy": "1.26"},
        "qc_rules": [{"qc_report_id": "qc_1", "passed": True}],
        "known_limitations": ["demonstration run only"],
        "original_run_summary": {"method_id": "deseq2_demo", "n_significant": 2},
        "trace_index": {"complete": True},
        "claims": [{"claim_id": "c1", "claim_level": "association", "gene": "BRCA1"}],
        "input_files": {"counts.tsv": "gene\tsample1\tsample2\nBRCA1\t10\t40\n"},
        "output_files": {"deg_results.tsv": render_deg_tsv(_DEG_ROWS)},
        "license": "CC-BY-4.0",
        "receipt_restrictions": ["no_redistribution"],
    }


def _sensitive_objects() -> dict:
    """Exportable objects whose input file leaks an absolute path, a secret and a URI."""
    objects = _clean_objects()
    objects["input_files"] = {
        "leak.txt": (
            "source: /home/analyst/private/patient_counts.tsv\n"
            "api_key = AKIAIOSFODNN7EXAMPLE\n"
            "backend: http://localhost:8000/results\n"
        )
    }
    return objects


class BuildReproductionBundleTests(unittest.TestCase):
    def test_bundle_contains_required_files_inputs_outputs_spec_run_order_and_manifest(self):
        result = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        self.assertIsInstance(result, BundleBuildResult)
        self.assertEqual(result.status, "valid")
        self.assertIn(result.status, BUNDLE_STATUSES)
        self.assertTrue(result.clean)
        for required in (
            "research_spec.json",
            "workflow_plan.json",
            "parameters.json",
            "environment.json",
            "comparison_spec.json",
            "run_order.md",
            "checksums.sha256",
            "inputs/counts.tsv",
            "outputs/deg_results.tsv",
        ):
            self.assertIn(required, result.files)
        self.assertIn("Reproduction run order", result.run_order_md)

    def test_checksum_manifest_covers_every_file_except_the_checksums_file(self):
        result = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        expected = {path for path in result.files if path != "checksums.sha256"}
        self.assertEqual(set(result.checksums), expected)
        self.assertNotIn("checksums.sha256", result.checksums)

    def test_manifest_validates_and_records_license_and_checksums(self):
        result = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        self.assertEqual(validate_reproduction_bundle_manifest(result.manifest), [])
        self.assertEqual(result.manifest["license"], "CC-BY-4.0")
        self.assertEqual(result.manifest["checksums_sha256"], result.checksums)
        self.assertTrue(result.manifest["sensitive_scan_clean"])
        self.assertTrue(result.manifest["bundle_id"])

    def test_repeated_builds_are_deterministic_in_checksums_and_bundle_ids(self):
        first = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        second = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        self.assertEqual(first.checksums, second.checksums)
        self.assertEqual(first.files, second.files)
        self.assertEqual(first.manifest["bundle_id"], second.manifest["bundle_id"])


class ComparisonSpecTests(unittest.TestCase):
    def test_comparison_spec_declares_bounded_strategies_and_covers_outputs(self):
        result = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        spec = result.comparison_spec
        self.assertEqual(tuple(spec["strategies"]), COMPARISON_STRATEGIES)
        used = {rule["strategy"] for rule in spec["rules"]}
        self.assertTrue(used.issubset(set(COMPARISON_STRATEGIES)))
        # Every rule targets a declared expected output and the primary is bitwise.
        primary_rule = next(rule for rule in spec["rules"] if rule["target"] == spec["primary_output"])
        self.assertEqual(primary_rule["strategy"], "bitwise")
        self.assertEqual(primary_rule["tolerance"], 0.0)


class SensitiveExportScanTests(unittest.TestCase):
    def test_scan_detects_absolute_path_secret_and_internal_uri(self):
        findings = scan_sensitive({"leak.txt": _sensitive_objects()["input_files"]["leak.txt"]})
        kinds = {finding["kind"] for finding in findings}
        self.assertIn("absolute_path", kinds)
        self.assertIn("secret", kinds)
        self.assertIn("internal_uri", kinds)
        self.assertTrue(kinds.issubset(set(SENSITIVE_SCAN_KINDS)))

    def test_clean_bundle_scan_is_empty(self):
        self.assertEqual(scan_sensitive({"ok.txt": "gene\tsample\nBRCA1\t10\n"}), [])

    def test_formal_export_refuses_sensitive_content(self):
        with self.assertRaises(SensitiveExportRefused) as caught:
            build_bundle(project_id="proj_wp22", objects=_sensitive_objects(), formal=True)
        self.assertTrue(caught.exception.findings)

    def test_non_formal_build_records_findings_and_marks_invalid_without_raising(self):
        result = build_bundle(project_id="proj_wp22", objects=_sensitive_objects(), formal=False)
        self.assertEqual(result.status, "invalid")
        self.assertFalse(result.clean)
        self.assertTrue(result.sensitive_findings)
        self.assertFalse(result.manifest["sensitive_scan_clean"])


class VerifyBundleTests(unittest.TestCase):
    def test_clean_bundle_verifies_valid(self):
        result = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        report = verify_bundle(result.files, result.checksums)
        self.assertEqual(report["overall"], "VALID")
        self.assertTrue(report["valid"])
        self.assertEqual(report["files_checked"], len(result.checksums))

    def test_tampered_file_is_detected_as_invalid(self):
        result = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        tampered = dict(result.files)
        tampered["outputs/deg_results.tsv"] = tampered["outputs/deg_results.tsv"] + "TAMPER\n"
        report = verify_bundle(tampered, result.checksums)
        self.assertEqual(report["overall"], "INVALID")
        self.assertFalse(report["valid"])
        statuses = {row["path"]: row["status"] for row in report["results"]}
        self.assertEqual(statuses["outputs/deg_results.tsv"], "mismatch")

    def test_missing_file_is_detected_as_invalid(self):
        result = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        missing = {path: content for path, content in result.files.items() if path != "outputs/deg_results.tsv"}
        report = verify_bundle(missing, result.checksums)
        self.assertFalse(report["valid"])
        statuses = {row["path"]: row["status"] for row in report["results"]}
        self.assertEqual(statuses["outputs/deg_results.tsv"], "missing")


class SupersedeBundleTests(unittest.TestCase):
    def test_supersede_increments_version_links_previous_and_does_not_mutate_old(self):
        original = build_bundle(project_id="proj_wp22", objects=_clean_objects())
        original_manifest_snapshot = dict(original.manifest)
        successor = supersede_bundle(original.manifest, project_id="proj_wp22", objects=_clean_objects())
        self.assertEqual(successor.manifest["bundle_version"], original.manifest["bundle_version"] + 1)
        self.assertEqual(successor.manifest["supersedes_bundle_id"], original.manifest["bundle_id"])
        # The prior bundle is untouched and still verifies.
        self.assertEqual(original.manifest, original_manifest_snapshot)
        self.assertEqual(validate_reproduction_bundle_manifest(successor.manifest), [])


class CleanRerunTests(unittest.TestCase):
    def test_rerun_uses_isolated_workdir_and_reproduces_outputs_bitwise(self):
        task_records = [{"task_id": "t1", "output_name": "deg_results.tsv", "rows": _DEG_ROWS}]
        rerun = run_clean_rerun(task_records, workdir_label="orig_workdir")
        self.assertIn("isolated", rerun["workdir"])
        self.assertNotEqual(rerun["workdir"], "orig_workdir")
        self.assertEqual(rerun["reproduced_outputs"]["deg_results.tsv"], render_deg_tsv(_DEG_ROWS))
        self.assertEqual(rerun["task_run_ids"], ["rerun::t1"])

    def test_rerun_matches_the_bundled_output(self):
        objects = _clean_objects()
        bundle = build_bundle(project_id="proj_wp22", objects=objects)
        rerun = run_clean_rerun([{"task_id": "t1", "output_name": "deg_results.tsv", "rows": _DEG_ROWS}])
        self.assertEqual(
            rerun["reproduced_outputs"]["deg_results.tsv"],
            bundle.files["outputs/deg_results.tsv"],
        )


class ComparisonLevelsTests(unittest.TestCase):
    def test_exactly_seven_bounded_comparison_levels(self):
        self.assertEqual(len(COMPARISON_LEVELS), 7)
        self.assertEqual(
            set(COMPARISON_LEVELS),
            {
                "BITWISE_IDENTICAL",
                "NUMERICALLY_EQUIVALENT_WITHIN_TOLERANCE",
                "SAME_CANDIDATE_SET",
                "SAME_DIRECTION",
                "SAME_SCIENTIFIC_CLAIM",
                "NOT_REPRODUCED",
                "NOT_COMPARABLE",
            },
        )

    def _level(self, strategy, original, reproduced, tolerance=0.0, target="x"):
        spec = {"rules": [{"target": target, "strategy": strategy, "tolerance": tolerance}]}
        report = compare_results({target: original}, {target: reproduced}, spec)
        return report["results"][0]["level"], report

    def test_bitwise_identical(self):
        level, report = self._level("bitwise", "abc", "abc")
        self.assertEqual(level, "BITWISE_IDENTICAL")
        self.assertTrue(report["reproduced"])

    def test_numeric_within_and_beyond_tolerance(self):
        within, _ = self._level("numeric", 1.0, 1.0005, tolerance=0.001)
        self.assertEqual(within, "NUMERICALLY_EQUIVALENT_WITHIN_TOLERANCE")
        beyond, report = self._level("numeric", 1.0, 2.0, tolerance=0.001)
        self.assertEqual(beyond, "NOT_REPRODUCED")
        self.assertFalse(report["reproduced"])

    def test_candidate_set_equality(self):
        level, _ = self._level("set", ["BRCA1", "TP53"], ["TP53", "BRCA1"])
        self.assertEqual(level, "SAME_CANDIDATE_SET")

    def test_direction_equality(self):
        level, _ = self._level("direction", 2.5, 0.7)
        self.assertEqual(level, "SAME_DIRECTION")

    def test_scientific_claim_equality(self):
        level, _ = self._level("claim", "association", "association")
        self.assertEqual(level, "SAME_SCIENTIFIC_CLAIM")

    def test_missing_target_is_not_comparable(self):
        spec = {"rules": [{"target": "y", "strategy": "bitwise", "tolerance": 0.0}]}
        report = compare_results({"x": 1}, {"x": 1}, spec)
        self.assertEqual(report["results"][0]["level"], "NOT_COMPARABLE")

    def test_overall_level_is_the_weakest_target(self):
        spec = {
            "rules": [
                {"target": "a", "strategy": "bitwise", "tolerance": 0.0},
                {"target": "b", "strategy": "bitwise", "tolerance": 0.0},
            ]
        }
        report = compare_results({"a": "x", "b": "x"}, {"a": "x", "b": "DIFFERENT"}, spec)
        self.assertEqual(report["overall_level"], "NOT_REPRODUCED")
        self.assertFalse(report["reproduced"])


class FailureClassificationTests(unittest.TestCase):
    def test_exactly_five_bounded_failure_classes(self):
        self.assertEqual(len(FAILURE_CLASSES), 5)
        self.assertEqual(
            set(FAILURE_CLASSES),
            {"environment", "input", "numeric", "method", "scientifically_incomparable"},
        )

    def test_environment_takes_precedence(self):
        result = classify_failure(
            {"environment_match": False, "input_checksum_match": False, "method_match": False}
        )
        self.assertEqual(result["failure_class"], "environment")

    def test_input_mismatch_when_environment_ok(self):
        result = classify_failure({"environment_match": True, "input_checksum_match": False})
        self.assertEqual(result["failure_class"], "input")

    def test_method_mismatch(self):
        result = classify_failure(
            {"environment_match": True, "input_checksum_match": True, "method_match": False}
        )
        self.assertEqual(result["failure_class"], "method")

    def test_scientifically_incomparable(self):
        result = classify_failure(
            {
                "environment_match": True,
                "input_checksum_match": True,
                "method_match": True,
                "scope_comparable": False,
            }
        )
        self.assertEqual(result["failure_class"], "scientifically_incomparable")

    def test_numeric_is_the_residual_class(self):
        result = classify_failure(
            {
                "environment_match": True,
                "input_checksum_match": True,
                "method_match": True,
                "scope_comparable": True,
            }
        )
        self.assertEqual(result["failure_class"], "numeric")


if __name__ == "__main__":
    unittest.main()
