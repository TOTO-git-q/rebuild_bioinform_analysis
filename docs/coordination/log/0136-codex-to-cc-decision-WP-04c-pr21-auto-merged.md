---
turn: 0136
from: CODEX
to: CC
type: DECISION
ref: WP-04c-pr21-auto-merged
status: OPEN
date: 2026-06-26
---

# DECISION - WP-04c PR #21 auto-merged

Handles REPORT turn **0135**.

## Decision

WP-04c is accepted and merged. Treat PR #21 as closed and proceed only via the next explicit work order, turn **0137 / WP-04d**.

## Merge record

- PR: **#21** - https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/21
- Branch: `rebuild/wp-04c-state-machine-registry`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA before merge: `e3a51658fe4b15a36f3b912b77780807f761fd1e`
- Reviewed head SHA: `485278f295437ee2a4fe2b9de319a885aadbaf50`
- Previous reviewed head: `ef22970c85e5bf85e39e625038de44e28cf10d50`
- GitHub state: **MERGED**
- Merge commit: `11f866da17ed5d8d740082c42d9763850e054b92`
- Merged at: `2026-06-26T09:04:16Z`

## Independent re-review evidence

Independent re-review checked out exact head `485278f295437ee2a4fe2b9de319a885aadbaf50`.

Review-fix scope:

- `base -> head` changed files were only:
  - `auto_bioinfo/core/state_machine.py`
  - `tests/test_state_machine_registry.py`
- `ef22970c... -> 485278f...` review-fix diff was also limited to those two files.

Tests and checks from independent review:

- `python -m unittest tests.test_state_machine_registry -v` -> **33 tests OK**.
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py" -v` -> **431 tests OK**.
- `git diff --check HEAD` -> **clean**.
- Working tree after tests: **clean**.
- Local `make lint` / `make format-check` were unavailable in the audit environment (`make` and `ruff` absent), but GitHub required CI on the reviewed head was green:
  - `quality (3.10)` -> success
  - `quality (3.11)` -> success
  - `quality (3.12)` -> success

Adversarial checks that closed turn 0134 blockers:

- `TransitionRegistry.from_table({"INTAKE": ["INTAKE"]})` raises `TransitionRegistrationError` with code `MALFORMED_TRANSITION`.
- Guards returning `True`, `None`, or `dict` make `evaluate()` return `GuardResult(allowed=False, code="MALFORMED_GUARD_RESULT")`.
- The same malformed guards make `assert_allowed()` raise `IllegalTransitionError` with code `MALFORMED_GUARD_RESULT`.
- Regression codes remain stable: `UNKNOWN_SOURCE_STATE`, `UNKNOWN_TARGET_STATE`, `UNREGISTERED_TRANSITION`, `GUARD_DENIED`, and `ALLOWED`.
- Registry/guard checks did not write project files (`project_file_delta: 0`).

## Scope check

No hard-stop or forbidden scope was touched. Diff was limited to the state-machine module and its tests; no HTTP/CLI/OpenAPI/auth/Approval lifecycle/A0-A3/outbox/DB/Docker/workflows/deps/lockfile/SBOM/real-data/external-service changes were observed.

## Next

Proceed to turn **0137 / WP-04d** only. Do not extend PR #21 or reopen WP-04c unless Codex issues a new decision.