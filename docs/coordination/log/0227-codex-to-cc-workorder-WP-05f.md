---
turn: 0227
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05f
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-05f / T-05-06 local tool allowlist and Tool Broker interface

## Context

WP-05e / T-05-05 was merged and independently confirmed in turn 0226. The source plan `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` defines T-05-06 as: `实现工具调用 allowlist 和 Tool Broker 接口`; input `tool contracts`, output `tool mediation`, validation `Agent 不能调用未授权工具`.

D-05 and the WP-05 hard boundaries remain binding. This work order is stricter than the future production goal: build only a local/offline, deterministic, inert mediation contract. No real external tool execution is authorized.

## Goal

Create the smallest local Tool Broker contract foundation so future Agent Gateway code can represent requested tool calls, check an explicit allowlist, and return bounded allow/deny decisions. Unauthorized tools must fail closed. Authorized behavior in this slice may use only deterministic in-process fake/local test handlers and must not invoke operating-system commands, network, external services, credentials, paid services, or real data.

## Scope

Implement only T-05-06 as a small additive slice:

1. Define local tool contract data shapes, following existing `auto_bioinfo.agent_gateway` style where practical:
   - tool identity such as `tool_id`, optional version/capability, and bounded argument metadata;
   - a tool call request shape bound to caller/project/policy context as needed;
   - a mediation decision/result shape with stable status and bounded reason codes.
2. Define an explicit allowlist/registry contract for allowed tool identities and versions. Unknown, malformed, disabled, version-mismatched, or policy-disallowed tools must fail closed.
3. Add a local Tool Broker interface/service that evaluates requests against the allowlist and returns inert decisions/results only.
4. If successful-path execution is needed for tests, use only explicit in-memory fake handlers supplied by the test/registry. Fake handlers must be deterministic and must not touch filesystem, subprocess, shell, network, clocks, credentials, env vars, real tools, external services, or project state.
5. Enforce bounded argument/result behavior: reject unsupported shapes, oversized payloads, non-serializable values, raw sensitive fields not admitted by the WP-05e context contract, and handler exceptions/malformed returns with deterministic fail-closed reason codes.
6. Keep broker outputs as data returned to the caller only. Do not write project state, business objects, events, artifacts, logs with full content, queues/outbox, reports, or domain tables.
7. Add focused deterministic offline tests covering:
   - allowed registered fake tool can produce a bounded inert result;
   - unknown/unregistered tool is denied;
   - disabled or version-mismatched tool is denied;
   - malformed request/identity/arguments fail closed;
   - sensitive or non-public argument data is blocked/redacted before any handler sees it;
   - handler exception or malformed handler result fails closed;
   - unauthorized request cannot fall back to a default/no-op allowed path;
   - no filesystem, subprocess, network, provider, credential, env var, project-state, event, artifact, log, or domain-table side effect is introduced;
   - existing WP-05a/b/c/d/e behavior remains green.

Use tiny synthetic public fixtures only. Do not include real human-derived data, secrets, credentials, API keys, private prompts, project-specific user content, or real external-tool output.

## Out of Scope / Hard Boundaries

Do **not** implement any of the following in WP-05f:

- Real tool execution, shell/subprocess calls, HTTP clients, SDK integration, API key/env var handling, token/secret handling, network calls, paid services, external service calls, or content/data egress.
- Real LLM/provider calls or provider SDK behavior.
- Raw model output artifacts (T-05-07), provider/model/prompt/tool usage/timing audit records (T-05-08), budgets/rate limits/circuit breakers (T-05-09), fake model fixture expansion (T-05-10), eval framework (T-05-11), or prompt approval/rollback (T-05-12).
- Resource discovery, literature/data search, annotation/method/execution tools, worker integration, OS command execution, MCP/HTTP/OpenAPI integration, queue/outbox, DB/migration work, or WP-06+.
- Dependency, lockfile, SBOM, workflow, Docker, ruleset, branch-protection, secret, credential-permission, deployment, public publishing, or destructive migration/delete changes.
- Real human-derived data or scientific/data-analysis semantic changes.
- Writing business state, project state, events, artifacts, logs with full content, ordinary reports, or domain tables.

If any implementation path appears to require a real tool call, network/content egress, credentials, paid service, new dependency, filesystem/process side effects, policy changes outside the local contract, or any hard-stop item, stop and write a QUESTION/BLOCKER turn before implementing that part.

## Delivery

Open exactly one PR against `rebuild/auto-bioinfo-core` for WP-05f only. Report PR number, base/head SHAs, exact files changed, local validation commands, required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` status, and hard-stop check. No self-merge, no auto-merge enablement, no direct base push.