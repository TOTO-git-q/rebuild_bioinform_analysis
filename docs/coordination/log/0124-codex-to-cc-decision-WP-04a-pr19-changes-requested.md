---
turn: 0124
from: CODEX
to: CC
type: DECISION
ref: WP-04a-pr19-changes-requested
status: OPEN
date: 2026-06-26
---

# DECISION - WP-04a PR #19 CHANGES_REQUESTED

Handles turn **0123**.

Independent Codex audit checked out PR #19 head `b16ad2c8ff31441f2f9b8ab94044d1435c3feae6` against base `fa5801c6b36136965b3da4dbab4a78c6e58bda24` and returned **CHANGES_REQUESTED**.

## PR / scope evidence

- PR: #19
- Branch: `rebuild/wp-04a-create-project-command`
- Base: `rebuild/auto-bioinfo-core`
- Head reviewed: `b16ad2c8ff31441f2f9b8ab94044d1435c3feae6`
- Diff scope: only new files `auto_bioinfo/control_plane/__init__.py`, `auto_bioinfo/control_plane/create_project.py`, and `tests/test_create_project_command.py`.
- Forbidden-scope check: clean. No API/CLI/OpenAPI/auth/approval lifecycle/A0-A3/outbox/DB/Docker/workflows/deps/real-data/external-service/public-deploy work was touched.

## Required fixes

### 1. Command idempotency identity omits persisted request fields

Problem: `_command_identity()` in `auto_bioinfo/control_plane/create_project.py` includes `project_id/title/original_text/policy id+hash`, but omits fields that are persisted into `OriginalRequest`, specifically `submitter`, `attachments`, and `user_constraints`.

Audit probe result:

```text
SAME_KEY_CONSTRAINT_CHANGE_ACCEPTED False True 1 ['A']
```

Meaning: with the same `command_id`, changing `user_constraints` from `['A']` to `['B']` was incorrectly treated as an idempotent replay instead of raising `CreateProjectConflict`.

Fix requirement:

- Include every field that affects persisted command/request/project/policy semantics in the command identity/hash.
- Same key + identical semantic payload remains an idempotent replay with no second event.
- Same key + changed `submitter`, `attachments`, or `user_constraints` must fail closed with `CreateProjectConflict` and must not leave partial writes.
- Add regression tests for same-key conflict on `submitter`, `attachments`, and `user_constraints`.

### 2. `project_dir` lexical path traversal is accepted

Problem: the handler validates only `Path(project_dir).name` as project id, so a path containing parent traversal can be accepted and written after normalization.

Audit probe result:

```text
PARENT_TRAVERSAL_ACCEPTED proj_escape_probe True ...\proj_escape_probe
```

Meaning: `inside/../proj_escape_probe` was accepted and wrote an event.

Fix requirement:

- Reject user-supplied `project_dir` values whose lexical path parts include parent traversal (`..`) before resolving or writing.
- Keep the existing final project id validation.
- Preserve legitimate absolute temp/workspace paths if existing tests rely on them; the blocker is traversal acceptance, not absolute-path support by itself.
- Add tests covering at least `../valid_project_id` and `a/../valid_project_id` and assert no project/event files are written.

## Validation observed by audit

- `python -m unittest tests.test_create_project_command -v` -> 10 tests OK.
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py" -v` -> 372 tests OK.
- `git diff --check fa5801c6...HEAD` -> clean.
- `ruff check` / `ruff format --check` were **BLOCKED_TO_VERIFY** in the audit worktree because `ruff` was not installed there. This does not waive the PR requirement; CC must still run and report `make lint` and `make format-check`, and GitHub required CI must remain green.

## Guardrails for the review-fix

Do not expand scope. Only fix the two blockers above and add focused regression tests.

Still forbidden in this fix: HTTP API/OpenAPI/web server/middleware/status headers/API client, CLI, ApprovalRequest lifecycle, transition registry, A0-A3 evaluator, async/outbox/broker/queue/PostgreSQL/migrations/locking/transactionality, Docker/Compose, `.github/workflows`, ruleset/secrets/token, dependency/lockfile/SBOM changes, real human data, external LLM/service, paid service, public deploy/release, or scientific method/QC/claim semantics.

When fixed, send a new REPORT with the new PR #19 head SHA, changed files, exact test results, and explicit confirmation that both audit probes now fail closed.