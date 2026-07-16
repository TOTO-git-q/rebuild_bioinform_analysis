"""Offline public-bio *query-plan* tool layer (project-native, clean-room).

This adapter exposes a catalogue of public bioinformatics resources (GEO, SRA,
Europe PMC, Ensembl, UniProt, Reactome, STRING, ...) as **deterministic offline
query planners**.  It is the clean-room, project-native translation of the
recovered biomedical connector taxonomy documented in
``docs/architecture/biomni_cleanroom_integration.md``.

Each planner here is registered as an inert ``ActionDescriptor`` by
:mod:`auto_bioinfo.agent_gateway.action_registry` (WP-28B1), which maps it onto
the recovered connector surface whose public domain it addresses.  That registry
is metadata only: it grants no execution capability beyond this module's own
offline planning.

What this module *is*:

* A pure, in-process function of its inputs.  The same query always yields the
  same plan (stable ``plan_id``).
* A *planner*: every tool returns a **query plan**, i.e. the public request it
  *would* make, never retrieved data.

What this module deliberately is **not**:

* It performs **no** network access, **no** subprocess, **no** dataset download,
  **no** materialization, and generates **no** scientific conclusion.
* A query plan is **not evidence**.  Plans are stamped with conservative,
  unverified provenance and ``scientific_output_eligible=False`` so a downstream
  auditor can never mistake a plan for a validated dataset or claim.

Provenance vocabulary
---------------------

The repository does not (yet) define ``source_class`` / ``retrieval_mode`` /
``verification_level`` enums.  Rather than introduce a large new enum framework,
this module records the required *semantics* from the landing plan using the
project's existing conservative provenance shape (a list of
``{source_type, source_id, note}`` records, see ``core.schemas``) plus a small
set of explicit boolean/string flags.  The semantics preserved are:

* ``verified = False``
* ``verification_level = "unverified"``
* ``retrieval_mode = "offline_no_retrieval"`` (a non-live mode)
* ``source_status = "offline_query_plan"`` (closest conservative status; note the
  existing ``core.validation.validate_no_unknown_verified_dataset`` guard treats
  non-real source statuses as unverifiable)
* ``scientific_output_eligible = False``

Reserved integration seam
-------------------------

A production system would route these plans through an audited ``ToolBroker`` /
``ResourceDiscoveryPort`` executor that records the request URL, response hash,
upstream terms/license, contact-email status, and rate-limit state *before* any
plan output could become evidence.  That executor is intentionally **not**
implemented here (it would require live network access, which is out of scope).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.ids import make_stable_id

# --- Conservative provenance constants (semantics from landing plan §B) ----------

EXECUTION_MODE_OFFLINE_QUERY_PLAN = "offline_query_plan"
RETRIEVAL_MODE_OFFLINE = "offline_no_retrieval"
VERIFICATION_LEVEL_UNVERIFIED = "unverified"
SOURCE_STATUS_QUERY_PLAN = "offline_query_plan"

_CLEANROOM_SOURCE_ID = "public_bio_tools_cleanroom"
_NEXT_STEP = (
    "Attach an audited live executor that records request URL, response hash, "
    "upstream terms/license, contact-email status, rate-limit state, and schema "
    "validation before any result may be treated as evidence."
)


class MaterializationRejected(RuntimeError):
    """Raised when a caller asks an offline query-plan tool to fetch/materialize.

    Offline query planners never retrieve, download, or write dataset bytes; the
    only safe answer is to refuse and point at the reserved audited executor.
    """


@dataclass(frozen=True)
class PublicBioToolSpec:
    """Static, inert descriptor for a single public-bio query planner.

    ``query_fields`` is the *allow-list* of public arguments the planner will
    echo into a plan.  Anything else in a caller's query (secrets, local paths,
    free-form instructions) is dropped, so a plan can never smuggle private
    content into a would-be request.
    """

    tool_id: str
    title: str
    resource: str
    resource_kind: str
    query_fields: tuple[str, ...]
    approval_gate: str
    terms_required: bool = True
    contact_email_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "title": self.title,
            "resource": self.resource,
            "resource_kind": self.resource_kind,
            "query_fields": list(self.query_fields),
            "approval_gate": self.approval_gate,
            "execution_mode": EXECUTION_MODE_OFFLINE_QUERY_PLAN,
            "terms_required": self.terms_required,
            "contact_email_required": self.contact_email_required,
        }


# Project-native catalogue.  Resource *names* and public argument shapes are
# public API facts used here as requirements; no vendor implementation, prompt
# text, or private schema is copied.  Every entry is a network-*reserved* gate.
_CATALOG: tuple[PublicBioToolSpec, ...] = (
    PublicBioToolSpec(
        "geo_dataset_search", "GEO dataset search planner", "NCBI GEO", "omics_archive", ("query", "organism", "assay", "condition"), "network.query_plan"
    ),
    PublicBioToolSpec("sra_run_search", "SRA run metadata planner", "NCBI SRA", "omics_archive", ("query", "organism", "platform"), "network.query_plan"),
    PublicBioToolSpec(
        "arrayexpress_search", "ArrayExpress/BioStudies planner", "EBI BioStudies", "omics_archive", ("query", "organism", "assay"), "network.query_plan"
    ),
    PublicBioToolSpec(
        "europe_pmc_search", "Europe PMC literature planner", "Europe PMC", "literature", ("query", "date_range", "full_text_required"), "network.query_plan"
    ),
    PublicBioToolSpec("pubmed_search", "PubMed literature planner", "NCBI PubMed", "literature", ("query", "mesh_terms", "date_range"), "network.query_plan"),
    PublicBioToolSpec(
        "ensembl_gene_lookup", "Ensembl gene/ortholog planner", "Ensembl", "gene_annotation", ("gene", "species", "target_species"), "network.query_plan"
    ),
    PublicBioToolSpec("ncbi_gene_summary", "NCBI Gene summary planner", "NCBI Gene", "gene_annotation", ("gene", "organism"), "network.query_plan"),
    PublicBioToolSpec(
        "uniprot_lookup", "UniProt protein annotation planner", "UniProt", "protein_annotation", ("gene", "protein", "organism"), "network.query_plan"
    ),
    PublicBioToolSpec("reactome_pathways", "Reactome pathway planner", "Reactome", "pathway", ("genes", "species"), "network.query_plan"),
    PublicBioToolSpec(
        "string_interactions", "STRING interaction planner", "STRING-DB", "network", ("genes", "species", "score_threshold"), "network.query_plan"
    ),
    PublicBioToolSpec(
        "gprofiler_enrichment", "g:Profiler enrichment planner", "g:Profiler", "enrichment", ("genes", "organism", "sources"), "network.query_plan"
    ),
    PublicBioToolSpec("pdb_structure", "PDB structure planner", "RCSB PDB", "structure", ("protein", "organism", "resolution"), "network.query_plan"),
)

_CATALOG_BY_ID: dict[str, PublicBioToolSpec] = {spec.tool_id: spec for spec in _CATALOG}


def _conservative_provenance(tool_id: str) -> dict[str, Any]:
    """Return the conservative, unverified provenance block for a plan."""
    return {
        "verified": False,
        "verification_level": VERIFICATION_LEVEL_UNVERIFIED,
        "retrieval_mode": RETRIEVAL_MODE_OFFLINE,
        "source_status": SOURCE_STATUS_QUERY_PLAN,
        "scientific_output_eligible": False,
        "records": [
            {
                "source_type": "clean_room_spec",
                "source_id": _CLEANROOM_SOURCE_ID,
                "note": f"offline query plan for {tool_id}; not retrieved data, not evidence",
            }
        ],
    }


def _filter_public_query(spec: PublicBioToolSpec, query: Mapping[str, Any] | None) -> dict[str, Any]:
    """Echo *only* the tool's allow-listed public fields; drop everything else."""
    if query is None:
        return {}
    if not isinstance(query, Mapping):
        raise TypeError("query must be a mapping of public field -> value")
    return {key: query[key] for key in spec.query_fields if key in query}


class PublicBioToolAdapter:
    """Deterministic, offline catalogue of public-bio query planners.

    Deny-by-default: the adapter refuses to retrieve or materialize; it only
    produces plans.  It imports no network/subprocess libraries.
    """

    execution_mode = EXECUTION_MODE_OFFLINE_QUERY_PLAN

    def list_tools(self) -> list[str]:
        """Return the sorted list of available tool ids (stable order)."""
        return sorted(_CATALOG_BY_ID)

    def describe_tool(self, tool_id: str) -> dict[str, Any]:
        """Return the inert descriptor for a tool (raises ``KeyError`` if unknown)."""
        return self._spec(tool_id).to_dict()

    def get_tool_spec(self, tool_id: str) -> PublicBioToolSpec:
        """Return the frozen :class:`PublicBioToolSpec` (raises ``KeyError`` if unknown).

        Read-only accessor for metadata layers (e.g. the WP-28B1 action registry)
        that need the typed spec rather than its dict projection.  The spec is
        frozen and carries no handler, so exposing it grants no capability.
        """
        return self._spec(tool_id)

    def plan_query(self, tool_id: str, query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Build a deterministic offline query plan for ``tool_id``.

        The returned dict is a *plan* only: it describes the public request that
        an audited executor could later make.  It carries conservative provenance
        and is never eligible to back a scientific claim.
        """
        spec = self._spec(tool_id)
        public_query = _filter_public_query(spec, query)
        plan_id = make_stable_id(
            "public_bio_query_plan",
            {"tool_id": spec.tool_id, "query": public_query},
        )
        return {
            "plan_id": plan_id,
            "tool_id": spec.tool_id,
            "title": spec.title,
            "resource": spec.resource,
            "resource_kind": spec.resource_kind,
            "execution_mode": EXECUTION_MODE_OFFLINE_QUERY_PLAN,
            "query": public_query,
            "approval_gate": spec.approval_gate,
            "terms_required": spec.terms_required,
            "contact_email_required": spec.contact_email_required,
            "provenance": _conservative_provenance(spec.tool_id),
            "is_query_plan": True,
            "is_retrieved_data": False,
            "next_step": _NEXT_STEP,
        }

    def materialize(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        """Always refuse — offline query planners never fetch or write data."""
        raise MaterializationRejected("public-bio tools are offline query planners; materialization/retrieval is not permitted. " + _NEXT_STEP)

    # ``discover``/``profile`` are intentionally absent: this adapter does not
    # implement ``ResourceDiscoveryPort`` (which would imply verified datasets).

    def _spec(self, tool_id: str) -> PublicBioToolSpec:
        try:
            return _CATALOG_BY_ID[tool_id]
        except KeyError as exc:
            raise KeyError(f"unknown public-bio tool: {tool_id!r} (available: {self.list_tools()})") from exc


@dataclass(frozen=True)
class _BoundPlanner:
    """A single tool bound as a callable planner for registry-style use."""

    adapter: PublicBioToolAdapter
    tool_id: str
    execution_mode: str = field(default=EXECUTION_MODE_OFFLINE_QUERY_PLAN)

    def __call__(self, query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.adapter.plan_query(self.tool_id, query)


def build_public_bio_tool_registry(tool_ids: Iterable[str] | None = None) -> dict[str, _BoundPlanner]:
    """Return ``{tool_id: bound offline planner}`` for interface completeness.

    This is the offline, deterministic registry the landing plan permits.  It
    grants **no** execution capability beyond planning; each bound entry is just
    a deterministic function of its query.  A future ``ToolBroker`` can adopt
    these bindings without changing the offline guarantee.
    """
    adapter = PublicBioToolAdapter()
    ids = list(tool_ids) if tool_ids is not None else adapter.list_tools()
    return {tid: _BoundPlanner(adapter, tid) for tid in ids}
