---
turn: 0262
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-06a
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-06a / T-06-01 local intake support-scope classifier

## Context

WP-05j / PR #40 was independently confirmed merged in turn 0261 at merge commit `cbfea829be5bdd6f2468aceb01907c5c9b3d7e9f`.

The next architecture-plan section is WP-06: phases 0-2 intake, question normalization, and ontology scope. This work order intentionally starts with only T-06-01:

- request support-scope classifier;
- deterministic rules first;
- LLM, if ever used later, is only suggestion-level and is not authorized in this work order;
- validation must prove out-of-scope requests can enter a bounded legal stop state.

The generic PromptRegistry foundation exists from WP-05b, but this turn does not authorize Question Normalizer / Scope Resolver agent calls or prompt execution. If you find T-06-01 cannot be implemented without real prompt registration, real project text, external calls, or broader WP-06 tasks, stop and write a QUESTION/BLOCKER turn.

## Goal

Add the smallest local deterministic intake classifier for an `OriginalRequest`-style request so unsupported or hard-stop-shaped requests fail closed before any planning, normalization, ontology, search, or execution path can start.

## Scope

Implement **T-06-01 only**.

Expected behavior:

1. Provide a local pure function/service, following existing package style, that classifies request support scope from explicit request text and explicit caller facts only.
2. Reuse existing `OriginalRequest` / request schema types if present. Keep schema changes additive and minimal if a helper object is needed.
3. Use bounded stable classification/reason codes. CC may choose local names, but they must be deterministic and testable, for example supported, needs clarification, out of scope, unsupported non-bioinformatics, unsupported external action, malformed request.
4. Deterministic checks must include at least:
   - blank, non-string, oversized, or malformed request input;
   - clearly non-bioinformatics request;
   - request requiring external LLM/provider/service/network call or content egress;
   - request asking for public deployment/publishing, paid service, credential/secrets/ruleset/branch-protection changes, or destructive operations;
   - request requiring real human-derived data before an approved dataset/data-lock workflow exists;
   - ambiguous or multi-topic request may be marked needs-clarification, but must not be split automatically.
5. Out-of-scope/unsupported classifications must map to an existing bounded stop/status object if one already exists, or to a minimal local intake decision object. Do not mutate project state, events, queues, DB, audit logs, or persistent stores.
6. Add focused tests using synthetic toy text only. Required fixture classes:
   - supported toy bioinformatics request using public/synthetic wording;
   - ambiguous request;
   - non-bioinformatics request;
   - external LLM/network/content-egress request;
   - real human-derived data hard-stop-shaped request;
   - destructive or credential/ruleset request;
   - malformed input.

## Out of scope

Do **not** implement or touch:

- T-06-02 through T-06-12.
- Automatic project split.
- ProjectPolicy builder.
- Question Normalizer command, Agent call, PromptRegistry prompt content, Scope Resolver, or any LLM/provider call.
- ResearchSpec creation/semantic validation, AmbiguityReport, OntologyAdapter, ScopeBundle, ApprovalRequest, version persistence, event emission, scheduler/queue/DB/audit/report/index/cache.
- Real user/project/research content, real human-derived data, real dataset/literature/API/ontology search, provider SDK/API key/env/credential handling, content egress, network calls, real model output.
- WP-07+, WP-08+, data acquisition, analysis execution, scientific thresholds, normalization methods, metrics, or model settings.
- Dependencies, lockfiles, SBOM, workflows, Docker, rulesets, branch protection, secrets, public deployment/publishing.

## Validation expected from CC

Before reporting back:

- run focused tests for the new classifier;
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
- confirmation that no real data, real user research content, external LLM/provider/service/network call, content egress, dependency/lockfile/SBOM/workflow/Docker/ruleset/secrets change, destructive operation, or broader WP-06 task was touched.