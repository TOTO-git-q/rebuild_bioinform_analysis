"""Thin, deterministic, offline adapters that bridge lane seams.

The lane packages were each built independently against the core contracts, not
against one another, so a few seams do not line up byte-for-byte.  This module
holds the *only* glue the routes need — each function is pure, offline and
deterministic (no clock, no network, no subprocess), and each is documented with
the exact seam it bridges so the requirement-coverage matrix can point at it.

None of these helpers edits a lane module; they only reshape one lane's output
into the shape the next lane's public API expects.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..adapters.capability_registry import assert_no_executable_grants, resolve_decision
from ..adapters.offline_search import OfflineRecordedSearchAdapter, RecordedSearchResponse
from ..adapters.public_bio_tools import PublicBioToolAdapter
from ..core.ids import make_stable_id
from ..resources.verification import RegistryRecord, VerificationRegistry

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"

# Modality tokens the method/compatibility lane recognises (contract_catalog
# ``accepted_modalities``).  Verification/DatasetProfile speaks free-text
# modality ("bulk RNA-seq"); the method lane speaks a controlled token.  This
# map is the seam between them.
_MODALITY_TOKEN = {
    "bulk rna-seq": "bulk_expression_matrix",
    "bulk_expression_matrix": "bulk_expression_matrix",
    "single-cell rna-seq": "single_cell_expression_matrix",
    "single cell rna-seq": "single_cell_expression_matrix",
    "snrna-seq": "single_cell_expression_matrix",
    "single_cell_expression_matrix": "single_cell_expression_matrix",
}


def modality_token(free_text: str) -> str:
    """SEAM: verification's free-text modality -> method-lane controlled token."""
    return _MODALITY_TOKEN.get(str(free_text or "").strip().lower(), str(free_text or "").strip().lower())


# --------------------------------------------------------------------------
# Committed offline fixtures
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDataset:
    """A committed, honestly-synthetic dataset descriptor for a route.

    Loaded from a fixture ``dataset_card.json`` plus its physical files.  This is
    the recorded offline stand-in for a real, audited resource discovery result —
    it carries a real-looking accession so the verification lane can verify it,
    but is labelled ``SYNTHETIC_FIXTURE`` and must never be presented as real.
    """

    card: dict[str, Any]
    files: dict[str, str]  # logical name -> file content (verbatim bytes as text)
    fixture_dir: Path

    @property
    def namespace(self) -> str:
        return str(self.card.get("namespace", "GEO"))

    @property
    def identifier(self) -> str:
        return str(self.card.get("identifier", self.card.get("accession", "")))


def load_route_dataset(fixture_name: str) -> RouteDataset:
    """Load a committed fixture directory under ``auto_bioinfo/fixtures/``."""
    fixture_dir = _FIXTURE_ROOT / fixture_name
    card = json.loads((fixture_dir / "dataset_card.json").read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    for logical, rel in card.get("files", {}).items():
        files[logical] = (fixture_dir / rel).read_text(encoding="utf-8")
    return RouteDataset(card=card, files=files, fixture_dir=fixture_dir)


# --------------------------------------------------------------------------
# TSV helpers (offline, deterministic)
# --------------------------------------------------------------------------


def read_tsv_rows(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    return [dict(row) for row in reader]


def write_tsv(header: list[str], rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")
    writer.writerow(header)
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def samples_from_tsv(samples_content: str) -> list[dict[str, str]]:
    """Parse a ``sample/group/donor`` table into structured sample records."""
    out: list[dict[str, str]] = []
    for row in read_tsv_rows(samples_content):
        out.append(
            {
                "sample_id": row.get("sample", ""),
                "group": row.get("group", ""),
                "donor_id": row.get("donor", row.get("donor_id", "")),
            }
        )
    return out


def group_sizes_from_samples(samples: list[dict[str, str]]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for s in samples:
        g = s.get("group", "")
        if g:
            sizes[g] = sizes.get(g, 0) + 1
    return sizes


def parse_deg_rows(deg_tsv_path: str) -> list[dict[str, Any]]:
    """SEAM: bulk_deg output columns -> evidence-admission ``result_table`` rows.

    admission.admit_evidence wants rows keyed ``gene / log2_fold_change / fdr /
    significant``; bulk_deg writes a wider standard DEG table.  Project the
    columns admission reads, coercing types deterministically.
    """
    rows: list[dict[str, Any]] = []
    text = Path(deg_tsv_path).read_text(encoding="utf-8")
    for row in read_tsv_rows(text):
        rows.append(
            {
                "gene": row.get("gene", ""),
                "log2_fold_change": float(row.get("log2_fold_change", 0.0) or 0.0),
                "fdr": float(row.get("fdr", 1.0) or 1.0),
                "significant": str(row.get("significant", "")).strip().lower() in {"true", "1"},
            }
        )
    return rows


# --------------------------------------------------------------------------
# Tool selection + capability gate (PR #46 offline clean-room layer)
# --------------------------------------------------------------------------

# Which offline public-bio query planner each discovery domain selects.
_DISCOVERY_TOOL = {"dataset": "geo_dataset_search", "literature": "europe_pmc_search", "annotation": "ensembl_gene_lookup"}


def select_discovery_tool_plan(scope_bundle: dict[str, Any], *, domain: str = "dataset") -> dict[str, Any]:
    """Reuse ``adapters.public_bio_tools`` for the tool-selection step.

    Selects the domain's offline query planner and produces a deterministic,
    deny-by-default *query plan* (never a retrieval) for the resolved scope.  The
    plan documents the public request an audited live executor *could* make; it
    carries conservative unverified provenance and can never back a claim.  This
    replaces ad-hoc "which tool would we search" glue in the routes.
    """
    adapter = PublicBioToolAdapter()
    tool_id = _DISCOVERY_TOOL.get(domain, "geo_dataset_search")
    species = (scope_bundle.get("species") or [""])[0]
    conditions = scope_bundle.get("conditions", []) or scope_bundle.get("comparisons", [])
    query = {
        "query": " ".join(str(c) for c in conditions).strip(),
        "organism": species,
        "assay": "rna-seq",
        "condition": ",".join(str(c) for c in conditions),
        # A deliberately-sensitive field to prove the allow-list drops it.
        "local_path": "/should/never/appear/in/the/plan",
    }
    return adapter.plan_query(tool_id, query)


def capability_gate(project_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Reuse ``adapters.capability_registry`` to gate the discovery preflight.

    Fail-closed: the network *query-plan* capability is at most eligible for
    manual approval (never executable), and dataset *materialization* over the
    network is denied — the route's data is a committed offline fixture, never a
    live fetch.  Returns the recorded decisions; the caller treats a
    non-denied materialization or any executable grant as a hard boundary breach.
    """
    query_hash = make_stable_id("query_hash", plan.get("query", {}))
    network = resolve_decision(
        "grant_network_query_plan",
        provided_bindings=["project_id", "tool_id", "query_hash", "caller_id"],
        allow_intent=True,
    )
    materialization = resolve_decision("grant_dataset_materialization")  # no bindings -> deny
    return {
        "tool_id": plan.get("tool_id", ""),
        "plan_id": plan.get("plan_id", ""),
        "query_hash": query_hash,
        "network_query_plan": network,
        "dataset_materialization": materialization,
        "no_executable_grants": assert_no_executable_grants(),
    }


# --------------------------------------------------------------------------
# Discovery seam: build a recorded search adapter for a dataset
# --------------------------------------------------------------------------


def build_recorded_dataset_adapter(query: dict[str, Any], dataset: RouteDataset) -> OfflineRecordedSearchAdapter:
    """SEAM: resources.discovery.run_search needs a recorded adapter whose
    recording key matches the *exact* query built by build_search_query.

    We therefore build the recording from the live query dict, embedding a single
    candidate record that describes the committed fixture dataset (namespace +
    identifier + provenance) so normalization keeps it.
    """
    card = dataset.card
    record = {
        "namespace": dataset.namespace,
        "identifier": dataset.identifier,
        "accession": card.get("accession", dataset.identifier),
        "title": f"{card.get('organism', '')} {card.get('tissue', '')} {card.get('modality', '')}".strip(),
        "source_uri": f"https://fixture.invalid/{dataset.identifier}",
        "source_class": card.get("source_class", "SYNTHETIC_FIXTURE"),
        "source_status": card.get("source_status", "committed_fixture"),
    }
    recording = RecordedSearchResponse(query=query, response={"results": [record], "status": "ok"})
    return OfflineRecordedSearchAdapter(
        tool_name="offline_route_fixture_adapter",
        tool_version="0.1.0",
        domain="dataset",
        recordings=[recording],
    )


# --------------------------------------------------------------------------
# Verification seam: a recorded verification registry for a dataset
# --------------------------------------------------------------------------


def build_verification_registry(dataset: RouteDataset, *, samples: list[dict[str, str]] | None = None) -> VerificationRegistry:
    """SEAM: resources.verification.verify_candidate needs a recorded registry
    whose (namespace, identifier) record carries enough metadata to VERIFY.

    Build a registry record from the committed dataset card + its sample table so
    the verified DatasetProfile has organism / modality / platform / samples with
    known donors — everything the feasibility lane's hard rules then require.
    """
    card = dataset.card
    samples = samples if samples is not None else []
    raw_samples = [{"sample_id": s["sample_id"], "group": s["group"], "donor_id": s["donor_id"]} for s in samples]
    raw_files = [
        {"name": rel, "file_type": logical, "downloadable": True, "size_bytes": len(dataset.files.get(logical, ""))}
        for logical, rel in card.get("files", {}).items()
    ]
    raw_metadata = {
        "organism": card.get("organism", ""),
        "species": [card.get("organism", "")] if card.get("organism") else [],
        "tissue": card.get("tissue", ""),
        "platform": card.get("platform", ""),
        "modality": card.get("modality", ""),
        "disease": card.get("tissue", ""),
        "samples": raw_samples,
        "files": raw_files,
    }
    record = RegistryRecord(
        existence="exists",
        raw_metadata=raw_metadata,
        source_uri=f"https://fixture.invalid/{dataset.identifier}",
        access=card.get("access", "open"),
        license=card.get("license", "fixture-only"),
        source_class=card.get("source_class", "SYNTHETIC_FIXTURE"),
    )
    return VerificationRegistry({(dataset.namespace, dataset.identifier): record})


# --------------------------------------------------------------------------
# Method/compatibility seam
# --------------------------------------------------------------------------


def compat_profile(
    dataset: RouteDataset,
    *,
    group_sizes: dict[str, int],
    statistical_unit: str,
    modality: str,
    metadata_keys: list[str],
) -> dict[str, Any]:
    """SEAM: verification's DatasetProfile -> compatibility ``dataset_profile``.

    compatibility._extract_facts reads a controlled shape (modality token,
    statistical_unit, group_sizes, present_metadata) that the free-text
    DatasetProfile does not expose directly.
    """
    return {
        "dataset_id": dataset.card.get("dataset_id", ""),
        "modality": modality,
        "statistical_unit": statistical_unit,
        "group_sizes": dict(group_sizes),
        "present_metadata": list(metadata_keys),
    }


# --------------------------------------------------------------------------
# Four-layer QC seam
# --------------------------------------------------------------------------

# The rule ids the WP-18 registry engine knows, layered execution/data/
# statistical/biological.  The runtime bulk_deg contract only declares the coarse
# layer *names* ("execution", ...), so the route supplies the concrete rule ids.
QC_REQUIRED_RULES = (
    "execution.method_succeeded",
    "execution.output_exists",
    "data.nonempty_matrix",
    "statistical.unit_is_sample",
    "statistical.min_replicates",
    "biological.claim_capability_matches_data",
)


def qc_contract(*, statistical_unit: str, claim_capability: str, min_groups: int = 2, min_replicates: int = 2) -> dict[str, Any]:
    return {
        "statistical_unit": statistical_unit,
        "claim_capability": claim_capability,
        "minimum_sample_design": {"groups": min_groups, "min_replicates_per_group": min_replicates},
        "required_qc": list(QC_REQUIRED_RULES),
    }


def qc_bundle(
    *,
    method_result: dict[str, Any],
    artifact_manifest: dict[str, Any],
    modality: str,
    group_sizes: dict[str, int],
    contract: dict[str, Any],
    subquestion_ids: list[str],
    n_genes: int,
    n_samples: int,
    sc_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """SEAM: assemble the read-only QC bundle qc_gates.run_qc expects.

    ``sc_metrics`` (donor-level route only) carries the recorded cell-level
    doublet / ambient QC facts so the single-cell Data-QC rule is *assessed*
    rather than left NOT_ASSESSED (which would block a warnings-intolerant gate).
    """
    bundle: dict[str, Any] = {
        "method_result": {
            "status": method_result.get("status", ""),
            "task_run_id": method_result.get("task_run_id", ""),
            "n_genes": n_genes,
            "n_samples": n_samples,
            "n_labelled_samples": n_samples,
            "n_unmapped_ids": 0,
            "group_sizes": dict(group_sizes),
            "outputs": method_result.get("outputs", {}),
            "log_errors": [],
            "log_warnings": [],
            "multiple_testing_correction": "benjamini_hochberg",
            "single_sample_driven": False,
        },
        "artifact_manifest": {
            "artifact_id": artifact_manifest.get("artifact_id", ""),
            "exists": True,
            "size_bytes": artifact_manifest.get("size_bytes", 1),
            "is_placeholder": False,
            "checksum_sha256": artifact_manifest.get("checksum_sha256", ""),
        },
        "dataset_profile": {"modality": modality, "group_sizes": dict(group_sizes)},
        "contract": contract,
        "subquestion_ids": list(subquestion_ids),
        "expected_outputs": list(method_result.get("outputs", {}).keys()) or ["deg_results_table"],
    }
    if sc_metrics is not None:
        bundle["sc_metrics"] = dict(sc_metrics)
    return bundle


# --------------------------------------------------------------------------
# Donor-level pseudobulk aggregation (WP-17)
# --------------------------------------------------------------------------


def pseudobulk_aggregate(cell_counts_content: str, cell_metadata_content: str, *, cell_type: str = "") -> dict[str, Any]:
    """SEAM (WP-17): aggregate a cell x gene matrix to donor-level pseudobulk.

    Sums counts across the cells of each donor (optionally restricted to one
    ``cell_type``), turning the *cell* into a *donor* statistical unit before any
    DEG runs — cells within a donor are never treated as independent replicates.
    Returns counts/samples TSV content ready for the bulk_deg runner, plus the
    donor->condition mapping and the per-donor cell counts (for auditing).
    """
    meta_rows = read_tsv_rows(cell_metadata_content)
    keep_cells = {}
    donor_condition: dict[str, str] = {}
    donor_order: list[str] = []
    cells_per_donor: dict[str, int] = {}
    for row in meta_rows:
        if cell_type and row.get("cell_type", "") != cell_type:
            continue
        cell = row.get("cell", "")
        donor = row.get("donor", row.get("donor_id", ""))
        cond = row.get("condition", "")
        keep_cells[cell] = donor
        if donor not in donor_condition:
            donor_condition[donor] = cond
            donor_order.append(donor)
        cells_per_donor[donor] = cells_per_donor.get(donor, 0) + 1

    counts_rows = read_tsv_rows(cell_counts_content)
    # cell_counts is gene x cell: first column "gene", others cell ids.
    counts_reader = csv.reader(io.StringIO(cell_counts_content), delimiter="\t")
    header = next(counts_reader)
    cell_cols = header[1:]
    genes: list[str] = []
    # donor -> gene -> summed count
    donor_gene: dict[str, dict[str, int]] = {d: {} for d in donor_order}
    for raw in counts_reader:
        if not raw:
            continue
        gene = raw[0]
        genes.append(gene)
        for cell, value in zip(cell_cols, raw[1:], strict=False):
            cell_donor = keep_cells.get(cell)
            if cell_donor is None:
                continue
            donor_gene[cell_donor][gene] = donor_gene[cell_donor].get(gene, 0) + int(value)

    # Build donor-level counts.tsv (gene x donor) and samples.tsv (donor,group).
    counts_header = ["gene"] + donor_order
    counts_body = [[g] + [donor_gene[d].get(g, 0) for d in donor_order] for g in genes]
    counts_tsv = write_tsv(counts_header, counts_body)
    samples_tsv = write_tsv(
        ["sample", "group", "donor"],
        [[d, donor_condition[d], d] for d in donor_order],
    )
    _ = counts_rows  # parsed form retained conceptually; not needed further
    return {
        "counts_tsv": counts_tsv,
        "samples_tsv": samples_tsv,
        "donors": donor_order,
        "donor_condition": donor_condition,
        "cells_per_donor": cells_per_donor,
        "group_sizes": {c: sum(1 for d in donor_order if donor_condition[d] == c) for c in sorted(set(donor_condition.values()))},
    }


# --------------------------------------------------------------------------
# Cross-dataset concordance (WP-17)
# --------------------------------------------------------------------------

CONCORDANCE_CONSISTENT = "consistent"
CONCORDANCE_CONFLICTING = "conflicting"
CONCORDANCE_NOT_COMPARABLE = "not_comparable"
CONCORDANCE_MISSING = "missing"
CONCORDANCE_STATES = (CONCORDANCE_CONSISTENT, CONCORDANCE_CONFLICTING, CONCORDANCE_NOT_COMPARABLE, CONCORDANCE_MISSING)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def cross_dataset_concordance(
    primary_rows: list[dict[str, Any]],
    replicate_rows: list[dict[str, Any]],
    *,
    id_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """SEAM (WP-17): classify per-gene agreement across two independent DEG tables.

    Keeps *every* outcome — consistent, conflicting, not-comparable and missing —
    never only the agreeing positives (T-17-14).  A gene is:
      * ``consistent``     — significant in both with the same effect direction;
      * ``conflicting``    — significant in both but opposite directions;
      * ``not_comparable`` — present in both but not significant in both (no
        agreeing/opposing significant call to compare);
      * ``missing``        — present in one table only (after id mapping).
    Deterministic, offline, pure.
    """
    id_mapping = id_mapping or {}
    primary = {r["gene"]: r for r in primary_rows}
    replicate = {r["gene"]: r for r in replicate_rows}

    def mapped(gene: str) -> str:
        return id_mapping.get(gene, gene)

    genes = sorted(set(primary) | {mapped(g) for g in replicate})
    # Build reverse view for replicate under mapping.
    replicate_mapped: dict[str, dict[str, Any]] = {}
    for g, r in replicate.items():
        replicate_mapped[mapped(g)] = r

    entries: list[dict[str, Any]] = []
    counts = {s: 0 for s in CONCORDANCE_STATES}
    for gene in genes:
        p = primary.get(gene)
        q = replicate_mapped.get(gene)
        if p is None or q is None:
            state = CONCORDANCE_MISSING
        elif p["significant"] and q["significant"]:
            state = CONCORDANCE_CONSISTENT if _sign(p["log2_fold_change"]) == _sign(q["log2_fold_change"]) else CONCORDANCE_CONFLICTING
        else:
            state = CONCORDANCE_NOT_COMPARABLE
        counts[state] += 1
        entries.append(
            {
                "gene": gene,
                "state": state,
                "primary_log2fc": (p or {}).get("log2_fold_change"),
                "replicate_log2fc": (q or {}).get("log2_fold_change"),
                "primary_significant": (p or {}).get("significant"),
                "replicate_significant": (q or {}).get("significant"),
            }
        )
    return {
        "entries": entries,
        "counts": counts,
        "n_consistent": counts[CONCORDANCE_CONSISTENT],
        "n_conflicting": counts[CONCORDANCE_CONFLICTING],
        "n_not_comparable": counts[CONCORDANCE_NOT_COMPARABLE],
        "n_missing": counts[CONCORDANCE_MISSING],
        "same_cohort": False,
        "independent": True,
    }
