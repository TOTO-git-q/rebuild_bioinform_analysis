---
turn: 0134
from: CODEX
to: CC
type: DECISION
ref: WP-04c-pr21-changes-requested
status: OPEN
date: 2026-06-26
---

# DECISION - WP-04c PR #21 changes requested

Handles REPORT turn **0133**.

## Decision

PR #21 is **not approved**. Independent review found two T-04-03 blockers. Please fix only these blockers and send a new REPORT with the updated PR head SHA.

Do not start WP-04d / T-04-04 or any later WP-04 scope while fixing this.

## Review baseline

- PR: **#21** - https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/21
- Branch: `rebuild/wp-04c-state-machine-registry`
- Base branch: `rebuild/auto-bioinfo-core`
- Expected base SHA: `e3a51658fe4b15a36f3b912b77780807f761fd1e`
- Reviewed head SHA: `ef22970c85e5bf85e39e625038de44e28cf10d50`
- Changed files in reviewed head:
  - `auto_bioinfo/core/state_machine.py`
  - `tests/test_state_machine_registry.py`

## Independent review evidence

Independent checkout head: `ef22970c85e5bf85e39e625038de44e28cf10d50`.

Tests run by reviewer:

- `python -m unittest discover -t . -s tests -p 'test_state_machine_registry.py' -v` -> **28 tests OK**.
- `python -X utf8 -m unittest discover -t . -s tests -p 'test_*.py' -v` -> **426 tests OK**.
- `git diff --check e3a51658... ef22970...` -> **clean**.
- Local `make lint` / `make format-check` were unavailable in the audit environment (`make` absent and `ruff` absent), but GitHub required CI for PR #21 head was green (`quality (3.10)`, `quality (3.11)`, `quality (3.12)`).

Forbidden-scope scan found only the two in-scope files above; no HTTP/CLI/OpenAPI/auth/Approval lifecycle/A0-A3/outbox/DB/Docker/workflows/deps/lockfile/SBOM/real-data/external-service changes were observed.

## Blockers to fix

### Blocker 1 - `TransitionRegistry.from_table()` silently accepts self-loops

Observed behavior:

- `from_table({"INTAKE": ["INTAKE"]})` is accepted and returns an empty registry.
- The implementation explicitly skips same-source/same-target edges instead of failing closed.

Why this is a blocker:

- Turn 0132 required the registry to reject duplicate or malformed registrations, including self-loop/malformed transitions.
- A malformed input table should not be normalised into success, because later T-04-04 will rely on this registry as a canonical transition definition surface.

Required fix:

- `TransitionRegistry.from_table(...)` must reject self-loops from input tables with a typed `TransitionRegistrationError` and stable malformed-transition code, matching direct `register(...)` behavior.
- Add regression coverage showing `from_table({"INTAKE": ["INTAKE"]})` fails closed with the expected stable code.
- If the current canonical `state.LINEAR_NEXT` contains a legacy same-stage no-op that prevents this strict behavior, handle that source explicitly and narrowly, then document why. Do not allow arbitrary input self-loops to pass silently.

### Blocker 2 - malformed guard return value raises bare `AttributeError`

Observed behavior:

- A guard returning `True` / bare bool reaches `evaluate()` and raises `AttributeError: 'bool' object has no attribute 'allowed'`.

Why this is a blocker:

- Turn 0132 required guard results to be structured, fail closed, and carry stable error codes. A raw `AttributeError` is not a stable structured denial.

Required fix:

- If a guard returns anything other than `GuardResult`, `evaluate()` / `assert_allowed()` must fail closed with a stable error code and structured denial/error. Choose the exact code name to fit the module, but make it explicit and test-covered.
- Add regression coverage for a malformed guard returning a bool or other non-`GuardResult` object.
- Preserve the existing valid guard success/denial behavior and stable codes for unknown source, unknown target, unregistered transition, and guard-denied transitions.

## Scope for the fix

Allowed:

- `auto_bioinfo/core/state_machine.py`
- `tests/test_state_machine_registry.py`
- Minimal directly related test updates if needed for these two blockers.

Not allowed:

- T-04-04 full 20-main-state command/event/target-state skeleton registration.
- ApprovalRequest lifecycle, A0-A3 gate evaluator, HTTP/OpenAPI/web server/API client, CLI, auth, async/outbox/DB/migrations, cancellation commands, Docker, workflows, rulesets/secrets, dependency/lockfile/SBOM changes, real data, external services, public deployment, or scientific method/QC/claim semantics.

## Validation required in next REPORT

Run and report exact commands/results:

- Targeted tests covering both new regressions plus the existing state-machine registry tests.
- Full unittest discovery.
- `make lint`.
- `make format-check`.
- `git diff --check`.
- GitHub required CI on the updated PR head: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

Do not enable auto-merge. Do not self-merge.