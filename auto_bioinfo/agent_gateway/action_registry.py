"""Unified biomedical action / connector registry (WP-28B1).

The single source of truth from which an agent **discovers** which biomedical
actions exist, what they need, what they may claim, and who may use them —
*without ever executing one*.  It is the project-native, clean-room translation
of the "declarative action registration" concept described in
``docs/architecture/biomni_cleanroom_integration.md``: the shape is reimplemented
against this repository's own contracts (:mod:`auto_bioinfo.core.agent_specs`,
:mod:`auto_bioinfo.agent_gateway.tool_broker`,
:mod:`auto_bioinfo.adapters.public_bio_tools`); no reference implementation is
imported, vendored, executed, or relied on at runtime.

What this module *is*
---------------------

* A **static catalogue of two kinds of fact**:

  1. :data:`CONNECTOR_INVENTORY` — the 24 recovered biomedical connector
     *surfaces* (19 ``local_stdio_bio_runner`` / 4 ``hosted_streamable_http`` /
     1 ``inline_connector``), carried forward as **inventory provenance only**.
     A connector entry is a name and a transport class.  It is *not* an
     endpoint, a schema, a license grant, an attachment, or a capability.
  2. :data:`ActionDescriptor` — the actions this project actually implements.
     Today that is exactly the 12 offline query planners owned by
     :class:`~auto_bioinfo.adapters.public_bio_tools.PublicBioToolAdapter`.
     Connectors without a project-native implementation stay
     ``inventory_only`` and expose **no** action; parity is never fabricated.

* **Pure, deterministic, offline, fail-closed.**  Building the registry is a
  total function of this module's literals plus the planner catalogue.  Listing,
  getting and filtering are deterministic and stably ordered.  Every uncertainty
  raises :class:`ActionRegistryError` at construction time — there is no
  fallback, no "closest match", and no default action.

What this module deliberately is **not**
----------------------------------------

* It holds **no handler, callable, endpoint, credential, or transport client**.
  A descriptor is inert data (:meth:`ActionDescriptor.to_dict` is JSON-safe).
  Discovery is not execution: nothing here retrieves, downloads, materializes,
  opens a socket, spawns a subprocess, imports MCP, touches the environment or
  the filesystem, reads a clock, or calls an LLM.
* A descriptor is **not evidence and not a verification**.  Every current entry
  is ``verification_status="unverified"``,
  ``scientific_output_eligible=False``, ``license_status="unreviewed"``, and
  carries the most conservative claim ceiling.  Being *listed* grants a
  connector nothing.

Recovered-inventory provenance warning
--------------------------------------

The connector ids, display names, ``mcp_*`` aliases and transport classes below
are **recovered facts from a source audit**, not official-documentation-verified
facts.  They are admitted solely as compatibility requirements so that a future
slice can be checked against the surface that was actually observed.  Endpoint
URLs, request/response schemas, terms assertions and license assertions from the
source pack are deliberately **not** carried over; they require a separate
public-docs-only review before any live use (see WP-28B2/B3).

Reserved seams (explicitly not implemented here)
------------------------------------------------

Live transports and the ToolBroker execution envelope (WP-28B2), independently
written public API adapters (WP-28B3), plan-act-observe-reflect orchestration
(WP-28B4) and the MCP list/describe/call bridge (WP-28B5) are out of scope.
Live API calls, external LLMs, real human-source data, paid services, public
deployment and credential/license acceptance remain point-of-action hard stops.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ..adapters.public_bio_tools import (
    EXECUTION_MODE_OFFLINE_QUERY_PLAN,
    PublicBioToolAdapter,
    PublicBioToolSpec,
)
from ..core.agent_specs import build_agent_specs
from ..core.schemas import CLAIM_LEVELS

# --- Bounds ------------------------------------------------------------------
# Fail-closed guards: an input past a bound is *malformed*, never truncated.
MAX_ID_LENGTH = 200
MAX_TEXT_LENGTH = 2_000
MAX_PARAMETERS = 32
MAX_LIST_ITEMS = 64


class ActionRegistryError(ValueError):
    """Raised when a descriptor, connector, or registry invariant fails closed."""


class UnknownActionError(KeyError):
    """Raised when an action id is not registered.  The registry never falls back."""


class UnknownConnectorError(KeyError):
    """Raised when a connector id is not in the inventory.  No fallback."""


# --- Transport classes (recovered inventory vocabulary) ----------------------
# These name *how the source pack attached a surface*, nothing this project runs.
TRANSPORT_LOCAL_STDIO = "local_stdio_bio_runner"
TRANSPORT_HOSTED_HTTP = "hosted_streamable_http"
TRANSPORT_INLINE = "inline_connector"

TRANSPORT_CLASSES = (TRANSPORT_LOCAL_STDIO, TRANSPORT_HOSTED_HTTP, TRANSPORT_INLINE)

# The transport split the audit recorded.  Asserted by the registry so a silent
# inventory drift cannot pass review.
EXPECTED_TRANSPORT_COUNTS: dict[str, int] = {
    TRANSPORT_LOCAL_STDIO: 19,
    TRANSPORT_HOSTED_HTTP: 4,
    TRANSPORT_INLINE: 1,
}
EXPECTED_CONNECTOR_COUNT = 24

# --- Implementation status ---------------------------------------------------
# ``inventory_only`` is the honest default: the surface was observed, this
# project implements nothing for it, and it must never look like parity.
IMPLEMENTATION_INVENTORY_ONLY = "inventory_only"
IMPLEMENTATION_PROJECT_NATIVE = "project_native"

IMPLEMENTATION_STATUSES = (IMPLEMENTATION_INVENTORY_ONLY, IMPLEMENTATION_PROJECT_NATIVE)

# --- Action categories -------------------------------------------------------
CATEGORY_OMICS_ARCHIVE = "omics_archive"
CATEGORY_LITERATURE = "literature"
CATEGORY_GENE_ANNOTATION = "gene_annotation"
CATEGORY_PROTEIN_ANNOTATION = "protein_annotation"
CATEGORY_PATHWAY = "pathway"
CATEGORY_INTERACTION_NETWORK = "network"
CATEGORY_ENRICHMENT = "enrichment"
CATEGORY_STRUCTURE = "structure"
CATEGORY_VARIANT = "variant"
CATEGORY_EXPRESSION = "expression"
CATEGORY_REGULATION = "regulation"
CATEGORY_CHEMISTRY = "chemistry"
CATEGORY_CLINICAL = "clinical"
CATEGORY_CANCER_MODELS = "cancer_models"
CATEGORY_HUMAN_GENETICS = "human_genetics"
CATEGORY_RNA = "rna"
CATEGORY_CELL_TYPES = "cell_types"
CATEGORY_RESEARCH_RESOURCES = "research_resources"
CATEGORY_AUTHORING_TOOL = "authoring_tool"

CATEGORIES = (
    CATEGORY_AUTHORING_TOOL,
    CATEGORY_CANCER_MODELS,
    CATEGORY_CELL_TYPES,
    CATEGORY_CHEMISTRY,
    CATEGORY_CLINICAL,
    CATEGORY_ENRICHMENT,
    CATEGORY_EXPRESSION,
    CATEGORY_GENE_ANNOTATION,
    CATEGORY_HUMAN_GENETICS,
    CATEGORY_INTERACTION_NETWORK,
    CATEGORY_LITERATURE,
    CATEGORY_OMICS_ARCHIVE,
    CATEGORY_PATHWAY,
    CATEGORY_PROTEIN_ANNOTATION,
    CATEGORY_REGULATION,
    CATEGORY_RESEARCH_RESOURCES,
    CATEGORY_RNA,
    CATEGORY_STRUCTURE,
    CATEGORY_VARIANT,
)

# --- Execution kinds ---------------------------------------------------------
# ``offline_query_plan`` is the only kind any *current* descriptor may use: the
# action is a pure function that returns the public request it *would* make.
# The other two are declared so a later slice cannot invent a new vocabulary,
# but no descriptor uses them yet and the registry holds no way to run them.
EXECUTION_KIND_OFFLINE_QUERY_PLAN = EXECUTION_MODE_OFFLINE_QUERY_PLAN
EXECUTION_KIND_LIVE_RETRIEVAL = "live_retrieval"
EXECUTION_KIND_LOCAL_COMPUTE = "local_compute"

EXECUTION_KINDS = (
    EXECUTION_KIND_OFFLINE_QUERY_PLAN,
    EXECUTION_KIND_LIVE_RETRIEVAL,
    EXECUTION_KIND_LOCAL_COMPUTE,
)

# Kinds that would actually *do* something outside a pure function.  These carry
# the "required facts" burden below (verification + license + approval gate).
EXECUTABLE_KINDS = (EXECUTION_KIND_LIVE_RETRIEVAL, EXECUTION_KIND_LOCAL_COMPUTE)

# --- Risk levels (ordered, least → most) -------------------------------------
RISK_NONE = "none"
RISK_LOW = "low"
RISK_MODERATE = "moderate"
RISK_HIGH = "high"

RISK_LEVELS = (RISK_NONE, RISK_LOW, RISK_MODERATE, RISK_HIGH)

# --- Verification / license / provenance vocabularies ------------------------
# Deliberately conservative: nothing in this slice may reach a "verified" state,
# because verification requires public-docs review and recorded contract tests
# that do not exist yet.
VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_NEEDS_PUBLIC_DOCS = "needs_public_docs_verification"
VERIFICATION_PUBLIC_DOCS_VERIFIED = "public_docs_verified"
VERIFICATION_CONTRACT_TESTED = "contract_tested"

VERIFICATION_STATUSES = (
    VERIFICATION_UNVERIFIED,
    VERIFICATION_NEEDS_PUBLIC_DOCS,
    VERIFICATION_PUBLIC_DOCS_VERIFIED,
    VERIFICATION_CONTRACT_TESTED,
)
# The only statuses that may back a scientifically eligible executable action.
VERIFIED_STATUSES = (VERIFICATION_PUBLIC_DOCS_VERIFIED, VERIFICATION_CONTRACT_TESTED)

LICENSE_UNREVIEWED = "unreviewed"
LICENSE_PROJECT_NATIVE = "project_native"
LICENSE_UPSTREAM_REVIEW_REQUIRED = "requires_upstream_review"
LICENSE_UPSTREAM_REVIEWED = "upstream_reviewed"

LICENSE_STATUSES = (
    LICENSE_UNREVIEWED,
    LICENSE_PROJECT_NATIVE,
    LICENSE_UPSTREAM_REVIEW_REQUIRED,
    LICENSE_UPSTREAM_REVIEWED,
)

PROVENANCE_PROJECT_NATIVE_CLEANROOM = "project_native_cleanroom"
PROVENANCE_RECOVERED_INVENTORY = "recovered_inventory_only"

PROVENANCE_ORIGINS = (PROVENANCE_PROJECT_NATIVE_CLEANROOM, PROVENANCE_RECOVERED_INVENTORY)

# --- Parameter shapes --------------------------------------------------------
# The registry admits only these scalar/one-level-list shapes.  A nested,
# free-form, path-like or callable parameter shape is rejected: an action
# descriptor must never be able to describe smuggling arbitrary structure.
PARAM_STRING = "string"
PARAM_INTEGER = "integer"
PARAM_NUMBER = "number"
PARAM_BOOLEAN = "boolean"
PARAM_STRING_LIST = "string_list"

PARAMETER_KINDS = (PARAM_STRING, PARAM_INTEGER, PARAM_NUMBER, PARAM_BOOLEAN, PARAM_STRING_LIST)

# --- Output record kinds -----------------------------------------------------
# The *domain record* an action targets.  NOTE: for an ``offline_query_plan``
# action this is the kind a future audited executor *would* return; the action
# itself returns only a query plan.  Every such descriptor carries that fact in
# :attr:`ActionDescriptor.limitations`, and ``execution_kind`` keeps it
# unambiguous.  Routing matches on this so an agent can express a modality need
# ("I need literature references") without being told a plan already satisfies it.
OUTPUT_DATASET_REFERENCE = "dataset_reference"
OUTPUT_LITERATURE_REFERENCE = "literature_reference"
OUTPUT_GENE_ANNOTATION_RECORD = "gene_annotation_record"
OUTPUT_PROTEIN_ANNOTATION_RECORD = "protein_annotation_record"
OUTPUT_PATHWAY_RECORD = "pathway_record"
OUTPUT_INTERACTION_RECORD = "interaction_record"
OUTPUT_ENRICHMENT_RECORD = "enrichment_record"
OUTPUT_STRUCTURE_RECORD = "structure_record"

OUTPUT_RECORD_KINDS = (
    OUTPUT_DATASET_REFERENCE,
    OUTPUT_ENRICHMENT_RECORD,
    OUTPUT_GENE_ANNOTATION_RECORD,
    OUTPUT_INTERACTION_RECORD,
    OUTPUT_LITERATURE_REFERENCE,
    OUTPUT_PATHWAY_RECORD,
    OUTPUT_PROTEIN_ANNOTATION_RECORD,
    OUTPUT_STRUCTURE_RECORD,
)

# --- Purposes ----------------------------------------------------------------
# The bounded vocabulary a task may use to say *why* it wants an action.  A
# purpose is a routing key, never an authorization.
PURPOSE_DATASET_DISCOVERY = "dataset_discovery"
PURPOSE_LITERATURE_DISCOVERY = "literature_discovery"
PURPOSE_GENE_ANNOTATION_LOOKUP = "gene_annotation_lookup"
PURPOSE_PROTEIN_ANNOTATION_LOOKUP = "protein_annotation_lookup"
PURPOSE_PATHWAY_LOOKUP = "pathway_lookup"
PURPOSE_INTERACTION_LOOKUP = "interaction_lookup"
PURPOSE_ENRICHMENT_PLANNING = "enrichment_planning"
PURPOSE_STRUCTURE_LOOKUP = "structure_lookup"

PURPOSES = (
    PURPOSE_DATASET_DISCOVERY,
    PURPOSE_ENRICHMENT_PLANNING,
    PURPOSE_GENE_ANNOTATION_LOOKUP,
    PURPOSE_INTERACTION_LOOKUP,
    PURPOSE_LITERATURE_DISCOVERY,
    PURPOSE_PATHWAY_LOOKUP,
    PURPOSE_PROTEIN_ANNOTATION_LOOKUP,
    PURPOSE_STRUCTURE_LOOKUP,
)


# --- Connector inventory -----------------------------------------------------


@dataclass(frozen=True)
class ConnectorDescriptor:
    """One recovered biomedical connector *surface*.  Inert inventory metadata.

    ``recovered_alias`` is the ``mcp_*`` package alias the audit observed.  It is
    carried **only** so a future slice can be matched against the surface that
    actually existed.  It never launches a subprocess, never imports MCP, never
    attaches a connector, and grants nothing.  ``summary`` is project-native
    prose describing the public domain; no upstream description, endpoint, schema
    or license assertion is copied.
    """

    connector_id: str
    display_name: str
    transport_class: str
    category: str
    summary: str
    recovered_alias: str = ""
    implementation_status: str = IMPLEMENTATION_INVENTORY_ONLY
    provenance_origin: str = PROVENANCE_RECOVERED_INVENTORY

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "display_name": self.display_name,
            "transport_class": self.transport_class,
            "category": self.category,
            "summary": self.summary,
            "recovered_alias": self.recovered_alias,
            "implementation_status": self.implementation_status,
            "provenance_origin": self.provenance_origin,
            # Explicit, so no reader can mistake presence for capability.
            "attached": False,
            "endpoint_known": False,
            "license_status": LICENSE_UNREVIEWED,
            "verification_status": VERIFICATION_NEEDS_PUBLIC_DOCS,
        }


# The 24 recovered surfaces, in the order the audit recorded them.  Ids, display
# names, ``mcp_*`` aliases and transport classes are recovered facts; categories
# and summaries are project-native.  ``implementation_status`` is derived at
# registry-build time from the actions that actually exist, not asserted here.
CONNECTOR_INVENTORY: tuple[ConnectorDescriptor, ...] = (
    ConnectorDescriptor(
        "biomart",
        "BioMart",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_GENE_ANNOTATION,
        "Genomic annotation and identifier cross-reference surface.",
        "mcp_biomart",
    ),
    ConnectorDescriptor(
        "pubmed",
        "PubMed",
        TRANSPORT_HOSTED_HTTP,
        CATEGORY_LITERATURE,
        "Biomedical literature search and citation metadata surface.",
    ),
    ConnectorDescriptor(
        "clinical-trials",
        "Clinical Trials",
        TRANSPORT_HOSTED_HTTP,
        CATEGORY_CLINICAL,
        "Registered clinical trial search and trial detail surface.",
    ),
    ConnectorDescriptor(
        "chembl",
        "ChEMBL",
        TRANSPORT_HOSTED_HTTP,
        CATEGORY_CHEMISTRY,
        "Small-molecule bioactivity, target and mechanism surface.",
    ),
    ConnectorDescriptor(
        "biorxiv",
        "bioRxiv",
        TRANSPORT_HOSTED_HTTP,
        CATEGORY_LITERATURE,
        "Preprint search and preprint metadata surface.",
    ),
    ConnectorDescriptor(
        "variants",
        "Variants",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_VARIANT,
        "Human genetic variant frequency, constraint and clinical-record surface.",
        "mcp_variants",
    ),
    ConnectorDescriptor(
        "clinical-genomics",
        "Clinical Genomics",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_CLINICAL,
        "Curated gene-disease validity and clinical evidence surface.",
        "mcp_clinical_genomics",
    ),
    ConnectorDescriptor(
        "expression",
        "Expression",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_EXPRESSION,
        "Tissue-level gene expression and expression-QTL surface.",
        "mcp_expression",
    ),
    ConnectorDescriptor(
        "regulation",
        "Regulation",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_REGULATION,
        "Regulatory element, transcription-factor motif and binding-site surface.",
        "mcp_regulation",
    ),
    ConnectorDescriptor(
        "protein-annotation",
        "Protein Annotation",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_PROTEIN_ANNOTATION,
        "Protein domain, family, tissue-atlas and interaction-network surface.",
        "mcp_protein_annotation",
    ),
    ConnectorDescriptor(
        "rna",
        "RNA",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_RNA,
        "Non-coding RNA family, alignment and model surface.",
        "mcp_rna",
    ),
    ConnectorDescriptor(
        "structures-interactions",
        "Structures & Interactions",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_STRUCTURE,
        "Experimental and predicted structure plus molecular-interaction surface.",
        "mcp_structures_interactions",
    ),
    ConnectorDescriptor(
        "omics-archives",
        "Omics Archives",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_OMICS_ARCHIVE,
        "Public omics dataset and study archive surface.",
        "mcp_omics_archives",
    ),
    ConnectorDescriptor(
        "genes-ontologies",
        "Genes & Ontologies",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_GENE_ANNOTATION,
        "Gene identity, ontology term, functional annotation and pathway surface.",
        "mcp_genes_ontologies",
    ),
    ConnectorDescriptor(
        "drug-regulatory",
        "Drug Regulatory",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_CLINICAL,
        "Regulatory drug application, approval and product-label surface.",
        "mcp_drug_regulatory",
    ),
    ConnectorDescriptor(
        "research-resources",
        "Research Resources",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_RESEARCH_RESOURCES,
        "Funding opportunity and research reagent registry surface.",
        "mcp_research_resources",
    ),
    ConnectorDescriptor(
        "cancer-models",
        "Cancer Models",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_CANCER_MODELS,
        "Cancer cohort mutation, copy-number and clinical-attribute surface.",
        "mcp_cancer_models",
    ),
    ConnectorDescriptor(
        "chemistry",
        "Chemistry",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_CHEMISTRY,
        "Compound property, chemical ontology, reaction and affinity surface.",
        "mcp_chemistry",
    ),
    ConnectorDescriptor(
        "human-genetics",
        "Human Genetics",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_HUMAN_GENETICS,
        "Genome-wide and phenome-wide association study surface.",
        "mcp_human_genetics",
    ),
    ConnectorDescriptor(
        "literature",
        "Literature Graph",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_LITERATURE,
        "Scholarly work, author, venue and citation graph surface.",
        "mcp_literature",
    ),
    ConnectorDescriptor(
        "genomes",
        "Genomes",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_GENE_ANNOTATION,
        "Genome assembly, sequence, homology and browser-track surface.",
        "mcp_genomes",
    ),
    ConnectorDescriptor(
        "cellguide",
        "CellGuide",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_CELL_TYPES,
        "Cell-type description, marker-gene and tissue-distribution surface.",
        "mcp_cellguide",
    ),
    ConnectorDescriptor(
        "zinc",
        "ZINC",
        TRANSPORT_LOCAL_STDIO,
        CATEGORY_CHEMISTRY,
        "Purchasable chemical space lookup and similarity-search surface.",
        "mcp_zinc",
    ),
    ConnectorDescriptor(
        "ketcher-chemistry",
        "Ketcher Chemistry",
        TRANSPORT_INLINE,
        CATEGORY_AUTHORING_TOOL,
        "Interactive molecule-sketching authoring surface.",
    ),
)

CONNECTOR_IDS: tuple[str, ...] = tuple(c.connector_id for c in CONNECTOR_INVENTORY)
_CONNECTOR_BY_ID: dict[str, ConnectorDescriptor] = {c.connector_id: c for c in CONNECTOR_INVENTORY}


# --- Action descriptor -------------------------------------------------------


@dataclass(frozen=True)
class ActionParameter:
    """One bounded, typed public parameter of an action.  Inert data."""

    name: str
    kind: str
    required: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "required": self.required, "description": self.description}


@dataclass(frozen=True)
class ActionDescriptor:
    """Immutable, bounded, JSON-serializable description of one biomedical action.

    A descriptor says what an action *is*, *needs*, and *may not claim*.  It
    holds **no handler**: there is intentionally no callable, endpoint, client,
    or credential field, so possessing a descriptor can never be mistaken for
    possessing the ability to run it.  Execution is the job of the (unbuilt)
    WP-28B2 ToolBroker envelope.
    """

    action_id: str
    version: str
    title: str
    description: str
    category: str
    connector_id: str
    parameters: tuple[ActionParameter, ...]
    output_record_kind: str
    execution_kind: str
    risk_level: str
    requires_approval: bool
    approval_gate: str
    requires_live_executor: bool
    network_egress: bool
    mutates_state: bool
    allowed_agent_ids: tuple[str, ...]
    required_agent_tool: str
    compatible_purposes: tuple[str, ...]
    provenance_origin: str
    provenance_notes: tuple[str, ...]
    license_status: str
    verification_status: str
    limitations: tuple[str, ...]
    scientific_output_eligible: bool
    max_claim_level: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "connector_id": self.connector_id,
            "parameters": [p.to_dict() for p in self.parameters],
            "output_record_kind": self.output_record_kind,
            "execution_kind": self.execution_kind,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
            "approval_gate": self.approval_gate,
            "requires_live_executor": self.requires_live_executor,
            "network_egress": self.network_egress,
            "mutates_state": self.mutates_state,
            "allowed_agent_ids": list(self.allowed_agent_ids),
            "required_agent_tool": self.required_agent_tool,
            "compatible_purposes": list(self.compatible_purposes),
            "provenance_origin": self.provenance_origin,
            "provenance_notes": list(self.provenance_notes),
            "license_status": self.license_status,
            "verification_status": self.verification_status,
            "limitations": list(self.limitations),
            "scientific_output_eligible": self.scientific_output_eligible,
            "max_claim_level": self.max_claim_level,
        }


# --- Validation --------------------------------------------------------------


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionRegistryError(f"{field}: must be a non-empty string")
    if len(value) > MAX_ID_LENGTH:
        raise ActionRegistryError(f"{field}: exceeds {MAX_ID_LENGTH} characters")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionRegistryError(f"{field}: must be non-empty text")
    if len(value) > MAX_TEXT_LENGTH:
        raise ActionRegistryError(f"{field}: exceeds {MAX_TEXT_LENGTH} characters")
    return value


def _require_choice(value: Any, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise ActionRegistryError(f"{field}: must be one of {', '.join(allowed)} (got {value!r})")
    return str(value)


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ActionRegistryError(f"{field}: must be a bool")
    return value


def _require_str_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ActionRegistryError(f"{field}: must be a tuple of strings")
    if len(value) > MAX_LIST_ITEMS:
        raise ActionRegistryError(f"{field}: exceeds {MAX_LIST_ITEMS} items")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ActionRegistryError(f"{field}: every item must be a non-empty string")
    return value


def _validate_parameters(params: Any) -> None:
    if not isinstance(params, tuple):
        raise ActionRegistryError("parameters: must be a tuple of ActionParameter")
    if len(params) > MAX_PARAMETERS:
        raise ActionRegistryError(f"parameters: exceeds {MAX_PARAMETERS} entries")
    seen: set[str] = set()
    for param in params:
        if not isinstance(param, ActionParameter):
            raise ActionRegistryError("parameters: every entry must be an ActionParameter")
        _require_id(param.name, "parameter.name")
        _require_text(param.description, "parameter.description")
        _require_bool(param.required, "parameter.required")
        # Unsupported shapes (nested objects, free-form blobs, paths, callables)
        # are rejected: a descriptor may not describe smuggling structure.
        _require_choice(param.kind, PARAMETER_KINDS, "parameter.kind")
        if param.name in seen:
            raise ActionRegistryError(f"parameters: duplicate parameter name {param.name!r}")
        seen.add(param.name)


def _validate_no_callable(descriptor: ActionDescriptor) -> None:
    """A descriptor must be inert data — no handler may hide on any field."""
    for name, value in vars(descriptor).items():
        candidates: Iterable[Any] = value if isinstance(value, tuple) else (value,)
        for item in candidates:
            if callable(item):
                raise ActionRegistryError(f"{name}: an action descriptor must not carry a callable/handler")


def validate_action_descriptor(descriptor: Any, *, known_agents: Mapping[str, Any] | None = None) -> ActionDescriptor:
    """Validate one descriptor and return it, or raise :class:`ActionRegistryError`.

    Fail-closed: every unknown reference, invalid vocabulary value, unsupported
    parameter shape, contradictory risk/eligibility combination, and every
    executable action asserting eligibility without the required verification /
    license / approval facts is rejected here rather than at use time.
    """
    if not isinstance(descriptor, ActionDescriptor):
        raise ActionRegistryError("descriptor: must be an ActionDescriptor")

    agents = build_agent_specs() if known_agents is None else known_agents

    _require_id(descriptor.action_id, "action_id")
    _require_id(descriptor.version, "version")
    _require_text(descriptor.title, "title")
    _require_text(descriptor.description, "description")
    _require_choice(descriptor.category, CATEGORIES, "category")
    _require_choice(descriptor.output_record_kind, OUTPUT_RECORD_KINDS, "output_record_kind")
    _require_choice(descriptor.execution_kind, EXECUTION_KINDS, "execution_kind")
    _require_choice(descriptor.risk_level, RISK_LEVELS, "risk_level")
    _require_choice(descriptor.provenance_origin, PROVENANCE_ORIGINS, "provenance_origin")
    _require_choice(descriptor.license_status, LICENSE_STATUSES, "license_status")
    _require_choice(descriptor.verification_status, VERIFICATION_STATUSES, "verification_status")
    _require_choice(descriptor.max_claim_level, tuple(CLAIM_LEVELS), "max_claim_level")
    _require_bool(descriptor.requires_approval, "requires_approval")
    _require_bool(descriptor.requires_live_executor, "requires_live_executor")
    _require_bool(descriptor.network_egress, "network_egress")
    _require_bool(descriptor.mutates_state, "mutates_state")
    _require_bool(descriptor.scientific_output_eligible, "scientific_output_eligible")
    _require_str_tuple(descriptor.provenance_notes, "provenance_notes")
    _require_str_tuple(descriptor.limitations, "limitations")
    if not descriptor.provenance_notes:
        raise ActionRegistryError("provenance_notes: an action must record at least one provenance fact")
    if not descriptor.limitations:
        raise ActionRegistryError("limitations: an action must record at least one explicit limitation")

    # Unknown connector fails closed — the registry never invents a surface.
    if descriptor.connector_id not in _CONNECTOR_BY_ID:
        raise ActionRegistryError(f"connector_id: unknown connector {descriptor.connector_id!r}")

    _validate_parameters(descriptor.parameters)

    for purpose in _require_str_tuple(descriptor.compatible_purposes, "compatible_purposes"):
        _require_choice(purpose, PURPOSES, "compatible_purposes")
    if not descriptor.compatible_purposes:
        raise ActionRegistryError("compatible_purposes: must declare at least one purpose")

    # Unknown agent fails closed, and every allow-listed agent must actually hold
    # the tool grant the action requires (cross-checked against AgentSpec, so a
    # descriptor cannot quietly widen an agent's authority).
    _require_id(descriptor.required_agent_tool, "required_agent_tool")
    for agent_id in _require_str_tuple(descriptor.allowed_agent_ids, "allowed_agent_ids"):
        spec = agents.get(agent_id)
        if spec is None:
            raise ActionRegistryError(f"allowed_agent_ids: unknown agent {agent_id!r}")
        if descriptor.required_agent_tool not in spec["allowed_tools"]:
            raise ActionRegistryError(f"allowed_agent_ids: agent {agent_id!r} does not hold required tool grant {descriptor.required_agent_tool!r}")
        # An action may never let an agent exceed its own AgentSpec ceiling.
        if CLAIM_LEVELS.index(descriptor.max_claim_level) > CLAIM_LEVELS.index(spec["max_claim_level"]):
            raise ActionRegistryError(f"max_claim_level: {descriptor.max_claim_level!r} exceeds the ceiling of agent {agent_id!r}")
    if not descriptor.allowed_agent_ids:
        raise ActionRegistryError("allowed_agent_ids: must allow at least one agent")

    _validate_contradictory_flags(descriptor)
    _validate_no_callable(descriptor)
    return descriptor


def _validate_contradictory_flags(d: ActionDescriptor) -> None:
    """Reject risk/eligibility combinations that cannot both be true."""
    if d.requires_approval and not d.approval_gate.strip():
        raise ActionRegistryError("approval_gate: an action requiring approval must name its gate")
    if d.network_egress and not d.requires_live_executor:
        raise ActionRegistryError("network_egress: egress without requires_live_executor is contradictory")
    if d.network_egress and d.risk_level == RISK_NONE:
        raise ActionRegistryError("risk_level: an action with network egress cannot be zero risk")
    if d.risk_level in (RISK_MODERATE, RISK_HIGH) and not d.requires_approval:
        raise ActionRegistryError(f"requires_approval: risk_level {d.risk_level!r} requires approval")

    if d.execution_kind == EXECUTION_KIND_OFFLINE_QUERY_PLAN:
        # An offline planner is a pure function.  It cannot egress, mutate,
        # need a live executor, need approval, or ever be evidence.
        for field_name, flag in (
            ("network_egress", d.network_egress),
            ("mutates_state", d.mutates_state),
            ("requires_live_executor", d.requires_live_executor),
            ("requires_approval", d.requires_approval),
            ("scientific_output_eligible", d.scientific_output_eligible),
        ):
            if flag:
                raise ActionRegistryError(f"{field_name}: an offline query planner must not set this flag")
        if d.risk_level not in (RISK_NONE, RISK_LOW):
            raise ActionRegistryError("risk_level: an offline query planner cannot exceed 'low'")

    if d.execution_kind in EXECUTABLE_KINDS and d.scientific_output_eligible:
        # "Executable + eligible" is the only path to real evidence, so it needs
        # the full fact set.  Missing any one of them fails closed.
        if d.verification_status not in VERIFIED_STATUSES:
            raise ActionRegistryError("scientific_output_eligible: an executable action needs a verified status")
        if d.license_status not in (LICENSE_PROJECT_NATIVE, LICENSE_UPSTREAM_REVIEWED):
            raise ActionRegistryError("scientific_output_eligible: an executable action needs a reviewed license")
        if not d.requires_approval:
            raise ActionRegistryError("scientific_output_eligible: an executable action needs an approval gate")


# --- Registry ----------------------------------------------------------------


class ActionRegistry:
    """Deterministic, fail-closed, handler-free catalogue of actions + connectors.

    Construction validates every descriptor and the connector inventory itself
    (exact ids, uniqueness, and the recorded 19/4/1 transport split).  Lookup
    never falls back: an unknown action or connector raises.
    """

    def __init__(self, descriptors: Iterable[ActionDescriptor]) -> None:
        _validate_connector_inventory()
        agents = build_agent_specs()
        by_id: dict[str, ActionDescriptor] = {}
        for descriptor in descriptors:
            validate_action_descriptor(descriptor, known_agents=agents)
            if descriptor.action_id in by_id:
                raise ActionRegistryError(f"duplicate action_id {descriptor.action_id!r}")
            by_id[descriptor.action_id] = descriptor
        self._by_id: dict[str, ActionDescriptor] = by_id
        self._by_connector: dict[str, tuple[str, ...]] = {
            connector_id: tuple(sorted(a.action_id for a in by_id.values() if a.connector_id == connector_id)) for connector_id in CONNECTOR_IDS
        }

    # --- actions ---
    def list_action_ids(self) -> list[str]:
        """Sorted action ids (stable order)."""
        return sorted(self._by_id)

    def get(self, action_id: str) -> ActionDescriptor:
        """Return one descriptor; raise :class:`UnknownActionError` — never fall back."""
        try:
            return self._by_id[action_id]
        except KeyError as exc:
            raise UnknownActionError(f"unknown action: {action_id!r}") from exc

    def filter(
        self,
        *,
        connector_id: str | None = None,
        category: str | None = None,
        agent_id: str | None = None,
        purpose: str | None = None,
        execution_kind: str | None = None,
        max_risk_level: str | None = None,
    ) -> list[ActionDescriptor]:
        """Deterministically filter actions.  Unknown filter values fail closed."""
        if connector_id is not None and connector_id not in _CONNECTOR_BY_ID:
            raise UnknownConnectorError(f"unknown connector: {connector_id!r}")
        if category is not None:
            _require_choice(category, CATEGORIES, "category")
        if purpose is not None:
            _require_choice(purpose, PURPOSES, "purpose")
        if execution_kind is not None:
            _require_choice(execution_kind, EXECUTION_KINDS, "execution_kind")
        if max_risk_level is not None:
            _require_choice(max_risk_level, RISK_LEVELS, "max_risk_level")
        if agent_id is not None and agent_id not in build_agent_specs():
            raise ActionRegistryError(f"unknown agent: {agent_id!r}")

        matches = [
            action
            for action in self._by_id.values()
            if (connector_id is None or action.connector_id == connector_id)
            and (category is None or action.category == category)
            and (agent_id is None or agent_id in action.allowed_agent_ids)
            and (purpose is None or purpose in action.compatible_purposes)
            and (execution_kind is None or action.execution_kind == execution_kind)
            and (max_risk_level is None or RISK_LEVELS.index(action.risk_level) <= RISK_LEVELS.index(max_risk_level))
        ]
        return sorted(matches, key=lambda a: a.action_id)

    # --- connectors ---
    def list_connector_ids(self) -> list[str]:
        """Connector ids in the recorded inventory order (stable)."""
        return list(CONNECTOR_IDS)

    def describe_connector(self, connector_id: str) -> dict[str, Any]:
        """Return the inert connector record, with derived implementation status."""
        try:
            connector = _CONNECTOR_BY_ID[connector_id]
        except KeyError as exc:
            raise UnknownConnectorError(f"unknown connector: {connector_id!r}") from exc
        action_ids = self._by_connector[connector_id]
        record = connector.to_dict()
        record["implementation_status"] = IMPLEMENTATION_PROJECT_NATIVE if action_ids else IMPLEMENTATION_INVENTORY_ONLY
        record["action_ids"] = list(action_ids)
        return record

    def connector_action_ids(self, connector_id: str) -> list[str]:
        """Sorted action ids implemented for a connector (empty ⇒ inventory-only)."""
        if connector_id not in self._by_connector:
            raise UnknownConnectorError(f"unknown connector: {connector_id!r}")
        return list(self._by_connector[connector_id])

    def transport_counts(self) -> dict[str, int]:
        """The inventory transport split, recomputed from the descriptors."""
        counts = {name: 0 for name in TRANSPORT_CLASSES}
        for connector in CONNECTOR_INVENTORY:
            counts[connector.transport_class] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection of the whole registry (deterministic ordering)."""
        return {
            "connector_count": len(CONNECTOR_IDS),
            "transport_counts": self.transport_counts(),
            "connectors": [self.describe_connector(cid) for cid in self.list_connector_ids()],
            "actions": [self.get(aid).to_dict() for aid in self.list_action_ids()],
        }


def _validate_connector_inventory() -> None:
    """Assert the recovered inventory is exactly what the audit recorded."""
    if len(CONNECTOR_INVENTORY) != EXPECTED_CONNECTOR_COUNT:
        raise ActionRegistryError(f"connector inventory: expected {EXPECTED_CONNECTOR_COUNT} surfaces, found {len(CONNECTOR_INVENTORY)}")
    if len(set(CONNECTOR_IDS)) != len(CONNECTOR_IDS):
        raise ActionRegistryError("connector inventory: connector ids must be unique")
    counts = {name: 0 for name in TRANSPORT_CLASSES}
    aliases: list[str] = []
    for connector in CONNECTOR_INVENTORY:
        _require_id(connector.connector_id, "connector_id")
        _require_text(connector.display_name, "display_name")
        _require_text(connector.summary, "summary")
        _require_choice(connector.transport_class, TRANSPORT_CLASSES, "transport_class")
        _require_choice(connector.category, CATEGORIES, "category")
        _require_choice(connector.implementation_status, IMPLEMENTATION_STATUSES, "implementation_status")
        _require_choice(connector.provenance_origin, PROVENANCE_ORIGINS, "provenance_origin")
        counts[connector.transport_class] += 1
        if connector.recovered_alias:
            if not connector.recovered_alias.startswith("mcp_"):
                raise ActionRegistryError(f"recovered_alias: {connector.recovered_alias!r} is not an mcp_* alias")
            aliases.append(connector.recovered_alias)
    if counts != EXPECTED_TRANSPORT_COUNTS:
        raise ActionRegistryError(f"connector inventory: transport split {counts} != recorded {EXPECTED_TRANSPORT_COUNTS}")
    if len(set(aliases)) != len(aliases):
        raise ActionRegistryError("connector inventory: mcp_* aliases must be unique")


# --- Default registry: the 12 existing offline planners ----------------------

# Project-native typing of the planner catalogue's public query fields.  The
# planner layer allow-lists field *names*; this table adds the shape and the
# human description the registry contract requires.  A field missing here fails
# closed rather than defaulting to "string".
_PARAM_SPECS: dict[str, tuple[str, bool, str]] = {
    "query": (PARAM_STRING, True, "Free-text public search expression."),
    "organism": (PARAM_STRING, False, "Organism/species scope for the request."),
    "species": (PARAM_STRING, False, "Species scope for the request."),
    "target_species": (PARAM_STRING, False, "Second species for a cross-species comparison."),
    "assay": (PARAM_STRING, False, "Assay/technology scope for the request."),
    "condition": (PARAM_STRING, False, "Experimental condition or contrast label."),
    "platform": (PARAM_STRING, False, "Sequencing/array platform scope."),
    "date_range": (PARAM_STRING, False, "Publication date window for the request."),
    "full_text_required": (PARAM_BOOLEAN, False, "Restrict to records with full text available."),
    "mesh_terms": (PARAM_STRING_LIST, False, "Controlled-vocabulary subject terms."),
    "gene": (PARAM_STRING, False, "Single gene symbol or identifier."),
    "genes": (PARAM_STRING_LIST, False, "Gene symbols or identifiers."),
    "protein": (PARAM_STRING, False, "Protein name or accession."),
    "sources": (PARAM_STRING_LIST, False, "Annotation sources to include."),
    "score_threshold": (PARAM_NUMBER, False, "Minimum interaction confidence score."),
    "resolution": (PARAM_NUMBER, False, "Maximum structural resolution in angstroms."),
}

# Mapping of each existing planner to the recovered connector surface whose
# public domain it addresses, plus its project-native routing metadata.
#
# IMPORTANT: this mapping is a *categorization by public domain*, chosen by this
# project.  It is **not** a claim that the recovered connector implements this
# planner, that endpoints match, or that any parity/verification exists.
_PLANNER_BINDINGS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "geo_dataset_search": ("omics-archives", OUTPUT_DATASET_REFERENCE, (PURPOSE_DATASET_DISCOVERY,)),
    "sra_run_search": ("omics-archives", OUTPUT_DATASET_REFERENCE, (PURPOSE_DATASET_DISCOVERY,)),
    "arrayexpress_search": ("omics-archives", OUTPUT_DATASET_REFERENCE, (PURPOSE_DATASET_DISCOVERY,)),
    "europe_pmc_search": ("literature", OUTPUT_LITERATURE_REFERENCE, (PURPOSE_LITERATURE_DISCOVERY,)),
    "pubmed_search": ("pubmed", OUTPUT_LITERATURE_REFERENCE, (PURPOSE_LITERATURE_DISCOVERY,)),
    "ensembl_gene_lookup": ("genomes", OUTPUT_GENE_ANNOTATION_RECORD, (PURPOSE_GENE_ANNOTATION_LOOKUP,)),
    "ncbi_gene_summary": ("genes-ontologies", OUTPUT_GENE_ANNOTATION_RECORD, (PURPOSE_GENE_ANNOTATION_LOOKUP,)),
    "uniprot_lookup": ("protein-annotation", OUTPUT_PROTEIN_ANNOTATION_RECORD, (PURPOSE_PROTEIN_ANNOTATION_LOOKUP,)),
    "reactome_pathways": ("genes-ontologies", OUTPUT_PATHWAY_RECORD, (PURPOSE_PATHWAY_LOOKUP,)),
    "string_interactions": ("protein-annotation", OUTPUT_INTERACTION_RECORD, (PURPOSE_INTERACTION_LOOKUP,)),
    "gprofiler_enrichment": ("genes-ontologies", OUTPUT_ENRICHMENT_RECORD, (PURPOSE_ENRICHMENT_PLANNING,)),
    "pdb_structure": ("structures-interactions", OUTPUT_STRUCTURE_RECORD, (PURPOSE_STRUCTURE_LOOKUP,)),
}

# The planner catalogue's ``resource_kind`` → this registry's category.
_RESOURCE_KIND_TO_CATEGORY: dict[str, str] = {
    "omics_archive": CATEGORY_OMICS_ARCHIVE,
    "literature": CATEGORY_LITERATURE,
    "gene_annotation": CATEGORY_GENE_ANNOTATION,
    "protein_annotation": CATEGORY_PROTEIN_ANNOTATION,
    "pathway": CATEGORY_PATHWAY,
    "network": CATEGORY_INTERACTION_NETWORK,
    "enrichment": CATEGORY_ENRICHMENT,
    "structure": CATEGORY_STRUCTURE,
}

ACTION_ID_PREFIX = "public_bio"
DEFAULT_ACTION_VERSION = "1.0.0"

# Only ``resource_discovery_agent`` holds the ``metadata_search`` grant in
# AgentSpec, so it is the only agent these planners may be routed to.  This is
# re-derived from AgentSpec at build time rather than hard-coded, and validated
# again per descriptor.
PLANNER_REQUIRED_AGENT_TOOL = "metadata_search"

_PLANNER_LIMITATIONS: tuple[str, ...] = (
    "Returns an offline query plan only — never retrieved records of the declared output_record_kind.",
    "Unverified: no public-documentation review, no endpoint check, no contract test exists.",
    "Not evidence: cannot back a claim, lock a dataset, or authorize an export.",
    "Connector mapping is a project-native domain categorization, not an upstream parity claim.",
)

_PLANNER_PROVENANCE: tuple[str, ...] = (
    "project_native clean-room planner catalogue (auto_bioinfo.adapters.public_bio_tools)",
    "connector surface id is recovered inventory provenance only, not official-doc verified",
)


def _action_id_for(tool_id: str) -> str:
    return f"{ACTION_ID_PREFIX}.{tool_id}"


def _parameters_for(spec: PublicBioToolSpec) -> tuple[ActionParameter, ...]:
    params: list[ActionParameter] = []
    for field_name in spec.query_fields:
        shape = _PARAM_SPECS.get(field_name)
        if shape is None:
            # Fail closed: an untyped public field may not be silently admitted.
            raise ActionRegistryError(f"parameter {field_name!r} of tool {spec.tool_id!r} has no declared shape")
        kind, required, description = shape
        params.append(ActionParameter(name=field_name, kind=kind, required=required, description=description))
    return tuple(params)


def _descriptor_for(spec: PublicBioToolSpec) -> ActionDescriptor:
    binding = _PLANNER_BINDINGS.get(spec.tool_id)
    if binding is None:
        raise ActionRegistryError(f"planner {spec.tool_id!r} has no connector binding")
    connector_id, output_kind, purposes = binding
    category = _RESOURCE_KIND_TO_CATEGORY.get(spec.resource_kind)
    if category is None:
        raise ActionRegistryError(f"planner {spec.tool_id!r} has unmapped resource_kind {spec.resource_kind!r}")
    return ActionDescriptor(
        action_id=_action_id_for(spec.tool_id),
        version=DEFAULT_ACTION_VERSION,
        title=spec.title,
        description=(f"Build a deterministic offline query plan against the public {spec.resource} surface. Produces a plan, never retrieved data."),
        category=category,
        connector_id=connector_id,
        parameters=_parameters_for(spec),
        output_record_kind=output_kind,
        execution_kind=EXECUTION_KIND_OFFLINE_QUERY_PLAN,
        risk_level=RISK_LOW,
        requires_approval=False,
        # The gate a *future* audited live executor would have to pass.  Recorded
        # here so the requirement is visible now; it authorizes nothing today.
        approval_gate=spec.approval_gate,
        requires_live_executor=False,
        network_egress=False,
        mutates_state=False,
        allowed_agent_ids=("resource_discovery_agent",),
        required_agent_tool=PLANNER_REQUIRED_AGENT_TOOL,
        compatible_purposes=purposes,
        provenance_origin=PROVENANCE_PROJECT_NATIVE_CLEANROOM,
        provenance_notes=_PLANNER_PROVENANCE,
        license_status=LICENSE_UNREVIEWED,
        verification_status=VERIFICATION_UNVERIFIED,
        limitations=_PLANNER_LIMITATIONS,
        # The two facts that keep a plan from ever being mistaken for evidence.
        scientific_output_eligible=False,
        max_claim_level=CLAIM_LEVELS[0],
    )


def build_default_action_registry() -> ActionRegistry:
    """Return the registry of every action this project actually implements.

    Today: exactly the 12 offline public-bio query planners, mapped onto the
    recovered connector surfaces they address.  The other 17 connectors have no
    action and stay ``inventory_only`` — parity is never fabricated.
    """
    adapter = PublicBioToolAdapter()
    return ActionRegistry(_descriptor_for(adapter.get_tool_spec(tool_id)) for tool_id in adapter.list_tools())


def registry_to_json(registry: ActionRegistry) -> str:
    """Serialize the registry deterministically (sorted keys, stable ordering)."""
    return json.dumps(registry.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
