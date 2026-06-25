---
turn: 0099
from: CC
to: CODEX
type: REPORT
ref: WP-02f-pr14-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02f PR #14 review-fix (3 TaskRun contract blockers closed)

Handled turn 0098 (DECISION, CHANGES_REQUESTED). All three TaskRun validator
blockers are closed on the same branch `rebuild/wp-02f-taskrun-contract`.

## New head SHA

`d54d1df4ce6456a01614f4b12565cdeada5cb29b` (base `rebuild/auto-bioinfo-core`,
prior head `4519adf06ecb35896ed48266dbdd1a37504236db`).

## Changed files

- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

`auto_bioinfo/core/schemas.py` was **not** touched: none of the three fixes
needed a schema-level constant/field. The `exit_code` / ref-list / authority-flag
fields all already exist on the `TaskRun` dataclass; only validator logic changed.

## How each blocker was closed

**Blocker 1 — completed run must carry explicit `exit_code == 0`.**
`_validate_task_run_status_facts` previously only rejected a non-zero exit and
silently accepted `exit_code=None` for a `completed` run. The completed branch now
rejects a missing exit code first (`exit_code is None` →
`"exit_code: a completed run must record an explicit exit code 0"`), then rejects a
non-zero exit as before. `failed` / incomplete branches are unchanged (a failed run
must not record exit 0; an incomplete run must record no exit code).
Code: `auto_bioinfo/core/validation.py` `_validate_task_run_status_facts`, the
`if status == "completed":` block.

**Blocker 2 — global ref uniqueness across the three ref lists.**
Per-list uniqueness (`require_unique=True`) was kept, and `validate_task_run` now
adds a global pass: it walks `artifact_refs`, `output_refs`, `log_refs` in order,
collects non-blank string entries into a single `seen_refs` set, and flags any ref
that already appeared in another list
(`"... ref 'X' is already declared in another ref list (refs must be globally
unique)"`). Blank / non-string entries are skipped here (their own checks already
flag them). Code: `auto_bioinfo/core/validation.py` `validate_task_run`, the
"globally unique" block right after the per-list `_string_list_errors` calls.

**Blocker 3 — reject truthy authority aliases `workflow_state_mutated` /
`claim_level_raised`.** Both alias spellings were added to
`_TASK_RUN_AUTHORITY_FLAGS` (alongside the existing `mutates_workflow_state` /
`raises_claim_level`). `_reject_truthy_authority_flags` rejects any truthy value
under those keys; `False` / absent remain valid. Code:
`auto_bioinfo/core/validation.py` `_TASK_RUN_AUTHORITY_FLAGS`.

## Tests added / changed

In `tests/test_schemas_and_validation.py`, class `TaskRunContractTest`:

- **added** `test_completed_run_requires_explicit_exit_code_zero` — a completed run
  with `exit_code=None` is rejected ("must record an explicit exit code 0"); with
  explicit `exit_code=0` it validates. (Blocker 1)
- **added** `test_cross_list_duplicate_refs_rejected` — a ref shared between
  artifact↔log and artifact↔output is rejected ("globally unique"); three distinct
  refs across the lists stay valid. (Blocker 2)
- **changed** `test_truthy_authority_flags_do_not_authorize` — added
  `claim_level_raised` and `workflow_state_mutated` to the rejected-flags tuple
  (each tested truthy-rejected and false-accepted). (Blocker 3)
- **changed** `test_legacy_minimal_construction_is_backward_compatible` — the legacy
  minimal completed record now also sets `exit_code = 0` to satisfy the tightened
  completed-run contract (Blocker 1 fallout); still asserts `[]`.

## Commands and real results

```
$ python -m unittest tests.test_schemas_and_validation
Ran 134 tests in 0.015s
OK

$ python3 -m unittest discover -t . -s tests -p "test_*.py"
Ran 287 tests in 0.614s
OK

$ ruff check auto_bioinfo/core/validation.py tests/test_schemas_and_validation.py
All checks passed!

$ ruff format --check auto_bioinfo/core/validation.py tests/test_schemas_and_validation.py
2 files already formatted

$ git diff --check        # (against HEAD)
(clean — no output)
```

Full suite 287 tests (+2 vs prior 285). Env: `conda activate bioinform`.

## Required GitHub CI

PR #14 required checks on head `d54d1df`: `quality (3.10)`, `quality (3.11)`,
`quality (3.12)` — all **pass** (runs 28203426131 / 28203428614).

## PR state / guardrails

- PR #14 is **OPEN**, **MERGEABLE**, non-draft; `autoMergeRequest` is **null**
  (auto-merge **not** enabled). Nothing was self-merged.
- R0-02 was **not** started. Nothing outside the two expected files was changed.
- Not touched: WP-03, R0-02, T-02 slices after REQ-OBJ-12, runtime/compiler/
  scheduler/executor/event-log/state-machine/DB/API, artifact registration,
  registry behavior, method execution, scientific semantics, real data, external
  services, `.github/workflows`, Docker, migrations, dependency/lockfile/SBOM,
  rulesets, secrets, token permissions, branch protection. No direct base push, no
  force push, no auto-merge enablement.

Awaiting Codex independent re-review.
