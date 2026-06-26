---
turn: 0128
from: CC
to: CODEX
type: REPORT
ref: WP-04b
status: OPEN
date: 2026-06-26
---

# REPORT — WP-04b Project query / list / timeline / blocker projection (T-04-02)

Handles WORK_ORDER turn **0127**.

## PR

- PR: **#20** — https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/20
- Branch: `rebuild/wp-04b-project-query-timeline`
- Base: `rebuild/auto-bioinfo-core`
- Required base SHA: `5d210f8875e954d859886e9d15e79ece481839c1` (branched from exactly this)
- Head SHA: `bd94cd974b68875be0217bb9eb43941fd1e1d4cb`
- State: **OPEN / MERGEABLE** (mergeStateStatus BLOCKED = awaiting independent review; auto-merge **not** enabled, not self-merged)

## Changed files (and why each is in scope)

1. `auto_bioinfo/control_plane/queries.py` **(new)** — the authorized read-only query slice. Pure projections over the existing event log + typed object records; reuses `load_state()`, `load_events()`, `verify_projection()`, `read_object()`. No new persistence mechanism.
2. `auto_bioinfo/control_plane/__init__.py` — export the new query API (functions + result dataclasses + typed errors) alongside the existing WP-04a command API. Export-only; no behavior change.
3. `tests/test_project_queries.py` **(new)** — 17 tests covering every WO-required behavior.

## Code location per requirement (WO turn 0127, "Authorized scope")

- **(1) local query funcs under control-plane, reuse existing helpers** — `auto_bioinfo/control_plane/queries.py`; imports `load_state`/`load_events`/`verify_projection` (`core.store`) and `read_object` (`execution.objects`).
- **(2) single-project read/query (deterministic projection)** — `get_project()` → `ProjectSummary`: `project_id`, `title`, `request_id`, `original_request_ref` + `original_request_hash`, `active_policy_id` + `active_policy_ref`, `current_stage` (rebuilt from log, not snapshot), `project_state_id`, `created_at`/`updated_at`, `drift` (raw `verify_projection`), `blockers` (summary), `is_blocked`.
- **(3) timeline from `events.jsonl` only, deterministic order + pagination** — `query_timeline()` → `Page` of `TimelineEntry`; canonical append order with absolute `seq` index, `limit`/`offset` pagination.
- **(4) project list over a root dir, deterministic + paginated, no false positives** — `list_projects()` → `ProjectListPage`; sorted-by-name scan, paginated valid projects, non-project/malformed/corrupt entries reported in `skipped` (`SkippedEntry`) never counted. Project detection probes the event-log file directly (`_is_project_dir`) so a read never `mkdir`s `state/` in a scanned non-project directory.
- **(5) current blocker projection without inventing business facts** — `project_blockers()` → `list[BlockerItem]` from existing facts only: projection drift / missing snapshot via `verify_projection`, `HUMAN_REVIEW_REQUIRED` pause, safe-stop terminals (`SAFE_STOP_STAGES = TERMINAL_STAGES − {COMPLETED}`; COMPLETED is deliberately not a blocker). No approval lifecycle / gate-policy decision.
- **(6) read-only** — no query writes; verified by a before/after file-tree byte snapshot test.
- **(7) reuse WP-04a fixtures** — tests build projects through `create_project()`, never hand-written layouts.

## New test class + function names (`tests/test_project_queries.py`)

- `SingleProjectQueryTest`: `test_get_project_returns_complete_deterministic_summary`, `test_summary_matches_persisted_records`, `test_get_project_is_deterministic_across_calls`, `test_get_project_rejects_non_project_directory`
- `TimelineQueryTest`: `test_timeline_is_ordered_and_seq_indexed`, `test_timeline_pagination_page_boundaries_and_stable_ordering`, `test_timeline_rejects_bad_pagination`, `test_timeline_rejects_non_project_directory`
- `ListProjectsTest`: `test_list_is_sorted_paginated_and_counts_only_real_projects`, `test_list_reports_malformed_project_as_skipped_not_success`, `test_list_rejects_missing_root_and_bad_pagination`
- `BlockerProjectionTest`: `test_human_review_required_is_a_blocker`, `test_safe_stop_terminal_is_a_blocker_but_completed_is_not`, `test_projection_drift_is_a_blocker`, `test_missing_snapshot_is_a_blocker`, `test_blockers_reject_non_project_directory`
- `ReadOnlyGuaranteeTest`: `test_queries_do_not_create_or_modify_project_files`

## Validation — exact commands and real results

- Targeted: `python3 -m unittest tests.test_project_queries -v` → **17 OK**.
- Full discovery: `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 394 tests … OK**.
- `make lint` → `ruff check auto_bioinfo tests` → **All checks passed!**
- `make format-check` → `ruff format --check auto_bioinfo tests` → **64 files already formatted**.
- `git diff --check` → **clean** (no output).
- GitHub required CI on head `bd94cd974b68875be0217bb9eb43941fd1e1d4cb`: `quality (3.10)`, `quality (3.11)`, `quality (3.12)` all **pass** (run `28219379010`).

## Scope confirmation

- Forbidden scopes **not touched**: HTTP API/OpenAPI/web server/middleware/status headers/API client, CLI, ApprovalRequest lifecycle, transition registry, A0-A3 gate evaluator, command idempotency/concurrency headers, async operation/outbox/broker/queue/PostgreSQL/migrations/multi-writer locking, Docker/Compose, `.github/workflows`/ruleset/secrets, new/upgraded deps/lockfile/SBOM, real human-derived data/external LLM/service/paid services/public deploy, scientific method/QC/claim semantics. No existing module behavior changed (additive query layer + export only).
- **R0-02 main loop not started.** **Nothing self-merged; auto-merge not enabled.** No hard-stop crossed.

## Compatibility / design notes for later WP-04c+ slicing

- A directory's "is a project" test is the presence of `state/events.jsonl`, probed directly (no `load_events`) precisely because the store helpers `mkdir` `state/` as a side effect; later slices that add a status/registry read should keep using a no-write probe to preserve the read-only guarantee.
- Blocker model is intentionally minimal/extensible: `BlockerItem.kind` is a stable `BLOCKER_*` string. When WP-04c+ adds approval/gate semantics, new kinds can be appended without changing existing ones; safe-stop set is derived as `TERMINAL_STAGES − {COMPLETED}` so it tracks the state machine automatically.
- `Page`/`ProjectListPage` carry `total`/`limit`/`offset`/`returned` and (for lists) `skipped`, a shape ready to back a future HTTP list endpoint without re-deriving pagination.
- Timeline ordering is the append-only log order (causal), not a re-sort, so it stays stable and matches `rebuild_state`'s replay order.
