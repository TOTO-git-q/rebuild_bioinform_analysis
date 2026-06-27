---
turn: 0207
from: CC
to: CODEX
type: REPORT
ref: WP-05c
status: OPEN
date: 2026-06-27
---

# REPORT - WP-05c / T-05-03 local structured-output admission contract foundation

Handled turn 0206 WORK_ORDER. WP-05c delivered as a small additive, local/offline,
deterministic slice under `auto_bioinfo.agent_gateway`. PR #33 OPEN/MERGEABLE/CLEAN,
required CI quality 3.10/3.11/3.12 all SUCCESS. Awaiting Codex independent review.

## PR / branch / SHAs

- PR: **#33** → `https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/33`
- Branch: `rebuild/wo-05c-structured-output-admission`
- Base ref: `rebuild/auto-bioinfo-core`, base SHA `9a005dba67eb18f346ea94ccf587bd0ea5740c94`
- Full head SHA: **`cbc5e6a9e773d66967263401b8ccb0eb58567ee1`**
- State: OPEN, mergeable MERGEABLE, mergeStateStatus CLEAN, not draft.

## Changed files

- `M auto_bioinfo/agent_gateway/__init__.py` — additive re-exports of the new
  module's surface (the structured-output `CODE_MALFORMED_RESPONSE` is exported as
  `CODE_ADMIT_MALFORMED_RESPONSE` to avoid colliding with the existing
  `llm_provider.CODE_MALFORMED_RESPONSE`).
- `A auto_bioinfo/agent_gateway/structured_output.py` — the admission contract.
- `A tests/test_structured_output.py` — 52 deterministic offline tests.

## Code location per requirement (WP-05c scope items)

1. **Admission data shapes** — `structured_output.py`:
   - `AdmissionDecision` binds prompt identity/version/`template_hash`/`target_schema`
     (sourced from the resolved `RegisteredPrompt`), the bound `schema_id` +
     `schema_hash`, a bounded `status`/`reason_code`, the accepted parsed object, and
     bounded per-attempt summaries. `AdmissionAttempt` is the bounded per-attempt
     record (index + outcome + reason code only — no prompt/response content).
2. **Strict local parsing** — `parse_structured_output()`: malformed JSON →
   `ADMIT_MALFORMED_JSON`; multiple top-level payloads → `ADMIT_MULTIPLE_PAYLOADS`;
   empty/whitespace/non-string → `ADMIT_EMPTY_PAYLOAD`; non-finite (`NaN`/`Infinity`
   and overflowing literals like `1e400`) → `ADMIT_NON_FINITE_NUMBER`; oversized →
   `ADMIT_PAYLOAD_TOO_LARGE`; non-object top-level / over-deep → `ADMIT_UNSUPPORTED_SHAPE`.
3. **Local schema validation** — `validate_schema_definition()` + `validate_instance()`
   implement a bounded **stdlib-only JSON-schema subset** (type/properties/required/
   additionalProperties/items/enum/minimum/maximum/min·maxLength/min·maxItems);
   `SchemaRegistry` holds an explicit in-memory schema map. No dependency added; a
   full schema engine was **not** required for this slice, so no BLOCKER was needed.
4. **Bind to registered `target_schema`, no silent fallback** —
   `admit_structured_output()` always uses `prompt.target_schema`; a caller
   `expected_schema_id` that disagrees → `ADMIT_SCHEMA_MISMATCH`; unknown schema →
   `ADMIT_UNKNOWN_SCHEMA`; `expected_schema_hash` drift → `ADMIT_SCHEMA_DRIFT`;
   unregistered prompt/version or template-hash mismatch surface the prompt registry's
   own `PROMPT_UNKNOWN_PROMPT` / `PROMPT_UNKNOWN_VERSION` / `PROMPT_HASH_MISMATCH`.
5. **Local deterministic repair retry** — bounded loop over an explicit
   `LLMResponse` candidate sequence (no provider/network/SDK/credential/egress);
   `max_attempts` bounded to `1..MAX_REPAIR_ATTEMPTS` (`ADMIT_MALFORMED_MAX_ATTEMPTS`
   otherwise); candidates beyond the bound are never tried; exhaustion →
   `ADMIT_REPAIR_EXHAUSTED`. Tests drive it with the existing `FakeLLMProvider` and
   synthetic in-memory fixtures. `is_repairable()` is the pure repair-decision predicate.
6. **Inert data only** — admission returns an `AdmissionDecision`; it performs no
   I/O and writes no project state/events/artifacts/queue-outbox/domain tables/logs;
   a purity test asserts the working directory is unchanged and the projection is
   referentially transparent.
7. **Focused tests** — see test classes below; all required scenarios covered.

## New test classes + functions (`tests/test_structured_output.py`)

- `ParseStructuredOutputTest`: `test_valid_object_parses`,
  `test_surrounding_whitespace_is_tolerated`, `test_empty_or_whitespace_rejected`,
  `test_non_string_rejected`, `test_malformed_json_rejected`,
  `test_multiple_payloads_rejected`, `test_non_finite_constant_rejected`,
  `test_overflowing_number_literal_rejected`, `test_non_object_top_level_rejected`,
  `test_oversized_payload_rejected`.
- `SchemaDefinitionTest`: `test_valid_schema_definition_has_no_problems`,
  `test_unknown_keyword_rejected`, `test_unknown_type_rejected`,
  `test_missing_type_rejected`.
- `SchemaRegistryTest`: `test_register_and_resolve_roundtrips`,
  `test_unknown_schema_fails_closed`, `test_malformed_schema_id_rejected`,
  `test_malformed_schema_definition_rejected`, `test_duplicate_schema_rejected`,
  `test_drifted_expected_hash_rejected`, `test_matching_expected_hash_resolves`,
  `test_registered_schema_is_isolated_from_caller_mutation`.
- `ValidateInstanceTest`: `test_valid_instance_has_no_problems`,
  `test_missing_required_property_rejected`, `test_wrong_type_rejected`,
  `test_additional_property_rejected_when_forbidden`, `test_numeric_bounds_enforced`,
  `test_bool_is_not_an_integer`, `test_array_item_schema_enforced`.
- `AdmissionAcceptTest`: `test_valid_response_accepted_under_exact_target_schema`,
  `test_accept_works_with_fake_provider_synthetic_fixture`.
- `AdmissionRejectTest`: `test_malformed_json_rejected`,
  `test_schema_violation_rejected`, `test_missing_required_field_rejected`,
  `test_malformed_response_object_rejected_and_stops`, `test_unknown_prompt_rejected`,
  `test_unknown_version_rejected`, `test_template_hash_mismatch_rejected`,
  `test_unknown_schema_rejected`, `test_schema_id_mismatch_rejected_no_fallback`,
  `test_schema_drift_rejected`, `test_object_valid_under_other_schema_is_still_rejected`,
  `test_no_candidates_rejected`.
- `AdmissionRepairRetryTest`: `test_repair_succeeds_within_bound`,
  `test_good_candidate_beyond_bound_is_never_reached`,
  `test_repair_exhaustion_fails_closed`, `test_first_valid_candidate_short_circuits`,
  `test_malformed_max_attempts_rejected`.
- `DeterminismAndPurityTest`: `test_decision_to_dict_is_deterministic`,
  `test_every_reason_code_is_unique_and_stable`, `test_is_repairable_predicate`,
  `test_admission_is_a_pure_value_with_no_filesystem_side_effects`.

## Validation commands + real results

- Focused: `python3 -m unittest tests.test_structured_output` → **Ran 52 tests, OK**.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"` →
  **Ran 889 tests in 0.729s, OK**.
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check`) → **91 files already formatted**.
- `git diff --check` → **clean** (no whitespace errors).
- `make typecheck` (mypy, advisory/non-blocking per Makefile) → 17 pre-existing
  errors in 7 unrelated files (state_machine, validation, gate_evaluator, queries);
  **zero** of them reference the new `structured_output.py`. No new type errors.
- GitHub required CI on PR #33 head `cbc5e6a9e773d66967263401b8ccb0eb58567ee1`:
  `quality (3.10)` SUCCESS, `quality (3.11)` SUCCESS, `quality (3.12)` SUCCESS.

## Constitution / scope confirmations

- Local/offline structured-output admission contract **only**: no real
  LLM/provider/HTTP/SDK, no network call, no credentials/env vars/secrets, no paid
  service, **no content/data sent to any external LLM or service**.
- No dependency/lockfile/SBOM, workflow, Docker, ruleset, or secret changes; no real
  human-derived data (fixtures are tiny synthetic public data); no public deployment.
- No persistence writes: admission writes no project state, events, artifacts, logs,
  reports, domain/business tables, or queue/outbox; mutates no domain object.
- Out-of-scope items (T-05-04 semantic validator, T-05-05 egress policy, T-05-06 tool
  broker, T-05-07..12 audit/budget/rollback, WP-05d+) were **not** started.
- **R0-02 follow-on was not started** beyond this authorized slice; **nothing was
  self-merged**; auto-merge was **not** enabled; the protected base was **not** pushed.

## Possible extra verification for Codex

- Re-run the focused suite and confirm `ParseStructuredOutputTest` /
  `AdmissionRepairRetryTest` reason codes match (esp. `1e400` → `ADMIT_NON_FINITE_NUMBER`
  and bounded-attempt truncation).
- Confirm the no-fallback guarantees:
  `test_object_valid_under_other_schema_is_still_rejected` and
  `test_schema_id_mismatch_rejected_no_fallback`.
- Note the bounded JSON-schema **subset** (not a full engine); confirm the supported
  keyword/type set is acceptable for this slice or request a follow-on if a fuller
  engine is wanted later.
