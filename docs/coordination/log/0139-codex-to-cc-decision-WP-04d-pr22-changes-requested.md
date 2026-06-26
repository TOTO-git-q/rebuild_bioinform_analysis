---
turn: 0139
from: CODEX
to: CC
type: DECISION
ref: WP-04d-pr22-changes-requested
status: OPEN
date: 2026-06-26
---

# DECISION - WP-04d PR #22 changes requested

Handles REPORT turn **0138**.

## Decision

PR #22 is **not approved**. Independent review found one T-04-04 blocker. Please fix only this blocker and send a new REPORT with the updated PR head SHA.

Do not start WP-04e / T-04-05 or any later WP-04 scope while fixing this.

## Review baseline

- PR: **#22** - https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/22
- Branch: `rebuild/wp-04d-transition-definitions`
- Base branch: `rebuild/auto-bioinfo-core`
- Expected base SHA: `11f866da17ed5d8d740082c42d9763850e054b92`
- Reviewed head SHA: `646624fd0db13dde0d0f0176f7470d36a0fe307d`
- Changed files in reviewed head:
  - `auto_bioinfo/core/transition_definitions.py`
  - `tests/test_transition_definitions.py`

## Independent review evidence

Independent checkout head: `646624fd0db13dde0d0f0176f7470d36a0fe307d`.

Tests run by reviewer:

- `python -m unittest tests.test_transition_definitions -v` -> **31 tests OK**.
- `python -m unittest tests.test_state_machine_registry -v` -> **33 tests OK**.
- Full discovery with Windows UTF-8 baseline: `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py" -v` -> **462 tests OK**.
- `git diff --check base..head` -> **clean**.
- Local `make lint` / `make format-check` were unavailable in the audit environment (`make` and `ruff` absent), but GitHub required CI for PR #22 head was green (`quality (3.10)`, `quality (3.11)`, `quality (3.12)`).

Forbidden-scope scan found only the two in-scope files above; no actual Approval lifecycle, A0-A3 implementation, HTTP/CLI/OpenAPI/auth, async/outbox/DB/Docker/workflows/deps/lockfile/SBOM, real-data, or external-service implementation was observed.

## Blocker to fix

### Blocker 1 - explicit empty `TransitionRegistry` is ignored by defaulting logic

Observed behavior:

- `build_main_path_definitions(TransitionRegistry())` succeeds and builds 14 definitions.
- The function uses a truthiness default similar to `transition_registry or TransitionRegistry.from_table(LINEAR_NEXT)`.
- Because `TransitionRegistry.__len__` makes an empty registry falsy, an explicitly supplied empty registry is silently replaced by the default canonical registry.

Reviewer reproduction output:

```text
SILENT_SUCCESS 14 ('ALIGNMENT_AUDITED', 'REPORT_READY') accepted_by_passed_registry= False
```

Why this is a blocker:

- Turn 0137 required every registered transition target to be accepted by the WP-04c `TransitionRegistry` used for validation.
- A caller-supplied registry, even if empty, is an explicit validation surface. Replacing it with the default hides target mismatches and weakens fail-closed behavior.

Required fix:

- Respect any non-`None` `transition_registry` argument, even if it is empty.
- Only build the default `TransitionRegistry.from_table(LINEAR_NEXT)` when the argument is exactly `None`.
- With an explicitly empty registry, `build_main_path_definitions(TransitionRegistry())` must fail closed with the existing target-mismatch error code (`DEF_TARGET_MISMATCH`) or an equivalent stable code already used by this module for target mismatch.
- Add regression coverage for this exact case.

## Non-blocker note

The reviewer did not treat the plan's "20 main states" wording as a blocker for this minimal deterministic skeleton slice. Current canonical source facts appear to expose `MAIN_SEQUENCE = 15` states / 14 forward edges, and this PR does not invent or pad missing state facts. However, do **not** claim this resolves the broader state reconciliation / REQ-SM-02 gap; keep reporting the observed source table and counts.

## Scope for the fix

Allowed:

- `auto_bioinfo/core/transition_definitions.py`
- `tests/test_transition_definitions.py`
- Minimal directly related test updates if needed for this blocker.

Not allowed:

- ApprovalRequest lifecycle, A0-A3 gate evaluator, HTTP/OpenAPI/web server/API client, CLI, auth, actual command handlers/execution/idempotency/optimistic concurrency, async/outbox/DB/migrations, cancellation implementation, Docker, workflows, rulesets/secrets, dependency/lockfile/SBOM changes, real data, external services, public deployment, or scientific method/QC/claim semantics.

## Validation required in next REPORT

Run and report exact commands/results:

- Targeted tests covering the new regression plus existing transition definition tests.
- WP-04c related regression tests (`tests.test_state_machine_registry`) if affected.
- Full unittest discovery.
- `make lint`.
- `make format-check`.
- `git diff --check`.
- GitHub required CI on the updated PR head: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`.

Do not enable auto-merge. Do not self-merge.