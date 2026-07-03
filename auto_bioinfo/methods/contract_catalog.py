"""Offline MethodContract catalog + machine-readable compatibility rules (WP-11).

This is the *scientific boundary* half of stage 8.  It promotes the seven
requirement-spec methods (T-11-06..T-11-12) to structured
:class:`auto_bioinfo.core.schemas.MethodContract` objects and pairs each with a
small, machine-readable :class:`MethodRule` the deterministic compatibility
evaluator (:mod:`auto_bioinfo.methods.compatibility`) reads.  A MethodContract
*describes* what a method may do; a MethodRule encodes the *hard conditions* the
evaluator checks against a dataset profile — the two stay separate exactly as the
existing :mod:`auto_bioinfo.methods.registry` keeps a contract dict beside a
``minimum_sample_design`` fact.

Everything here is a pure, deterministic, offline value: no I/O, no clock read,
no network, no randomness.  A contract only bounds a method; it never selects,
executes, or authorises one — that authority lives with the registry admission
gate, the compatibility decision, and (much later) an execution authorization.
The catalog reuses the existing ``bulk_deg`` contract verbatim for the
``bulk_deg`` entry so the golden numbers (T-11-06) never drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.schemas import MethodContract

# --- Statistical-unit vocabulary (bounded) -----------------------------------
# The unit of replication a method's statistics are computed over.  A method that
# requires ``donor`` (or ``sample``) can never be satisfied by ``cell``-level
# pseudo-replication (T-11-04/T-11-07).
STAT_UNIT_SAMPLE = "sample"
STAT_UNIT_DONOR = "donor"
STAT_UNIT_CELL = "cell"
STAT_UNITS = (STAT_UNIT_SAMPLE, STAT_UNIT_DONOR, STAT_UNIT_CELL)


@dataclass(frozen=True)
class MethodRule:
    """The machine-readable hard conditions the compatibility evaluator checks.

    Every field is an explicit fact the evaluator compares against a dataset
    profile; nothing here is inferred.  ``accepted_modalities`` gates the input
    type; ``required_statistical_unit`` gates the unit of replication so
    cell-level pseudo-replication can never masquerade as donor/sample-level
    evidence; ``min_groups`` / ``min_replicates_per_group`` gate the minimum
    design; ``required_metadata_keys`` are profile facts that must be present;
    ``requires_gene_universe`` / ``requires_independent_datasets`` /
    ``requires_annotation_version`` encode the method-specific gates
    (enrichment background set, cross-dataset independence, annotation version).
    ``claim_capability`` is the hard ceiling the method's evidence can ever
    support.
    """

    accepted_modalities: tuple[str, ...]
    required_statistical_unit: str
    claim_capability: str
    min_groups: int = 2
    min_replicates_per_group: int = 2
    required_metadata_keys: tuple[str, ...] = ()
    requires_gene_universe: bool = False
    requires_independent_datasets: bool = False
    requires_annotation_version: bool = False
    forbidden_statistical_units: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogEntry:
    """A MethodContract paired with its machine-readable MethodRule."""

    contract: MethodContract
    rule: MethodRule
    contract_id: str = field(default="")

    def contract_dict(self) -> dict[str, Any]:
        return self.contract.to_dict()


# The exact bulk_deg contract fields already committed in
# ``auto_bioinfo.methods.bulk_deg`` (kept identical so the golden test is stable).
_BULK_DEG_VERSION = "0.1.0"


def _bulk_deg_contract() -> MethodContract:
    return MethodContract(
        method_id="bulk_deg",
        method_name="Bulk RNA differential expression",
        version=_BULK_DEG_VERSION,
        scientific_purpose="Identify genes whose bulk RNA expression differs between two sample groups.",
        supported_modalities=["bulk_expression_matrix"],
        required_inputs=["bulk_expression_matrix"],
        required_metadata=["sample_group_labels"],
        minimum_design_facts=["two comparison groups", "at least two replicates per group", "statistical unit is the sample"],
        outputs=["deg_results_table"],
        statistical_assumptions=["independent samples", "approximately continuous log-CPM expression"],
        required_qc=["execution", "data", "statistical", "biological"],
        known_limitations=[
            "RNA differential expression is association-level evidence only.",
            "Does not establish protein abundance, secretion, causality, or mechanism.",
        ],
        claim_capability="association",
        claim_ceiling="association",
        applicable_conditions=["two-group bulk expression comparison with >=2 replicates per group"],
        forbidden_conditions=[
            "fewer than 2 replicates in any group",
            "a single comparison group",
            "interpreting results as protein/secretion or causal evidence",
        ],
    )


def _scrna_pseudobulk_contract() -> MethodContract:
    return MethodContract(
        method_id="scrna_pseudobulk_deg",
        method_name="Single-cell pseudobulk differential expression",
        version="0.1.0",
        scientific_purpose="Compare cell-type expression between conditions after aggregating to donor-level pseudobulk.",
        supported_modalities=["single_cell_expression_matrix"],
        required_inputs=["single_cell_expression_matrix"],
        required_metadata=["donor_labels", "cell_type_labels", "condition_labels"],
        minimum_design_facts=["donor-level statistical unit", "at least two donors per condition"],
        outputs=["pseudobulk_deg_results_table"],
        statistical_assumptions=["donors are the independent unit", "cells within a donor are not independent replicates"],
        required_qc=["execution", "data", "statistical", "biological"],
        known_limitations=[
            "Cell-level pseudo-replication inflates significance and is not valid.",
            "Association-level evidence only.",
        ],
        claim_capability="association",
        claim_ceiling="association",
        applicable_conditions=["donor-level pseudobulk comparison with >=2 donors per condition"],
        forbidden_conditions=[
            "using individual cells as statistical replicates (pseudo-replication)",
            "fewer than 2 donors per condition",
        ],
    )


def _gene_set_score_contract() -> MethodContract:
    return MethodContract(
        method_id="gene_set_score",
        method_name="Gene-set / pathway scoring",
        version="0.1.0",
        scientific_purpose="Summarise expression of a predefined gene set into a per-sample score.",
        supported_modalities=["bulk_expression_matrix", "single_cell_expression_matrix"],
        required_inputs=["expression_matrix", "gene_set_definition"],
        required_metadata=["sample_group_labels"],
        minimum_design_facts=["a predefined gene set", "at least two samples"],
        outputs=["gene_set_score_table"],
        statistical_assumptions=["the gene set is defined a priori, not selected from the same data"],
        required_qc=["execution", "data", "statistical"],
        known_limitations=[
            "A score summarises expression; it cannot by itself prove aging, causality, or mechanism.",
        ],
        claim_capability="descriptive",
        claim_ceiling="association",
        applicable_conditions=["scoring a predefined gene set across samples"],
        forbidden_conditions=[
            "claiming a mechanism or aging conclusion from a score alone",
            "defining the gene set from the same data it scores",
        ],
    )


def _enrichment_contract() -> MethodContract:
    return MethodContract(
        method_id="enrichment",
        method_name="Gene-set enrichment / over-representation",
        version="0.1.0",
        scientific_purpose="Test whether a gene list is enriched for annotated categories against a background universe.",
        supported_modalities=["gene_list"],
        required_inputs=["gene_list", "gene_universe"],
        required_metadata=["annotation_database_version"],
        minimum_design_facts=["an explicit background gene universe", "a multiple-testing correction"],
        outputs=["enrichment_results_table"],
        statistical_assumptions=["the background universe is the correct reference set", "tests are multiplicity-corrected"],
        required_qc=["execution", "data", "statistical"],
        known_limitations=[
            "Enrichment is association-level and depends entirely on the chosen universe.",
        ],
        claim_capability="association",
        claim_ceiling="association",
        applicable_conditions=["over-representation test with an explicit universe and multiple-testing correction"],
        forbidden_conditions=[
            "running enrichment without a defined background universe",
            "reporting uncorrected p-values as significant",
        ],
    )


def _differential_abundance_contract() -> MethodContract:
    return MethodContract(
        method_id="differential_abundance",
        method_name="Cell-type / compositional differential abundance",
        version="0.1.0",
        scientific_purpose="Compare cell-type or feature composition between conditions at the donor level.",
        supported_modalities=["single_cell_expression_matrix", "composition_table"],
        required_inputs=["composition_table"],
        required_metadata=["donor_labels", "condition_labels"],
        minimum_design_facts=["donor-level statistical unit", "at least two donors per condition"],
        outputs=["differential_abundance_table"],
        statistical_assumptions=["donors are the independent unit", "compositional constraints are accounted for"],
        required_qc=["execution", "data", "statistical", "biological"],
        known_limitations=["Association-level compositional evidence only."],
        claim_capability="association",
        claim_ceiling="association",
        applicable_conditions=["donor-level compositional comparison with >=2 donors per condition"],
        forbidden_conditions=[
            "using cells as statistical replicates",
            "fewer than 2 donors per condition",
        ],
    )


def _surface_secretome_contract() -> MethodContract:
    return MethodContract(
        method_id="surface_secretome_annotation",
        method_name="Surface / secretome annotation join",
        version="0.1.0",
        scientific_purpose="Annotate candidate genes with surface/secretome membership from a versioned annotation source.",
        supported_modalities=["gene_list"],
        required_inputs=["gene_list", "annotation_profile"],
        required_metadata=["annotation_database_version", "annotation_evidence_type"],
        minimum_design_facts=["a versioned annotation source", "recorded annotation evidence type"],
        outputs=["annotated_candidate_table"],
        statistical_assumptions=["annotation membership is a lookup, not an experimental measurement"],
        required_qc=["execution", "data"],
        known_limitations=[
            "Annotation is not experimental evidence of surface localisation or secretion.",
        ],
        claim_capability="descriptive",
        claim_ceiling="candidate_biomarker",
        applicable_conditions=["annotating candidates from a versioned surface/secretome source"],
        forbidden_conditions=[
            "labelling an annotation as experimental secretion evidence",
            "using an unversioned annotation source",
        ],
    )


def _cross_dataset_concordance_contract() -> MethodContract:
    return MethodContract(
        method_id="cross_dataset_concordance",
        method_name="Cross-dataset concordance / replication",
        version="0.1.0",
        scientific_purpose="Assess whether an effect replicates in an independent dataset with mapped identifiers.",
        supported_modalities=["deg_results_table"],
        required_inputs=["primary_result_table", "independent_result_table"],
        required_metadata=["dataset_independence", "id_mapping"],
        minimum_design_facts=["two independent datasets", "an identifier mapping", "a defined effect direction"],
        outputs=["concordance_report_table"],
        statistical_assumptions=["the two datasets are independent samples of the same question"],
        required_qc=["execution", "data", "statistical"],
        known_limitations=[
            "Re-analysing the same dataset is not replication.",
        ],
        claim_capability="association",
        claim_ceiling="candidate_biomarker",
        applicable_conditions=["concordance between two genuinely independent datasets with mapped ids"],
        forbidden_conditions=[
            "treating a re-analysis of the same dataset as independent replication",
            "comparing effects without an identifier mapping",
        ],
    )


def _build_catalog() -> dict[str, CatalogEntry]:
    entries: list[tuple[MethodContract, MethodRule]] = [
        (
            _bulk_deg_contract(),
            MethodRule(
                accepted_modalities=("bulk_expression_matrix",),
                required_statistical_unit=STAT_UNIT_SAMPLE,
                claim_capability="association",
                required_metadata_keys=("sample_group_labels",),
                forbidden_statistical_units=(STAT_UNIT_CELL,),
            ),
        ),
        (
            _scrna_pseudobulk_contract(),
            MethodRule(
                accepted_modalities=("single_cell_expression_matrix",),
                required_statistical_unit=STAT_UNIT_DONOR,
                claim_capability="association",
                required_metadata_keys=("donor_labels", "cell_type_labels", "condition_labels"),
                forbidden_statistical_units=(STAT_UNIT_CELL,),
            ),
        ),
        (
            _gene_set_score_contract(),
            MethodRule(
                accepted_modalities=("bulk_expression_matrix", "single_cell_expression_matrix"),
                required_statistical_unit=STAT_UNIT_SAMPLE,
                claim_capability="descriptive",
                min_groups=1,
                min_replicates_per_group=2,
                required_metadata_keys=("sample_group_labels",),
            ),
        ),
        (
            _enrichment_contract(),
            MethodRule(
                accepted_modalities=("gene_list",),
                required_statistical_unit=STAT_UNIT_SAMPLE,
                claim_capability="association",
                min_groups=1,
                min_replicates_per_group=1,
                required_metadata_keys=("annotation_database_version",),
                requires_gene_universe=True,
            ),
        ),
        (
            _differential_abundance_contract(),
            MethodRule(
                accepted_modalities=("single_cell_expression_matrix", "composition_table"),
                required_statistical_unit=STAT_UNIT_DONOR,
                claim_capability="association",
                required_metadata_keys=("donor_labels", "condition_labels"),
                forbidden_statistical_units=(STAT_UNIT_CELL,),
            ),
        ),
        (
            _surface_secretome_contract(),
            MethodRule(
                accepted_modalities=("gene_list",),
                required_statistical_unit=STAT_UNIT_SAMPLE,
                claim_capability="descriptive",
                min_groups=1,
                min_replicates_per_group=1,
                required_metadata_keys=("annotation_database_version", "annotation_evidence_type"),
                requires_annotation_version=True,
            ),
        ),
        (
            _cross_dataset_concordance_contract(),
            MethodRule(
                accepted_modalities=("deg_results_table",),
                required_statistical_unit=STAT_UNIT_SAMPLE,
                claim_capability="association",
                min_groups=1,
                min_replicates_per_group=1,
                required_metadata_keys=("dataset_independence", "id_mapping"),
                requires_independent_datasets=True,
            ),
        ),
    ]
    catalog: dict[str, CatalogEntry] = {}
    for contract, rule in entries:
        # Inert, deterministic fixtures: no wall-clock timestamp, so byte-identical
        # catalogs are produced on every call.
        contract.created_at = ""
        contract_id = contract.to_dict()["method_contract_id"]
        catalog[contract.method_id] = CatalogEntry(contract=contract, rule=rule, contract_id=contract_id)
    return catalog


# The method ids the catalog ships, in a stable order (deterministic iteration).
CATALOG_METHOD_IDS = (
    "bulk_deg",
    "scrna_pseudobulk_deg",
    "gene_set_score",
    "enrichment",
    "differential_abundance",
    "surface_secretome_annotation",
    "cross_dataset_concordance",
)


def build_contract_catalog() -> dict[str, CatalogEntry]:
    """Return ``{method_id: CatalogEntry}`` for all seven catalog methods.

    A fresh dict of frozen values on every call, so a caller can never mutate the
    shared catalog.  Deterministic: the same contracts and contract ids every
    time.
    """
    return _build_catalog()


def get_catalog_entry(method_id: str) -> CatalogEntry:
    catalog = build_contract_catalog()
    if method_id not in catalog:
        raise KeyError(f"unknown catalog method_id: {method_id} (known: {sorted(catalog)})")
    return catalog[method_id]


__all__ = [
    "STAT_UNIT_SAMPLE",
    "STAT_UNIT_DONOR",
    "STAT_UNIT_CELL",
    "STAT_UNITS",
    "MethodRule",
    "CatalogEntry",
    "CATALOG_METHOD_IDS",
    "build_contract_catalog",
    "get_catalog_entry",
]
