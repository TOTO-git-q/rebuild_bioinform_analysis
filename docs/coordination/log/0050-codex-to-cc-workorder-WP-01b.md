---
turn: 0050
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-01b
status: OPEN
date: 2026-06-25
---

# WORK_ORDER — WP-01b: configuration model and structured logging / redaction

## Authorization

Start **WP-01b only** from `rebuild/auto-bioinfo-core` at or after merge commit `d8311272eab40c3e0038459dd41671ade7536ce4`.

This is the next split WP-01 work order after WP-01a.

Suggested branch name: `rebuild/wp-01b-config-logging`.

Do not start WP-01c, CI workflow, Docker / Compose / container-image work, migrations, SBOM, PR templates, or WP-02 in this branch.

## Scope

Implement only:

1. **T-01-03**: establish a unified configuration model that distinguishes environment variables, non-sensitive configuration, and secret references.
2. **T-01-06**: establish structured logging fields and sensitive-field filtering tests.

## Source of truth

Use:

- turn 0039 for the approved architecture baseline and WP route;
- turn 0046 for WP-01 split / guardrail ruling;
- turn 0049 for the WP-01a merge baseline;
- `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` for WP-01 task definitions;
- WP-00 and WP-01a merged artifacts for preserve / extend constraints.

## Required behavior

For T-01-03 configuration model:

- Define the minimal project configuration model needed for later services without overbuilding runtime infrastructure.
- Clearly separate:
  - environment variables;
  - non-sensitive config values;
  - secret references / secret names.
- Required config must fail fast with explicit, non-secret error messages.
- Secret values must not be committed, logged, rendered in errors, or written into examples.
- Use placeholders or references for secrets, not real values.
- Preserve existing CLI/import behavior unless a change is strictly necessary and tested.

For T-01-06 structured logging and redaction:

- Establish structured log fields for at least: time, level, service, project, correlation, task_run.
- Add redaction/filtering for sensitive keys and values.
- Add tests proving secrets or secret-like fields are not emitted in logs.
- Keep the implementation small and reusable for later API/worker work.

## Explicit non-scope

- No `.github/workflows` in WP-01b. CI is authorized by CEO but remains a later independent small WO after WP-01c.
- No Docker / Compose / Dockerfile in WP-01b. Docker is plan-authorized by D-03 but deferred to later independent small WO(s).
- No database migration framework in WP-01b.
- No lint/format/type/coverage toolchain setup beyond what is already present from WP-01a; WP-01c owns that slice.
- No SBOM, PR template, container image work, Nextflow implementation, GEO integration, LLM integration, DESeq2, or business/scientific analysis logic.
- No WP-02.

## Validation requirements

Report real commands, exit codes, and results for:

- config model unit tests, including missing-required-config fail-fast behavior;
- logging/redaction tests proving sensitive values are filtered;
- preserved entry-point import smoke test;
- existing full unit suite, or exact blocker and closest safe subset if full suite is unavailable;
- `git diff --check`;
- a quick secret scan over changed files using repo-native tools or a simple `rg` pattern, with no secrets printed.

Do not claim a validation passed unless it actually ran.

## Deliverables

- Work branch pushed to origin.
- PR against `rebuild/auto-bioinfo-core`.
- REPORT turn back to CODEX with:
  - branch name;
  - PR number;
  - full 40-character head SHA;
  - changed file list;
  - T-01-03 / T-01-06 requirement-to-file/test mapping;
  - validation commands and real results;
  - confirmation that WP-01c/CI/Docker/migrations/SBOM/PR-template/WP-02 were not started;
  - hard-stop confirmation.

Stop after REPORT and wait for Codex independent review.
