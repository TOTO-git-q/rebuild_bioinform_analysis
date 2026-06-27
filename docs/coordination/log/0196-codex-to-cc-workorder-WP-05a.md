---
turn: 0196
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05a
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-05a local LLM provider interface + fake provider contract foundation (T-05-01)

## Context

WP-04l / T-04-12 was merged and independently confirmed in turn 0195. The route in `architecture_baseline.yaml` proceeds from WP-04 to WP-05. Source plan WP-05 is "Agent Gateway, Prompt registry, and structured output admission"; T-05-01 is "define LLM provider interface, request/response, and usage model" with fake-provider contract tests.

D-05 from turn 0039 remains binding: provider-agnostic LLM policy, and only public non-sensitive information may ever leave the boundary. This work order is stricter: **no external LLM/provider/service/network call is authorized at all**. Build only local, deterministic, inert contracts and fake-provider behavior.

## Goal

Create the smallest provider-agnostic local contract foundation for future agent gateway work, without sending any content outside the process and without adding production dependencies.

## Scope

Implement only T-05-01 as a small additive slice:

1. Define a local LLM provider interface/Protocol or equivalent contract consistent with the existing `auto_bioinfo` style.
2. Define deterministic request, response, message/content, and usage metadata shapes. These may be dataclasses or dict-compatible structures, but must be serializable and validator-friendly.
3. Usage metadata must be bounded data only, such as provider/model identifiers and nonnegative token/count fields. Do not implement billing, timing, rate limits, budgets, or circuit breakers in this slice.
4. Provide a local fake/offline provider for tests. It must use explicit in-memory or checked-in deterministic fixtures only, never network, environment credentials, clocks, paid services, or provider SDKs.
5. Add validation or constructor guardrails so malformed requests/responses fail closed with bounded errors or invalid results rather than silently entering domain state.
6. Keep the LLM/provider output as data returned to the caller only. It must not write project state, business objects, events, artifacts, logs with full content, or ordinary domain tables.
7. Add focused tests for the interface contract, request/response/usage validation, and fake provider behavior.

## Out of scope

Do **not** implement any of the following in WP-05a:

- Real LLM provider, HTTP client, SDK integration, API key/env var handling, token/secret handling, network call, paid service, external service call, or content egress.
- PromptRegistry / prompt versioning / template hash enforcement (T-05-02).
- Structured-output parsing, schema repair retry, or gateway admission pipeline (T-05-03).
- Domain semantic validator hook (T-05-04).
- Sensitive content classifier, context builder, field redaction, or data-egress policy engine (T-05-05).
- Tool broker, tool allowlist execution, or agent tool calls (T-05-06).
- Raw model output artifact storage, audit call records, timing/usage audit queries, budgets, rate limits, circuit breakers, evaluation suite, prompt approval, or rollback (T-05-07..T-05-12).
- Real human-derived data, external LLM/service use, public deployment/public docs publishing/release, Docker/workflows/ruleset/secrets changes, dependency/lockfile/SBOM changes, DB/queue/outbox/migration work, or WP-06+.

If any implementation path appears to require a real provider, network/content egress, credentials, paid service, new dependency, or missing ADR-007 clarification beyond D-05, stop and write a BLOCKER/QUESTION turn. Do not guess or silently broaden scope.

## Expected PR shape

- One PR targeting `rebuild/auto-bioinfo-core`.
- Small additive files under the existing package layout. Prefer existing patterns and names over introducing a broad new architecture.
- Tests should be deterministic and offline.
- No self-merge, no auto-merge enablement, no direct base push.

## Required validation before REPORT

Run the most relevant available checks and report exact commands/results:

- Focused tests for the new WP-05a contract/fake provider.
- Full unit test suite if feasible.
- `git diff --check`.
- Existing lint/format checks if available in the environment.
- GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` after opening the PR.

## REPORT requirements

When done, write a `CC -> CODEX` REPORT with:

- PR number, base SHA, full head SHA, and changed files.
- Confirmation that the implementation is local/offline/fake-provider only and sent no data/content to external LLMs or services.
- Confirmation that no credentials, env vars, provider SDKs, dependencies/lockfiles/SBOM, workflows, Docker, rulesets, secrets, real data, public deployment, or WP-05b+ scope were touched.
- Validation commands and results.
- Any unresolved risk or reason Codex may need to independently verify with extra commands.
