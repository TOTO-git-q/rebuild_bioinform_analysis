# operon Static-Analysis Summary (clean-room evidence)

Status: **evidence summary**, not runtime. Directional proposal 0292, landed on
an isolated branch under an explicit CEO override. This document records only
*facts and taxonomy* recovered by a static, no-execution analysis of an external
Linux package, so the project can reuse the **design lessons** without copying
any vendor implementation.

## Provenance and clean-room boundary

- **Derived from (read-only, outside the repo tree):**
  `operon_agent_runtime_analysis_20260701.md` and the extraction/inventory
  metadata in `/tmp/fable5_operon_review/` (the reusable evidence superset).
- **Method:** static inspection only. The ELF binary was **not executed**.
- **What is reproduced here:** package identity hashes, section offsets, asset
  *family* counts, prompt-key *taxonomy* (names + approximate sizes), and
  runtime *concept* names.
- **What is NOT reproduced here:** vendor source bodies, private prompt text,
  generated web bundles, connector response schemas, or any binary. None were
  copied into this repository.

## Package identity (recovered facts)

| Field | Value |
|---|---|
| Source file | external Linux package `operon` |
| Type | ELF64 Linux executable |
| Size | 156,399,936 bytes |
| SHA-256 | `d13771ba4e85c827ef484772d2d5045b2dafff94a2d569d65510e9375f8e2b06` |
| Notable section | `.bun` @ offset 101,818,368, size 54,576,437 |
| Nested payload | gzip→tar inside `.bun`, 1,159 entries, incl. 433 `mcp-servers/bio-tools` entries |

The nested archive **contains vendor bio-tool source** (e.g.
`mcp-servers/bio-tools/run_server.py`). This is treated strictly as *quarantined
static evidence / requirements source* — see
[`operon_quarantine_boundary.md`](operon_quarantine_boundary.md). It is **not**
clean-room code and is **not** copied.

## Recovered agent-runtime taxonomy (design lessons only)

The static analysis identified a modular runtime organised around these concept
groups. Only the *taxonomy* is reused; no prompt text is copied.

- **Modular prompt registry** — separate rule packs (`RULES_CORE`,
  `RULES_SECURITY`, `RULES_SECURITY_SANDBOX`, `RULES_BIOSECURITY`,
  `RULES_NETWORK_SANDBOX`, `RULES_SKILLS`, `RULES_MEMORY`,
  `RULES_ORCHESTRATION`, `RULES_PLAN_MODE`, compaction prompts, ...). Lesson:
  do not keep one giant system prompt.
- **Skill system** — `search_skills` (lexical/BM25) separate from `skill`
  loading; skills labelled by source (bundled / project / connector /
  marketplace / draft); third-party skill text treated as untrusted data.
- **Memory system** — profile vs recalled vs `search_memory` vs `write_memory`,
  with a strong "do not save transient state" policy.
- **Orchestration** — `host.delegate()` with depth caps, parent-visible plan
  tracks, and a rule that parents never fabricate blocked child results.
- **Approval / capability gates** — scoped, deny-over-allow grants
  (`network`, `host`, `host_delete`, `mcp_tool`, `local_exec`, `remote_exec`,
  `remote_read`, ...). Deny-list wins over later allow.
- **MCP connector runtime** — bundled vs local-stdio vs hosted-HTTP transports;
  connector license/terms/contact metadata treated as *provenance*, not docs.
- **Scientific / biosecurity guardrails** — biosecurity screening,
  contact-email disclosure, license acknowledgment, rate-limit pacing, and the
  key boundary this repo already keeps: **offline query plans are not evidence**.
- **Remote compute** — local-vs-remote routing behind explicit approvals.

## How this maps to the current repository

The current repo (`coordination` branch base) already implements a good first
translation of the offline boundary. This branch adds the *project-native*
clean-room pieces:

- `auto_bioinfo/adapters/public_bio_tools.py` — offline query-plan tool layer.
- `docs/rebuild/agent_runtime_capability_classes.md` — capability classes.
- `docs/rebuild/cleanroom_runtime_mapping.md` — concept→seam mapping.

See those documents for the current-state alignment.

## Do-not-overclaim

This repository claims only **project-native clean-room coverage** of the
recovered public-API surface and design taxonomy. It does **not** claim parity
with the Linux `operon` product, nor scientific validity from any recovered
material.
