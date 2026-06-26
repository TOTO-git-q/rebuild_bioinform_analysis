---
turn: 0152
from: CODEX
to: CEO
type: BLOCKER
ref: WP-04f-pr24-clean-no-auto-merge
status: OPEN
date: 2026-06-26
---

# BLOCKER - WP-04f PR #24 CLEAN PR CANNOT ACCEPT AUTO-MERGE REQUEST

Owner explicitly requested `启用auto merge` in the Codex session after turn 0151.

Codex enabled repository-level GitHub auto-merge for `TOTO-git-q/rebuild_bioinform_analysis` using the existing authenticated GitHub credential. The token was used only in memory and was not written to coordination, logs, or repository files.

## Repository And PR State

GitHub REST verification after the owner request:

- Repository `allow_auto_merge`: `true`
- PR: #24
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `560ae564041e83800cc2ea29bdb46e5a5e8efccc`
- Head SHA: `97eeb9bbcef71e28717db91cf4f1bc7478bd6502`
- PR state: `open`
- Merged: `false`
- Mergeable: `true`
- Mergeable state: `clean`

Independent review evidence from turn 0151 remains unchanged: PR #24 was APPROVED by Codex at head `97eeb9bbcef71e28717db91cf4f1bc7478bd6502`; required CI `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` were green; local independent validation passed.

## Auto-Merge Attempt Result

After repository-level auto-merge was enabled, Codex retried the GitHub auto-merge path for PR #24.

The GitHub connector still returned the stale repository-level error:

```text
Auto-merge is not enabled for repository TOTO-git-q/rebuild_bioinform_analysis
```

A direct GitHub GraphQL `enablePullRequestAutoMerge` mutation with `mergeMethod: MERGE` and `expectedHeadOid: 97eeb9bbcef71e28717db91cf4f1bc7478bd6502` returned:

```text
UNPROCESSABLE: Pull request Pull request is in clean status
```

Interpretation: repository-level auto-merge is now enabled, but PR #24 is already immediately mergeable/clean. GitHub will not attach an auto-merge request to an already-clean PR; it expects an immediate merge action instead.

## Policy Constraint

Per turn 0063 and the current BOARD merge strategy:

- Codex must use PR + required CI + GitHub auto-merge.
- Codex must not directly merge PRs or directly push/hard-merge `rebuild/auto-bioinfo-core`.
- Protected-base direct merge remains forbidden unless coordination explicitly updates the merge authorization.

Therefore Codex did **not** directly merge PR #24, despite the PR being approved, CI-green, and clean.

## Needed Owner / Coordination Action

To unblock WP-04f, coordination must explicitly authorize one of these paths:

1. Permit the equivalent clean-PR merge path for this already-approved, CI-green, clean PR #24, using the reviewed head SHA `97eeb9bbcef71e28717db91cf4f1bc7478bd6502`; or
2. Update the merge policy so that, when GitHub refuses `enablePullRequestAutoMerge` because an approved PR is already `clean`, Codex may perform the normal PR merge with expected-head protection.

Until then:

- PR #24 remains approved but unmerged.
- WP-04g / T-04-07+ must not be dispatched.