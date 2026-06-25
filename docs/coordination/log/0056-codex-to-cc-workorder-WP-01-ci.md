---
turn: 0056
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-01-ci
status: OPEN
date: 2026-06-25
---

# WORK_ORDER - WP-01 CI workflow gate

Start **WP-01 CI workflow only** from `rebuild/auto-bioinfo-core` at or after merge commit `92e865e04bb9ae4e838b9ad00fe9b755f6e3a06b`.

This work order is the dedicated CI slice promised by the CEO ruling in turn 0046.
This WO explicitly authorizes use of `.github/workflows` for this CI workflow.

Suggested branch name: `rebuild/wp-01-ci-quality-gate`.

## Scope

Implement the CI portion of **T-01-08** using the quality commands established by WP-01c.

Required behavior:

- Add a minimal GitHub Actions workflow under `.github/workflows/`.
- The workflow should install the project and dev/test tooling using the repo packaging from WP-01a/WP-01c.
- It should run the same repo-native gates used locally, preferably `make lint`, `make format-check`, `make typecheck`, and `make test`.
- If coverage is practical in CI, include `make coverage`; if not, document why and keep local coverage intact.
- Keep local and CI command names aligned.
- Do not add Docker, Compose, service containers, database migration checks, object storage, broker, or external services in this CI slice.
- Do not modify repository rulesets, branch protection, secrets, or token permissions.

Explicit non-scope:

- No Docker / Compose / Dockerfile.
- No database migration framework.
- No SBOM, PR template, container image work, Nextflow, GEO, LLM, DESeq2, business/scientific analysis logic, or WP-02.
- No real human data or external service data transfer.

Validation to report:

- Workflow syntax/path check.
- Local `make lint`, `make format-check`, `make typecheck`, `make test`, and coverage if included.
- A scope check confirming only allowed CI/workflow and minimal supporting docs/config changed.
- If GitHub Actions run is available on the PR, report run URL/status/check names. If not available, report the exact reason.
- `git diff --check`.

Deliver PR against `rebuild/auto-bioinfo-core` and a REPORT turn with branch, PR number, full head SHA, changed files, requirement mapping, validation results, and hard-stop confirmation.

Stop after REPORT and wait for Codex independent review.
