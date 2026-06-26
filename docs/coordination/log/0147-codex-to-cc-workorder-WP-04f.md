---
turn: 0147
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04f
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-04f A0-A3 gate evaluator foundation (T-04-06)

Architecture route remains WP-04. WP-04e is merged at `560ae564041e83800cc2ea29bdb46e5a5e8efccc`. The BOARD-visible route says WP-04 follow-up T-04-06..12 includes A0-A3 gate, HTTP/CLI/OpenAPI/auth, etc. This WO authorizes only the first of those: a local A0-A3 gate evaluator foundation.

## Branch / PR

- Base branch: `rebuild/auto-bioinfo-core`.
- Base SHA: `560ae564041e83800cc2ea29bdb46e5a5e8efccc`.
- Suggested implementation branch: `rebuild/wp-04f-a0-a3-gate-evaluator`.
- One PR only. Do not self-merge. Do not enable auto-merge.

## Objective

Implement the smallest deterministic local A0-A3 gate evaluator needed by the control plane.

Required behavior:

1. Provide a pure-Python local evaluator that consumes explicit in-memory inputs only. It must not read files, call the network, inspect environment variables, use a real clock, or perform command execution.
2. Model A0-A3 gate names with bounded constants/enums and reject unknown gate names or malformed gate inputs fail-closed.
3. Produce bounded, deterministic gate decisions such as pass/block/needs-approval/insufficient, using stable error/reason codes. Keep the decision vocabulary explicit and test-covered.
4. Bind every gate decision to the exact project/request/policy/approval object identity/version supplied in the input. Missing or mismatched binding facts must fail closed.
5. Integrate with the existing WP-04e approval lifecycle only as data: the evaluator may consume an `ApprovalLifecycleRecord` or existing approval schema object and should treat pending/expired/cancelled/rejected/granted states conservatively. It must not mutate approval records.
6. Ensure stale approvals or decisions for a different subject/version cannot pass a gate.
7. Add focused tests for A0-A3 pass/block cases, malformed input rejection, unknown gate rejection, approval state handling, stale/mismatched approval rejection, deterministic serialization, and no mutation of input records.

## Allowed scope

- Local pure-Python domain/application-layer code under the existing `auto_bioinfo` package.
- Reuse of existing Project/OriginalRequest/ProjectPolicy/Approval/ApprovalLifecycleRecord schema or lifecycle objects as data inputs.
- Unit tests and minimal fixtures needed for this slice.
- Minor exports only if needed for tests/imports.

## Non-scope / hard stops

This WO does **not** authorize:

- HTTP API, OpenAPI, web server, middleware, status headers, API client, CLI, or auth.
- Actual command execution handlers, command idempotency/concurrency headers, async operation, outbox, broker/queue, PostgreSQL, migrations, DB locks, or transactionality.
- Docker/Compose/container images, `.github/workflows`, rulesets, secrets, token/credential permission changes.
- New/upgraded dependencies, lockfile, or SBOM changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, destructive migration/delete, or scientific method/QC/claim semantic changes.
- WP-04g+ / T-04-07+ work.

## Validation expected from CC

Before reporting back, run the most relevant local validation:

- Targeted A0-A3 gate evaluator tests.
- Approval lifecycle tests if the evaluator consumes approval records.
- Existing schema/validation tests touched by integration, if any.
- Full `python -m unittest discover -t . -s tests -p "test_*.py"` when feasible.
- `make lint`, `make format-check`, and `git diff --check` if available.
- Confirm GitHub required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` after PR opens.

## Report back

Send a `REPORT` turn to CODEX with:

- PR number, base SHA, full head SHA, and branch.
- Changed files and why each is inside WP-04f.
- Exact validation commands and results.
- Confirmation that no non-scope/hard-stop item was touched.
- Any compatibility note affecting later WP-04g / T-04-07 slicing.