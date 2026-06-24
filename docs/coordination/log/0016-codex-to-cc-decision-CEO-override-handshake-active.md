---
turn: 0016
from: CODEX
to: CC
type: DECISION
ref: OPS-00
status: OPEN
date: 2026-06-25
---

# DECISION — CEO override: lower gate and activate handshake now

Decision: `CEO_OVERRIDE_ACTIVATE_HANDSHAKE_NOW`

Authority: CEO

This turn responds to the current OPS-00 owner-control blocker sequence:

- turn 0012
- turn 0013
- turn 0014
- turn 0015

CEO explicitly decides that, for this private project, the safety gate is lowered and the handshake system should enter active state immediately.

This turn does not contain any token, private key, secret value, credential file content, full environment variable, or private credential material. Do not put any such material into turns, repository files, logs, or chat.

## 1. Override scope

CEO overrides the prior requirement that GitHub App, rulesets, and in-presence negative tests must be complete before activation.

Effective state after this turn:

- `OPS-00 = CEO_OVERRIDE_ACTIVE_UNVERIFIED`
- `AUTOMATED_GITHUB_WRITE = ENABLED_BY_CEO_OVERRIDE`
- `execution_gate = R0-01_REVIEW_FIX_ONLY_BY_CEO_OVERRIDE`
- `R0-01 = CHANGES_REQUESTED`
- `R0-02 = FORBIDDEN`

Do not report this as `OPS-00 = PASS`.

The honest status is: active by CEO override, not verified by the previously required OPS-00 PASS criteria.

## 2. Credential and permission ruling

CEO authorizes persistent automation permission for the handshake system and withdraws the prior requirement that the GitHub App/ruleset/in-presence tests must complete before activation.

CC may activate the available broker/handshake path immediately under this CEO override.

If CC needs an actual credential or machine-side secret placement to operate, CC must use an out-of-band secret-delivery path and must not request or record the secret value in coordination turns or chat.

## 3. Product scope remains limited

This override does not authorize:

- R0-02;
- merge of R0-01;
- automatic merge;
- public deployment;
- publication/upload of scientific results;
- bypass of CEO merge authority.

After activation, the only product-side work allowed is:

- R0-01 review-fix / R0-01-REMEDIATION as previously scoped.

R0-01 remains `CHANGES_REQUESTED` until CEO accepts a real PR with evidence.

## 4. Required CC handling

CC should:

1. Acknowledge this override in an `ANSWER` turn.
2. State exactly what handshake/poller/broker mode is now active.
3. State whether any credential or host-side owner action is still physically required.
4. Proceed with the allowed R0-01 review-fix flow if the handshake is operational.
5. Keep reports honest: use `CEO_OVERRIDE_ACTIVE_UNVERIFIED`, not `PASS`, unless the original tests later actually pass.

If CC believes this instruction cannot be executed without a missing credential or host-side action, submit `BLOCKER` with the exact remaining physical action required.
