---
turn: 0044
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-01
status: OPEN
date: 2026-06-25
---

# WORK_ORDER — WP-01: repository skeleton, development environment and quality gates

## Authorization

WP-00 has been merged by PR #2 at merge commit `1fd8844c3f4f50d04d64ad962aaaa69b48d0764a`.
Start **WP-01 only** on a new work branch from `rebuild/auto-bioinfo-core`.

Suggested branch name: `rebuild/wp-01-engineering-skeleton-quality-gates`.

Do not start WP-02. Do not self-merge. Complete WP-01 with a PR and REPORT turn back to CODEX.

## Source of truth

Use the approved WP route from turn 0039 and the WP-01 section of:

- `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md`

WP-01 title: **仓库骨架、开发环境与质量门**.

Goal: establish the shared engineering skeleton for all subsequent work so each change can be reproducibly installed, tested, and audited.

Entry condition is satisfied by WP-00 merge: directory structure and compatibility strategy are confirmed.

## Required tasks

Implement WP-01 tasks T-01-01 through T-01-12, scoped to engineering skeleton and quality gates:

1. T-01-01: Create or adjust modular directories while preserving existing compatible entry points; do not delete preserved modules.
2. T-01-02: Pin package management / lockfile and dependency groups for dev, test, and runtime.
3. T-01-03: Establish a unified configuration model separating environment variables, non-sensitive config, and secret references; secrets must not enter the repo.
4. T-01-04: Establish local Compose for API, Worker, Postgres, Broker, and object storage, with healthcheck path.
5. T-01-05: Establish database migration framework and empty baseline migration with upgrade/downgrade validation on a temporary database.
6. T-01-06: Establish structured logging fields: time, level, service, project, correlation, task_run; add sensitive-field filtering tests.
7. T-01-07: Establish lint, format, type-check, unit-test, and coverage commands; local and CI commands must be consistent.
8. T-01-08: Establish basic CI pipeline: install, lint, type, unit, migration; clean branches must run and failures must block merge.
9. T-01-09: Establish test directory and fixture lifecycle rules; example tests must run with isolated DB/object storage fixtures.
10. T-01-10: Establish container image build and base-image digest policy; build must not include secrets and image must start.
11. T-01-11: Establish license, third-party dependency inventory, and SBOM generation entry point.
12. T-01-12: Establish PR/change templates requiring Requirement ID, Task ID, tests, and rollback fields.

## Boundaries

- Preserve reusable existing `auto_bioinfo` capabilities identified by WP-00; do not rewrite preserved modules just to fit the new skeleton.
- WP-01 may add or adjust engineering/config/CI/container/test skeleton files needed for the tasks above.
- `.github/` changes are allowed only for WP-01 CI and PR/change templates; do not modify rulesets, secrets, repository permissions, or credentials.
- Do not add business/scientific analysis logic, GEO integration, LLM integration, DESeq2, Nextflow workflow implementation, public deployment, paid services, or real human data use in WP-01.
- If pushing workflow files or any CI-related change is blocked by GitHub permission, report a BLOCKER; do not expand robot credentials yourself.
- Do not write token, private key, password, or secret values into turn files, logs, repo files, fixtures, or reports.

## Expected deliverables

- Work branch pushed to origin.
- PR against `rebuild/auto-bioinfo-core`.
- Updated or new engineering skeleton files required by T-01-01..T-01-12.
- Documentation for commands, local startup, healthchecks, fixture lifecycle, dependency/SBOM entry, and rollback expectations.
- REPORT turn back to CODEX with branch, PR number, head SHA, changed file summary, task-to-deliverable mapping, validation commands, results, and hard-stop confirmation.

## Required validation evidence

At minimum, report real command names, exit codes, and results for:

- install / dependency lock validation or the closest repo-native equivalent;
- lint / format check;
- type check if configured;
- unit tests;
- migration upgrade/downgrade check against a temporary database or clearly documented local substitute;
- Compose startup and healthcheck, if supported in the current environment;
- container build/start check, if supported in the current environment;
- SBOM/dependency inventory command;
- `git diff --check`.

If an environment capability is unavailable, report it as unavailable with the exact blocker and the closest safe validation performed. Do not claim PASS for checks that did not run.

## Exit criteria

WP-01 is complete only when a new environment can be installed from scratch, API/Worker healthchecks succeed or have a documented local-equivalent proof, CI quality gates are defined and runnable, and no business logic has been added.

After completion, stop and wait for Codex independent review.
