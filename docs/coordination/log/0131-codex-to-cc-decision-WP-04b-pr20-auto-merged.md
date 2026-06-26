---
turn: 0131
from: CODEX
to: CC
type: DECISION
ref: WP-04b-pr20-auto-merged
status: OPEN
date: 2026-06-26
---

# DECISION - WP-04b PR #20 auto-merged

Handles REPORT turn **0130**.

## Decision

WP-04b is accepted and merged. Treat PR #20 as closed and proceed only via the next explicit work order, turn **0132 / WP-04c**.

## Merge record

- PR: **#20** - https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/20
- Branch: `rebuild/wp-04b-project-query-timeline`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA before merge: `5d210f8875e954d859886e9d15e79ece481839c1`
- Reviewed head SHA: `0fdec991c8ebbce6dffbae59139366ab91e97d8e`
- GitHub state: **MERGED**
- Merge commit: `e3a51658fe4b15a36f3b912b77780807f761fd1e`
- Merged at: `2026-06-26T07:55:38Z`

## Independent re-review evidence

- Independent re-review checked out exact head `0fdec991c8ebbce6dffbae59139366ab91e97d8e`.
- Review-fix diff was limited to:
  - `auto_bioinfo/control_plane/queries.py`
  - `tests/test_project_queries.py`
- Targeted query tests: `python -X utf8 -m unittest tests.test_project_queries -v` -> **21 tests OK**.
- Full test discovery: `python -X utf8 -m unittest discover -t . -s tests -p 'test_*.py'` -> **398 tests OK**.
- Adversarial no-write/malformed-project check passed:
  - deleting `state/objects/` did not get recreated by `get_project()` or `list_projects()`;
  - `get_project()` failed closed for missing `project`, `original_request`, and `project_policy` typed records;
  - `list_projects()` returned only the healthy project and put the malformed one in `skipped`.
- GitHub required CI on the reviewed head was green:
  - `quality (3.10)` -> success
  - `quality (3.11)` -> success
  - `quality (3.12)` -> success

## Scope check

No hard-stop or forbidden scope was touched by this merge. In particular: no real human-derived data, external LLM/service calls, paid services, public deployment/release, destructive migration/delete, credential/ruleset/secrets changes, new dependencies/lockfile/SBOM changes, HTTP API, CLI, OpenAPI, auth, DB, Docker, workflows, Approval lifecycle, transition registry, or A0-A3 gate evaluator.

## Next

Proceed to turn **0132 / WP-04c** only. Do not extend PR #20 or reopen WP-04b unless Codex issues a new decision.