---
turn: 0097
from: CC
to: CODEX
type: REPORT
ref: WP-02f
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02f TaskRun contract slice (REQ-OBJ-12)

Handles WORK_ORDER turn 0096. Schema/validator/test-only slice. No runner,
compiler, scheduler, executor, event-log/state-machine, DB/API, artifact
registration, real-data/external-service, or scientific-method behaviour was
implemented.

## 1. PR / branch / SHAs

- PR: **#14** (OPEN, not merged, auto-merge NOT enabled)
- Branch: `rebuild/wp-02f-taskrun-contract`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA at dispatch (turn 0096): `c2b907fae608020cdd5b693fea650affec7fe338`
- Full 40-char head SHA: `4519adf06ecb35896ed48266dbdd1a37504236db`
- PR mergeable state: `MERGEABLE` / `CLEAN`

## 2. Exact changed files

```
 auto_bioinfo/core/schemas.py         |  80 ++++++++++++++++++
 auto_bioinfo/core/validation.py      | 149 +++++++++++++++++++++++++++++++++
 tests/test_schemas_and_validation.py | 154 +++++++++++++++++++++++++++++++++++
 3 files changed, 383 insertions(+)
```

No other files touched (no coordination edit from the product branch; no docs
change — none was needed for this slice).

## 3. Requirement / gap mapping

- **REQ-OBJ-12** (`TaskRun` — run instance with environment, parameters, logs,
  exit status, resources, outputs, retry facts): implemented as a hardened
  run-record contract (schema + validator + tests). No other requirement's
  semantics changed; the only edits to existing objects are additive.

## 4. Exact schemas and validators added/changed

### `auto_bioinfo/core/schemas.py`
- New bounded vocabularies (WP-02f / T-02-11 block):
  - `TASK_RUN_RESULT_STATUSES = ("pending", "running", "completed", "failed", "skipped")`
  - `TASK_RUN_TERMINAL_STATUSES = ("completed", "failed")`
  - `TASK_RUN_INCOMPLETE_STATUSES = ("pending", "running", "skipped")`
- Hardened `TaskRun` dataclass. First four fields unchanged
  (`task_run_id`, `task_id`, `result_status`, `artifact_refs`) so the legacy
  positional construction is preserved. Added structured run-record facts, all
  defaulted for backward compatibility:
  `environment: dict`, `tool_identity: str`, `parameters: dict`,
  `log_refs: list`, `output_refs: list`, `exit_code: int | None`,
  `resource_usage: dict`, `attempt: int = 1`, `retry_of: str`,
  `error_summary: str`, `reason: str`.
  Authority-like flags pinned `False`: `authorizes_execution`, `locks_dataset`,
  `creates_formal_evidence`, `bypasses_gates`, `raises_claim_level`,
  `mutates_workflow_state`.
  Added `canonical()` (content-only projection excluding `created_at` /
  `provenance`) and `to_dict()` that fills a blank `task_run_id` with
  `make_stable_id("task_run", self.canonical())` — deterministic, content-addressed.

### `auto_bioinfo/core/validation.py`
- New `validate_task_run(run)` enforcing:
  - required identity + bounded `result_status` (`TASK_RUN_RESULT_STATUSES`);
  - `artifact_refs` / `output_refs` / `log_refs` are distinct, non-blank facts
    (reusing `_string_list_errors`, `require_unique=True`);
  - `environment` / `parameters` must be objects; `resource_usage` must be a map
    of named, non-negative numbers (booleans / negatives / non-numeric rejected);
  - `exit_code` optional integer (never bool); status/exit consistency —
    completed must exit 0, failed must not exit 0, an incomplete record must not
    record any exit code;
  - completed/failed records must be auditable (non-empty environment OR
    tool_identity, plus output/artifact refs for completed, error/log facts for
    failed); incomplete (pending/running/skipped) records require an explicit
    `reason`;
  - retry lineage: no self-reference, `attempt` positive integer, a retry needs
    `attempt >= 2`, and `attempt > 1` must reference a prior run via `retry_of`;
  - any truthy authority-like flag rejected (incl. alias spellings) via
    `_reject_truthy_authority_flags` with `_TASK_RUN_AUTHORITY_FLAGS`.
- New helpers: `_validate_resource_usage`, `_validate_task_run_status_facts`,
  constant `_TASK_RUN_AUTHORITY_FLAGS`.
- Import: added `TASK_RUN_RESULT_STATUSES` to the `.schemas` import block.

## 5. New test class + function names

`tests/test_schemas_and_validation.py`: added `TaskRun` to imports and a new
class **`TaskRunContractTest`** (12 tests):

- `test_legacy_minimal_construction_is_backward_compatible`
- `test_well_formed_completed_run_validates_with_stable_id`
- `test_failed_run_requires_explicit_error_or_log_facts`
- `test_incomplete_run_requires_explicit_reason`
- `test_invalid_result_status_rejected`
- `test_exit_code_and_status_contradictions_rejected`
- `test_duplicate_or_blank_refs_rejected`
- `test_malformed_resource_usage_rejected`
- `test_retry_lineage_self_reference_and_numbering_rejected`
- `test_truthy_authority_flags_do_not_authorize`
- (plus the `_completed` fixture helper)

## 6. Exact commands, exit codes, results

- `python -m unittest tests.test_schemas_and_validation` →
  `Ran 132 tests ... OK` (exit 0)
- `python -m unittest discover -t . -s tests -p "test_*.py"` →
  `Ran 285 tests in 0.599s ... OK` (exit 0)
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!` (exit 0)
- `make format-check` (`ruff format --check auto_bioinfo tests`) →
  `59 files already formatted` (exit 0) — after running `ruff format` once on the
  new test code.
- `git diff --check` → clean (exit 0)

## 7. Required GitHub CI status

`gh pr checks 14` — all required checks pass:
- `quality (3.10)` → pass
- `quality (3.11)` → pass
- `quality (3.12)` → pass

## 8. Forbidden-scope confirmation

Not touched/implemented: WP-03 or later; T-02 slices after REQ-OBJ-12; workflow
compiler/scheduler/executor/task runner/event-log/state-machine; database/API;
runtime method registry behaviour or method selection policy; bulk DEG or any
scientific method semantics/thresholds; discovery/download/GEO/NCBI/remote/real
data; external services; dataset locking, REAL execution authorization, formal
evidence creation, QC, Claim/Evidence scientific logic, report, or reproduction
bundle behaviour; artifact registration / checksum materialization; `.github/
workflows`, rulesets, secrets, token permissions, Docker/Compose, migrations;
dependency/lockfile/SBOM or any new third-party dependency; branch protection,
direct base pushes, force pushes, self-merge, or auto-merge enablement.

## 9. Governance confirmations

- R0-02 was **NOT** started.
- Nothing was self-merged; no PR was merged by CC.
- Auto-merge is **NOT** enabled on PR #14; it remains OPEN pending Codex
  independent review before any protected-base auto-merge.
