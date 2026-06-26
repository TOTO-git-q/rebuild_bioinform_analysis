---
turn: 0168
from: CEO
to: ALL
type: CEO_AMENDMENT
ref: green-lane-auto-merge
status: OPEN
date: 2026-06-27
---

# CEO_AMENDMENT - Green-lane automatic merge channel

This amendment becomes effective once written to the `coordination` branch.

## 1. Amend G1 / §2.6 / §5: green-lane automatic merge channel

When a PR simultaneously satisfies all conditions below, it is equivalent to `MERGE_AUTHORIZED`; Codex does not need to request individual CEO authorization:

(a) target branch is `rebuild/auto-bioinfo-core`, not `main`;

(b) the PR was opened by CC, and CC has not self-merged it;

(c) Codex has independently reviewed the PR's exact head SHA and approved it, with real checkout and test evidence;

(d) required CI (`quality (3.10)`, `quality (3.11)`, `quality (3.12)`) is green at that exact SHA;

(e) GitHub reports the PR as clean / mergeable;

(f) the head SHA has not changed after Codex review;

(g) the PR does not touch any mandatory hard-stop item under §4.

## 2. Execution mechanism

Because the current Codex connector cannot directly merge already-clean PRs and cannot attach auto-merge to them, CEO authorizes local administrator automation using TOTO-git-q credentials on the CC side to mechanically press the merge button.

Qualification remains decided by Codex only: the machine may execute only after Codex has issued an APPROVED/green-lane decision, required CI is green, and the head SHA is unchanged. The executor must record the resulting merge commit SHA back to coordination.

Approval and execution remain separated. CC does not decide to merge its own code; CC-side automation only mechanically executes a merge that Codex has already approved under this amendment.

## 3. Red-lane unchanged

Merges to `main`, claim ceiling changes, privacy/external sending, irreversible deletion, credential/permission expansion, and stage advancement remain red-lane items. They still require explicit CEO authorization and continue to use BLOCKER flow.

## 4. Immediate case authorization

PR #26 at head SHA `1a5a07ebf663f26eba3d4465362aeb6491efb638` is authorized for immediate green-lane merge under this amendment, because Codex already independently approved that exact head in turn 0165, required CI was green, GitHub reported clean, and no hard stop was found.