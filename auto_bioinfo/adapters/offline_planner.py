"""Deterministic, offline planner adapter (implements ``ports.PlannerPort``).

This stands in for the LLM-backed planning agents.  It is intentionally
rule-based and offline so the default test suite never needs a paid model or the
network, and so the same question always yields the same plan.  Crucially it
follows the "no business preset" rule: it extracts only what the question
actually states and records everything else as an ``open_question`` / assumption
rather than inventing an organism, tissue, or disease.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import EvidencePlan, ResearchSpec, ScopeBundle, SubQuestion

# Neutral fixture vocabulary the planner is allowed to recognise.  These are not
# biological presets — they are structural tokens used by the offline fixtures.
_CONDITION_RE = re.compile(r"condition_[a-z0-9]+", re.IGNORECASE)
_TISSUE_RE = re.compile(r"tissue_[a-z0-9]+", re.IGNORECASE)
_KNOWN_ORGANISMS = ("human", "mouse", "rat")
_VS_RE = re.compile(r"\b([\w-]+)\s+(?:vs\.?|versus)\s+([\w-]+)\b", re.IGNORECASE)
_BETWEEN_RE = re.compile(r"between\s+([\w-]+)\s+and\s+([\w-]+)", re.IGNORECASE)


class OfflineDeterministicPlanner:
    """Rule-based planner; pure function of the question text."""

    def normalize_question(self, project_id: str, question: str) -> dict[str, Any]:
        text = question.strip()
        comparison = _extract_comparison(text)
        tissue_match = _TISSUE_RE.search(text)
        organism = next((o for o in _KNOWN_ORGANISMS if re.search(rf"\b{o}\b", text, re.IGNORECASE)), "")

        open_questions: list[str] = []
        assumptions: list[str] = []
        if not comparison:
            open_questions.append("No explicit comparison groups detected in the question.")
        if not tissue_match:
            open_questions.append("Tissue / context not explicitly stated; downstream scope is unconstrained.")
        if not organism:
            open_questions.append("Organism not stated; left empty rather than assumed.")

        spec = ResearchSpec(
            project_id=project_id,
            research_question=text,
            status="resolved",
            organism=organism,
            tissue=tissue_match.group(0) if tissue_match else "",
            condition_or_phenotype=" vs ".join(comparison) if comparison else "",
            comparison_groups=comparison,
            target_outputs=["differentially_expressed_genes"],
            # RNA-expression questions cannot, on their own, exceed association level.
            max_claim_level="association",
            claim_ceiling="association",
            assumptions=assumptions,
            open_questions=open_questions,
        )
        return spec.to_dict()

    def decompose(self, research_spec: dict[str, Any]) -> list[dict[str, Any]]:
        rsid = research_spec["research_spec_id"]
        groups = research_spec.get("comparison_groups") or []
        contrast = " vs ".join(groups) if groups else "the requested groups"
        questions = [
            f"Which genes are differentially expressed between {contrast}?",
            "Are the differential-expression results supported by an adequate, donor/sample-level statistical design?",
        ]
        out: list[dict[str, Any]] = []
        for q in questions:
            sq = SubQuestion(research_spec_id=rsid, question=q, status="resolved").to_dict()
            out.append(sq)
        return out

    def resolve_scope(self, research_spec: dict[str, Any], subquestions: list[dict[str, Any]]) -> dict[str, Any]:
        scope = ScopeBundle(
            research_spec_id=research_spec["research_spec_id"],
            species=[research_spec["organism"]] if research_spec.get("organism") else [],
            tissues=[research_spec["tissue"]] if research_spec.get("tissue") else [],
            conditions=list(research_spec.get("comparison_groups") or []),
            status="resolved",
        )
        from dataclasses import asdict

        data = asdict(scope)
        data["scope_bundle_id"] = make_stable_id(
            "scope_bundle",
            {"research_spec_id": research_spec["research_spec_id"], "subquestion_ids": [s["subquestion_id"] for s in subquestions]},
        )
        return data

    def plan_evidence(self, research_spec: dict[str, Any], subquestions: list[dict[str, Any]]) -> dict[str, Any]:
        from dataclasses import asdict

        plan = EvidencePlan(
            research_spec_id=research_spec["research_spec_id"],
            evidence_axes=["bulk_rna_differential_expression", "statistical_design_adequacy"],
            max_claim_level=research_spec.get("claim_ceiling", "association"),
            status="planned",
        )
        data = asdict(plan)
        data["evidence_plan_id"] = make_stable_id(
            "evidence_plan",
            {"research_spec_id": research_spec["research_spec_id"], "subquestion_ids": [s["subquestion_id"] for s in subquestions]},
        )
        data["minimum_replication"] = {"min_replicates_per_group": 2}
        data["negative_evidence_strategy"] = "Report non-significant and opposite-direction genes; do not drop them."
        data["stop_conditions"] = ["No verifiable dataset", "Design below minimum replicates"]
        return data


def _extract_comparison(text: str) -> list[str]:
    conditions = [m.group(0) for m in _CONDITION_RE.finditer(text)]
    if len(conditions) >= 2:
        # preserve order, dedup
        seen: list[str] = []
        for c in conditions:
            if c not in seen:
                seen.append(c)
        if len(seen) >= 2:
            return seen[:2]
    for regex in (_BETWEEN_RE, _VS_RE):
        m = regex.search(text)
        if m:
            return [m.group(1), m.group(2)]
    return []
