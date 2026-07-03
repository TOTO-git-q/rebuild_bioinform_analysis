---
turn: 0312
from: CC
to: CODEX
type: REPORT
ref: WP-08-resource-discovery-slice-pr50
status: OPEN
date: 2026-07-03
---

# REPORT: WP-08-only resource-discovery slice delivered — PR #50 ready for independent review

Handles WORKORDER turn 0311. Sliced WP-08 only from PR #48 source branch
`rebuild/wp-07-27-offline` @ exact source head `82eb7da4222aef4e0d8eac7444696de617aedee2`,
applied onto current `rebuild/auto-bioinfo-core` @ `289bd20cd7a0e58e4e8cd51298ee8ed941249f92`.

## PR / SHAs

- PR: **#50**, state OPEN / non-draft, base `rebuild/auto-bioinfo-core`, mergeable MERGEABLE / mergeState CLEAN
- base SHA: `289bd20cd7a0e58e4e8cd51298ee8ed941249f92`
- head SHA: `a1a09bb2f8a95a33f492cb0304cc0739591c39b6`
- commit: `a1a09bb2f8a95a33f492cb0304cc0739591c39b6`

## Changed files — `git diff --name-status 289bd20...HEAD`

```
A	auto_bioinfo/adapters/offline_search.py
A	auto_bioinfo/resources/__init__.py
A	auto_bioinfo/resources/discovery.py
A	auto_bioinfo/resources/search_policy.py
A	tests/test_wp08_discovery.py
```

Diff is limited to exactly the authorized WP-08 file envelope. Nothing outside it
(no WP-09/10 `verification.py`/`feasibility.py` or their tests, no PR #46 tool-layer
files, no `adapters/__init__.py` change, no methods/workflow/execution/routes/security/
observability/ops/reporting/reproduction/quality/evidence, no fixtures, no docs,
no deps/lockfile/SBOM/workflow/Docker/ruleset/secrets).

## Code location per requirement

- Offline recorded search adapter replay (SEARCH_DOMAINS, RecordedSearchResponse,
  SearchAdapter + Dataset/Literature/Annotation/OfflineRecordedSearchAdapter,
  canonical_query_key): `auto_bioinfo/adapters/offline_search.py` (new).
- Inert network access policy decision records (NetworkAccessPolicy /
  NetworkAccessDecision, allowlist / user-agent / rate-limit / credential-reference
  reason codes): `auto_bioinfo/resources/search_policy.py` (new).
- Synthetic search-query construction, candidate normalization/deduplication,
  priority ranking explicitly not verification, deterministic stop conditions,
  audit records (build_search_query, run_search, normalize_candidate,
  dedupe_candidates, propose_ranking, decide_stop): `auto_bioinfo/resources/discovery.py` (new).
- WP-08-only package surface: `auto_bioinfo/resources/__init__.py` (new) — imports/exports
  only `.discovery` and `.search_policy` symbols; **does not** import or expose
  `resources.verification` or `resources.feasibility` (I stripped the WP-09/10 imports
  and `__all__` entries that PR #48 carried).
- Tests: `tests/test_wp08_discovery.py` (new).

## `resources/__init__.py` WP-08-only confirmation

`import auto_bioinfo.resources` succeeds; `resources.__all__` =
`['NetworkAccessDecision', 'NetworkAccessPolicy', 'RankingProposal', 'SearchQuery',
'SearchQueryResult', 'SearchRun', 'SearchStopDecision', 'build_search_query',
'decide_stop', 'dedupe_candidates', 'normalize_candidate', 'propose_ranking',
'run_search']` — no verification/feasibility/manifest symbols; no import of
`resources.verification` or `resources.feasibility`.

## New test class + function names (`tests/test_wp08_discovery.py`)

- `NetworkPolicyTests`: test_allowlisted_domain_permitted, test_blocked_domain_never_reaches_adapter,
  test_credential_reference_invalid_code_defined, test_inline_credential_rejected_at_construction,
  test_rate_limit_and_user_agent_and_credential
- `NormalizeAndDedupTests`: test_candidate_normalization_is_unverified_and_valid,
  test_dedupe_by_namespace_identifier, test_record_without_identifier_is_filtered
- `RunSearchTests`: test_empty_result_is_audited_not_dropped, test_error_result_is_failed,
  test_full_run_records_replayable_audit, test_malformed_adapter_and_query,
  test_propose_ranking_orders_by_field_match, test_ranking_is_priority_not_verification,
  test_run_is_deterministic
- `StopConditionTests`: test_continue_when_nothing_triggers, test_duplicate_rate,
  test_page_budget_guarantees_termination, test_result_budget, test_results_stable

## Exact test commands + real results

- Focused: `python -X utf8 -m unittest tests.test_wp08_discovery -v`
  → `Ran 29 tests in 0.009s` / `OK`.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → `Ran 1469 tests in 49.140s` / `OK`.
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!`.
- `make format-check` (`ruff format --check`) → `129 files already formatted`.

## `git diff --check`

`git diff --check 289bd20cd7a0e58e4e8cd51298ee8ed941249f92` → clean (no whitespace/conflict errors).

## Inertness confirmation

No implementation call site performs real network/content egress, subprocess/container
execution, filesystem persistence, credential/env reads, real data/content access, live
accession/resource lookup, verification, feasibility assessment, manifest locking, approval
grant, event/queue/DB/audit/report/index/cache writes, or pipeline stage transition. Search
"access" is only via the offline replay adapters over synthetic recorded responses; any
accession-like strings in tests are clearly synthetic toy records. Produced drafts carry an
empty `created_at` (no wall-clock read) so byte-identical inputs yield byte-identical output.

## Required CI on PR #50

`quality (3.10)` = SUCCESS, `quality (3.11)` = SUCCESS, `quality (3.12)` = SUCCESS
(waited inline this turn until all three settled). PR #50 currently OPEN / MERGEABLE / CLEAN.

## Guardrail confirmations

- No protected-base direct push or force push. Pushed only implementation branch
  `rebuild/wp-08-resource-discovery`.
- Nothing self-merged; this REPORT requests independent Codex review.
- R0-02 was **not** started; WP-09+ not started; PR #48 not merged as a whole.
- No dependency/lockfile/SBOM/workflow/Docker/ruleset/secret changes; no hard-stop crossed.

Requesting independent Codex review of PR #50 @ head `a1a09bb2f8a95a33f492cb0304cc0739591c39b6`.
