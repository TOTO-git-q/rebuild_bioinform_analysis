---
turn: 0234
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05g
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-05g / T-05-07 local restricted raw-output artifact reference contract

## Context

WP-05f / T-05-06 was merged and independently confirmed in turn 0233. The source plan `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` defines T-05-07 as: `保存原始模型输出为受限 Artifact，业务对象只保存解析结果引用`; input `Artifact 接口占位`; output `audit record`; validation `能追溯但不在普通日志泄露全文`.

D-05 and all WP-05 hard boundaries remain binding. This work order is deliberately narrower than the future production goal: build only a local/offline, deterministic contract for representing a restricted raw model output artifact reference and for proving ordinary business objects/audit projections do not expose full raw output. No real model output, real user data, external service, network call, or durable artifact storage is authorized.

## Goal

Create the smallest local contract foundation so future Agent Gateway code can associate an already-returned synthetic `LLMResponse` / structured-output admission result with a restricted raw-output artifact reference, while keeping ordinary business objects, reports, events, and public projections limited to parsed-result references and bounded metadata. Full raw output must never appear in ordinary logs, public decision dictionaries, business/domain tables, or unrestricted audit projections.

## Scope

Implement only T-05-07 as a small additive slice:

1. Define local restricted raw-output artifact contract data shapes, following existing `auto_bioinfo.agent_gateway` style where practical. The shapes may include bounded fields such as:
   - artifact/reference id or content-address-like fingerprint;
   - prompt id/version/template hash or admission binding;
   - model/provider identifiers from existing inert `LLMResponse` metadata;
   - parsed-result/admission reference id;
   - restriction label / access tier / retention hint / redaction status;
   - bounded reason/status codes.
2. Provide a local function/service that accepts only synthetic/in-memory already-returned response data and produces:
   - a restricted raw-output artifact reference suitable for future storage layers;
   - an ordinary business-object-safe reference/projection that contains no full raw output;
   - a bounded audit projection that can trace the relationship without leaking the full content.
3. If a raw content digest/fingerprint is needed, compute it in memory using the standard library only. Do not write files, artifact registries, project state, events, queues/outbox, DB records, reports, or ordinary logs in this slice.
4. Reuse existing local contracts where appropriate (`LLMResponse`, structured-output admission metadata, redaction/context helpers, existing artifact vocabulary), but do not change their public semantics or existing scientific/data behavior.
5. Enforce fail-closed validation for malformed/missing response binding, missing prompt/admission identifiers, malformed restriction labels, oversized raw output, non-serializable values, missing parsed-result reference, or attempts to include full raw output in unrestricted projections.
6. Add focused deterministic offline tests covering:
   - restricted raw-output reference can be built from a tiny synthetic response;
   - ordinary business projection contains only reference/metadata and never full raw output;
   - bounded audit projection is traceable by ids/hashes but does not expose full raw output;
   - malformed/missing bindings fail closed with deterministic reason codes;
   - oversized or non-serializable raw output fails closed;
   - raw output is redacted/withheld from `to_dict()`/public projections/repr-like output;
   - no filesystem, project-state, event, queue/outbox, DB, ordinary log, report, domain-table, subprocess, network, provider, credential, env var, or clock side effect is introduced;
   - existing WP-05a/b/c/d/e/f behavior remains green.

Use tiny synthetic public fixtures only, such as `{"answer":"synthetic"}`. Do not include real human-derived data, private prompts, project-specific user content, real model output, secrets, credentials, API keys, or external-tool output.

## Out of Scope / Hard Boundaries

Do **not** implement any of the following in WP-05g:

- Real LLM/provider calls, HTTP clients, SDK integration, API key/env var handling, token/secret handling, network calls, paid services, external service calls, or content/data egress.
- Persisting real artifact files, writing artifact registries, project state, business/domain objects, events, queues/outbox, databases, reports, or ordinary logs with full content.
- Reading or processing real human-derived data, real project/user content, private prompts, real model outputs, or real external-tool outputs.
- Provider/model/prompt/tool usage/timing audit records beyond the minimal local reference/audit projection needed for T-05-07. T-05-08 is a separate future slice.
- Budgets, rate limits, timeouts, circuit breakers, cost accounting, or NEED_HUMAN_REVIEW transitions (T-05-09).
- Fake model fixture expansion (T-05-10), Agent evaluation framework (T-05-11), or prompt approval/rollback (T-05-12).
- Resource discovery, literature/data search, annotation/method/execution tools, worker integration, OS command execution, MCP/HTTP/OpenAPI integration, DB/migration work, or WP-06+.
- Dependency, lockfile, SBOM, workflow, Docker, ruleset, branch-protection, secret, credential-permission, deployment, public publishing, or destructive migration/delete changes.
- Scientific/data-analysis semantic changes, dataset handling, method/QC thresholds, claim levels, or evidence synthesis behavior.

If any implementation path appears to require real raw model output, real data/content, persistent storage, a real provider/tool call, network/content egress, credentials, paid service, new dependency, filesystem/process side effects, policy changes outside this local contract, or any hard-stop item, stop and write a QUESTION/BLOCKER turn before implementing that part.

## Delivery

Open exactly one PR against `rebuild/auto-bioinfo-core` for WP-05g only. Report PR number, base/head SHAs, exact files changed, local validation commands, required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` status, and hard-stop check. No self-merge, no auto-merge enablement, no direct base push.
