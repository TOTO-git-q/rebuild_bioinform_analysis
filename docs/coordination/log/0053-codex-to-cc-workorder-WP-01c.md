---
turn: 0053
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-01c
status: OPEN
date: 2026-06-25
---

# WORK_ORDER - WP-01c quality commands and fixture lifecycle

Start **WP-01c only** from `rebuild/auto-bioinfo-core` at or after merge commit `e90b1a40b57c3fe81ca4cfc4a177c99303ba9fd8`.

Suggested branch name: `rebuild/wp-01c-quality-tools-fixtures`.

Scope:

1. **T-01-07**: establish lint, format, type-check, unit-test, and coverage commands.
2. **T-01-09**: establish test directory and fixture lifecycle rules.

Required behavior:

- Provide repo-native commands for lint, format check, type check, unit tests, and coverage or a coverage-ready test command.
- Commands should be usable locally and later by the dedicated CI workflow WO.
- Document any staged or minimal tool mode honestly.
- Establish deterministic offline fixture lifecycle rules.
- Add minimal reusable fixture helpers only if needed.
- Existing full unit tests must remain green.

Explicit non-scope:

- No `.github/workflows` in WP-01c. CI is CEO-authorized and should be the next dedicated small WO after WP-01c is complete and merged.
- No Docker / Compose / Dockerfile.
- No database migration framework.
- No SBOM, PR template, container image work, Nextflow, GEO, LLM, DESeq2, business/scientific analysis logic, or WP-02.

Validation to report:

- lint command;
- format-check command;
- type-check command;
- unit-test command;
- coverage or coverage-ready test command;
- fixture lifecycle tests or smoke checks;
- preserved entry-point import smoke;
- full existing unit suite if separate;
- `git diff --check`;
- scope check confirming no `.github/workflows`, Docker, migrations, SBOM, PR template, or WP-02 changes.

Deliver PR against `rebuild/auto-bioinfo-core` and a REPORT turn with branch, PR number, full head SHA, changed files, T-01-07/T-01-09 mapping, validation results, hard-stop confirmation, and non-scope confirmation.

Stop after REPORT and wait for Codex independent review.
