---
turn: 0249
from: CC
to: CODEX
type: REPORT
ref: WP-05i-pr39-rate-window-fix
status: OPEN
date: 2026-06-28
---

# REPORT - WP-05i / PR #39 rate-limit window pairing blocker fixed

Handles turn 0248 (CODEX CHANGES_REQUESTED). The rate-limit window ambiguity
blocker is fixed on PR #39; review fix only, no scope expansion.

## New head

- Branch: `rebuild/wp-05i-gateway-reliability-policy`
- New full HEAD SHA: `3435ee0e9a0eb6b7d3d987cd0253970ea3ef254d`
- Previous head (reviewed in turn 0248): `3eb7f0a8bf6b1f10d08b88c150942a896a8138d0`
- Commit: `fix(agent-gateway): fail closed on ambiguous rate-limit window pairing (WP-05i / PR #39)`

## Changed files (vs base `f95c964ae947e7d16c37ad4340666120219c1d5a`)

- `auto_bioinfo/agent_gateway/reliability_policy.py`
- `auto_bioinfo/agent_gateway/__init__.py`
- `tests/test_reliability_policy.py`

(Same three files as the original WP-05i diff; no new files, dirs, or surfaces.)

## What was wrong (turn 0248 blocker)

The rate dimension validated `p.rate_window` and `r.window` as bounded
references but never required them to be **paired or equal** when engaged. So a
`w-1m` policy could be satisfied by a `w-1h` count, by a count with no declared
window, or (more broadly) by a policy that declared no window at all — each
silently returned `allowed`, making the rate-limit decision ambiguous.

## Fix (code location per requirement)

1. **New stable reason code** — `CODE_AMBIGUOUS_RATE_WINDOW =
   "RELIABILITY_AMBIGUOUS_RATE_WINDOW"`, added to `LIMIT_FACT_CODES`
   (`reliability_policy.py`), so it flows into `REASON_CODES` and the
   uniqueness/prefix invariant test. Re-exported from `agent_gateway/__init__.py`
   (import + `__all__`).
2. **Pairing enforced when the rate dimension is engaged**
   (`reliability_policy.py`, step 11 "engaged-dimension pairing", rate branch):
   after the existing `CODE_MISSING_LIMIT` check, the evaluator now fails closed
   with `CODE_AMBIGUOUS_RATE_WINDOW` unless `p.rate_window` and `r.window` are
   **both present and identical**:
   ```python
   if p.rate_window is None or r.window is None or p.rate_window != r.window:
       return reject(CODE_AMBIGUOUS_RATE_WINDOW)
   ```
   This is the deliberately stricter fail-closed alternative invited by turn
   0248 point 3: an engaged rate decision is now always judged against one
   defined, matching window — covering policy `rate_window` + mismatched request
   `window`, policy `rate_window` + missing request `window`, request `window` +
   missing policy `rate_window`, and rate engaged with no window on either side.
3. **Docstrings** (module fail-closed bullet + `evaluate_reliability`
   pairing paragraph) updated to record the new fail-closed condition.

The windows are still validated as bounded printable-ASCII tokens at step 4
(optional references) before the equality check, so the comparison only ever
runs on `None`-or-valid tokens. Change stays pure / offline / inert: no new
deps, no network/provider/tool/clock/sleep/retry/persistence, no T-05-10+ scope.

## Focused regression tests (new)

`tests/test_reliability_policy.py`, new class `RateWindowPairingTest`:
- `test_mismatched_windows_fail_closed` — policy `w-1m` + request `w-1h` → REJECTED / `CODE_AMBIGUOUS_RATE_WINDOW`.
- `test_policy_window_with_missing_request_window_fails_closed` — policy `w-1m` + request `window=None` → REJECTED.
- `test_request_window_with_missing_policy_window_fails_closed` — request `w-1m` + policy `rate_window=None` → REJECTED.
- `test_rate_engaged_without_any_window_fails_closed` — neither side declares a window → REJECTED.
- `test_matching_windows_remain_allowed_under_limit` — matching `w-1m`/`w-1m` under `max_requests` → ALLOWED, engaged `(rate_limit,)`.
- `test_matching_windows_still_deny_over_limit` — matching windows, count over ceiling → DENIED / `CODE_RATE_LIMIT_EXCEEDED`.

Also updated `test_policy_shaped_mapping_is_accepted` so its rate-only mapping
now declares `rate_window="w-1m"` with the request `window="w-1m"` (it formerly
relied on the now-rejected unpaired-window behavior); still asserts ALLOWED /
engaged `(rate_limit,)`.

## Test command + real result

```
source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform
python3 -m unittest discover -t . -s tests -p "test_*.py"
```
Result: `Ran 1154 tests in 44.093s` → `OK`.
Module-focused: `python3 -m unittest tests.test_reliability_policy -v` → `Ran 63 tests` → `OK`.

`git diff --check` → clean (no output; "diff-check-clean").

## PR state

`gh pr view 39`: state OPEN, non-draft, base `rebuild/auto-bioinfo-core`,
headRefOid `3435ee0e9a0eb6b7d3d987cd0253970ea3ef254d`, mergeable MERGEABLE,
mergeStateStatus BLOCKED (awaiting independent review/required-check rollup at
the new head — CI not yet re-run at report time).

## Hard-stop / guardrail check

- R0-02 was **not** started; only the authorized WP-05i / PR #39 review fix was done.
- Nothing was self-merged; no merge attempted. No push to `main` or
  `rebuild/auto-bioinfo-core`. Only the implementation branch was pushed.
- No real provider/tool/network/clock/sleep/retry/cost-API call, no persistence,
  no deps/lockfiles/SBOM/workflows/Docker/rulesets/secrets, no content egress,
  no real data. No HARD STOP crossed.
- Self-reported green only; no claim of CEO acceptance or OPS-00 PASS.

Over to CODEX for independent re-review of head `3435ee0e9a0eb6b7d3d987cd0253970ea3ef254d`.
