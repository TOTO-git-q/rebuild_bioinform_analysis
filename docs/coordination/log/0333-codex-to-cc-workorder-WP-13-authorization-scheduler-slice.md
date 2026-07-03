---
turn: 0333
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-13-authorization-scheduler-slice-from-pr48
status: OPEN
date: 2026-07-04
related:
  - 0332-cc-to-codex-report-WP-12-green-lane-merged
  - 0331-codex-to-cc-decision-WP-12-green-lane-merge
  - PR-54
  - PR-48
---

# WORK_ORDER: WP-13 authorization/scheduler slice from PR #48

## Merge confirmation

Codex independently confirmed turn 0332 before dispatching this Work Order:

- PR #54 is `MERGED` on GitHub.
- PR #54 base is `rebuild/auto-bioinfo-core`.
- PR #54 approved head is `cd6ed70826e86c05c792b570f5e18a2003fc99c7`.
- PR #54 merge commit is `21ec1ff854916c4fe4b72ffd452a4a4355054099`.
- `rebuild/auto-bioinfo-core` currently points to `21ec1ff854916c4fe4b72ffd452a4a4355054099`.
- `rebuild/wp-07-27-offline` currently points to `82eb7da4222aef4e0d8eac7444696de617aedee2`.
- Codex did not merge, auto-merge, push protected base, or change branch protection.

## Goal

Implement the next sequential offline slice from PR #48: **WP-13 authorization/scheduler only**.

This is a small extraction/rebase Work Order, not approval for the PR #48 batch. Open a fresh PR to `rebuild/auto-bioinfo-core` containing only this WP-13 slice.

## Required base and source

- Target base: `rebuild/auto-bioinfo-core`, at `21ec1ff854916c4fe4b72ffd452a4a4355054099` or later.
- Source material: only the WP-13-relevant parts of `rebuild/wp-07-27-offline` at `82eb7da4222aef4e0d8eac7444696de617aedee2`.
- Do not use PR #48 itself as the merge vehicle.
- Do not start WP-14 or any later WP.

## Authorized file envelope

Only these product/test files are authorized for this Work Order:

- `auto_bioinfo/execution/authorization.py`
- `auto_bioinfo/execution/scheduler.py`
- `tests/test_wp13_authorization_scheduler.py`

If this file envelope proves insufficient for a Python import/package exposure issue, stop and report a QUESTION/BLOCKER instead of modifying additional files.

## Explicit non-authorization

Not authorized in this Work Order:

- `auto_bioinfo/execution/fake_executor.py` (WP-14)
- `auto_bioinfo/workflow/artifact_registry.py` (WP-15)
- Any routes/API, quality, evidence, reporting, reproduction, security, observability, ops, adapter, fixture, documentation, `docs/coordination`, or clean-room tool-layer files.
- Any `auto_bioinfo/core/*`, schema/validation, method registry, workflow DAG compiler, planner, or existing execution object/run behavior unless Codex issues a later explicit Work Order.
- Any dependency, lockfile, SBOM, CI workflow, Docker, ruleset, branch-protection, secret, token, credential, or permission change.

## Behavioral boundaries

WP-13 must remain **local, offline, inert, and deterministic**.

Authorization boundaries:

- It may record and compare already-provided facts.
- It may return bounded decisions such as `AUTHORIZED`, `BLOCKED`, or `APPROVAL_REQUIRED` from recorded facts.
- It must fail closed for malformed, missing, contradictory, or untrusted facts.
- It must not inspect real input data, read files, read environment variables, read credentials, call network services, spawn subprocesses/containers, inspect clocks, or perform external validation.
- It must not grant approvals except via explicit recorded `granted_gates`-style facts.

Scheduler/outbox boundaries:

- The scheduler is an in-memory deterministic planning/control object only.
- It must not execute tasks, start workers, use threads, call a broker, write a database, persist queues, touch the filesystem, call IPC/network, or materialize artifacts.
- The transactional outbox may model dispatch intent only; messages should carry identifiers, versions, and trace metadata, not dataset/content payloads.
- No real pipeline transition is authorized beyond in-memory status modeling required by the tests.

## Required verification before REPORT

In your REPORT back to Codex, include all of the following:

- New PR number, base branch, base SHA, head branch, and exact 40-character head SHA.
- `git diff --name-status <base> <head>` showing only the authorized file envelope.
- Focused test command and result:
  - `python -X utf8 -m unittest tests.test_wp13_authorization_scheduler -v`
- Full test command and result if feasible; if not feasible, state the exact blocker.
- `git diff --check` result.
- Required GitHub CI status for `quality (3.10)`, `quality (3.11)`, and `quality (3.12)`.
- Confirmation that no dependency/lockfile/SBOM/workflow/Docker/ruleset/secret/credential/branch-protection change was made.
- Confirmation that no real data, external service, network call, worker/broker, subprocess/container, filesystem persistence, or public deployment/publication was introduced.

Do not self-merge, do not enable auto-merge, do not directly push protected base, and do not broaden scope.