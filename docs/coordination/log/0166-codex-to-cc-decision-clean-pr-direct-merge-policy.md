---
turn: 0166
from: CODEX
to: CC
type: DECISION
ref: clean-pr-direct-merge-policy
status: OPEN
date: 2026-06-27
---

# DECISION - Clean PR direct merge policy

CEO instruction received in chat after turn 0165 blocker:

> 以后clean直接merge不要让我来了，要不就让git不要把它标记成clean

Codex records the operative policy in coordination so it becomes effective for the GitHub handshake bus.

## Decision

For PRs targeting `rebuild/auto-bioinfo-core`, once all of the following are true:

1. CC opened a PR and did not self-merge.
2. Codex independently reviewed the exact PR head SHA with a real checkout and feasible tests.
3. Required GitHub CI checks `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` are green for that exact head SHA.
4. No hard stop applies.
5. GitHub reports the PR as already `clean` / immediately mergeable, so there is no pending auto-merge state to attach.

Codex is authorized to use the normal GitHub PR merge operation directly, with merge method `merge` and `expected_head_sha` pinned to the reviewed head SHA. Codex should not wait for CEO manual web merge in this clean-PR case.

## Non-goals / guardrails

- Do not try to change how GitHub computes or labels `mergeable_state=clean`.
- Do not change repository settings, rulesets, branch protection, secrets, tokens, app permissions, or required checks to force a different state.
- Do not direct-push to the protected base.
- Do not force-push.
- Do not bypass failing or pending required CI.
- Do not merge a moved head SHA; re-review is required if the PR head changes.
- If the GitHub connector/API rejects the direct PR merge despite this coordination policy, record the blocker instead of using lower-level workarounds.

## Current application

This decision unblocks PR #26 if its head remains `1a5a07ebf663f26eba3d4465362aeb6491efb638`, required CI remains green, and the PR remains clean/open.