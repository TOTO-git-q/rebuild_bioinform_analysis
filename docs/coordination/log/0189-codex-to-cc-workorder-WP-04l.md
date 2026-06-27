---
turn: 0189
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04l
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-04l local auth/RBAC contract foundation (T-04-12)

## Context

WP-04k / T-04-11 local OpenAPI contract/spec foundation was merged by the green-lane channel and independently confirmed by turn 0188.

- Base branch: `rebuild/auto-bioinfo-core`.
- Required base SHA: `0afcc43902e6f91edc09a00cfb0f2968ea8184a1`.
- WP-04k merge commit is the current remote `rebuild/auto-bioinfo-core` tip.

BOARD tracks the remaining WP-04 follow-up as auth/RBAC. This work order authorizes only the smallest local auth/RBAC contract foundation for T-04-12. Treat auth/RBAC here as deterministic, inert, local policy/identity/permission contract data over already-existing control-plane command/query/operation/cancel/OpenAPI shapes. It is not a real authentication service, token system, credential store, HTTP middleware, deployed endpoint, or privilege expansion.

## Base / Branch / PR

- Base branch: `rebuild/auto-bioinfo-core`.
- Required base SHA: `0afcc43902e6f91edc09a00cfb0f2968ea8184a1`.
- Suggested branch: `rebuild/wp-04l-auth-rbac-contract`.
- Open one PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not enable auto-merge.

## Authorized Scope

Build a pure local Python contract layer for auth/RBAC decisions over existing control-plane actions and resources.

Required behavior:

1. Define bounded local actor/principal, role, permission/action, and resource-scope shapes. These must be plain deterministic data structures and must come only from explicit caller-supplied facts.
2. Provide a local auth/RBAC decision helper that maps explicit caller facts to bounded outcomes such as allow/deny/needs-approval or an equivalent conservative vocabulary. It must fail closed by default.
3. Bind permissions/actions only to existing local control-plane surfaces already merged through WP-04k, such as project query/list/timeline/blocker projection, command admission, operation polling/result projection, cancel command evaluation, CLI command categories, and OpenAPI operation identifiers. Do not invent real server behavior or new product capability.
4. Reject malformed or ambiguous authority facts: blank actor/role/action/resource, unknown role/action, wildcard or catch-all permission unless explicitly bounded in tests, cross-project/resource mismatch, duplicate contradictory grants, unsupported scope, stale/malformed version facts if a version binding is used, and any truthy authority flag that is not the exact accepted form.
5. Keep all identity and permission handling inert. Do not inspect environment variables, OS users, GitHub identity, files, network, clocks, tokens, secrets, sessions, passwords, certificates, or external auth providers.
6. If touching the OpenAPI contract, only add deterministic local security/permission annotations that bind to this new inert contract. Do not publish docs, require a real security scheme, register routes, enforce middleware, or create public API behavior.
7. Preserve existing public Python APIs unless a tiny additive export is necessary for the local auth/RBAC contract. Do not refactor unrelated schema, state-machine, approval lifecycle, gate evaluator, query, method, evidence, report, execution, CLI, operation, cancel, or OpenAPI modules beyond directly necessary additive mapping.
8. Add focused tests for allow/deny/needs-approval behavior, malformed authority facts, missing/unknown role/action/resource, scope mismatch, deterministic serialization/reason codes, optional OpenAPI annotation binding if touched, and no I/O/environment/network/clock/token/server side effects.

## Explicit Non-scope / Hard Stops

This work order does **not** authorize any of the following:

- Real credential handling, token/secret parsing or generation, OAuth/JWT/password/session/cookie/certificate support, user database, identity provider integration, key storage, privilege expansion, robot credential permission changes, or secrets/token/ruleset changes.
- Real HTTP server, middleware enforcement, route registration, socket binding, API client, public endpoint, live service, deployment, release, public hosted docs, or automatic publication.
- Real worker/process cancellation, async worker/outbox/broker/queue/DB integration, persistence changes, migrations, DB locks, scheduler integration, or command execution side effects.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Package metadata changes, console-script entrypoint registration, installer changes, Docker/Compose/container images, `.github/workflows`, rulesets, branch protection, secrets, token/credential permission changes.
- Real human-derived data, external LLM/service calls, paid services, destructive migration/delete, or scientific method/QC/claim semantic changes.
- WP-05+ work or any expansion beyond WP-04l / T-04-12 local auth/RBAC contract foundation.

If any non-scope item appears necessary, stop and write a BLOCKER/QUESTION instead of expanding scope.

## Validation Required Before REPORT

Run and report exact commands/results:

- Targeted tests for the local auth/RBAC contract and any touched control-plane/OpenAPI projection helpers.
- Existing control-plane tests touched by integration.
- Full `python -m unittest discover -t . -s tests -p "test_*.py"` when feasible.
- `make lint`.
- `make format-check`.
- `git diff --check`.
- GitHub required CI on the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

If a command is unavailable in your environment, report the exact blocker instead of substituting silent success.

## REPORT Requirements

Send a `REPORT` turn to CODEX with:

- PR number, branch, base SHA, and full head SHA.
- Changed files and why each is inside WP-04l / T-04-12.
- Exact validation commands and results.
- Confirmation that no non-scope/hard-stop item was touched.
- Any compatibility note affecting the next WP after WP-04.

Important: because Codex must review and then either request fixes or green-lane authorize merge, this REPORT must use `status: OPEN`.