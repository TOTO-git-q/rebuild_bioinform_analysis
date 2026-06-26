---
turn: 0115
from: CODEX
to: CEO
type: BLOCKER
ref: WP-03a-pr17-auto-merge-disabled
status: OPEN
date: 2026-06-26
---

# BLOCKER - WP-03a PR #17 APPROVED BUT AUTO-MERGE DISABLED

PR #17 passed independent Codex review at head `43120a421fa21e3bf2a69b012012d596bf6dc03d`, but Codex could not enable GitHub auto-merge.

## Review Result

Independent review result: **APPROVED**.

Evidence:
- PR #17 is open, non-draft, not merged, and mergeable.
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `2cd2eda4ef88313fa28fc83514d873749de42b86`
- Head SHA reviewed: `43120a421fa21e3bf2a69b012012d596bf6dc03d`
- Total PR diff remains limited to:
  - `docs/rebuild/WP-03A-EVENT-STORE-AUDIT.md`
  - `auto_bioinfo/core/store.py`
  - `tests/test_state_machine.py`
- Required GitHub Actions CI succeeded: `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` all passed in run `28211838780`.
- Local independent validation passed: `tests.test_state_machine` 18 tests OK; full unittest discovery 351 tests OK; adversarial probe PASS; `git diff --check` clean.
- Remaining forged no-op blocker from turn 0113 is closed.
- No forbidden scope was detected.

## Blocker

Codex attempted to enable auto-merge for PR #17, as required by turn 0063 / protected-base policy. GitHub returned:

```text
Auto-merge is not enabled for repository TOTO-git-q/rebuild_bioinform_analysis
```

Therefore Codex cannot complete the merge using the approved mechanism.

## Policy Constraint

Per turn 0063 and current BOARD merge strategy:
- Codex must use PR + required CI + GitHub auto-merge.
- Codex must not directly merge PRs or push/hard-merge `rebuild/auto-bioinfo-core`.
- Enabling or changing repository settings / protection / permissions is a CEO-level action and not something Codex should do autonomously.

## Needed Owner Action

To unblock WP-03a, the repository owner must either:
1. Enable GitHub repository auto-merge, then Codex can retry enabling auto-merge for PR #17; or
2. Provide an explicit updated merge policy/authorization in coordination.

Until then:
- PR #17 remains approved but unmerged.
- WP-03b must not be dispatched.