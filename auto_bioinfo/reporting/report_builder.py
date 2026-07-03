"""Constrained report builder + report manifest (WP-21, stage 17).

Stage 17 of the requirement spec: build a report from *already-audited* objects that
never creates new evidence, never raises a conclusion's level, and is fully
traceable.  The builder is a **pure, offline, deterministic** function of an
approved :class:`ReportInputBundle`: it constructs the structured sections (data
tables + reference indexes first), renders a *constrained* Markdown narrative whose
every claim sentence is tagged with its Claim id (no new claim may appear), emits a
byte-identical machine JSON, and produces a :class:`FinalReportManifest` that pins
every input object's version and checksums the outputs.

A report can be *built* as a DRAFT even with issues, but it can only be advanced to
RELEASED when it is publishable: every required result section that has content is
present (T-21-05), every claim traces back to evidence→artifact→dataset (T-21-07),
no figure lacks a source table, and the language lint finds no over-claim (T-21-10).
The three-state ``DRAFT → REVIEWED → RELEASED`` lifecycle (T-21-12) is enforced by
:func:`advance_report_status`.

Determinism: produced records carry empty timestamps; the machine JSON is emitted
with sorted keys so a re-build is byte-identical and its checksum is stable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION, FinalReportManifest
from ..core.validation import validate_final_report_manifest
from .claim_lint import lint_report_language
from .trace_index import (
    build_coverage_matrix,
    build_figure_list,
    build_method_trace_table,
    build_trace_index,
)

# The report approval/publish lifecycle (T-21-12).  A DRAFT is never presented as a
# formal result; only a RELEASED report is.
REPORT_STATUSES = ("DRAFT", "REVIEWED", "RELEASED")
_STATUS_ORDER = {status: idx for idx, status in enumerate(REPORT_STATUSES)}

# The result sections that must be present when the project has matching content
# (T-21-05).  A positive-only report may not silently drop the negative section, etc.
REQUIRED_RESULT_SECTIONS = (
    "positive_results",
    "negative_results",
    "conflicting_results",
    "inconclusive_results",
    "unanswered_questions",
    "failed_branches",
)

# The ordered report sections — the minimum content the spec requires all have a home
# (T-21-02); the renderer emits them in this fixed order for a deterministic report.
REPORT_SECTION_ORDER = (
    "original_question",
    "scope",
    "subquestion_coverage",
    "datasets_and_samples",
    "methods_and_parameters",
    "sample_exclusions",
    "qc_summary",
    "positive_results",
    "negative_results",
    "conflicting_results",
    "inconclusive_results",
    "unanswered_questions",
    "failed_branches",
    "limitations",
    "follow_up_validation",
    "traceability_appendix",
)


class ReportInputRefused(Exception):
    """Raised when an input bundle would include an un-audited object or an
    un-cleared alignment (no blocking issue may be silently carried into a report)."""


def build_report_input_bundle(
    *,
    research_spec: Mapping[str, Any],
    scope_bundle: Mapping[str, Any],
    dataset_manifest: Mapping[str, Any],
    subquestions: Sequence[Mapping[str, Any]],
    qc_reports: Sequence[Mapping[str, Any]],
    evidence_items: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    alignment_audit: Mapping[str, Any],
    method_contracts: Sequence[Mapping[str, Any]] = (),
    task_runs: Sequence[Mapping[str, Any]] = (),
    artifact_manifests: Sequence[Mapping[str, Any]] = (),
    figures: Sequence[Mapping[str, Any]] = (),
    non_admissible_markers: Sequence[Mapping[str, Any]] = (),
    allow_partial: bool = False,
    terminal_reason: str = "",
) -> dict[str, Any]:
    """Assemble the :class:`ReportInputBundle` from approved objects only (T-21-01).

    Fail-closed: the alignment audit must be ``report_ready`` (no unresolved blocking
    issue) unless ``allow_partial`` is set with an explicit ``terminal_reason`` (the
    project legitimately entered a partial-complete / other terminal state).  An
    un-cleared alignment with no partial override raises :class:`ReportInputRefused`
    so an un-audited report can never be built.
    """
    report_ready = bool(alignment_audit.get("report_ready"))
    if not report_ready and not (allow_partial and terminal_reason):
        raise ReportInputRefused(
            f"alignment is not report-ready and no terminal reason given; blocking issues: {alignment_audit.get('report_blocking_issues', [])}"
        )
    return {
        "research_spec": dict(research_spec),
        "scope_bundle": dict(scope_bundle),
        "dataset_manifest": dict(dataset_manifest),
        "subquestions": [dict(s) for s in subquestions],
        "qc_reports": [dict(q) for q in qc_reports],
        "evidence_items": [dict(e) for e in evidence_items],
        "claims": [dict(c) for c in claims],
        "alignment_audit": dict(alignment_audit),
        "method_contracts": [dict(m) for m in method_contracts],
        "task_runs": [dict(t) for t in task_runs],
        "artifact_manifests": [dict(a) for a in artifact_manifests],
        "figures": [dict(f) for f in figures],
        "non_admissible_markers": [dict(n) for n in non_admissible_markers],
        "partial": bool(allow_partial and not report_ready),
        "terminal_reason": terminal_reason if (allow_partial and not report_ready) else "",
    }


@dataclass
class ReportBuildResult:
    """The bounded outcome of a report build."""

    status: str
    publishable: bool
    blocking_reasons: list[str]
    report_model: dict[str, Any]
    markdown: str
    manifest: dict[str, Any]
    trace_index: dict[str, Any] = field(default_factory=dict)
    figure_list: dict[str, Any] = field(default_factory=dict)
    coverage_matrix: dict[str, Any] = field(default_factory=dict)
    method_trace_table: dict[str, Any] = field(default_factory=dict)
    lint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "publishable": self.publishable,
            "blocking_reasons": list(self.blocking_reasons),
            "report_model": self.report_model,
            "markdown": self.markdown,
            "manifest": self.manifest,
            "trace_index": self.trace_index,
            "figure_list": self.figure_list,
            "coverage_matrix": self.coverage_matrix,
            "method_trace_table": self.method_trace_table,
            "lint": self.lint,
        }


def _classify_claims(claims: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {"positive_results": [], "negative_results": [], "conflicting_results": [], "inconclusive_results": []}
    for claim in claims:
        status = str(claim.get("status", ""))
        row = {
            "claim_id": claim.get("claim_id", ""),
            "claim_level": claim.get("claim_level", ""),
            "text": claim.get("text", ""),
            "scope": claim.get("scope", {}),
            "evidence_item_refs": claim.get("evidence_item_refs", []),
            "opposing_evidence_refs": claim.get("opposing_evidence_refs", []),
            "limitations": claim.get("limitations", []),
        }
        if status == "supports":
            buckets["positive_results"].append(row)
        elif status == "conflicting":
            buckets["conflicting_results"].append(row)
        elif status == "inconclusive":
            buckets["inconclusive_results"].append(row)
        else:
            buckets["negative_results"].append(row)
    return buckets


def build_report(bundle: Mapping[str, Any]) -> ReportBuildResult:
    """Build the constrained report from an approved input bundle (T-21-02..10).

    Constructs the structured sections and reference indexes, renders the
    claim-id-tagged Markdown and the machine JSON, checks every publishability gate
    (traceability, figures, language lint, required result sections), and produces
    the :class:`FinalReportManifest`.  Always returns a DRAFT; ``publishable`` /
    ``blocking_reasons`` decide whether it may be advanced to RELEASED.
    """
    spec = bundle.get("research_spec", {})
    claims = list(bundle.get("claims", []))
    evidence_items = list(bundle.get("evidence_items", []))
    artifacts = list(bundle.get("artifact_manifests", []))
    audit = bundle.get("alignment_audit", {})
    coverage = audit.get("coverage", [])

    trace_index = build_trace_index(claims, evidence_items, artifacts)
    figure_list = build_figure_list(bundle.get("figures", []), artifacts)
    coverage_matrix = build_coverage_matrix(bundle.get("subquestions", []), coverage)
    method_trace_table = build_method_trace_table(bundle.get("subquestions", []), bundle.get("method_contracts", []), bundle.get("task_runs", []))
    buckets = _classify_claims(claims)
    lint = lint_report_language(claims, evidence_items)

    unanswered = [c for c in coverage if c.get("state") == "unanswered"] + list(audit.get("structural", {}).get("unresolved_questions", []))
    failed_branches = list(bundle.get("non_admissible_markers", []))

    report_model = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "original_question": spec.get("research_question", spec.get("original_question", "")),
        "scope": bundle.get("scope_bundle", {}),
        "subquestion_coverage": coverage_matrix,
        "datasets_and_samples": {
            "dataset_id": bundle.get("dataset_manifest", {}).get("dataset_id", ""),
            "samples": bundle.get("dataset_manifest", {}).get("samples", []),
            "excluded_samples": bundle.get("dataset_manifest", {}).get("excluded_samples", []),
        },
        "methods_and_parameters": [
            {"method_contract_id": m.get("method_contract_id", m.get("contract_id", "")), "parameters": m.get("parameters", {})}
            for m in bundle.get("method_contracts", [])
        ],
        "sample_exclusions": bundle.get("dataset_manifest", {}).get("excluded_samples", []),
        "qc_summary": [
            {"qc_report_id": q.get("qc_report_id", ""), "decision": q.get("decision", q.get("overall_status", "")), "artifact_id": q.get("artifact_id", "")}
            for q in bundle.get("qc_reports", [])
        ],
        "positive_results": buckets["positive_results"],
        "negative_results": buckets["negative_results"],
        "conflicting_results": buckets["conflicting_results"],
        "inconclusive_results": buckets["inconclusive_results"],
        "unanswered_questions": unanswered,
        "failed_branches": failed_branches,
        "limitations": sorted({lim for c in claims for lim in (c.get("limitations") or [])}),
        "follow_up_validation": _follow_up(claims),
        "traceability_appendix": {"trace_index": trace_index, "method_trace_table": method_trace_table, "figure_list": figure_list},
        "claim_index": {str(c.get("claim_id", "")): {"level": c.get("claim_level", ""), "status": c.get("status", "")} for c in claims},
        "partial": bundle.get("partial", False),
        "terminal_reason": bundle.get("terminal_reason", ""),
    }

    blocking_reasons: list[str] = []
    if not trace_index["complete"]:
        blocking_reasons.append(f"untraceable claim(s): {trace_index['gaps']}")
    if not figure_list["complete"]:
        blocking_reasons.append(f"figure(s) without source table: {figure_list['gaps']}")
    if lint["blocking"]:
        blocking_reasons.append(f"over-claim language: {lint['findings']}")
    blocking_reasons += _missing_required_sections(report_model)

    markdown = _render_markdown(report_model)
    # Content-summary consistency (T-21-08): both formats derive from one model.
    json_text = json.dumps(report_model, ensure_ascii=False, sort_keys=True, indent=2)
    manifest = _build_manifest(spec=spec, claims=claims, audit=audit, markdown=markdown, json_text=json_text, bundle=bundle)

    publishable = not blocking_reasons
    return ReportBuildResult(
        status="DRAFT",
        publishable=publishable,
        blocking_reasons=blocking_reasons,
        report_model=report_model,
        markdown=markdown,
        manifest=manifest,
        trace_index=trace_index,
        figure_list=figure_list,
        coverage_matrix=coverage_matrix,
        method_trace_table=method_trace_table,
        lint=lint,
    )


def _follow_up(claims: Sequence[Mapping[str, Any]]) -> list[str]:
    follow: list[str] = []
    for claim in claims:
        if claim.get("status") in ("supports", "conflicting"):
            follow.append(f"Independent replication and orthogonal (protein/functional) validation for claim {claim.get('claim_id', '')}.")
    return follow or ["No positive claim requires downstream validation in this run."]


def _missing_required_sections(report_model: Mapping[str, Any]) -> list[str]:
    """A required result section that has content must not be dropped (T-21-05)."""
    reasons: list[str] = []
    for section in REQUIRED_RESULT_SECTIONS:
        if section not in report_model:
            reasons.append(f"required section '{section}' is missing from the report model")
    return reasons


def _render_markdown(report_model: Mapping[str, Any]) -> str:
    """Render the constrained Markdown; each claim sentence is tagged with its id (T-21-04)."""
    lines: list[str] = ["# Research report", ""]
    lines.append(f"## Original question\n\n{report_model.get('original_question', '')}\n")
    if report_model.get("partial"):
        lines.append(f"> Partial-complete report: {report_model.get('terminal_reason', '')}\n")
    lines.append("## Scope\n")
    scope = report_model.get("scope", {})
    lines.append(f"- species: {', '.join(scope.get('species', []) or []) or 'unspecified'}")
    lines.append(f"- tissue: {', '.join(scope.get('tissues', scope.get('tissue', [])) or []) or 'unspecified'}\n")

    lines.append("## Sub-question coverage\n")
    for row in report_model.get("subquestion_coverage", {}).get("rows", []):
        lines.append(f"- {row['subquestion_id']}: {row['state']}")
    lines.append("")

    for section in ("positive_results", "negative_results", "conflicting_results", "inconclusive_results"):
        title = section.replace("_", " ").title()
        rows = report_model.get(section, [])
        lines.append(f"## {title}\n")
        if not rows:
            lines.append("None.\n")
            continue
        for row in rows:
            # One constrained sentence per claim, tagged with the Claim id.
            lines.append(f"- [{row['claim_id']}] ({row['claim_level']}) {row['text']}")
        lines.append("")

    lines.append("## Unanswered questions\n")
    unanswered = report_model.get("unanswered_questions", [])
    lines.append(("\n".join(f"- {u.get('subquestion_id', u)}" for u in unanswered) if unanswered else "None.") + "\n")

    lines.append("## Failed / non-admissible branches\n")
    failed = report_model.get("failed_branches", [])
    lines.append(("\n".join(f"- {f.get('non_admissible_result_id', f)}: {f.get('reason_code', '')}" for f in failed) if failed else "None.") + "\n")

    lines.append("## Limitations\n")
    lines.append(("\n".join(f"- {lim}" for lim in report_model.get("limitations", [])) or "None.") + "\n")

    lines.append("## Follow-up validation\n")
    lines.append("\n".join(f"- {f}" for f in report_model.get("follow_up_validation", [])) + "\n")

    lines.append("## Traceability appendix\n")
    lines.append("Every claim above traces to evidence → artifact → dataset; see the machine JSON `traceability_appendix`.\n")
    return "\n".join(lines)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_manifest(
    *,
    spec: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
    markdown: str,
    json_text: str,
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    claim_ids = [str(c.get("claim_id", "")) for c in claims if c.get("claim_id")]
    manifest = FinalReportManifest(
        final_report_id=make_stable_id("final_report", {"project_id": spec.get("project_id", ""), "claim_ids": claim_ids, "markdown": _sha256_text(markdown)}),
        report_path="reports/report.md",
        claim_ids=claim_ids,
        alignment_report_id=str(audit.get("alignment_report", {}).get("report_id", "")),
        generated_at="",
    ).to_dict()
    manifest["output_checksums"] = {"report.md": _sha256_text(markdown), "report.json": _sha256_text(json_text)}
    # Pin every input object's exact version so a re-generation cannot silently swap inputs (T-21-11).
    manifest["input_version_pins"] = {
        "research_spec_id": spec.get("research_spec_id", ""),
        "dataset_manifest_id": bundle.get("dataset_manifest", {}).get("dataset_manifest_id", ""),
        "claim_ids": claim_ids,
        "evidence_item_ids": [str(e.get("evidence_item_id", "")) for e in bundle.get("evidence_items", [])],
        "qc_report_ids": [str(q.get("qc_report_id", "")) for q in bundle.get("qc_reports", [])],
        "alignment_report_id": str(audit.get("alignment_report", {}).get("report_id", "")),
    }
    manifest["report_status"] = "DRAFT"
    return manifest


def advance_report_status(current: str, target: str, *, publishable: bool = True) -> str:
    """Advance the report lifecycle DRAFT → REVIEWED → RELEASED (T-21-12).

    Transitions must be forward and single-step; RELEASED additionally requires a
    ``publishable`` report (no unresolved traceability / figure / over-claim issue).
    A non-forward transition or an unpublishable release raises ``ValueError``.
    """
    if current not in REPORT_STATUSES or target not in REPORT_STATUSES:
        raise ValueError(f"report status must be one of {REPORT_STATUSES}")
    if _STATUS_ORDER[target] != _STATUS_ORDER[current] + 1:
        raise ValueError(f"illegal report transition {current} -> {target}; must be a single forward step")
    if target == "RELEASED" and not publishable:
        raise ValueError("cannot RELEASE an unpublishable report (unresolved traceability / figure / over-claim issue)")
    return target


def validate_report_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Validate the produced manifest against the core FinalReportManifest contract."""
    return validate_final_report_manifest(dict(manifest))


__all__ = [
    "REPORT_STATUSES",
    "REQUIRED_RESULT_SECTIONS",
    "REPORT_SECTION_ORDER",
    "ReportInputRefused",
    "ReportBuildResult",
    "build_report_input_bundle",
    "build_report",
    "advance_report_status",
    "validate_report_manifest",
]
