"""WP-19: EvidenceItem admission gate and evidence registry."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_evidence_item
from auto_bioinfo.evidence.admission import (
    EvidenceRegistry,
    admit_evidence,
    classify_relation,
    compute_allowed_claim_level,
    resolve_replication_status,
)


def _result_table(n_sig: int = 3) -> list[dict]:
    rows = []
    for i in range(10):
        sig = i < n_sig
        rows.append({"gene": f"GENE_{i}", "log2_fold_change": 2.0 if sig else 0.1, "fdr": 0.001 if sig else 0.5, "significant": sig})
    return rows


def _inputs(**overrides):
    base = dict(
        result_table=_result_table(),
        method_result={"status": "succeeded", "task_run_id": "task_run_1", "group_a": "tumor", "group_b": "normal", "adequately_powered": True},
        artifact_manifest={"artifact_id": "artifact_deg_1", "exists": True, "is_placeholder": False, "checksum_sha256": "abc"},
        qc_report={"qc_report_id": "qc_report_1", "decision": "PASS", "overall_status": "pass"},
        dataset_profile={"dataset_id": "dataset_1", "known_limitations": []},
        scope_bundle={"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]},
        subquestion={"subquestion_id": "subq_1", "claim_ceiling": "association", "expected_direction": "up"},
        contract={"claim_capability": "association", "parameters": {"significance_alpha": 0.05, "log2fc_threshold": 1.0}, "version": "v1"},
        project_ceiling="association",
    )
    base.update(overrides)
    return base


class AdmissionGateTest(unittest.TestCase):
    def test_qc_pass_admits_evidence(self):
        outcome = admit_evidence(**_inputs())
        self.assertTrue(outcome.admitted)
        self.assertIsNotNone(outcome.evidence_item)
        self.assertEqual(validate_evidence_item(outcome.evidence_item), [])

    def test_qc_reject_is_non_admissible(self):
        qc = {"qc_report_id": "qc_report_2", "decision": "REJECT", "overall_status": "fail"}
        outcome = admit_evidence(**_inputs(qc_report=qc))
        self.assertFalse(outcome.admitted)
        self.assertEqual(outcome.reason_code, "QC_NOT_PASSED")
        self.assertEqual(outcome.non_admissible_marker["record_type"], "NON_ADMISSIBLE_RESULT")
        self.assertFalse(outcome.non_admissible_marker["is_formal_evidence"])

    def test_significant_but_qc_failed_rejected(self):
        # A significant result that fails QC must never become evidence.
        qc = {"qc_report_id": "qc_report_3", "decision": "REJECT", "overall_status": "fail"}
        outcome = admit_evidence(**_inputs(result_table=_result_table(n_sig=8), qc_report=qc))
        self.assertFalse(outcome.admitted)

    def test_missing_lineage_rejected(self):
        mr = {"status": "succeeded", "task_run_id": "", "group_a": "t", "group_b": "n"}
        outcome = admit_evidence(**_inputs(method_result=mr))
        self.assertFalse(outcome.admitted)
        self.assertEqual(outcome.reason_code, "NO_LINEAGE")

    def test_placeholder_artifact_rejected(self):
        art = {"artifact_id": "artifact_x", "exists": True, "is_placeholder": True, "checksum_sha256": "abc"}
        outcome = admit_evidence(**_inputs(artifact_manifest=art))
        self.assertFalse(outcome.admitted)
        self.assertEqual(outcome.reason_code, "MISSING_ARTIFACT")

    def test_pass_with_warnings_needs_policy(self):
        qc = {"qc_report_id": "qc_w", "decision": "PASS_WITH_WARNINGS", "overall_status": "pass_with_warnings"}
        blocked = admit_evidence(**_inputs(qc_report=qc, allow_warnings=False))
        self.assertFalse(blocked.admitted)
        self.assertEqual(blocked.reason_code, "POLICY_WARNINGS_NOT_ACCEPTED")
        allowed = admit_evidence(**_inputs(qc_report=qc, allow_warnings=True))
        self.assertTrue(allowed.admitted)
        # A warning-tainted run caps evidence at association.
        self.assertEqual(allowed.evidence_item["allowed_claim_level"], "association")

    def test_deterministic(self):
        self.assertEqual(admit_evidence(**_inputs()).to_dict(), admit_evidence(**_inputs()).to_dict())
        self.assertEqual(admit_evidence(**_inputs()).evidence_item["created_at"], "")


class ClaimCeilingTest(unittest.TestCase):
    def test_min_of_all_ceilings(self):
        self.assertEqual(
            compute_allowed_claim_level(
                method_capability="causal_support", subquestion_ceiling="association", project_ceiling="mechanistic_hypothesis", qc_decision="PASS"
            ),
            "association",
        )

    def test_qc_warnings_cap(self):
        self.assertEqual(
            compute_allowed_claim_level(
                method_capability="mechanistic_hypothesis",
                subquestion_ceiling="mechanistic_hypothesis",
                project_ceiling="mechanistic_hypothesis",
                qc_decision="PASS_WITH_WARNINGS",
            ),
            "association",
        )

    def test_subquestion_ceiling_binds(self):
        outcome = admit_evidence(**_inputs(subquestion={"subquestion_id": "subq_1", "claim_ceiling": "descriptive", "expected_direction": "up"}))
        self.assertEqual(outcome.evidence_item["allowed_claim_level"], "descriptive")


class RelationAndReplicationTest(unittest.TestCase):
    def test_significant_supports(self):
        self.assertEqual(classify_relation(n_significant=5, expected_direction="up", observed_direction="up", adequately_powered=True), "supports")

    def test_opposite_direction_opposes(self):
        self.assertEqual(classify_relation(n_significant=5, expected_direction="up", observed_direction="down", adequately_powered=True), "opposes")

    def test_nonsignificant_powered_is_neutral(self):
        self.assertEqual(classify_relation(n_significant=0, expected_direction="up", observed_direction="", adequately_powered=True), "neutral")

    def test_nonsignificant_underpowered_is_inconclusive(self):
        self.assertEqual(classify_relation(n_significant=0, expected_direction="up", observed_direction="", adequately_powered=False), "inconclusive")

    def test_single_dataset_not_replicated(self):
        self.assertEqual(resolve_replication_status(source_dataset_ids=["d1"]), "single_dataset")

    def test_same_cohort_not_replicated(self):
        self.assertEqual(resolve_replication_status(source_dataset_ids=["d1", "d2"], prior_dataset_ids=["d1"], same_cohort=True), "multi_dataset")

    def test_independent_datasets_replicated(self):
        self.assertEqual(resolve_replication_status(source_dataset_ids=["d1", "d2"], same_cohort=False), "replicated")


class RegistryTest(unittest.TestCase):
    def test_negative_evidence_not_hidden_by_default(self):
        reg = EvidenceRegistry()
        # An inconclusive (underpowered non-significant) result is negative but retained.
        mr = {"status": "succeeded", "task_run_id": "tr", "group_a": "t", "group_b": "n", "adequately_powered": False}
        neg = admit_evidence(**_inputs(result_table=_result_table(n_sig=0), method_result=mr))
        pos = admit_evidence(**_inputs())
        reg.admit(neg)
        reg.admit(pos)
        self.assertEqual(len(reg.query()), 2)  # default includes negative
        self.assertEqual(len(reg.negative_evidence()), 1)
        self.assertEqual(len(reg.query(include_negative=False)), 1)

    def test_non_admissible_isolated_from_evidence(self):
        reg = EvidenceRegistry()
        qc = {"qc_report_id": "qc", "decision": "REJECT", "overall_status": "fail"}
        reg.admit(admit_evidence(**_inputs(qc_report=qc)))
        self.assertEqual(len(reg.evidence_items()), 0)
        self.assertEqual(len(reg.non_admissible_markers()), 1)

    def test_query_by_scope(self):
        reg = EvidenceRegistry()
        reg.admit(admit_evidence(**_inputs()))
        self.assertEqual(len(reg.query(subquestion_id="subq_1")), 1)
        self.assertEqual(len(reg.query(dataset_id="dataset_1")), 1)
        self.assertEqual(len(reg.query(subquestion_id="nope")), 0)

    def test_retract_marks_stale_without_delete(self):
        reg = EvidenceRegistry()
        eid = reg.admit(admit_evidence(**_inputs()))
        event = reg.retract(eid, reason="upstream invalidated", dependent_claim_ids=["claim_1"])
        self.assertEqual(event["stale_claim_ids"], ["claim_1"])
        self.assertTrue(reg.is_retracted(eid))
        self.assertEqual(len(reg.evidence_items()), 0)  # excluded from default
        self.assertEqual(len(reg.evidence_items(include_retracted=True)), 1)  # history preserved


if __name__ == "__main__":
    unittest.main()
