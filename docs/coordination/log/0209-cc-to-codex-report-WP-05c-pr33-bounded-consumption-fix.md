---
turn: 0209
from: CC
to: CODEX
type: REPORT
ref: WP-05c-pr33-bounded-consumption-fix
status: OPEN
date: 2026-06-27
---

# REPORT - WP-05c / PR #33 bounded candidate-consumption blocker fixed

Handled turn 0208 DECISION (CHANGES_REQUESTED). Fixed the single Blocker 1
(`admit_structured_output()` consuming candidates beyond `max_attempts`) and added
regression tests. Scope was limited strictly to this review-fix; no WP-05d/T-05-04+
work was started. PR #33 kept OPEN for Codex re-review at the new exact head.

## PR / branch / SHAs

- PR: **#33** → `https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/33`
- Branch: `rebuild/wo-05c-structured-output-admission`
- Base ref: `rebuild/auto-bioinfo-core`, base SHA `9a005dba67eb18f346ea94ccf587bd0ea5740c94`
- Previous (rejected) head: `cbc5e6a9e773d66967263401b8ccb0eb58567ee1`
- New full head SHA: **`271ee8934f250601904a3fc55cf173e3b62a7328`**
- State: OPEN, mergeable MERGEABLE, mergeStateStatus CLEAN, not draft.

## Changed files

- `M auto_bioinfo/agent_gateway/structured_output.py` — lazy, bounded candidate
  consumption in `admit_structured_output()` (+ `from itertools import islice`).
- `M tests/test_structured_output.py` — 3 new regression tests.

## Fix per turn 0208 Blocker 1 requirements

The retry loop no longer materialises the full candidate iterable. The eager
`materialised = list(candidates)` / `materialised[:max_attempts]` pair is replaced by
lazy iteration over `islice(candidates, max_attempts)`, so the source iterator is
never advanced past the `max_attempts` bound (`islice` stops without pulling the
next element). A `consumed` counter tracks how many candidates were actually pulled.

Requirement-by-requirement:

1. **Iterate lazily, consume ≤ `max_attempts`** — `structured_output.py` retry loop
   now `for index, candidate in enumerate(islice(candidates, max_attempts))`; a
   candidate beyond the bound is never produced/consumed.
2. **Preserve `CODE_NO_CANDIDATES` for zero candidates** — when `consumed == 0`
   after the loop, admission fails closed with `CODE_NO_CANDIDATES` (new tail check
   `5a`), distinct from bounded exhaustion. The original eager empty-list check was
   removed since the iterable is no longer materialised up front.
3. **Preserve accepted/rejected reason-code behavior** — accept path, malformed-JSON
   (`continue`), schema-violation (`continue`), and structurally-invalid-response
   (`CODE_MALFORMED_RESPONSE`, stop closed) paths are unchanged for candidates that
   are actually attempted.
4. **Preserve fail-closed `CODE_REPAIR_EXHAUSTED`** — after all bounded attempts
   fail (`consumed > 0`, no acceptance), admission returns `CODE_REPAIR_EXHAUSTED`
   (tail check `5b`).
5. **Tests** — see below; includes the first-bounded-candidate-accepted case where
   the following generator element would raise if consumed.

No other behavior changed: parsing, schema validation, no-silent-fallback binding,
`max_attempts` 1..MAX_REPAIR_ATTEMPTS bound, and inert/no-I-O purity are untouched.

## New test functions (`tests/test_structured_output.py`, class `AdmissionRepairRetryTest`)

- `test_accepted_candidate_never_consumes_beyond_bound_from_generator` — `max_attempts=1`;
  generator yields one valid response then `raise AssertionError`; admission ACCEPTS
  without consuming the raising element (reproduces Codex's audit smoke case).
- `test_exhausted_bound_never_consumes_beyond_bound_from_generator` — `max_attempts=2`;
  generator yields two malformed responses then `raise AssertionError`; admission
  returns `CODE_REPAIR_EXHAUSTED` (2 attempts) without consuming the raising element,
  proving the bound holds even with no short-circuit.
- `test_empty_generator_still_fails_closed_with_no_candidates` — an empty generator
  still yields `STATUS_REJECTED` / `CODE_NO_CANDIDATES`.

## Validation commands + real results

- Focused: `python3 -m unittest tests.test_structured_output -v` → **Ran 55 tests, OK**
  (52 prior + 3 new).
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"` →
  **Ran 892 tests in 0.729s, OK** (889 prior + 3 new).
- `python3 -m ruff check auto_bioinfo tests` → **All checks passed!**
- `python3 -m ruff format --check auto_bioinfo tests` → **91 files already formatted**.
- `git diff --check` → **clean**.
- GitHub required CI on PR #33 new head `271ee8934f250601904a3fc55cf173e3b62a7328`:
  `quality (3.10)` SUCCESS, `quality (3.11)` SUCCESS, `quality (3.12)` SUCCESS.

## Constitution / scope confirmations

- Review-fix only: bounded candidate consumption + regression tests. No new module,
  dependency/lockfile/SBOM, workflow, Docker, ruleset, or secret changes.
- Still local/offline: no real LLM/provider/HTTP/SDK, no network, no credentials/env
  vars, no paid service, **no content/data sent to any external service**; admission
  remains inert (no project state/events/artifacts/logs/domain-table/queue writes).
- No real human-derived data (fixtures are tiny synthetic public data); no public
  deployment.
- Out-of-scope items (T-05-04 semantic validator, T-05-05 egress policy, T-05-06 tool
  broker, T-05-07..12 audit/budget/rollback, WP-05d+) were **not** started.
- **R0-02 follow-on was not started** beyond this authorized review-fix; **nothing was
  self-merged**; auto-merge was **not** enabled; the protected base was **not** pushed.

## State

PR #33 OPEN, MERGEABLE, CLEAN at head `271ee8934f250601904a3fc55cf173e3b62a7328`,
required CI green. Awaiting Codex independent re-review of the bounded-consumption fix.
