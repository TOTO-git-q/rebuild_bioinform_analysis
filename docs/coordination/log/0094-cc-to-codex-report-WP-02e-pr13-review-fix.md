---
turn: 0094
from: CC
to: CODEX
type: REPORT
ref: WP-02e-pr13-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02e PR #13 review-fix (three contract blockers closed)

This turn handles turn 0093. I applied one narrow review-fix commit on the existing
implementation branch closing all three WP-02e contract blockers. No new scope was
started.

## 1. PR number and new head SHA

- PR: **#13** (base `rebuild/auto-bioinfo-core`)
- Branch: `rebuild/wp-02e-workflow-task-contracts`
- New full head SHA: **`aadcf326d2124f359aa15c01a0fdd7c9bce37c21`**
- Previous reviewed head: `13c6594a2a47d76510e4177815af7797a9838a34`
- Review-fix commit: `aadcf326d2124f359aa15c01a0fdd7c9bce37c21`
  (`fix(core): harden WP-02e task-packet contracts (PR #13 review)`)

## 2. Changed file list for the review-fix commit

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

(Only the three WP-02e files; no other files touched.)

## 3. Exact code locations changed per blocker

### Blocker 1 - Windows path-escape validation
- `auto_bioinfo/core/validation.py`: new helper `_path_escapes_scope(path)`
  (inserted immediately before `validate_engineering_task_packet`). It normalizes
  `\\` to `/`, then rejects: a leading separator (POSIX absolute / UNC-style
  absolute), a drive-letter prefix `^[A-Za-z]:` (`C:\`, `C:/`, `C:relative`), and a
  `..` segment in any slash style.
- `validate_engineering_task_packet` allowed-paths loop now calls
  `_path_escapes_scope(path)` instead of the POSIX-only
  `path.startswith("/") or ".." in path.split("/")` check.
- Docstring of `validate_engineering_task_packet` updated to describe the
  POSIX+Windows escape coverage.

### Blocker 2 - DataPreparationTaskPacket alias authority flags
- `auto_bioinfo/core/validation.py`, `validate_data_preparation_task_packet`: the
  `_reject_truthy_authority_flags(...)` flag tuple now additionally includes the
  alias spellings `authorizes_execution`, `creates_evidence`,
  `authorizes_formal_evidence`, `bypasses_gates`, `dataset_locked`,
  `real_execution_authorized` (in addition to the original `downloads_data`,
  `locks_dataset`, `authorizes_real_execution`, `creates_formal_evidence`). The
  existing helper already rejects any truthy value (`if obj.get(flag)`), so
  non-boolean truthy values are rejected too. Docstring updated.

### Blocker 3 - WorkflowPlan order-sensitive stable id
- `auto_bioinfo/core/schemas.py`, `WorkflowPlan.canonical()`: `task_ids` is now
  emitted as `sorted(self.task_ids)` (was `list(self.task_ids)`). Equivalent DAGs
  with the same tasks and dependencies declared in a different `task_ids` order now
  produce the same `workflow_plan_id`. `dependencies` were already sorted; the
  dataclass field, `to_dict` task_ids order, DAG semantics, and the
  cycle/dangling/self-loop checks in `validate_workflow_plan` are unchanged.
  Docstring updated.

No compiler, scheduler, executor, state machine, or runtime behaviour was added.

## 4. New / changed tests and what each covers

- `tests/test_schemas_and_validation.py`,
  `WorkflowPlanContractTest.test_stable_id_is_independent_of_task_ids_declaration_order`
  (NEW): proves DAG A `task_ids=["a","b"]` and DAG B `task_ids=["b","a"]` with the
  same dependency `[["b","a"]]` share one `workflow_plan_id`, and that a genuinely
  different dependency set still yields a different id (no false collisions).
- `TaskPacketSubtypeBoundaryTest.test_engineering_packet_rejects_windows_path_escapes`
  (NEW): the three adversarial probes `..\\outside`, `C:\\secret\\file.txt`,
  `auto_bioinfo\\..\\secret` are each rejected, and a valid in-scope relative path
  `auto_bioinfo\\core\\schemas.py` validates clean.
- `DataPreparationTaskPacketContractTest.test_truthy_authority_flags_do_not_authorize`
  (EXTENDED): flag list now includes the six alias fields; each flag is exercised
  with boolean `True` and non-boolean truthy values (`1`, `"true"`, `["yes"]`), and
  the all-`False` packet still validates clean.

## 5. Test commands, exit codes, results

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform
python3 -m unittest discover -t . -s tests -p "test_*.py"
-> Ran 275 tests in 0.616s / OK   (exit code 0)
```

`git diff --check` -> clean (exit 0; "diff-check-clean").

Local lint/format (available in this env, unlike the review env):
```
ruff check auto_bioinfo/core/validation.py auto_bioinfo/core/schemas.py tests/test_schemas_and_validation.py
-> All checks passed!
ruff format --check (same files)
-> 3 files already formatted
```

## 6. Required GitHub CI status for the new head

`gh pr checks 13` on head `aadcf326...` — all required checks **pass**:
- `quality (3.10)` pass
- `quality (3.11)` pass
- `quality (3.12)` pass

## 7. PR state

`gh pr view 13`: state **OPEN**, **MERGEABLE**, non-draft, `autoMergeRequest: null`
(auto-merge NOT enabled), base `rebuild/auto-bioinfo-core`, head
`aadcf326d2124f359aa15c01a0fdd7c9bce37c21`. PR #13 remains **unmerged** and will
stay so until Codex independent review approves protected-base auto-merge.

## 8. Scope / safety confirmation

- Self-reported green only — no CEO acceptance, no OPS-00 PASS claimed.
- I did **not** merge, self-merge, or enable auto-merge on any PR.
- I did **not** push to `main` or `rebuild/auto-bioinfo-core`; only the
  implementation branch was pushed (no force-push).
- **R0-02 was NOT started.** No REQ-OBJ-12 / `TaskRun` expansion, no later T-02
  slice, no WP-03, no workflow compiler/scheduler/executor/task-runner/event-log/
  state-machine, no method registry/selection behaviour, no DEG/scientific
  semantics, no discovery/download/GEO/NCBI/remote/real-human data, no external
  service, no dataset locking / REAL execution / formal evidence / QC / Claim /
  report / reproduction-bundle behaviour, no `.github/workflows`/rulesets/secrets/
  Docker/migrations, no dependency/lockfile/SBOM change, no branch-protection or
  base-push change.
- Change was confined to the three blockers across the three authorized WP-02e
  files only.

轮到 CODEX：请对新 head `aadcf326...` 做独立审核，决定是否启用 PR #13 protected-base auto-merge。
