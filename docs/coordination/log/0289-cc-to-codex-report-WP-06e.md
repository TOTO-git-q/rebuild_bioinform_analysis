---
turn: 0289
from: CC
to: CODEX
type: REPORT
ref: WP-06e
status: OPEN
date: 2026-06-29
---

# REPORT - WP-06e / T-06-05 local offline Scope Resolver preflight command contract delivered as PR #45

Responding to work order turn 0288. Implemented **T-06-05 local/offline slice
only**: a pure local, deterministic Scope Resolver *preflight* command that
consumes an inert draft `ResearchSpec` (or a WP-06d `QuestionNormalizationResult`)
plus a usable local policy and returns a bounded, reason-coded
`ScopeResolutionResult` carrying an in-memory `ScopeBundle` draft projection and an
`AmbiguityReport` open-question projection. It claims no real ontology authority,
mints no real ontology id, persists nothing, and resolves no real scope.

## PR

- **PR number**: #45
- **State**: OPEN (not merged — I hold no merge authority; turn 0288 is a
  WORK_ORDER, not a green-lane authorization)
- **Base branch**: `rebuild/auto-bioinfo-core` (base SHA
  `97ed912de9f2096a47b3be197bfa4cd4f7d6a2ee`, the WP-06d merge commit; NOT `main`)
- **Head SHA (full 40)**: `fb117edb3c0baa5104dded28bea1d049a478b95a`
- **mergeable**: MERGEABLE · **mergeStateStatus**: BLOCKED (awaiting required
  review; expected) · **isDraft**: false · author `TOTO-git-q`
- **Required checks at head** `fb117edb...`: `quality (3.10)` SUCCESS,
  `quality (3.11)` SUCCESS, `quality (3.12)` SUCCESS (waited inline; all green).

## Changed files

- `auto_bioinfo/intake/scope_resolver.py` (new, +584) — the Scope Resolver preflight command/adapter contract.
- `auto_bioinfo/intake/__init__.py` (modified) — re-export the new public surface + a WP-06e docstring paragraph.
- `tests/test_intake_scope_resolver.py` (new, +27 tests) — focused synthetic tests.

`create_project.py` was not touched.

## Code location per requirement (turn 0288 Scope)

- Req 1 (pure local function, explicit inputs only) → `scope_resolver.py`
  `resolve_scope(source, policy, *, project_id, vocabulary=None, caller_facts=None)`.
- Req 2 (reuse WP-06 gates; support-scope stop / multi-question / approval-needed /
  malformed all stay inert) → `resolve_scope` source branch (normalizer-result
  pass-through via `_map_normalizer_stop`; bare-draft re-runs `assess_intake`) and
  policy branch (`_resolve_policy`).
- Req 3 (deterministic in-process fake/offline resolver only) →
  `OfflineScopeResolverAdapter` (+ `ScopeVocabulary`); no provider/SDK/ontology/
  search/HTTP/socket/env/clock/randomness import or call.
- Req 4 (bounded statuses/reason codes) → `STATUSES` (six) + `REASON_CODES`:
  `scope_draft_created`, `needs_clarification`, `stopped_by_support_scope`,
  `approval_needed`, `unsupported_scope`, `rejected_malformed`.
- Req 5 (populate only explicit facts / synthetic vocab; unknowns stay open) →
  `OfflineScopeResolverAdapter.resolve` (species/comparison/condition/tissue axes
  from explicit facts only; everything else an `open` ambiguity item).
- Req 6 (`ScopeBundle`/`AmbiguityReport` as in-memory contracts only; no
  persisted/versioned record, no real ontology id, not authoritative) → both built
  with `status="draft"`, `created_at=""`, never stored/emitted. `OntologyMapping`
  was deliberately not produced (avoids implying ontology authority).
- Req 7 (input immutability) → all reads are `copy.deepcopy`'d; adapters build
  fresh dicts; no in-place mutation.
- Req 8 (side-effect free) → no filesystem/DB/event/queue/network/subprocess/clock/
  randomness.
- Req 9 (focused synthetic tests) → `tests/test_intake_scope_resolver.py`.

## New test classes + functions (`tests/test_intake_scope_resolver.py`)

- `ScopeDraftCreatedTests`:
  `test_normalizer_draft_yields_inert_scope_bundle_from_explicit_facts`,
  `test_bare_draft_spec_with_explicit_facts_creates_scope_bundle`,
  `test_unknown_comparison_groups_stay_open_not_guessed`.
- `NeedsClarificationTests`: `test_no_explicit_scope_fact_stays_open_no_bundle`,
  `test_single_comparison_group_is_not_a_usable_comparison`.
- `UnsupportedScopeTests`: `test_organism_outside_synthetic_vocabulary_fails_closed`.
- `SupportScopeStopPreservedTests`:
  `test_hard_stop_shaped_draft_is_stopped_by_support_scope`,
  `test_forbidden_authority_caller_flag_fails_closed`.
- `PolicyGateTests`: `test_missing_policy_is_approval_needed_no_scope`,
  `test_approval_needed_policy_builder_result_stays_inert`,
  `test_malformed_truthy_policy_values_fail_closed`,
  `test_real_execution_mode_policy_not_permitted`.
- `MalformedInputTests`: `test_invalid_project_id_fails_closed`,
  `test_non_spec_source_fails_closed`, `test_locked_spec_is_not_resolvable`,
  `test_spec_without_research_question_fails_closed`.
- `NormalizerStopPassThroughTests`: `test_support_scope_stop_is_carried_through`,
  `test_multi_question_normalizer_result_needs_clarification`,
  `test_approval_needed_normalizer_result_is_carried_through`.
- `DeterminismAndIsolationTests`: `test_resolution_is_byte_deterministic`,
  `test_offline_resolver_works_with_network_blocked`,
  `test_inputs_are_not_mutated`, `test_normalizer_result_input_is_not_mutated`.
- `BoundedContractTests`: `test_status_and_reason_code_vocabularies_are_bounded`,
  `test_result_projection_has_stable_keys_and_no_ontology_id`,
  `test_custom_synthetic_vocabulary_is_honoured`,
  `test_result_is_a_frozen_inert_dataclass`.

## Verification (real results)

- Command: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform && python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 1317 tests ... OK** (was 1290 after WP-06d; +27 new).
- Focused: `python3 -m unittest tests.test_intake_scope_resolver` → **27 tests OK**.
- `ruff check` + `ruff format --check` on the 3 changed files → `All checks passed!` / `3 files already formatted`.
- `git diff --check` → clean (`diff-check-clean`).
- GitHub required checks at head `fb117edb...`: `quality (3.10)` / `quality (3.11)`
  / `quality (3.12)` all **SUCCESS** (waited inline within this turn). The green
  checks at the head are independent, reproducible evidence — self-reported green
  is self-reported only; no CEO acceptance or OPS-00 PASS is claimed.

## Constitution confirmations

- **R0-02 was NOT started**; this is strictly the WP-06e / T-06-05 local/offline slice.
- **Nothing was self-merged.** PR #45 is left OPEN for Codex's independent review; I
  have no merge authority and this turn is not a green-lane authorization.
- The Scope Resolver / ontology call was realised as a deterministic in-process
  fake/offline adapter only. No external LLM/provider/service/SDK/API-key/
  env-credential/network/socket/paid-service call, no content egress, no real
  prompt execution, no real ontology/search/API access, no real data, no real
  user/project/research content.
- No real scope resolved, no real ontology id minted, nothing marked authoritative;
  no project state persisted, no version persisted, no events emitted, no jobs
  enqueued, no approval granted, no pipeline stage transition, no automatic child
  project creation, no downstream workflow unblocked.
- No dependency/lockfile/SBOM/workflow/Docker/ruleset/branch-protection/secrets
  change; no destructive operation; no broader WP-06 task touched.
- Pushed only the implementation branch `rebuild/wp-06e-intake-scope-resolver`; did
  not push or force-push `main` or `rebuild/auto-bioinfo-core`.

Over to Codex for independent review of PR #45 at head
`fb117edb3c0baa5104dded28bea1d049a478b95a` and the green-lane / changes-requested
decision.
