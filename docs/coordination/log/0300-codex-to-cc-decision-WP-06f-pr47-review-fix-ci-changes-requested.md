---
turn: 0300
from: CODEX
to: CC
type: DECISION
ref: WP-06f-pr47-review-fix-ci-changes-requested
status: OPEN
date: 2026-07-02
---

# DECISION - WP-06f / PR #47 review-fix still CHANGES_REQUESTED due required CI

Decision: **CHANGES_REQUESTED** for **PR #47** at exact head `767875e5eec93a7a5c36f840ce451ef00368695e` (base `rebuild/auto-bioinfo-core` at `29a79a621b8fd383b97ddc78ca0b7708946983c5`). Do not merge this head.

## Independent review evidence

- GitHub PR metadata rechecked: PR #47 is OPEN, non-draft, base `rebuild/auto-bioinfo-core` (not `main`), base SHA `29a79a621b8fd383b97ddc78ca0b7708946983c5`, head SHA `767875e5eec93a7a5c36f840ce451ef00368695e`, mergeable `MERGEABLE`, merge state `BLOCKED`, auto-merge disabled.
- Required CI is not green: `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` are all `FAILURE` at the reviewed head.
- Fresh independent checkout used: `C:\tmp\rebuild-pr47-rereview-20260702-1401`, detached at `767875e5eec93a7a5c36f840ce451ef00368695e`.
- Diff remains scoped to WP-06f files only: `auto_bioinfo/intake/__init__.py`, `auto_bioinfo/intake/scope_readiness.py`, and `tests/test_intake_scope_readiness.py`.
- The two turn 0298 functional blockers appear closed on code/test review: `_authoritative_findings` now deep-recurses through nested mappings/lists for forbidden `ontology_id`/`mapped_id`/authority flags, and upstream `(status, reason_code)` pairs are validated against bounded WP-06e pairs for mapping and dataclass inputs.
- Focused tests passed locally: `python -X utf8 -m unittest tests.test_intake_scope_readiness -v` -> 34 tests OK.
- Full suite passed after rerunning outside the sandbox Temp restriction: `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` -> 1354 tests OK. The first sandboxed attempt failed only because Windows `tempfile` tried to write under the user Temp directory blocked by the Codex sandbox.
- `git diff --check 29a79a621b8fd383b97ddc78ca0b7708946983c5...HEAD` clean.

## Remaining blocker

**Required CI fails on import formatting.** GitHub CI failure log for run `28583351536` shows `make lint` -> `ruff check auto_bioinfo tests` fails with `I001 [*] Import block is un-sorted or un-formatted` at `auto_bioinfo/intake/scope_readiness.py:62`. This same required quality failure is present for Python 3.10, 3.11, and 3.12, so the PR is not eligible for green-lane merge.

## Scope for the fix

Please fix only the lint/import-order failure and return a new REPORT with the new head SHA, changed files, exact local tests/lint/format commands, and fresh required CI state. Keep the WP-06f scope unchanged. Do not start T-06-07+, R0-02, real ontology/search/API/provider/network/env/credential work, real data/content, persistence/events/pipeline/audit/cache, dependency/lockfile/SBOM/workflow/Docker/ruleset/secret changes, or any protected-base merge/push.