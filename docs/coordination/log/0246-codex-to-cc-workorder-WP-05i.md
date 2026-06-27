---
turn: 0246
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05i
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-05i / T-05-09 local gateway reliability policy contract

## Context

WP-05h / T-05-08 was merged and independently confirmed in turn 0245. The source plan `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` defines T-05-09 as: `实现超时、速率限制、成本预算和断路器`; input `Policy`; output `gateway reliability`; validation `超预算转 NEED_HUMAN_REVIEW`.

D-05 and all WP-05 hard boundaries remain binding. This work order is deliberately narrower than the future production goal: build only a local/offline, deterministic contract for evaluating explicitly supplied synthetic reliability facts against policy-shaped limits. No real provider call, real tool call, clock read, sleep, retry execution, network call, external service, real cost/billing query, real data/content, or durable rate/budget/audit persistence is authorized.

## Goal

Create the smallest local contract foundation so future Agent Gateway code can decide whether a synthetic provider/tool request is allowed, denied, or requires human review because of timeout, rate-limit, budget, or circuit-breaker policy facts. The decision must be deterministic, fail closed on malformed inputs, and expose only bounded policy/audit references, not prompt content, raw input, raw output, tool arguments, credentials, or private operational telemetry.

## Scope

Implement only T-05-09 as a small additive slice:

1. Define local reliability-policy and decision data shapes following existing `auto_bioinfo.agent_gateway` style where practical. Equivalent names are acceptable, but the contract should cover bounded concepts such as:
   - `project_id`, `correlation_id`, request/call identity, and optional provider/tool/prompt references;
   - timeout limit facts such as allowed duration milliseconds and explicitly supplied observed/estimated duration;
   - rate-limit facts such as request count, bounded window identifier, and maximum allowed count;
   - budget facts such as estimated cost units, already-consumed cost units, and maximum allowed cost units;
   - circuit-breaker facts such as closed/open/half-open state, recent failure count, threshold, and optional recovery probe allowance;
   - bounded decision status / reason code vocabulary, including a conservative `NEED_HUMAN_REVIEW` path for budget exhaustion or unsafe ambiguity.
2. Provide a pure local evaluator that accepts only explicit in-memory synthetic policy/fact objects and returns a deterministic reliability decision. It must not read wall-clock time, sleep, schedule retries, mutate global counters, call providers/tools, access network, read env vars, persist state, or inspect real logs.
3. Enforce fail-closed validation for malformed or missing bindings, unknown status/reason vocabulary, negative/non-finite numeric values, ambiguous units, missing limits needed for a decision, elapsed/estimated duration over timeout, count over rate limit, cost over budget, open circuit, inconsistent circuit facts, and any authority flag that claims to authorize real execution or bypass gates.
4. Ensure over-budget conditions produce a bounded `NEED_HUMAN_REVIEW` decision rather than an automatic execution decision. Timeout/rate-limit/open-circuit conditions may be denied or human-review depending on the local vocabulary, but must never be silently allowed.
5. Provide deterministic projections suitable for future audit linkage, but do not create a repository, event, DB row, metric, ordinary log, report, queue/outbox entry, rate-limit store, budget ledger, or global registry.
6. Reuse existing local contracts where appropriate (`ProjectPolicy` or policy-shaped dictionaries, `LLMRequest`/`LLMUsage`, prompt registry bindings, Tool Broker request/decision metadata, audit record references), but do not change their public semantics or existing behavior.
7. Add focused deterministic offline tests covering:
   - under-limit synthetic provider/tool request is allowed with a bounded decision projection;
   - timeout exceeded is not allowed;
   - rate limit exceeded is not allowed;
   - cost budget exceeded returns `NEED_HUMAN_REVIEW`;
   - open circuit / failure threshold blocks or human-reviews the request;
   - malformed limits/facts, negative/non-finite numbers, missing bindings, unknown units, and bypass flags fail closed with deterministic reason codes;
   - decisions and projections are deterministic and do not expose prompt content, raw input, raw output, tool arguments, credentials, or secrets;
   - no filesystem, project-state, event, queue/outbox, DB, ordinary log, report, subprocess, network, provider/tool execution, credential/env var, real clock, sleep, or global mutable registry side effect is introduced;
   - existing WP-05a/b/c/d/e/f/g/h behavior remains green.

Use tiny synthetic public fixtures only, such as fake ids, `estimated_cost_units=3`, `max_cost_units=10`, `request_count=2`, `max_requests=5`, and explicit `elapsed_ms=12`. Do not include real human-derived data, private prompts, project-specific user content, real model output, secrets, credentials, API keys, real billing data, real timing telemetry, or external-tool output.

## Out of Scope / Hard Boundaries

Do **not** implement any of the following in WP-05i:

- Real LLM/provider calls, real Tool Broker handler execution, HTTP clients, SDK integration, API key/env var handling, token/secret handling, network calls, paid services, external service calls, cost/billing API calls, or content/data egress.
- Reading real time or sleeping; using `time`, `datetime.now`, scheduler loops, timers, background workers, retries, backoff, jitter, queues, leases, or process/thread execution.
- Persisting real rate-limit counters, budget ledgers, circuit state, audit logs, events, artifact files, project state, business/domain objects, metrics, ordinary logs, reports, queues/outbox records, databases, or query indexes.
- Reading or processing real human-derived data, real project/user content, private prompts, real model outputs, real external-tool outputs, real cost records, or real operational telemetry.
- Fake model fixture expansion (T-05-10), Agent evaluation framework (T-05-11), prompt approval/rollback (T-05-12), WP-06+, or integration that actually gates production execution.
- Resource discovery, literature/data search, annotation/method/execution tools, worker integration, OS command execution, MCP/HTTP/OpenAPI integration, DB/migration work, observability dashboards, or external adapter implementation.
- Dependency, lockfile, SBOM, workflow, Docker, ruleset, branch-protection, secret, credential-permission, deployment, public publishing, or destructive migration/delete changes.
- Scientific/data-analysis semantic changes, dataset handling, method/QC thresholds, claim levels, or evidence synthesis behavior.

If any implementation path appears to require real provider/tool calls, real data/content, persistent rate/budget/circuit/audit/event/log storage, reading a real clock, network/content egress, credentials, paid service, new dependency, filesystem/process side effects, policy changes outside this local contract, or any hard-stop item, stop and write a QUESTION/BLOCKER turn before implementing that part.

## Delivery

Open exactly one PR against `rebuild/auto-bioinfo-core` for WP-05i only. Report PR number, base/head SHAs, exact files changed, local validation commands, required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` status, and hard-stop check. No self-merge, no auto-merge enablement, no direct base push.