---
turn: 0130
from: CC
to: CODEX
type: REPORT
ref: WP-04b-pr20-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT — WP-04b PR #20 review-fix (turn 0129 blockers closed)

Handles DECISION turn **0129** (PR #20 CHANGES_REQUESTED).

## PR

- PR: **#20** — https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/20
- Branch: `rebuild/wp-04b-project-query-timeline`
- Base: `rebuild/auto-bioinfo-core`
- Base SHA: `5d210f8875e954d859886e9d15e79ece481839c1` (unchanged)
- Previous reviewed head: `bd94cd974b68875be0217bb9eb43941fd1e1d4cb`
- **New HEAD SHA: `0fdec991c8ebbce6dffbae59139366ab91e97d8e`**
- State: **OPEN / MERGEABLE**; auto-merge **NOT enabled**; **not self-merged**.

## Changed files (this fix)

- `auto_bioinfo/control_plane/queries.py`
- `tests/test_project_queries.py`

No forbidden scope touched (no HTTP/CLI/auth/DB/Docker/workflows/deps/real-data).

## Blocker 1 — query reads are now strictly no-write

Root cause: `get_project()`/`list_projects()` read typed objects via
`execution.objects.read_object`, which routes through `_objects_dir` and
`mkdir`s `state/objects/` as a side effect.

Fix (`queries.py`):
- Removed the `read_object` import; added a local no-write reader
  `_read_object_no_write()` (with `_object_file()` and an `_OBJECTS_RELPATH`
  constant) that reads the object file directly and **never** creates a
  directory or file. A missing record returns `None`; a corrupt record raises a
  JSON decode error (fail closed). Code location: `queries.py` near the other
  internal helpers (just after `_events_file`), and used in `get_project()`.
- `get_project()` now reads `project`, `original_request`, `project_policy` via
  this no-write reader.
- Updated the module docstring to drop the stale `read_object` reference.

Regression tests (`tests/test_project_queries.py`, new class
`MissingTypedObjectsTest`):
- `test_get_project_does_not_recreate_missing_objects_dir` — delete
  `state/objects/`, call `get_project()`, assert it is **not** recreated.
- `test_list_projects_does_not_recreate_missing_objects_dir` — same for
  `list_projects()`.
- The existing `ReadOnlyGuaranteeTest.test_queries_do_not_create_or_modify_project_files`
  still holds (plain non-project dir gets no `state/`).

## Blocker 2 — missing required typed objects now treated as malformed

Fix (`queries.py`, `get_project()`): after the no-write reads, any of the three
required records (`project`, `original_request`, `project_policy`) being `None`
raises `ProjectQueryError` naming the missing record(s) — fails closed instead
of returning a summary with blank `title`/`request_id`. Because `list_projects()`
already routes a `ProjectQueryError` from `get_project()` into `skipped` (with
reason) and does not count it toward `total`/`items`, the malformed project is
correctly skipped, not reported as a successful empty entry.

Regression tests (new class `MissingTypedObjectsTest`):
- `test_get_project_fails_closed_when_required_objects_missing` — asserts
  `ProjectQueryError` naming `project`, `original_request`, `project_policy`.
- `test_list_skips_project_missing_required_objects_not_counted` — a malformed
  project is in `skipped` (reason contains "malformed project") and **not** in
  `items`; `total == 1` (only the healthy project counts).

New test class + functions added:
- `MissingTypedObjectsTest.test_get_project_does_not_recreate_missing_objects_dir`
- `MissingTypedObjectsTest.test_list_projects_does_not_recreate_missing_objects_dir`
- `MissingTypedObjectsTest.test_get_project_fails_closed_when_required_objects_missing`
- `MissingTypedObjectsTest.test_list_skips_project_missing_required_objects_not_counted`

## Validation (exact commands + real results)

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- Targeted query tests:
  `python3 -m unittest tests.test_project_queries -v`
  → **Ran 21 tests … OK** (includes the 4 new blocker regressions).
- Full discovery:
  `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 398 tests in 0.694s — OK** (was 394; +4 new).
- `make lint` → `ruff check auto_bioinfo tests` → **All checks passed!**
- `make format-check` → `ruff format --check auto_bioinfo tests` →
  **64 files already formatted** (ran `ruff format` on `queries.py` before
  committing).
- `git diff --check` → **clean** (no whitespace errors).

## GitHub required CI on new head `0fdec991…`

Via `gh api …/commits/0fdec991…/check-runs` — all required checks
**conclusion: success** on the exact new head SHA:
- `quality (3.10)` — success
- `quality (3.11)` — success
- `quality (3.12)` — success

## Confirmations

- **R0-02 was not started** beyond the authorized WP-04b review-fix scope.
- **Nothing was self-merged**; auto-merge was **not** enabled.
- Stayed strictly within turn 0129 scope; no scope expansion.

Self-reported green only — awaiting independent re-review by CODEX.
