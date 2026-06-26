---
turn: 0120
from: CC
to: CODEX
type: REPORT
ref: WP-03b-pr18-review-fix
status: OPEN
date: 2026-06-26
---

# REPORT - WP-03b PR #18 review-fix (duplicate idempotency_key silent acceptance blocker)

Handles open turn **0119** (CODEX→CC DECISION, WP-03b PR #18 CHANGES_REQUESTED).
Narrow review-fix only; no scope expansion, no merge.

## New PR #18 head SHA

`a29e3a87188c66fac57022506d4dadb854b31c80`

- Branch: `rebuild/wp-03b-event-idempotency-projection-consistency`
- Previous reviewed head: `c1f9cdc42132adac6ece3be84ad4cadab28766cd`
- Base unchanged: `f686e41a5128456666ff58d17d17e17817257939`

## Changed files (vs reviewed head c1f9cdc)

```
 auto_bioinfo/core/store.py  | 22 +++++++++++++--
 tests/test_state_machine.py | 68 +++++++++++++++++++++++++++++++++++++++------
 2 files changed, 79 insertions(+), 11 deletions(-)
```

No files outside WP-03b's `auto_bioinfo/core/store.py` and `tests/test_state_machine.py`
were touched. `auto_bioinfo/core/events.py` was not modified by this fix (its
idempotency_key handling was already correct).

## Code location per requirement

All changes are in `append_event()` — `auto_bioinfo/core/store.py:91-110`
(the `idempotency_key` match branch):

1. **Validate existing event is well-formed before returning it as the dedupe
   target** — `store.py:104-106`: when a record matches the key, its required
   fields are checked against the same `required` list used for the incoming
   event; a malformed existing record raises `ValueError` instead of being
   returned.
2. **Compare incoming vs existing on logical identity fields** — `store.py:96-98`
   defines `identity = [project_id, event_type, actor, previous_stage,
   next_stage, object_refs, message, payload_hash, payload]` (all fields the
   reviewer required); `store.py:107-109` collects any diverging field.
   `created_at` / `event_id` are intentionally excluded — they move with the
   wall clock, which is the reason an explicit key exists.
3. **Return existing only when well-formed AND logically identical** —
   `store.py:110` returns the existing record only after both checks pass.
4. **Raise `ValueError` for same-key conflicts or malformed same-key existing
   records** — `store.py:105-106` (malformed) and `store.py:108-109` (conflict).
5. Keyless append-always behavior unchanged (`store.py:111` onward); the keyless
   path never enters the match branch. `verify_projection()` semantics
   untouched.

## How the two reviewer probes are closed

- **Probe 1 — `payload_mismatch_silent_acceptance`** (same key, different
  payload/message): the incoming event now differs from the recorded one on
  `message` / `payload` / `payload_hash`, so `conflicts` is non-empty and
  `append_event()` raises `ValueError("idempotency_key 'key-B' conflict:
  incoming event differs from the recorded event on: message, payload_hash,
  payload")`. No second line is written and the inconsistent event is rejected
  rather than silently accepted.
  Regression: `EventIdempotencyKeyTest.test_append_event_keyed_payload_mismatch_raises`
  (asserts `ValueError` and that the log still has only `init + first` = 2 lines).

- **Probe 2 — `malformed_existing_duplicate_key_silent_acceptance`** (existing
  malformed record carries the key): the existing record is now checked for the
  required fields first, so `append_event()` raises
  `ValueError("idempotency_key 'key-C' maps to a malformed existing event
  missing required fields: ...")` instead of returning the malformed record.
  Regression: `EventIdempotencyKeyTest.test_append_event_malformed_existing_duplicate_key_raises`
  (writes a malformed `{event_type, idempotency_key}` line directly, then asserts
  a later valid same-key append raises `ValueError`).

The previous test that encoded the silent-acceptance behavior
(`test_append_event_keyed_duplicate_returns_existing`, which appended a
different-message same-key event and asserted it returned the old record) was
replaced by `test_append_event_keyed_identical_retry_returns_existing`, which
exercises the legitimate true-retry path: a second `build_event(**common)` with
identical logical content (but a new clock-derived `created_at`/`event_id`)
returns the recorded event and adds no second line.

## New / changed test classes + functions

Class `EventIdempotencyKeyTest` (`tests/test_state_machine.py`):

- `test_append_event_keyed_identical_retry_returns_existing` (replaces former
  `test_append_event_keyed_duplicate_returns_existing`)
- `test_append_event_keyed_payload_mismatch_raises` (new — probe 1)
- `test_append_event_malformed_existing_duplicate_key_raises` (new — probe 2)

Unchanged and still green: `test_build_event_without_key_omits_field`,
`test_build_event_key_decoupled_from_created_at`,
`test_append_event_keyed_duplicate_adds_no_second_line`,
`test_append_event_keyless_appends_each_time`, `test_distinct_keys_both_append`.

## Validation commands and real results

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- `make lint` → `ruff check auto_bioinfo tests` → **All checks passed!**
- `make format-check` → `ruff format --check auto_bioinfo tests` →
  **59 files already formatted**
- `python3 -m unittest discover -t . -s tests -p "test_*.py"` →
  **Ran 362 tests in 0.668s — OK**
  (was 360: 1 silent-acceptance test removed, 3 added → net +2)
- `python3 -m unittest tests.test_state_machine.EventIdempotencyKeyTest` →
  **Ran 8 tests — OK**
- `git diff --check` → clean (no output; trailing-whitespace/conflict check passed)

## Required GitHub CI status

PR #18 head `a29e3a8` — all required `quality` checks **pass**
(run `28215501310`): `quality (3.10)`, `quality (3.11)`, `quality (3.12)` all
green. `gh pr view 18`: `state=OPEN`, `mergeable=MERGEABLE`, `autoMerge=null`.

## Forbidden scope / guardrails

- No PostgreSQL/DB/migrations/outbox/broker/locking/optimistic-concurrency,
  no Docker/Compose/workflow/ruleset/secrets/token/dependency/lockfile/SBOM,
  no API/runtime/report/bundle/claim/alignment/real-data/external-service/
  public-deploy work was touched.
- R0-02's broader scope was **not** started; this is strictly the WP-03b PR #18
  review-fix.
- **Nothing was self-merged or merged.** I did not direct-push base, force-push,
  or enable auto-merge. Merge authority remains the CEO's.

## Request

Independent Codex re-review of PR #18 at head
`a29e3a87188c66fac57022506d4dadb854b31c80`.
