---
turn: 0047
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-01a
status: OPEN
date: 2026-06-25
---

# WORK_ORDER — WP-01a: directory skeleton and lockfile / dependency groups

## Authorization

Start **WP-01a only** from `rebuild/auto-bioinfo-core`.

This work order is the split replacement for the first slice of WP-01 after the CEO ruling in turn 0046.

Suggested branch name: `rebuild/wp-01a-skeleton-lockfile`.

Do not start WP-01b, WP-01c, CI workflow, Docker / Compose / container-image work, or WP-02 in this branch.

## Scope

Implement only:

1. **T-01-01**: Create or adjust the modular repository directory skeleton while preserving existing compatible entry points.
2. **T-01-02**: Pin package management / lockfile and declare dependency groups for development, testing, and runtime.

## Source of truth

Use:

- turn 0039 for the approved architecture baseline and WP route;
- turn 0046 for WP-01 split / guardrail ruling;
- `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` for WP-01 task definitions;
- WP-00 artifacts merged in PR #2, especially the preserve / replace / retire and compatibility findings.

## Required behavior

For T-01-01:

- Establish the minimal modular directory skeleton needed for later WP-01 slices.
- Preserve existing reusable `auto_bioinfo` capabilities identified by WP-00.
- Keep compatible import / CLI entry points working where they already exist.
- Do not delete preserved modules.
- Do not rewrite business/scientific logic to fit the skeleton.

For T-01-02:

- Use the repository's appropriate Python packaging mechanism.
- Declare dependency groups for at least runtime, development, and testing if the chosen package tool supports groups.
- Add or update the lockfile if the chosen tool requires one.
- Keep dependency additions minimal and justified by WP-01a.
- Do not add Docker, Compose, CI workflow, database, broker, object storage, LLM, GEO, DESeq2, Nextflow implementation, or external service dependencies in WP-01a unless already required by existing baseline behavior.

## Explicit non-scope

- No `.github/workflows` in WP-01a. CI is authorized by CEO but will be a later independent small WO after WP-01c.
- No Docker / Compose / Dockerfile in WP-01a. Docker is plan-authorized by D-03 but deferred to later independent small WO(s).
- No migration framework, structured logging implementation, fixture lifecycle framework, SBOM, PR template, or container image work in WP-01a unless a tiny placeholder is strictly necessary to keep packaging coherent; if so, label it as placeholder and do not claim the later task is complete.
- No WP-02.

## Validation requirements

Report real commands, exit codes, and results for:

- package metadata validation / install check from a clean or controlled environment, or the closest safe equivalent;
- import smoke test for preserved compatible entry points;
- existing unit test suite, or a focused subset if full suite is unavailable with exact reason;
- lockfile consistency check if applicable;
- `git diff --check`.

Do not claim a validation passed unless it actually ran.

## Deliverables

- Work branch pushed to origin.
- PR against `rebuild/auto-bioinfo-core`.
- REPORT turn back to CODEX with:
  - branch name;
  - PR number;
  - full 40-character head SHA;
  - changed file list;
  - T-01-01 / T-01-02 requirement-to-file mapping;
  - validation commands and real results;
  - confirmation that WP-01b/WP-01c/CI/Docker/WP-02 were not started;
  - hard-stop confirmation.

Stop after REPORT and wait for Codex independent review.
