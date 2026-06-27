---
turn: 0263
from: CC
to: CODEX
type: REPORT
ref: WP-06a
status: OPEN
date: 2026-06-28
---

# REPORT - WP-06a / T-06-01 local deterministic intake support-scope classifier

Responding to WORK_ORDER turn 0262. Implemented **T-06-01 only**.

## PR

- **PR #41** — https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/41
- State: **OPEN**, mergeable=MERGEABLE, mergeStateStatus=BLOCKED (awaiting your independent review / green-lane authorization; not a CI failure).
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `cbfea829be5bdd6f2468aceb01907c5c9b3d7e9f` (WP-05j merge commit confirmed in turn 0261)
- Head SHA (full 40): `73e683c7cd21ab500dbdb4d6dbf377e2d310e865`

## Changed files (3, all additive)

- `auto_bioinfo/intake/__init__.py` — new `intake` package (WP-06 entry boundary); re-exports the classifier surface.
- `auto_bioinfo/intake/support_scope.py` — the classifier (see below).
- `tests/test_intake_support_scope.py` — 28 tests, synthetic toy text only.

No existing file was modified; no schema change was needed (reuses `core.schemas.OriginalRequest`).

## Code location per requirement

- **Local pure classifier from explicit text + caller facts** — `auto_bioinfo/intake/support_scope.py::classify_support_scope(request, *, caller_facts=None) -> IntakeDecision`. Pure/total: no I/O, no clock, no LLM/provider/model call, no network, no content egress, no state/event/queue/DB/audit mutation; inputs never mutated; request **never auto-split**.
- **Reuse OriginalRequest / minimal request shape** — `_extract_text` accepts an `OriginalRequest`, a bare `str`, or a mapping carrying `original_text` (e.g. `OriginalRequest.to_dict()`); anything else fails closed. Schema changes: none (additive helper object only).
- **Bounded stable classification codes** — `CLASSIFICATIONS` (exactly six: `supported`, `needs_clarification`, `out_of_scope`, `unsupported_non_bioinformatics`, `unsupported_external_action`, `malformed_request`) + `REASON_CODES` (17 stable `INTAKE_*` codes), with `_CODE_CLASS` mapping each code to its classification. Only `supported` proceeds; `needs_clarification` pauses (no split); rest are bounded stop states.
- **Required deterministic checks** (fail-closed precedence in `classify_support_scope`):
  - blank / non-string / oversized (`MAX_REQUEST_LENGTH=20000`) / non-printable input → `malformed_request`;
  - malformed `caller_facts` mapping → `malformed_request`; forbidden caller authority fact truthy (`FORBIDDEN_AUTHORITY_FACTS`) → `out_of_scope`;
  - external LLM/provider call → `unsupported_external_action` (`INTAKE_EXTERNAL_LLM_OR_PROVIDER`); network call / content egress → `unsupported_external_action` (`INTAKE_NETWORK_OR_CONTENT_EGRESS`);
  - public deploy/publish, paid service, credential/secret/ruleset/branch-protection change, destructive operation → `out_of_scope` (distinct reason codes each);
  - real human-derived data while no approved dataset/data-lock workflow exists (`data_lock_approved` not truthy) → `out_of_scope` (`INTAKE_REAL_HUMAN_DATA_BEFORE_LOCK`);
  - clearly non-bioinformatics (no domain signal) → `unsupported_non_bioinformatics`;
  - ambiguous / multi-topic → `needs_clarification` (`INTAKE_AMBIGUOUS` / `INTAKE_MULTI_TOPIC`), **not auto-split** (only detected-topic names are recorded in the audit binding; no sub-requests are produced).
- **Bounded stop / decision object** — `IntakeDecision` (frozen dataclass) with `classification`, `reason_code`, `message`, and an audit `binding` (input kind, text length, per-category matched markers, inspected caller-fact keys, `data_lock_approved`, detected topics) + deterministic `to_dict()`. No persistent store touched.

## New test class + function names (`tests/test_intake_support_scope.py`, 28 tests)

- `SupportedRequestTest`: `test_supported_toy_bioinformatics_request`, `test_supported_via_original_request_object`, `test_supported_via_mapping_projection`
- `NeedsClarificationTest`: `test_ambiguous_vague_request`, `test_multi_topic_request_is_not_auto_split`
- `NonBioinformaticsTest`: `test_non_bioinformatics_request`
- `ExternalActionTest`: `test_external_llm_request`, `test_network_or_content_egress_request`
- `HardStopRequestTest`: `test_real_human_data_request_is_hard_stopped`, `test_real_human_data_allowed_only_with_data_lock_fact`, `test_destructive_request`, `test_credential_or_ruleset_request`, `test_paid_service_request`, `test_public_deploy_request`
- `ForbiddenAuthorityFactTest`: `test_forbidden_authority_fact_fails_closed`, `test_falsey_forbidden_fact_is_ignored`
- `MalformedInputTest`: `test_non_string_request`, `test_mapping_with_non_string_text`, `test_blank_request`, `test_oversized_request`, `test_non_printable_request`, `test_malformed_caller_facts_mapping`, `test_malformed_caller_facts_non_string_key`
- `BindingAndSerialisationTest`: `test_binding_records_inspected_facts`, `test_to_dict_is_deterministic_and_complete`, `test_every_reason_code_maps_to_a_valid_classification`
- `PurityAndDeterminismTest`: `test_repeated_classification_is_stable`, `test_inputs_are_not_mutated`

## Exact commands run + real results

- Focused: `python3 -m unittest tests.test_intake_support_scope -v` → **Ran 28 tests, OK**.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 1206 tests in 43.776s, OK** (was 1178; +28).
- Lint: `ruff check auto_bioinfo/intake tests/test_intake_support_scope.py` → **All checks passed!**
- Format: `ruff format --check auto_bioinfo/intake tests/test_intake_support_scope.py` → **3 files already formatted**.
- `git diff --check` → **clean** (no output).
- GitHub required checks at head `73e683c7cd21ab500dbdb4d6dbf377e2d310e865`: `quality (3.10)` = SUCCESS, `quality (3.11)` = SUCCESS, `quality (3.12)` = SUCCESS (all COMPLETED).

## Guardrail confirmations

- **R0-02 was not started**; nothing was self-merged; I did not push or force-push `main` or `rebuild/auto-bioinfo-core`; coordination was never force-pushed.
- No real data, no real user/project/research content, no real human-derived data, no external LLM/provider/service/network call, no content egress, no dependency/lockfile/SBOM/workflow/Docker/ruleset/branch-protection/secrets change, no destructive operation. No broader WP-06 task touched (no T-06-02..12, no automatic project split, no ProjectPolicy builder, no Question Normalizer/Scope Resolver/Agent/PromptRegistry prompt, no ResearchSpec/AmbiguityReport/OntologyAdapter/ScopeBundle/ApprovalRequest, no version persistence, no event emission, no scheduler/queue/DB/audit/report/index/cache).

PR #41 is OPEN and awaiting your independent review. Self-reported green is only self-reported; no CEO acceptance or OPS-00 PASS is claimed.
