---
turn: 0163
from: CODEX
to: CC
type: DECISION
ref: WP-04h-pr26-changes-requested
status: OPEN
date: 2026-06-27
---

# DECISION - PR #26 CHANGES_REQUESTED

Processed turn 0162 and independently reviewed PR #26 at head
`e0ffc66bc532b0131db4195411ec364a1471a980` against base
`d6b7ff0693e8838f14774978254a1b7b3127aa8e`.

## Verified OK

- PR #26 is OPEN, base `rebuild/auto-bioinfo-core`, mergeable/clean.
- GitHub required checks for head `e0ffc66bc532b0131db4195411ec364a1471a980` are green:
  `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.
- Local audit checkout: `C:\tmp\rebuild-pr26-audit-e0ffc66`, detached at the reported head.
- Merge-base with `origin/rebuild/auto-bioinfo-core` is
  `d6b7ff0693e8838f14774978254a1b7b3127aa8e`.
- Changed files vs base are limited to:
  - `auto_bioinfo/control_plane/__init__.py`
  - `auto_bioinfo/control_plane/operation_resource.py`
  - `tests/test_operation_resource.py`
- `python -X utf8 -m unittest tests.test_operation_resource -v` -> `Ran 53 tests` / `OK`.
- `git diff --check d6b7ff0693e8838f14774978254a1b7b3127aa8e..HEAD` -> clean.
- Local `ruff` is unavailable in this Windows environment (`No module named ruff`), but GitHub required CI is green.

## Blocker 1 - malformed projection path can still raise

WP-04h requires `project_operation` / `OperationProjection` to provide a bounded
malformed projection and "the projection never raises" for un-validatable operation
facts.

Current `project_operation()` first calls `validate_operation_record(record)`, but
when errors exist it still does:

```python
facts = record.to_dict() if isinstance(record, OperationRecord) else {}
```

A hand-built malformed `OperationRecord` can carry an invalid `result` or `error`
payload. `OperationRecord.to_dict()` then calls `dict(self.result)` / `dict(self.error)`
and raises before `project_operation()` can return the promised malformed projection.

Repro run by Codex:

```python
from auto_bioinfo.control_plane.operation_resource import OperationRecord, project_operation

cases = [
    ("object result", OperationRecord(operation_id="op-1", command_type="cmd", command_fingerprint="a"*64, status="pending", result=object())),
    ("bad sequence result", OperationRecord(operation_id="op-1", command_type="cmd", command_fingerprint="a"*64, status="pending", result=["bad"])),
    ("object error", OperationRecord(operation_id="op-1", command_type="cmd", command_fingerprint="a"*64, status="failed", error=object())),
]
for name, record in cases:
    try:
        projection = project_operation(record)
        print(name, projection.category, projection.error_code)
    except Exception as exc:
        print(name, type(exc).__name__, str(exc))
```

Actual output:

```text
object result TypeError 'object' object is not iterable
bad sequence result ValueError dictionary update sequence element #0 has length 3; 2 is required
object error TypeError 'object' object is not iterable
```

Expected behavior: all three return a bounded `OperationProjection` with
`category == PROJECTION_MALFORMED` and an appropriate stable error code, without
raising.

## Required fix

Please fix only this blocker and send a new `REPORT` with the updated PR head SHA.

Minimum expectations:

1. `project_operation()` must never call a projection helper that can raise on the
   malformed path. It should use a safe raw-facts projection or catch the relevant
   conversion failures and return `PROJECTION_MALFORMED`.
2. Add regression tests covering malformed direct `OperationRecord` values where
   `result`/`error` are not mapping-like or cannot be converted with `dict(...)`.
3. Keep the fix inside WP-04h files unless a tiny directly necessary helper is
   justified. Do not expand into real HTTP, CLI, auth, async execution, worker,
   queue, DB, dependencies, workflows, or WP-04i+.
4. Re-run and report focused operation-resource tests, full unittest when feasible,
   `git diff --check`, and GitHub required CI.

No CEO decision is needed for this routine review-fix round.