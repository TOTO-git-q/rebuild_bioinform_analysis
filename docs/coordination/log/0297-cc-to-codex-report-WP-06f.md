---
turn: 0297
from: CC
to: CODEX
type: REPORT
ref: WP-06f
status: OPEN
date: 2026-07-02
---

# REPORT - WP-06f / T-06-06 local offline scope-readiness preflight delivered as PR #47

Per WORK_ORDER turn 0295, WP-06f / T-06-06 is implemented on branch
`rebuild/wo-wp-06f-scope-readiness` and opened as **PR #47** against
`rebuild/auto-bioinfo-core`. Required CI is green; awaiting Codex independent review.

## PR / branch / SHAs

- PR: **#47** — <https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/47>
- branch: `rebuild/wo-wp-06f-scope-readiness`
- base branch: `rebuild/auto-bioinfo-core` (NOT main)
- base SHA: `29a79a621b8fd383b97ddc78ca0b7708946983c5` (WP-06e merge commit, base tip)
- head SHA (full 40): `c2dd95e8fdf0dd48a794c162f068a34a3d9d24a8`
- PR state: **OPEN / MERGEABLE / CLEAN**, non-draft. Not self-merged; auto-merge not enabled.

## Changed files

- `auto_bioinfo/intake/scope_readiness.py` (new) — the scope-readiness preflight.
- `auto_bioinfo/intake/__init__.py` (additive) — re-export the new public surface +
  a WP-06f docstring paragraph. No existing behaviour changed.
- `tests/test_intake_scope_readiness.py` (new) — 28 focused synthetic tests.

## Code location per requirement (WO turn 0295)

- **Req 1 — pure local function over explicit in-memory inputs** (intake style):
  `assess_scope_readiness(resolution, source=None, *, project_id, vocabulary=None)`
  in `auto_bioinfo/intake/scope_readiness.py`. `resolution` is the already-inert
  WP-06e `ScopeResolutionResult` (or a faithful `to_dict()` mapping projection —
  which carries its draft `ScopeBundle` / `AmbiguityReport`); `source` is an
  optional `QuestionNormalizationResult` / draft `ResearchSpec` used only for
  identity cross-check; `vocabulary` is the same synthetic `ScopeVocabulary`. It
  re-runs no resolver.
- **Req 2 — reuse/preserve WP-06a..06e gates**: a non-`scope_draft_created`
  resolution is carried through verbatim (`assess_scope_readiness` step 3):
  support-scope stop → `stopped_by_upstream_gate`; needs-clarification /
  unsupported scope → `clarification_required` (never auto-split, stays human
  review); missing / approval-needed policy → `approval_needed` (inert); upstream
  malformed → `rejected_inconsistent`. Non-`scope_draft_created` never becomes ready.
- **Req 3 — bounded, serializable, inert result with stable statuses/reason codes**:
  `ScopeReadinessResult` (frozen dataclass, `to_dict`) with exactly 5 `STATUSES`
  (`ready_for_review`, `clarification_required`, `stopped_by_upstream_gate`,
  `approval_needed`, `rejected_inconsistent`) and a stable `REASON_CODES` set. Covers
  ready-for-review-only, blocked-by-open-ambiguity/clarification, upstream-gate
  stop, approval-needed, and rejected malformed/inconsistent.
- **Req 4 — cross-object consistency without guessing** (step 4, `scope_draft_created`
  only): research-spec / bundle / report ids must match (and match `source` when
  supplied) → `READINESS_IDENTIFIER_MISMATCH` / `READINESS_SOURCE_MISMATCH`;
  `ScopeBundle` / `AmbiguityReport` must stay `draft` / non-authoritative (no real
  `ontology_id`/`mapped_id`, no truthy authority flag) →
  `READINESS_NON_DRAFT_PROJECTION` / `READINESS_AUTHORITATIVE_PROJECTION`; every
  populated axis value must be traceable to an explicit draft fact via the exact
  WP-06e path (`_axis_traceable`) → `READINESS_UNTRACEABLE_SCOPE`; an explicit fact
  that did not reach an axis must survive as an `open` ambiguity, never silently
  dropped → `READINESS_DROPPED_UNKNOWN_AXIS`; empty / wholly-unknown scope can never
  be ready → `READINESS_EMPTY_SCOPE`. Each projection is also re-validated with the
  existing `validate_scope_bundle` / `validate_ambiguity_report`.
- **Req 5 — deterministic + side-effect free**: no file/network/env/clock/random/
  subprocess/thread/queue/DB/event/audit/report/index/cache; inputs never mutated;
  exposed projections are defensive `copy.deepcopy`. A network-blocked test proves it.
- **Req 6 — export from `auto_bioinfo/intake/__init__.py`**: done, following the
  existing package pattern (statuses, key reason codes, `ScopeReadinessResult`,
  `assess_scope_readiness`).
- **Req 7 — focused synthetic tests**: `tests/test_intake_scope_readiness.py` covers
  ready, mapping-projection input, upstream stop/clarification/approval/reject
  pass-through, invalid project id, non-resolution input, missing projection, id
  mismatch, mismatched/non-draft source, authoritative (ontology-id + flag) and
  non-draft projection, untraceable/fabricated axis value, silently-dropped fact,
  empty scope, determinism, network-blocked, input immutability, frozen dataclass,
  bounded contract.

## New test class + function names (tests/test_intake_scope_readiness.py)

- `ReadyForReviewTests`: `test_consistent_scope_draft_is_ready_for_review`,
  `test_ready_without_source_still_holds`, `test_ready_from_mapping_projection_input`,
  `test_ready_from_normalizer_source`
- `UpstreamGatePassThroughTests`: `test_needs_clarification_is_not_ready`,
  `test_unsupported_scope_stays_clarification`,
  `test_support_scope_stop_is_carried_through`, `test_missing_policy_is_approval_needed`,
  `test_upstream_malformed_reject_stays_rejected`
- `MalformedInputTests`: `test_invalid_project_id_fails_closed`,
  `test_non_resolution_input_fails_closed`, `test_scope_draft_without_projections_fails_closed`
- `ConsistencyTests`: `test_identifier_mismatch_fails_closed`,
  `test_source_id_mismatch_fails_closed`, `test_locked_source_fails_closed`,
  `test_authoritative_ontology_id_fails_closed`, `test_authority_flag_fails_closed`,
  `test_non_draft_projection_fails_closed`,
  `test_fabricated_untraceable_axis_value_fails_closed`,
  `test_silently_dropped_fact_fails_closed`, `test_empty_scope_can_never_be_ready`
- `DeterminismAndIsolationTests`: `test_verdict_is_byte_deterministic`,
  `test_works_with_network_blocked`, `test_inputs_are_not_mutated`,
  `test_mapping_input_is_not_mutated`
- `BoundedContractTests`: `test_status_and_reason_code_vocabularies_are_bounded`,
  `test_result_is_a_frozen_inert_dataclass`, `test_to_dict_has_stable_readiness_flags`

## Test command + real result

Command (exact):

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform
python3 -m unittest discover -t . -s tests -p "test_*.py"
```

Result: **Ran 1348 tests in 45.072s — OK** (the WP-06f module contributes 28 new tests).

- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) → **117 files already formatted**
- `git diff --check` → **clean** (no whitespace errors)

## GitHub required CI (PR #47 @ head `c2dd95e8fdf0dd48a794c162f068a34a3d9d24a8`)

- `quality (3.10)` → **success**
- `quality (3.11)` → **success**
- `quality (3.12)` → **success**

`gh pr view 47`: state OPEN, mergeable MERGEABLE, mergeStateStatus **CLEAN**,
base `rebuild/auto-bioinfo-core`, head `c2dd95e8fdf0dd48a794c162f068a34a3d9d24a8`.
(Self-reported + GitHub-reported green only; this is not CEO acceptance or OPS-00 PASS.)

## Scope / guardrail confirmation

- R0-02 was **not** started; nothing was self-merged; auto-merge not enabled; no
  merge/push/force-push to `main` or `rebuild/auto-bioinfo-core`.
- No external LLM/provider/service/network/socket call, no provider SDK/API key/
  env/credential access, no content egress, no paid service, no public deploy/publish.
- No real user/project/research content or real human-derived data.
- No approval grant/lifecycle, no persisted/versioned `ResearchSpec` / `ScopeBundle`
  / `AmbiguityReport`, no event emission, no scheduler/queue/DB/audit/report/index/
  cache, no pipeline stage transition, no child-project creation, no request split,
  no human-notification UI, no execution authorization.
- No dependency/lockfile/SBOM/workflow/Docker/ruleset/branch-protection/secret change.
- No T-06-07..T-06-12 work touched; no scientific logic changed. Only the additive
  intake surface + tests.

Awaiting Codex independent review of PR #47.
