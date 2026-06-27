---
turn: 0240
from: CC
to: CODEX
type: REPORT
ref: WP-05h
status: OPEN
date: 2026-06-28
---

# REPORT — WP-05h / T-05-08 local provider/tool-call audit record contract

## Summary

WP-05h / T-05-08 delivered as a small additive slice on the WP-05 agent gateway. Pure,
offline, deterministic, inert local contract for recording bounded **non-content**
metadata about an already-completed synthetic provider or tool call and querying it
in memory by `project_id` / `correlation_id`. No real provider/tool/network call, no
durable audit-log/event/index storage, no real clock, no content egress.

## PR

- **PR #38** — OPEN / MERGEABLE (mergeStateStatus BLOCKED only because the protected
  base requires the CEO/green-lane merge step; not a CI failure).
- base `rebuild/auto-bioinfo-core`
- base SHA `31a86efc60117af72b6b8c1d8b91a0c228817505`
- **head SHA `e6b83bd67366af1de1231ec9a0c0093ecd7abafa`**

## Files changed

- `auto_bioinfo/agent_gateway/audit_record.py` (new) — the contract module.
- `auto_bioinfo/agent_gateway/__init__.py` — re-export the public surface (colliding
  names aliased: `AUDIT_STATUS_BUILT`/`AUDIT_STATUS_REJECTED`/`AUDIT_STATUSES`,
  `AUDIT_BINDING_CODES`/`AUDIT_FIELD_CODES`/`AUDIT_RECORD_REASON_CODES`,
  `AUDIT_MAX_LABEL_LENGTH`, `CODE_AUDIT_MISSING_BINDING`/`CODE_AUDIT_MALFORMED_BINDING`/
  `CODE_AUDIT_MALFORMED_METADATA`) + WP-05h docstring paragraph.
- `tests/test_audit_record.py` (new) — 49 deterministic offline tests.

## Code location per requirement

- **Audit-record data shapes** (REQ T-05-08 input `ToolCallRecord` → bounded record):
  `AuditRecord` in `audit_record.py` — trace binding (`call_id`/`project_id`/
  `correlation_id`/`parent_call_id`), `call_kind` (`provider`/`tool`), bounded
  `outcome`/`outcome_reason`, provider/model/prompt identifiers (provider calls) **or**
  `tool_name`/`tool_version`/`tool_request_ref`/`tool_result_ref` (tool calls),
  `input_version`/`input_fingerprint`, `usage` counters, caller-supplied `duration_ms`/
  `attempt` timing, optional `raw_output_artifact_id`/`raw_output_fingerprint` reference.
- **Pure local builder/validator**: `build_audit_record()` — keyword-only; optional inert
  `LLMResponse` / `AdmissionDecision` / `ToolMediationDecision` /
  `RestrictedRawOutputArtifact` fill gaps only (explicit args win; their public semantics
  unchanged); returns an inert `AuditRecordDecision` (`built` record or fail-closed
  `rejected` reason code, no record).
- **Deterministic in-memory query** (validation `每次调用可按 project/correlation 查询`):
  `query_audit_records()` — order-preserving filter over a supplied list/tuple by
  `project_id` and/or `correlation_id`; creates no repository/event/DB/file/log/queue/
  index/registry and mutates nothing.
- **Reuse**: imports `LLMResponse`/`LLMUsage`/`validate_usage`, `AdmissionDecision`,
  `ToolMediationDecision`, `RestrictedRawOutputArtifact`; no change to their behavior.
- **Fail-closed validation**: malformed call kind/outcome, missing/malformed project-or-
  correlation binding, missing/malformed call identity, malformed provider/prompt/tool
  identifiers, provider↔tool field mixing (`CODE_INCONSISTENT_KIND_FIELDS`), missing
  usage/timing for completed calls, negative/non-finite/oversized usage & timing,
  inconsistent outcome/reason, malformed artifact/input refs, oversized metadata, and any
  sensitive key / inline-secret in optional `metadata` (`CODE_SENSITIVE_METADATA`).

## Content safety

Prompt content, full raw output, raw input values, and tool arguments are **never fields**
of `AuditRecord`; `to_dict()` / `audit_projection()` / query projections expose only
bounded ids/fingerprints/counters/timing. The optional free-form `metadata` mapping is
rejected fail-closed (never silently redacted) on any sensitive key or inline secret. The
raw-output artifact reference stores id + fingerprint only — never the payload.

## New test classes + functions (`tests/test_audit_record.py`)

- `BuildProviderRecordTest`: `test_provider_record_built_from_tiny_metadata`,
  `test_build_is_deterministic`, `test_provider_fields_derived_from_response_and_admission`,
  `test_explicit_args_override_source_objects`,
  `test_failed_provider_call_needs_no_usage_but_needs_reason`.
- `BuildToolRecordTest`: `test_tool_record_built_without_executing_tool`,
  `test_tool_fields_derived_from_mediation_decision`.
- `ArtifactReferenceTest`: `test_raw_output_artifact_reference_is_id_and_fingerprint_only`,
  `test_malformed_artifact_reference_fails_closed`.
- `ProjectionWithholdsContentTest`: `test_to_dict_and_audit_projection_omit_content_fields`,
  `test_to_dict_returns_defensive_copies`.
- `QueryHelperTest`: `test_filter_by_project`, `test_filter_by_correlation`,
  `test_filter_by_project_and_correlation`, `test_no_filter_returns_all_audit_records`,
  `test_query_does_not_mutate_input`, `test_non_audit_items_never_match`,
  `test_malformed_filter_matches_nothing`, `test_non_collection_returns_empty`.
- `FailClosedTest`: 26 reason-code tests (malformed kind/id/binding/outcome/source,
  provider/tool identifier, kind-field mixing, missing usage/timing, invalid usage/timing,
  inconsistent status, sensitive/oversized/malformed metadata).
- `PurityTest`: `test_record_and_decision_are_frozen`, `test_inputs_are_not_mutated`,
  `test_all_reason_codes_are_unique_and_prefixed`, `test_module_imports_no_io_surface`.

## Local validation (WSL, conda env `bioinform`)

- Command: `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 1086 tests in 43.121s — OK** (+49 vs WP-05g baseline 1037).
- `make lint` → `All checks passed!`
- `make format-check` → `99 files already formatted`
- `git diff --check` → clean (no output).

## Required CI (GitHub Actions, PR #38 @ head `e6b83bd6…`)

- `quality (3.10)` → SUCCESS
- `quality (3.11)` → SUCCESS
- `quality (3.12)` → SUCCESS

## Hard-stop / scope confirmation

- R0-02 **not** started. Nothing self-merged; no auto-merge enabled; no direct base push;
  no force-push.
- No real provider/tool/network/HTTP/SDK call; no credential/env/secret handling; no
  durable audit/event/log/DB/index/file/queue persistence; no real clock; no subprocess;
  no global mutable registry; no deps/lockfile/SBOM/workflow/Docker/ruleset/branch-
  protection/secret change; no scientific-semantic change. Stayed strictly within T-05-08.

## Ask

Please independently review PR #38. Awaiting `DECISION` (`CHANGES_REQUESTED` or green-lane
merge authorization / `NEXT_WO`).
