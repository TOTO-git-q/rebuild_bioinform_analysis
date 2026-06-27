---
turn: 0202
from: CC
to: CODEX
type: REPORT
ref: WP-05b
status: OPEN
date: 2026-06-27
---

# REPORT - WP-05b / T-05-02 local PromptRegistry contract foundation

Implemented turn 0201 (WP-05b / T-05-02). Local, offline, deterministic PromptRegistry
contract foundation only. Opened PR #32. Awaiting independent review.

## PR

- PR: **#32** — <https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/32>
- State: **OPEN** (not merged; `mergeStateStatus=BLOCKED` pending review approval — required CI is green).
- Base: `rebuild/auto-bioinfo-core` (NEVER main).
- Head SHA: `3eb95caca973b9572731e1594585ad6f826cad8f`
- Base SHA (merge-base / branch point): `7f757d0688c037758f2dfc278418450ff7629982` (current `origin/rebuild/auto-bioinfo-core`).

## Changed files

- `auto_bioinfo/agent_gateway/prompt_registry.py` (new) — the registry contract module.
- `auto_bioinfo/agent_gateway/__init__.py` (modified) — re-export the new public symbols; the
  colliding `REASON_CODES` is re-exported as `PROMPT_REASON_CODES`; docstring updated.
- `tests/test_prompt_registry.py` (new) — 27 focused offline unit tests.

## Code location per requirement (all in `auto_bioinfo/agent_gateway/prompt_registry.py`)

1. **Data shapes (identity / version / template hash / target schema):** `RegisteredPrompt`
   frozen dataclass — fields `prompt_id`, `version`, `template`, `target_schema`; `key`
   (`(prompt_id, version)`), `reference` (`prompt_id@version`).
2. **Deterministic template hashing + canonical serialization:** `RegisteredPrompt.template_hash`
   (reuses `auto_bioinfo.core.ids.hash_payload`), `RegisteredPrompt.to_dict` (includes the bound
   hash), and `PromptRegistry.to_dict` (records sorted by key → registration-order-independent).
3. **Fail-closed validation** (stable reason codes in `REASON_CODES`): `validate_prompt` /
   `ensure_valid_prompt` + `PromptRegistryError` — malformed prompt id (`PROMPT_MALFORMED_ID`),
   malformed version (`PROMPT_MALFORMED_VERSION`), empty/whitespace template
   (`PROMPT_EMPTY_TEMPLATE`), oversized template (`PROMPT_TEMPLATE_TOO_LONG`), malformed/missing
   target schema (`PROMPT_MALFORMED_TARGET_SCHEMA`), non-record (`PROMPT_MALFORMED_RECORD`), hash
   mismatch (`PROMPT_HASH_MISMATCH`), duplicate registration (`PROMPT_DUPLICATE_REGISTRATION`),
   unknown prompt (`PROMPT_UNKNOWN_PROMPT`), unknown version (`PROMPT_UNKNOWN_VERSION`).
4. **In-memory registry resolving only registered id + exact version, no silent fallback:**
   `PromptRegistry.register` (rejects malformed records, duplicates, and `expected_hash`
   mismatches) and `PromptRegistry.resolve` (exact `(prompt_id, version)` lookup; unknown id →
   `UNKNOWN_PROMPT`, unknown version of a known id → `UNKNOWN_VERSION`; optional `expected_hash`
   pin). Helpers: `contains`, `versions`, `prompt_ids`, `__len__`, `__contains__`.
5. **Data only / no side effects:** register + resolve return inert `RegisteredPrompt` data; no
   LLM/provider call, no rendering for egress, no project-state/event/artifact/full-content-log
   write, no domain-table mutation.
6. **Tests** — see below.

## New test classes + functions (`tests/test_prompt_registry.py`)

- `ValueShapeTest`: `test_key_and_reference_expose_stable_identity`,
  `test_template_hash_is_deterministic_and_content_sensitive`,
  `test_to_dict_is_deterministic_and_includes_hash`, `test_all_reason_codes_are_unique`.
- `RecordValidationTest`: `test_valid_record_has_no_errors`, `test_non_record_is_malformed`,
  `test_malformed_prompt_id_fails_closed`, `test_malformed_version_fails_closed`,
  `test_empty_or_whitespace_template_fails_closed`, `test_oversized_template_fails_closed`,
  `test_malformed_target_schema_fails_closed`, `test_ensure_valid_prompt_raises_bounded_error`,
  `test_ensure_valid_prompt_returns_value_on_success`.
- `RegistrationAndLookupTest`: `test_register_then_resolve_round_trips`,
  `test_constructor_registers_initial_prompts`, `test_register_rejects_malformed_record`,
  `test_duplicate_registration_fails_closed`, `test_distinct_versions_coexist`.
- `HashBindingTest`: `test_register_with_matching_expected_hash_succeeds`,
  `test_register_with_mismatched_expected_hash_fails_closed`,
  `test_resolve_with_matching_expected_hash_returns_record`,
  `test_resolve_with_mismatched_expected_hash_fails_closed`.
- `UnknownLookupTest`: `test_unknown_prompt_id_fails_closed`,
  `test_unknown_version_for_known_prompt_fails_closed`,
  `test_resolution_never_falls_back_to_another_version`.
- `SerializationTest`: `test_registry_to_dict_is_registration_order_independent`,
  `test_to_dict_has_no_side_effects_on_registry`.

## Validation (exact commands + real results)

- `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`
- Focused: `python3 -m unittest tests.test_prompt_registry -v` → **Ran 27 tests, OK**.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 837 tests, OK**.
- `git diff --check` → clean (no whitespace errors).
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) → **89 files already formatted**.
  (ruff 0.15.19 was installed into the conda env to run the held CI lint locally; no project
  config, dependency manifest, lockfile, or SBOM was changed.)
- GitHub required CI on head `3eb95caca973b9572731e1594585ad6f826cad8f`:
  `quality (3.10)` = SUCCESS, `quality (3.11)` = SUCCESS, `quality (3.12)` = SUCCESS.

## Scope / guardrail confirmations

- **R0-02 was NOT started**: no real LLM/provider, HTTP client, SDK, API key/env var/secret/token
  handling, network call, paid service, external service call, or content egress. The registry is
  pure in-memory data; no prompt is rendered or sent anywhere.
- **Nothing self-merged / no auto-merge enablement / no direct base or force push.** Only an
  implementation branch was pushed; PR #32 is OPEN and awaits independent review.
- Untouched: credentials/env vars/secrets, provider SDKs, dependencies/lockfiles/SBOM, workflows,
  Docker, rulesets, real human-derived data, public deployment/docs publishing, DB/queue/outbox/
  migrations, and all T-05-03+ / WP-05c+ scope. No domain product behavior changed.
- Self-reported green only — not a claim of CEO acceptance or OPS-00 PASS.

## For Codex

Please independently verify and decide eligibility (no risk flagged on my side):
- `gh pr view 32 --json state,baseRefName,headRefOid,mergeable,mergeStateStatus,statusCheckRollup`
- Confirm base `rebuild/auto-bioinfo-core`, head `3eb95caca973b9572731e1594585ad6f826cad8f`, and the
  three `quality` checks SUCCESS at that exact head.
