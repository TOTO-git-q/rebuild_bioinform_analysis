"""EvidenceItem extraction and Claim synthesis.

Turns a QC-passed DEG artifact into a structured EvidenceItem, then synthesises a
Claim whose ``claim_level`` is hard-capped by both the method's claim capability
and the project ceiling.  Negative / non-significant results are preserved in the
EvidenceItem rather than dropped (requirement spec, stage 14-15).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import CLAIM_LEVELS, Claim, EvidenceItem
from ..core.validation import validate_claim_ceiling


def _min_level(a: str, b: str) -> str:
    ia = CLAIM_LEVELS.index(a) if a in CLAIM_LEVELS else 0
    ib = CLAIM_LEVELS.index(b) if b in CLAIM_LEVELS else 0
    return CLAIM_LEVELS[min(ia, ib)]


def read_deg_table(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            row["significant"] = str(row.get("significant")).lower() == "true"
            for key in ("log2_fold_change", "fdr", "p_value"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def build_evidence_item(
    *,
    deg_table_path: str,
    method_result: dict[str, Any],
    artifact_manifest: dict[str, Any],
    qc_report: dict[str, Any],
    dataset_profile: dict[str, Any],
    scope_bundle: dict[str, Any],
    subquestion_ids: list[str],
    contract: dict[str, Any],
    project_ceiling: str,
) -> dict[str, Any]:
    rows = read_deg_table(deg_table_path)
    sig = [r for r in rows if r["significant"]]
    sig_sorted = sorted(sig, key=lambda r: r["fdr"])
    top = [r["gene"] for r in sig_sorted[:10]]
    max_abs_lfc = max((abs(r["log2_fold_change"]) for r in rows), default=0.0)

    allowed = _min_level(contract.get("claim_capability", "association"), project_ceiling)
    group_a = method_result.get("group_a", "")
    group_b = method_result.get("group_b", "")
    observation = (
        f"{len(sig)} of {len(rows)} genes show significant bulk-RNA differential expression "
        f"between {group_a} and {group_b} (FDR < {contract['parameters']['significance_alpha']}, "
        f"|log2FC| >= {contract['parameters']['log2fc_threshold']})."
    )
    item = EvidenceItem(
        evidence_item_id=make_stable_id("evidence_item", {"artifact_id": artifact_manifest.get("artifact_id", ""), "observation": observation}),
        artifact_id=artifact_manifest.get("artifact_id", ""),
        review_status="audited",
        subquestion_ids=subquestion_ids,
        source_dataset_ids=[dataset_profile.get("dataset_id", "")],
        source_task_run_ids=[method_result.get("task_run_id", "")],
        observation=observation,
        effect_summary={
            "n_genes": len(rows),
            "n_significant": len(sig),
            "top_significant_genes": top,
            "max_abs_log2_fold_change": round(max_abs_lfc, 4),
        },
        uncertainty={
            "statistical_test": "welch_t_test",
            "fdr_method": "benjamini_hochberg",
            "significance_alpha": contract["parameters"]["significance_alpha"],
            "log2fc_threshold": contract["parameters"]["log2fc_threshold"],
        },
        evidence_type="bulk_rna_differential_expression",
        scope={
            "species": scope_bundle.get("species", []),
            "tissue": scope_bundle.get("tissues", []),
            "condition": scope_bundle.get("conditions", []),
        },
        qc_status="pass" if qc_report.get("overall_status") in {"pass", "pass_with_warnings"} else "fail",
        allowed_claim_level=allowed,
        supports_or_opposes="supports" if sig else "neutral",
        replication_status="single_dataset",
        limitations=[
            "RNA differential expression is association-level evidence; it does not establish protein abundance, secretion, or causality.",
            "Single dataset; results are not independently replicated.",
        ]
        + list(dataset_profile.get("known_limitations", [])),
    )
    from dataclasses import asdict

    return asdict(item)


def synthesize_claims(
    *,
    evidence_items: list[dict[str, Any]],
    research_spec: dict[str, Any],
    scope_bundle: dict[str, Any],
    project_ceiling: str,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for ev in evidence_items:
        allowed = _min_level(ev.get("allowed_claim_level", "association"), project_ceiling)
        n_sig = ev.get("effect_summary", {}).get("n_significant", 0)
        top = ev.get("effect_summary", {}).get("top_significant_genes", [])
        if n_sig > 0:
            statement = (
                f"At the RNA level, {n_sig} gene(s) show association-level differential expression for the requested "
                f"contrast (top candidates: {', '.join(top[:5])}). This is an expression association only."
            )
            support = "supports"
        else:
            statement = (
                "No genes reached the significance and effect-size thresholds for the requested contrast; "
                "the available evidence does not support a differential-expression claim."
            )
            support = "null_result"

        claim = Claim(
            claim_id=make_stable_id("claim", {"evidence_item_id": ev["evidence_item_id"], "statement": statement}),
            text=statement,
            claim_level=allowed,
            evidence_item_refs=[ev["evidence_item_id"]],
            supports_subquestion_ids=list(ev.get("subquestion_ids", [])),
            scope={
                "species": scope_bundle.get("species", []),
                "tissue": scope_bundle.get("tissues", []),
                "condition": scope_bundle.get("conditions", []),
            },
            limitations=list(ev.get("limitations", [])),
            status=support,
        )
        from dataclasses import asdict

        claim_dict = asdict(claim)
        ceiling_errors = validate_claim_ceiling(claim_dict, project_ceiling)
        if ceiling_errors:
            raise ValueError("; ".join(ceiling_errors))
        claims.append(claim_dict)
    return claims
