---
turn: 0117
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-03b
status: OPEN
date: 2026-06-26
---

# WORK ORDER - WP-03b Event-Log Idempotency Key And Projection Consistency Hardening

## Context

WP-03a is merged in PR #17 at merge commit `f686e41a5128456666ff58d17d17e17817257939`.

WP-03a produced the audit/split artifact and closed the immediate projection replay fail-closed gaps. Its proposed next slice is accepted as the next narrow phase-0 implementation slice: event-log idempotency key support plus transition/snapshot consistency hardening, without introducing DB infrastructure.

## Base

- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA: `f686e41a5128456666ff58d17d17e17817257939`
- Suggested branch: `rebuild/wp-03b-event-idempotency-projection-consistency`

## Scope

Implement the narrow phase-0 WP-03b slice only:

1. Add optional explicit `idempotency_key` support to event construction in `auto_bioinfo/core/events.py`.
   - The key must be decoupled from `created_at`.
   - Existing callers/events without a key must keep current backward-compatible behavior.
2. Harden `auto_bioinfo/core/store.py` event append behavior.
   - `append_event` should be idempotent when a matching `idempotency_key` is present.
   - Duplicate-key re-append must not add a second log line.
   - Duplicate-key re-append should return the existing event/result consistently with the current local store style and mirror the `runs.py` idempotency pattern where applicable.
3. Add a projection drift detector.
   - Prefer a focused `verify_projection()` surface in `auto_bioinfo/core/store.py` if it fits the current module shape.
   - Detection only: return/report precise mismatches for tampered snapshots.
   - No auto-repair, no mutation of snapshots during verification.
4. Add focused coverage in `tests/test_state_machine.py` or the smallest existing test module that already owns this behavior.

## Acceptance Criteria

- Duplicate-key re-append adds no second event-log line.
- Duplicate-key re-append returns the existing event/result deterministically.
- Events without `idempotency_key` preserve current behavior and backward compatibility.
- Healthy projection verification reports no mismatch.
- Tampered snapshot/projection verification reports a precise mismatch list.
- Existing transition legality and fail-closed replay tests from WP-03a remain green.
- Required GitHub CI quality 3.10 / 3.11 / 3.12 is green before reporting ready for Codex review.

## Required Validation

Run and report:

- Targeted state/event/store tests covering changed behavior.
- Full unittest discovery.
- `make lint` if available.
- `make format-check` if available.
- `git diff --check`.
- GitHub required CI quality 3.10 / 3.11 / 3.12 status for the PR head.

## Forbidden Scope

Do not implement or modify:

- PostgreSQL, database adapters, database migrations, outbox dispatcher, broker/queue, multi-writer locking, or optimistic concurrency.
- Docker, Compose, container images, `.github/workflows`, rulesets, branch protection, secrets, token permissions, dependency/lockfile/SBOM changes.
- API layer, WP-04+, runtime task execution, formal evidence admission, report generation, bundle materialization/export, claim synthesis, or alignment engine behavior.
- Real data, external services, paid services, public deployment, public publishing, or release automation.
- Direct push to `rebuild/auto-bioinfo-core`, force push, self-merge, or direct merge bypassing PR + required CI + Codex independent review + GitHub auto-merge.

If this slice appears to require any forbidden item, stop and write a BLOCKER/QUESTION turn instead of widening scope.

## Report Back

Open a PR and report:

- PR number;
- base/head SHA;
- exact files changed;
- concise implementation summary;
- validation commands and results;
- required GitHub CI status;
- confirmation that no forbidden scope was touched.
