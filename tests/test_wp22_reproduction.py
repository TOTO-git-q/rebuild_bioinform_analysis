"""WP-22: reproduction bundle + clean deterministic rerun + result comparison."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_reproduction_bundle_manifest
from auto_bioinfo.reproduction.clean_rerun import (
    COMPARISON_LEVELS,
    classify_failure,
    compare_results,
    render_deg_tsv,
    run_clean_rerun,
)
from auto_bioinfo.reproduction.repro_bundle import (
    SensitiveExportRefused,
    build_bundle,
    scan_sensitive,
    supersede_bundle,
    verify_bundle,
)

_ROWS = [
    {"gene": "GENE_A", "log2_fold_change": 2.0, "fdr": 0.001, "significant": True},
    {"gene": "GENE_B", "log2_fold_change": 0.1, "fdr": 0.5, "significant": False},
]


def _objects(**overrides):
    base = dict(
        research_spec={"research_spec_id": "spec_1", "project_id": "proj_1"},
        scope_bundle={"species": ["human"]},
        subquestions=[{"subquestion_id": "subq_1"}],
        evidence_plan={"plan_id": "ep_1"},
        dataset_manifest={"dataset_manifest_id": "dm_1", "dataset_id": "dataset_1"},
        workflow_plan={"workflow_plan_id": "wf_1"},
        task_packets=[{"task_id": "t1"}],
        parameters={"significance_alpha": 0.05},
        environment={"python": "3.11", "numpy": "1.24"},
        qc_rules=[{"qc_report_id": "qc_1", "overall_status": "pass"}],
        known_limitations=["single dataset"],
        original_run_summary={"method_id": "deg_welch", "n_significant": 1},
        trace_index={"complete": True},
        claims=[{"claim_id": "claim_1", "claim_level": "association"}],
        input_files={"counts.tsv": "gene\ts1\ts2\nGENE_A\t10\t20\n"},
        output_files={"deg_results.tsv": render_deg_tsv(_ROWS)},
        license="CC-BY-4.0",
    )
    base.update(overrides)
    return base


class BuildBundleTest(unittest.TestCase):
    def test_bundle_has_required_files(self):
        result = build_bundle(project_id="proj_1", objects=_objects())
        for required in [
            "research_spec.json",
            "dataset_manifest.json",
            "parameters.json",
            "environment.json",
            "claims.json",
            "comparison_spec.json",
            "run_order.md",
            "checksums.sha256",
            "inputs/counts.tsv",
            "outputs/deg_results.tsv",
        ]:
            self.assertIn(required, result.files, required)
        self.assertEqual(result.status, "valid")

    def test_manifest_validates(self):
        result = build_bundle(project_id="proj_1", objects=_objects())
        self.assertEqual(validate_reproduction_bundle_manifest(result.manifest), [])
        self.assertIn("checksums_sha256", result.manifest)
        self.assertEqual(result.manifest["license"], "CC-BY-4.0")

    def test_deterministic(self):
        a = build_bundle(project_id="proj_1", objects=_objects())
        b = build_bundle(project_id="proj_1", objects=_objects())
        self.assertEqual(a.checksums, b.checksums)
        self.assertEqual(a.manifest["bundle_id"], b.manifest["bundle_id"])

    def test_comparison_spec_covers_outputs(self):
        result = build_bundle(project_id="proj_1", objects=_objects())
        strategies = {r["strategy"] for r in result.comparison_spec["rules"]}
        self.assertTrue(strategies <= set(result.comparison_spec["strategies"]))
        self.assertTrue(result.comparison_spec["rules"])


class SensitiveScanTest(unittest.TestCase):
    def test_absolute_path_detected(self):
        findings = scan_sensitive({"a.json": "path is /home/toto/data"})
        self.assertTrue(any(f["kind"] == "absolute_path" for f in findings))

    def test_secret_detected(self):
        findings = scan_sensitive({"env": "api_key = sk-abc123"})
        self.assertTrue(any(f["kind"] == "secret" for f in findings))

    def test_internal_uri_detected(self):
        findings = scan_sensitive({"cfg": "db at postgres://user@host/db"})
        self.assertTrue(any(f["kind"] == "internal_uri" for f in findings))

    def test_formal_export_refused_on_sensitive(self):
        objs = _objects(known_limitations=["stored at /home/toto/secret.tsv"])
        with self.assertRaises(SensitiveExportRefused):
            build_bundle(project_id="proj_1", objects=objs, formal=True)
        # Non-formal build returns findings and marks invalid instead of raising.
        result = build_bundle(project_id="proj_1", objects=objs, formal=False)
        self.assertEqual(result.status, "invalid")
        self.assertFalse(result.clean)


class VerifyAndSupersedeTest(unittest.TestCase):
    def test_clean_bundle_verifies(self):
        result = build_bundle(project_id="proj_1", objects=_objects())
        checks = {p: c for p, c in result.checksums.items()}
        report = verify_bundle({p: result.files[p] for p in checks}, checks)
        self.assertTrue(report["valid"])

    def test_tampered_file_detected(self):
        result = build_bundle(project_id="proj_1", objects=_objects())
        files = dict(result.files)
        files["outputs/deg_results.tsv"] = files["outputs/deg_results.tsv"] + "TAMPERED\n"
        report = verify_bundle(files, result.checksums)
        self.assertFalse(report["valid"])
        self.assertEqual(report["overall"], "INVALID")

    def test_supersede_bumps_version_and_links(self):
        first = build_bundle(project_id="proj_1", objects=_objects())
        second = supersede_bundle(first.manifest, project_id="proj_1", objects=_objects(license="MIT"))
        self.assertEqual(second.manifest["bundle_version"], 2)
        self.assertEqual(second.manifest["supersedes_bundle_id"], first.manifest["bundle_id"])
        # The old bundle still verifies (not overwritten).
        self.assertTrue(verify_bundle({p: first.files[p] for p in first.checksums}, first.checksums)["valid"])


class CleanRerunTest(unittest.TestCase):
    def test_rerun_isolated_workdir_reproduces_bitwise(self):
        records = [{"task_id": "t1", "output_name": "deg_results.tsv", "rows": _ROWS}]
        rerun = run_clean_rerun(records)
        self.assertIn("isolated", rerun["workdir"])
        original = {"outputs/deg_results.tsv": render_deg_tsv(_ROWS)}
        reproduced = {"outputs/deg_results.tsv": rerun["reproduced_outputs"]["deg_results.tsv"]}
        spec = {"rules": [{"target": "outputs/deg_results.tsv", "strategy": "bitwise", "tolerance": 0.0}]}
        cmp = compare_results(original, reproduced, spec)
        self.assertEqual(cmp["overall_level"], "BITWISE_IDENTICAL")
        self.assertTrue(cmp["reproduced"])

    def test_seven_levels(self):
        self.assertEqual(len(COMPARISON_LEVELS), 7)

    def test_numeric_within_tolerance(self):
        spec = {"rules": [{"target": "effect", "strategy": "numeric", "tolerance": 0.01}]}
        cmp = compare_results({"effect": 1.000}, {"effect": 1.005}, spec)
        self.assertEqual(cmp["overall_level"], "NUMERICALLY_EQUIVALENT_WITHIN_TOLERANCE")

    def test_numeric_beyond_tolerance_not_reproduced(self):
        spec = {"rules": [{"target": "effect", "strategy": "numeric", "tolerance": 0.001}]}
        cmp = compare_results({"effect": 1.0}, {"effect": 2.0}, spec)
        self.assertEqual(cmp["overall_level"], "NOT_REPRODUCED")
        self.assertFalse(cmp["reproduced"])

    def test_same_candidate_set(self):
        spec = {"rules": [{"target": "genes", "strategy": "set", "tolerance": 0}]}
        cmp = compare_results({"genes": ["A", "B"]}, {"genes": ["B", "A"]}, spec)
        self.assertEqual(cmp["overall_level"], "SAME_CANDIDATE_SET")

    def test_direction(self):
        spec = {"rules": [{"target": "lfc", "strategy": "direction", "tolerance": 0}]}
        self.assertEqual(compare_results({"lfc": 2.0}, {"lfc": 3.0}, spec)["overall_level"], "SAME_DIRECTION")
        self.assertEqual(compare_results({"lfc": 2.0}, {"lfc": -3.0}, spec)["overall_level"], "NOT_REPRODUCED")

    def test_missing_target_not_comparable(self):
        spec = {"rules": [{"target": "absent", "strategy": "bitwise", "tolerance": 0}]}
        self.assertEqual(compare_results({}, {}, spec)["overall_level"], "NOT_COMPARABLE")

    def test_failure_classification(self):
        self.assertEqual(classify_failure({"environment_match": False})["failure_class"], "environment")
        self.assertEqual(classify_failure({"input_checksum_match": False})["failure_class"], "input")
        self.assertEqual(classify_failure({"method_match": False})["failure_class"], "method")
        self.assertEqual(classify_failure({"scope_comparable": False})["failure_class"], "scientifically_incomparable")
        self.assertEqual(classify_failure({})["failure_class"], "numeric")


if __name__ == "__main__":
    unittest.main()
