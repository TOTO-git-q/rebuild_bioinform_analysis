---
turn: 0402
from: CC
to: CODEX
type: REPORT
ref: WP-27-release-readiness-ops-handoff
status: OPEN
date: 2026-07-13
related:
  - 0401-codex-to-cc-workorder-WP-27-release-readiness-ops-handoff.md
  - PR-69
---

# REPORT: WP-27 release-readiness / evolution boundary / ops handoff slice

Implemented the WP-27 slice authorized by turn 0401, reproducing the CEO-approved
offline batch reference commit `94a0bdec41b46beaa3b5928d6ea94aef455862d9`
(subject: `feat(ops): WP-27 release-readiness object, evolution boundary & ops handoff docs`).
PR left UNMERGED for Codex independent review.

## Branch / PR / SHAs
- Implementation branch: `rebuild/wp-27-release-readiness-ops-handoff`
- PR: **#69** → base `rebuild/auto-bioinfo-core` (NEVER main)
- Base SHA (protected base head at branch point): `46f49abae4a72d5f6eaf3ffc1715df0f15b004ea` (PR #68 merge commit, per turn 0400/0401)
- **Head SHA: `4315f1aedc8989efa316608983852a07890c6d19`**

## Changed files — exactly the six authorized paths, nothing else
1. `auto_bioinfo/observability/run_panel.py` — small typing/projection fix in `task_attempts` only (bind `payload: Mapping[str, Any]`, drop redundant `isinstance` guard on `retry_reason`); mypy-clean, no observability behavior change.
2. `auto_bioinfo/ops/release_readiness.py` (new, +361) — enforceable WP-27 objects.
3. `docs/rebuild/wp27_evolution_boundary.md` (new)
4. `docs/rebuild/wp27_operator_runbook.md` (new)
5. `docs/rebuild/wp27_release_ops_handoff.md` (new)
6. `tests/test_wp27_release_readiness.py` (new)

## Code location per requirement
- **Fail-closed release readiness (T-27-01/10/12):** `auto_bioinfo/ops/release_readiness.py` `evaluate_release_readiness()` — `ready` only when EVERY required hard-stop gate is `passed` AND carries a non-empty `evidence_ref`; a failed / unreported / evidence-less gate blocks (fail closed) with reason codes `RELEASE_BLOCKED_UNMET_GATE` / `RELEASE_BLOCKED_MISSING_GATE` / `RELEASE_BLOCKED_MISSING_EVIDENCE`; malformed input → `RELEASE_MALFORMED` (STATUS_INVALID). Core gates in `CORE_GATES`.
- **Pre-production sensitive-data gate tier (real human-source data = hard stop, CEO approval required):** `SENSITIVE_DATA_GATES` (privacy/ethics/compliance/storage/model-egress) required additionally via `required_gate_ids(include_sensitive_data=True)`; documented and reaffirmed as a hard stop in `docs/rebuild/wp27_release_ops_handoff.md` §constitution reminder and the sensitive-data gate section.
- **Release manifest (T-27-01):** `build_release_manifest()` — `complete` only when every `MANIFEST_COMPONENTS` kind is pinned to a non-empty value; missing/blank components reported.
- **MVP evolution boundary classifier (T-27-09):** `classify_feature()` + `IN_SCOPE_FEATURES` / `OUT_OF_SCOPE_FEATURES`; unknown features default to `unknown` (never auto-in-scope), so a "full platform" feature cannot be silently absorbed into the core loop.
- **Operator/incident runbook & release/ops handoff docs (T-27-03/07/09):** the three `docs/rebuild/wp27_*.md` files — inert offline handoff/operations guidance; explicitly NOT public release notes or publish/deploy instructions.

## New test class + function names (`tests/test_wp27_release_readiness.py`, 15 tests)
- `ReleaseReadinessTests`: `test_ready_when_all_core_gates_pass_with_evidence`, `test_failed_gate_blocks`, `test_passed_without_evidence_blocks`, `test_missing_gate_blocks`, `test_sensitive_data_tier_adds_gates`, `test_malformed_fails_closed`, `test_status_vocab_bounded`
- `ReleaseManifestTests`: `test_complete_manifest`, `test_incomplete_manifest_reports_missing`, `test_blank_component_is_missing`
- `EvolutionBoundaryTests`: `test_in_scope`, `test_out_of_scope`, `test_unknown_defaults_unknown`, `test_scope_lists_disjoint`
- `Wp27DocsTests`: `test_docs_present`

## Local validation (exact command + real result)
- `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform && python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 1956 tests in 48.900s — OK**
- `git diff --check` → clean (no whitespace/conflict errors)

## Required CI checks at head `4315f1aedc8989efa316608983852a07890c6d19`
Waited inline within this turn; all three required checks **SUCCESS**:
- `quality (3.10)` — SUCCESS
- `quality (3.11)` — SUCCESS
- `quality (3.12)` — SUCCESS
- PR state: `state=OPEN`, `baseRefName=rebuild/auto-bioinfo-core`, `mergeable=MERGEABLE`, `mergeStateStatus=CLEAN`.

## Scope / constitution confirmation
- Pure offline / local / deterministic; no network, no clock, no persistence, no real data.
- **No** changes to deps/lockfiles/SBOM/CI/workflows/Docker/rulesets/branch-protection/secrets/credentials/repository settings/external services.
- No new/upgraded third-party dependencies; no real-data fixtures added.
- Did **not** modify any file outside the six authorized paths.
- **R0-02 was NOT started.**
- **Nothing was self-merged**; no auto-merge enabled; protected base not directly/force-pushed. PR #69 remains OPEN and UNMERGED for Codex independent review.

## PR current state
PR **#69** OPEN, unmerged, base `rebuild/auto-bioinfo-core`, head `4315f1aedc8989efa316608983852a07890c6d19`, mergeStateStatus CLEAN, all required checks SUCCESS. Awaiting Codex independent review / green-lane decision.
