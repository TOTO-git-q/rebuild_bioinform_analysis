---
turn: 0406
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-28A-public-bio-resource-registry
status: OPEN
date: 2026-07-13
related:
  - 0405-codex-to-cc-decision-WP-27-merged-route-complete.md
  - CEO-direct-request-2026-07-13-rewrite-reusable-assets
---

# WORK ORDER: WP-28A clean-room public-bio resource registry

CEO requested that reusable resources under
`E:\串流\claude_science_reusable_unpack_assets_20260701` be rewritten and
landed in the project. This turn authorizes only the safe offline slice below.
It does not authorize the later live/network slice.

## Objective

Extend the existing project-native `PublicBioToolAdapter` into a truthful,
deterministic inventory of the 24 biomedical connector surfaces identified by
the source audit while preserving the current offline closed-loop boundary.
This is a registry/query-plan capability only, not scientific execution.

## Clean-room boundary

- Do not copy, import, execute, or adapt implementation bodies from
  `03_reconstructed_mcp_server`, `08_rebuilt_biotool`, any `vendor_extracted`
  tree, `06_raw_payload_for_future_static_search/bun_section.bin`, JS fragments,
  recovered context dumps, or reconstructed manifests.
- The recovered inventory may be used only as compatibility requirements:
  connector ids/names, `mcp_*` aliases, and transport-class counts. Mark these
  facts as recovered/inventory-only, not official-doc verified.
- Do not copy endpoint URLs, request/response schemas, terms assertions, or
  license assertions from the unpack assets. Those require a separate
  public-docs-only review before live use.
- Preserve explicit provenance and limitations; no registry entry or query plan
  may become evidence, authorize export, or claim scientific eligibility.

## Authorized files

- `auto_bioinfo/adapters/public_bio_tools.py`
- `auto_bioinfo/adapters/__init__.py` only if an additive re-export is required
- `tests/test_public_bio_tools.py`
- `docs/audit/public_bio_resource_landing.md`
- `docs/rebuild/WP-28A-REPORT.md`

No other files are authorized without a QUESTION turn.

## Required behavior

1. Add a deterministic connector registry with exactly 24 unique connector ids:
   `biomart`, `pubmed`, `clinical-trials`, `chembl`, `biorxiv`, `variants`,
   `clinical-genomics`, `expression`, `regulation`, `protein-annotation`, `rna`,
   `structures-interactions`, `omics-archives`, `genes-ontologies`,
   `drug-regulatory`, `research-resources`, `cancer-models`, `chemistry`,
   `human-genetics`, `literature`, `genomes`, `cellguide`, `zinc`, and
   `ketcher-chemistry`.
2. Preserve the inventory transport split: 19 `local_stdio_bio_runner`,
   4 `hosted_streamable_http`, and 1 `inline_connector`.
3. Preserve the 19 recovered `mcp_*` compatibility aliases as inert metadata.
   They must not launch a subprocess, import MCP, or grant connector attachment.
4. Map the existing 12 offline query planners to the applicable connectors.
   Connectors without a project-native planner must be explicit
   `inventory_only` entries with an empty tool list; do not fabricate parity.
5. Add read-only APIs sufficient to list connectors, describe one connector,
   and list its project-native tool ids. Output ordering and ids must be stable.
6. Keep every descriptor/query plan conservative:
   `verified=False`, `scientific_output_eligible=False`, no retrieval, no
   materialization, no export authority, and an explicit
   `needs_public_docs_verification` status where appropriate.
7. Replace the current broken documentation reference to the nonexistent
   `docs/audit/operon_static_analysis_summary.md` with the new landing document.
8. Document what was admitted, rewritten, deferred, and rejected, including the
   source-pack provenance warning and the live-layer approval gates.

## Explicit non-goals / hard stops

- No network access, live API calls, downloads, real human-source data, external
  LLM/service calls, contact-email submission, remote MCP attachment, or public
  deployment/publication.
- No new/updated dependency, `pyproject.toml`, lockfile, SBOM, CI workflow,
  Docker/container, ruleset, secret, token, or credential change.
- No `ResourceDiscoveryPort` live implementation, no dataset verification or
  materialization, and no claim/evidence/report scientific semantics change.
- If official-doc lookup, live endpoint verification, dependencies, credentials,
  contact email, or upstream account/license acceptance becomes necessary,
  stop and write a QUESTION/BLOCKER turn. Do not silently broaden WP-28A.

## Acceptance evidence

- Tests prove exact connector ids, uniqueness, 19/4/1 transport counts, inert
  19-alias metadata, deterministic ordering, and valid tool mappings.
- Tests prove inventory-only connectors expose no executable planner and unknown
  connector/tool ids fail closed.
- Existing query-plan tests remain green, including no-network/no-subprocess,
  deterministic plan ids, field allow-listing, materialization rejection, and
  conservative provenance.
- `python -m unittest tests.test_public_bio_tools -v` passes.
- Full `python -m unittest discover -s tests -v`, project lint/format checks, and
  `git diff --check` pass; required CI quality 3.10/3.11/3.12 must be green.
- PR targets `rebuild/auto-bioinfo-core`; CC does not merge it. Report exact
  base/head SHA, changed files, test evidence, and any residual gaps.

## Delivery protocol

Implement on a fresh branch from current protected base
`d428659dc2edbede2b7a5e8acb8ee00d07e02a58`, open a PR, then write a REPORT
turn to CODEX. Codex will independently checkout and verify the exact PR head.
