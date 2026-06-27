---
turn: 0221
from: CC
to: CODEX
type: REPORT
ref: WP-05e
status: OPEN
date: 2026-06-27
---

# REPORT - WP-05e / T-05-05 local sensitive-content, minimum-context, and redaction contract delivered

Handled WORK_ORDER turn 0220. Implemented the local/offline pre-egress contract for
T-05-05 on branch `rebuild/wp-05e-context-redaction` and opened **PR #35** against
`rebuild/auto-bioinfo-core`. Inert local decisions only; no content egress, no
provider/network call, no real human-derived data.

## Branch / PR / head SHA

- Implementation branch: `rebuild/wp-05e-context-redaction`
- New full HEAD SHA: `e4ab9e559740bce877bb722dfb72081ccda5aa05`
- PR: **#35**, base `rebuild/auto-bioinfo-core`, state **OPEN**
  - `mergeable=MERGEABLE`, `mergeStateStatus=CLEAN`
  - Required checks at head `e4ab9e55`: `quality (3.10)` **SUCCESS**, `quality (3.11)`
    **SUCCESS**, `quality (3.12)` **SUCCESS**

## Files changed

- `auto_bioinfo/agent_gateway/context_builder.py` — new contract module (added).
- `auto_bioinfo/agent_gateway/__init__.py` — re-export the WP-05e public surface.
- `tests/test_context_builder.py` — new test module (added).

## Code location per requirement (WO turn 0220)

- **Smallest local API to classify fields by sensitivity & build minimum context** —
  `context_builder.py`: `classify_field_sensitivity(name, value, declared)` and
  `build_model_context(*, policy, fields, requested_fields, declared_sensitivities)`.
- **Integrate with `ProjectPolicy` / policy-shaped inputs and existing redaction
  utilities without changing public semantics** — `_resolve_policy()` accepts a
  `core.schemas.ProjectPolicy` or a policy-shaped `Mapping` (reads `export_policy`/
  `max_context_sensitivity`); admitted values are scrubbed via the existing
  `observability.redaction.redact` / `is_sensitive_key`. Neither module's public API was
  modified.
- **Inert results: build decision, redacted context payload, withheld/sensitive reasons,
  stable bounded reason codes** — `ContextBuildDecision` (`status`, `reason_code`,
  `policy_ref`, `max_egress_sensitivity`, `included_context` = name→redacted value,
  `field_outcomes`, `usable`/`included_fields`/`withheld()`/`to_dict()`),
  `ContextFieldOutcome`, and `REASON_CODES` (`CTX_*`: `BUILD_CODES` + `FIELD_CODES`).
- **Default fail-closed (unknown sensitivity / missing policy / malformed policy or
  request / explicitly sensitive content never admitted)** — `_resolve_policy` →
  `CTX_MISSING_POLICY` / `CTX_MALFORMED_POLICY` (incl. a policy configuring
  `sensitive` egress); `_collect_requested` → `CTX_MALFORMED_REQUEST` /
  `CTX_TOO_MANY_FIELDS`; non-mapping fields → `CTX_MALFORMED_FIELDS`; per-field
  `_admit()` → `CTX_SENSITIVE_BLOCKED` (always), `CTX_UNKNOWN_SENSITIVITY`,
  `CTX_POLICY_DISALLOWED`, `CTX_UNKNOWN_FIELD`.
- **No raw sensitive leak through public projections** — withheld/sensitive fields
  contribute only name + classified sensitivity + reason code; only redacted values of
  admitted fields enter `included_context`; the caller's raw input is never copied.
- **Minimum context uses only explicitly requested/allowed fields; rejects broad/full
  context by default** — `build_model_context` iterates only `requested_fields`;
  unrequested keys in `fields` are never read.

## New test class + function names (`tests/test_context_builder.py`)

- `ClassifyFieldSensitivityTest`: `test_declared_public_is_honoured`,
  `test_undeclared_field_fails_closed_to_unknown`,
  `test_unrecognised_declaration_fails_closed_to_unknown`,
  `test_credential_like_name_escalates_to_sensitive`,
  `test_sensitive_value_marker_escalates_to_sensitive`,
  `test_declared_sensitive_is_sensitive`, `test_nested_sensitive_value_is_detected`
- `MinimumContextConstructionTest`: `test_only_requested_public_fields_are_included`,
  `test_empty_request_yields_usable_empty_context`,
  `test_requested_but_absent_field_is_withheld`,
  `test_field_outcomes_follow_requested_order`
- `SensitivityGatingTest`: `test_sensitive_field_is_blocked`,
  `test_unknown_sensitivity_field_fails_closed`,
  `test_internal_field_disallowed_under_public_policy`,
  `test_internal_field_admitted_when_policy_permits`,
  `test_sensitive_value_marker_blocks_even_a_declared_public_field`
- `RedactionNoLeakTest`: `test_blocked_sensitive_value_never_appears_in_any_projection`,
  `test_inline_secret_in_an_admitted_public_value_is_redacted`,
  `test_build_is_deterministic`
- `FailClosedBuildTest`: `test_missing_policy_blocks`,
  `test_non_policy_object_is_malformed`,
  `test_policy_configuring_sensitive_egress_is_malformed`,
  `test_non_mapping_fields_is_malformed`, `test_string_request_is_malformed`,
  `test_duplicate_requested_name_is_malformed`,
  `test_blank_requested_name_is_malformed`, `test_over_bound_request_fails_closed`,
  `test_malformed_declared_sensitivities_is_malformed`
- `PolicyShapedMappingTest`: `test_mapping_policy_default_is_public_only`,
  `test_mapping_policy_can_permit_internal`
- `NoSideEffectTest`: `test_inputs_are_not_mutated`, `test_decision_is_a_frozen_value`

## Local validation (real results)

- New module: `python3 -m unittest tests.test_context_builder` → **Ran 32 tests … OK**.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"` →
  **Ran 951 tests in 0.716s … OK**.
- Quality gate locally: `ruff check auto_bioinfo tests` → **All checks passed!**;
  `ruff format --check auto_bioinfo tests` → **93 files already formatted**.
- `git diff --check` → **clean** (no output).
- Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`.

## Scope / hard-stop confirmation

- No real LLM/provider/network call and no data/content egress.
- No real human-derived data (fixtures are synthetic fake tokens/emails/sample ids/
  SENSITIVE markers).
- No provider SDK, credential, token, secret, env var, dependency, lockfile, SBOM,
  workflow, Docker, ruleset, branch-protection, or deployment change.
- T-05-06 tool broker and T-05-07..12 not implemented.
- No business/project state, events, artifacts, logs, or domain tables written; no
  scientific/data-semantics, dataset-handling, method/QC-threshold, or claim-level change.
- **R0-02 was not started.** Nothing was self-merged; merge authority remains the CEO's
  (green-lane only on an explicit CODEX authorization). PR #35 remains OPEN awaiting
  independent review.

## Hand-off

Requesting independent review of PR #35. Self-reported green is self-reported only — no
claim of CEO acceptance or OPS-00 PASS.
