---
turn: 0046
from: CODEX
to: CC
type: DECISION
ref: WP-01-scope-and-guardrails
status: OPEN
date: 2026-06-25
---

# DECISION — WP-01 split and guardrail ruling

This DECISION resolves turn 0045.

## CEO ruling

1. **WP-01 must be split.** The original broad turn 0044 must not be executed as one monolithic WO / PR. Proceed with smaller work orders following the WP-01a..e sequence proposed in turn 0045.
2. **First executable work order is WP-01a only:** T-01-01 directory skeleton + T-01-02 lockfile / dependency grouping.
3. **CI / `.github/workflows` is authorized** as part of WP-01 because it is the real merge gate and the token has workflow permission. It must still be dispatched as an independent small WO after the lint/test toolchain from WP-01c is ready. Do not let it drift indefinitely.
4. **Docker / Compose / container image work is plan-authorized by D-03**, but deferred to later independent small WO(s). Do not include Docker / Compose / Dockerfile in WP-01a.
5. Future WO(s) that use `.github/workflows` or Docker must state that authorization explicitly in the turn so the authorization is auditable on the coordination bus.

## Immediate execution model

- Turn 0044 is superseded as an execution unit and replaced by split WP-01 work orders.
- Turn 0047 dispatches WP-01a.
- After WP-01a is completed, reviewed, and merged, Codex should dispatch WP-01b.
- After WP-01c prepares lint/test tooling, Codex should dispatch a dedicated CI workflow WO promptly.
- Docker / Compose / container-image tasks remain planned but deferred until separately dispatched.

## Boundaries retained

- No WP-02.
- No business/scientific analysis logic.
- No real human data.
- No external LLM/service data transfer.
- No paid service.
- No public deployment/release.
- No destructive migration or irreversible deletion.
- No credential-permission expansion by CC. If workflow push permission fails despite the CEO statement that token has workflow permission, report a BLOCKER.
