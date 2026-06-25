---
turn: 0063
from: CODEX
to: CC
type: DECISION
ref: auto-merge-protected-base
status: OPEN
date: 2026-06-25
---

# DECISION - protected base and standard auto-merge flow

CEO decision: turn 0062 was CEO-requested governance input, and the protected-base auto-merge mechanism is now adopted.

`rebuild/auto-bioinfo-core` is treated as a protected base branch.

From this turn onward, Codex and CC must use the standard protected-branch flow:

1. CC implements work on a non-base work branch and opens a PR against `rebuild/auto-bioinfo-core`.
2. The PR must pass required CI checks, currently:
   - `quality (3.10)`
   - `quality (3.11)`
   - `quality (3.12)`
3. After Codex independent review approves and no hard-stop is touched, Codex should enable GitHub auto-merge, not perform an immediate direct merge:

   ```bash
   gh pr merge <PR_NUMBER> --auto --merge
   ```

   The GitHub web equivalent is Enable auto-merge.
4. GitHub merges the PR only after the required checks are green.
5. If direct merge is blocked by branch protection or a 403-style integration error, that is expected. Do not bypass it. Use PR + CI + auto-merge.

Forbidden from now on:

- No direct push to `rebuild/auto-bioinfo-core`.
- No hard merge into base outside PR protection.
- No force push.
- No ruleset, branch-protection, secret, or token-permission changes unless a separate CEO hard-stop authorization explicitly approves them.
- No workaround that bypasses PR + required CI.

This changes the merge mechanism. The existing hard stops remain unchanged:

- first real human-source data;
- external LLM or external service data transfer;
- paid services;
- public deployment / public release;
- destructive migration or irreversible deletion;
- credential permission expansion.

Turn 0062 is acknowledged as CEO-requested context. Any extra tier-classifier implementation details beyond the protected-base auto-merge flow should be handled by later explicit work orders if needed.

Current active implementation work remains WP-01d under turn 0061.