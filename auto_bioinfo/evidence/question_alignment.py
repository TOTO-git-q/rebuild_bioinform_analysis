"""Original-question alignment & over-claim audit (WP-20, stage 16).

Stage 16 of the requirement spec: after claims are synthesised, check that they
still answer the *original* question and never over-reach the evidence.  This module
reuses the structural auditor
:func:`auto_bioinfo.core.alignment_auditor.audit_question_alignment` (coverage,
scope fidelity, unsupported claims, ceiling violations, omitted negatives) and
layers on the **language-level over-claim audit** the spec calls out (T-20-13):
RNA→protein/secretion, correlation→causation, single-cohort→universal, and
annotation→experimental leaps are each caught by a bounded pattern set and turned
into a :data:`ClaimCorrection`.  The omission audit (T-20-14) keeps dropped negative
evidence, failed branches and unanswered sub-questions visible, and the result is an
immutable :class:`~auto_bioinfo.core.schemas.QuestionAlignmentReport` plus the
``ClaimCorrection`` / ``ReportBlockingIssue`` records (T-20-15).  ``report_ready`` is
true only when no blocking issue remains.

``ClaimCorrection`` and ``ReportBlockingIssue`` are not defined in
``core/schemas.py``; they are recorded here as bounded lane dicts (see the WO report).
Everything is pure, offline and deterministic; produced records carry empty
timestamps.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from ..core.alignment_auditor import audit_question_alignment
from ..core.ids import make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION, CLAIM_LEVELS, QuestionAlignmentReport
from ..core.validation import validate_question_alignment_report

# --- Bounded vocabularies ----------------------------------------------------
# The four-state per-sub-question coverage verdict (T-20-10).
COVERAGE_STATES = ("answered", "answered_negative", "unresolved", "unanswered")

# The bounded over-claim kinds the language audit detects (T-20-13).
OVERCLAIM_KINDS = (
    "rna_to_protein_or_secretion",
    "correlation_to_causation",
    "single_cohort_to_universal",
    "annotation_to_experimental",
)

# The bounded blocking-issue kinds a report must clear before REPORT_READY (T-20-15).
BLOCKING_ISSUE_KINDS = (
    "overclaim",
    "scope_drift",
    "traceability_gap",
    "unsupported_claim",
    "omitted_negative_evidence",
    "unanswered_subquestion",
)

# Language patterns that assert more than RNA-association evidence can support.  Each
# maps to an over-claim kind, the claim level the language *implies*, and the
# evidence type the leap would require.  Matched case-insensitively on word bounds.
_OVERCLAIM_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        r"\b(secreted|secretion|secretome|protein level|protein abundance|surface protein|cell.surface)\b",
        "rna_to_protein_or_secretion",
        "candidate_biomarker",
        "protein",
    ),
    (r"\b(causes?|causal|causally|drives?|induces?|leads? to|results? in|responsible for)\b", "correlation_to_causation", "causal_support", "intervention"),
    (r"\b(universal(ly)?|in all|across all|in every|generally|always|any tissue)\b", "single_cohort_to_universal", "association", "replicated"),
    (
        r"\b(validated target|experimentally (confirmed|validated)|knockout confirmed|knockdown confirmed)\b",
        "annotation_to_experimental",
        "experimentally_validated_target",
        "experimental_validation",
    ),
)


def _level_index(level: str) -> int:
    return CLAIM_LEVELS.index(level) if level in CLAIM_LEVELS else 0


def detect_overclaims(claims: Sequence[Mapping[str, Any]], evidence_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Detect language-level over-claims and emit ClaimCorrections (T-20-13).

    A claim whose *text* uses causal / protein-secretion / universalising /
    experimental-validation language that its level or backing evidence types cannot
    support yields a bounded ``ClaimCorrection`` (never silently rewritten): the
    offending terms, the implied vs actual level, and the corrective action.
    """
    ev_types_by_id = {str(ev.get("evidence_item_id", "")): str(ev.get("evidence_type", "")).lower() for ev in evidence_items}
    corrections: list[dict[str, Any]] = []
    for claim in claims:
        text = str(claim.get("text", "")).lower()
        level = str(claim.get("claim_level", ""))
        backing_types = {ev_types_by_id.get(i, "") for i in (claim.get("evidence_item_refs") or [])}
        for pattern, kind, implied_level, required_type in _OVERCLAIM_PATTERNS:
            match = re.search(pattern, text)
            if not match:
                continue
            has_required = any(required_type in t for t in backing_types)
            level_ok = _level_index(level) >= _level_index(implied_level)
            if has_required and level_ok:
                continue
            corrections.append(
                {
                    "schema_version": CANONICAL_SCHEMA_VERSION,
                    "record_type": "ClaimCorrection",
                    "claim_correction_id": make_stable_id("claim_correction", {"claim_id": claim.get("claim_id", ""), "kind": kind}),
                    "claim_id": claim.get("claim_id", ""),
                    "kind": kind,
                    "offending_terms": [match.group(0)],
                    "implied_level": implied_level,
                    "actual_level": level,
                    "required_evidence_type": required_type,
                    "reason": f"claim language implies {kind} but backing evidence/level cannot support it",
                    "recommended_action": "lower_claim_level_or_reword_to_association",
                    "created_at": "",
                    "status": "open",
                }
            )
    return corrections


def _coverage_four_state(subquestions: Sequence[Mapping[str, Any]], claims: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Four-state coverage per sub-question (T-20-10): never drop an unanswered item."""
    out: list[dict[str, Any]] = []
    for sq in subquestions:
        sq_id = str(sq.get("subquestion_id", ""))
        supporting = [c for c in claims if sq_id in (c.get("supports_subquestion_ids") or [])]
        if supporting and any(c.get("status") in ("supports", "conflicting") for c in supporting):
            state = "answered"
        elif supporting:  # only null_result / inconclusive claims
            state = "answered_negative"
        elif sq.get("unresolved_reason"):
            state = "unresolved"
        else:
            state = "unanswered"
        out.append({"subquestion_id": sq_id, "state": state, "supporting_claim_ids": [c.get("claim_id") for c in supporting]})
    return out


def _blocking_issue(kind: str, reason: str, ref: str = "") -> dict[str, Any]:
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "record_type": "ReportBlockingIssue",
        "report_blocking_issue_id": make_stable_id("report_blocking_issue", {"kind": kind, "ref": ref, "reason": reason}),
        "kind": kind,
        "ref": ref,
        "reason": reason,
        "created_at": "",
        "status": "open",
    }


def audit_alignment(
    *,
    research_spec: Mapping[str, Any],
    subquestions: Sequence[Mapping[str, Any]],
    scope_bundle: Mapping[str, Any],
    evidence_items: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    artifact_manifests: Sequence[Mapping[str, Any]],
    qc_reports: Sequence[Mapping[str, Any]],
    project_ceiling: str | None = None,
) -> dict[str, Any]:
    """Run the full alignment + over-claim + omission audit (T-20-10..15).

    Returns a bounded audit result: an immutable
    :class:`QuestionAlignmentReport` (which validates against
    :func:`auto_bioinfo.core.validation.validate_question_alignment_report`), the
    four-state ``coverage``, the ``claim_corrections`` (over-claims), the
    ``report_blocking_issues``, and ``report_ready`` (true only when no blocking
    issue remains).  The structural checks reuse the core alignment auditor; the
    language over-claim audit and the blocking-issue synthesis are layered here.
    """
    ceiling = project_ceiling or research_spec.get("max_claim_level") or "association"
    structural = audit_question_alignment(
        research_spec=dict(research_spec),
        subquestions=[dict(s) for s in subquestions],
        scope_bundle=dict(scope_bundle),
        evidence_item_refs=[dict(e) for e in evidence_items],
        claims=[dict(c) for c in claims],
        artifact_manifests=[dict(a) for a in artifact_manifests],
        qc_reports=[dict(q) for q in qc_reports],
        max_claim_level=ceiling,
    )
    corrections = detect_overclaims(claims, evidence_items)
    coverage = _coverage_four_state(subquestions, claims)

    # Assemble the bounded blocking issues from every source.
    blocking: list[dict[str, Any]] = []
    for correction in corrections:
        blocking.append(_blocking_issue("overclaim", correction["reason"], correction["claim_id"]))
    for item in structural.get("scope_fidelity", []):
        if item.get("status") == "drift":
            blocking.append(_blocking_issue("scope_drift", "claim scope drifts outside the requested scope", item.get("claim_id", "")))
    for item in structural.get("unsupported_claims", []):
        blocking.append(_blocking_issue("unsupported_claim", item.get("reason", "unsupported claim"), item.get("claim_id", "")))
    for item in structural.get("claim_ceiling_violations", []):
        blocking.append(_blocking_issue("overclaim", item.get("reason", "claim exceeds ceiling"), item.get("claim_id", "")))
    for item in structural.get("omitted_negative_or_failed_evidence", []):
        blocking.append(_blocking_issue("omitted_negative_evidence", item.get("reason", "omitted negative evidence"), item.get("evidence_item_id", "")))
    for entry in coverage:
        if entry["state"] == "unanswered":
            blocking.append(
                _blocking_issue("unanswered_subquestion", "sub-question has no admitted evidence and no recorded unresolved reason", entry["subquestion_id"])
            )

    # Build the QuestionAlignmentReport.  A passing 'approve' may not stand while any
    # finding remains, so the decision fails closed to reject/needs_review.
    scope_drift = [i for i in structural.get("scope_fidelity", []) if i.get("status") == "drift"]
    overclaim_findings = corrections + list(structural.get("claim_ceiling_violations", []))
    traceability_gaps = [i for i in structural.get("unsupported_claims", []) if "evidence" in str(i.get("reason", "")).lower()]
    unsupported = sorted({str(i.get("claim_id", "")) for i in structural.get("unsupported_claims", []) if i.get("claim_id")})
    omitted = list(structural.get("omitted_negative_or_failed_evidence", []))

    if blocking or unsupported or overclaim_findings or scope_drift or traceability_gaps:
        decision = "reject"
    elif any(e["state"] in ("unresolved",) for e in coverage) or omitted or structural.get("unresolved_questions"):
        decision = "needs_review"
    else:
        decision = "approve"

    report = QuestionAlignmentReport(
        report_id=make_stable_id(
            "question_alignment_report",
            {"project_id": research_spec.get("project_id", ""), "decision": decision, "claims": [c.get("claim_id") for c in claims]},
        ),
        final_decision=decision,
        unsupported_claims=unsupported,
        research_spec_id=str(research_spec.get("research_spec_id", "")),
        project_id=str(research_spec.get("project_id", "")),
        scope_drift_findings=scope_drift,
        overclaim_findings=overclaim_findings,
        omitted_evidence=omitted,
        traceability_gaps=traceability_gaps,
        blocker_facts=sorted({b["reason"] for b in blocking}),
        generated_at="",
    )
    report_dict = report.to_dict()
    errors = validate_question_alignment_report(report_dict)
    if errors:
        raise ValueError(f"assembled alignment report is invalid: {'; '.join(errors)}")

    return {
        "alignment_report": report_dict,
        "coverage": coverage,
        "claim_corrections": corrections,
        "report_blocking_issues": blocking,
        "report_ready": not blocking,
        "structural": structural,
    }


__all__ = [
    "COVERAGE_STATES",
    "OVERCLAIM_KINDS",
    "BLOCKING_ISSUE_KINDS",
    "detect_overclaims",
    "audit_alignment",
]
