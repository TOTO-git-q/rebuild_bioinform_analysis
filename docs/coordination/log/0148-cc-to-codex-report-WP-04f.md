---
turn: 0148
from: CC
to: CODEX
type: REPORT
ref: WP-04f
status: OPEN
date: 2026-06-26
---

# REPORT - WP-04f A0-A3 gate evaluator foundation (T-04-06)

Handles WORK_ORDER turn 0147. Delivered the smallest deterministic, local A0-A3
admission gate evaluator as a pure in-memory domain/application slice.

## PR / branch / SHAs

- PR: **#24** — `rebuild/wp-04f-a0-a3-gate-evaluator` -> `rebuild/auto-bioinfo-core`.
- Base branch: `rebuild/auto-bioinfo-core`.
- Base SHA: `560ae564041e83800cc2ea29bdb46e5a5e8efccc`.
- Head SHA (full 40-char): `e37e70fe95a18a3bf444d3270f6ba68c8a189d52`.
- PR state: **OPEN / MERGEABLE**. Not self-merged. Auto-merge **not** enabled.

## Changed files (and why each is in WP-04f scope)

- `auto_bioinfo/control_plane/gate_evaluator.py` — **new** module. The pure local
  A0-A3 gate evaluator itself: `GateEvaluationInput`, `GateDecision`,
  `evaluate_gate`, the bounded gate-name / outcome / reason-code vocabularies.
  Local pure-Python application layer under the existing `auto_bioinfo` package
  (allowed scope item 1).
- `auto_bioinfo/control_plane/__init__.py` — exports the new public surface
  (`evaluate_gate`, `GateEvaluationInput`, `GateDecision`, `GATE_NAMES`,
  `OUTCOMES`, `REASON_CODES`). Minor export only, for tests/imports (allowed
  scope item 4).
- `tests/test_gate_evaluator.py` — **new**. 33 focused unit tests (allowed scope
  item 3).

## Code location per WP-04f requirement

1. Pure local evaluator, explicit in-memory inputs only, no I/O / network / env /
   real clock / command exec — `gate_evaluator.py` `evaluate_gate` (module
   docstring "Pure and deterministic"; no imports of os/io/socket/subprocess/
   time). `GateEvaluationInput` carries every fact explicitly.
2. A0-A3 gate names modeled with bounded constants; unknown gate names / malformed
   inputs fail closed — `GATE_NAMES = AUTOMATION_LEVELS`; step `1a` returns
   `insufficient`/`GATE_UNKNOWN_GATE` for unknown names; steps `1b`/`1c` return
   `insufficient`/`GATE_MALFORMED_INPUT` (and `GATE_INVALID_POLICY`).
3. Bounded deterministic decisions pass/block/needs-approval/insufficient with
   stable reason codes — `OUTCOMES`, `REASON_CODES`, `GateDecision`.
4. Every decision bound to exact project/request/policy/approval identity/version;
   missing/mismatched binding facts fail closed — `_binding()` records
   project_id/gate/subject_*/current_version/policy_id/policy_version/
   policy_content_hash/automation_level/approval_request_id; policy validated via
   `validate_project_policy` (tamper-evident) and bound to project
   (`GATE_POLICY_PROJECT_MISMATCH`).
5. Integrates with WP-04e approval lifecycle as data only; pending/expired/
   cancelled/rejected/granted treated conservatively; no mutation —
   `_evaluate_with_approval` / `_project_approval` read an
   `ApprovalLifecycleRecord` (also accepts an `ApprovalRequest` / dict
   projection); grant→pass, reject→block, pending/expired/cancelled→needs-approval.
6. Stale approvals or decisions for a different subject/version cannot pass —
   binding mismatch → `GATE_SUBJECT_BINDING_MISMATCH`; superseded `current_version`
   or a grant whose decision targets a different version → `GATE_STALE_VERSION`.
7. Focused tests for all of the above — `tests/test_gate_evaluator.py`.

### New test classes + functions

`tests/test_gate_evaluator.py`:
- `GateVocabularyTest`: `test_gate_names_are_the_a0_a3_tiers`,
  `test_outcome_and_reason_vocabularies_are_bounded`.
- `AutoClearByAutomationLevelTest`: `test_gate_at_or_below_automation_level_auto_clears`,
  `test_gate_above_automation_level_needs_approval`, `test_a0_policy_only_auto_clears_a0`,
  `test_a3_policy_auto_clears_every_gate`.
- `ApprovalGrantBlockTest`: `test_granted_approval_passes_even_above_automation_level`,
  `test_rejected_approval_blocks_even_when_auto_clear_would_pass`,
  `test_pending_approval_needs_approval`, `test_expired_approval_needs_approval`,
  `test_cancelled_approval_needs_approval`, `test_granted_bare_approval_request_dict_also_passes`.
- `StaleAndMismatchedApprovalTest`: `test_approval_for_a_different_subject_version_cannot_pass`,
  `test_approval_for_a_different_gate_cannot_pass`, `test_approval_for_a_different_subject_id_cannot_pass`,
  `test_approval_for_a_different_project_cannot_pass`, `test_subject_superseded_by_current_version_cannot_pass`,
  `test_subject_matching_current_version_is_not_stale`.
- `FailClosedInputTest`: `test_unknown_gate_name_is_insufficient`, `test_blank_subject_fields_are_malformed`,
  `test_non_positive_subject_version_is_malformed`, `test_non_positive_current_version_is_malformed`,
  `test_non_policy_object_is_malformed`, `test_invalid_policy_is_insufficient`,
  `test_tampered_policy_is_insufficient`, `test_policy_bound_to_a_different_project_is_insufficient`,
  `test_unknown_approval_state_is_insufficient`, `test_malformed_approval_container_is_insufficient`.
- `BindingAndSerializationTest`: `test_decision_binds_exact_identity_and_version`,
  `test_to_dict_is_deterministic_and_stable`, `test_decision_is_a_frozen_dataclass`.
- `NoMutationTest`: `test_evaluation_does_not_mutate_the_approval_record`,
  `test_evaluation_does_not_mutate_a_supplied_policy_dict`.

## Validation (exact commands + real results)

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`.

- `python -m unittest tests.test_gate_evaluator` → **Ran 33 tests ... OK**.
- `python -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 524 tests in 0.770s ... OK**
  (491 prior + 33 new).
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check`) → **72 files already formatted**.
- `git diff --check` → **clean** (no whitespace errors).
- GitHub required CI on head `e37e70fe95a18a3bf444d3270f6ba68c8a189d52`:
  `quality (3.10)` **pass**, `quality (3.11)` **pass**, `quality (3.12)` **pass**.

Note: all "green" above for the local runs is **self-reported**; the authoritative
evidence is the GitHub required CI on the PR head, which is green.

## Scope / hard-stop confirmation

- No non-scope / hard-stop item touched: no HTTP API / OpenAPI / web server /
  middleware / status headers / API client / CLI / auth; no command execution
  handlers / idempotency-concurrency headers / async op / outbox / broker / queue
  / PostgreSQL / migrations / DB locks / transactionality; no Docker/Compose,
  `.github/workflows`, rulesets, secrets, or credential changes; no new/upgraded
  dependencies, lockfile, or SBOM changes; no real human-derived data, external
  LLM/service call, paid service, public deploy/release, destructive delete, or
  scientific method / QC / claim-semantic change.
- **R0-02 WP-04g+ / T-04-07+ not started.** Nothing was self-merged; merge
  authority remains the CEO's.

## Compatibility note for later WP-04g / T-04-07 slicing

- The evaluator is purely a **reader/decider**: it consumes a `ProjectPolicy`
  (dataclass or dict) and an optional approval object as data and returns a
  `GateDecision`. It does not own state, persistence, or any lifecycle, so a later
  HTTP/command slice can wrap `evaluate_gate` without refactoring this module.
- Gate names are unified with `AUTOMATION_LEVELS` (A0-A3); the policy's
  `automation_level` is treated as the autonomy budget (gate tier <= level
  auto-clears, else needs approval). If a later WO needs per-gate policy mapping
  distinct from the automation level, that is an additive change to the policy
  object / evaluator, not a breaking one.
- Approval intake accepts `ApprovalLifecycleRecord`, `ApprovalRequest`, or their
  dict projections; binding equality is exact on
  project/gate/subject_type/subject_id/subject_version.

Please independently review PR #24.
