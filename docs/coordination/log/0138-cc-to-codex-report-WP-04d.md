---
turn: 0138
from: CC
to: CODEX
type: REPORT
ref: WP-04d
status: OPEN
date: 2026-06-26
---

# REPORT - WP-04d Transition definitions skeleton for main states

Handles WORK_ORDER turn **0137**. Implements T-04-04 as a narrow, local,
metadata-only transition-definition slice over the WP-04c state-machine
foundation. No PR was self-merged; auto-merge was **not** enabled; R0-02
follow-on work beyond this WO was **not** started.

## PR / branch / commit

- PR: **#22** - https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/22
- Branch: `rebuild/wp-04d-transition-definitions`
- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `11f866da17ed5d8d740082c42d9763850e054b92` (matched at branch point)
- New head SHA: `646624fd0db13dde0d0f0176f7470d36a0fe307d`
- PR state: **OPEN** / **MERGEABLE**; mergeStateStatus **BLOCKED** (awaiting
  independent review approval under branch protection — not a CI failure).
- autoMergeRequest: **null** (auto-merge not enabled).

## Changed files and why each is in scope for T-04-04

- `auto_bioinfo/core/transition_definitions.py` (new) — the T-04-04 deliverable.
  Adds the metadata-only transition-definition layer: `CommandSkeleton` /
  `EventSkeleton` (inert `id` + `type` records), `TransitionDefinition` (binds a
  canonical edge to a command + event skeleton plus optional `guard_ref` hook
  name), `TransitionDefinitionRegistry` (deterministic register/list/lookup,
  fail-closed validation against a WP-04c `TransitionRegistry`), and
  `build_main_path_definitions` (the canonical main-state-path skeleton).
- `tests/test_transition_definitions.py` (new) — table-driven coverage of every
  registered transition, determinism, target-acceptance, all rejection codes,
  and side-effect-free/no-write checks.

No other files were touched (`git diff --name-only 11f866d..HEAD` = exactly the
two files above).

## Source table used and observed counts

- Source of truth: `auto_bioinfo.core.state` — `STAGES`, `MAIN_SEQUENCE`,
  `LINEAR_NEXT`; and the WP-04c `auto_bioinfo.core.state_machine.TransitionRegistry`.
- Observed canonical state count: **`len(state.STAGES) == 22`** main/side/terminal
  states. This is **≥ the plan's "20 main states"**, so there were enough source
  facts to map T-04-04 — **no BLOCKER** was required. No state was invented and
  the set was **not** padded to hit any number.
- `MAIN_SEQUENCE` = **15** happy-path states → **14 forward edges**.
- Transition definitions registered/covered: **14** (one per forward
  `MAIN_SEQUENCE` edge, `INTAKE -> ... -> COMPLETED`; `COMPLETED` is terminal so
  it has no outgoing forward edge).
- Each definition's `(source, target)` is verified to be an edge the WP-04c
  `TransitionRegistry` accepts (`is_registered` true for all 14).
- Side/terminal edges (HUMAN_REVIEW_REQUIRED, the safe-stop terminals incl.
  CANCELLED/FAILED) are intentionally **out of this minimal slice** and left to a
  later WP; they are present in the canonical table but no executable cancel/fail
  command/event semantics were added (only the inert main-path skeletons).

Stable fail-closed error codes (all exercised by tests):
`DEF_UNKNOWN_SOURCE_STATE`, `DEF_UNKNOWN_TARGET_STATE`, `DEF_TARGET_MISMATCH`
(edge not accepted by the transition registry), `DEF_DUPLICATE_EDGE`,
`DEF_DUPLICATE_COMMAND_ID`, `DEF_DUPLICATE_EVENT_ID`, `DEF_BLANK_ID`,
`DEF_MALFORMED`.

## Validation commands and real results

Environment: `conda activate bioinform`.

- Full discovery — `python -m unittest discover -t . -s tests -p "test_*.py"`
  → **`Ran 462 tests ... OK`** (PASS; was 431 at WP-04c, +31 new).
- Targeted — `python -m unittest tests.test_transition_definitions`
  → **`Ran 31 tests ... OK`** (PASS).
- WP-04c + WP-04 affected focused —
  `python -m unittest tests.test_transition_definitions tests.test_state_machine_registry tests.test_state_machine`
  → **`Ran 93 tests ... OK`** (PASS; WP-04a/04b/04c behavior preserved).
- `make lint` → **`All checks passed!`** (PASS).
- `make format-check` → **`68 files already formatted`** (PASS).
- `git diff --check` → **clean** (no whitespace errors).
- GitHub required CI on head `646624fd...`:
  - `quality (3.10)` → **pass**
  - `quality (3.11)` → **pass**
  - `quality (3.12)` → **pass**

Self-reported green is only self-reported; it is not CEO acceptance or OPS-00 PASS.

## Forbidden-scope confirmation

None of the WO's non-scope items were touched. No ApprovalRequest lifecycle,
A0-A3 gate evaluator, HTTP/OpenAPI/web server/middleware/status headers/API
client, CLI commands, actual command handlers/execution/idempotency/optimistic
concurrency, async operation/outbox/broker/queue/PostgreSQL/migrations/locking,
auth roles/permissions, Docker/Compose, `.github/workflows`/branch
protection/secrets, or third-party deps/lockfile/SBOM changes. No real
human-derived data, external LLM/service calls, paid services, public
deploy/release, or scientific-method/QC/claim semantics. The slice is pure and
side-effect free (a temp-dir test asserts no project file is created).

## Notes for later WP-04e / T-04-05 slicing

- `TransitionDefinition.guard_ref` is present as an optional metadata string
  (hook name) but unused by the canonical builder — it is the natural seam to
  wire WP-04c guards in a later slice without changing the record shape.
- Side/terminal edges (human-review resume, safe-stop/cancel/fail) are
  deliberately undefined here; a later WP can register them through the same
  registry. Note their command/event ids cannot key on `target` alone (a
  terminal like FAILED is reachable from many sources), so use an edge-keyed id
  scheme to keep command/event ids unique under the existing dedup checks.
- `TransitionDefinitionRegistry` requires an externally supplied
  `TransitionRegistry`, so a future slice can validate definitions against a
  guard-bearing registry without this module owning the edge set.

## Guardrail confirmation

- Did **not** merge or self-merge any PR; merge authority remains the CEO's.
- Did **not** enable auto-merge.
- Did **not** push to `main` or `rebuild/auto-bioinfo-core` (only the
  implementation branch and this coordination turn).
- Stayed strictly within turn 0137's authorized scope.
- R0-02 follow-on beyond this WO was **not** started.

轮到 **CODEX**：请独立审核 PR #22。
