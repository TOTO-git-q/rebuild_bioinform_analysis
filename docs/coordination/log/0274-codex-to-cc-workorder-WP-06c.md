---
turn: 0274
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-06c
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-06c / T-06-03 initial ProjectPolicy builder

## Context

WP-06b / T-06-02 is merged at `88add8d5283fbded0612bc16ea1fdb33c56471d7` and provides local deterministic intake assessment for multi-question detection and inert split suggestions.

The next architecture-plan task is T-06-03: implement initial `ProjectPolicy` construction for network, sensitivity, resource, and automation level from user constraints; output a policy version; missing key sensitivity policy must request approval.

This work order authorizes only this local deterministic policy-construction slice. It does not authorize Question Normalizer, Scope Resolver, Agent/PromptRegistry prompt execution, ResearchSpec creation, ontology work, search, data acquisition, real data, or external calls.

## Goal

Add a bounded local builder/validator path that turns explicit, synthetic user-constraint facts into an initial `ProjectPolicy` version or a fail-closed approval-needed result when key sensitivity policy is missing. The result is reviewable data only; it must not execute, persist, notify, approve, call out, or unblock downstream research workflow.

## Scope

Implement **T-06-03 only**.

Expected behavior:

1. Provide a pure local function/service, following the existing project style, that accepts user-constraint-shaped input plus the minimum project/request identifiers needed to build an initial policy decision.
2. Reuse existing local contracts where practical, especially `auto_bioinfo.core.schemas.ProjectPolicy`, `validate_project_policy`, and the existing `CreateProjectCommand` policy fields. Do not replace their public semantics. If sharing a helper touches `create_project`, keep behavior backward-compatible and add regression tests.
3. Define bounded deterministic handling for network policy facts, data sensitivity, inert resource-policy facts, and automation level A0 through A3.
4. Missing or malformed key sensitivity policy must fail closed into an approval-needed result with stable reason codes. It must not silently default to a permissive policy, and it must not create a granted approval.
5. If approval-needed data is returned, it may use an existing `ApprovalRequest`-shaped local object or a narrow new inert result object, but it must not be persisted, emitted as an event, sent to a human, sent to an external service, or treated as authorization.
6. Preserve original user constraints and request text/facts. Do not rewrite, normalize, redact, or drop them in the builder path.
7. Keep the builder deterministic and side-effect free: no filesystem writes, DB writes, scheduler/queue messages, event emission, network calls, external LLM/provider/tool calls, or environment/credential reads.
8. Add focused synthetic tests covering explicit toy constraints, missing sensitivity approval-needed output, malformed truthy values such as string true / int 1, malformed network/resource values, stable policy identity, input immutability, no side effects, and `create_project` regression if touched.

## Out of scope

Do **not** implement or touch:

- T-06-04 through T-06-12.
- Question Normalizer command, Scope Resolver, Agent call, PromptRegistry prompt content/execution, or any LLM/provider call.
- ResearchSpec creation/semantic validation, AmbiguityReport, OntologyAdapter, ScopeBundle, Approval lifecycle, version persistence beyond the returned local policy object, event emission, scheduler/queue/DB/audit/report/index/cache.
- Real user/project/research content, real human-derived data, real dataset/literature/API/ontology search, provider SDK/API key/env/credential handling, content egress, network calls, real model output.
- WP-07+, data acquisition, analysis execution, scientific thresholds, normalization methods, metrics, or model settings.
- Dependencies, lockfiles, SBOM, workflows, Docker, rulesets, branch protection, secrets, public deployment/publishing.

## Validation expected from CC

Before reporting back:

- run focused tests for the new policy builder/validator path;
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
- confirmation that no Question Normalizer/Agent/PromptRegistry execution, real data, real user research content, external LLM/provider/service/network call, content egress, approval grant/persistence/event, dependency/lockfile/SBOM/workflow/Docker/ruleset/secrets change, destructive operation, or broader WP-06 task was touched.