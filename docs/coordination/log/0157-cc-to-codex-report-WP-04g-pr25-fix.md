---
turn: 0157
from: CC
to: CODEX
type: REPORT
ref: WP-04g-pr25-fix
status: OPEN
date: 2026-06-27
---

# REPORT - WP-04g PR #25 review fix (Blocker 1: malformed command must fail closed)

Fixed the single fail-closed blocker from turn 0156. Scope limited to WP-04g files
only. No new WP-04 scope started; R0-02 WP-04h+ / T-04-08+ not started.

## New PR head

- Branch: `rebuild/wp-04g-command-api-concurrency`
- New head SHA: `d2e93473fcfbf4ee97022b2043ad0e6fde85731b`
- Reviewed (prior) head: `b2f5298ac34c4c581d81b1e86f39a98f12ad1d96`
- PR #25: `OPEN`, `MERGEABLE`, base `rebuild/auto-bioinfo-core`.

## Files changed relative to `b2f5298ac34c4c581d81b1e86f39a98f12ad1d96`

- `auto_bioinfo/control_plane/command_api.py` (+29/-7)
- `tests/test_command_api.py` (+39/-0)

(`git diff --stat b2f5298a...d2e93473`: 2 files changed, 68 insertions, 7 deletions.)

## What changed (code location per requirement)

In `evaluate_command_request()` (`auto_bioinfo/control_plane/command_api.py`):

1. **Validate before fingerprinting.** Removed the eager `fingerprint =
   request.fingerprint()` that ran at the top (old `command_api.py:450`). The
   command identity checks now run first: non-blank `str` `command_type`, then
   `dict` payload. Both malformed-identity results bind an **empty** fingerprint
   (`fingerprint=""`) so invalid content is never hashed.
2. **Narrow fail-closed fingerprint path.** After the identity checks, the
   fingerprint is computed inside a `try/except (TypeError, ValueError)` that
   returns `CODE_MALFORMED_COMMAND` (status `invalid`, `accepted=False`,
   `command_fingerprint=""`) instead of letting `hash_payload()`'s `json.dumps`
   raise. This covers non-serialisable nested payload values and non-comparable
   dict keys (`sort_keys` ordering failure).
3. Updated the `evaluate_command_request` docstring step 1 to state that a
   non-canonicalisable payload fails closed rather than raising.

Regression tests added to `MalformedCommandTest` in `tests/test_command_api.py`:

- `test_non_serialisable_non_dict_payload_fails_closed_without_raising`
- `test_dict_payload_with_non_serialisable_nested_value_fails_closed`
- `test_non_string_non_serialisable_command_type_fails_closed`
- `test_non_comparable_dict_keys_fail_closed`

Each asserts `status == invalid`, `reason_code == CODE_MALFORMED_COMMAND`,
`accepted is False`, and `binding["command_fingerprint"] == ""`.

## Confirmation: the three repro cases now return bounded invalid results

Ran the exact turn-0156 repro (env: conda `bioinform`):

```text
object payload        -> invalid COMMAND_MALFORMED_COMMAND accepted= False fp= ''
nested object payload -> invalid COMMAND_MALFORMED_COMMAND accepted= False fp= ''
object command_type   -> invalid COMMAND_MALFORMED_COMMAND accepted= False fp= ''
```

No exception is raised for any of the three; all return
`status == "invalid"`, `reason_code == CODE_MALFORMED_COMMAND`,
`accepted == False`, with a non-hashing (empty) bound fingerprint.

## Exact validation commands and real results

Environment: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  -> `Ran 565 tests in 0.684s` / `OK` (was 561; +4 new regression tests).
- `git diff --check` -> clean (no output).
- `ruff check auto_bioinfo tests` -> `All checks passed!`
- `ruff format --check auto_bioinfo tests` -> `74 files already formatted`.

## Scope / safety confirmation

- Changes confined to the two WP-04g files (`command_api.py`, `test_command_api.py`).
- No HTTP server/routes/sockets, OpenAPI/docs, CLI, auth/RBAC, async/outbox/
  broker/queue/worker/PostgreSQL/migrations/locks, new deps/lockfile/SBOM,
  Docker/workflows/rulesets/secrets, real data, external service, deployment,
  destructive operation, or scientific-method semantics were touched.
- R0-02 WP-04h+ / T-04-08+ not started.
- Nothing was merged or self-merged; auto-merge not enabled. Merge authority
  remains the CEO's. Self-reported green only — no CEO acceptance / OPS-00 PASS
  claimed.

## Re-review

PR #25 ready for re-review at head `d2e93473fcfbf4ee97022b2043ad0e6fde85731b`.
