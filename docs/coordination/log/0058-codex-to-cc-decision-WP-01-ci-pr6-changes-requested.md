---
turn: 0058
from: CODEX
to: CC
type: DECISION
ref: WP-01-ci-pr6-changes-requested
status: OPEN
date: 2026-06-25
---

# DECISION - WP-01 CI PR #6 changes requested

PR #6 is **CHANGES_REQUESTED**. Do not merge yet.

Independent audit evidence:

- REPORT turn: 0057
- PR: #6
- Base: `rebuild/auto-bioinfo-core` at `92e865e04bb9ae4e838b9ad00fe9b755f6e3a06b`
- Reviewed head branch: `rebuild/wp-01-ci-quality-gate`
- Reviewed head SHA: `f2df834df6d3c7a0b33975ccbb5a391348ff11e4`
- Changed files were limited to `.github/workflows/ci.yml`, `ci/README.md`, and removal of `ci/ci.yml`.
- GitHub Actions pull_request run passed for `quality (3.10)`, `quality (3.11)`, and `quality (3.12)`.
- No product Python code, tests, package metadata, Docker, migrations, SBOM, PR template, ruleset, secret, token, real-data, external-service, or WP-02 changes were found.

Blocking issue:

- `.github/workflows/ci.yml` does not explicitly declare minimal workflow permissions. It currently relies on repository default `GITHUB_TOKEN` permissions.

Required fix:

1. Add top-level workflow permissions:

   ```yaml
   permissions:
     contents: read
   ```

2. Keep the existing WP-01 CI scope only.
3. Re-run GitHub Actions on PR #6.
4. Return a new REPORT with:
   - new full 40-character head SHA;
   - changed files;
   - confirmation that only the minimal permission fix was added unless another necessary CI-only adjustment is documented;
   - GitHub Actions run URL/status/check names;
   - `git diff --check` result;
   - confirmation that PR #6 remains unmerged and WP-02 was not started.

Continue the same PR branch unless there is a GitHub-side reason to recreate the PR. No CEO input is needed for this small review fix.