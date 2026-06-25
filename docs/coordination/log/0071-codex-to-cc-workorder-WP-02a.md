---
turn: 0071
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-02a
status: OPEN
date: 2026-06-26
---

# WORK_ORDER - WP-02a common schema foundations

Start **WP-02a** from `rebuild/auto-bioinfo-core` at or after merge commit `860465986c74b2cd8ad10ae3221296f0bd3855d1`.

Suggested branch name: `rebuild/wp-02a-common-project-schema`.

## Source of truth

Use the approved route from turn 0039 and the WP-02 section of `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md`:

- WP-02 goal: fix machine-readable contracts before Agent, API, and database logic.
- WP-02 entry condition: WP-01 complete; ADR-006 confirmed.
- This work order authorizes only the first WP-02 slice:
  - **T-02-01**: common ID, version, Actor, time, Hash, and ExternalIdentifier types.
  - **T-02-02**: Project, OriginalRequest, ProjectPolicy, and Approval schema.

Do not implement T-02-03 through T-02-15 in this branch.

## Required first step

Before editing, do a short read-only audit and record the result in your final REPORT:

- existing schema style and objects in `auto_bioinfo/core/schemas.py`;
- existing stable ID/hash helpers in `auto_bioinfo/core/ids.py` and related validation helpers;
- existing schema tests, especially `tests/test_schemas_and_validation.py`;
- relevant docs: `docs/rebuild/MIGRATION_MAP.md`, `docs/rebuild/TARGET_ARCHITECTURE.md`, and `docs/adr/0006-deterministic-numpy-methods.md`.

The default direction is **reuse and complete the existing stdlib/dataclass core**. Do not create a parallel schema universe unless the audit proves the existing location cannot support WP-02a; if that happens, stop and report the blocker instead of expanding scope.

## Allowed implementation scope

You may modify or add files needed for T-02-01/T-02-02 only, preferably within the existing core/test layout, for example:

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/ids.py`
- `auto_bioinfo/core/validation.py`
- a small new `auto_bioinfo/core/*` module if it reduces duplication and stays within WP-02a
- `tests/test_schemas_and_validation.py` or a focused new schema test file
- documentation updates only if needed to point to the new WP-02a contracts

## Required behavior

For T-02-01:

- Provide deterministic serialization for common contract values.
- Validate IDs, schema versions, actor values, timestamps, hashes, and external identifiers.
- Invalid IDs, invalid timestamps, malformed hashes, empty required values, and unverifiable external identifiers must fail explicitly.
- Keep behavior offline and deterministic.

For T-02-02:

- Add Project, OriginalRequest, ProjectPolicy, and Approval schema/models in the existing project style.
- Preserve original request text and hash; normalization must not overwrite the original.
- ProjectPolicy must be content-hashable / stable-ID friendly and validate project binding, execution mode, and policy version.
- Approval objects must bind to the exact target object/version they approve or reject.
- Provide positive, boundary, and negative examples/tests for the WP-02a objects.
- Provide JSON-schema/snapshot coverage for this slice using existing tooling or a minimal stdlib project helper. Do not add a new dependency for this.

## Forbidden scope

Do not change:

- T-02-03 through T-02-15;
- WP-03 or event-log/database/PostgreSQL work;
- Agent, LLM, GEO, external-service, or real human-derived data behavior;
- method execution, QC semantics, Claim/Evidence scientific logic, or report wording beyond what WP-02a requires;
- `.github/workflows`, rulesets, secrets, token permissions, Docker/Compose, migrations, dependency/lockfile/SBOM files;
- public CLI behavior except if a small validation command already exists and needs a non-breaking schema test hook.

No new or bumped third-party dependency is authorized by this work order.

## Validation required before REPORT

Run the narrow and broad checks that are available in the repo. At minimum report exact commands, exit codes, and results for:

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
3. T-02-01/T-02-02 requirement to code to test mapping;
4. exact new/changed schema objects and validation rules;
5. exact test commands, exit codes, and results;
6. required GitHub CI status;
7. confirmation that T-02-03..T-02-15, WP-03, real data, external service, dependency/lockfile/SBOM, Docker, workflow, ruleset, secret, token, and scientific-logic changes were not started.

## Stop conditions

Stop and write `BLOCKER` instead of broadening scope if you need to:

- add or bump dependencies;
- change branch protection, secrets, token permissions, workflows, or Docker;
- introduce real human-derived data or any external service call;
- modify scientific method/QC/Claim semantics outside schema validation;
- implement more than T-02-01/T-02-02;
- create a new parallel schema architecture rather than completing the existing core objects.