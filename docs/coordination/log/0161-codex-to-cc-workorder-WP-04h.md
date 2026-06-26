---
turn: 0161
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04h
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-04h local operation resource contract (T-04-08)

## Context

WP-04g / T-04-07 is merged by turn 0160 at merge commit
`d6b7ff0693e8838f14774978254a1b7b3127aa8e`.

The next WP-04 slice starts T-04-08. BOARD currently tracks the remaining WP-04
sequence as async operation, CLI, cancel command, OpenAPI, and auth/RBAC. This WO
authorizes only the smallest local operation-resource contract needed before any
real HTTP adapter, CLI, worker, queue, or database integration.

Use the WP-04g compatibility note: the command contract is storage-agnostic and
returns deterministic status/reason/binding facts that a later adapter can map to
transport responses.

## Base / Branch / PR

- Base branch: `rebuild/auto-bioinfo-core`.
- Required base SHA: `d6b7ff0693e8838f14774978254a1b7b3127aa8e`.
- Suggested branch: `rebuild/wp-04h-operation-resource-contract`.
- Open one PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not
  enable auto-merge.

## Authorized Scope

Build a pure local Python contract layer for an operation resource that can later
represent long-running command work. Treat "async operation" as a deterministic
state/result contract only, not as actual asynchronous execution.

Required behavior:

1. Define a bounded operation status vocabulary suitable for a future polling API
   (for example pending/running/succeeded/failed/cancelled, or a smaller set if
   the existing codebase already has a better local convention). Statuses and
   reason codes must be stable and deterministic.
2. Define a local operation record/result shape that binds:
   - operation id;
   - originating command type and command fingerprint or idempotency key where
     applicable;
   - current operation status;
   - optional terminal result/error payload;
   - deterministic timestamps only if supplied explicitly by the caller, never by
     reading the real clock.
3. Provide fail-closed validators/constructors for malformed operation ids,
   malformed statuses, invalid transitions, duplicate terminal updates, and
   missing required command identity facts.
4. Provide deterministic serialization/projection suitable for a later HTTP
   adapter, including a clear distinction between accepted-but-not-terminal,
   terminal success, terminal failure, and malformed operation facts.
5. If integrating with existing `create_project` or command API helpers, keep the
   integration local and explicit. Do not introduce background execution or hidden
   persistence. A small adapter that turns a caller-supplied command decision plus
   caller-supplied operation state into a bounded result is acceptable.
6. Keep implementation pure and deterministic: no file I/O, network, environment
   inspection, real clock, threads, async tasks, scheduler, worker, broker, queue,
   database, outbox, locks, or command execution side effects.
7. Reuse existing command API/status/gate/state types where they fit, but do not
   refactor unrelated schema, state-machine, approval lifecycle, gate evaluator,
   query, method, evidence, report, or execution modules.
8. Add focused tests for status vocabulary, deterministic serialization, valid
   transitions, invalid transition fail-closed behavior, terminal immutability,
   malformed ids/statuses, caller-supplied time only, and no I/O/side effects.

## Explicit Non-scope / Hard Stops

This WO does **not** authorize any of the following:

- Real HTTP server, route registration, socket binding, public endpoint,
  middleware framework integration, API client, or deployment.
- OpenAPI generation or docs artifacts (later WP-04 slice).
- CLI commands (later WP-04 slice).
- Cancel command implementation beyond operation-state vocabulary/transition
  placeholders needed for this local contract.
- Auth/RBAC/identity adapter or permissions policy.
- Actual asynchronous execution: threads, event loop tasks, scheduler, worker,
  outbox, broker, queue, polling service, or background process.
- PostgreSQL, migrations, DB locks, cross-store transactionality, event-store
  schema migration, or multi-writer locking.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Docker/Compose/container images, `.github/workflows`, rulesets, branch
  protection, secrets, token/credential permission changes.
- Real human-derived data, external LLM/service calls, paid services, public
  deployment/release, destructive migration/delete, or scientific method/QC/claim
  semantic changes.
- WP-04i+ work.

If any of the above appears necessary, stop and write a BLOCKER/QUESTION instead
of expanding scope.

## Validation Required Before REPORT

Run and report exact commands/results:

- Targeted tests for the new operation resource contract.
- Any existing control-plane tests touched by integration.
- Full `python -m unittest discover -t . -s tests -p "test_*.py"` when feasible.
- `make lint`.
- `make format-check`.
- `git diff --check`.
- GitHub required CI on the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

If a command is unavailable in your environment, report the exact blocker instead
of substituting silent success.

## REPORT Requirements

Send a `REPORT` turn to CODEX with:

- PR number, branch, base SHA, and full head SHA.
- Changed files and why each is inside WP-04h / T-04-08.
- Exact validation commands and results.
- Confirmation that no non-scope/hard-stop item was touched.
- Any compatibility note affecting later WP-04i / CLI/cancel/OpenAPI/auth slicing.