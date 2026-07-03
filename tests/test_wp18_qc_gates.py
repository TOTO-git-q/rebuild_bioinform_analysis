"""WP-18: four-layer QC rule registry, engine, and advancement gate."""

from __future__ import annotations

import copy
import unittest

from auto_bioinfo.core.validation import validate_qc_report
from auto_bioinfo.quality.qc_gates import (
    DEFAULT_REGISTRY,
    QC_DECISIONS,
    QCRuleRegistry,
    apply_human_review,
    propose_remediation,
    qc_gate_admits,
    qc_summary,
    run_qc,
)


def _passing_bundle() -> dict:
    return {
        "method_result": {
            "status": "succeeded",
            "task_run_id": "task_run_1",
            "n_genes": 100,
            "n_samples": 6,
            "n_labelled_samples": 6,
            "n_unmapped_ids": 0,
            "group_sizes": {"tumor": 3, "normal": 3},
            "outputs": {"deg_results_table": "deg.tsv"},
            "log_errors": [],
            "log_warnings": [],
            "multiple_testing_correction": "benjamini_hochberg",
            "single_sample_driven": False,
        },
        "artifact_manifest": {
            "artifact_id": "artifact_deg_1",
            "exists": True,
            "size_bytes": 4096,
            "is_placeholder": False,
            "checksum_sha256": "abc123",
        },
        "dataset_profile": {"modality": "bulk_rna", "group_sizes": {"tumor": 3, "normal": 3}},
        "contract": {
            "statistical_unit": "sample",
            "claim_capability": "association",
            "minimum_sample_design": {"groups": 2, "min_replicates_per_group": 2},
            "required_qc": ["execution.method_succeeded", "statistical.unit_is_sample", "statistical.min_replicates"],
        },
        "subquestion_ids": ["subq_1"],
    }


class QCEngineTest(unittest.TestCase):
    def test_passing_bundle_decides_pass_and_gate_admits(self):
        report = run_qc(_passing_bundle())
        self.assertEqual(report["decision"], "PASS")
        self.assertEqual(report["overall_status"], "pass")
        admitted, reason = qc_gate_admits(report)
        self.assertTrue(admitted, reason)

    def test_report_validates_against_core_validator(self):
        report = run_qc(_passing_bundle())
        self.assertEqual(validate_qc_report(report), [])

    def test_decision_is_bounded_vocabulary(self):
        report = run_qc(_passing_bundle())
        self.assertIn(report["decision"], QC_DECISIONS)

    def test_deterministic_identical_inputs(self):
        b = _passing_bundle()
        self.assertEqual(run_qc(b), run_qc(copy.deepcopy(b)))
        self.assertEqual(run_qc(b)["created_at"], "")

    def test_input_not_mutated(self):
        b = _passing_bundle()
        snapshot = copy.deepcopy(b)
        run_qc(b)
        self.assertEqual(b, snapshot)

    def test_pseudo_replication_hard_rejects_and_gate_blocks(self):
        b = _passing_bundle()
        b["contract"]["statistical_unit"] = "cell"
        report = run_qc(b)
        self.assertEqual(report["decision"], "REJECT")
        admitted, _ = qc_gate_admits(report)
        self.assertFalse(admitted)
        self.assertEqual(validate_qc_report(report), [])

    def test_missing_replicates_requires_replan(self):
        b = _passing_bundle()
        b["method_result"]["group_sizes"] = {"tumor": 1, "normal": 3}
        b["dataset_profile"]["group_sizes"] = {"tumor": 1, "normal": 3}
        report = run_qc(b)
        self.assertEqual(report["decision"], "REPLAN")
        self.assertFalse(qc_gate_admits(report)[0])

    def test_missing_expected_output_requires_retry(self):
        b = _passing_bundle()
        b["method_result"]["outputs"] = {}
        report = run_qc(b)
        self.assertEqual(report["decision"], "RETRY")

    def test_method_failure_hard_rejects(self):
        b = _passing_bundle()
        b["method_result"]["status"] = "failed"
        report = run_qc(b)
        self.assertEqual(report["decision"], "REJECT")

    def test_rna_overclaim_blocked_by_biological_layer(self):
        b = _passing_bundle()
        b["contract"]["claim_capability"] = "causal_support"
        report = run_qc(b)
        self.assertEqual(report["decision"], "REJECT")
        rule_ids = {f["rule_id"] for f in report["blocking_findings"]}
        self.assertIn("biological.claim_capability_matches_data", rule_ids)

    def test_single_cell_metrics_not_assessed_when_absent(self):
        b = _passing_bundle()
        b["dataset_profile"]["modality"] = "single_cell_rna"
        report = run_qc(b)
        statuses = {f["rule_id"]: f["status"] for f in report["findings"]}
        self.assertEqual(statuses.get("data.sc_quality_metrics"), "not_assessed")

    def test_single_cell_doublet_out_of_range_fails(self):
        b = _passing_bundle()
        b["dataset_profile"]["modality"] = "single_cell_rna"
        b["sc_metrics"] = {"doublet_rate": 0.4, "ambient_rna_fraction": 0.1}
        report = run_qc(b)
        self.assertIn("data.sc_quality_metrics", {f["rule_id"] for f in report["blocking_findings"]})

    def test_required_qc_gap_cannot_pass(self):
        b = _passing_bundle()
        # Require a single-cell rule that will not run on bulk data -> not executed.
        b["contract"]["required_qc"] = ["data.sc_quality_metrics"]
        report = run_qc(b)
        self.assertFalse(report["required_qc_coverage"]["complete"])
        self.assertEqual(report["decision"], "NEED_HUMAN_REVIEW")
        self.assertFalse(qc_gate_admits(report)[0])

    def test_warnings_pass_with_warnings_and_policy_gate(self):
        b = _passing_bundle()
        b["method_result"]["log_warnings"] = ["deprecation notice"]
        report = run_qc(b, allow_warnings=False)
        self.assertEqual(report["decision"], "PASS_WITH_WARNINGS")
        self.assertFalse(qc_gate_admits(report)[0])
        self.assertTrue(qc_gate_admits(report, allow_warnings=True)[0])

    def test_single_sample_driven_needs_human_review(self):
        b = _passing_bundle()
        b["method_result"]["single_sample_driven"] = True
        report = run_qc(b)
        self.assertEqual(report["decision"], "NEED_HUMAN_REVIEW")

    def test_findings_are_scoped(self):
        report = run_qc(_passing_bundle())
        for finding in report["findings"]:
            self.assertEqual(finding["scope"]["artifact_id"], "artifact_deg_1")
            self.assertIn("task_run_id", finding["scope"])


class RemediationAndReviewTest(unittest.TestCase):
    def test_remediation_forbids_threshold_tuning(self):
        b = _passing_bundle()
        b["method_result"]["group_sizes"] = {"tumor": 1, "normal": 3}
        b["dataset_profile"]["group_sizes"] = {"tumor": 1, "normal": 3}
        proposal = propose_remediation(run_qc(b))
        self.assertTrue(proposal["proposals"])
        for item in proposal["proposals"]:
            self.assertIn("significance_alpha", item["forbidden_parameters"])
            self.assertEqual(item["mutable_parameters"], [])

    def test_human_review_cannot_erase_fail(self):
        b = _passing_bundle()
        b["contract"]["statistical_unit"] = "cell"
        report = run_qc(b)
        record = apply_human_review(report, accept_warnings=True, reviewer="curator", note="looks ok")
        self.assertEqual(record["outcome"], "rejected_fail_present")
        self.assertEqual(record["effective_decision"], "REJECT")
        self.assertEqual(len(record["preserved_findings"]), len(report["findings"]))

    def test_human_review_accepts_warnings_under_policy(self):
        b = _passing_bundle()
        b["method_result"]["log_warnings"] = ["deprecation"]
        report = run_qc(b)
        record = apply_human_review(report, accept_warnings=True, reviewer="curator", note="acceptable")
        self.assertEqual(record["outcome"], "warnings_accepted")
        self.assertTrue(record["warnings_accepted"])

    def test_human_review_blocked_when_policy_forbids(self):
        b = _passing_bundle()
        b["method_result"]["log_warnings"] = ["deprecation"]
        report = run_qc(b)
        record = apply_human_review(report, accept_warnings=True, reviewer="c", note="n", policy_allows_override=False)
        self.assertEqual(record["outcome"], "override_not_permitted")


class RegistryTest(unittest.TestCase):
    def test_registry_is_queryable_and_frozen(self):
        self.assertIsNotNone(DEFAULT_REGISTRY.get("execution.method_succeeded"))
        self.assertEqual(len(DEFAULT_REGISTRY.for_layer("statistical")), 4)
        self.assertEqual(DEFAULT_REGISTRY.freeze(), QCRuleRegistry().freeze())

    def test_summary_counts_by_layer(self):
        summary = qc_summary(run_qc(_passing_bundle()))
        self.assertEqual(summary["decision"], "PASS")
        self.assertIn("execution", summary["by_layer"])


if __name__ == "__main__":
    unittest.main()
