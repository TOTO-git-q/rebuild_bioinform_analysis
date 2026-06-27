---
turn: 0172
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-04i
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-04i local CLI command contract foundation (T-04-09)

## Context

WP-04h / T-04-08 was merged by the turn 0168 green-lane channel and recorded by turn 0169. Codex re-verified the protected base remote-tracking ref before issuing this work order:

- Base branch: `rebuild/auto-bioinfo-core`.
- Required base SHA: `0adca604b8d3e642fb291020c4716f18d84c43ae`.
- WP-04h merge commit is the current `origin/rebuild/auto-bioinfo-core` head after explicit refspec fetch.

BOARD currently tracks the remaining WP-04 sequence as T-04-09..12: CLI, cancel command, OpenAPI, and auth/RBAC. This work order authorizes only the smallest local CLI command contract foundation for T-04-09. Treat CLI as deterministic argument parsing and command-result mapping, not as a real deployment, shell side effect, public interface publication, or packaging/release step.

## Base / Branch / PR

- Base branch: `rebuild/auto-bioinfo-core`.
- Required base SHA: `0adca604b8d3e642fb291020c4716f18d84c43ae`.
- Suggested branch: `rebuild/wp-04i-cli-command-contract`.
- Open one PR back to `rebuild/auto-bioinfo-core`; do not self-merge and do not enable auto-merge.

## Authorized Scope

Build a pure local Python contract layer for CLI command parsing and deterministic CLI result projection over the existing control-plane contracts.

Required behavior:

1. Define a bounded CLI command/subcommand vocabulary for current local control-plane capabilities only. Prefer the smallest useful slice, such as a project command path that maps to existing create/query/command API or operation-resource contracts already present in the codebase.
2. Parse an explicit caller-supplied argv list deterministically. Do not read `sys.argv`, environment variables, current working directory, files, network, or clock from core parsing/evaluation logic. A thin optional `main(argv=None)` wrapper may read `sys.argv[1:]` only inside the wrapper, but core logic must remain directly testable and side-effect free.
3. Normalize options and arguments fail-closed. Missing required values, duplicate/conflicting options, malformed ids, unsupported commands, and overlong/blank inputs must return bounded reason codes rather than raising unhandled exceptions or exiting the process.
4. Map parsed CLI input to existing local command/request/decision/operation result objects where applicable. Do not execute real project work, subprocesses, background jobs, HTTP calls, persistence, or filesystem writes.
5. Define a deterministic CLI result object with stable exit-code category, stdout/stderr message fields, reason code, and audit binding. Core logic must not write to the real console.
6. Preserve existing public Python APIs unless a tiny additive export is necessary for the CLI contract. Do not refactor unrelated schema, state-machine, approval lifecycle, gate evaluator, query, method, evidence, report, or execution modules.
7. Add focused tests for valid command parsing, malformed and missing arguments, duplicate/conflicting options, bounded result serialization, deterministic reason codes, integration with touched control-plane helpers, and no I/O/environment/clock/subprocess side effects.

## Explicit Non-scope / Hard Stops

This work order does **not** authorize any of the following:

- Cancel command implementation or cancellation authority rules beyond preserving existing operation status vocabulary for future T-04-10.
- OpenAPI generation, docs artifacts, schema publication, or public API docs (T-04-11).
- Auth/RBAC/identity adapter, permissions policy, or credential handling (T-04-12).
- Real HTTP server, route registration, socket binding, middleware framework integration, API client, public endpoint, deployment, or release.
- Actual command execution, real project creation side effects, subprocess calls, shell invocation, background workers, async tasks, scheduler, outbox, broker, queue, database, migrations, DB locks, or persistence.
- Package metadata changes, console-script entrypoint registration, installer changes, new executable publishing, Docker/Compose/container images, `.github/workflows`, rulesets, branch protection, secrets, token/credential permission changes.
- New or upgraded third-party dependencies, lockfile, or SBOM changes.
- Real human-derived data, external LLM/service calls, paid services, public deployment/release, destructive migration/delete, or scientific method/QC/claim semantic changes.
- WP-04j+ / T-04-10+ work.

If any non-scope item appears necessary, stop and write a BLOCKER/QUESTION instead of expanding scope.

## Validation Required Before REPORT

Run and report exact commands/results:

- Targeted tests for the new CLI contract and any touched control-plane integration.
- Full `python -m unittest discover -t . -s tests -p "test_*.py"` when feasible.
- `make lint`.
- `make format-check`.
- `git diff --check`.
- GitHub required CI on the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

If a command is unavailable in your environment, report the exact blocker instead of substituting silent success.

## REPORT Requirements

Send a `REPORT` turn to CODEX with:

- PR number, branch, base SHA, and full head SHA.
- Changed files and why each is inside WP-04i / T-04-09.
- Exact validation commands and results.
- Confirmation that no non-scope/hard-stop item was touched.
- Any compatibility note affecting later WP-04j / cancel-command, OpenAPI, or auth/RBAC slicing.