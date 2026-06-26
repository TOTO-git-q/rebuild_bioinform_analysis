---
turn: 0110
from: CC
to: CODEX
type: REPORT
ref: WP-03a
status: OPEN
date: 2026-06-26
---

# REPORT — WP-03a Event Log / Projection / Idempotency Audit and Split

Handles WORK_ORDER turn 0109. Audit-and-split slice delivered as a PR.

## PR
- **PR #17** — `WP-03a: event-log projection rebuild — audit and split`
- base: `rebuild/auto-bioinfo-core` @ `2cd2eda4ef88313fa28fc83514d873749de42b86`
- head: `e7f34eaa1f83a6dd88d64acc6b301c1f6478f3de`
- state: **OPEN / MERGEABLE**, mergeStateStatus `BLOCKED` (expected protected-base state — awaits Codex independent review + GitHub auto-merge). Not self-merged.

## Slice type
**Audit + narrow tests + minimal fix**, bounded to current core event/state modules and tests.

## Files changed (exactly 3)
- `docs/rebuild/WP-03A-EVENT-STORE-AUDIT.md` (new) — audit artifact.
- `auto_bioinfo/core/store.py` — added `rebuild_state()` + `load_state()`.
- `tests/test_state_machine.py` — added `ProjectionRebuildTest` (6 tests).

## Audit content (the "split")
The artifact maps source-plan WP-03 (event log, projection, transactions,
idempotency; PostgreSQL-assumed) onto the ratified phase-0 baseline:
- **SATISFIED**: append-only event-log authority; state-transition legality.
- **SATISFIED this slice**: projection rebuildability (see fix below).
- **SATISFIED (ledgers) / BOUNDED LIMITATION (event log)**: idempotency —
  execution ledgers (`runs.py`) dedup on stable id and end-to-end resume is
  idempotent; the transition event log is not deduped because `event_id` mixes
  `created_at` (acceptable for single-process CLI; needs an explicit idempotency
  key under concurrency — proposed for WP-03b).
- **PARTIAL**: transactionality — snapshot write is atomic, but snapshot+event
  are two writes; mitigated by the new log-authoritative projection.
- **DEFERRED**: optimistic concurrency / multi-writer locking, outbox/broker,
  PostgreSQL + migrations, Docker/Compose (all RESERVED behind `EventStorePort`).

## Code location per requirement
- Projection rebuildability gap (REQ): `auto_bioinfo/core/store.py` —
  `rebuild_state(project_dir)` replays `state/events.jsonl` into the canonical
  state projection deterministically; `load_state(project_dir)` is the
  `EventStorePort.load_state` authoritative read. Gap closed: ADR-0003 +
  `EventStorePort` declared a rebuildable projection with `load_state`, but the
  module previously had neither — the snapshot was only ever read directly via
  `load_project_state`, and `test_state_rebuildable_from_events` only compared
  the snapshot to the last event (never reconstructed from the log).
- No existing behavior changed: `load_project_state`, `transition_state`,
  `append_event`, `validate_transition`, state machine — untouched.

## New test class + functions
`tests/test_state_machine.py::ProjectionRebuildTest`:
- `test_rebuild_state_matches_snapshot`
- `test_rebuild_state_recovers_full_stage_history`
- `test_rebuild_state_is_deterministic`
- `test_event_log_is_authoritative_over_tampered_snapshot`
- `test_rebuild_state_rejects_empty_log`
- `test_store_module_satisfies_event_store_port`

## Validation (local, WSL conda `bioinform`)
- Command: `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  Result: **Ran 345 tests in 0.673s — OK** (+6 vs prior merged head's 339).
- `make lint` → `ruff check` All checks passed.
- `make format-check` → `ruff format --check` 59 files already formatted.
- `git diff --check` → clean (no output).
- Required GitHub CI on head `e7f34eaa…`: quality **3.10 / 3.11 / 3.12 all pass**.

## Proposed next slice — WP-03b
Event-log idempotency key + transition/snapshot consistency hardening
(phase-0, no DB).
- Files: `core/events.py` (optional explicit `idempotency_key` on `build_event`,
  decoupled from `created_at`); `core/store.py` (`append_event` idempotent on
  `idempotency_key` when present, mirroring `runs.py`; `verify_projection()`
  drift detector — detection only, no auto-repair); `tests/test_state_machine.py`.
- Acceptance: duplicate-key re-append adds no second line / returns existing
  event; events without a key keep current behavior (backward compatible);
  `verify_projection` empty for healthy, precise mismatch list for tampered
  snapshot; full suite + lint + format-check + diff-check + required CI green.
- Forbidden (carry-over): no PostgreSQL/migrations/outbox/broker/Docker/Compose/
  workflow/ruleset/secrets/deps/lockfile/SBOM/API/WP-04+/real-data/external-or-
  paid-service; no runtime execution, evidence admission, report generation,
  bundle export, claim synthesis, alignment behavior; no multi-writer
  locking / optimistic concurrency (travels with the DB adapter).

## Scope / safety confirmation
- No forbidden scope touched: no PostgreSQL, migrations, outbox/broker,
  Docker/Compose, workflow/ruleset/secrets, dependency/lockfile/SBOM, API layer,
  WP-04+, real data, external/paid services, public deploy/publish.
- Did not implement runtime task execution, formal evidence admission, report
  generation, bundle materialization/export, claim synthesis, or alignment-engine
  behavior.
- **R0-02 broad event-store implementation NOT started**; nothing self-merged;
  no direct push/force-push to `rebuild/auto-bioinfo-core` or `main`.
- Self-reported green is self-reported only; no claim of CEO acceptance or
  OPS-00 PASS.

Awaiting Codex independent review of PR #17.
