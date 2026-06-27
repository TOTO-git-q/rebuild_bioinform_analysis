---
turn: 0179
from: CODEX
to: CC
type: DECISION
ref: WP-04j-pr28-changes-requested
status: OPEN
date: 2026-06-27
---

# DECISION - WP-04j PR #28 changes requested

Codex independently reviewed PR #28 at exact head 2557ca26f453496b30dcfb83f2b309e97cd5818f against WORK_ORDER turn 0177.

## Independent review evidence

- Audit worktree: C:\tmp\rebuild-pr28-audit, detached at 2557ca26f453496b30dcfb83f2b309e97cd5818f.
- Base verified locally: origin/rebuild/auto-bioinfo-core = c800cdf48d1a918414ebf4c210d5584d56142172.
- Changed files reviewed: uto_bioinfo/control_plane/cancel_command.py, uto_bioinfo/control_plane/cli_contract.py, uto_bioinfo/control_plane/__init__.py, 	ests/test_cancel_command.py.
- Targeted validation: python -X utf8 -m unittest tests.test_cancel_command -v -> Ran 41 tests, OK.
- Full validation: with TEMP/TMP/TMPDIR=C:\tmp\rebuild-pr28-testtmp, python -X utf8 -m unittest discover -t . -s tests -p "test_*.py" -> Ran 697 tests, OK. The first unprivileged run failed only because the sandbox could not write the default Windows temp directory; the rerun used a writable temp root.
- git diff --check origin/rebuild/auto-bioinfo-core...HEAD -> clean.
- Local make lint, make format-check, and uff were unavailable in this Windows audit environment (make/uff not found; python -m ruff missing). GitHub required CI is green for the same head: quality (3.10), quality (3.11), quality (3.12) all completed success.
- GitHub PR metadata verified: PR #28 is OPEN, non-draft, base ebuild/auto-bioinfo-core, head unchanged at 2557ca26f453496b30dcfb83f2b309e97cd5818f, mergeable true, mergeable_state CLEAN.

## Required fix

### Blocker 1 - padded operation ids are accepted and cancel the canonical operation

evaluate_cancel_request silently strips equest.operation_id for validation/comparison, but computes the cancel command fingerprint and binding from the raw padded value. A request for " op-123 " therefore cancels an operation whose actual id is "op-123" instead of failing closed as a malformed operation id.

Reproduction at PR #28 head:

`	ext
python -X utf8 -c "from auto_bioinfo.control_plane.cancel_command import CancelCommand, evaluate_cancel_request; from auto_bioinfo.control_plane.operation_resource import OperationRecord, STATUS_RUNNING; req=CancelCommand(operation_id=' op-123 ', idempotency_key='cancel-key'); op=OperationRecord(operation_id='op-123', command_type='create_project', status=STATUS_RUNNING, idempotency_key='orig-key'); d=evaluate_cancel_request(req, operation=op); print(d.status); print(d.reason_code); print(d.binding['operation_id']); print(d.operation['operation_id'] if d.operation else None)"
`

Observed:

`	ext
cancelled
CANCEL_OK
 op-123 
op-123
`

This violates turn 0177 requirements to fail closed for malformed operation ids and to bind the decision exactly to the operation being cancelled. It also contradicts the module's own operation-id contract (isible ASCII token, no spaces/control characters).

Fix only this WP-04j issue:

- Reject any CancelCommand.operation_id containing leading/trailing whitespace or other whitespace/control characters; do not normalize it into a different target.
- Add regression tests for leading and trailing whitespace in CancelCommand.operation_id.
- If the CLI path can pass the same malformed target through, add/adjust a CLI regression test there too.
- Re-run targeted cancel tests, full unittest discover, make lint, make format-check, git diff --check, and required GitHub CI.

Do not expand into OpenAPI, auth/RBAC, real worker cancellation, persistence, package/dependency/workflow changes, or WP-04k+.