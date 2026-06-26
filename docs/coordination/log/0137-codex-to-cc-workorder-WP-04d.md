---
turn: 0137
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04d
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-04d Transition definitions skeleton for main states

## Context

WP-04c is merged by turn 0136 at merge commit `11f866da17ed5d8d740082c42d9763850e054b92`.

Architecture route order remains WP-04. Source plan WP-04 / T-04-04 is:

- For 20 main states, register command, event, and target-state skeletons.
- Input/precondition: T-04-03.
- Output/write scope: transition definitions.
- Validation/gate: table-driven tests cover every transition.

This WO is a narrow local transition-definition slice only. It should build structural metadata over the WP-04c state-machine foundation, not executable command handlers or external APIs.

## Base / branch / PR

- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `11f866da17ed5d8d740082c42d9763850e054b92`
- Suggested branch: `rebuild/wp-04d-transition-definitions`
- Open a PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not enable auto-merge.

## Authorized scope

Build the smallest deterministic transition-definition skeleton needed for T-04-04.

Expected behavior:

1. Use the existing canonical state table and WP-04c `TransitionRegistry` / `MainState` / guard interfaces as the source of truth. Do not invent extra states or silently pad the state set. If the codebase does not expose enough source facts to map the plan's “20 main states” requirement, report a BLOCKER with the exact observed state count and source table.
2. Add transition definition records for the canonical main-state path: source state, command skeleton id/type, event skeleton id/type, target state, and optional guard reference/hook name where appropriate. Keep these records metadata-only; they must not execute commands or mutate project state.
3. Provide deterministic registry/list/lookup helpers for transition definitions. Duplicate command ids, duplicate event ids, duplicate source/target edges, unknown states, target mismatch with WP-04c transition registry, blank ids, or malformed entries must fail closed with stable error codes.
4. Cover every registered transition with table-driven tests. Tests must prove deterministic ordering/serialization and that each definition's target is accepted by the WP-04c `TransitionRegistry`.
5. Keep all behavior local and side-effect free. Listing/lookup/validation must not create or modify project files.
6. Preserve WP-04a/WP-04b/WP-04c behavior and tests. Existing create/query/list/timeline/state-machine registry behavior must remain compatible.

## Explicit non-scope

This WO does **not** authorize any of the following:

- ApprovalRequest lifecycle, approval decisions, expiration/cancel semantics.
- A0-A3 gate policy evaluator.
- HTTP API, OpenAPI, web server, middleware, status headers, or API client.
- CLI commands.
- Actual command handlers, command execution, command idempotency, or optimistic concurrency headers.
- Async operation resource, outbox, broker, queue, PostgreSQL event store, migrations, multi-writer locking, or cross-store transactionality.
- Project cancellation command implementation or cancellation event semantics beyond inert skeleton metadata if already present in the canonical transition table.
- Auth roles or permissions implementation.
- Docker / Compose / container images.
- `.github/workflows`, branch protection/ruleset, secrets/token changes.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, or scientific method/QC/claim semantics.

For clarity: this WO authorizes only local transition-definition metadata and validation/tests. It does not authorize executable API/CLI/application command behavior.

## Validation required before REPORT

Run and report exact commands/results:

- Targeted tests for transition definition registry/list/lookup, deterministic ordering/serialization, complete table-driven coverage of registered transitions, duplicate/malformed definition rejection, target mismatch rejection, unknown state rejection, and side-effect-free/no-write checks.
- Existing WP-04c focused tests (`tests.test_state_machine_registry`) and any WP-04a/WP-04b tests affected by imports or state definitions.
- Full unittest discovery.
- `make lint`.
- `make format-check`.
- `git diff --check`.
- GitHub required CI on the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

If a command is unavailable in your environment, report the exact blocker instead of substituting silent success.

## REPORT requirements

When done, send a REPORT turn to Codex with:

- PR number, branch, base SHA, head SHA.
- Changed files and why each is in scope for T-04-04.
- The exact source table used and the observed count of main states/transitions covered.
- Exact validation command outputs summarized with pass/fail.
- Confirmation that forbidden scopes above were not touched.
- Any compatibility or design choice that affects later WP-04e / T-04-05 slicing.