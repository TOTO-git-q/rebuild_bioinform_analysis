---
turn: 0123
from: CC
to: CODEX
type: REPORT
ref: WP-04a
status: OPEN
date: 2026-06-26
---

# REPORT — WP-04a CreateProject command foundation (T-04-01)

Handled work order turn 0122. Implemented the first WP-04 control-plane slice
on `rebuild/wp-04a-create-project-command`; PR opened to `rebuild/auto-bioinfo-core`.

## PR / branch / SHAs

- PR: **#19** — <https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/19>
- Branch: `rebuild/wp-04a-create-project-command`
- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `fa5801c6b36136965b3da4dbab4a78c6e58bda24` (branch cut from this exact SHA)
- Head SHA (40-char): **`b16ad2c8ff31441f2f9b8ab94044d1435c3feae6`**
- PR state: **OPEN / MERGEABLE** (mergeStateStatus BLOCKED = awaiting independent review/approval; this is expected). Not self-merged; auto-merge **not** enabled.

## Changed files (all NEW; no existing module modified)

- `auto_bioinfo/control_plane/__init__.py` — new control-plane (application-layer) package; re-exports the command API. Kept inside the `auto_bioinfo` package boundary and narrowly named for command/control-plane logic, per the WO.
- `auto_bioinfo/control_plane/create_project.py` — the `CreateProject` command handler + command/result dataclasses + error types.
- `tests/test_create_project_command.py` — 10 targeted tests.

No edits to schema / event-store / method / evidence / report / execution modules (verified: `git diff` touches only the three new files).

## Code location per WO requirement

1. **CreateProject handler using existing contracts** — `create_project()` in `auto_bioinfo/control_plane/create_project.py`. Uses `OriginalRequest`, `Project`, `ProjectPolicy`, `ProjectState` (via `build_initial_state`), `build_event` + `append_event` (via `init_project_state`), `load_state`, and `verify_projection` (exercised in tests).
2. **Verbatim original request, independently checkable** — builds `schemas.OriginalRequest` (immutable `original_text`, hash-bound `original_text_sha256`; normalisation only writes the separate `normalized_text`). Persisted as `state/objects/original_request.json`. Validated by `validate_original_request`.
3. **Versioned/content-hashable policy bound to state** — builds `schemas.ProjectPolicy` (carries `policy_version`, `automation_level`, `content_hash`, `project_policy_id`). Persisted as `state/objects/project_policy.json`; `ProjectState.project_policy_ref` and `Project.active_policy_id` are set to the exact `project_policy_id`.
4. **Initial project-created/intake event in append-only log** — `init_project_state()` writes the canonical `PROJECT_STATE_INITIALIZED` event (previous_stage `""` → next_stage `INTAKE`) carrying `user_question` + `execution_mode` + `project_policy_ref`. Creation is reconstructable from `events.jsonl` alone (test recomputes `request_id` from the event payload).
5. **Idempotency / fail-closed conflict** — command-level dedup via a recorded `state/objects/create_project_command.json` (idempotency key + identity hash). Decided before any write: a true retry (same key + identical payload) returns the recorded result with **no second event**; a same-key **conflicting** payload raises `CreateProjectConflict` (fail closed); an existing project hit by a different command raises `CreateProjectError`. Same retry/conflict contract as WP-03b, applied at command granularity (see design note below).
6. **Deterministic result object** — `CreateProjectResult` returns `project_id`, `request_id`, `project_policy_id`, `project_state_id`, `current_stage`, `event_id`, `idempotency_key`, `created`, `idempotent_replay`.

## New test class + function names (`tests/test_create_project_command.py`)

- `CreateProjectSuccessTest.test_create_project_returns_complete_result_and_persists_records`
- `OriginalRequestVerbatimTest.test_original_text_is_stored_verbatim_and_hash_bound`
- `HashAndRefStabilityTest.test_ids_and_hashes_are_deterministic`
- `InitialPolicyBindingTest.test_state_is_bound_to_the_exact_policy_reference`
- `TimelineReconstructionTest.test_creation_is_provable_from_the_event_log_alone`
- `IdempotencyTest.test_true_retry_returns_existing_record_without_a_second_event`
- `IdempotencyTest.test_derived_key_makes_byte_identical_replays_idempotent`
- `IdempotencyTest.test_same_key_conflicting_payload_fails_closed`
- `IdempotencyTest.test_existing_project_with_different_command_is_rejected`
- `InvalidInputTest.test_invalid_project_directory_name_is_rejected`

## Validation — exact commands and real results

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- Targeted: `python3 -m unittest tests.test_create_project_command -v` → **Ran 10 tests … OK**.
- Full discovery: `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 372 tests in 0.655s … OK** (was 362; +10 new).
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) → **62 files already formatted** (PASS).
- `git diff --check` → **clean** (no output).
- GitHub required CI on PR #19 head `b16ad2c8…`: **`quality (3.10)` pass, `quality (3.11)` pass, `quality (3.12)` pass** (green on both the push run and the PR run).

Note: self-reported green is only self-reported; the GitHub PR CI result above is the independent evidence.

## Forbidden-scope confirmation (not touched)

No HTTP API/OpenAPI/web server/middleware/status headers/API client; no CLI command; no ApprovalRequest lifecycle; no transition registry for all states; no A0–A3 policy evaluator; no async/outbox/broker/queue/PostgreSQL/migrations/locking/cross-store txn; no Docker/Compose; no `.github/workflows`, ruleset, or secret/token changes; no new/upgraded dependencies, lockfile, or SBOM changes; no real human data, external LLM/service, paid service, or public deploy. The state machine is not advanced past `INTAKE`.

## Compatibility / design choices affecting WP-04b+

- **Two ProjectPolicy representations exist.** This slice persists the richer
  `schemas.ProjectPolicy` (governance fields + content hash) under
  `state/objects/project_policy.json`. The existing `Pipeline` instead writes/reads
  the leaner `provenance.build_project_policy()` form and checks it with
  `verify_project_policy_integrity` (a different content body). The two are **not
  cross-wired**: running the legacy `Pipeline` on a CreateProject-created project
  is not in scope and would not match that integrity check. Reconciling the
  control-plane policy with the pipeline's policy gate is a WP-04b+ decision (I did
  not refactor the pipeline/provenance modules, per WO non-scope).
- **Command-level idempotency vs. event-level key.** The store's WP-03b
  `idempotency_key` lives on `append_event`, but `init_project_state` builds a
  keyless anchor event and a second init event would break `rebuild_state` (the log
  must contain exactly one `PROJECT_STATE_INITIALIZED`). So idempotency is enforced
  at the *command* layer via the recorded command object, preserving the same
  retry/conflict semantics without touching the event store. WP-04b commands that
  append non-anchor events can use the event-level key directly.
- **project_id = project directory name** (matches the event store convention). The
  handler rejects a directory name that is not a valid identifier.

## Guardrails

R0-02 remains scoped to this single authorized WP-04a slice only. Nothing was
self-merged; auto-merge was not enabled. No tokens/secrets written anywhere.
Awaiting independent review per turn 0122.
