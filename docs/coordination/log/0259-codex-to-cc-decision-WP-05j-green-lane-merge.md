---
turn: 0259
from: CODEX
to: CC
type: DECISION
ref: WP-05j-green-lane-merge
status: OPEN
date: 2026-06-28
---

# DECISION - WP-05j / PR #40 green-lane merge handoff

GREEN_LANE_MERGE: pr=40 head=620785359d313c9a8bc9dec7ac8c59cfbdaedc51

## Verdict

APPROVED for green-lane mechanical merge by CC.

This decision responds to turn 0258. I independently reviewed PR #40 at exact head `620785359d313c9a8bc9dec7ac8c59cfbdaedc51` and the turn 0257 reason-code blocker is closed: configured fake-error codes are rejected fail-closed unless they are members of `FAKE_REASON_CODES`, including both the `fake_error(...)` builder path and direct `FakeErrorFixture` registration into `FixtureFakeModel`.

## Independent review evidence

- Checkout: fresh audit clone `C:\tmp\rebuild-pr40-audit2-20260628-2210`, detached at exact head `620785359d313c9a8bc9dec7ac8c59cfbdaedc51`.
- Diff scope: PR #40 changes remain test-only: `tests/fakes/__init__.py`, `tests/fakes/fake_model.py`, `tests/test_fake_model.py`.
- Code review: `_ensure_stable_reason_code()` rejects non-member codes with `CODE_MALFORMED_FIXTURE_REQUEST`; `fake_error()` calls it; `FixtureFakeModel.__init__()` calls it for direct `FakeErrorFixture` values before registration; `respond()` can therefore only raise stable codes from registered error fixtures.
- Probe: `fake_error("bad-builder", code="UNBOUNDED_ARBITRARY_CODE", ...)` and direct `FakeErrorFixture(... code="UNBOUNDED_ARBITRARY_CODE" ...)` registration both fail closed with `FAKE_MALFORMED_REQUEST`; all raised public error-path codes checked by the probe were in `FAKE_REASON_CODES`.
- Focused tests: `python -X utf8 -m unittest tests.test_fake_model -v` -> 24 tests OK.
- Full tests: `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` with `TMP/TEMP/TMPDIR=C:\tmp\pr40-testtmp2-escalated` -> 1178 tests OK.
- Whitespace/conflict check: `git diff --check origin/rebuild/auto-bioinfo-core...HEAD` -> clean.
- Local ruff note: local Python lacks `ruff`, so local ruff was not counted as a pass; GitHub required `quality` jobs cover lint/format.

## Green-lane condition check

- PR: #40.
- Author: `TOTO-git-q`.
- Base: `rebuild/auto-bioinfo-core` (not `main`).
- Current head: `620785359d313c9a8bc9dec7ac8c59cfbdaedc51`; this is the exact head reviewed above and it still matched GitHub immediately before this turn.
- GitHub PR state: OPEN, non-draft, `mergeable=true`, `mergeable_state=clean`, not merged.
- Required CI at this head: `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` all completed with `success`.
- Hard-stop review: no real external LLM/provider/network/tool call, no content egress, no paid service, no credential/secrets/ruleset/branch-protection change, no dependency/lockfile/SBOM/workflow/Docker change, no destructive action, and no real human-source data started.

## Instruction to CC

CC should re-check the green-lane preconditions mechanically and merge PR #40 with exact-head protection only if they still hold. If head/base/checks/mergeability changed, do not merge; write a BLOCKER/REPORT instead. Codex did not merge, did not enable auto-merge, and did not push the protected base.