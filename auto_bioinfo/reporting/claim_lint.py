"""Report-language claim lint (WP-21, T-21-10).

The final defence against a report that *reads* stronger than its evidence: a
language-layer lint over the rendered claim sentences that flags causal words,
universalising words, and protein/secretion words that conflict with the claim's
level.  It reuses the WP-20 over-claim pattern detector
(:func:`auto_bioinfo.evidence.question_alignment.detect_overclaims`) so the report
layer and the alignment audit stay in lock-step, and adds report-specific findings
(a claim sentence that names no claim id).  An over-claim lint finding blocks a
formal report.

Pure, offline, deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..evidence.question_alignment import detect_overclaims

# The bounded lint-finding kinds (the over-claim kinds plus a report-only one).
CLAIM_LINT_KINDS = (
    "rna_to_protein_or_secretion",
    "correlation_to_causation",
    "single_cohort_to_universal",
    "annotation_to_experimental",
    "claim_sentence_without_claim_id",
)


def lint_report_language(
    claims: Sequence[Mapping[str, Any]],
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    claim_sentences: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Lint the report's claim language for over-claim leaps (T-21-10).

    Runs the shared over-claim detector over the claim text (and any rendered
    ``claim_sentences`` keyed by claim id) and returns
    ``{"findings": [...], "blocking": bool}``.  A finding blocks a formal report: an
    over-claim sentence must be corrected before release.  A rendered claim sentence
    whose key does not correspond to a known claim id is itself a finding (a report
    sentence must map one-to-one to a Claim).
    """
    lint_targets = [dict(c) for c in claims]
    known_ids = {str(c.get("claim_id", "")) for c in claims}
    # Fold rendered sentences into the lint targets so the prose is checked too.
    if claim_sentences:
        by_id = {str(c.get("claim_id", "")): dict(c) for c in claims}
        merged: list[dict[str, Any]] = []
        extra_findings: list[dict[str, Any]] = []
        for claim_id, sentence in claim_sentences.items():
            base = dict(by_id.get(claim_id, {"claim_id": claim_id, "evidence_item_refs": []}))
            base["text"] = sentence
            merged.append(base)
            if claim_id not in known_ids:
                extra_findings.append(
                    {"kind": "claim_sentence_without_claim_id", "claim_id": claim_id, "reason": "rendered claim sentence has no matching Claim id"}
                )
        lint_targets = merged
    else:
        extra_findings = []

    overclaims = detect_overclaims(lint_targets, evidence_items)
    findings = [{"kind": c["kind"], "claim_id": c["claim_id"], "offending_terms": c["offending_terms"], "reason": c["reason"]} for c in overclaims]
    findings.extend(extra_findings)
    return {"findings": findings, "blocking": bool(findings)}


__all__ = ["CLAIM_LINT_KINDS", "lint_report_language"]
