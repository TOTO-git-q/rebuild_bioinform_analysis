"""WP-21: constrained report generation + traceability index."""

from __future__ import annotations

import unittest

from auto_bioinfo.evidence.admission import admit_evidence
from auto_bioinfo.evidence.claim_synthesis import synthesize_claims
from auto_bioinfo.evidence.question_alignment import audit_alignment
from auto_bioinfo.reporting.report_builder import (
    ReportInputRefused,
    advance_report_status,
    build_report,
    build_report_input_bundle,
    validate_report_manifest,
)
from auto_bioinfo.reporting.trace_index import build_figure_list, build_trace_index

_SPEC = {
    "project_id": "proj_1",
    "research_spec_id": "spec_1",
    "research_question": "Which genes differ between tumor and normal liver?",
    "max_claim_level": "association",
}
_SCOPE = {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]}
_SUBQ = [{"subquestion_id": "subq_1", "claim_ceiling": "association"}]
_MANIFEST = {"dataset_manifest_id": "dm_1", "dataset_id": "dataset_1", "samples": [{"id": "s1"}], "excluded_samples": []}


def _result_table(n_sig=3):
    return [{"gene": f"G{i}", "log2_fold_change": 2.0 if i < n_sig else 0.1, "fdr": 0.001 if i < n_sig else 0.5, "significant": i < n_sig} for i in range(10)]


def _pipeline_objects():
    outcome = admit_evidence(
        result_table=_result_table(),
        method_result={"status": "succeeded", "task_run_id": "tr_1", "group_a": "tumor", "group_b": "normal"},
        artifact_manifest={"artifact_id": "artifact_1", "exists": True, "is_placeholder": False, "checksum_sha256": "abc"},
        qc_report={"qc_report_id": "qc_1", "decision": "PASS", "overall_status": "pass", "artifact_id": "artifact_1"},
        dataset_profile={"dataset_id": "dataset_1", "known_limitations": []},
        scope_bundle=_SCOPE,
        subquestion={"subquestion_id": "subq_1", "claim_ceiling": "association", "expected_direction": "up"},
        contract={"claim_capability": "association", "parameters": {"significance_alpha": 0.05}, "version": "v1"},
        project_ceiling="association",
    )
    evidence = [outcome.evidence_item]
    claims = synthesize_claims(evidence_items=evidence, subquestions=_SUBQ, scope_bundle=_SCOPE, project_ceiling="association").claims
    artifacts = [{"artifact_id": "artifact_1", "exists": True, "is_placeholder": False, "qc_status": "pass", "expected_by_task_ids": ["tr_1"]}]
    audit = audit_alignment(
        research_spec=_SPEC,
        subquestions=_SUBQ,
        scope_bundle=_SCOPE,
        evidence_items=evidence,
        claims=claims,
        artifact_manifests=artifacts,
        qc_reports=[{"qc_report_id": "qc_1", "decision": "PASS", "overall_status": "pass", "artifact_id": "artifact_1", "checks": []}],
        project_ceiling="association",
    )
    return evidence, claims, artifacts, audit


def _bundle(**overrides):
    evidence, claims, artifacts, audit = _pipeline_objects()
    base = dict(
        research_spec=_SPEC,
        scope_bundle=_SCOPE,
        dataset_manifest=_MANIFEST,
        subquestions=_SUBQ,
        qc_reports=[{"qc_report_id": "qc_1", "decision": "PASS", "overall_status": "pass", "artifact_id": "artifact_1"}],
        evidence_items=evidence,
        claims=claims,
        alignment_audit=audit,
        method_contracts=[{"method_contract_id": "mc_1", "parameters": {"alpha": 0.05}, "supports_subquestion_ids": ["subq_1"]}],
        task_runs=[{"task_run_id": "tr_1", "method_contract_id": "mc_1"}],
        artifact_manifests=artifacts,
    )
    base.update(overrides)
    return build_report_input_bundle(**base)


class InputBundleTest(unittest.TestCase):
    def test_refuses_when_not_report_ready(self):
        # Craft an audit that is not report-ready via an over-claim.
        _, claims, artifacts, _ = _pipeline_objects()
        bad_claim = dict(claims[0])
        bad_claim["text"] = "Gene X causes tumor progression"
        audit = audit_alignment(
            research_spec=_SPEC,
            subquestions=_SUBQ,
            scope_bundle=_SCOPE,
            evidence_items=[],
            claims=[bad_claim],
            artifact_manifests=artifacts,
            qc_reports=[],
            project_ceiling="association",
        )
        self.assertFalse(audit["report_ready"])
        with self.assertRaises(ReportInputRefused):
            build_report_input_bundle(
                research_spec=_SPEC,
                scope_bundle=_SCOPE,
                dataset_manifest=_MANIFEST,
                subquestions=_SUBQ,
                qc_reports=[],
                evidence_items=[],
                claims=[bad_claim],
                alignment_audit=audit,
            )

    def test_partial_override_allowed_with_reason(self):
        _, claims, artifacts, _ = _pipeline_objects()
        audit = {"report_ready": False, "report_blocking_issues": [{"kind": "unanswered_subquestion"}], "coverage": [], "structural": {}}
        bundle = build_report_input_bundle(
            research_spec=_SPEC,
            scope_bundle=_SCOPE,
            dataset_manifest=_MANIFEST,
            subquestions=_SUBQ,
            qc_reports=[],
            evidence_items=[],
            claims=claims,
            alignment_audit=audit,
            allow_partial=True,
            terminal_reason="partial complete",
        )
        self.assertTrue(bundle["partial"])


class BuildReportTest(unittest.TestCase):
    def test_clean_report_is_publishable_draft(self):
        result = build_report(_bundle())
        self.assertEqual(result.status, "DRAFT")
        self.assertTrue(result.publishable, result.blocking_reasons)
        self.assertEqual(result.blocking_reasons, [])

    def test_manifest_validates_and_pins_inputs(self):
        result = build_report(_bundle())
        self.assertEqual(validate_report_manifest(result.manifest), [])
        self.assertIn("input_version_pins", result.manifest)
        self.assertEqual(result.manifest["input_version_pins"]["research_spec_id"], "spec_1")
        self.assertIn("report.md", result.manifest["output_checksums"])

    def test_markdown_and_json_reference_same_claims(self):
        result = build_report(_bundle())
        for claim in result.report_model["positive_results"]:
            self.assertIn(claim["claim_id"], result.markdown)

    def test_deterministic_checksums(self):
        a = build_report(_bundle()).manifest["output_checksums"]
        b = build_report(_bundle()).manifest["output_checksums"]
        self.assertEqual(a, b)

    def test_required_result_sections_present(self):
        model = build_report(_bundle()).report_model
        for section in ("positive_results", "negative_results", "conflicting_results", "unanswered_questions", "failed_branches"):
            self.assertIn(section, model)

    def test_coverage_matrix_lists_every_subquestion(self):
        result = build_report(_bundle(subquestions=_SUBQ + [{"subquestion_id": "subq_2", "claim_ceiling": "association"}]))
        ids = {r["subquestion_id"] for r in result.coverage_matrix["rows"]}
        self.assertEqual(ids, {"subq_1", "subq_2"})

    def test_untraceable_claim_blocks_release(self):
        # Claim references evidence not in the pool.
        _, claims, artifacts, audit = _pipeline_objects()
        broken = dict(claims[0])
        broken["evidence_item_refs"] = ["missing_evidence"]
        bundle = _bundle(claims=[broken], evidence_items=[])
        result = build_report(bundle)
        self.assertFalse(result.publishable)
        self.assertTrue(any("untraceable" in r for r in result.blocking_reasons))
        with self.assertRaises(ValueError):
            advance_report_status(advance_report_status("DRAFT", "REVIEWED"), "RELEASED", publishable=result.publishable)

    def test_figure_without_source_blocks(self):
        result = build_report(_bundle(figures=[{"figure_id": "f1", "title": "Volcano", "source_artifact_id": "", "task_run_id": ""}]))
        self.assertFalse(result.publishable)
        self.assertTrue(any("source table" in r for r in result.blocking_reasons))

    def test_overclaim_language_blocks(self):
        _, claims, artifacts, _ = _pipeline_objects()
        # Force over-claim text but keep the audit ready by auditing the clean claim.
        _, clean_claims, _, audit = _pipeline_objects()
        loud = dict(claims[0])
        loud["text"] = "This gene causes tumor growth"
        bundle = _bundle(claims=[loud])
        result = build_report(bundle)
        self.assertFalse(result.publishable)
        self.assertTrue(any("over-claim" in r for r in result.blocking_reasons))


class StatusTest(unittest.TestCase):
    def test_forward_transitions(self):
        self.assertEqual(advance_report_status("DRAFT", "REVIEWED"), "REVIEWED")
        self.assertEqual(advance_report_status("REVIEWED", "RELEASED"), "RELEASED")

    def test_illegal_skip(self):
        with self.assertRaises(ValueError):
            advance_report_status("DRAFT", "RELEASED")

    def test_unpublishable_release_refused(self):
        with self.assertRaises(ValueError):
            advance_report_status("REVIEWED", "RELEASED", publishable=False)


class TraceIndexTest(unittest.TestCase):
    def test_complete_chain(self):
        evidence, claims, artifacts, _ = _pipeline_objects()
        idx = build_trace_index(claims, evidence, artifacts)
        self.assertTrue(idx["complete"])
        chain = idx["chains"][claims[0]["claim_id"]][0]
        self.assertEqual(chain["artifact_id"], "artifact_1")
        self.assertEqual(chain["dataset_ids"], ["dataset_1"])

    def test_figure_list_gap(self):
        fl = build_figure_list([{"figure_id": "f1", "source_artifact_id": "nope", "task_run_id": "tr"}], [{"artifact_id": "artifact_1"}])
        self.assertFalse(fl["complete"])


if __name__ == "__main__":
    unittest.main()
