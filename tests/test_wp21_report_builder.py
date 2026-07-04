"""WP-21: constrained report generation, manifest pinning, and traceability.

Validation slice locking the already-merged ``auto_bioinfo.reporting`` package
(``report_builder`` / ``claim_lint`` / ``trace_index``) against the requirement-spec
stage-17 contract: constrained report input gating, partial-report override
semantics, deterministic publishable draft generation, manifest/input pinning,
claim-to-markdown traceability, coverage matrices, blocking of untraceable
claims/figures and over-claim language, bounded report-status transitions, and
trace-index completeness.  These tests never mutate production implementation; they
build fixtures from the real synthesis pipeline (so the objects are shaped exactly as
the builder expects) and assert the builder's fail-closed behaviour.
"""

from __future__ import annotations

import json
import unittest

from auto_bioinfo.evidence.admission import admit_evidence
from auto_bioinfo.evidence.claim_synthesis import synthesize_claims
from auto_bioinfo.evidence.question_alignment import audit_alignment
from auto_bioinfo.reporting.claim_lint import CLAIM_LINT_KINDS, lint_report_language
from auto_bioinfo.reporting.report_builder import (
    REQUIRED_RESULT_SECTIONS,
    ReportInputRefused,
    advance_report_status,
    build_report,
    build_report_input_bundle,
    validate_report_manifest,
)
from auto_bioinfo.reporting.trace_index import (
    build_coverage_matrix,
    build_figure_list,
    build_method_trace_table,
    build_trace_index,
    has_untraceable_claim,
)

_SPEC = {
    "project_id": "proj_wp21",
    "research_spec_id": "spec_wp21",
    "research_question": "Which genes differ between tumor and normal liver tissue?",
    "max_claim_level": "association",
}
_SCOPE = {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"]}
_SUBQ = [{"subquestion_id": "subq_1", "claim_ceiling": "association", "expected_direction": "up"}]
_MANIFEST = {
    "dataset_manifest_id": "dm_wp21",
    "dataset_id": "dataset_wp21",
    "samples": [{"id": "s1"}, {"id": "s2"}],
    "excluded_samples": [{"id": "s3", "reason": "low_reads"}],
}


def _result_table(n_sig: int = 3) -> list[dict]:
    return [
        {
            "gene": f"G{i}",
            "log2_fold_change": 2.2 if i < n_sig else 0.1,
            "fdr": 0.001 if i < n_sig else 0.6,
            "significant": i < n_sig,
        }
        for i in range(10)
    ]


def _pipeline_objects():
    """Run the real evidence→claim→alignment pipeline to get correctly-shaped inputs."""
    outcome = admit_evidence(
        result_table=_result_table(),
        method_result={"status": "succeeded", "task_run_id": "tr_1", "group_a": "tumor", "group_b": "normal"},
        artifact_manifest={"artifact_id": "artifact_1", "exists": True, "is_placeholder": False, "checksum_sha256": "abc123"},
        qc_report={"qc_report_id": "qc_1", "decision": "PASS", "overall_status": "pass", "artifact_id": "artifact_1"},
        dataset_profile={"dataset_id": "dataset_wp21", "known_limitations": []},
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


def _clean_bundle(**overrides):
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


class ConstrainedInputGatingTest(unittest.TestCase):
    """T-21-01: an un-cleared alignment can never be silently carried into a report."""

    def test_non_report_ready_input_is_refused_without_override(self):
        _, _, artifacts, _ = _pipeline_objects()
        over_claim = {
            "claim_id": "claim_bad",
            "claim_level": "association",
            "status": "supports",
            "text": "This gene causes tumor progression",
            "evidence_item_refs": [],
        }
        audit = audit_alignment(
            research_spec=_SPEC,
            subquestions=_SUBQ,
            scope_bundle=_SCOPE,
            evidence_items=[],
            claims=[over_claim],
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
                claims=[over_claim],
                alignment_audit=audit,
            )

    def test_partial_override_requires_both_flag_and_terminal_reason(self):
        audit = {"report_ready": False, "report_blocking_issues": [{"kind": "unanswered_subquestion"}], "coverage": [], "structural": {}}
        # allow_partial without a terminal_reason is still refused.
        with self.assertRaises(ReportInputRefused):
            build_report_input_bundle(
                research_spec=_SPEC,
                scope_bundle=_SCOPE,
                dataset_manifest=_MANIFEST,
                subquestions=_SUBQ,
                qc_reports=[],
                evidence_items=[],
                claims=[],
                alignment_audit=audit,
                allow_partial=True,
                terminal_reason="",
            )
        # allow_partial + explicit terminal_reason is accepted and marks the bundle partial.
        bundle = build_report_input_bundle(
            research_spec=_SPEC,
            scope_bundle=_SCOPE,
            dataset_manifest=_MANIFEST,
            subquestions=_SUBQ,
            qc_reports=[],
            evidence_items=[],
            claims=[],
            alignment_audit=audit,
            allow_partial=True,
            terminal_reason="project entered partial-complete terminal state",
        )
        self.assertTrue(bundle["partial"])
        self.assertEqual(bundle["terminal_reason"], "project entered partial-complete terminal state")

    def test_report_ready_bundle_is_not_marked_partial(self):
        bundle = _clean_bundle()
        self.assertFalse(bundle["partial"])
        self.assertEqual(bundle["terminal_reason"], "")


class PublishableDraftTest(unittest.TestCase):
    """T-21-02: a clean bundle builds a publishable DRAFT with no blocking reasons."""

    def test_clean_bundle_builds_publishable_draft(self):
        result = build_report(_clean_bundle())
        self.assertEqual(result.status, "DRAFT")
        self.assertEqual(result.blocking_reasons, [])
        self.assertTrue(result.publishable)

    def test_positive_claim_lands_in_positive_results(self):
        result = build_report(_clean_bundle())
        self.assertTrue(result.report_model["positive_results"], "significant result should synthesize a supported claim")

    def test_partial_bundle_renders_terminal_reason_banner(self):
        audit = {"report_ready": False, "report_blocking_issues": [], "coverage": [], "structural": {}}
        bundle = build_report_input_bundle(
            research_spec=_SPEC,
            scope_bundle=_SCOPE,
            dataset_manifest=_MANIFEST,
            subquestions=_SUBQ,
            qc_reports=[],
            evidence_items=[],
            claims=[],
            alignment_audit=audit,
            allow_partial=True,
            terminal_reason="dataset unavailable — partial complete",
        )
        result = build_report(bundle)
        self.assertTrue(result.report_model["partial"])
        self.assertIn("dataset unavailable — partial complete", result.markdown)


class ManifestPinningTest(unittest.TestCase):
    """T-21-08 / T-21-11: manifest validates, pins every input, and is deterministic."""

    def test_manifest_validates_against_core_contract(self):
        result = build_report(_clean_bundle())
        self.assertEqual(validate_report_manifest(result.manifest), [])

    def test_manifest_pins_every_input_version(self):
        result = build_report(_clean_bundle())
        pins = result.manifest["input_version_pins"]
        self.assertEqual(pins["research_spec_id"], "spec_wp21")
        self.assertEqual(pins["dataset_manifest_id"], "dm_wp21")
        self.assertIn("qc_1", pins["qc_report_ids"])
        self.assertTrue(pins["claim_ids"])
        self.assertTrue(pins["evidence_item_ids"])
        self.assertIn("alignment_report_id", pins)

    def test_output_checksums_are_deterministic_and_cover_both_formats(self):
        first = build_report(_clean_bundle()).manifest["output_checksums"]
        second = build_report(_clean_bundle()).manifest["output_checksums"]
        self.assertEqual(first, second)
        self.assertIn("report.md", first)
        self.assertIn("report.json", first)

    def test_machine_json_is_byte_identical_across_rebuilds(self):
        a = json.dumps(build_report(_clean_bundle()).report_model, ensure_ascii=False, sort_keys=True, indent=2)
        b = json.dumps(build_report(_clean_bundle()).report_model, ensure_ascii=False, sort_keys=True, indent=2)
        self.assertEqual(a, b)


class ContentConsistencyTest(unittest.TestCase):
    """T-21-04 / T-21-05: markdown and JSON share claim ids; required sections present."""

    def test_markdown_tags_every_positive_claim_id(self):
        result = build_report(_clean_bundle())
        for claim in result.report_model["positive_results"]:
            self.assertIn(claim["claim_id"], result.markdown)

    def test_claim_index_mirrors_json_claim_ids(self):
        result = build_report(_clean_bundle())
        model_ids = {
            c["claim_id"]
            for section in ("positive_results", "negative_results", "conflicting_results", "inconclusive_results")
            for c in result.report_model[section]
        }
        self.assertTrue(model_ids)
        self.assertEqual(set(result.report_model["claim_index"]), model_ids)

    def test_all_required_result_sections_always_present(self):
        model = build_report(_clean_bundle()).report_model
        for section in REQUIRED_RESULT_SECTIONS:
            self.assertIn(section, model)
        for section in ("positive_results", "negative_results", "conflicting_results", "unanswered_questions", "failed_branches"):
            self.assertIn(section, model)

    def test_failed_branches_carry_non_admissible_markers(self):
        marker = {"non_admissible_result_id": "nar_1", "reason_code": "qc_fail"}
        result = build_report(_clean_bundle(non_admissible_markers=[marker]))
        self.assertEqual(result.report_model["failed_branches"], [marker])
        self.assertIn("nar_1", result.markdown)


class ClaimClassificationTest(unittest.TestCase):
    """T-21-02: claims route into the four bounded result buckets by status."""

    def _bucket_bundle(self, claims):
        # A partial bundle bypasses report-ready gating so classification can be tested directly.
        return build_report_input_bundle(
            research_spec=_SPEC,
            scope_bundle=_SCOPE,
            dataset_manifest=_MANIFEST,
            subquestions=_SUBQ,
            qc_reports=[],
            evidence_items=[],
            claims=claims,
            alignment_audit={"report_ready": False, "coverage": [], "structural": {}},
            allow_partial=True,
            terminal_reason="classification fixture",
        )

    def test_status_routes_claims_to_correct_bucket(self):
        claims = [
            {"claim_id": "c_pos", "status": "supports", "claim_level": "association", "text": "up", "evidence_item_refs": ["e"]},
            {"claim_id": "c_conf", "status": "conflicting", "claim_level": "association", "text": "mixed", "evidence_item_refs": ["e"]},
            {"claim_id": "c_inc", "status": "inconclusive", "claim_level": "association", "text": "unclear", "evidence_item_refs": ["e"]},
            {"claim_id": "c_neg", "status": "refutes", "claim_level": "association", "text": "down", "evidence_item_refs": ["e"]},
        ]
        model = build_report(self._bucket_bundle(claims)).report_model
        self.assertEqual([c["claim_id"] for c in model["positive_results"]], ["c_pos"])
        self.assertEqual([c["claim_id"] for c in model["conflicting_results"]], ["c_conf"])
        self.assertEqual([c["claim_id"] for c in model["inconclusive_results"]], ["c_inc"])
        self.assertEqual([c["claim_id"] for c in model["negative_results"]], ["c_neg"])


class CoverageMatrixTest(unittest.TestCase):
    """T-21-09: every sub-question appears in the coverage matrix."""

    def test_coverage_matrix_lists_every_subquestion(self):
        extra = _SUBQ + [{"subquestion_id": "subq_2", "claim_ceiling": "association"}]
        result = build_report(_clean_bundle(subquestions=extra))
        ids = {row["subquestion_id"] for row in result.coverage_matrix["rows"]}
        self.assertEqual(ids, {"subq_1", "subq_2"})
        self.assertEqual(result.coverage_matrix["n_subquestions"], 2)

    def test_uncovered_subquestion_defaults_to_unanswered(self):
        matrix = build_coverage_matrix([{"subquestion_id": "subq_x"}], coverage=[])
        self.assertEqual(matrix["rows"][0]["state"], "unanswered")


class TraceabilityGateTest(unittest.TestCase):
    """T-21-03 / T-21-07: untraceable claims and source-less figures block release."""

    def test_untraceable_claim_blocks_and_cannot_reach_released(self):
        _, claims, _, _ = _pipeline_objects()
        broken = dict(claims[0])
        broken["evidence_item_refs"] = ["missing_evidence_item"]
        result = build_report(_clean_bundle(claims=[broken], evidence_items=[]))
        self.assertFalse(result.publishable)
        self.assertTrue(any("untraceable" in r for r in result.blocking_reasons))
        reviewed = advance_report_status("DRAFT", "REVIEWED")
        with self.assertRaises(ValueError):
            advance_report_status(reviewed, "RELEASED", publishable=result.publishable)

    def test_figure_without_source_artifact_blocks_publishability(self):
        result = build_report(_clean_bundle(figures=[{"figure_id": "f1", "title": "Volcano", "source_artifact_id": "", "task_run_id": ""}]))
        self.assertFalse(result.publishable)
        self.assertTrue(any("source table" in r for r in result.blocking_reasons))

    def test_figure_without_task_run_lineage_blocks_publishability(self):
        result = build_report(_clean_bundle(figures=[{"figure_id": "f2", "title": "Heatmap", "source_artifact_id": "artifact_1", "task_run_id": ""}]))
        self.assertFalse(result.publishable)
        self.assertTrue(any("source table" in r for r in result.blocking_reasons))


class OverClaimLintTest(unittest.TestCase):
    """T-21-10: over-claim language is caught even when upstream alignment was clean."""

    def test_overclaim_language_blocks_despite_clean_audit(self):
        _, claims, _, _ = _pipeline_objects()
        loud = dict(claims[0])
        loud["text"] = "This gene causes tumor growth in every tissue"
        # _clean_bundle keeps the clean audit (report_ready) but swaps in the loud claim.
        result = build_report(_clean_bundle(claims=[loud]))
        self.assertFalse(result.publishable)
        self.assertTrue(any("over-claim" in r for r in result.blocking_reasons))
        self.assertTrue(result.lint["blocking"])

    def test_claim_sentence_without_claim_id_is_a_finding(self):
        _, claims, evidence, _ = _pipeline_objects()
        lint = lint_report_language(claims, evidence, claim_sentences={"unknown_claim": "An orphan sentence."})
        kinds = {f["kind"] for f in lint["findings"]}
        self.assertIn("claim_sentence_without_claim_id", kinds)
        self.assertTrue(lint["blocking"])
        self.assertIn("claim_sentence_without_claim_id", CLAIM_LINT_KINDS)

    def test_clean_claim_language_has_no_findings(self):
        _, claims, evidence, _ = _pipeline_objects()
        lint = lint_report_language(claims, evidence)
        self.assertEqual(lint["findings"], [])
        self.assertFalse(lint["blocking"])


class ReportStatusTransitionTest(unittest.TestCase):
    """T-21-12: the DRAFT → REVIEWED → RELEASED lifecycle is bounded and forward-only."""

    def test_forward_single_steps_allowed(self):
        self.assertEqual(advance_report_status("DRAFT", "REVIEWED"), "REVIEWED")
        self.assertEqual(advance_report_status("REVIEWED", "RELEASED"), "RELEASED")

    def test_illegal_skip_is_refused(self):
        with self.assertRaises(ValueError):
            advance_report_status("DRAFT", "RELEASED")

    def test_backward_transition_is_refused(self):
        with self.assertRaises(ValueError):
            advance_report_status("REVIEWED", "DRAFT")

    def test_unknown_status_is_refused(self):
        with self.assertRaises(ValueError):
            advance_report_status("DRAFT", "PUBLISHED")

    def test_unpublishable_release_is_refused(self):
        with self.assertRaises(ValueError):
            advance_report_status("REVIEWED", "RELEASED", publishable=False)


class TraceIndexCompletenessTest(unittest.TestCase):
    """T-21-03 / T-21-07: trace index chains claims to evidence→artifact→dataset."""

    def test_complete_chain_reaches_dataset(self):
        evidence, claims, artifacts, _ = _pipeline_objects()
        index = build_trace_index(claims, evidence, artifacts)
        self.assertTrue(index["complete"])
        self.assertFalse(has_untraceable_claim(index))
        chain = index["chains"][claims[0]["claim_id"]][0]
        self.assertEqual(chain["artifact_id"], "artifact_1")
        self.assertEqual(chain["dataset_ids"], ["dataset_wp21"])

    def test_missing_evidence_ref_is_a_gap(self):
        index = build_trace_index([{"claim_id": "c1", "evidence_item_refs": ["e_missing"]}], evidence_items=[], artifact_manifests=[])
        self.assertFalse(index["complete"])
        self.assertTrue(has_untraceable_claim(index))

    def test_incomplete_figure_source_list_is_marked_incomplete(self):
        figure_list = build_figure_list(
            [{"figure_id": "f1", "source_artifact_id": "nope", "task_run_id": "tr_1"}],
            artifact_manifests=[{"artifact_id": "artifact_1"}],
        )
        self.assertFalse(figure_list["complete"])
        self.assertEqual(figure_list["gaps"][0]["figure_id"], "f1")

    def test_method_trace_table_links_subquestion_contract_and_run(self):
        table = build_method_trace_table(
            _SUBQ,
            method_contracts=[{"method_contract_id": "mc_1", "supports_subquestion_ids": ["subq_1"]}],
            task_runs=[{"task_run_id": "tr_1", "method_contract_id": "mc_1"}],
        )
        row = table["rows"][0]
        self.assertEqual(row["subquestion_id"], "subq_1")
        self.assertEqual(row["method_contract_ids"], ["mc_1"])
        self.assertEqual(row["task_run_ids"], ["tr_1"])


if __name__ == "__main__":
    unittest.main()
