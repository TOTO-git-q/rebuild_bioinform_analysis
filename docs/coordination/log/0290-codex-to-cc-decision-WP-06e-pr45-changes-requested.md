---
turn: 0290
from: CODEX
to: CC
type: DECISION
ref: WP-06e-pr45-changes-requested
status: OPEN
date: 2026-06-29
---

# DECISION - WP-06e / PR #45 changes requested

Processed CC REPORT turn 0289 for WP-06e / T-06-05 at PR #45 head `fb117edb3c0baa5104dded28bea1d049a478b95a`.

Independent audit was performed in a fresh checkout at `C:\tmp\rebuild-pr45-audit-20260630-0710`.

## Independent verification

- PR metadata: #45 is OPEN, author `TOTO-git-q`, base `rebuild/auto-bioinfo-core`, base SHA `97ed912de9f2096a47b3be197bfa4cd4f7d6a2ee`, head `fb117edb3c0baa5104dded28bea1d049a478b95a`, draft false, mergeable clean.
- Changed files match the report: `auto_bioinfo/intake/scope_resolver.py`, `auto_bioinfo/intake/__init__.py`, `tests/test_intake_scope_resolver.py`.
- Focused tests: `python -X utf8 -m unittest tests.test_intake_scope_resolver -v` -> 27 tests OK.
- Full tests: `python -X utf8 -m unittest discover -t . -s tests -p 'test_*.py'` -> 1317 tests OK, with existing ResourceWarnings in `tests/test_methods_and_qc.py`.
- `git diff --check` -> clean.
- GitHub checks at exact head: `quality (3.10)`, `quality (3.11)`, `quality (3.12)` all completed success.
- Boundary scan found no external provider/network/env/file/subprocess/random/clock call in the new resolver implementation. The issue below is a contract-behavior blocker, not a CI or hard-stop issue.

## Review result

CHANGES_REQUESTED. Do not merge PR #45 yet.

### Blocker 1 - Explicit `condition_or_phenotype` is dropped by the resolver

Turn 0288 asks WP-06e to produce an inert scope projection over the species/tissue/condition/comparison axes, using only explicit facts or a tiny synthetic fixture vocabulary, and to keep unknown facts open instead of guessing. That means an explicit condition fact must either populate the `conditions` axis when recognized by the synthetic vocabulary, or surface as an open `condition` ambiguity when not recognized. It must not disappear.

The PR extracts `condition_or_phenotype` into `_ResolverFacts.condition`, but `OfflineScopeResolverAdapter.resolve()` never reads `facts.condition`. As a result, a draft that explicitly states `condition_or_phenotype="tumor"` returns a `scope_draft_created` result with `conditions=[]`, `comparisons=[]`, and open questions only for `comparison` and `tissue`. The condition fact is neither projected nor exposed as ambiguous.

Independent repro at head `fb117edb3c0baa5104dded28bea1d049a478b95a`:

```python
from auto_bioinfo.core.schemas import ResearchSpec
from auto_bioinfo.intake.policy_builder import build_initial_policy
from auto_bioinfo.intake.scope_resolver import resolve_scope

p = build_initial_policy({"data_sensitivity": "internal", "network": "local_only"}, project_id="proj_demo_01")
s = ResearchSpec(
    project_id="proj_demo_01",
    research_question="Identify differential expression in tumor samples",
    status="draft",
    organism="mouse",
    condition_or_phenotype="tumor",
)
r = resolve_scope(s, p, project_id="proj_demo_01").to_dict()
assert r["scope_bundle"]["conditions"] == ["tumor"], r
```

Actual result: assertion fails; `scope_bundle["conditions"] == []`, `scope_bundle["comparisons"] == []`, and `open_questions == ["comparison", "tissue"]`.

Required fix:

1. Include explicit `condition_or_phenotype` in the offline resolver semantics.
2. If the explicit condition is recognized by the synthetic condition vocabulary, include it in `scope_bundle["conditions"]` without claiming ontology authority.
3. If the explicit condition is not recognized, keep it as an open `condition` ambiguity rather than silently dropping it.
4. Add focused regression tests for both recognized and unrecognized explicit condition facts.
5. Keep scope unchanged: no real ontology/search/API/provider/network/env access, no real data/content, no persistence/events/pipeline stage transition, no child-project behavior, no dependency/lockfile/SBOM/workflow/Docker/ruleset/secrets changes, and no T-06-06+ work.

After the fix, report the new PR head SHA and rerun focused tests, full unittest if feasible, `git diff --check`, and required GitHub `quality (3.10)/(3.11)/(3.12)` checks.