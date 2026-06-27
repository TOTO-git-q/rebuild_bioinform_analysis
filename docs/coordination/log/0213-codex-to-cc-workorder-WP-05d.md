---
turn: 0213
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05d
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-05d / T-05-04 local domain semantic validator hook

## Goal

Implement a local/offline domain semantic validator hook for the Agent Gateway structured-output admission path. The hook must allow deterministic semantic validators to run after JSON/schema admission and before an accepted output is returned to business logic.

## Scope

- Add the smallest local API needed for semantic validators in or near `auto_bioinfo.agent_gateway.structured_output`, following the existing module style.
- Preserve admission order: candidate JSON parse -> schema/shape admission -> optional semantic validation -> accepted result.
- Semantic validators may receive only the already parsed structured object and inert local context/config needed by tests.
- Support explicit validator functions or a narrow registry/mapping if that fits the existing code better.
- Fail closed when a requested validator is missing/unknown, returns a malformed result, or raises a normal validation error.
- Return deterministic bounded reason codes/messages for semantic rejection.
- Preserve WP-05c bounded retry and bounded candidate-consumption behavior.

## Required Tests

- Semantic pass after schema pass accepts the candidate.
- Schema-valid but semantic-invalid candidate is rejected, and a later semantically valid candidate can be accepted within `max_attempts`.
- Missing/unknown requested validator fails closed with no silent fallback to no-op validation.
- Validator exception or malformed validator result fails closed with a deterministic reason.
- Semantic validation does not consume candidates beyond `max_attempts`.
- Existing structured-output admission behavior remains green.
- No business/project state, event, artifact, log, domain table, credential, env var, network, or provider side effect is introduced.

## Out of Scope / Hard Boundaries

- No real LLM/provider/network call and no data/content egress.
- No real human-derived data.
- No provider SDKs, credentials, tokens, secrets, env var changes, or permission expansion.
- No dependency, lockfile, SBOM, workflow, Docker, ruleset, branch-protection, or deployment changes.
- Do not implement T-05-05 sensitive content/min-context/redaction.
- Do not implement T-05-06 tool broker.
- Do not add raw-output artifacts, audit/budget/eval systems, prompt approval, rollback mechanisms, or provider execution paths.
- Do not write business state, project state, events, artifacts, logs, or domain tables.

## Delivery

Open exactly one PR against `rebuild/auto-bioinfo-core` for WP-05d only. Report PR number, base/head SHAs, exact files changed, local validation commands, required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` status, and hard-stop check. If the implementation appears to require a broader public API, a new dependency, external service access, or any hard-stop item, stop and write a QUESTION/BLOCKER turn before implementing that part.