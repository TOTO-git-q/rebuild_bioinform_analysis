---
turn: 0288
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-06e
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-06e / T-06-05 local offline Scope Resolver preflight command contract

## Context

WP-06d / T-06-04 is merged at `97ed912de9f2096a47b3be197bfa4cd4f7d6a2ee` and provides the local offline Question Normalizer command contract that can produce an inert `ResearchSpec` draft while preserving original and normalized text.

The next adjacent WP-06 slice is T-06-05, Scope Resolver. Because real external LLM/provider/service calls, content egress, real ontology/search/API work, and real data/content remain hard-stop territory, this work order authorizes only a local/offline deterministic preflight contract.

If implementing this slice appears to require a real ontology service, real literature/dataset/API search, external provider/model/tool call, real prompt execution against an external system, credential/env access, network/content egress, new dependency, persistence/event integration, real user/project/research content, or broader WP-06 behavior, stop and write a QUESTION/BLOCKER turn.

## Goal

Add the smallest local Scope Resolver preflight command contract that can consume an inert draft-style `ResearchSpec` or Question Normalizer result plus explicit local policy/context data, then return reviewable in-memory scope-resolution data.

The result must remain inert. It may expose a `ScopeBundle` draft/projection and an `AmbiguityReport`-style open-question projection when enough explicit synthetic facts exist, but it must not claim real ontology authority, persist/version objects, execute analysis, call providers/tools, search resources, enqueue jobs, or advance project state.

## Scope

Implement **T-06-05 local/offline Scope Resolver preflight only**.

Expected behavior:

1. Provide a pure local function/service, following existing `auto_bioinfo.intake` / core style, that accepts only explicit local inputs: a draft-like `ResearchSpec` or normalizer result, original/normalized request context, and local policy or policy-builder output where needed.
2. Reuse existing WP-06 gates where practical:
   - support-scope stops remain stops and must not produce a scope bundle;
   - multi-question / needs-human-review outputs must not auto-create child projects or resolve downstream scope;
   - approval-needed or missing policy remains inert and must not become approval;
   - malformed draft/policy data fails closed.
3. Implement any resolver or adapter path as a deterministic in-process fake/offline component only. It must not import or call any external provider, SDK, HTTP client, socket, environment credential, real ontology database, real search API, real model, or paid service.
4. Return a bounded local result object/data projection with stable statuses/reason codes for at least:
   - scope draft created;
   - needs clarification / ambiguity remains open;
   - blocked by intake support-scope;
   - approval needed / policy missing;
   - unsupported scope;
   - malformed request/spec/policy.
5. When a scope draft is created, populate only facts explicitly present in the synthetic/local input or in a tiny offline synthetic fixture vocabulary. Unknown organism/tissue/condition/comparison facts must remain open questions, empty fields, or ambiguity items. Do not silently infer or guess.
6. If existing `ScopeBundle`, `AmbiguityReport`, or `OntologyMapping` schemas are reused, use them as in-memory contracts only. Do not create persisted/versioned scope or ambiguity records, do not add real ontology IDs, and do not mark synthetic mappings as authoritative.
7. Preserve input immutability. Do not redact, rewrite, drop, or mutate original request, normalized request, policy, or draft spec data in place.
8. Keep the command side-effect free: no filesystem writes, project-store writes, DB writes, events, scheduler/queue/outbox, audit logs, report/index/cache updates, subprocesses, network calls, external LLM/provider/tool calls, environment/credential reads, real clock sleeps, or randomness.
9. Add focused synthetic tests covering:
   - supported toy draft/spec creates an inert scope result and preserves original/normalized context;
   - ambiguous or missing organism/tissue/condition/comparison facts remain open and are not guessed;
   - unsupported/external/hard-stop-shaped requests return a stop/no-scope status;
   - approval-needed or missing policy returns inert approval-needed/no-scope status;
   - malformed truthy values such as string `true` / int `1` fail closed where policy or authority flags are expected;
   - the fake/offline resolver path is deterministic and cannot perform network/env/provider/search access;
   - inputs are not mutated;
   - no project stage transition, persistence, event, queue, or child-project behavior is introduced.

## Out of scope

Do **not** implement or touch:

- T-06-06 through T-06-12.
- Real external LLM/provider/service/network calls, content egress, provider SDK/API key/env/credential handling, real model output, paid services, or real prompt execution against any external system.
- Real user/project/research content, real human-derived data, real dataset/literature/API/ontology search, resource discovery, or real ontology-backed mapping/resolution.
- Production `OntologyAdapter`, provider-backed resolver, real ontology IDs, authoritative biological normalization, or search/resource lookup.
- Persisted/versioned `ScopeBundle` or `AmbiguityReport`, Approval grant/lifecycle, version persistence, event emission, scheduler/queue/DB/audit/report/index/cache.
- Pipeline orchestration or project-state stage transitions. Do not wire this into automatic `Pipeline.run()` execution in this work order.
- Automatic project splitting or child project creation.
- Scientific thresholds, normalization methods, metrics, model settings, data acquisition, analysis execution, WP-07+, WP-08+.
- Dependencies, lockfiles, SBOM, workflows, Docker, rulesets, branch protection, secrets, public deployment/publishing, or destructive operations.

If tiny synthetic fixture vocabulary is required, keep it public, test-only, non-sensitive, offline, and clearly marked as synthetic. Do not add private prompt bodies, real prompts, real user text, secrets, or any content intended for external egress.

## Validation expected from CC

Before reporting back:

- run focused tests for the new Scope Resolver preflight command contract;
- run the full local unittest suite if feasible;
- run lint/format checks if available;
- run `git diff --check`;
- open one PR to `rebuild/auto-bioinfo-core` and wait for required `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` checks.

## REPORT requirements

Your REPORT turn must include:

- PR number;
- base branch and base SHA;
- full 40-character head SHA;
- changed files;
- exact tests/checks run and results;
- confirmation that no external LLM/provider/service/network call, content egress, real prompt execution, provider SDK/API key/env/credential access, real ontology/search/API access, real data, real user/project/research content, approval grant/persistence/event, pipeline stage transition, automatic child project creation, dependency/lockfile/SBOM/workflow/Docker/ruleset/secrets change, destructive operation, or broader WP-06 task was touched.