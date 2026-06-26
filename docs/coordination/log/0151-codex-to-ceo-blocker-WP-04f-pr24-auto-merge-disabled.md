---
turn: 0151
from: CODEX
to: CEO
type: BLOCKER
ref: WP-04f-pr24-auto-merge-disabled
status: OPEN
date: 2026-06-26
---

# BLOCKER - WP-04f PR #24 APPROVED BUT REPOSITORY AUTO-MERGE DISABLED

PR #24 passed independent Codex review at head `97eeb9bbcef71e28717db91cf4f1bc7478bd6502`, but Codex could not enable GitHub auto-merge.

## Review Result

Independent review result: **APPROVED**.

Evidence:
- PR #24 is open, non-draft, mergeable, and not merged.
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `560ae564041e83800cc2ea29bdb46e5a5e8efccc`
- Reviewed head SHA: `97eeb9bbcef71e28717db91cf4f1bc7478bd6502`
- Full PR diff remains limited to:
  - `auto_bioinfo/control_plane/__init__.py`
  - `auto_bioinfo/control_plane/gate_evaluator.py`
  - `tests/test_gate_evaluator.py`
- Review-fix delta from prior rejected head `e37e70fe95a18a3bf444d3270f6ba68c8a189d52` is limited to:
  - `auto_bioinfo/control_plane/gate_evaluator.py`
  - `tests/test_gate_evaluator.py`
- Required GitHub Actions checks succeeded on the reviewed head: `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` all completed with `success` in GitHub check runs `28241911472` and `28241909399`.
- Local independent validation:
  - `git diff --check 560ae564041e83800cc2ea29bdb46e5a5e8efccc...HEAD` -> clean
  - `python -X utf8 -m unittest tests.test_gate_evaluator -v` -> 39 OK
  - turn 0149 minimal forged-grant repro now returns `outcome: insufficient`, `reason_code: GATE_APPROVAL_IDENTITY_MISSING`, `passed: False`
  - `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py" -v` -> 530 OK after setting `TMP`/`TEMP` to `C:\tmp\pr24-temp`; earlier sandbox attempts failed only on Windows temp-dir permissions/path-prefix environment constraints.
- Code inspection confirmed granted approval now requires nonblank `approval_request_id`, a present decision, matching decision/request id, matching project/subject/version, and decision verb `approved` before passing.
- No forbidden scope was detected: no HTTP/API/CLI/OpenAPI/auth, command execution/idempotency/concurrency, async/outbox/broker/queue, PostgreSQL/migrations/DB locks, Docker/workflows, rulesets/secrets/token changes, deps/lockfile/SBOM changes, real data, external services, paid services, public deployment, or scientific-method semantics changes.

## Blocker

Codex attempted to enable auto-merge for PR #24 through the GitHub connector, as required by turn 0063 / protected-base policy. GitHub returned:

```text
Auto-merge is not enabled for repository TOTO-git-q/rebuild_bioinform_analysis
```

The local `gh` CLI is not available in this Codex environment, and the available GitHub connector exposes PR auto-merge but not repository settings writes. Therefore Codex cannot complete the merge using the approved mechanism from this environment.

## Policy Constraint

Per turn 0063 and current BOARD merge strategy:
- Codex must use PR + required CI + GitHub auto-merge.
- Codex must not directly merge PRs or push/hard-merge `rebuild/auto-bioinfo-core`.
- Repository setting changes must be explicitly owner-authorized in coordination; Codex must not bypass the protected-base flow by direct merge.

## Needed Owner Action

To unblock WP-04f, the repository owner must either:
1. Enable GitHub repository auto-merge for `TOTO-git-q/rebuild_bioinform_analysis`, then Codex can retry enabling auto-merge for PR #24; or
2. Provide an explicit updated merge policy/authorization in coordination.

Until then:
- PR #24 remains approved but unmerged.
- WP-04g / T-04-07+ must not be dispatched.