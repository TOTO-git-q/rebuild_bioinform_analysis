---
turn: 0220
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-05e
status: OPEN
date: 2026-06-27
---

# WORK_ORDER - WP-05e / T-05-05 local sensitive-content, minimal-context, and redaction contract

## Goal

Implement the local/offline foundation for T-05-05: sensitive content classification, minimum-context construction, and field redaction before any future model/provider call. This work order must create inert local decisions/data structures only; it must not send content anywhere.

The plan source is `自动生信系统_超细颗粒度架构落地实施计划_v1.0.md` T-05-05: `实现敏感内容分类、最小上下文构建和字段脱敏` with input `ProjectPolicy`, output `context builder`, and validation that SENSITIVE data egress is blocked.

## Scope

- Add the smallest local API needed to classify prompt/context fields by sensitivity and to build a minimum allowed context for future gateway use.
- Integrate with existing local contracts where practical, especially `ProjectPolicy` / policy-shaped inputs and the existing redaction utilities, without changing their public semantics.
- Produce inert results such as a context-build decision, redacted context payload, withheld/sensitive field reasons, and stable bounded reason codes.
- Default fail-closed: unknown sensitivity, missing policy, malformed policy/context request, or explicitly sensitive content must not be admitted to an external-model context.
- Preserve raw input only in caller-owned memory; returned public projections and `to_dict()`/repr-like values must not leak raw sensitive values.
- Support synthetic test fixtures only. Tests may use fake field values like tokens, emails, sample IDs, or SENSITIVE markers, but no real human-derived data.

## Required Tests

- Public/allowed fields can be included in a minimal context; unrequested fields are omitted.
- Sensitive fields are blocked or redacted before the context is marked usable for model/provider input.
- Unknown or malformed sensitivity/policy state fails closed with deterministic reason codes.
- Redaction is deterministic and does not leak the original sensitive value through decision dictionaries, logs, or public projections.
- The context builder uses only explicitly requested/allowed fields and rejects broad/full-object context by default.
- Existing WP-05a/b/c/d behavior remains green.
- No filesystem, network, provider, credential, environment, project-state, event, artifact, log, or domain-table side effect is introduced.

## Out of Scope / Hard Boundaries

- No real LLM/provider/network call and no data/content egress.
- No real human-derived data.
- No provider SDKs, credentials, tokens, secrets, env var changes, or permission expansion.
- No dependency, lockfile, SBOM, workflow, Docker, ruleset, branch-protection, or deployment changes.
- Do not implement T-05-06 tool broker.
- Do not implement T-05-07 raw model output artifacts, T-05-08 audit/usage records, T-05-09 budget/rate-limit/circuit-breaker, T-05-10 fake model fixtures, T-05-11 eval framework, or T-05-12 prompt approval/rollback.
- Do not write business state, project state, events, artifacts, logs, or domain tables.
- Do not alter scientific/data semantics, dataset handling, method/QC thresholds, or claim levels.

## Delivery

Open exactly one PR against `rebuild/auto-bioinfo-core` for WP-05e only. Report PR number, base/head SHAs, exact files changed, local validation commands, required CI `quality (3.10)`, `quality (3.11)`, `quality (3.12)` status, and hard-stop check. If the implementation appears to require real content egress, an actual provider call, a new dependency, credential access, policy changes outside the local contract, or any hard-stop item, stop and write a QUESTION/BLOCKER turn before implementing that part.