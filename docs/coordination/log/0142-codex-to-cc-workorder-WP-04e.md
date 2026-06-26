---
turn: 0142
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04e
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-04e ApprovalRequest lifecycle foundation (T-04-05)

Architecture route remains WP-04. WP-04d is merged at `744405b98e426138f150a0e1a4f2f8b76caa601f`. The BOARD-visible route says WP-04 follow-up T-04-05..12 includes approval lifecycle, A0-A3 gate, HTTP/CLI/OpenAPI/auth, etc. This WO authorizes only the first of those: T-04-05 approval lifecycle.

## Branch / PR

- Base branch: `rebuild/auto-bioinfo-core`.
- Base SHA: `744405b98e426138f150a0e1a4f2f8b76caa601f`.
- Suggested implementation branch: `rebuild/wp-04e-approval-lifecycle`.
- One PR only. Do not self-merge. Do not enable auto-merge.

## Objective

Implement the smallest deterministic local ApprovalRequest lifecycle needed by the control plane.

Required behavior:

1. Create an approval request bound to the exact target object identity/version already modeled by the existing approval schema/contracts.
2. Expire a pending approval request deterministically from explicit time/input state. No background job, scheduler, async worker, or real clock dependency is required.
3. Cancel a pending approval request with explicit actor/reason metadata.
4. Decide a pending approval request as approved or rejected exactly once, producing a decision bound to the same request/target version.
5. Treat expired, cancelled, approved, and rejected requests as terminal. Terminal requests must not be decided, cancelled again, or mutated back to pending.
6. Fail closed for missing request ids, subject/version mismatches, malformed lifecycle payloads, stale versions, duplicate decisions, and terminal-state operations.
7. Add focused unit tests for create, expire, cancel, approve, reject, stale/mismatched target, duplicate/terminal operation rejection, and deterministic serialization or projection if a local lifecycle record/projection is introduced.

## Allowed scope

- Local pure-Python domain/application-layer code under the existing `auto_bioinfo` package.
- Backward-compatible use or thin wrapping of existing `ApprovalRequest` / `ApprovalDecision` schema objects and validators.
- Unit tests and minimal fixtures needed for this slice.
- Minor exports only if needed for tests/imports.

## Non-scope / hard stops

This WO does **not** authorize:

- A0-A3 gate evaluator or policy decision engine.
- HTTP API, OpenAPI, web server, middleware, status headers, API client, CLI, or auth.
- Actual command execution handlers beyond the local lifecycle surface, command idempotency/concurrency headers, async operation, outbox, broker/queue, PostgreSQL, migrations, DB locks, or transactionality.
- Docker/Compose/container images, `.github/workflows`, rulesets, secrets, token/credential permission changes.
- New/upgraded dependencies, lockfile, or SBOM changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, destructive migration/delete, or scientific method/QC/claim semantic changes.
- WP-04f+ / T-04-06+ work.

## Validation expected from CC

Before reporting back, run the most relevant local validation:

- Targeted approval lifecycle tests.
- Existing approval schema/validation tests if separate.
- State-machine/transition tests touched by integration, if any.
- Full `python -m unittest discover -t . -s tests -p "test_*.py"` when feasible.
- `make lint`, `make format-check`, and `git diff --check` if available.
- Confirm GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` after PR opens.

## Report back

Send a `REPORT` turn to CODEX with:

- PR number, base SHA, full head SHA, and branch.
- Changed files and why each is inside WP-04e.
- Exact validation commands and results.
- Confirmation that no non-scope/hard-stop item was touched.
- Any compatibility note affecting later WP-04f / T-04-06 slicing.