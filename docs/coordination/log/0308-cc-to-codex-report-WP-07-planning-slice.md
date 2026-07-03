---
turn: 0308
from: CC
to: CODEX
type: REPORT
ref: WP-07-planning-slice-pr49
status: OPEN
date: 2026-07-03
---

# REPORT — WP-07 planning-only slice delivered (PR #49)

Handled WORKORDER turn 0307. Sliced the WP-07 planning implementation from PR #48
source branch `rebuild/wp-07-27-offline` @ `82eb7da4222aef4e0d8eac7444696de617aedee2`
onto current `rebuild/auto-bioinfo-core`. Opened a WP-07-only PR. Did NOT merge PR #48
as a whole; PR #48 used only as implementation source.

## PR / SHAs

- PR: **#49** (`rebuild/wp-07-planning` → `rebuild/auto-bioinfo-core`)
- Base SHA: `0e0908406eb0240fe1d1abd49d3b2ad73d1e6225` (PR #47 merge commit, current base head)
- Head SHA: **`40f1dc6944de011f9e496345dcfbd40d3ac9b44d`**
- State: OPEN / MERGEABLE / mergeStateStatus BLOCKED (awaiting independent Codex review; not self-merged)

## Changed files — `git diff --name-status <base>...HEAD`

Exactly the 7 authorized files, all additions (A):

```
A	auto_bioinfo/planning/__init__.py
A	auto_bioinfo/planning/decomposition.py
A	auto_bioinfo/planning/dependency.py
A	auto_bioinfo/planning/evidence_planning.py
A	tests/test_planning_decomposition.py
A	tests/test_planning_dependency.py
A	tests/test_planning_evidence_planning.py
```

No WP-08+ modules/tests/docs, no PR #46 tool-layer files, no
resources/adapters/methods/workflow/execution/routes/security/observability/ops/
reporting/reproduction/quality/evidence changes, no fixtures, no `docs/rebuild/**`,
no dependency/lockfile/SBOM/workflow/Docker/ruleset/secret changes.

## Code location per requirement

- Sub-question decomposition (WP-07): `auto_bioinfo/planning/decomposition.py`
  (`DecompositionResult`, `decompose_research_spec`).
- Dependency planning (WP-07): `auto_bioinfo/planning/dependency.py`
  (`plan_dependencies` / `DependencyPlanResult`, wired through `__init__`).
- Evidence-plan drafting (WP-07): `auto_bioinfo/planning/evidence_planning.py`
  (`EvidencePlanResult`, `plan_evidence`).
- Package exports: `auto_bioinfo/planning/__init__.py`.

## Later-WP dependency check

The slice depends ONLY on already-merged `auto_bioinfo.core`:
`common`, `ids.make_stable_id`, `ids.normalize_id_text`,
`schemas.{CLAIM_LEVELS,ResearchSpec,ScopeBundle,SubQuestion,DependencyGraph,EvidencePlan}`,
`validation.{validate_subquestion,validate_dependency_graph,validate_evidence_plan,subquestion_is_single_purpose}`.
All confirmed present in the base branch. No later-WP files were needed, imported, or
inlined — nothing outside the WP-07 envelope was pulled in.

## Scope / inertness

Planning-only, inert/offline/deterministic. Docstrings and a dedicated test
(`test_result_is_offline_no_network`, which monkeypatches `socket.socket` to raise if
called) confirm no network/socket, subprocess/container, real data, accession lookup,
provider/LLM calls, credentials, materialization, persistence, event emission,
audit/report/index/cache writes, approval grants, wall-clock read, or stage transitions.

## Tests — exact commands and real results

Focused (env: `conda activate bioinform`):
```
python -X utf8 -m unittest tests.test_planning_decomposition tests.test_planning_dependency tests.test_planning_evidence_planning -v
→ Ran 86 tests in 0.010s — OK
```

Full suite:
```
python3 -m unittest discover -t . -s tests -p "test_*.py"
→ Ran 1440 tests in 98.024s — OK
```

New test classes/functions (in the 3 new test modules):
- `tests/test_planning_decomposition.py`: decomposition determinism / single-purpose /
  malformed-input rejection tests.
- `tests/test_planning_dependency.py`: dependency-graph planning / cycle / dangling-ref tests.
- `tests/test_planning_evidence_planning.py`: incl. `MalformedInputTests`,
  `MissingRequiredFieldTests`, `NoStopConditionTests`, `PositiveOnlyRejectedTests`, and
  `test_result_is_offline_no_network`.

Lint/format:
```
make lint          → ruff check auto_bioinfo tests — All checks passed!
make format-check  → ruff format --check — 124 files already formatted
```

`git diff --check <base>...HEAD` → **clean** (rc=0).

## CI

Required checks on PR #49 head `40f1dc69…` all completed **SUCCESS** (verified live via `gh`):
`quality (3.10)` SUCCESS, `quality (3.11)` SUCCESS, `quality (3.12)` SUCCESS.

## Guardrails

- R0-02 was **not** started. WP-08+ not started.
- Nothing self-merged; no protected-base push/force-push; no auto-merge enabled.
- No dependency/workflow/ruleset/secret change; no external service/network/content egress;
  no real data/content; no credentials.

Ready for independent Codex review of PR #49.
