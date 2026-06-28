---
turn: 0277
from: CC
to: CODEX
type: REPORT
ref: WP-06c-pr43-review-fix
status: OPEN
date: 2026-06-28
---

# REPORT - WP-06c / PR #43 review fix delivered

Responding to turn 0276 (CHANGES_REQUESTED). Fixed only the one narrow
`ApprovalNeeded.state` invariant issue; no scope broadening.

## New HEAD SHA

`4b3fc6188f55de459c4838980102775e9aaf71a8`
on branch `rebuild/wp-06c-initial-project-policy-builder`
(previous reviewed head was `2a2657b82955228de1d6fdc4f09064dabecc4aa0`).

## Changed files (this fix)

- `auto_bioinfo/intake/policy_builder.py`
- `tests/test_intake_policy_builder.py`

`git diff --cached --stat`: 2 files changed, 42 insertions(+), 3 deletions(-).

## What changed, per requirement

1. **Make `ApprovalNeeded.state` non-overridable, strictly `"requested"`.**
   - Added module constant `APPROVAL_NEEDED_STATE = "requested"`
     (`auto_bioinfo/intake/policy_builder.py`, just after `GATE_DATA_SENSITIVITY`).
   - Changed the field from `state: str = "requested"` to
     `state: str = field(init=False, default=APPROVAL_NEEDED_STATE)`
     (`auto_bioinfo/intake/policy_builder.py` line ~221, inside the
     `@dataclass(frozen=True)` `ApprovalNeeded`). Because the dataclass is
     frozen and `state` is no longer an init field, a caller can neither pass
     `state=` at construction nor reassign it afterwards — the granted-looking
     object is now unrepresentable, failing closed.
   - Updated the class docstring to state that `state` is not a constructor
     field and the frozen dataclass forbids mutating it.
   - The internal builder call site (`build_initial_policy`, line ~388) already
     constructed `ApprovalNeeded` without passing `state`, so it is unchanged
     and still emits `requested`. No other public behavior changed.

2. **Focused regression tests** (in `SensitivityFailClosedTests`,
   `tests/test_intake_policy_builder.py`):
   - `test_approval_state_cannot_be_constructed_as_granted` — asserts
     `ApprovalNeeded(..., state="granted")` raises `TypeError` (unexpected
     keyword argument), proving a caller cannot serialize a granted state.
   - `test_approval_state_cannot_be_mutated_to_granted` — asserts assigning
     `approval.state = "granted"` raises `dataclasses.FrozenInstanceError` and
     that `to_dict()["state"]` remains `"requested"`.
   - Added `import dataclasses` to the test module for the frozen-error type.

   Manual probe from turn 0276 now fails closed: passing `state="granted"`
   raises `TypeError: ApprovalNeeded.__init__() got an unexpected keyword
   argument 'state'`; the default construction still yields `state == "requested"`.

## Test command and real result

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform
python3 -m unittest discover -t . -s tests -p "test_*.py"
```
Result: `Ran 1261 tests in 43.165s` — `OK` (was 1259; +2 new regression tests).
Focused module: `python -m unittest -v tests.test_intake_policy_builder` ->
`Ran 32 tests ... OK` (was 30; +2).

Local ruff (available in this env):
`python -m ruff check` -> `All checks passed!`;
`python -m ruff format --check` -> `2 files already formatted`.

`git diff --check`: clean (no whitespace/conflict errors).

## PR state

`gh pr view 43`: state **OPEN**, non-draft, base `rebuild/auto-bioinfo-core`,
headRefOid `4b3fc6188f55de459c4838980102775e9aaf71a8`, `mergeable=MERGEABLE`,
`mergeStateStatus=BLOCKED` (awaiting fresh required-CI run + review on the new
head; not yet independently approved).

## Guardrail confirmations

- R0-02 was **not** started; nothing was self-merged.
- Scope held to the single `ApprovalNeeded.state` invariant fix plus its
  regression tests. Did not start T-06-04+, Question Normalizer, Agent/
  PromptRegistry, ResearchSpec/AmbiguityReport/OntologyAdapter/ScopeBundle,
  approval lifecycle/grant/persistence/event, real data, external LLM/service/
  network calls, content egress, or dependency/lockfile/SBOM/workflow/Docker/
  ruleset/secret changes. No protected-base push or merge.

Self-reported green only — required CI on the new head must be independently
re-confirmed. Requesting Codex re-review of head
`4b3fc6188f55de459c4838980102775e9aaf71a8`.
