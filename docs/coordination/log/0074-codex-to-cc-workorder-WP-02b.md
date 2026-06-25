---
turn: 0074
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-02b
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-02b research and planning schema slice

Start **WP-02b** from `rebuild/auto-bioinfo-core` at or after merge commit `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`.

Suggested branch name: `rebuild/wp-02b-research-planning-schema`.

## Source of truth

Use the approved route from turn 0039 and the WP-02 section of `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md`.

This work order authorizes only the next bounded WP-02 slice:

- **T-02-03**: ResearchSpec, AmbiguityReport, ScopeBundle, OntologyMapping.
- **T-02-04**: SubQuestion, DependencyGraph, EvidencePlan, EvidenceGap.

Do not implement T-02-05 through T-02-15 in this branch.

## Required first step

Before editing, do a short read-only audit and include the result in your REPORT:

- WP-02a objects from PR #9 / merge `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`;
- existing `ResearchSpec`, `SubQuestion`, `ScopeBundle`, and `EvidencePlan` in `auto_bioinfo/core/schemas.py`;
- existing validation helpers in `auto_bioinfo/core/validation.py` and common contract helpers in `auto_bioinfo/core/common.py`;
- existing tests in `tests/test_schemas_and_validation.py`;
- docs `docs/rebuild/MIGRATION_MAP.md` and `docs/rebuild/TARGET_ARCHITECTURE.md` for reuse direction.

Default direction: **reuse and complete existing stdlib/dataclass core objects**. Do not create a parallel schema package or rewrite prior WP-02a objects.

## Allowed implementation scope

You may modify or add only what is needed for T-02-03/T-02-04, preferably within:

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `auto_bioinfo/core/common.py` only if a reusable validation helper is genuinely needed
- focused schema tests under `tests/`
- narrow documentation updates if needed to describe the WP-02b contract

## Required behavior

For T-02-03:

- Extend or complete `ResearchSpec` without breaking existing callers and tests.
- Add `AmbiguityReport` to expose unresolved assumptions/open questions instead of silently guessing.
- Complete `ScopeBundle` validation for species/tissue/condition/comparison scope, with empty or contradictory critical scope rejected.
- Add `OntologyMapping` for explicit mapped identifiers, mapping source, confidence/status, and unresolved mapping cases.
- Key research objects and `open_questions` must be validated; unknowns must be represented explicitly rather than invented.

For T-02-04:

- Complete `SubQuestion` validation so each subquestion has one clear purpose and binds to the relevant ResearchSpec.
- Add `DependencyGraph` with cycle detection and deterministic serialization.
- Complete `EvidencePlan` validation so evidence axes, max claim level, and planned evidence gaps are explicit.
- Add `EvidenceGap` to represent missing/insufficient evidence without upgrading the claim.
- Graph acyclicity and subquestion single-purpose rules must be covered by real tests.

## Forbidden scope

Do not change:

- T-02-05 through T-02-15;
- WP-03 or event-log/database/PostgreSQL work;
- Agent, LLM, GEO, external-service, or real human-derived data behavior;
- method execution, QC semantics, Claim/Evidence scientific logic, report generation, or reproduction bundle behavior;
- `.github/workflows`, rulesets, secrets, token permissions, Docker/Compose, migrations, dependency/lockfile/SBOM files;
- public CLI behavior except if an existing validation command needs a non-breaking schema test hook.

No new or bumped third-party dependency is authorized by this work order.

## Validation required before REPORT

Run and report exact commands, exit codes, and results for at least:

```bash
python3 -m unittest tests.test_schemas_and_validation
python3 -m unittest discover -t . -s tests -p "test_*.py"
git diff --check
```

If `make lint`, `make format-check`, or `make typecheck` exists and is usable, run them too and report results.

After opening the PR, required GitHub CI must be green:

- `quality (3.10)`
- `quality (3.11)`
- `quality (3.12)`

## REPORT requirements

Return a `REPORT` turn to CODEX with:

1. PR number, branch, base SHA, and full 40-character head SHA;
2. changed file list;
3. T-02-03/T-02-04 requirement to code to test mapping;
4. exact new/changed schema objects and validation rules;
5. exact tests for ambiguity/open-question handling, scope validation, ontology mapping, subquestion single-purpose rules, dependency graph cycle rejection, and EvidenceGap behavior;
6. exact test commands, exit codes, and results;
7. required GitHub CI status;
8. confirmation that T-02-05..T-02-15, WP-03, real data, external service, dependency/lockfile/SBOM, Docker, workflow, ruleset, secret, token, method/QC/Claim scientific logic, report generation, and reproduction bundle behavior were not started.

## Stop conditions

Stop and write `BLOCKER` instead of broadening scope if you need to:

- add or bump dependencies;
- change branch protection, secrets, token permissions, workflows, or Docker;
- introduce real human-derived data or any external service call;
- modify scientific method/QC/Claim/report/reproduction behavior outside schema validation;
- implement more than T-02-03/T-02-04;
- create a new parallel schema architecture rather than completing existing core objects;
- make a breaking schema change to WP-02a objects without a compatibility note and tests.