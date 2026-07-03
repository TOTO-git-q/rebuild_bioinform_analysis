"""Report traceability index, figure list, coverage matrix, method-trace table (WP-21).

Every conclusion in a report must be traceable back to the run that produced it
(T-21-03, T-21-07, T-21-09).  This module builds, from already-audited fixture
objects, the deterministic indexes the report appends: a per-claim
claim→evidence→artifact→dataset chain (:func:`build_trace_index`), a figure list
whose every figure references a source-table artifact and a task-run
(:func:`build_figure_list`), the original-question coverage matrix
(:func:`build_coverage_matrix`), and the method-trace table
(:func:`build_method_trace_table`).  A claim with a broken chain, or a figure with
no source table, is a **traceability gap** that blocks publication — the report may
never present an untraceable claim or figure.

Pure, offline, deterministic; inputs are never mutated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_trace_index(
    claims: Sequence[Mapping[str, Any]],
    evidence_items: Sequence[Mapping[str, Any]],
    artifact_manifests: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the per-claim claim→evidence→artifact→dataset traceability index (T-21-03).

    Returns ``{"chains": {claim_id: [links...]}, "gaps": [...], "complete": bool}``.
    A ``gap`` is recorded (and ``complete`` is false) whenever a claim references a
    missing evidence item, an evidence item points at a missing artifact, or an
    artifact/evidence carries no source dataset — so a downstream builder can refuse
    to publish an untraceable claim.
    """
    ev_by_id = {str(e.get("evidence_item_id", "")): e for e in evidence_items}
    art_by_id = {str(a.get("artifact_id", "")): a for a in artifact_manifests}
    chains: dict[str, list[dict[str, Any]]] = {}
    gaps: list[dict[str, Any]] = []

    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        refs = [str(r) for r in (claim.get("evidence_item_refs") or [])]
        if not refs:
            gaps.append({"claim_id": claim_id, "reason": "claim references no evidence item"})
            chains[claim_id] = []
            continue
        links: list[dict[str, Any]] = []
        for ref in refs:
            evidence = ev_by_id.get(ref)
            if evidence is None:
                gaps.append({"claim_id": claim_id, "evidence_item_id": ref, "reason": "referenced evidence item is missing"})
                continue
            artifact_id = str(evidence.get("artifact_id", ""))
            artifact = art_by_id.get(artifact_id)
            datasets = [str(d) for d in (evidence.get("source_dataset_ids") or []) if str(d)]
            task_runs = [str(t) for t in (evidence.get("source_task_run_ids") or []) if str(t)]
            if artifact is None:
                gaps.append({"claim_id": claim_id, "evidence_item_id": ref, "artifact_id": artifact_id, "reason": "referenced artifact manifest is missing"})
                continue
            if not datasets:
                gaps.append({"claim_id": claim_id, "evidence_item_id": ref, "reason": "evidence has no source dataset (chain does not reach a dataset)"})
            links.append(
                {
                    "claim_id": claim_id,
                    "evidence_item_id": ref,
                    "artifact_id": artifact_id,
                    "task_run_ids": task_runs,
                    "dataset_ids": datasets,
                }
            )
        chains[claim_id] = links
        if not links:
            gaps.append({"claim_id": claim_id, "reason": "claim has no complete evidence→artifact chain"})
    return {"chains": chains, "gaps": gaps, "complete": not gaps}


def has_untraceable_claim(trace_index: Mapping[str, Any]) -> bool:
    return not trace_index.get("complete", False)


def build_figure_list(figures: Sequence[Mapping[str, Any]], artifact_manifests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the figure list; every figure must reference a source-table artifact (T-21-07).

    A figure that names no ``source_artifact_id`` (or names one with no registered
    manifest) or no ``task_run_id`` is a gap that blocks publication — a figure with
    no source table is never allowed.
    """
    art_ids = {str(a.get("artifact_id", "")) for a in artifact_manifests}
    entries: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for fig in figures:
        fig_id = str(fig.get("figure_id", ""))
        source = str(fig.get("source_artifact_id", ""))
        task_run = str(fig.get("task_run_id", ""))
        traceable = bool(source) and source in art_ids and bool(task_run)
        entries.append({"figure_id": fig_id, "title": fig.get("title", ""), "source_artifact_id": source, "task_run_id": task_run, "traceable": traceable})
        if not traceable:
            gaps.append({"figure_id": fig_id, "reason": "figure has no registered source-table artifact / task run"})
    return {"figures": entries, "gaps": gaps, "complete": not gaps}


def build_coverage_matrix(
    subquestions: Sequence[Mapping[str, Any]],
    coverage: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the original-question coverage matrix (T-21-09).

    Joins each sub-question (and its parent requirement, when present) to its
    four-state coverage verdict.  Every sub-question appears — an unanswered item is
    never omitted from the matrix.
    """
    state_by_sq = {str(c.get("subquestion_id", "")): c for c in coverage}
    rows: list[dict[str, Any]] = []
    for sq in subquestions:
        sq_id = str(sq.get("subquestion_id", ""))
        entry = state_by_sq.get(sq_id, {})
        rows.append(
            {
                "subquestion_id": sq_id,
                "requirement_id": sq.get("requirement_id", sq.get("parent_requirement_id", "")),
                "text": sq.get("text", sq.get("question", "")),
                "state": entry.get("state", "unanswered"),
                "supporting_claim_ids": entry.get("supporting_claim_ids", []),
            }
        )
    return {"rows": rows, "n_subquestions": len(rows)}


def build_method_trace_table(
    subquestions: Sequence[Mapping[str, Any]],
    method_contracts: Sequence[Mapping[str, Any]],
    task_runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the method-trace table: sub-question → method contract → task run (T-21-09)."""
    contracts_by_sq: dict[str, list[str]] = {}
    for contract in method_contracts:
        cid = str(contract.get("method_contract_id", contract.get("contract_id", "")))
        for sq in contract.get("supports_subquestion_ids", []) or []:
            contracts_by_sq.setdefault(str(sq), []).append(cid)
    runs_by_contract: dict[str, list[str]] = {}
    for run in task_runs:
        cid = str(run.get("method_contract_id", run.get("contract_id", "")))
        runs_by_contract.setdefault(cid, []).append(str(run.get("task_run_id", "")))
    rows: list[dict[str, Any]] = []
    for sq in subquestions:
        sq_id = str(sq.get("subquestion_id", ""))
        cids = contracts_by_sq.get(sq_id, [])
        rows.append(
            {
                "subquestion_id": sq_id,
                "method_contract_ids": cids,
                "task_run_ids": sorted({rid for cid in cids for rid in runs_by_contract.get(cid, [])}),
            }
        )
    return {"rows": rows}


__all__ = [
    "build_trace_index",
    "has_untraceable_claim",
    "build_figure_list",
    "build_coverage_matrix",
    "build_method_trace_table",
]
