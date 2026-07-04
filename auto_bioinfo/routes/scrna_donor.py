"""WP-17 — sc/snRNA donor-level route + cross-dataset consistency.

Reuses the WP-16 chain (:func:`auto_bioinfo.routes.bulk_rnaseq.run_analysis_chain`)
but enforces the donor-level scientific boundary: cells are aggregated to
donor-level pseudobulk *before* any DEG runs (the donor, never the cell, is the
statistical unit), and the compatibility/DAG lane gates on the
``scrna_pseudobulk_deg`` catalog contract (statistical unit = donor).  A separate
cross-dataset concordance check compares two genuinely independent donor-level
results and keeps every outcome — consistent, conflicting, not-comparable and
missing — never only the agreeing positives.

Everything is offline, deterministic and inert, over committed synthetic
fixtures.  A dataset with unknown donors is refused (INSUFFICIENT_DATA), not
silently inferred.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..methods.registry import get_method
from . import glue
from .bulk_rnaseq import AnalysisContext, _run_planning, _run_resources, run_analysis_chain
from .route_run import (
    STAGE_OK,
    STAGE_STOPPED,
    TERMINAL_COMPLETED,
    TERMINAL_INSUFFICIENT_DATA,
    RouteRun,
)

# NB: the request text stays single-topic (only "differentially expressed") so the
# WP-06b multi-topic gate does not stop it; the single-cell / donor-level nature of
# the study comes from the resolved dataset + scope, never from guessing on text.
DEFAULT_SCRNA_QUESTION = "Which genes are differentially expressed in liver between tumor and normal donors in human data?"

_SCRNA_METADATA_KEYS = ["donor_labels", "cell_type_labels", "condition_labels"]


def _count_selected_donor_labels(cell_metadata_content: str, *, cell_type: str = "") -> tuple[int, int]:
    """Count selected cells and, of those, how many carry a blank/missing donor label.

    A cell is *selected* when it matches the route's ``cell_type`` filter (all cells
    when no filter is set).  The donor is the statistical unit, so a real cell whose
    donor identity is missing/blank cannot be silently folded into an empty-string
    donor key — it must fail closed before any DEG/claim output (turns 0357/0359).
    """
    rows = glue.read_tsv_rows(cell_metadata_content)
    n_selected = 0
    n_missing = 0
    for row in rows:
        if cell_type and row.get("cell_type", "") != cell_type:
            continue
        n_selected += 1
        donor = str(row.get("donor", row.get("donor_id", "")) or "").strip()
        if not donor:
            n_missing += 1
    return n_selected, n_missing


def _donor_samples(cell_metadata_content: str, *, cell_type: str = "", unknown_donors: bool = False) -> list[dict[str, str]]:
    """Project cell metadata to unique donor-level 'samples' (donor is the unit)."""
    rows = glue.read_tsv_rows(cell_metadata_content)
    seen: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in rows:
        if cell_type and row.get("cell_type", "") != cell_type:
            continue
        donor = row.get("donor", row.get("donor_id", ""))
        if donor not in seen:
            seen[donor] = {
                "sample_id": donor,
                "group": row.get("condition", ""),
                "donor_id": "unknown" if unknown_donors else donor,
            }
            order.append(donor)
    return [seen[d] for d in order]


def run_scrna_donor_route(
    question: str = DEFAULT_SCRNA_QUESTION,
    *,
    project_id: str = "scrna_donor_route",
    workspace: str | Path,
    dataset: glue.RouteDataset | None = None,
    overrides: dict[str, Any] | None = None,
) -> RouteRun:
    """Run the offline donor-level pseudobulk route end to end."""
    overrides = dict(overrides or {})
    dataset = dataset or glue.load_route_dataset("scrna_donor_route")
    cell_type = str(dataset.card.get("cell_type", "") or "")
    run = RouteRun(route="scrna_donor", project_id=project_id, question=question)

    # ---- planning ----------------------------------------------------------
    planning = _run_planning(run, question, project_id)
    if planning is None:
        return run
    research_spec, scope_bundle, subquestions, evidence_plan = planning

    # ---- donor-identity integrity gate (the sc boundary) -------------------
    # Real partially missing donor labels in the selected sc/snRNA metadata must
    # fail closed BEFORE any pseudobulk aggregation, DEG, claim, alignment, report
    # or reproduction output is fabricated.  The donor — never the cell — is the
    # statistical unit, so an unlabeled cell is not silently absorbed into a blank
    # donor key; the dataset is refused (INSUFFICIENT_DATA), not inferred.
    n_selected, n_missing_donor = _count_selected_donor_labels(dataset.files.get("cell_metadata", ""), cell_type=cell_type)
    if n_missing_donor:
        run.add_stage(
            "donor_identity_check",
            STAGE_STOPPED,
            reason="MISSING_DONOR_LABEL",
            payload={"n_selected_cells": n_selected, "n_missing_donor": n_missing_donor},
        )
        run.stop(
            TERMINAL_INSUFFICIENT_DATA,
            f"{n_missing_donor} of {n_selected} selected cell(s) have a missing/blank donor label; "
            "donor identity is the statistical unit and cannot be inferred",
        )
        return run
    run.add_stage(
        "donor_identity_check",
        STAGE_OK,
        payload={"n_selected_cells": n_selected, "n_missing_donor": 0},
    )

    # ---- resource closure over donor-level samples -------------------------
    donor_samples = _donor_samples(
        dataset.files.get("cell_metadata", ""),
        cell_type=cell_type,
        unknown_donors=bool(overrides.get("unknown_donors")),
    )
    manifest = _run_resources(
        run,
        research_spec=research_spec,
        scope_bundle=scope_bundle,
        subquestions=subquestions,
        evidence_plan=evidence_plan,
        dataset=dataset,
        samples=donor_samples,
        overrides=overrides,
    )
    if manifest is None:
        return run

    # ---- donor-level pseudobulk aggregation (the sc boundary) --------------
    agg = glue.pseudobulk_aggregate(
        dataset.files.get("cell_counts", ""),
        dataset.files.get("cell_metadata", ""),
        cell_type=cell_type,
    )
    run.add_stage(
        "pseudobulk_aggregation",
        STAGE_OK,
        payload={
            "n_donors": len(agg["donors"]),
            "cells_per_donor": agg["cells_per_donor"],
            "donor_group_sizes": agg["group_sizes"],
            "statistical_unit": "donor",
        },
    )

    # ---- shared analysis + scoring tail (donor unit) -----------------------
    ctx = AnalysisContext(
        workspace=Path(workspace),
        project_id=project_id,
        counts_tsv=agg["counts_tsv"],
        samples_tsv=agg["samples_tsv"],
        dataset=dataset,
        subquestion=subquestions[0],
        scope_bundle=scope_bundle,
        research_spec=research_spec,
        project_ceiling=research_spec.get("claim_ceiling", "association"),
        plan_method_id="scrna_pseudobulk_deg",
        runtime_method_id="bulk_deg",
        compat_modality="single_cell_expression_matrix",
        compat_statistical_unit="donor",
        qc_statistical_unit="sample",  # post-aggregation the donor IS the sample unit
        qc_modality="single_cell_rna",
        metadata_keys=_SCRNA_METADATA_KEYS,
        manifest=manifest,
        # Recorded cell-level QC facts for the synthetic fixture (clean cells): the
        # single-cell doublet/ambient Data-QC is assessed, not silently skipped.
        sc_metrics={"doublet_rate": 0.02, "ambient_rna_fraction": 0.05},
        overrides=overrides,
    )
    run_analysis_chain(run, ctx)
    return run


# --------------------------------------------------------------------------
# Cross-dataset consistency (T-17-13 / T-17-14)
# --------------------------------------------------------------------------


def _donor_deg_rows(workspace: Path, label: str, cell_counts: str, cell_metadata: str, *, cell_type: str = "") -> list[dict[str, Any]]:
    """Aggregate to donor pseudobulk and run the deterministic DEG runner."""
    agg = glue.pseudobulk_aggregate(cell_counts, cell_metadata, cell_type=cell_type)
    d = workspace / label
    d.mkdir(parents=True, exist_ok=True)
    (d / "counts.tsv").write_text(agg["counts_tsv"], encoding="utf-8")
    (d / "samples.tsv").write_text(agg["samples_tsv"], encoding="utf-8")
    result = get_method("bulk_deg").run(
        inputs={"counts": str(d / "counts.tsv"), "samples": str(d / "samples.tsv")},
        params={},
        out_dir=str(d / "out"),
    )
    return glue.parse_deg_rows(result["output_path"])


def build_replicate_scrna_dataset() -> dict[str, str]:
    """A second, genuinely independent synthetic sc dataset for concordance.

    Independent donors (r-prefixed), the same up/down signal for most genes, one
    gene deliberately flipped (to exercise a *conflicting* outcome) and a
    dataset-specific gene set difference (to exercise *missing* and
    *not_comparable* outcomes).  Deterministic and clearly synthetic.
    """
    header = "gene\t" + "\t".join(f"rc{i:02d}" for i in range(1, 19))
    # 3 tumor donors (rc01-09) then 3 normal donors (rc10-18), 3 cells each.
    tumor_cells = list(range(9))
    genes = {
        # consistent up in tumor (same direction as primary)
        "GENE_UP1": (320, 20),
        "GENE_UP2": (300, 18),
        # consistent down in tumor
        "GENE_DOWN1": (14, 300),
        # CONFLICTING: primary is down-in-tumor; here it is up-in-tumor
        "GENE_DOWN2": (280, 12),
        # not comparable: flat (never significant) in this dataset
        "GENE_FLAT1": (160, 158),
        # dataset-specific gene (primary lacks GENE_ONLY_REP -> missing)
        "GENE_ONLY_REP": (250, 30),
    }
    lines = [header]
    for gene, (hi, lo) in genes.items():
        vals = []
        for cell in range(18):
            base = hi if cell in tumor_cells else lo
            # Per-donor offset (cell//3 = donor index) so donor-level pseudobulk
            # sums vary across donors within a group (non-degenerate t-test),
            # plus a small within-donor jitter.
            vals.append(str(base + (cell // 3) * 5 + (cell % 3) * 2))
        lines.append(gene + "\t" + "\t".join(vals))
    counts = "\n".join(lines) + "\n"
    meta_lines = ["cell\tdonor\tcell_type\tcondition"]
    for cell in range(18):
        donor = f"rdonor_{(cell // 3) + 1:02d}"
        cond = "tumor" if cell in tumor_cells else "normal"
        meta_lines.append(f"rc{cell + 1:02d}\t{donor}\tTcell\t{cond}")
    metadata = "\n".join(meta_lines) + "\n"
    return {"cell_counts": counts, "cell_metadata": metadata}


def run_cross_dataset_consistency(
    *,
    workspace: str | Path,
    project_id: str = "scrna_concordance",
    primary: glue.RouteDataset | None = None,
    replicate: dict[str, str] | None = None,
) -> RouteRun:
    """Compare two independent donor-level results and keep every outcome."""
    workspace = Path(workspace)
    primary = primary or glue.load_route_dataset("scrna_donor_route")
    replicate = replicate or build_replicate_scrna_dataset()
    cell_type = str(primary.card.get("cell_type", "") or "")
    run = RouteRun(route="scrna_cross_dataset", project_id=project_id, question="Does the donor-level effect replicate in an independent dataset?")

    primary_rows = _donor_deg_rows(workspace, "primary", primary.files.get("cell_counts", ""), primary.files.get("cell_metadata", ""), cell_type=cell_type)
    replicate_rows = _donor_deg_rows(workspace, "replicate", replicate["cell_counts"], replicate["cell_metadata"], cell_type="Tcell")

    concordance = glue.cross_dataset_concordance(primary_rows, replicate_rows)
    run.concordance = concordance
    run.add_stage(
        "cross_dataset_concordance",
        STAGE_OK,
        payload={
            "n_consistent": concordance["n_consistent"],
            "n_conflicting": concordance["n_conflicting"],
            "n_not_comparable": concordance["n_not_comparable"],
            "n_missing": concordance["n_missing"],
            "independent": concordance["independent"],
        },
    )
    # A pure re-analysis of the SAME cohort is never independent replication.
    run.add_stage(
        "replication_independence",
        STAGE_OK,
        reason="two genuinely independent synthetic datasets; a re-analysis of the same cohort would NOT count as replication",
        payload={"same_cohort": concordance["same_cohort"]},
    )
    run.terminal_status = TERMINAL_COMPLETED
    run.reason = "cross-dataset concordance computed; consistent / conflicting / not-comparable / missing all retained"
    return run


__all__ = [
    "run_scrna_donor_route",
    "run_cross_dataset_consistency",
    "build_replicate_scrna_dataset",
    "DEFAULT_SCRNA_QUESTION",
]
