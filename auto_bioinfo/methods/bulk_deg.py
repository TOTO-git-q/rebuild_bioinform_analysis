"""``bulk_deg`` — a real, deterministic bulk differential-expression method.

This is the registered analysis that the vertical slice actually executes (no
metadata-only role).  Given a bulk count matrix and per-sample group labels it
computes CPM-normalised log2 expression, a Welch two-sample t-test per gene, and
Benjamini-Hochberg FDR, then writes a standard DEG table.  It is fully
deterministic (no randomness) and depends only on numpy, so a third party can
re-run it from the reproduction bundle and obtain identical numbers.

The method *never* asserts anything beyond an RNA-level association — its
MethodContract caps ``claim_capability`` at ``association``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from ._stats import benjamini_hochberg, welch_t_test

METHOD_ID = "bulk_deg"
METHOD_VERSION = "0.1.0"
METHOD_CONTRACT_ID = f"method_contract_{METHOD_ID}_{METHOD_VERSION}"


class BulkDegMethod:
    """Adapter implementing ``ports.AnalysisMethodPort`` for bulk DEG."""

    method_id = METHOD_ID
    version = METHOD_VERSION

    def contract(self) -> dict[str, Any]:
        return {
            "method_contract_id": METHOD_CONTRACT_ID,
            "method_id": METHOD_ID,
            "version": METHOD_VERSION,
            "scientific_purpose": "Identify genes whose bulk RNA expression differs between two sample groups.",
            "accepted_input_types": ["bulk_expression_matrix"],
            "required_metadata": ["sample_group_labels"],
            "minimum_sample_design": {"groups": 2, "min_replicates_per_group": 2},
            "statistical_unit": "sample",
            "required_qc": ["execution", "data", "statistical", "biological"],
            "parameters": {
                "significance_alpha": 0.05,
                "log2fc_threshold": 1.0,
                "random_seed": 0,
            },
            "expected_outputs": ["deg_results_table"],
            "known_limitations": [
                "RNA differential expression is association-level evidence only.",
                "Does not establish protein abundance, secretion, causality, or mechanism.",
            ],
            "forbidden_conditions": [
                "fewer than 2 replicates in any group",
                "a single comparison group",
                "interpreting results as protein/secretion or causal evidence",
            ],
            "claim_capability": "association",
            "implementation_reference": {"module": "auto_bioinfo.methods.bulk_deg", "version": METHOD_VERSION},
        }

    def run(self, *, inputs: dict[str, str], params: dict[str, Any], out_dir: str) -> dict[str, Any]:
        contract = self.contract()
        merged_params = {**contract["parameters"], **(params or {})}
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        genes, sample_names, matrix = _read_matrix(inputs["counts"])
        sample_to_group = _read_sample_groups(inputs["samples"])
        groups = _ordered_groups(sample_names, sample_to_group, merged_params)

        # --- hard precondition: minimum design (mirrors the MethodContract) ---
        design = contract["minimum_sample_design"]
        group_sizes = {g: len(idx) for g, idx in groups.items()}
        if len(groups) < design["groups"] or any(n < design["min_replicates_per_group"] for n in group_sizes.values()):
            return {
                "status": "precondition_failed",
                "reason": f"minimum design not met: groups={group_sizes}, "
                f"need >= {design['groups']} groups with >= {design['min_replicates_per_group']} replicates each",
                "method_id": METHOD_ID,
                "version": METHOD_VERSION,
                "group_sizes": group_sizes,
                "params": merged_params,
                "software_versions": _software_versions(),
            }

        group_a, group_b = list(groups.keys())[:2]
        idx_a, idx_b = groups[group_a], groups[group_b]

        # CPM normalise then log2(CPM + 1); deterministic.
        lib_sizes = matrix.sum(axis=0)
        lib_sizes[lib_sizes == 0] = 1.0
        cpm = matrix / lib_sizes * 1e6
        logcpm = np.log2(cpm + 1.0)

        rows: list[dict[str, Any]] = []
        p_values: list[float] = []
        for gi, gene in enumerate(genes):
            a_vals = logcpm[gi, idx_a]
            b_vals = logcpm[gi, idx_b]
            stat = welch_t_test(a_vals, b_vals)
            rows.append(
                {
                    "gene": gene,
                    "mean_logcpm_a": round(stat["mean_a"], 6),
                    "mean_logcpm_b": round(stat["mean_b"], 6),
                    "log2_fold_change": round(stat["mean_diff"], 6),
                    "t_stat": round(stat["t"], 6),
                    "df": round(stat["df"], 4),
                    "p_value": stat["p_value"],
                }
            )
            p_values.append(stat["p_value"])

        fdr = benjamini_hochberg(p_values)
        alpha = float(merged_params["significance_alpha"])
        lfc_thr = float(merged_params["log2fc_threshold"])
        n_sig = 0
        for row, q in zip(rows, fdr):
            row["fdr"] = round(q, 8)
            row["p_value"] = round(row["p_value"], 8)
            significant = (q < alpha) and (abs(row["log2_fold_change"]) >= lfc_thr)
            row["direction"] = "up_in_a" if row["log2_fold_change"] > 0 else "down_in_a"
            row["significant"] = bool(significant)
            n_sig += int(significant)

        # Stable ordering: by FDR then gene, so the output table is deterministic.
        rows.sort(key=lambda r: (r["fdr"], r["gene"]))
        output_path = out / "deg_results.tsv"
        _write_table(output_path, rows)

        return {
            "status": "succeeded",
            "method_id": METHOD_ID,
            "version": METHOD_VERSION,
            "output_path": str(output_path),
            "outputs": {"deg_results_table": str(output_path)},
            "group_a": group_a,
            "group_b": group_b,
            "group_sizes": group_sizes,
            "n_genes": len(genes),
            "n_significant": n_sig,
            "params": merged_params,
            "software_versions": _software_versions(),
            "claim_capability": contract["claim_capability"],
        }


# --- IO helpers (numpy-only, no pandas) -------------------------------------

def _read_matrix(path: str) -> tuple[list[str], list[str], np.ndarray]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        sample_names = header[1:]
        genes: list[str] = []
        data: list[list[float]] = []
        for row in reader:
            if not row:
                continue
            genes.append(row[0])
            data.append([float(v) for v in row[1:]])
    return genes, sample_names, np.asarray(data, dtype=float)


def _read_sample_groups(path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        cols = {name: i for i, name in enumerate(header)}
        if "sample" not in cols or "group" not in cols:
            raise ValueError("samples table must have 'sample' and 'group' columns")
        for row in reader:
            if row:
                mapping[row[cols["sample"]]] = row[cols["group"]]
    return mapping


def _ordered_groups(sample_names: list[str], sample_to_group: dict[str, str], params: dict[str, Any]) -> dict[str, list[int]]:
    """Map group label -> column indices, preserving first-seen group order."""
    groups: dict[str, list[int]] = {}
    for col, name in enumerate(sample_names):
        group = sample_to_group.get(name)
        if group is None:
            raise ValueError(f"sample {name!r} in matrix has no group label")
        groups.setdefault(group, []).append(col)
    # Honour explicit contrast if the caller pinned group_a / group_b.
    pinned = [params.get("group_a"), params.get("group_b")]
    if all(p in groups for p in pinned if p):
        ordered = {p: groups[p] for p in pinned if p}
        for g, idx in groups.items():
            ordered.setdefault(g, idx)
        return ordered
    return groups


def _write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["gene", "mean_logcpm_a", "mean_logcpm_b", "log2_fold_change", "t_stat", "df", "p_value", "fdr", "direction", "significant"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in fields})


def _software_versions() -> dict[str, str]:
    return {"python_method": f"{METHOD_ID}/{METHOD_VERSION}", "numpy": np.__version__}
