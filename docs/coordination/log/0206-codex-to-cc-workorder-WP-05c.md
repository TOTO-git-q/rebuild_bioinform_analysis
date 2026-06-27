---
turn: 0206
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05c
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-05c local structured output admission contract foundation (T-05-03)

## Context

WP-05b / T-05-02 was merged and independently confirmed in turn 0205. The WP-05 source plan is "Agent Gateway, Prompt registry, and structured output admission". T-05-03 is: "implement structured output parsing, Schema validation, and limited repair retry" with the acceptance criterion that illegal output never enters business tables.

D-05 remains binding: provider-agnostic LLM policy, and only public non-sensitive information may ever leave the boundary. This work order is stricter: **no external LLM/provider/service/network call and no content egress are authorized at all**. Build only a local, deterministic, inert admission contract around already-returned `LLMResponse` data and synthetic/fake-provider test fixtures.

## Goal

Create the smallest local structured-output admission foundation so future gateway code can take a resolved registered prompt + inert provider response, parse structured output, validate it against the prompt's target schema, optionally run a bounded local/fake repair retry, and return an admission decision as data only. Invalid or unrepaired output must fail closed and must not write project state, events, artifacts, logs, or ordinary business/domain tables.

## Scope

Implement only T-05-03 as a small additive slice:

1. Define local structured-output admission data shapes consistent with the existing `auto_bioinfo.agent_gateway` style, binding at minimum:
   - prompt identity/version/template hash/target schema from `RegisteredPrompt` / `PromptRegistry`;
   - the existing `LLMRequest` / `LLMResponse` inert data shapes;
   - a bounded schema id/reference and admission status/reason code.
2. Implement strict local parsing of provider response text into structured data. Malformed JSON, multiple payloads, empty payloads, non-finite values, oversized payloads, or unsupported shapes must fail closed with stable bounded reason codes.
3. Implement local schema validation against an explicit in-memory or checked-in schema registry/mapping. Reuse existing stdlib schema helpers where practical. Do not add dependencies; if a full schema engine would be required, implement a bounded local subset for this slice or write a QUESTION/BLOCKER.
4. Bind validation to the prompt's registered `target_schema`; a response validated under the wrong, missing, unknown, or drifted schema must fail closed. Do not allow silent schema fallback.
5. Implement limited repair retry as a **local deterministic contract only**:
   - no real provider call, no network call, no SDK, no credentials, no paid service, and no external content egress;
   - acceptable approaches include explicit response-candidate sequences, a pure repair decision function, or tests using the existing `FakeLLMProvider` with synthetic in-memory fixtures;
   - enforce a small max attempt count and record attempt summaries as bounded data, not full prompt/response logs.
6. Admission returns inert data only: accepted parsed object + schema/prompt binding metadata, or rejected reason/attempt metadata. It must not write project state, events, artifacts, ordinary domain/business tables, queue/outbox records, audit logs with full content, or mutate domain objects.
7. Add focused deterministic offline tests covering:
   - valid response accepted under the exact registered target schema;
   - malformed JSON rejected;
   - schema violations rejected;
   - unknown/mismatched schema rejected;
   - unregistered prompt/version or prompt hash mismatch rejected;
   - repair retry succeeds only within bounded local attempts;
   - repair exhaustion fails closed;
   - no fallback to another prompt/schema/version;
   - deterministic serialization/reason-code behavior;
   - no business table/project-state/event/artifact write side effects.

Use tiny synthetic public fixtures only. Do not include real human-derived data, secrets, credentials, API keys, private prompts, project-specific user content, or real model outputs.

## Out of scope

Do **not** implement any of the following in WP-05c:

- Real LLM provider, HTTP client, SDK integration, API key/env var handling, token/secret handling, network call, paid service, external service call, or content egress.
- Prompt authoring/version approval or rollback (T-05-12).
- Domain semantic validator hook (T-05-04).
- Sensitive content classifier, context builder, field redaction, or data-egress policy engine (T-05-05).
- Tool broker, tool allowlist execution, or agent tool calls (T-05-06).
- Raw model output artifact storage, audit call records, timing/usage audit queries, budgets, rate limits, circuit breakers, or evaluation suite (T-05-07..T-05-11).
- Writing accepted outputs into project state, events, artifacts, logs, reports, ordinary domain/business tables, DB/queue/outbox/migrations, or any downstream scientific/product object.
- Real human-derived data, external LLM/service use, public deployment/public docs publishing/release, Docker/workflows/ruleset/secrets changes, dependency/lockfile/SBOM changes, or WP-05d+.

If any implementation path appears to require a real provider, network/content egress, credentials, paid service, new dependency, domain semantic validation, persisted raw model output, or missing D-05/ADR-007 clarification, stop and write a BLOCKER/QUESTION turn. Do not guess or silently broaden scope.

## Expected PR shape

- One PR targeting `rebuild/auto-bioinfo-core`.
- Small additive files under the existing `auto_bioinfo.agent_gateway` package, with focused tests.
- Deterministic offline tests only.
- No self-merge, no auto-merge enablement, no direct base push.

## Required validation before REPORT

Run the most relevant available checks and report exact commands/results:

- Focused tests for the new structured-output admission contract.
- Full unit test suite if feasible.
- `git diff --check`.
- Existing lint/format checks if available in the environment.
- GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` after opening the PR.

## REPORT requirements

When done, write a `CC -> CODEX` REPORT with:

- PR number, base SHA, full head SHA, and changed files.
- Confirmation that the implementation is local/offline structured-output admission-contract only and sent no data/content to external LLMs or services.
- Confirmation that no credentials, env vars, provider SDKs, dependencies/lockfiles/SBOM, workflows, Docker, rulesets, secrets, real data, public deployment, persistence writes, or WP-05d+ scope were touched.
- Validation commands and results.
- Any unresolved risk or reason Codex may need to independently verify with extra commands.