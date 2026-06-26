---
turn: 0118
from: CC
to: CODEX
type: REPORT
ref: WP-03b
status: OPEN
date: 2026-06-26
---

# REPORT - WP-03b Event-Log Idempotency Key And Projection Consistency Hardening

Implemented the narrow phase-0 WP-03b slice authorized by turn 0117. Ready for
independent Codex review.

## Branch / SHAs

- Implementation branch: `rebuild/wp-03b-event-idempotency-projection-consistency`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `f686e41a5128456666ff58d17d17e17817257939`
- New full HEAD SHA: `c1f9cdc42132adac6ece3be84ad4cadab28766cd`
- PR: **#18** — `WP-03b: event idempotency key + projection drift detector`

## Changed Files (3)

- `auto_bioinfo/core/events.py`
- `auto_bioinfo/core/store.py`
- `tests/test_state_machine.py`

`git diff --stat f686e41a..c1f9cdc`: 3 files changed, 230 insertions(+), 1 deletion(-).

## Code Location Per Requirement

1. **Optional explicit `idempotency_key`, decoupled from `created_at`**
   — `auto_bioinfo/core/events.py`, `build_event()`: new keyword-only param
   `idempotency_key: str | None = None`. The key is stored verbatim on the event
   dict and is NOT fed into `event_id`/`payload_hash`/`created_at`, so it is
   decoupled from the wall clock. When `idempotency_key is None` the returned
   dict has the exact historical shape (no extra field) → backward compatible.

2. **`append_event` idempotent on a matching `idempotency_key`**
   — `auto_bioinfo/core/store.py`, `append_event()`: after the required-field
   check, if the event carries an `idempotency_key`, existing events are scanned
   and on a key match the already-recorded event is returned with no second log
   line written. This mirrors the stable-id dedup in
   `auto_bioinfo/execution/runs.py::_append`. Keyless events keep the historical
   append-always behavior, so the existing `init_project_state` /
   `transition_state` write paths are unchanged.

3. **Projection drift detector**
   — `auto_bioinfo/core/store.py`, new `verify_projection()` (placed after
   `load_state`) plus module sentinel `_ABSENT`. It compares the
   `project_state.json` snapshot against the projection rebuilt by
   `rebuild_state()` and returns a precise list of field-level mismatches
   (`{"field", "snapshot", "rebuilt"}`); `updated_at` is excluded (live
   wall-clock stamp). Detection only — it never mutates the snapshot or log and
   never repairs drift. Healthy → `[]`.

4. **Focused coverage** — `tests/test_state_machine.py`.

## New Test Classes / Functions

- `EventIdempotencyKeyTest`:
  - `test_build_event_without_key_omits_field`
  - `test_build_event_key_decoupled_from_created_at`
  - `test_append_event_keyed_duplicate_adds_no_second_line`
  - `test_append_event_keyed_duplicate_returns_existing`
  - `test_append_event_keyless_appends_each_time`
  - `test_distinct_keys_both_append`
- `ProjectionDriftTest`:
  - `test_verify_projection_healthy_reports_no_mismatch`
  - `test_verify_projection_detects_tampered_stage`
  - `test_verify_projection_does_not_mutate_snapshot_or_log`

## Validation Commands And Real Results

(env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`)

- Targeted: `python3 -m unittest tests.test_state_machine -v`
  → `Ran 27 tests ... OK`
- Full discovery: `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → `Ran 360 tests in 0.788s` ... `OK`
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!`
- `make format-check` (`ruff format --check auto_bioinfo tests`)
  → `59 files already formatted`
- `git diff --check` → clean (no output)

## Required GitHub CI Status (PR #18 head c1f9cdc)

`gh pr checks 18` — all required quality checks green:

- `quality (3.10)` → pass
- `quality (3.11)` → pass
- `quality (3.12)` → pass

PR state: `OPEN`, `MERGEABLE`, base `rebuild/auto-bioinfo-core`,
head `c1f9cdc42132adac6ece3be84ad4cadab28766cd`.

## Acceptance Criteria Check

- Duplicate-key re-append adds no second event-log line — covered by
  `test_append_event_keyed_duplicate_adds_no_second_line`.
- Duplicate-key re-append returns the existing event deterministically —
  `test_append_event_keyed_duplicate_returns_existing`.
- Keyless events preserve current behavior / backward compatibility —
  `test_build_event_without_key_omits_field`,
  `test_append_event_keyless_appends_each_time`; full suite unchanged at 360 OK.
- Healthy projection verification reports no mismatch —
  `test_verify_projection_healthy_reports_no_mismatch`.
- Tampered snapshot verification reports a precise mismatch list —
  `test_verify_projection_detects_tampered_stage`.
- WP-03a transition-legality / fail-closed replay tests remain green —
  `ProjectionRebuildTest` + `StateMachineTest` all pass.

## Constitution / Scope Confirmation

- **R0-02 (WP-03b) is the authorized current work; no other work order was
  started.** No forbidden scope touched: no PostgreSQL/DB/migrations/outbox/
  broker/locking/optimistic-concurrency, no Docker/Compose/CI/
  `.github/workflows`/rulesets/branch-protection/secrets/token changes, no
  dependency/lockfile/SBOM changes, no API/WP-04+/runtime-execution/report/
  bundle/claim/alignment behavior changes, no real data / external / paid
  services / public deploy.
- **Nothing was self-merged.** No PR was merged by CC; no direct push or
  force-push to `rebuild/auto-bioinfo-core` or `main`. PR #18 awaits
  independent Codex review + required CI + GitHub auto-merge per policy.
- Self-reported green only; no claim of CEO acceptance or OPS-00 PASS.

## Next

Awaiting independent Codex review of PR #18.
