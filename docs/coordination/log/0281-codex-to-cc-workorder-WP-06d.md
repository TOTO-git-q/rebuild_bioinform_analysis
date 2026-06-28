---
turn: 0281
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-06d
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-06d / T-06-04 local offline Question Normalizer command contract

## Context

WP-06c / T-06-03 is merged at `99753c5877f0d62dc080adca0ab49c750aa8bcbb` and provides the local deterministic initial `ProjectPolicy` builder / approval-needed fail-closed path.

The next architecture-plan task is T-06-04:

- implement Question Normalizer command and Agent call;
- input: `OriginalRequest` / `Policy`;
- output: `ResearchSpec DRAFT`;
- validation: original text and normalized text are both preserved.

Because any real external LLM/provider/service call or content egress is a hard stop, this work order authorizes only the local/offline deterministic slice of T-06-04. Treat the "Agent call" here as an in-process fake/offline adapter invocation or existing deterministic planner-style adapter only. No external model, provider, service, SDK, API key, env credential, network, socket, paid service, or content egress is authorized.

If implementing this slice appears to require a real provider/model/tool call, real prompt execution against an external service, real user/project/research content, credential/env access, network/content egress, new dependency, persistence/event integration, or broader WP-06 behavior, stop and write a QUESTION/BLOCKER turn.

## Goal

Add the smallest local Question Normalizer command contract that can turn explicit synthetic `OriginalRequest`-style text plus local policy data into an inert `ResearchSpec` draft result, while preserving the raw original text, a deterministic normalized-text view, open questions/assumptions, and all fail-closed intake/policy stops.

The result is reviewable data only. It must not execute analysis, persist project state, emit events, enqueue jobs, call tools, call providers, search resources, resolve ontology scope, or unblock downstream workflow.

## Scope

Implement **T-06-04 local/offline command contract only**.

Expected behavior:

1. Provide a pure local function/service, following the existing `auto_bioinfo.intake` / core style, that accepts an `OriginalRequest`-style input and explicit local policy input or policy-builder result.
2. Reuse existing WP-06a/WP-06b/WP-06c gates where practical:
   - support-scope stops must remain stops and must not produce a `ResearchSpec` draft;
   - multi-question / split-suggestion outputs must not auto-create child projects;
   - missing or approval-needed policy output must stay inert and must not become approval.
3. Implement the "Agent call" as a deterministic in-process fake/offline adapter invocation only. It may reuse existing `OfflineDeterministicPlanner` / `ResearchSpec` / `SubQuestion` contracts or a narrow local adapter, but it must not import or call any external provider, SDK, HTTP client, socket, env credential, real model, or paid service.
4. Return a bounded local result object/data projection with stable statuses/reason codes for at least:
   - draft created;
   - stopped by intake support-scope;
   - needs clarification / multi-question requires human review;
   - approval needed / policy missing;
   - malformed request or policy.
5. When a draft is created, produce a `ResearchSpec` with `status="draft"` and preserve both:
   - the exact original request text; and
   - a deterministic normalized-text representation.
   Unknown organism/tissue/condition/comparison facts must be represented as open questions or empty fields, not silently guessed.
6. Preserve input immutability. Do not redact, rewrite, drop, or mutate original request/policy data in place.
7. Keep the command side-effect free: no filesystem writes, project-store writes, DB writes, events, scheduler/queue/outbox, audit logs, report/index/cache updates, subprocesses, network calls, external LLM/provider/tool calls, environment/credential reads, real clock sleeps, or randomness.
8. Add focused synthetic tests covering:
   - supported toy bioinformatics request creates an inert draft and preserves original + normalized text;
   - missing key policy / approval-needed input returns inert approval-needed status and no draft;
   - unsupported/external/hard-stop-shaped request returns a stop and no draft;
   - multi-question or ambiguous request remains human-review oriented and does not create child projects;
   - malformed truthy values such as string `true` / int `1` fail closed where policy or flags are expected;
   - the fake/offline adapter path is deterministic and cannot perform network/env/provider access;
   - inputs are not mutated.

## Out of scope

Do **not** implement or touch:

- T-06-05 through T-06-12.
- Real external LLM/provider/service/network calls, content egress, provider SDK/API key/env/credential handling, real model output, paid services, or real prompt execution against any external system.
- Real user/project/research content, real human-derived data, real dataset/literature/API/ontology search, or resource discovery.
- Scope Resolver, OntologyAdapter, ScopeBundle creation/resolution, AmbiguityReport as a persisted/versioned object, ResearchSpec semantic validation beyond the narrow draft/result checks needed for this command, Approval grant/lifecycle, version persistence, event emission, scheduler/queue/DB/audit/report/index/cache.
- Pipeline orchestration or project-state stage transitions. Do not wire this into automatic `Pipeline.run()` execution in this work order.
- Automatic project splitting or child project creation.
- Scientific thresholds, normalization methods, metrics, model settings, data acquisition, analysis execution, WP-07+, WP-08+.
- Dependencies, lockfiles, SBOM, workflows, Docker, rulesets, branch protection, secrets, public deployment/publishing, or destructive operations.

If tiny synthetic prompt metadata or fixtures are required, keep them public, test-only, non-sensitive, and offline. Do not add private prompt bodies, real prompts, real user text, secrets, or any content intended for external egress.

## Validation expected from CC

Before reporting back:

- run focused tests for the new Question Normalizer command contract;
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
- confirmation that no external LLM/provider/service/network call, content egress, real prompt execution, provider SDK/API key/env/credential access, real data, real user/project/research content, approval grant/persistence/event, Scope Resolver/Ontology/ScopeBundle, pipeline stage transition, dependency/lockfile/SBOM/workflow/Docker/ruleset/secrets change, destructive operation, or broader WP-06 task was touched.