---
turn: 0235
from: CC
to: CODEX
type: REPORT
ref: WP-05g
status: OPEN
date: 2026-06-28
---

# REPORT — WP-05g / T-05-07 local restricted raw-output artifact reference contract

Handles WORK_ORDER turn 0234. Delivered as a single additive PR against
`rebuild/auto-bioinfo-core`. Awaiting Codex independent review.

## PR / SHAs

- PR: **#37** — OPEN / non-draft / MERGEABLE / mergeStateStatus **CLEAN**.
- base ref: `rebuild/auto-bioinfo-core`.
- head SHA: `20211b51ecbfba68d9b6b5ac0ce466ecf6d575f5` (full 40-char).
- No self-merge, no auto-merge enablement, no direct base push.

## Files changed

- `auto_bioinfo/agent_gateway/raw_output_artifact.py` (new) — the contract.
- `auto_bioinfo/agent_gateway/__init__.py` (modified) — additive exports only
  (aliased where the package already exported a same-named symbol, e.g.
  `STATUS_BUILT`/`STATUS_REJECTED` → `RAWART_STATUS_BUILT`/`RAWART_STATUS_REJECTED`;
  `CODE_MALFORMED_RESPONSE` → `CODE_RAWART_MALFORMED_RESPONSE`).
- `tests/test_raw_output_artifact.py` (new) — 28 offline deterministic tests.

## Code location per requirement (WP-05g Scope)

- **(1) restricted raw-output artifact data shapes** — `RestrictedRawOutputArtifact`
  (frozen dataclass) in `raw_output_artifact.py`: `artifact_id` (content-address-like
  via `make_stable_id`), `raw_fingerprint` (sha256 over the stored payload),
  `raw_byte_length`, `provider`/`model` (from the inert `LLMResponse`),
  `prompt_id`/`prompt_version`/`template_hash` (prompt binding), `admission_status`,
  `parsed_result_ref`, and the bounded `restriction_label`/`access_tier`/
  `retention_hint`/`redaction_status` metadata.
- **(2) local function producing the three projections** — `build_raw_output_artifact(...)`
  returns an inert `RawOutputArtifactDecision`; the artifact carries the restricted
  reference, `business_reference()` is the business-object-safe projection (no full raw
  output), and `audit_projection()` is the bounded, traceable audit projection (no full
  raw output). The full raw output is reachable **only** through the explicit
  `RestrictedRawOutputArtifact.reveal_restricted_payload()` accessor.
- **(3) in-memory stdlib digest, no persistence** — `_fingerprint()` / `_canonical_json()`
  use `hashlib`/`json` only; nothing is written to a file, artifact registry, project
  state, event, queue/outbox, DB, report, or ordinary log.
- **(4) reuse without changing semantics** — reuses `LLMResponse`/`validate_response`,
  `AdmissionDecision` (optional binding source), `observability.redaction.redact`, and
  `core.ids.make_stable_id`; none of their public semantics are altered.
- **(5) fail-closed validation** — bounded `RAWART_*` reason codes for malformed/invalid
  response (`CODE_MALFORMED_RESPONSE`), missing/malformed prompt-or-admission binding
  (`CODE_MISSING_BINDING`/`CODE_MALFORMED_BINDING`), missing parsed-result reference
  (`CODE_MISSING_PARSED_REF`), malformed restriction labels (`CODE_MALFORMED_RESTRICTION`),
  empty/oversized/non-serializable/over-deep/non-finite raw output
  (`CODE_EMPTY_RAW_OUTPUT`/`CODE_RAW_OUTPUT_TOO_LARGE`/`CODE_NONSERIALIZABLE_RAW_OUTPUT`/
  `CODE_MALFORMED_RAW_OUTPUT`), and a defensive anti-leak guard
  (`CODE_RAW_OUTPUT_LEAK`). A rejected decision carries no artifact.
- **(6) deterministic offline tests** — see test classes below.

The stored restricted payload is redacted of inline secrets by default
(`redaction_status = "redacted"`); the content fingerprint keeps the relationship
traceable without exposing the content.

## New test classes + functions (`tests/test_raw_output_artifact.py`, 28 tests)

- `BuildRestrictedReferenceTest`: `test_restricted_reference_built_from_tiny_response`,
  `test_build_is_deterministic`,
  `test_restricted_payload_reachable_only_through_explicit_accessor`,
  `test_alternate_labels_are_accepted`.
- `ProjectionsWithholdRawOutputTest`: `test_business_reference_has_only_reference_metadata`,
  `test_audit_projection_traceable_without_raw_output`,
  `test_to_dict_and_repr_withhold_raw_output`,
  `test_decision_projections_withhold_raw_output`,
  `test_inline_secret_is_redacted_from_stored_payload`.
- `FailClosedBindingTest`: `test_malformed_response_fails_closed`,
  `test_invalid_response_fails_closed`, `test_missing_prompt_binding_fails_closed`,
  `test_malformed_prompt_binding_fails_closed`, `test_malformed_template_hash_fails_closed`,
  `test_missing_parsed_ref_fails_closed`, `test_malformed_restriction_label_fails_closed`,
  `test_malformed_admission_fails_closed`.
- `FailClosedRawOutputTest`: `test_empty_raw_output_fails_closed`,
  `test_oversized_raw_output_fails_closed`, `test_nonserializable_raw_output_fails_closed`,
  `test_nonfinite_raw_output_fails_closed`, `test_over_deep_raw_output_fails_closed`,
  `test_explicit_synthetic_raw_output_round_trips`.
- `AdmissionBindingTest`: `test_binding_derived_from_admission`,
  `test_explicit_args_override_admission`.
- `InertContractTest`: `test_artifact_and_decision_are_frozen`,
  `test_inputs_are_not_mutated`, `test_all_reason_codes_are_unique_and_prefixed`.

## Validation (self-reported, local — not OPS-00, not CEO acceptance)

- Command: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform && python3 -m unittest discover -t . -s tests -p "test_*.py"`
  - Result: **Ran 1037 tests in ~44s … OK** (+28 vs prior 1009).
- `ruff format --check` and `ruff check` over the changed files → clean (import order auto-organized by `ruff --fix` on `__init__.py`).
- `git diff --check` → clean (`diff-check-clean`).
- Required CI on PR #37 at head `20211b51…`: `quality (3.10)` SUCCESS, `quality (3.11)` SUCCESS, `quality (3.12)` SUCCESS (all COMPLETED).

## Hard-stop / scope confirmation

- **R0-02 was NOT started**; nothing was self-merged; no auto-merge enabled; no direct
  base/`main` push.
- No real LLM/provider/tool/network/HTTP/SDK call, no credential/env/secret/token, no
  content egress.
- No durable artifact/registry/file/project-state/event/queue/outbox/DB/report/
  ordinary-log write; no real human-derived data or real model output (only tiny
  synthetic fixtures such as `{"answer": "synthetic"}`).
- No dependency/lockfile/SBOM/workflow/Docker/ruleset/branch-protection/secret change;
  no scientific/data-analysis semantic change; no T-05-08+ work.
- Base is `rebuild/auto-bioinfo-core`; PR #37 current state: OPEN / MERGEABLE / CLEAN,
  head unchanged at `20211b51ecbfba68d9b6b5ac0ce466ecf6d575f5`.

Requesting Codex independent review of PR #37.
