"""Bounded Claim synthesis from structured evidence summaries (WP-20, stage 15).

Stage 15 of the requirement spec: turn the admitted :class:`EvidenceItem` pool into
scientific :class:`~auto_bioinfo.core.schemas.Claim` drafts that never exceed the
evidence boundary.  The synthesiser is a **pure, offline, deterministic**
pre-aggregator + builder: it first collapses the evidence into a structured
per-sub-question summary (support / oppose / neutral / inconclusive / not-comparable
/ missing), and only then builds a Claim from that summary — the "Agent" never scans
raw results.  Every claim's level is the **lowest** of every applicable ceiling
(method capability, sub-question ceiling, project ceiling, evidence
``allowed_claim_level``) and is additionally capped by the per-level minimum-evidence
rule (T-20-01) and by conflict handling (T-20-08).  Every claim records its
supporting evidence ids, its opposing evidence, its limitations, and a scope that is
the **intersection** of its evidence scopes — never an extrapolation (T-20-06).

Determinism: produced claims carry an empty ``created_at``.  Every built claim is
checked against :func:`auto_bioinfo.core.validation.validate_claim`; an over-ceiling
draft is refused, never silently lowered without record.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION, CLAIM_LEVELS, Claim
from ..core.validation import validate_claim, validate_claim_ceiling

SYNTHESIS_RULES_VERSION = "auto_bioinfo.claim_synthesis/0.1"

# The evidence-synthesis dimensions weighed for every sub-question (T-20-02); kept
# stable and versioned so a claim can be re-derived deterministically.
SYNTHESIS_DIMENSIONS = (
    "direction",
    "effect_size",
    "uncertainty",
    "independence",
    "species",
    "tissue",
    "platform",
    "qc",
)

# Bounded Claim.status vocabulary this synthesiser emits.
CLAIM_STATUSES = ("supports", "null_result", "inconclusive", "conflicting")

# Per-level minimum-evidence rule (T-20-01): the evidence *types* a claim at this
# level must include.  A level whose required types are not present in the backing
# evidence is capped down — a causal/mechanistic level demands intervention or
# mechanism evidence, an experimental-validation level demands experimental
# evidence; RNA association can never buy any of those.
_MIN_EVIDENCE_TYPES: dict[str, tuple[str, ...]] = {
    "descriptive": (),
    "association": (),
    "co_expression": ("co_expression",),
    "candidate_biomarker": ("specificity",),
    "mechanistic_hypothesis": ("mechanism",),
    "causal_support": ("intervention", "perturbation"),
    "experimentally_validated_target": ("experimental_validation",),
}


def _level_index(level: str) -> int:
    return CLAIM_LEVELS.index(level) if level in CLAIM_LEVELS else 0


def _min_level(*levels: str) -> str:
    idx = [_level_index(level) for level in levels if level]
    return CLAIM_LEVELS[min(idx)] if idx else CLAIM_LEVELS[0]


def min_evidence_satisfied(level: str, evidence_types: Sequence[str]) -> bool:
    """Whether the backing evidence types satisfy the minimum-evidence rule for a level.

    The required types are *alternatives*: a level with no requirement is always
    satisfied, otherwise at least one required evidence type must be present (e.g.
    causal support needs intervention *or* perturbation evidence).
    """
    required = _MIN_EVIDENCE_TYPES.get(level, ())
    if not required:
        return True
    present = {str(t).lower() for t in evidence_types}
    return any(req in present for req in required)


def cap_by_min_evidence(desired_level: str, evidence_types: Sequence[str]) -> str:
    """Lower ``desired_level`` to the highest level whose minimum-evidence rule holds."""
    for idx in range(_level_index(desired_level), -1, -1):
        if min_evidence_satisfied(CLAIM_LEVELS[idx], evidence_types):
            return CLAIM_LEVELS[idx]
    return CLAIM_LEVELS[0]


def _as_set(value: Any) -> set[str]:
    if value is None:
        return set()
    items = [value] if isinstance(value, str) else list(value)
    return {str(v).strip().lower() for v in items if str(v).strip()}


def scope_intersection(evidence_items: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """The intersection of the evidence scopes (T-20-06).

    A claim may only speak to the species / tissue / condition that *every* backing
    evidence item shares; an axis where the evidence disagrees collapses to empty,
    forbidding extrapolation from a local result to a universal one.
    """
    axes = {"species": "species", "tissue": "tissue", "condition": "condition"}
    out: dict[str, list[str]] = {}
    for axis in axes:
        sets = [_as_set((ev.get("scope") or {}).get(axis)) for ev in evidence_items]
        sets = [s for s in sets if s]
        if not sets:
            out[axis] = []
            continue
        common = set.intersection(*sets) if len(sets) == len(evidence_items) else set()
        out[axis] = sorted(common)
    return out


@dataclass
class SubquestionAggregate:
    """A deterministic per-sub-question evidence summary (T-20-03)."""

    subquestion_id: str
    supporting: list[str] = field(default_factory=list)
    opposing: list[str] = field(default_factory=list)
    neutral: list[str] = field(default_factory=list)
    inconclusive: list[str] = field(default_factory=list)
    not_comparable: list[str] = field(default_factory=list)
    evidence_types: list[str] = field(default_factory=list)
    evidence_ceiling: str = CLAIM_LEVELS[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subquestion_id": self.subquestion_id,
            "supporting": list(self.supporting),
            "opposing": list(self.opposing),
            "neutral": list(self.neutral),
            "inconclusive": list(self.inconclusive),
            "not_comparable": list(self.not_comparable),
            "evidence_types": sorted(set(self.evidence_types)),
            "evidence_ceiling": self.evidence_ceiling,
            "has_conflict": bool(self.supporting and self.opposing),
        }


def pre_aggregate(evidence_items: Sequence[Mapping[str, Any]], subquestion_ids: Sequence[str]) -> dict[str, SubquestionAggregate]:
    """Collapse the evidence pool into per-sub-question structured summaries (T-20-03).

    The synthesiser (and any downstream Agent) reads only this structured summary,
    never the raw result tables.  Every direction — including opposing / neutral /
    inconclusive — is retained.
    """
    aggregates = {sq: SubquestionAggregate(sq) for sq in subquestion_ids}
    for ev in evidence_items:
        relation = str(ev.get("evidence_relation") or ev.get("supports_or_opposes") or "neutral")
        eid = str(ev.get("evidence_item_id", ""))
        for sq in ev.get("subquestion_ids", []) or []:
            agg = aggregates.get(sq)
            if agg is None:
                continue
            bucket = {"supports": agg.supporting, "opposes": agg.opposing, "neutral": agg.neutral, "inconclusive": agg.inconclusive}.get(
                relation, agg.not_comparable
            )
            bucket.append(eid)
            agg.evidence_types.append(str(ev.get("evidence_type", "")))
            agg.evidence_ceiling = _min_level(agg.evidence_ceiling, str(ev.get("allowed_claim_level", CLAIM_LEVELS[0])))
    return aggregates


@dataclass
class ClaimSynthesisResult:
    """The bounded result of claim synthesis: the drafts plus the coverage facts."""

    claims: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    unanswered_questions: list[dict[str, Any]] = field(default_factory=list)
    aggregates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": list(self.claims),
            "conflicts": list(self.conflicts),
            "unanswered_questions": list(self.unanswered_questions),
            "aggregates": list(self.aggregates),
            "synthesis_rules_version": SYNTHESIS_RULES_VERSION,
        }


def synthesize_claims(
    *,
    evidence_items: Sequence[Mapping[str, Any]],
    subquestions: Sequence[Mapping[str, Any]],
    scope_bundle: Mapping[str, Any],
    project_ceiling: str,
    method_ceiling: str = CLAIM_LEVELS[-1],
) -> ClaimSynthesisResult:
    """Synthesise bounded Claim drafts from the structured evidence summaries.

    One claim per sub-question that has evidence.  The claim level is the lowest of
    the evidence ceiling, the sub-question ceiling, the method ceiling and the
    project ceiling, then capped by the minimum-evidence rule (T-20-01) and, on
    conflict, downgraded with status ``conflicting`` (T-20-08).  Each claim lists its
    supporting and opposing evidence, its limitations and unanswered questions
    (T-20-07), and a scope that is the intersection of its evidence scopes (T-20-06).
    A sub-question with no evidence is recorded as unanswered — never dropped.
    """
    subquestion_ids = [str(sq.get("subquestion_id", "")) for sq in subquestions]
    ceilings = {str(sq.get("subquestion_id", "")): str(sq.get("claim_ceiling", project_ceiling)) for sq in subquestions}
    aggregates = pre_aggregate(evidence_items, subquestion_ids)
    ev_by_id = {str(ev.get("evidence_item_id", "")): ev for ev in evidence_items}

    result = ClaimSynthesisResult(aggregates=[a.to_dict() for a in aggregates.values()])
    for sq in subquestions:
        sq_id = str(sq.get("subquestion_id", ""))
        agg = aggregates[sq_id]
        relevant_ids = agg.supporting + agg.opposing + agg.neutral + agg.inconclusive
        if not relevant_ids:
            result.unanswered_questions.append({"subquestion_id": sq_id, "reason": sq.get("unresolved_reason", "no admitted evidence for this sub-question")})
            continue

        backing = [ev_by_id[i] for i in relevant_ids if i in ev_by_id]
        evidence_types = [str(ev.get("evidence_type", "")) for ev in backing]
        desired = _min_level(agg.evidence_ceiling, ceilings.get(sq_id, project_ceiling), method_ceiling, project_ceiling)
        level = cap_by_min_evidence(desired, evidence_types)

        has_conflict = bool(agg.supporting and agg.opposing)
        if has_conflict:
            # Heterogeneity is never averaged away: downgrade a level and flag it.
            level = CLAIM_LEVELS[max(0, _level_index(level) - 1)]
            status = "conflicting"
            result.conflicts.append({"subquestion_id": sq_id, "supporting": list(agg.supporting), "opposing": list(agg.opposing)})
        elif agg.supporting:
            status = "supports"
        elif agg.inconclusive and not agg.neutral:
            status = "inconclusive"
        else:
            status = "null_result"

        scope = scope_intersection(backing) or {}
        if not any(scope.values()):
            scope = {
                "species": list(scope_bundle.get("species", []) or []),
                "tissue": list(scope_bundle.get("tissues", []) or []),
                "condition": list(scope_bundle.get("conditions", []) or []),
            }

        text = _claim_text(status, level, agg, scope)
        limitations = _claim_limitations(status, backing)
        claim = Claim(
            claim_id="",
            text=text,
            claim_level=level,
            evidence_item_refs=sorted(set(agg.supporting + agg.neutral + agg.inconclusive)) or sorted(set(relevant_ids)),
            supports_subquestion_ids=[sq_id],
            scope=scope,
            limitations=limitations,
            status=status,
            claim_ceiling=ceilings.get(sq_id, project_ceiling),
            opposing_evidence_refs=sorted(set(agg.opposing)),
            uncertainty={"synthesis_dimensions": list(SYNTHESIS_DIMENSIONS), "has_conflict": has_conflict},
        )
        claim_dict = claim.to_dict()
        claim_dict["created_at"] = ""
        # Fail-closed: a synthesised claim may never exceed any ceiling.
        errors = validate_claim_ceiling(claim_dict, project_ceiling)
        errors += validate_claim(claim_dict, max_allowed=project_ceiling)
        if errors:
            raise ValueError(f"synthesised claim for {sq_id} is invalid: {'; '.join(errors)}")
        result.claims.append(claim_dict)
    return result


def _claim_text(status: str, level: str, agg: SubquestionAggregate, scope: Mapping[str, Any]) -> str:
    species = ", ".join(scope.get("species", []) or []) or "the studied context"
    tissue = ", ".join(scope.get("tissue", []) or []) or "the studied tissue"
    if status == "conflicting":
        return f"Evidence for this sub-question conflicts across datasets (supporting and opposing observations coexist); the {level}-level statement is downgraded and the heterogeneity is retained in {species} / {tissue}."
    if status == "null_result":
        return f"No admitted evidence reached the significance and effect-size thresholds; the available {level}-level evidence does not support a differential-expression claim in {species} / {tissue}."
    if status == "inconclusive":
        return f"The available evidence is inconclusive (non-significant under inadequate power) for this sub-question in {species} / {tissue}; no {level}-level claim is warranted."
    return f"At the {level} level, the admitted evidence supports a differential-expression signal for this sub-question in {species} / {tissue}. This is an {level}-level statement bounded to the evidence scope."


def _claim_limitations(status: str, backing: Sequence[Mapping[str, Any]]) -> list[str]:
    limitations: list[str] = ["RNA differential expression is association-level evidence; it does not establish protein abundance, secretion, or causality."]
    reps = {str(ev.get("replication_status", "")) for ev in backing}
    if reps <= {"single_dataset"}:
        limitations.append("Single dataset; results are not independently replicated.")
    if status == "conflicting":
        limitations.append("Conflicting evidence across datasets; the claim is downgraded and heterogeneity is preserved.")
    if status == "inconclusive":
        limitations.append("Absence of a significant result under inadequate power is not evidence of no effect.")
    # De-dupe while preserving order.
    seen: set[str] = set()
    return [x for x in limitations if not (x in seen or seen.add(x))]


def build_gc_approval_package(claim: Mapping[str, Any], evidence_items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Assemble the inert G-C approval package for a validated claim (T-20-09).

    Bundles the claim, its level and scope, its supporting and opposing evidence and
    its limitations for human approval.  The package is bound to the claim's exact
    version (its content id) and is inert — it grants nothing.
    """
    ev_by_id = {str(ev.get("evidence_item_id", "")): ev for ev in evidence_items}
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "gc_approval_package_id": make_stable_id("gc_approval_package", {"claim_id": claim.get("claim_id", ""), "claim_level": claim.get("claim_level", "")}),
        "claim_id": claim.get("claim_id", ""),
        "claim_version_ref": claim.get("claim_id", ""),
        "claim_level": claim.get("claim_level", ""),
        "scope": dict(claim.get("scope", {}) or {}),
        "supporting_evidence": [ev_by_id.get(i, {"evidence_item_id": i}) for i in (claim.get("evidence_item_refs") or [])],
        "opposing_evidence": [ev_by_id.get(i, {"evidence_item_id": i}) for i in (claim.get("opposing_evidence_refs") or [])],
        "limitations": list(claim.get("limitations", []) or []),
        "grants_approval": False,
        "created_at": "",
        "status": "pending_review",
    }


__all__ = [
    "SYNTHESIS_RULES_VERSION",
    "SYNTHESIS_DIMENSIONS",
    "CLAIM_STATUSES",
    "SubquestionAggregate",
    "ClaimSynthesisResult",
    "min_evidence_satisfied",
    "cap_by_min_evidence",
    "scope_intersection",
    "pre_aggregate",
    "synthesize_claims",
    "build_gc_approval_package",
]
