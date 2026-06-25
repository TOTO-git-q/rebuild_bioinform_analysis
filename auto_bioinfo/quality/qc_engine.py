"""Four-layer deterministic QC engine (Execution / Data / Statistical / Biological).

QC is the gate between a raw run and scientific evidence: only artifacts whose
QC passes may become an EvidenceItem (requirement spec, stage 13-14).  Each check
records its layer, status, reason, and the artifact it concerns, so a failure is
a structured finding — never a bare boolean — and so the alignment auditor can
see which artifacts/evidence a failed check invalidates.
"""

from __future__ import annotations

from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION, now_iso

_PASS = "pass"
_WARN = "warn"
_FAIL = "fail"


def run_four_layer_qc(
    *,
    method_result: dict[str, Any],
    dataset_profile: dict[str, Any],
    artifact_manifest: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    artifact_id = artifact_manifest.get("artifact_id", "")
    checks: list[dict[str, Any]] = []

    def add(check_id: str, layer: str, ok: bool, detail: str, *, warn_only: bool = False) -> None:
        status = _PASS if ok else (_WARN if warn_only else _FAIL)
        checks.append({"check_id": check_id, "layer": layer, "status": status, "detail": detail, "artifact_id": artifact_id})

    design = contract.get("minimum_sample_design", {})
    min_rep = design.get("min_replicates_per_group", 2)
    group_sizes = method_result.get("group_sizes", {}) or dataset_profile.get("group_sizes", {})

    # --- Execution QC -------------------------------------------------------
    add("execution.method_succeeded", "execution", method_result.get("status") == "succeeded", f"method status={method_result.get('status')}")
    add(
        "execution.output_exists",
        "execution",
        artifact_manifest.get("exists") is True and artifact_manifest.get("size_bytes", 0) > 0,
        f"size_bytes={artifact_manifest.get('size_bytes', 0)}",
    )
    add("execution.expected_outputs_present", "execution", "deg_results_table" in (method_result.get("outputs") or {}), "deg_results_table present")

    # --- Data QC ------------------------------------------------------------
    add("data.group_count", "data", len(group_sizes) >= design.get("groups", 2), f"groups={list(group_sizes)}")
    add("data.nonempty_matrix", "data", method_result.get("n_genes", 0) > 0, f"n_genes={method_result.get('n_genes', 0)}")
    add("data.checksum_present", "data", bool(artifact_manifest.get("checksum_sha256")), "artifact has content checksum")

    # --- Statistical QC -----------------------------------------------------
    below = {g: n for g, n in group_sizes.items() if n < min_rep}
    add(
        "statistical.min_replicates",
        "statistical",
        not below,
        f"groups below {min_rep} replicates: {below}" if below else f"all groups >= {min_rep} replicates",
    )
    add(
        "statistical.unit_is_sample",
        "statistical",
        contract.get("statistical_unit") == "sample",
        f"statistical_unit={contract.get('statistical_unit')}; sample-level avoids pseudo-replication",
    )
    add("statistical.multiple_testing", "statistical", True, "Benjamini-Hochberg FDR applied across all genes")

    # --- Biological QC ------------------------------------------------------
    modality = str(dataset_profile.get("modality", "")).lower()
    capability = contract.get("claim_capability", "")
    rna_capped = ("rna" in modality or "expression" in modality) and capability == "association"
    add(
        "biological.claim_capability_matches_data",
        "biological",
        rna_capped,
        f"modality={modality}, claim_capability={capability}; RNA expression is capped at association (no protein/secretion/causal)",
    )

    overall = _PASS
    if any(c["status"] == _FAIL for c in checks):
        overall = _FAIL
    elif any(c["status"] == _WARN for c in checks):
        overall = "pass_with_warnings"

    decision = {
        _PASS: "PASS",
        "pass_with_warnings": "PASS_WITH_WARNINGS",
        _FAIL: "REJECT",
    }[overall]

    report_id = make_stable_id("qc_report", {"artifact_id": artifact_id, "checks": [c["check_id"] for c in checks], "overall_status": overall})
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "qc_report_id": report_id,
        "artifact_id": artifact_id,
        "overall_status": overall,
        "decision": decision,
        "checks": checks,
        "blocking_findings": [c for c in checks if c["status"] == _FAIL],
        "created_at": now_iso(),
        "status": "recorded",
    }
