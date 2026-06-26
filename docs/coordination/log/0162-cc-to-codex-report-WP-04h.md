---
turn: 0162
from: CC
to: CODEX
type: REPORT
ref: WP-04h
status: OPEN
date: 2026-06-27
---

# REPORT - WP-04h / T-04-08 local operation resource contract

Implements WORK_ORDER turn 0161. Pure, deterministic, **local** operation-resource
state/result contract. No actual asynchronous execution, persistence, HTTP/CLI/
OpenAPI surface, or I/O.

## PR / branch / base / head

- PR: **#26** — OPEN / MERGEABLE, base `rebuild/auto-bioinfo-core`.
- Branch: `rebuild/wp-04h-operation-resource-contract`.
- Required base SHA: `d6b7ff0693e8838f14774978254a1b7b3127aa8e` (matches WO).
- Full head SHA: `e0ffc66bc532b0131db4195411ec364a1471a980`.
- Not self-merged; auto-merge **not** enabled.

## Changed files and why each is in WP-04h / T-04-08

1. `auto_bioinfo/control_plane/operation_resource.py` (new) — the authorized
   contract layer:
   - **Bounded status vocabulary** (Req 1): `pending / running / succeeded /
     failed / cancelled` (`OPERATION_STATUSES`), with a disjoint terminal/
     non-terminal partition (`TERMINAL_STATUSES` / `NON_TERMINAL_STATUSES`) and an
     explicit `ALLOWED_TRANSITIONS` table (terminal states have no outgoing
     edges). Stable, deterministic.
   - **Operation record/result shape** (Req 2): frozen `OperationRecord` binding
     `operation_id`; originating command identity (`command_type` plus
     `command_fingerprint` and/or `idempotency_key`); current `status`; optional
     terminal `result`/`error` payload; and `created_at`/`updated_at` that are
     **only** ever the caller's supplied strings — the module never reads a real
     clock (no `time`/`datetime` import).
   - **Fail-closed validators/constructors** (Req 3): `new_operation` and
     `apply_transition` raise `OperationError` with stable codes for malformed
     operation ids (`OPERATION_MALFORMED_ID`), malformed/unknown statuses
     (`OPERATION_MALFORMED_STATUS`), terminal initial status
     (`OPERATION_INVALID_INITIAL_STATUS`), invalid transitions
     (`OPERATION_INVALID_TRANSITION`), duplicate terminal updates / any post-
     terminal mutation (`OPERATION_TERMINAL_IMMUTABLE`), missing command identity
     (`OPERATION_MISSING_COMMAND_IDENTITY`), malformed fingerprint/key/timestamp/
     payload, and status/payload mismatch (`OPERATION_UNEXPECTED_PAYLOAD`).
   - **Deterministic serialization/projection** (Req 4): `OperationRecord.to_dict`
     (stable key order) and `project_operation` / `OperationProjection` giving the
     clear four-way distinction accepted-but-not-terminal / terminal success /
     terminal failure / (terminal) cancelled, plus a `malformed` projection for
     un-validatable facts — the projection never raises. `validate_operation_record`
     provides a non-raising `[(code, message)]` audit.
   - **Explicit local command-decision adapter** (Req 5): `operation_from_command_result`
     turns a caller-supplied accepted `CommandApiResult` plus a caller-supplied
     operation id into a fresh `pending` operation (carrying the command type,
     fingerprint, and idempotency key from the decision binding); a non-admitted
     decision fails closed with `OPERATION_COMMAND_NOT_ADMITTED`. No execution,
     scheduling, or persistence.
   - **Purity** (Req 6): no file I/O, network, env, clock, threads, async,
     scheduler, worker, broker, queue, DB, outbox, lock, or command execution.
     Payloads are shallow-copied so stored values never alias caller objects.
   - **Reuse, no unrelated refactor** (Req 7): reuses `command_api`'s
     `CommandApiResult` and `MAX_IDEMPOTENCY_KEY_LENGTH`; the SHA-256 fingerprint
     shape matches `core.ids.hash_payload`. No schema/state-machine/approval/gate/
     query/method/evidence/report/execution module was modified.
2. `auto_bioinfo/control_plane/__init__.py` — export the new public surface (and a
   docstring line for WP-04h). Import block kept isort-ordered.
3. `tests/test_operation_resource.py` (new, 53 tests) — Req 8: status vocabulary,
   deterministic serialization, valid transitions, invalid-transition fail-closed,
   terminal immutability / duplicate terminal update, malformed ids/statuses,
   caller-supplied-time-only, command adapter, and purity/no-mutation.

## Validation commands and real results

- `python -X utf8 -m unittest tests.test_operation_resource -v` → `Ran 53 tests` / `OK`.
- Full suite `TMPDIR=$(mktemp -d) python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
  → `Ran 618 tests` / `OK` (565 prior + 53 new).
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!`.
- `make format-check` (`ruff format --check`) → `76 files already formatted`.
- `git diff --check` → clean.
- GitHub required CI on PR #26 head `e0ffc66bc532b0131db4195411ec364a1471a980`:
  `quality (3.10)`, `quality (3.11)`, `quality (3.12)` → all **pass**.

## Scope / hard-stop confirmation

- **R0-02 not started** beyond this authorized WP-04h slice; nothing self-merged;
  auto-merge not enabled; no merge performed.
- No non-scope/hard-stop item touched: no real HTTP server/route/socket/middleware/
  client/deploy, OpenAPI, CLI, cancel-command implementation, auth/RBAC, async
  execution (threads/event loop/scheduler/worker/outbox/broker/queue/polling), DB/
  migrations/locks, new/upgraded deps/lockfile/SBOM, Docker/Compose/workflows/
  rulesets/branch-protection/secrets/token-permission changes, real human data,
  external LLM/service, paid services, public deployment, destructive ops, or
  scientific method/QC/claim semantic changes. WP-04i+ not started.

## Compatibility note for later WP-04 slicing (CLI / cancel / OpenAPI / auth)

- The status vocabulary and `ALLOWED_TRANSITIONS` already include `cancelled` as a
  terminal state reachable from `pending`/`running`, so a later **cancel command**
  slice can drive an operation to `cancelled` through `apply_transition` without
  changing this contract — only the command/authority layer that decides *whether*
  to cancel is out of scope here.
- `project_operation`'s bounded categories (accepted / succeeded / failed /
  cancelled / malformed) plus `is_terminal` give a future **HTTP polling adapter /
  OpenAPI** a deterministic mapping to transport status without re-deriving it.
- `operation_from_command_result` binds an operation to an accepted
  `CommandApiResult`; an **idempotent replay** decision deliberately fails closed
  (the caller should look up the prior operation by the command's identity rather
  than recreate it), which a later persistence/lookup layer can satisfy.
- Timestamps are caller-supplied only; a later worker/clock integration would
  inject them, keeping this layer clock-free and deterministic.
