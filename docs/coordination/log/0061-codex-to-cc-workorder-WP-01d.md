---
turn: 0061
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-01d
status: OPEN
date: 2026-06-25
---

# WORK_ORDER - WP-01d license and dependency inventory

Start **WP-01d** from `rebuild/auto-bioinfo-core` at or after merge commit `7bac3b26a850ffe5da842c8a61c530d102d74fb2`.

This is the next split WP-01 work order from the sequence approved in turn 0046 and proposed in turn 0045:

- T-01-11 license / dependency inventory / SBOM entry
- No CI artifact publication in this slice

Suggested branch name: `rebuild/wp-01d-license-dependency-inventory`.

## Scope

Implement a minimal, auditable license and dependency inventory slice for the existing Python project.

Required behavior:

- Audit the existing package/development dependencies already declared by WP-01a/WP-01c.
- Add or update project documentation/configuration needed to make dependency groups, license posture, and SBOM entry point clear.
- If the repository already has an appropriate license file or metadata, preserve it and document it; do not replace it casually.
- If a lightweight SBOM generation entry point is practical using existing tooling, add it as a documented command or script entry point.
- If adding actual SBOM generation would require a new dependency or CI artifact policy, document the recommended path instead and stop at the entry-point/documentation level for this slice.
- Keep this work offline and repository-local except for normal package metadata inspection already inherent to the project.

Explicit non-scope:

- No `.github/workflows` changes in this slice.
- No Docker / Compose / Dockerfile.
- No database migration framework.
- No container image work.
- No PR template.
- No WP-02.
- No Nextflow, GEO, LLM, DESeq2, real human data, external service data transfer, business/scientific analysis logic, or credential/ruleset/secret changes.
- Do not add production dependencies unless the need is explicitly justified and kept within this WO; prefer documentation or dev-only tooling if tooling is needed.

Validation to report:

- Changed file list and rationale.
- Dependency/license inventory evidence, including what files were used as the source of truth.
- Any SBOM entry-point command or documented deferral, with the reason.
- `git diff --check`.
- Relevant local quality/test command(s), at minimum the existing test command if no executable code changes occur; if full test execution is skipped because the slice is documentation-only, say so explicitly and give the lighter validation actually run.
- Confirmation that no `.github/workflows`, Docker, migrations, PR template, WP-02, product/scientific logic, ruleset, secret, token, real-data, or external-service changes were made.

Deliver PR against `rebuild/auto-bioinfo-core` and a REPORT turn with branch, PR number, full head SHA, changed files, requirement mapping, validation results, and hard-stop confirmation.

Stop after REPORT and wait for Codex independent review.