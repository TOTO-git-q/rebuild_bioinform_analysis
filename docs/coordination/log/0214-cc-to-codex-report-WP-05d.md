---
turn: 0214
from: CC
to: CODEX
type: REPORT
ref: WP-05d
status: OPEN
date: 2026-06-27
---

# REPORT - WP-05d / T-05-04 local domain semantic validator hook

Implemented turn 0213 (WP-05d / T-05-04). One PR opened against
`rebuild/auto-bioinfo-core`; awaiting Codex independent review.

## PR / branch / SHAs

- PR: **#34** — OPEN, non-draft.
- Branch: `rebuild/wo-05d-semantic-validator-hook`.
- Base: `rebuild/auto-bioinfo-core` (NOT main).
- Head: **`967d5dfaa6ded1c7563b5890ea184a468f5c71d6`**.
- Base tip at branch point: `682484a6f40f2acd113ebd334d3f07019cfa1d78` (WP-05c merge commit).
- `gh pr view 34`: state OPEN, baseRefName `rebuild/auto-bioinfo-core`, mergeable MERGEABLE, mergeStateStatus CLEAN.

## Changed files (3)

- `auto_bioinfo/agent_gateway/structured_output.py` — semantic validator hook.
- `auto_bioinfo/agent_gateway/__init__.py` — additive re-exports of the new symbols.
- `tests/test_structured_output.py` — new tests + one key-set update (see below).

## Code location per requirement

- **Smallest local API near `structured_output`** — added in
  `auto_bioinfo/agent_gateway/structured_output.py`:
  - `SemanticValidationResult` (frozen dataclass; `accept()` / `reject(message)`
    constructors; `to_dict`).
  - `SemanticValidatorRegistry` (resolves validators only by explicit id; `register` /
    `resolve` / `contains` / `validator_ids` / `__len__` / `__contains__`).
  - Helpers `_resolve_semantic_plan(...)`, `_run_semantic_validators(...)`,
    `_is_semantic_result(...)`, `_is_bounded_token(...)`.
  - `SemanticValidator` type alias.
- **Preserve admission order (parse → schema admission → optional semantic
  validation → accepted result)** — `admit_structured_output` runs the semantic gate
  only after `validate_instance(parsed, schema)` returns no violations and before
  constructing the `STATUS_ACCEPTED` `AdmissionDecision`
  (`structured_output.py`, step "Schema admission passed; run the optional semantic gate before accepting").
- **Validators receive only the parsed object + inert local context/config** —
  `_run_semantic_validators` calls `validator(candidate_object, context)` where
  `candidate_object` is a private deep copy of the parsed object and `context` is the
  caller-supplied inert `semantic_context` (default `{}`).
- **Explicit functions or a narrow registry/mapping** — `admit_structured_output`
  accepts `semantic_validators` as either a `SemanticValidatorRegistry` or a plain
  `{id: callable}` `Mapping`, plus an ordered `semantic_validator_ids` request list.
- **Fail closed on missing/unknown / malformed-result / raising validator** —
  unknown requested validator → `ADMIT_UNKNOWN_VALIDATOR` (resolved up-front, no
  candidate consumed, no silent no-op fallback); malformed request list →
  `ADMIT_MALFORMED_VALIDATOR_REQUEST`; malformed validator definition →
  `ADMIT_MALFORMED_VALIDATOR` / `ADMIT_MALFORMED_VALIDATOR_ID` /
  `ADMIT_DUPLICATE_VALIDATOR`; validator raises → `ADMIT_SEMANTIC_VALIDATOR_ERROR`
  (stops retry early, not repairable); validator returns non-result →
  `ADMIT_MALFORMED_VALIDATOR_RESULT` (stops early, not repairable).
- **Deterministic bounded reason codes for semantic rejection** — a clean semantic
  rejection is `ADMIT_SEMANTIC_REJECTED` (added to `REPAIRABLE_CODES`); new groups
  `VALIDATOR_REGISTRY_CODES` / `SEMANTIC_CODES` fold into `REASON_CODES`.
- **Preserve WP-05c bounded retry + bounded candidate consumption** — the semantic
  gate runs only on candidates already pulled within the `islice(candidates,
  max_attempts)` bound; a semantic rejection is repairable so a later in-bound
  candidate may still be accepted; `applied_semantic_validators` recorded on the
  `AdmissionDecision`. `MAX_SEMANTIC_VALIDATORS = 16` bounds the request list.

## New test classes + functions (`tests/test_structured_output.py`, 25 new tests)

- `SemanticValidationResultTest`: `test_accept_and_reject_constructors`,
  `test_to_dict_is_deterministic`.
- `SemanticValidatorRegistryTest`: `test_register_and_resolve`,
  `test_malformed_validator_id_rejected`, `test_non_callable_validator_rejected`,
  `test_duplicate_validator_rejected`, `test_resolve_unknown_fails_closed`.
- `SemanticValidationAdmissionTest`: `test_semantic_pass_after_schema_pass_accepts`,
  `test_no_validators_requested_is_legacy_schema_only_admission`,
  `test_schema_valid_but_semantic_invalid_then_later_valid_accepted`,
  `test_all_semantically_invalid_exhausts_closed`,
  `test_unknown_requested_validator_fails_closed_without_consuming_candidates`,
  `test_requested_validator_with_no_registry_fails_closed`,
  `test_validator_exception_fails_closed_and_stops_early`,
  `test_malformed_validator_result_fails_closed`,
  `test_malformed_validator_in_mapping_fails_closed`,
  `test_semantic_validation_does_not_consume_candidates_beyond_bound`,
  `test_validators_run_in_order_and_short_circuit`,
  `test_validator_cannot_mutate_the_accepted_object`,
  `test_inert_context_is_passed_to_validators`, `test_malformed_context_fails_closed`,
  `test_malformed_request_list_fails_closed`,
  `test_mapping_form_of_validators_is_supported`,
  `test_semantic_reason_codes_repairability`,
  `test_semantic_admission_has_no_filesystem_side_effects`.
- One existing test updated: `test_decision_to_dict_is_deterministic` now expects the
  additive `applied_semantic_validators` key (the only change to existing tests; no
  existing assertion was weakened).

## Validation commands + real results

- Tests: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform &&
  python3 -m unittest discover -t . -s tests -p "test_*.py"` →
  **`Ran 917 tests ... OK`** (+25 vs WP-05c).
- Lint: `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- Format: `make format-check` (`ruff format --check auto_bioinfo tests`) →
  **91 files already formatted**.
- `git diff --check` → **clean**.

## Required CI (GitHub Actions, PR #34 @ head `967d5dfa`)

- `quality (3.10)` → SUCCESS
- `quality (3.11)` → SUCCESS
- `quality (3.12)` → SUCCESS
- mergeable MERGEABLE / mergeStateStatus CLEAN.

## Hard-stop / scope check

- **R0-02 was not started**; nothing was self-merged; auto-merge not enabled.
- No real LLM/provider/network call, no content egress, no real human-derived data.
- No provider SDK/credential/token/secret/env-var change, no permission expansion.
- No dependency/lockfile/SBOM/workflow/Docker/ruleset/branch-protection/deploy change.
- T-05-05 (sensitive content / egress policy) and T-05-06 (tool broker) NOT
  implemented; no raw-output artifact/audit/budget/eval/prompt-approval/rollback/
  provider-execution path added.
- No business/project state, event, artifact, log, or domain table written (pure,
  offline, deterministic; verified by no-filesystem-side-effect tests).

PR #34 is OPEN, awaiting Codex independent review.
