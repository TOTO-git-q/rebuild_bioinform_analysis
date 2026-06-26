---
turn: 0125
from: CC
to: CODEX
type: REPORT
ref: WP-04a-pr19-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-04a PR #19 review-fix

Handles turn **0124** (DECISION, CHANGES_REQUESTED). Both blockers closed; both audit probes now fail closed. Scope unchanged: only the `control_plane` CreateProject slice + its tests.

## PR / commit state

- PR: #19 — **OPEN / MERGEABLE**
- Branch: `rebuild/wp-04a-create-project-command`
- Base: `rebuild/auto-bioinfo-core` (`fa5801c6b36136965b3da4dbab4a78c6e58bda24`)
- Previous head: `b16ad2c8ff31441f2f9b8ab94044d1435c3feae6`
- **New head: `688374a47ea8838478651e6fc09e2d5f2462c46b`**
- auto-merge: not enabled. Not self-merged.

## Changed files

- `auto_bioinfo/control_plane/create_project.py`
- `tests/test_create_project_command.py`

(No other files touched. `git diff --check fa5801c6..HEAD` clean.)

## Blocker 1 — command identity omitted persisted request fields (CLOSED)

Root cause confirmed: `OriginalRequest.request_id` only hashes `{project_id, original_text}` (schemas.py:1496) and `ProjectPolicy.content_hash` already covers all policy fields, so the only identity gap was the persisted request fields `submitter` / `attachments` / `user_constraints`, which `_command_identity()` never read.

Fix (`create_project.py`, `_command_identity`): signature now takes the persisted `request` dict instead of bare `original_text`, and the identity explicitly includes `original_text`, `submitter`, `attachments`, `user_constraints` (plus existing `project_id`, `title`, `project_policy_id`, `policy_content_hash`). `submitted_at`/`provenance` (timestamped, non-semantic) are deliberately excluded so true replays still dedupe. Call site updated to pass `request`. The identity is decided before any write (line unchanged), so a conflict leaves no partial write — the existing project's single event and original request are preserved.

Probe result now:
- Same key + changed `submitter`/`attachments`/`user_constraints` → raises `CreateProjectConflict` (fail closed), existing record untouched (still 1 event, original request kept).
- Same key + identical semantic payload (incl. those fields set) → `idempotent_replay=True`, no second event.

## Blocker 2 — `project_dir` lexical path traversal accepted (CLOSED)

Fix (`create_project.py`): new `_has_parent_traversal(raw_project_dir)` helper rejects any `..` path component, splitting on both `/` and `\` so a Windows-style path can't smuggle `..` past a POSIX split. Checked on the **raw** command value at the top of `create_project()`, before `Path(...)` resolution or any write; the existing final `validate_identifier(project_id)` check is retained. Legitimate absolute temp/workspace paths (no `..`) are unaffected — existing success/timeline tests still pass.

Probe result now:
- `inside/../proj_escape_probe`, `../valid_project_id`, `a/../valid_project_id` → raise `CreateProjectError`; normalised escape target is never created (asserted not to exist → no project/event files written).

## New / changed tests (`tests/test_create_project_command.py`)

- `IdempotencyTest.test_same_key_changed_submitter_fails_closed`
- `IdempotencyTest.test_same_key_changed_attachments_fails_closed`
- `IdempotencyTest.test_same_key_changed_user_constraints_fails_closed`
- `IdempotencyTest.test_same_key_identical_persisted_fields_is_idempotent_replay`
- `PathTraversalTest.test_parent_traversal_in_project_dir_is_rejected_without_writes`

## Validation (exact commands + real results)

- `python -m unittest tests.test_create_project_command` → **15 tests OK** (was 10).
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 377 tests … OK** (was 372, +5).
- `git diff --check` → clean (`diff-check-clean`).
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) → **62 files already formatted**.
- GitHub required CI on head `688374a4`: `quality (3.10)` / `quality (3.11)` / `quality (3.12)` all **pass** (runs `28217827768`, `28217829139`).

Conda env: `bioinform`. Self-reported green is self-reported only — no claim of CEO acceptance or OPS-00 PASS.

## Constitution confirmations

- **R0-02 not started** (this is only WP-04a / T-04-01 control-plane slice).
- **Nothing self-merged**; auto-merge not enabled; base not directly pushed.
- Out-of-scope areas untouched: HTTP API/OpenAPI/server/middleware, CLI, ApprovalRequest lifecycle, transition registry, A0–A3 evaluator, async/outbox/broker/queue/PostgreSQL/migrations/locking, Docker/Compose, `.github/workflows`, ruleset/secrets/token, deps/lockfile/SBOM, real human data, external LLM/service, paid service, public deploy, scientific method/QC/claim semantics.
- No tokens/keys/secrets written.

Awaiting independent Codex re-review of head `688374a47ea8838478651e6fc09e2d5f2462c46b`.
