# WP-03a — Event Log / Projection / Idempotency Audit and Split

> Scope: audit-and-split slice for WP-03 (work order turn 0109).
> Base: `rebuild/auto-bioinfo-core` @ `2cd2eda4ef88313fa28fc83514d873749de42b86`.
>
> Purpose: reconcile the **source implementation plan** for WP-03 (event log,
> projection, transactions, idempotency — written assuming PostgreSQL) with the
> **ratified phase-0 baseline** (local/offline core; append-only JSONL event log
> and projection contracts; PostgreSQL / outbox / broker / Docker deferred behind
> ports). This document is the contract that splits WP-03 into what is satisfiable
> now versus what stays deferred, and proposes the next slice (WP-03b).

---

## 1. Current event / state / idempotency surface

| Concern | Where | Summary |
|---|---|---|
| Event construction | `auto_bioinfo/core/events.py` | `build_event(...)` builds a canonical event with a content-addressed `payload_hash` and a stable `event_id` (`event_id` mixes `created_at`, so two events are distinct by wall-clock time). |
| Append-only log | `auto_bioinfo/core/store.py` → `append_event`, `_events_path` | Events are appended to `state/events.jsonl`, one JSON object per line, `sort_keys=True`. `append_event` validates the required field set; it only ever appends (no rewrite, no truncate). |
| State snapshot | `store.py` → `_write_state`, `load_project_state` | `state/project_state.json` is written atomically (`*.json.tmp` + `replace`). It is a **cache** of the projection, not the authority. |
| Projection rebuild | `store.py` → `rebuild_state`, `load_state` *(added this slice)* | Replays the event log into the canonical state; `load_state` is the `EventStorePort.load_state` operation. |
| State machine | `auto_bioinfo/core/state.py` | `MAIN_SEQUENCE` + side/terminal stages, `LINEAR_NEXT` edge map, `allowed_next_stages`, `build_initial_state`, `with_stage`. Acyclic happy path; every working stage can reach conservative-stop terminals; terminals have no exits. |
| Transition legality | `store.py` → `transition_state`, `validate_transition` | Rejects unknown stages, illegal edges, and leaving a terminal without explicit `resume`. Enforces the cross-event guard `TASKS_RUNNING → EVIDENCE_SYNTHESIZED` requires a prior `QC_COMPLETED` event. |
| Legacy migration | `store.py` → `record_legacy_migration` | One-time conservative migration recorded as an explicit `LEGACY_PROJECT_MIGRATED` event (never silent). |
| Idempotent ledgers | `auto_bioinfo/execution/runs.py` | TaskRun / QCReport / EvidenceItem / Claim each in their own append-only `state/*.jsonl`; `_append` dedups on the record's stable id, so re-appending the same record is a no-op. |
| Port contract | `auto_bioinfo/ports/__init__.py` → `EventStorePort` | Declares `append_event`, `load_events`, `load_state` (rebuild the projection). RESERVED production adapter: PostgreSQL event store + outbox + optimistic concurrency. |
| ADR | `docs/adr/0003-event-sourced-state.md` | "Project state is a projection of the append-only event log; the JSON snapshot is only a rebuildable cache; state advances only via legal transitions; per-id idempotent ledgers; immutability via new versions; PostgreSQL reserved behind `EventStorePort`." |

---

## 2. Source-plan WP-03 → phase-0 baseline mapping

| Source-plan WP-03 concern | Phase-0 status | Where / disposition |
|---|---|---|
| **Append-only event log authority** | **SATISFIED** | `events.jsonl` is append-only; `append_event` never rewrites. The snapshot is a derived cache (see projection row). |
| **Projection rebuildability** | **SATISFIED (this slice)** | Previously the snapshot was only ever read directly (`load_project_state`) and the "rebuildable" test merely compared the snapshot to the last event. `rebuild_state` / `load_state` now replay the log into the canonical projection; tests prove the log — not the snapshot — is authoritative (tampered-snapshot test). |
| **State-transition legality** | **SATISFIED** | `validate_transition` + the `LINEAR_NEXT` edge map + the `QC_COMPLETED`-before-`EVIDENCE_SYNTHESIZED` guard. Well covered by `StateMachineTest`. |
| **Idempotent command / operation behavior** | **SATISFIED (ledgers); BOUNDED LIMITATION (event log)** | Execution ledgers dedup on stable id (`runs.py`). End-to-end resume is idempotent (`test_resume_is_idempotent`). The transition event log is **not** deduped: `event_id` includes `created_at`, so a re-issued transition would append a distinct row. This is acceptable in phase 0 (single-process CLI; resume short-circuits at terminal stages so no duplicate transition is emitted) but must be made explicit with an **idempotency key** when concurrency / retries arrive — deferred to WP-03b/DB work. |
| **Transaction / atomicity** | **PARTIAL — best-effort, single-writer** | Snapshot write is atomic (`tmp` + `replace`). But a transition does **two** writes (`_write_state` then `append_event`) that are not a single atomic unit; a crash between them can leave the snapshot ahead of the log. The projection is the mitigation: `rebuild_state` recovers the true state from the log regardless of a stale snapshot. True multi-write transactionality (snapshot+event+ledger as one commit) needs a transactional store and is **deferred**. |
| **Optimistic concurrency / multi-writer safety** | **DEFERRED** | JSONL has no write lock or version-CAS (ADR-0003 known limitation: single-process CLI is sufficient). Belongs to the PostgreSQL adapter. |
| **Outbox / broker / event dispatch** | **DEFERRED** | No outbox in phase 0. RESERVED behind `EventStorePort`; explicitly forbidden by this work order. |
| **PostgreSQL event store + migrations** | **DEFERRED** | RESERVED adapter; forbidden by this work order. |

---

## 3. Gap closed in this slice (narrow fix + tests)

**Gap:** ADR-0003 and `EventStorePort` both state the project state is a *rebuildable
projection* of the event log and declare a `load_state` operation, but `store.py`
had **no** projection-rebuild function and **no** `load_state`. The only reader,
`load_project_state`, trusts the JSON snapshot verbatim; the existing
`test_state_rebuildable_from_events` only checked that the snapshot's
`current_stage` equalled the last event's `next_stage` — it never reconstructed
state from the log, so a tampered or stale snapshot would have gone undetected and
the documented port surface was unmet.

**Fix (bounded to core event/state modules + tests):**
- `auto_bioinfo/core/store.py`: added `rebuild_state(project_dir)` (replays the
  append-only log into the canonical state projection, deterministically) and
  `load_state(project_dir)` (the `EventStorePort.load_state` authoritative read).
  No existing behavior changed; `load_project_state` and `transition_state` are
  untouched.
- `tests/test_state_machine.py`: added `ProjectionRebuildTest` —
  `test_rebuild_state_matches_snapshot`, `test_rebuild_state_recovers_full_stage_history`,
  `test_rebuild_state_is_deterministic`,
  `test_event_log_is_authoritative_over_tampered_snapshot` (proves the log, not the
  snapshot, is the source of truth), `test_rebuild_state_rejects_empty_log`, and
  `test_store_module_satisfies_event_store_port`.

This slice is **audit + narrow tests + minimal fix**. No runtime task execution,
formal evidence admission, report generation, bundle export, claim synthesis, or
alignment behavior was implemented or changed.

---

## 4. Proposed next slice — WP-03b

**Title:** Event-log idempotency key + transition/snapshot consistency hardening
(still phase-0, no DB).

**Intended files (tightly bounded):**
- `auto_bioinfo/core/events.py` — add an optional explicit `idempotency_key`
  (a.k.a. command id) to `build_event`, independent of `created_at`, so a
  re-issued logical event is identifiable without wall-clock coupling.
- `auto_bioinfo/core/store.py` — make `append_event` idempotent on
  `idempotency_key` when present (skip a duplicate logical event, mirroring
  `runs.py`); add a `verify_projection(project_dir)` helper that reports drift
  between the snapshot and `rebuild_state` (no auto-repair, just detection).
- `tests/test_state_machine.py` — tests for idempotent event re-append and for
  drift detection / projection-vs-snapshot consistency.

**Acceptance criteria:**
- Re-appending an event with the same `idempotency_key` does not add a second log
  line and returns the existing event.
- Events without an `idempotency_key` keep today's behavior (backward compatible).
- `verify_projection` returns an empty report for a healthy project and a precise
  mismatch list for a tampered snapshot.
- Full suite green; `make lint` / `make format-check` / `git diff --check` clean;
  required CI green.

**Forbidden scope for WP-03b (carry-over):** No PostgreSQL, migrations, outbox,
broker/queue, Docker/Compose, workflow/ruleset/secrets, dependency/lockfile/SBOM,
API layer, WP-04+, real data, external/paid services, public deploy/publish. No
runtime task execution, formal evidence admission, report generation, bundle
materialization/export, claim synthesis, or alignment-engine behavior. No
multi-writer locking / optimistic-concurrency (that travels with the DB adapter).

---

## 5. Deferred-to-later-WO register (do not implement in WP-03)

- PostgreSQL event store + migrations (RESERVED `EventStorePort` adapter).
- Outbox dispatcher / broker / queue.
- Optimistic concurrency / multi-writer locking.
- Single-commit transactionality across snapshot + event + ledger writes.
- Docker / Compose / container images (D-03, planned but deferred).

All of the above remain behind ports; the domain core does not change when they
land. WP-25 (observability) is noted as continuous from WP-03 in the architecture
baseline but is out of scope here.
