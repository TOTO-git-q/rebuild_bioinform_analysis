# Public-Bio Tools (offline query-plan layer)

Module: `auto_bioinfo/adapters/public_bio_tools.py`
Status: **offline query planners** — inert, deterministic, no network.

These tools are the project-native, clean-room translation of the recovered
public bioinformatics connector surface (see
[`../audit/operon_static_analysis_summary.md`](../audit/operon_static_analysis_summary.md)).
They turn a query into the *public request that would be made* — a **query
plan** — and never retrieve or materialize anything.

## Guarantees

- **Execution mode:** every output is `execution_mode = "offline_query_plan"`.
- **Plan, not data:** each result has `is_query_plan=True`, `is_retrieved_data=False`.
- **No network / no subprocess:** the module imports no `socket`, `requests`,
  `urllib`, `http`, or `subprocess`; planning works with sockets disabled.
- **Materialization refused:** `materialize()` raises `MaterializationRejected`.
- **Conservative provenance:** `verified=False`,
  `verification_level="unverified"`, `retrieval_mode="offline_no_retrieval"`,
  `source_status="offline_query_plan"`, `scientific_output_eligible=False`.
- **Allow-listed fields only:** a planner echoes only its declared `query_fields`;
  anything else (secrets, local paths, injected instructions) is dropped.
- **Deterministic:** identical query → identical plan (stable `plan_id`).

## Catalogue (12 tools)

| tool_id | resource | resource_kind |
|---|---|---|
| `geo_dataset_search` | NCBI GEO | omics_archive |
| `sra_run_search` | NCBI SRA | omics_archive |
| `arrayexpress_search` | EBI BioStudies | omics_archive |
| `europe_pmc_search` | Europe PMC | literature |
| `pubmed_search` | NCBI PubMed | literature |
| `ensembl_gene_lookup` | Ensembl | gene_annotation |
| `ncbi_gene_summary` | NCBI Gene | gene_annotation |
| `uniprot_lookup` | UniProt | protein_annotation |
| `reactome_pathways` | Reactome | pathway |
| `string_interactions` | STRING-DB | network |
| `gprofiler_enrichment` | g:Profiler | enrichment |
| `pdb_structure` | RCSB PDB | structure |

## Usage

```python
from auto_bioinfo.adapters.public_bio_tools import PublicBioToolAdapter

adapter = PublicBioToolAdapter()
adapter.list_tools()                       # -> sorted tool ids
plan = adapter.plan_query("uniprot_lookup", {"gene": "TP53", "organism": "human"})
plan["execution_mode"]                     # "offline_query_plan"
plan["provenance"]["scientific_output_eligible"]  # False

# Registry form (inert bound planners):
from auto_bioinfo.adapters.public_bio_tools import build_public_bio_tool_registry
registry = build_public_bio_tool_registry()
registry["uniprot_lookup"]({"gene": "TP53"})
```

## What a plan is NOT

A plan is **not evidence**. Before any result could support a scientific claim, a
future *audited executor* (reserved `ToolBroker` seam) must record the request
URL, response hash, upstream terms/license, contact-email status, rate-limit
state, and schema validation. That executor is deliberately not implemented here
because it would require live network access.

## Tests

`tests/test_public_bio_tools.py` — determinism, plan-only output, conservative
provenance, false-scientific-eligibility rejection, field allow-listing,
materialization rejection, network disabled, and import stability.
