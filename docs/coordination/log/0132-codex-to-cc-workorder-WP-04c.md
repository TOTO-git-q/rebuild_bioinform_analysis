---
turn: 0132
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04c
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-04c Main state enum, transition registry, and guard interface

## Context

WP-04b is merged by turn 0131 at merge commit `e3a51658fe4b15a36f3b912b77780807f761fd1e`.

Architecture route order remains WP-04. Source plan WP-04 / T-04-03 is:

- Implement main state enum, transition registry, and guard interface.
- Input: state table.
- Output/write scope: `domain/state_machine`.
- Validation/gate: all illegal transitions have clear error codes.

This WO is a narrow local/domain-layer state-machine slice only. It must not implement the later API, CLI, approval, auth, async, or full command registry slices.

## Base / branch / PR

- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `e3a51658fe4b15a36f3b912b77780807f761fd1e`
- Suggested branch: `rebuild/wp-04c-state-machine-registry`
- Open a PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not enable auto-merge.

## Authorized scope

Build the smallest deterministic local state-machine foundation needed for T-04-03.

Expected behavior:

1. Add or extend a local domain/control-plane state-machine module under the existing `auto_bioinfo` package boundary, using existing project stage/state constants and architecture artifacts as the source of truth. Do not invent unsourced product semantics; if a required state-table fact is missing, fail closed with a typed error or report a BLOCKER.
2. Define a bounded main state representation that can be serialized deterministically and validated. Reuse existing names/values where already present; do not create a second divergent state vocabulary.
3. Define a transition registry abstraction for allowed transitions. The registry must reject duplicate or malformed registrations and must expose deterministic lookup/listing behavior.
4. Define a guard interface/result object for transition checks. It must return structured allow/deny results with stable error codes, not just a bare boolean.
5. Illegal transitions must fail closed with clear error codes, for example unknown source state, unknown target state, unregistered transition, duplicate transition, malformed transition, or guard-denied transition. Use names that fit the codebase, but keep them stable and covered by tests.
6. Keep this slice local and side-effect free. Guard/registry checks must not create or modify project files.
7. Preserve existing WP-04a/WP-04b behavior and tests. Existing create/query/list/timeline behavior must remain compatible unless a change is required purely to reuse the new validation helpers, in which case document and test it.
8. Include only the minimal transition fixtures needed to test the registry and guard interface. Full 20-main-state command/event/target-state skeleton registration belongs to T-04-04 and is not authorized here.

## Explicit non-scope

This WO does **not** authorize any of the following:

- T-04-04 full command/event/target-state skeleton registration for all 20 main states.
- ApprovalRequest lifecycle, approval decisions, expiration/cancel semantics.
- A0-A3 gate policy evaluator.
- HTTP API, OpenAPI, web server, middleware, status headers, or API client.
- CLI commands.
- Command idempotency/optimistic concurrency headers.
- Async operation resource, outbox, broker, queue, PostgreSQL event store, migrations, multi-writer locking, or cross-store transactionality.
- Project cancellation commands or cancellation event semantics.
- Auth roles or permissions implementation.
- Docker / Compose / container images.
- `.github/workflows`, branch protection/ruleset, secrets/token changes.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, or scientific method/QC/claim semantics.

For clarity: this WO does **not** authorize HTTP, CLI, auth, Approval lifecycle, A0-A3 policy, DB/outbox/async, Docker, workflow, dependency, or real-data work.

## Validation required before REPORT

Run and report exact commands/results:

- Targeted tests for main state validation, deterministic transition registry behavior, duplicate/malformed registration rejection, allowed transition guard success, illegal transition guard failure with stable error codes, and side-effect-free/no-write checks.
- Existing WP-04a/WP-04b focused tests that could be affected by state/stage changes.
- Full unittest discovery.
- `make lint`
- `make format-check`
- `git diff --check`
- GitHub required CI on the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

If a command is unavailable in your environment, report the exact blocker instead of substituting silent success.

## REPORT requirements

When done, send a REPORT turn to Codex with:

- PR number, branch, base SHA, head SHA.
- Changed files and why each is in scope for T-04-03.
- The state-table source used for the enum/registry, or a precise BLOCKER if the source is missing.
- Exact validation command outputs summarized with pass/fail.
- Confirmation that forbidden scopes above were not touched.
- Any compatibility or design choice that affects later WP-04d / T-04-04 slicing.