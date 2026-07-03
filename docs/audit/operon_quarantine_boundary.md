# operon Quarantine Boundary (excluded material)

Status: **quarantine policy** for the external evidence used to inform this
branch. This document exists so a reviewer can confirm, mechanically, that **no
vendor / quarantined asset was copied** into the repository.

## Evidence tiers (keep these separate)

The landing plan requires distinguishing six categories. This branch treats them
as follows:

| Tier | What it is | Location | Committed here? |
|---|---|---|---|
| **Static evidence** | Recovered facts/taxonomy (hashes, offsets, family counts, concept names) | `/tmp/fable5_operon_review/operon_agent_runtime_analysis_20260701.md`, `*_meta/` | No — summarized only |
| **Clean-room rebuild** | Independently written specs beside the extraction | `/tmp/fable5_operon_review/cleanroom_rebuild/` | No — referenced as design input |
| **GAP150 proposal** | Bridge-unit planning pack | `/tmp/fable5_operon_review/gap150_cleanroom_integration_pack/` | No — re-expressed as project-native proposal docs |
| **Current project code** | The repo on the `coordination` base | this repository | Yes — extended additively |
| **Current uncommitted supplement** | Directional proposal 0292 material | evidence dir | No — informs docs only |
| **Coordination state** | Governance/handshake ledger | `docs/coordination/` | Untouched (off-limits) |

## Allowed clean-room inputs

Per the upstream `README_QUARANTINE.md`, only these may inform clean-room work:

- path **names**, file **sizes**, and high-level **asset families**;
- behavior **inferred from public documentation** and public API facts;
- **independently written** specs and tests.

## Disallowed / excluded material (NOT copied, NOT committed)

The following are explicitly excluded from this repository. None appears in the
diff for this branch:

- `vendor_extracted/` tree and any vendor implementation source
  (e.g. `mcp-servers/bio-tools/run_server.py`, `mcp_*` packages);
- the raw Linux `operon` binary and the `.bun` payload / `bun_section.bin`;
- copied **private prompt text** (only the prompt-key *taxonomy* is summarized);
- generated `web-dist/` bundles, `sharp-runtime/`, `micromamba/`, `seccomp`
  binaries, fonts;
- `seed/` datasets or any raw biomedical data;
- extraction TSV/JSON manifests, caches, git internals;
- API keys, `.env`, or any secret.

## Verification hooks

- `tests/test_adversarial_boundaries.py` scans the tracked tree and fails if any
  quarantined path token (`vendor_extracted`, `bun_section`, `.bun`, `web-dist`,
  `sharp-runtime`, `micromamba`, `seccomp`, ...) is committed.
- The public-bio tool layer is proven offline-only in
  `tests/test_public_bio_tools.py` (no network, materialization rejected).

## Boundary statement

Recovered connector names and public endpoint shapes are used **as
requirements**, never as recovered source. Query plans built from them are
planning data only and can **never** support a scientific claim until a future
audited executor records request/response provenance, response hashes,
terms/license state, contact-email status, and rate-limit handling.
