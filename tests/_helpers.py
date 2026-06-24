"""Shared test helpers (offline, deterministic)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from auto_bioinfo.adapters.fixture_resources import FixtureResourceAdapter

DEMO_QUESTION = "Which genes are differentially expressed in tissue_x between condition_a and condition_b?"


def tiny_fixture(group_a_n: int = 3, group_b_n: int = 3) -> Path:
    """Write a tiny committed-style fixture with a chosen number of replicates."""
    base = Path(tempfile.mkdtemp()) / "fx"
    base.mkdir(parents=True)
    samples = ["sample\tgroup"]
    cols = []
    for i in range(group_a_n):
        cols.append(f"a{i}")
        samples.append(f"a{i}\tcondition_a")
    for i in range(group_b_n):
        cols.append(f"b{i}")
        samples.append(f"b{i}\tcondition_b")
    header = "gene\t" + "\t".join(cols)
    # Small within-group variation so the t-test is well-defined (non-degenerate).
    up_vals = [str(1000 + 30 * i) for i in range(group_a_n)] + [str(50 + 5 * i) for i in range(group_b_n)]
    flat_vals = [str(500 + 5 * i) for i in range(group_a_n)] + [str(500 + 4 * i) for i in range(group_b_n)]
    up = "GENE_UP\t" + "\t".join(up_vals)
    flat = "GENE_FLAT\t" + "\t".join(flat_vals)
    (base / "counts.tsv").write_text(header + "\n" + up + "\n" + flat + "\n", encoding="utf-8")
    (base / "samples.tsv").write_text("\n".join(samples) + "\n", encoding="utf-8")
    card = {
        "dataset_id": "FIXTURE_TINY",
        "accession": "FIXTURE-TINY",
        "source_status": "committed_fixture",
        "verified": True,
        "modality": "bulk_expression_matrix",
        "organism": "synthetic_fixture_organism",
        "tissue": "tissue_x",
        "platform": "synthetic",
        "files": {"counts": "counts.tsv", "samples": "samples.tsv"},
        "group_sizes": {"condition_a": group_a_n, "condition_b": group_b_n},
        "comparison_groups": ["condition_a", "condition_b"],
        "known_limitations": ["synthetic fixture"],
    }
    (base / "dataset_card.json").write_text(json.dumps(card), encoding="utf-8")
    return base


def fixture_adapter(group_a_n: int = 3, group_b_n: int = 3) -> FixtureResourceAdapter:
    return FixtureResourceAdapter(fixture_dir=tiny_fixture(group_a_n, group_b_n))
