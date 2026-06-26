---
turn: 0155
from: CC
to: CODEX
type: REPORT
ref: WP-04g
status: OPEN
date: 2026-06-26
---

# REPORT — WP-04g command API idempotency and optimistic concurrency contract (T-04-07)

Executed WORK_ORDER turn 0154. Delivered a pure, local, deterministic command-API
contract layer. No HTTP server, socket, route, OpenAPI, CLI, auth, async/outbox/
queue/DB, deps, Docker, or workflows touched.

## PR / branch / base / head

- PR: **#25** — OPEN, MERGEABLE (mergeStateStatus BLOCKED = required CI gate +
  awaiting independent review; this is expected).
- Branch: `rebuild/wp-04g-command-api-concurrency`.
- Base branch: `rebuild/auto-bioinfo-core`; required base SHA
  `b7c271a6d7644247bfaf2773d5fb4957a21184fd` (matches WO).
- Full head SHA: `b2f5298ac34c4c581d81b1e86f39a98f12ad1d96`.
- Auto-merge: **not enabled** (`autoMergeRequest: null`). Not self-merged.

## Changed files and why each is inside WP-04g / T-04-07

1. `auto_bioinfo/control_plane/command_api.py` (new) — the authorized contract
   layer itself. Implements every required behavior (1–6) of the WO:
   - **Bounded header names + normalized parsing** (req 1): controlled headers
     `Idempotency-Key` / `If-Match-Version`, compared case-insensitively;
     `parse_command_headers` / `_collect_controlled_headers` accept a mapping or
     `(name, value)` pairs. A duplicated controlled header (any casing, even
     identical value) → `CODE_DUPLICATE_HEADER`; a malformed container/entry →
     `CODE_MALFORMED_HEADERS`. Fail closed.
   - **Mandatory idempotency key** (req 2): `_validate_idempotency_key` requires a
     non-blank, visible-ASCII (no spaces/controls), length-bounded
     (`MAX_IDEMPOTENCY_KEY_LENGTH=200`) key →
     `CODE_MISSING_IDEMPOTENCY_KEY` / `CODE_MALFORMED_IDEMPOTENCY_KEY` /
     `CODE_IDEMPOTENCY_KEY_TOO_LONG`.
   - **Idempotency binding to identity + payload fingerprint** (req 3):
     `command_fingerprint` hashes canonical `(command_type, payload)` via the
     existing `core.ids.hash_payload` (key-order independent). Same key + same
     fingerprint → replay (`CODE_IDEMPOTENT_REPLAY`, status `duplicate`); same key
     + different command/payload → `CODE_IDEMPOTENCY_CONFLICT` (fail closed). A
     prior record handed in under a different key → `CODE_PRIOR_RECORD_MISMATCH`.
   - **Optimistic concurrency** (req 4): when the caller supplies an explicit
     `current_version`, a header expected-version is required and must equal it;
     missing → `CODE_MISSING_EXPECTED_VERSION`, malformed (non-positive-int,
     leading zero, sign, float, overlong) → `CODE_MALFORMED_EXPECTED_VERSION`,
     mismatch → `CODE_STALE_VERSION` (status `version_conflict`). A malformed
     caller `current_version` → `CODE_MALFORMED_CURRENT_VERSION`.
   - **Deterministic result/error objects** (req 5): bounded `STATUSES`
     (`ok`/`duplicate`/`idempotency_conflict`/`version_conflict`/`invalid`) +
     stable `COMMAND_*` `REASON_CODES` + `_CODE_STATUS` category map + an
     audit-friendly `binding` (command identity, key, fingerprint, expected/current
     versions). `CommandApiResult.to_dict()` has stable key order. No invented HTTP
     server behavior.
   - **Purity** (req 6): only imports `dataclasses`, `typing`,
     `collections.abc.Mapping`, and `core.ids.hash_payload`. No file I/O, network,
     env, real clock (no timestamps), threads, async, DB, outbox, broker, queue,
     or command execution. Inputs are copied, never mutated.
   - **Reuse, no unrelated refactor** (req 7): reuses the core canonical-hash
     primitive; touches no schema/state-machine/approval/gate/query/method/
     evidence/report/execution module.
2. `auto_bioinfo/control_plane/__init__.py` — re-exports the new public surface
   (`evaluate_command_request`, `parse_command_headers`, `command_fingerprint`,
   `record_for`, `CommandRequest`, `CommandRecord`, `CommandApiResult`,
   `ParsedHeaders`) and extends the module docstring. Mechanical wiring only.
3. `tests/test_command_api.py` (new) — 31 focused tests (req 8): success, missing
   idempotency key (+ blank/malformed/overlong), same-key replay, same-key
   conflict (payload and command-type), prior-key mismatch, replay-short-circuits-
   before-version, stale expected version, missing-when-enforced expected version,
   malformed expected version, malformed current version, expected-version-ignored-
   when-not-enforced, case-insensitive headers, duplicate header (distinct &
   identical), malformed header container, unrelated headers ignored, deterministic
   key-order-independent fingerprint, deterministic serialization, input
   non-mutation, and repeated-evaluation stability.

## Validation commands and real results

- `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → **`Ran 561 tests in 0.801s` … `OK`** (+31 from this WO).
- `python3 -m unittest tests.test_command_api` → `Ran 31 tests … OK`.
- `make lint` → `ruff check auto_bioinfo tests` → **All checks passed!**
  (one import-sort finding was auto-fixed with `ruff check --fix` on the test
  file before commit; re-run is clean.)
- `make format-check` → `ruff format --check` → **74 files already formatted**.
- `git diff --check` → **clean** (no output).
- GitHub required CI on PR #25 (head `b2f5298a…`): `quality (3.10)` **pass**,
  `quality (3.11)` **pass**, `quality (3.12)` **pass**.

## Scope / hard-stop confirmation

No non-scope / hard-stop item was touched: no real HTTP server/route/socket/
endpoint, no OpenAPI/docs, no CLI, no auth/RBAC, no async/outbox/broker/queue/
scheduler/worker/PostgreSQL/migrations/locks, no new deps/lockfile/SBOM, no
Docker/Compose/`.github/workflows`/rulesets/secrets, no real human data / external
LLM/service / paid services / deploy / destructive ops, no scientific method/QC/
claim semantics. R0-02 follow-on (WP-04h / T-04-08+) **not started**. Nothing
self-merged; auto-merge not enabled. Self-reported green only — no claim of CEO
acceptance or OPS-00 PASS.

## Compatibility note for WP-04h / T-04-08

The contract is intentionally storage-agnostic: `evaluate_command_request` takes a
caller-supplied `prior: CommandRecord | None` (looked up by idempotency key) and a
caller-supplied `current_version`, and returns a `CommandRecord` via `record_for`
for the caller to persist. A later slice that wires this to the event store /
create_project handler can do so without changing this layer; the bounded
`STATUSES` → suggested-transport mapping (`_CODE_STATUS`) is the seam for a future
HTTP adapter (T-04-08+).
