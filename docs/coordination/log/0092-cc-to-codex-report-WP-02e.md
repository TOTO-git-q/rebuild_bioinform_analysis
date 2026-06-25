---
turn: 0092
from: CC
to: CODEX
type: REPORT
ref: WP-02e
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02e workflow DAG & task-packet contracts (T-02-09/10)

This turn handles WORK_ORDER turn 0091. Implements the next conservative WP-02
slice: REQ-OBJ-10 (WorkflowPlan explicit acyclic DAG) and REQ-OBJ-11
(TaskPacket subtype coverage, adding the missing DataPreparationTaskPacket).
Schema/validator/test only — no compiler, scheduler, executor, runtime, data
access, DB/API, or external-service behaviour.

## 1. PR / branch / base / head

- PR: **#13** (OPEN, MERGEABLE, non-draft)
- Branch: `rebuild/wp-02e-workflow-task-contracts`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA at dispatch (verified before branching): `db560a30d8217849e782e15ce3528b9d94b4189d`
- Full head SHA: `13c6594a2a47d76510e4177815af7797a9838a34`

## 2. Changed files (exactly the WO-allowed set)

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

`git diff --name-only db560a30…HEAD` returns exactly those three. No docs,
coordination, CI, ruleset, dependency, or other files touched.

## 3. Requirement / gap mapping

- **REQ-OBJ-10** (`requirements_catalog.csv:19`, gap_matrix `PARTIAL` → "add
  dependency edges + acyclicity"): `WorkflowPlan` hardened into an explicit
  acyclic DAG. Adds dependency-by-id edges, per-task expected inputs/outputs,
  and gates as contract data; deterministic serialization + stable id; explicit
  cycle detection.
- **REQ-OBJ-11** (`requirements_catalog.csv:20`, gap_matrix `PARTIAL` → "add
  DataPreparationTaskPacket"): added the missing `DataPreparationTaskPacket`
  contract and added contract validators for all four packet subtypes.
- REQ-OBJ-12 / `TaskRun` expansion: **not touched** (explicitly forbidden).

## 4. Exact schemas / validators added or changed

`auto_bioinfo/core/schemas.py`:

- `WorkflowPlan` (extended, backward-compatible): new fields `dependencies:
  list[list[str]]` (`[from_task, to_task]` = "from depends on to"),
  `expected_inputs: dict[str, list[str]]`, `expected_outputs: dict[str,
  list[str]]`, `gates: list[dict]`. New methods `_dependency_graph()`,
  `has_cycle()`, `topological_order()`, `canonical()`, `to_dict()`
  (deterministic, sorted dependencies; content-addressed `workflow_plan_id`).
  Legacy `WorkflowPlan(workflow_name, task_ids, ...)` construction preserved;
  `workflow_compiler.py` / `task_packets.py` runtime untouched.
- `DataPreparationTaskPacket` (new dataclass): `task_id`, `subquestion_id`,
  `planned_inputs`, `expected_outputs`, plus `planned_resource_ids`,
  `planned_dataset_profile_ids`, `preparation_steps`, `failure_conditions`, and
  non-authority flags `downloads_data` / `locks_dataset` /
  `authorizes_real_execution` / `creates_formal_evidence` pinned `False`.
  `to_dict()` stamps `packet_type="DataPreparationTaskPacket"` + stable id.

`auto_bioinfo/core/validation.py` (all additive; imports `WorkflowPlan`):

- `_string_list_errors(value, field, *, require_unique=False)` — shared helper.
- `validate_workflow_plan(plan)` — rejects blank/duplicate task ids, malformed
  edges, self-loops, dangling dependency endpoints, dependency cycles
  (explicit), and `expected_inputs`/`expected_outputs`/`gates` referencing
  undeclared tasks; duplicate IO facts rejected.
- `_reject_truthy_authority_flags(obj, flags, subject)` — shared helper.
- `validate_analysis_task_packet` — identity + distinct non-blank facts;
  rejects code-change authority.
- `validate_engineering_task_packet` — identity + distinct non-blank paths;
  rejects allowed-path scope escape (absolute / `..`) and allowed∩forbidden
  overlap.
- `validate_review_task_packet` — identity + valid `claim_ceiling` + non-blank
  audit scope / required checks.
- `validate_data_preparation_task_packet` — identity + planned input/output
  facts (non-blank, distinct) + rejects any truthy authority-like flag.

Runtime `auto_bioinfo.core.task_packets.validate_task_packets` is unchanged;
the new functions are independent schema-first contract validators.

## 5. New test classes / functions (`tests/test_schemas_and_validation.py`)

- `WorkflowPlanContractTest`: `test_legacy_minimal_workflow_plan_still_valid`,
  `test_well_formed_dag_validates_and_orders_deterministically`,
  `test_serialization_is_deterministic_regardless_of_dependency_order`,
  `test_blank_or_duplicate_task_ids_rejected`,
  `test_dangling_self_loop_and_cycle_rejected`,
  `test_inputs_outputs_and_gates_must_reference_declared_tasks`,
  `test_duplicate_io_facts_rejected`.
- `DataPreparationTaskPacketContractTest`:
  `test_well_formed_prep_packet_validates_and_id_is_stable`,
  `test_blank_identity_rejected`,
  `test_missing_planned_input_or_output_facts_rejected`,
  `test_duplicate_facts_rejected`,
  `test_truthy_authority_flags_do_not_authorize`.
- `TaskPacketSubtypeBoundaryTest`:
  `test_analysis_packet_validator_preserves_boundary`,
  `test_engineering_packet_validator_rejects_path_escape_and_overlap`,
  `test_review_packet_validator_requires_criteria_and_valid_ceiling`.

## 6. Exact commands, exit codes, results

Run in `conda activate bioinform`, on head `13c6594a…`:

- `python -m unittest tests.test_schemas_and_validation` → `Ran 120 tests ... OK` (exit 0)
- `python -m unittest discover -t . -s tests -p "test_*.py"` → `Ran 273 tests ... OK` (exit 0; was 258, +15)
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!` (exit 0)
- `make format-check` (`ruff format --check`) → `59 files already formatted` (exit 0)
- `git diff --check` → clean (exit 0)
- `make typecheck` (advisory / non-blocking) → only the pre-existing
  `auto_bioinfo/core/provenance.py:247` warning; **no** error in changed files.

## 7. Required GitHub CI status (exact head `13c6594a…`)

All three required checks **pass**:

- `quality (3.10)` — pass
- `quality (3.11)` — pass
- `quality (3.12)` — pass

## 8. Forbidden-scope confirmation

None of the following were touched/implemented: REQ-OBJ-12 / TaskRun expansion;
T-02 slices after REQ-OBJ-11; WP-03+; workflow compiler / scheduler / executor /
task runner / event-log / state-machine / DB / API; runtime method registry or
selection policy; bulk DEG / statistical thresholds; discovery/download/GEO/NCBI/
remote/real-human data; external services; dataset locking / REAL execution
authorization / formal evidence / QC / Claim-Evidence logic / report / bundle;
`.github/workflows` / rulesets / secrets / token permissions / Docker/Compose /
migrations; dependency / lockfile / SBOM changes; branch protection / direct base
push / force push / self-merge / auto-merge enablement.

## 9. Governance confirmations

- R0-02 was **not** started.
- Nothing was self-merged; **no** auto-merge was enabled. PR #13 remains OPEN and
  unmerged, pending Codex independent review before any protected-base auto-merge.
- No token / key / secret written to any file.
- Self-reported green only; no claim of CEO acceptance or OPS-00 PASS.
