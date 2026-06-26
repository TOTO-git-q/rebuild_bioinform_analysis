---
turn: 0158
from: CODEX
to: CEO
type: BLOCKER
ref: WP-04g-pr25-clean-no-auto-merge
status: OPEN
date: 2026-06-27
---

# BLOCKER - WP-04g PR #25 approved, but GitHub refused auto-merge on clean PR

Processed turn 0157 and independently re-reviewed PR #25 at head
`d2e93473fcfbf4ee97022b2043ad0e6fde85731b` against protected base
`rebuild/auto-bioinfo-core` / base SHA `b7c271a6d7644247bfaf2773d5fb4957a21184fd`.

## Review result

APPROVED for WP-04g scope. The turn 0156 blocker is closed.

Evidence checked by Codex:

- Fresh audit checkout: `C:\tmp\rebuild-pr25-audit-d2e934`, detached at
  `d2e93473fcfbf4ee97022b2043ad0e6fde85731b`.
- Merge-base with `origin/rebuild/auto-bioinfo-core` is
  `b7c271a6d7644247bfaf2773d5fb4957a21184fd`.
- Files changed vs base remain limited to:
  - `auto_bioinfo/control_plane/__init__.py`
  - `auto_bioinfo/control_plane/command_api.py`
  - `tests/test_command_api.py`
- Delta vs prior reviewed head `b2f5298ac34c4c581d81b1e86f39a98f12ad1d96` is only
  `command_api.py` and `tests/test_command_api.py` (`68 insertions`, `7 deletions`).
- The original turn 0156 repro now returns bounded invalid results for all three
  cases: `invalid / COMMAND_MALFORMED_COMMAND / accepted=False / fingerprint=''`;
  no exception is raised.
- `python -X utf8 -m unittest tests.test_command_api -v` -> `Ran 35 tests` / `OK`.
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` with `TEMP/TMP`
  set to `C:\tmp\codex-pr25-temp` -> `Ran 565 tests` / `OK`.
  Earlier full-test attempts failed only because the sandbox blocked writes to the
  default `%TEMP%`, then because a temporary root path contained the checkout path
  substring and tripped the repo-isolation assertion.
- `git diff --check b7c271a6d7644247bfaf2773d5fb4957a21184fd..HEAD` -> clean.
- Local `make` and local `ruff` are unavailable in this Windows environment, but
  GitHub required checks for PR #25 head are all green: `quality (3.10)`,
  `quality (3.11)`, `quality (3.12)`.

No hard-stop scope was touched by this PR review: no real data, external service,
new dependency/lockfile/SBOM, workflow/ruleset/secret change, deployment, or
scientific-method change.

## Merge blocker

Codex attempted to enable GitHub auto-merge for PR #25 using the GitHub GraphQL
`enablePullRequestAutoMerge` mutation with `mergeMethod: MERGE` and
`expectedHeadOid: d2e93473fcfbf4ee97022b2043ad0e6fde85731b`.

GitHub rejected the request:

```text
UNPROCESSABLE: Pull request Pull request is in clean status
```

This is the same failure mode observed on PR #24 after repository-level auto-merge
was enabled: when the PR is already mergeable/clean, GitHub refuses to attach an
auto-merge request.

Per the active merge strategy, Codex must not directly merge, directly push base,
force push, or bypass branch protection. Therefore PR #25 is approved but blocked
on the merge mechanism.

## Needed CEO action

Please either:

1. Manually merge PR #25 in the GitHub UI, then Codex can record the merge SHA and
   dispatch WP-04h; or
2. Write an explicit coordination policy amendment for clean PR handling.

CC has no implementation action pending on WP-04g, and Codex will not dispatch
WP-04h/T-04-08+ until PR #25 is merged or the merge-policy blocker is resolved.