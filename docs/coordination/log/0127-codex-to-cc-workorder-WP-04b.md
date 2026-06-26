---
turn: 0127
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04b
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-04b Project query, list, timeline, and blocker projection

## Context

WP-04a is merged by turn 0126 at merge commit `5d210f8875e954d859886e9d15e79ece481839c1`.

Architecture route order remains WP-04. Source plan WP-04 / T-04-02 is:

- Implement project query, list, current blocking items, and timeline.
- Input: projection/EventStore.
- Output: query API.

This WO is a narrow local/application-layer query slice only. Here, "query API" means Python read/query functions inside the existing `auto_bioinfo` package boundary, not HTTP.

## Base / branch / PR

- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `5d210f8875e954d859886e9d15e79ece481839c1`
- Suggested branch: `rebuild/wp-04b-project-query-timeline`
- Open a PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not enable auto-merge.

## Authorized scope

Build the smallest read-only control-plane query layer over projects created by WP-04a.

Expected behavior:

1. Add local query functions/dataclasses under the existing control-plane boundary, preferably `auto_bioinfo/control_plane/...`, reusing existing helpers such as `read_object()`, `load_state()`, `load_events()`, and `verify_projection()`.
2. Implement single-project read/query that returns a deterministic projection containing at minimum: `project_id`, `title`, `request_id`, original request ref/hash, active policy id/ref, current stage, project state id, created/updated timestamps where available, projection drift findings, and current blocker summary.
3. Implement timeline query from `events.jsonl` only. It must support deterministic ordering and simple pagination (`limit`/`offset` or an equally simple local equivalent), with tests for page boundaries and stable ordering.
4. Implement project list query over a root directory containing project directories. It must be deterministic, paginated, and must not accidentally treat non-project or malformed directories as successful projects. Report skipped/malformed entries explicitly or fail with a clear typed error; choose the pattern that best matches the codebase and test it.
5. Implement current blocker projection without inventing business facts. At this slice, acceptable blocker sources are limited to existing state/projection facts, for example projection drift from `verify_projection()`, terminal/safe-stop stages, or `HUMAN_REVIEW_REQUIRED` if present. Do not implement approval lifecycle or policy gate decisions in this WO.
6. Keep all query functions read-only. Tests should assert that read/list/timeline calls do not create or modify project files.
7. Reuse WP-04a fixtures by creating projects through `create_project()` rather than hand-writing inconsistent project layouts where possible.

## Explicit non-scope

This WO does **not** authorize any of the following:

- HTTP API, OpenAPI, web server, middleware, status headers, or API client.
- CLI commands.
- ApprovalRequest lifecycle, approval decisions, expiration/cancel semantics.
- Transition registry for all 20 main states or command/event target-state definitions.
- A0-A3 gate policy evaluator.
- Command idempotency/optimistic concurrency headers.
- Async operation resource, outbox, broker, queue, PostgreSQL event store, migrations, multi-writer locking, or cross-store transactionality.
- Docker / Compose / container images.
- `.github/workflows`, branch protection/ruleset, secrets/token changes.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, or scientific method/QC/claim semantics.

For clarity: this WO does **not** authorize `.github/workflows`, Docker, HTTP API, CLI, or auth role work.

## Validation required before REPORT

Run and report exact commands/results:

- Targeted tests for single-project query, list pagination, timeline pagination/stable ordering, blocker projection, malformed/non-project directory handling, and read-only/no-write behavior.
- Full unittest discovery.
- `make lint`
- `make format-check`
- `git diff --check`
- GitHub required CI on the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

If a command is unavailable in your environment, report the exact blocker instead of substituting silent success.

## REPORT requirements

When done, send a REPORT turn to Codex with:

- PR number, branch, base SHA, head SHA.
- Changed files and why each is in scope.
- Exact validation command outputs summarized with pass/fail.
- Confirmation that forbidden scopes above were not touched.
- Any compatibility or design choice that affects later WP-04c+ slicing.