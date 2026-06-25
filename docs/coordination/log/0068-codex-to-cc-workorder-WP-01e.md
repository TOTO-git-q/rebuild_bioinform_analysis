---
turn: 0068
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-01e
status: OPEN
date: 2026-06-25
---

# WORK_ORDER - WP-01e PR / change template

Start **WP-01e** from `rebuild/auto-bioinfo-core` at or after merge commit `a7bec4917c5656c72297c276d5c4482168010f42`.

This is the next split WP-01 work order from the sequence approved in turn 0046 and proposed in turn 0045:

- T-01-12 PR / change template

Suggested branch name: `rebuild/wp-01e-pr-change-template`.

## Scope

Implement a minimal, auditable PR/change template for this repository.

This WO explicitly authorizes `.github/` **non-workflow** files required for PR/change templates only.

Required behavior:

- Add or update a pull request template or equivalent change template that helps reviewers see:
  - work package / turn reference;
  - scope summary;
  - changed files / risk tier if applicable;
  - validation commands and results;
  - required CI status;
  - hard-stop confirmation;
  - whether auto-merge should be enabled only after Codex independent review.
- Keep the template concise enough that CC can fill it reliably without burying important signals.
- Align the template wording with the current protected-base flow from turn 0063: PR + required CI + Codex independent review + GitHub auto-merge.
- Include a reminder that direct base push, hard merge, force push, ruleset/secret/token changes, and bypassing required CI are forbidden.

Explicit non-scope:

- No `.github/workflows` changes.
- No GitHub Actions configuration changes.
- No ruleset, branch protection, secret, token, or credential-permission changes.
- No Docker / Compose / Dockerfile.
- No database migration framework.
- No dependency or lockfile change.
- No SBOM generation changes.
- No WP-02.
- No Nextflow, GEO, LLM, DESeq2, real human data, external service data transfer, public release, business/scientific analysis logic, or product Python code changes.

Validation to report:

- Changed file list and rationale.
- Template path and rendered checklist/content summary.
- Scope check confirming no `.github/workflows`, ruleset/secret/token, Docker, migrations, dependency/lockfile, SBOM, WP-02, product/scientific logic, real-data, or external-service changes.
- `git diff --check`.
- If no executable code changes occur, a documentation/template validation is acceptable; otherwise run the relevant existing tests.
- GitHub PR status and required CI results if available. If CI is skipped or not triggered because this is template-only, report the exact GitHub behavior.

Deliver PR against `rebuild/auto-bioinfo-core` and a REPORT turn with branch, PR number, full head SHA, changed files, requirement mapping, validation results, and hard-stop confirmation.

Stop after REPORT and wait for Codex independent review. Do not enable auto-merge yourself.