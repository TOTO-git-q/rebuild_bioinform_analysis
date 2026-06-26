---
turn: 0122
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04a
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-04a CreateProject command foundation

## Context

WP-03b is merged by turn 0121 at merge commit `fa5801c6b36136965b3da4dbab4a78c6e58bda24`.

Architecture route order is WP-03 -> WP-04. Source plan WP-04 is "项目、审批、状态机 API 与 CLI". This WO starts only the first narrow slice of WP-04:

- T-04-01: implement CreateProject command, preserving OriginalRequest and initial ProjectPolicy.

## Base / branch / PR

- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `fa5801c6b36136965b3da4dbab4a78c6e58bda24`
- Suggested branch: `rebuild/wp-04a-create-project-command`
- Open a PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not enable auto-merge.

## Authorized scope

Implement the smallest application/control-plane slice that can create a project locally and auditably, using the existing core contracts.

Expected behavior:

1. Add a CreateProject command handler/service using existing schemas and helpers where possible: `Project`, `OriginalRequest`, `ProjectPolicy`, `ProjectState`, `build_initial_state()`, `build_event()`, `append_event()`, `load_state()`, and `verify_projection()`.
2. Store the user's original request verbatim. The original text/bytes and hash must be independently checkable; normalization/defaulting must not overwrite the original request.
3. Create or persist the initial `ProjectPolicy` as a versioned/content-hashable object and bind the initial project state to the exact policy reference.
4. Record an initial project-created/intake event in the append-only event log so timeline reconstruction can prove project creation without reading chat history.
5. Use explicit command id/idempotency behavior if the existing local store shape supports it. A true retry must not create a duplicate event; a same-key conflicting CreateProject payload must fail closed, consistent with WP-03b.
6. Return a deterministic, testable result object containing at minimum the project id, original request id/ref, policy id/ref, current stage, and event id/ref, using names consistent with the existing codebase.

Prefer existing module patterns. If a new module is needed, keep it under the existing `auto_bioinfo` package boundary and keep it narrowly named for command/control-plane logic. Do not refactor unrelated schema, event-store, method, evidence, report, or execution modules.

## Explicit non-scope

This WO does **not** authorize any of the following:

- T-04-02..T-04-12 beyond what is strictly necessary for T-04-01 tests.
- HTTP API, OpenAPI, web server, middleware, status headers, or API client.
- CLI command implementation.
- ApprovalRequest lifecycle beyond using existing schema refs if needed.
- Transition registry for all 20 main states.
- A0-A3 policy evaluator.
- Async operation resource, outbox, broker, queue, PostgreSQL event store, migrations, multi-writer locking, or cross-store transactionality.
- Docker / Compose / container images.
- `.github/workflows`, branch protection/ruleset, secrets/token changes.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, or scientific method/QC/claim semantics.

For clarity: this WO does **not** authorize `.github/workflows` or Docker changes.

## Validation required before REPORT

Run and report exact commands/results:

- Targeted tests for CreateProject success, original request verbatim preservation, hash/ref stability, initial policy binding, initial event/timeline reconstruction, and idempotent retry/conflict behavior if implemented.
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
- Any compatibility or design choice that affects later WP-04b+ slicing.