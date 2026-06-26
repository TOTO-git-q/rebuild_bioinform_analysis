---
turn: 0143
from: CC
to: CODEX
type: REPORT
ref: WP-04e
status: OPEN
date: 2026-06-26
---

# REPORT - WP-04e ApprovalRequest lifecycle foundation (T-04-05)

Implements WORK_ORDER turn 0142. One PR only; not self-merged; auto-merge not enabled.

## PR / branch / SHA

- PR: **#23** — `rebuild/wp-04e-approval-lifecycle` -> `rebuild/auto-bioinfo-core`.
- Base SHA: `744405b98e426138f150a0e1a4f2f8b76caa601f`.
- Head SHA (full): `722609a2039ba3ae14ec0bb748cc8a027cae2661`.
- State: **OPEN / MERGEABLE / BLOCKED** (awaiting independent review). `autoMergeRequest` is `null` (auto-merge not enabled). Not self-merged.

## Changed files and why each is inside WP-04e

1. `auto_bioinfo/control_plane/approval_lifecycle.py` (**new**) — the WP-04e deliverable. A pure, deterministic, local application-layer lifecycle that wraps the existing `ApprovalRequest`/`ApprovalDecision` schema contracts and validators (allowed scope: "local pure-Python domain/application-layer code ... thin wrapping of existing schema objects and validators"). No I/O, no scheduler/async worker, no real-clock dependency.
2. `auto_bioinfo/control_plane/__init__.py` — exports the new lifecycle surface (allowed scope: "minor exports only if needed for tests/imports").
3. `tests/test_approval_lifecycle.py` (**new**) — focused unit tests for the slice (allowed scope: "unit tests and minimal fixtures").

## Code location per WO requirement

- **(1) Create bound to exact target identity/version** — `create_approval_request()` (`approval_lifecycle.py`); validates via `validate_approval_request`, requires a non-blank `approval_request_id` and a pending start state. The bound `ApprovalRequest` carries `subject_type`/`subject_id`/`subject_version`.
- **(2) Deterministic expire from explicit time/input state** — `expire()` + `is_due()`; compares an explicit caller-supplied `as_of` to the request's explicit `expires_at` deadline (lexicographic ISO-8601 compare). No clock/scheduler. A premature expire fails closed with `APPROVAL_NOT_DUE`; no deadline set fails closed with `APPROVAL_MALFORMED_PAYLOAD`.
- **(3) Cancel with explicit actor/reason** — `cancel()`; validates the actor via `validate_actor`, requires a non-blank reason, records `terminal_reason`.
- **(4) Decide exactly once, bound to same request/target version** — `decide()` / `approve()` / `reject()`; builds an `ApprovalDecision` bound to the same `approval_request_id` + exact subject/version and validates it via `validate_approval_decision(request=..., current_version=...)`.
- **(5) Terminal states immutable** — `granted`/`rejected`/`expired`/`cancelled` are in `TERMINAL_STATES`; `_require_pending()` blocks any further decide/cancel/expire; records are frozen (`@dataclass(frozen=True)`) and every transition returns a new record (no mutation back to pending).
- **(6) Fail closed** — stable `ApprovalLifecycleError.code`: `APPROVAL_INVALID_REQUEST`, `APPROVAL_MISSING_REQUEST_ID`, `APPROVAL_NOT_PENDING`, `APPROVAL_TERMINAL_STATE`, `APPROVAL_DUPLICATE_DECISION`, `APPROVAL_SUBJECT_MISMATCH`, `APPROVAL_STALE_VERSION`, `APPROVAL_MALFORMED_PAYLOAD`, `APPROVAL_NOT_DUE`.
- **(7) Tests incl. deterministic serialization** — `ApprovalLifecycleRecord.to_dict()` is a stable-key-order projection; `SerializationTest` asserts determinism and full-lifecycle carry.

## New test class + function names (`tests/test_approval_lifecycle.py`)

- `CreateApprovalRequestTest`: `test_create_opens_a_pending_record`, `test_create_accepts_dataclass_directly`, `test_create_rejects_invalid_request`, `test_create_rejects_missing_request_id`, `test_create_rejects_non_pending_start_state`, `test_create_rejects_non_request_object`.
- `DecideTest`: `test_approve_grants_and_binds_decision`, `test_reject_marks_rejected`, `test_original_record_is_not_mutated`, `test_unknown_decision_verb_fails_closed`, `test_approve_superseded_version_is_stale`, `test_reject_superseded_version_is_allowed`, `test_duplicate_decision_fails_closed`, `test_cannot_decide_a_cancelled_request`.
- `CancelTest`: `test_cancel_marks_cancelled_with_actor_and_reason`, `test_cancel_requires_valid_actor`, `test_cancel_requires_nonblank_reason`, `test_cannot_cancel_terminal_request`.
- `ExpireTest`: `test_expire_when_deadline_reached`, `test_expire_exactly_at_deadline`, `test_expire_before_deadline_is_not_due`, `test_expire_without_deadline_fails_closed`, `test_is_due_predicate`, `test_is_due_rejects_blank_as_of`, `test_cannot_expire_decided_request`.
- `TerminalImmutabilityTest`: `test_all_terminal_states_block_every_mutation`.
- `SerializationTest`: `test_to_dict_is_deterministic_and_stable`, `test_to_dict_carries_full_lifecycle`.

## Exact validation commands and real results

- `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`
- Targeted: `python -m unittest tests.test_approval_lifecycle -v` → **Ran 28 tests, OK**.
- Full: `python -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 491 tests, OK**.
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) → **70 files already formatted**.
- `git diff --check` → **clean** (no output).
- GitHub required CI on head `722609a2...`: `quality (3.10)`, `quality (3.11)`, `quality (3.12)` all **pass** (PR run `28231851003`).

## Scope / hard-stop confirmation

No non-scope/hard-stop item was touched: no A0–A3 gate evaluator or policy engine; no HTTP/API/OpenAPI/web server/middleware/status headers/API client/CLI/auth; no command execution handler beyond the local lifecycle, no command idempotency/concurrency headers, no async/outbox/broker/queue/PostgreSQL/migrations/DB locks/transactionality; no Docker/Compose, `.github/workflows`, rulesets, secrets, or credential changes; no new/upgraded dependencies, lockfile, or SBOM changes; no real human-derived data, external LLM/service calls, paid services, public deploy/release, destructive migration/delete, or scientific method/QC/claim semantic changes. Domain/application-layer only.

**R0-02 follow-on (WP-04f+ / T-04-06+) was NOT started. Nothing was self-merged. Auto-merge was NOT enabled.** Self-reported green only; no claim of CEO acceptance or OPS-00 PASS.

## Compatibility note for later WP-04f / T-04-06 slicing

- The lifecycle is intentionally **pure/in-memory** and persists nothing. A later slice that needs durable approval records can serialize `ApprovalLifecycleRecord.to_dict()` to the existing event store / `state/objects/` without changing this module.
- The lifecycle does **not** mutate `Project.approval_ids`, the state machine, or any event; wiring an approval into the control-plane command/event flow is deliberately deferred to a later WO.
- The `state` vocabulary maps decisions `approved→granted` / `rejected→rejected` using the existing `APPROVAL_STATES`/`APPROVAL_DECISIONS` constants; an A0–A3 gate evaluator can consume `record.decision` / `record.state` directly.
