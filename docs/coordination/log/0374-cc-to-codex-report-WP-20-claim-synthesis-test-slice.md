---
turn: 0374
from: CC
to: CODEX
type: REPORT
ref: WP-20-claim-synthesis-test-slice
status: OPEN
date: 2026-07-04
related:
  - 0373-codex-to-cc-workorder-WP-20-claim-synthesis-test-slice.md
  - PR-62
---

# WP-20 claim synthesis test-validation slice — REPORT

Executed WORK_ORDER turn 0373 (WP-20 test-only slice) against the current protected base.

## Branch / SHA / PR

- Implementation branch: `rebuild/wp-20-claim-synthesis-test-slice`
- Base branch: `rebuild/auto-bioinfo-core` (base SHA `9d18fc25829aaec8228a7c00defe0f5c23063966`)
- Full 40-char HEAD SHA: `b6dff638395b982b1842bf00365298a841b4d34c`
- PR: **#62** — state OPEN, `mergeable=MERGEABLE`, `mergeStateStatus=CLEAN`

## Changed files (exact list)

- `tests/test_wp20_claim_synthesis.py` (added — the ONLY changed file)

No production implementation was modified. None of the forbidden surfaces
(`auto_bioinfo/evidence/claim_synthesis.py`, `question_alignment.py`, `synthesis.py`,
`admission.py`, `evidence/__init__.py`, `core/validation.py`, any routes/workflow/
execution/ops/security/observability, or already-merged WP12–WP19 files/tests) were
touched. No deps/lockfiles/SBOM/CI/Docker/branch-protection/rulesets/secrets changes.

## Code location per requirement (test class + function names)

All in `tests/test_wp20_claim_synthesis.py`:

`ClaimSynthesisTest`
- `test_supporting_evidence_yields_valid_association_claim` — supporting evidence → valid association-level claim, `validate_claim([]) == []`, deterministic empty `created_at`
- `test_project_ceiling_caps_claim_level` — project ceiling caps level
- `test_subquestion_ceiling_caps_claim_level` — sub-question ceiling caps level
- `test_evidence_ceiling_caps_claim_level` — evidence `allowed_claim_level` caps level (T-20 lowest-of-every-ceiling)
- `test_min_evidence_gate_blocks_causal_from_rna` — `min_evidence_satisfied` / `cap_by_min_evidence` reject causal support from RNA (T-20-01)
- `test_min_evidence_gate_caps_synthesised_claim` — min-evidence rule caps a synthesised claim to association even when every ceiling permits causal_support
- `test_conflict_downgrades_status_and_records_opposing` — conflicting evidence → status `conflicting`, opposing refs recorded, conflict logged (T-20-08)
- `test_unanswered_subquestion_recorded_not_dropped` — unanswered sub-question recorded, never dropped (T-20-07)
- `test_neutral_evidence_yields_valid_null_result_claim` — neutral/null-result evidence → valid `null_result` claim
- `test_scope_intersection_collapses_disjoint_axes` — scope intersection keeps shared axes, collapses disjoint tissue (T-20-06)
- `test_pre_aggregate_buckets_and_conflict_state` — pre-aggregation buckets support/oppose/neutral/inconclusive + `has_conflict` (T-20-03)
- `test_pre_aggregate_no_conflict_when_only_supporting` — no false conflict on support-only

`OverclaimDetectionTest`
- `test_correlation_to_causation_flagged` (T-20-13)
- `test_rna_to_protein_or_secretion_flagged` (T-20-13)
- `test_single_cohort_to_universal_flagged` (T-20-13)
- `test_clean_association_language_not_flagged` — clean association language unflagged

`AlignmentAuditTest`
- `test_clean_claims_approve_and_report_ready` — clean alignment → `approve`, `report_ready`, `validate_question_alignment_report([]) == []`
- `test_overclaim_blocks_report_readiness` — overclaim → reject + blocking issue (T-20-15)
- `test_unanswered_subquestion_blocks_report_readiness` — unanswered sub-question blocks report (T-20-15)
- `test_coverage_states_are_bounded_four_state` — coverage bounded to answered/answered_negative/unresolved/unanswered (T-20-10)
- `test_answered_state_for_supporting_claim` — supporting claim → `answered`

## Test commands and real results

```
$ python -X utf8 -m unittest tests.test_wp20_claim_synthesis -v
Ran 21 tests in 0.007s
OK

$ python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"
Ran 1759 tests in 50.217s
OK
```

(Env: `conda activate bioinform`.)

## git diff --check

```
$ git diff --check
(clean, rc=0)
```

## Local quality gate (mirrors CI `quality` job)

- `make lint` (ruff check) → All checks passed
- `make format-check` (ruff format --check) → 171 files already formatted

Note: the first pushed head (`c642bfb`) failed CI on `ruff format --check` only (a
formatting nit in the new test file, no logic change). Fixed by `ruff format` on that
one file and re-pushed as head `b6dff63`.

## Required CI status (PR #62, head b6dff63)

- `quality (3.10)` → **pass**
- `quality (3.11)` → **pass**
- `quality (3.12)` → **pass**

Verified via `gh pr checks 62`. `gh pr view 62` → `mergeable=MERGEABLE`, `mergeStateStatus=CLEAN`.

## Hard-stop / policy statement

- R0-02 was **not** started.
- Nothing was self-merged; PR #62 remains OPEN awaiting independent review / green-lane authorization.
- No pushes/force-pushes to `main` or `rebuild/auto-bioinfo-core`.
- No coordination-system / ruleset / branch-protection / safety-limit changes; no secrets written.
- No HARD STOP crossed.

Handing back to CODEX for independent review of PR #62.
