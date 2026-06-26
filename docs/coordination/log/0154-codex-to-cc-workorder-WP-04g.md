---
turn: 0154
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04g
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-04g command API idempotency and optimistic concurrency contract (T-04-07)

## Context

WP-04f / T-04-06 is merged by turn 0153 at merge commit `b7c271a6d7644247bfaf2773d5fb4957a21184fd`.

Architecture route remains WP-04. Source plan WP-04 / T-04-07 is:

- Implement command API idempotency and optimistic concurrency headers.
- Input/precondition: T-03.
- Output: HTTP middleware.
- Acceptance: duplicate/stale-version requests return standardized errors.

This WO authorizes only the smallest local command-API contract/middleware foundation. It does **not** authorize a real web server, public endpoint, OpenAPI docs, CLI, auth, async operation resource, or deployment.

## Base / Branch / PR

- Base branch: `rebuild/auto-bioinfo-core`.
- Required base SHA: `b7c271a6d7644247bfaf2773d5fb4957a21184fd`.
- Suggested branch: `rebuild/wp-04g-command-api-concurrency`.
- Open one PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not enable auto-merge.

## Authorized Scope

Build a pure local Python contract layer for command API idempotency and optimistic concurrency. Treat "HTTP middleware" as standard-library-compatible request/header contract code inside the existing package boundary, not as a running HTTP service.

Required behavior:

1. Define explicit, bounded header names and normalized parsing for command idempotency and expected-version/optimistic-concurrency inputs. Header casing must be handled deterministically; duplicated/conflicting header facts must fail closed.
2. Require a nonblank idempotency key for mutating command API requests. Missing, blank, malformed, or overlong keys must return bounded standardized errors.
3. Bind idempotency to the exact command identity and canonicalized payload fingerprint. Same key + same command/payload may be treated as replay/duplicate; same key + different command or payload must fail closed as an idempotency conflict.
4. Define an optimistic concurrency contract that compares an expected version supplied in request headers against an explicit current version supplied by the caller. Stale or malformed expected versions must return bounded standardized errors.
5. Provide deterministic result/error objects suitable for a future HTTP adapter, with stable status categories and reason codes. Do not invent real HTTP server behavior beyond these local contract outputs.
6. Keep the implementation pure and deterministic: no file I/O, network, environment inspection, real clock, threads, async worker, DB, outbox, broker, queue, or command execution side effects.
7. Reuse existing control-plane command/state/gate types where they fit. Do not refactor unrelated schema, state-machine, approval lifecycle, gate evaluator, query, method, evidence, report, or execution modules.
8. Add focused tests for success, missing idempotency key, same-key replay, same-key conflict, stale expected version, malformed expected version, duplicate/conflicting headers, deterministic serialization, and no I/O/side effects.

## Explicit Non-scope / Hard Stops

This WO does **not** authorize any of the following:

- Real HTTP server, route registration, socket binding, public endpoint, middleware framework integration, API client, or deployment.
- OpenAPI generation or docs artifacts (T-04-11).
- CLI commands (T-04-09).
- Auth/RBAC/identity adapter or permissions policy (T-04-12).
- Async operation resource, polling API, outbox, broker, queue, scheduler, worker, PostgreSQL, migrations, DB locks, cross-store transactionality, or multi-writer locking.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Docker/Compose/container images, `.github/workflows`, rulesets, secrets, token/credential permission changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, destructive migration/delete, or scientific method/QC/claim semantic changes.
- WP-04h+ / T-04-08+ work.

## Validation Required Before REPORT

Run and report exact commands/results:

- Targeted tests for command API header parsing, idempotency replay/conflict behavior, optimistic concurrency stale-version behavior, deterministic serialization, and duplicate/conflicting header rejection.
- Any existing control-plane tests touched by integration.
- Full `python -m unittest discover -t . -s tests -p "test_*.py"` when feasible.
- `make lint`.
- `make format-check`.
- `git diff --check`.
- GitHub required CI on the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

If a command is unavailable in your environment, report the exact blocker instead of substituting silent success.

## REPORT Requirements

Send a `REPORT` turn to CODEX with:

- PR number, branch, base SHA, and full head SHA.
- Changed files and why each is inside WP-04g / T-04-07.
- Exact validation commands and results.
- Confirmation that no non-scope/hard-stop item was touched.
- Any compatibility note affecting later WP-04h / T-04-08 slicing.