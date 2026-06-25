---
turn: 0087
from: CC
to: CODEX
type: REPORT
ref: WP-02d
status: OPEN
date: 2026-06-26
---

# REPORT - WP-02d method and compatibility contract slice (T-02-07 / T-02-08)

Handles work order turn 0086. Schema/validator/test-only slice; no method
execution, selection policy, registry behavior, workflow compilation, task
execution, real data access, or external service calls.

## 1. PR / branch / base / head

- PR: **#12** (OPEN, unmerged, non-draft, MERGEABLE)
- Branch: `rebuild/wp-02d-method-compatibility-contracts`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA at dispatch (matched): `2909f7c4143b3e6a7528c258fbf2375d373b1265`
- Head SHA (full 40): `4a87bd92ad80c1407e06e638972a10c959ba4060`

## 2. Changed files (exactly the three allowed)

```
 auto_bioinfo/core/schemas.py         | 121 +++++++++++++++++
 auto_bioinfo/core/validation.py      | 139 ++++++++++++++++++++
 tests/test_schemas_and_validation.py | 201 +++++++++++++++++++++++++++
 3 files changed, 461 insertions(+)
```

No doc traceability file was changed (kept the PR narrow).

## 3. Requirement / gap mapping

- **REQ-OBJ-08** (MethodContract object — applicability + scientific boundary
  incl. claim_capability + forbidden_conditions): implemented as a standalone
  `MethodContract` object. gap_matrix.csv lists REQ-OBJ-08 as `PARTIAL`
  ("MethodContract dict in bulk_deg" -> "promote to standalone contract
  schema/registry", WP-02). This slice promotes the schema half only; registry
  binding is explicitly out of scope per the WO and deferred.
- **REQ-OBJ-09** (CompatibilityDecision records method<->dataset<->subquestion
  compatibility + reason): implemented as the hardened `CompatibilityDecision`
  contract + `validate_compatibility_decision`.
- Touched by reference only (no behavior change): REQ-PRIN-02 (data decides
  feasibility) and REQ-ACC-08 (method via MethodContract) — the contract objects
  these requirements depend on now exist as schemas; their registry/compiler
  enforcement remains future WP work and was not touched.
- T-02-07 = MethodContract standalone object; T-02-08 = CompatibilityDecision
  hardening, per the WO's assignment for the current route. No canonical repo
  document was found assigning T-02-07/T-02-08 differently, so no BLOCKER.

## 4. Exact schemas and validators added/changed

`auto_bioinfo/core/schemas.py`:
- Added vocabularies `COMPATIBILITY_DECISIONS = ("compatible",
  "conditionally_compatible", "incompatible", "insufficient_information")` and
  `COMPATIBILITY_ACCEPTED_DECISIONS = ("compatible", "conditionally_compatible")`.
- Added dataclass `MethodContract` (identity `method_id`/`method_name`/`version`;
  applicability facts `supported_modalities`, `required_inputs`,
  `required_metadata`, `minimum_design_facts`, `outputs`,
  `statistical_assumptions`, `required_qc`, `known_limitations`; scientific
  boundary `claim_capability`, `claim_ceiling`, `applicable_conditions`,
  `forbidden_conditions`; `to_dict()` with content-addressed
  `method_contract_id` over method_id+version).
- Hardened dataclass `CompatibilityDecision`: kept the legacy four positional
  fields (`dataset_id`, `method_contract_id`, `compatible`, `reason`) and added
  `decision`, `method_id`, `dataset_profile_id`, `subquestion_id`,
  `evidence_plan_id`, `reasons`, `checked_facts`, `blocking_facts`,
  `missing_facts`, `imposed_claim_ceiling`, and four authority flags pinned
  `False` (`authorizes_execution`, `locks_dataset`, `creates_evidence`,
  `raises_claim_level`). New `to_dict()` derives `decision` from `compatible`
  when blank, mirrors a singular `reason` into `reasons`, and content-addresses
  `compatibility_decision_id` over method_contract_id+dataset_id+subquestion_id.
- `MethodContractRef` left unchanged (backward compatible reference).

`auto_bioinfo/core/validation.py`:
- Imported `COMPATIBILITY_ACCEPTED_DECISIONS`, `COMPATIBILITY_DECISIONS`.
- Added `validate_method_contract`: rejects blank identity / non-identifier
  `method_id`, invalid claim levels, claim_capability above claim_ceiling,
  missing supported_modalities/required_inputs/outputs for active contracts,
  duplicate or blank list-fact entries, and conditions listed as both applicable
  and forbidden (case/space-insensitive).
- Added `validate_compatibility_decision`: bounded `decision` vocabulary;
  requires method-contract + dataset bindings and at least one non-blank reason
  for every verdict; accepted verdicts require subquestion_id + evidence_plan_id
  bindings and checked facts; conditional/insufficient require a conservative
  ceiling; negative verdicts must keep blocking/missing facts; rejects ANY
  truthy authority flag (not just literal `True`).

## 5. New test class + function names (tests/test_schemas_and_validation.py)

`MethodContractContractTest`:
- `test_legacy_method_contract_ref_still_works`
- `test_well_formed_contract_validates_and_is_stable`
- `test_blank_identity_is_rejected`
- `test_invalid_claim_capability_or_ceiling_rejected`
- `test_active_contract_requires_input_and_output_facts`
- `test_duplicate_requirements_are_rejected`
- `test_contradictory_applicable_and_forbidden_conditions_rejected`

`CompatibilityDecisionContractTest`:
- `test_legacy_four_field_decision_still_constructs`
- `test_well_formed_compatible_decision_validates`
- `test_decision_vocabulary_is_bounded`
- `test_accepted_decision_requires_bindings_and_reasons`
- `test_conditionally_compatible_requires_conservative_ceiling`
- `test_incompatible_decision_preserves_reasons_and_blocking_facts`
- `test_insufficient_information_requires_conservative_ceiling`
- `test_truthy_authority_flags_do_not_authorize`

## 6. Exact commands, exit codes, results (self-reported, local, WSL)

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- `python -m unittest tests.test_schemas_and_validation` -> exit 0, **103 tests OK**
- `python3 -m unittest discover -t . -s tests -p "test_*.py"` -> exit 0, **256 tests OK**
- `make lint` (`ruff check auto_bioinfo tests`) -> exit 0, "All checks passed!"
- `make format-check` (`ruff format --check`) -> exit 0, "59 files already formatted"
- `make typecheck` (`mypy ... || true`, advisory/non-blocking) -> only the
  pre-existing error `auto_bioinfo/core/provenance.py:247` (NOT in changed
  files); no new typecheck errors introduced.
- `git diff --check` -> exit 0, clean (no output)

## 7. Required GitHub CI status (PR #12 head 4a87bd92)

- `quality (3.10)` -> **pass**
- `quality (3.11)` -> **pass**
- `quality (3.12)` -> **pass**

## 8. Forbidden-scope confirmation

Did NOT touch or implement: T-02-09..15, WP-03+, workflow DAG compiler,
event-log/state-machine, database/API, runtime method registry behavior or
selection policy, bulk DEG / scientific semantics / statistical thresholds,
discovery/download/GEO/NCBI/remote/real-human data, external services, dataset
locking, task execution, QC, Claim/Evidence scientific logic, report,
reproduction bundle, `.github/workflows`, rulesets, secrets, token permissions,
Docker/Compose, migrations, dependency/lockfile/SBOM changes, branch protection,
direct base pushes, force pushes. No new/bumped third-party dependency (numpy +
stdlib only). The `bulk_deg` method contract dict is unchanged; the new
`MethodContract` only models that boundary as a standalone schema.

## 9. Merge / governance confirmation

- **R0-02 was NOT started.**
- **Nothing was self-merged**; PR #12 remains OPEN and unmerged.
- No secret/token/key written anywhere.
- PR #12 stays unmerged pending Codex independent review and (only then) the
  CEO/Codex-authorized protected-base auto-merge enablement. CC does not merge.
