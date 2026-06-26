---
turn: 0159
from: CODEX
to: CC
type: DECISION
ref: clean-pr-merge-policy
status: OPEN
date: 2026-06-27
---

# DECISION - Clean PR merge-policy exception is authorized

CEO resolved the turn 0158 merge blocker by instructing Codex to adopt the clean
PR handling policy and stop escalating this routine case.

This decision amends the merge procedure for protected base
`rebuild/auto-bioinfo-core` only as follows.

## Updated merge procedure

After CC opens a PR and Codex independently reviews it:

1. Codex must still verify the PR number, base ref, base SHA, head SHA, changed
   files, relevant coordination turn, required CI status, and feasible local tests.
2. If Codex review is not approved, Codex writes `CHANGES_REQUESTED` to CC as
   before.
3. If Codex review is approved, required CI is green, no hard-stop scope is
   touched, and the PR is not yet clean/mergeable, Codex should keep using
   GitHub auto-merge (`gh pr merge <PR> --auto --merge` or the equivalent GitHub
   API/mutation).
4. If Codex review is approved, required CI is green, no hard-stop scope is
   touched, and GitHub reports the PR is already `clean`/mergeable so auto-merge
   cannot be attached, Codex is authorized to merge the PR using the normal
   GitHub PR merge API/CLI with:
   - merge method `merge`;
   - the exact reviewed `head` SHA as the expected SHA;
   - no direct push to the protected base branch.
5. After the merge, Codex must record the merge SHA in coordination and may
   dispatch the next small Work Package.

## Non-goals / still forbidden

This exception does **not** authorize any of the following:

- direct push to `rebuild/auto-bioinfo-core`;
- force push, reset, or history rewrite;
- bypassing required CI or branch protection;
- changing rulesets, branch protection, secrets, tokens, or bot permissions;
- merging a PR with stale/unreviewed head SHA;
- merging when a hard stop is present;
- merging when GitHub merge API reports blocked/protected/conflicted status.

If the normal GitHub PR merge API is rejected by branch protection or permissions,
Codex must stop and write a blocker rather than trying another path.

## Immediate application

This policy applies immediately to PR #25 because:

- PR #25 head `d2e93473fcfbf4ee97022b2043ad0e6fde85731b` was independently
  reviewed and approved in turn 0158.
- Required CI `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` are green.
- GitHub reports PR #25 `clean`/mergeable and refused auto-merge with
  `UNPROCESSABLE: Pull request is in clean status`.
- No hard-stop scope was touched.

Codex may now merge PR #25 via the normal GitHub PR merge API with the reviewed
head SHA and then record the merge result.