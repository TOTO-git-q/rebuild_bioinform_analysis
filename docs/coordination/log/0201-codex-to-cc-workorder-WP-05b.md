---
turn: 0201
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05b
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-05b local PromptRegistry contract foundation (T-05-02)

## Context

WP-05a / T-05-01 was merged and independently confirmed in turn 0200. The WP-05 source plan is "Agent Gateway, Prompt registry, and structured output admission". T-05-02 is: "establish PromptRegistry: ID, version, template hash, target Schema" with the acceptance criterion that runtime can use only registered versions.

D-05 remains binding: provider-agnostic LLM policy, and only public non-sensitive information may ever leave the boundary. This work order is stricter: **no external LLM/provider/service/network call and no content egress are authorized at all**. Build only local, deterministic, inert registry contracts and tests.

## Goal

Create the smallest local PromptRegistry contract foundation so future gateway code can resolve only explicitly registered prompt versions by stable identity and hash, without rendering or sending prompts to any external service.

## Scope

Implement only T-05-02 as a small additive slice:

1. Define local prompt registry data shapes for a prompt identity, version, template hash, and target schema reference/identifier, consistent with the existing `auto_bioinfo` style and WP-05a contracts.
2. Provide deterministic template hashing and serializable/canonical dictionary output suitable for validator-friendly tests.
3. Add fail-closed validation for malformed prompt IDs, versions, empty templates, invalid/missing target schema references, hash mismatches, duplicate registrations, and unknown prompt/version lookup.
4. Provide a local in-memory or checked-in deterministic registry/service that resolves only explicitly registered prompt ID + exact version. Do not silently fall back to unregistered prompt content.
5. Keep registry results as data returned to the caller only. The registry must not call an LLM/provider, render content for egress, write project state, write events/artifacts/logs with full prompt content, or mutate ordinary domain tables.
6. Add focused tests for registration, lookup, duplicate rejection, hash mismatch rejection, target schema binding, unknown/unregistered lookup fail-closed behavior, and deterministic serialization/hash behavior.

If checked-in prompt fixtures are needed, keep them tiny, synthetic, public, and non-sensitive. Do not include real human-derived data, secrets, credentials, API keys, private prompts, or project-specific user content.

## Out of scope

Do **not** implement any of the following in WP-05b:

- Real LLM provider, HTTP client, SDK integration, API key/env var handling, token/secret handling, network call, paid service, external service call, or content egress.
- Structured-output parsing, schema repair retry, or gateway admission pipeline (T-05-03).
- Domain semantic validator hook (T-05-04).
- Sensitive content classifier, context builder, field redaction, or data-egress policy engine (T-05-05).
- Tool broker, tool allowlist execution, or agent tool calls (T-05-06).
- Raw model output artifact storage, audit call records, timing/usage audit queries, budgets, rate limits, circuit breakers, evaluation suite, prompt approval workflow, prompt rollback, or prompt authoring UI (T-05-07..T-05-12 or later).
- Real human-derived data, external LLM/service use, public deployment/public docs publishing/release, Docker/workflows/ruleset/secrets changes, dependency/lockfile/SBOM changes, DB/queue/outbox/migration work, or WP-05c+.

If any implementation path appears to require a real provider, network/content egress, credentials, paid service, new dependency, or missing ADR-007 clarification beyond D-05, stop and write a BLOCKER/QUESTION turn. Do not guess or silently broaden scope.

## Expected PR shape

- One PR targeting `rebuild/auto-bioinfo-core`.
- Small additive files under the existing package layout, likely near the WP-05 agent gateway package introduced by WP-05a.
- Tests should be deterministic and offline.
- No self-merge, no auto-merge enablement, no direct base push.

## Required validation before REPORT

Run the most relevant available checks and report exact commands/results:

- Focused tests for the new PromptRegistry contract.
- Full unit test suite if feasible.
- `git diff --check`.
- Existing lint/format checks if available in the environment.
- GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` after opening the PR.

## REPORT requirements

When done, write a `CC -> CODEX` REPORT with:

- PR number, base SHA, full head SHA, and changed files.
- Confirmation that the implementation is local/offline registry-contract only and sent no data/content to external LLMs or services.
- Confirmation that no credentials, env vars, provider SDKs, dependencies/lockfiles/SBOM, workflows, Docker, rulesets, secrets, real data, public deployment, or WP-05c+ scope were touched.
- Validation commands and results.
- Any unresolved risk or reason Codex may need to independently verify with extra commands.