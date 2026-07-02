---
turn: 0295
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-06f
status: OPEN
date: 2026-07-02
---

# WORK_ORDER - WP-06f / T-06-06 local offline scope-readiness preflight

WP-06e / T-06-05 is merged at `29a79a621b8fd383b97ddc78ca0b7708946983c5` and provides the local deterministic `resolve_scope` preflight contract: inert `ScopeBundle` draft projection plus inert `AmbiguityReport` draft projection, with upstream gates preserved.

The next WP-06 slice must remain local/offline and must not start real ontology/search/data acquisition, approval lifecycle, persistence, events, or pipeline transitions. This work order authorizes only a narrow **scope-readiness consistency preflight** over the already-inert draft outputs.

## Goal

Add the smallest pure local readiness/consistency layer that can decide whether a synthetic draft `ResearchSpec` plus scope-resolution output is internally consistent enough for later human review, or must remain paused with bounded reasons. This is a preflight/status projection only; it must not authorize execution, persist anything, or contact any external service.

## Scope

Implement **T-06-06 local/offline scope-readiness preflight only**.

1. Provide a pure local function/service, following existing `auto_bioinfo.intake` style, that accepts explicit in-memory inputs such as a `QuestionNormalizationResult` or draft `ResearchSpec`, a `ScopeResolutionResult` or its draft `ScopeBundle` / `AmbiguityReport`, and local policy/context only when needed.
2. Reuse/preserve upstream gates from WP-06a through WP-06e:
   - support-scope stops remain stops;
   - multi-question / needs-clarification outcomes remain human-review oriented and are never auto-split;
   - approval-needed / malformed / non-permitted policy outcomes remain inert;
   - non-`scope_draft_created` scope outcomes do not become ready.
3. Return a bounded, serializable, inert readiness result (name chosen by CC) with stable statuses/reason codes. At minimum cover:
   - ready for human review only;
   - blocked by open ambiguity / clarification required;
   - stopped by upstream gate;
   - approval needed;
   - rejected malformed / inconsistent.
4. Validate cross-object consistency without guessing:
   - draft/spec/scope identifiers must match where those fields exist;
   - `ScopeBundle` and `AmbiguityReport` must remain `draft`/non-authoritative review projections;
   - unresolved or unsupported scope axes must remain represented as open ambiguity rather than silently disappearing;
   - populated axes must be traceable to explicit draft facts or the existing synthetic fixture vocabulary path from WP-06e;
   - empty or wholly unknown scope cannot become ready.
5. Keep the result deterministic and side-effect free: no file/network/env/clock/random/subprocess/thread/queue/DB/event/audit/report/index/cache calls; no mutation of caller-owned inputs; defensive copies where projections are exposed.
6. Export the new local surface from `auto_bioinfo/intake/__init__.py` only if it follows the existing package pattern.
7. Add focused synthetic tests covering ready, open ambiguity, upstream stop, approval-needed, malformed/inconsistent IDs, non-draft/authoritative-looking projections, dropped unknown axis prevention, deterministic output, and input immutability.

## Out Of Scope / Hard Stops

Do **not** implement or touch:

- T-06-07 through T-06-12.
- Real ontology adapter/service, real search API, real dataset/literature/API/resource discovery, or data acquisition.
- Any external LLM/provider/service/network/socket call, provider SDK/API key/env/credential access, content egress, paid service, or public deployment/publish.
- Real user/project/research content or real human-derived data.
- Approval grant/lifecycle, persisted/versioned `ResearchSpec` / `ScopeBundle` / `AmbiguityReport`, event emission, scheduler/queue/DB/audit/report/index/cache, or pipeline stage transition.
- Automatic child-project creation, request splitting, human notification UI, or execution authorization.
- Dependency/lockfile/SBOM/workflow/Docker/ruleset/branch-protection/secret changes.
- Direct push or force-push to `main` or `rebuild/auto-bioinfo-core`.

If any of these appear required, stop and write a BLOCKER/QUESTION turn.

## Expected Delivery

Open a PR against `rebuild/auto-bioinfo-core` and report back with:

- PR number, base SHA, head SHA, and branch name.
- Changed files and public API names.
- Focused tests for the new scope-readiness preflight.
- Full local test result when feasible.
- `git diff --check` result.
- GitHub required `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` status.
- Confirmation that no external service/network/content egress, real data/content, approval grant/persistence/event, broader WP-06 task, dependency/lockfile/SBOM/workflow/Docker/ruleset/secret change, destructive operation, or protected-base direct push occurred.