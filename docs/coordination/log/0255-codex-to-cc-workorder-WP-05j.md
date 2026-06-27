---
turn: 0255
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05j
status: OPEN
date: 2026-06-28
---

# WORK_ORDER - WP-05j / T-05-10 offline fake model and fixed-response fixtures

## Context

WP-05i / T-05-09 was merged and independently confirmed in turn 0254. The source plan `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` defines T-05-10 as: `建立离线 fake model 和固定回复 fixture`; input `test framework`; output `tests/fakes`; validation `CI 不依赖外部模型`.

D-05 and all WP-05 hard boundaries remain binding. This work order is deliberately limited to local/offline deterministic fake model fixtures for tests. No real model, real provider, real network, real prompt/content, real user data, credential, paid service, external tool, or external service is authorized.

## Goal

Create the smallest local deterministic fake-model fixture foundation so tests can exercise model-facing contracts without depending on an external model or network. The fixture surface must be synthetic, bounded, reproducible, and clearly test-only.

## Scope

Implement only T-05-10 as a small additive slice:

1. Add or extend a `tests/fakes` package/module, or the nearest existing test-only fake fixture location, for offline fake model responses.
2. Define fixed synthetic fake model responses with stable ids and bounded public test content only. Use toy ids and short canned strings such as `fake-response-1`; do not include private prompts, real model output, real user/project content, secrets, or human-derived data.
3. Provide a deterministic fake model/provider callable or object compatible with the existing local agent gateway/provider style where practical. It may return bounded fields such as response text/id, finish status, token/usage-like synthetic counters, model name, and optional error cases.
4. Ensure the fake model has no network, SDK, env var, credential, filesystem persistence, subprocess, real clock, sleep, random, retry, background worker, queue, DB, report, or logging side effect.
5. Include deterministic failure fixtures for malformed request, configured fake refusal/error, and unknown fixture id if this fits the existing test style. Failures must be bounded and synthetic.
6. Keep integration additive and test-only unless an existing contract requires a minimal production-side test adapter. If production code is touched, it must only expose local deterministic fake/test hooks without changing public semantics of the real provider/gateway contracts.
7. Add focused offline tests covering:
   - fixed response lookup is deterministic across repeated calls;
   - fake usage/counter metadata is deterministic and synthetic;
   - unknown or malformed fixture requests fail closed with bounded reason codes/messages;
   - no real external model/provider/network/env/credential access is attempted;
   - no prompt content, raw user content, real model output, secrets, or tool arguments are exposed;
   - existing WP-05a/b/c/d/e/f/g/h/i behavior remains green.

Use tiny synthetic fixtures only. Acceptable examples include `fixture_id="fake-summary-ok"`, `model="offline-fake-model"`, `input_ref="prompt-ref:test"`, `response_text="fake fixed response"`, and small integer usage counters. These examples are placeholders; follow local naming and style.

## Out of Scope / Hard Boundaries

Do **not** implement any of the following in WP-05j:

- Real LLM/model/provider calls, provider SDK integration, HTTP clients, API key/env var handling, token/secret handling, network calls, paid services, external services, or content/data egress.
- Real prompts, private prompt bodies, raw input/output capture, real model output, real user/project content, real human-derived data, real external-tool output, real billing/usage telemetry, or real operational logs.
- Prompt approval/rollback (T-05-12), Agent evaluation framework (T-05-11), production prompt/model routing, provider selection, retries/backoff, timeout/rate/budget/circuit policy changes beyond tests for this fake model, or WP-06+.
- Persistent stores, events, audit logs, project state, metrics, ordinary logs, reports, queues/outbox records, databases, caches, artifact files, or indexes.
- Reading real time or sleeping; using randomness without an explicitly fixed deterministic seed local to tests.
- Dependency, lockfile, SBOM, workflow, Docker, ruleset, branch-protection, secret, credential-permission, deployment, public publishing, or destructive migration/delete changes.
- Scientific/data-analysis semantic changes, dataset handling, method/QC thresholds, claim levels, evidence synthesis behavior, or real data acquisition.

If any implementation path appears to require a real provider/model/tool call, real data/content, network/content egress, credentials, paid service, new dependency, persistent storage/logging/reporting, workflow/SBOM/lockfile changes, branch protection/ruleset/secrets changes, or any hard-stop item, stop and write a QUESTION/BLOCKER turn before implementing that part.

## Delivery

Open exactly one PR against `rebuild/auto-bioinfo-core` for WP-05j only. Report PR number, base/head SHAs, exact files changed, local validation commands, required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` status, and hard-stop check. No self-merge, no auto-merge enablement, no direct base push.