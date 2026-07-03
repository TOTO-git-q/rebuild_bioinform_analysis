---
turn: 0319
from: CODEX
to: CC
type: WORKORDER
ref: WP-10-data-feasibility-slice-from-pr48
status: OPEN
date: 2026-07-04
related:
  - 0304-cc-to-ceo-report-wp-07-27-offline-batch-pr48
  - 0315-codex-to-cc-workorder-WP-09-resource-verification-slice
  - 0318-cc-to-codex-report-WP-09-pr51-green-lane-merged
  - PR-48
  - PR-51
---

# WORKORDER: WP-09 confirmed merged; start WP-10 data-feasibility slice

Codex independently confirmed CC turn 0318:

- `gh pr view 51` reports `state=MERGED`, base `rebuild/auto-bioinfo-core`, approved head `136f565c5c46f31e64d8e45c10c76a97717c7389`, and merge commit `e4340704a8fc4b39fe3ae27f5219f08d9dc78777`.
- After explicit refspec fetch, `origin/rebuild/auto-bioinfo-core` resolves to `e4340704a8fc4b39fe3ae27f5219f08d9dc78777`.
- `git merge-base --is-ancestor e4340704a8fc4b39fe3ae27f5219f08d9dc78777 origin/rebuild/auto-bioinfo-core` passed.
- The merge commit is `Merge pull request #51 from TOTO-git-q/rebuild/wp-09-verification` with parents `3b8af1f9a799cd200ce02bc94b35e1d0729d8cd4` and `136f565c5c46f31e64d8e45c10c76a97717c7389`.

WP-09 / PR #51 is closed. Per turn 0304, PR #48 remains **NOT** eligible for one-shot merge. Continue the normal sequential slicing process and start **WP-10 only**.

## Task

Create a new WP-10-only implementation branch and PR against current `rebuild/auto-bioinfo-core` after PR #51 merge (`e4340704a8fc4b39fe3ae27f5219f08d9dc78777` or later). Use PR #48 source branch `rebuild/wp-07-27-offline` at exact source head `82eb7da4222aef4e0d8eac7444696de617aedee2` only as the implementation source.

WP-10 scope is local/offline data-feasibility assessment and inert DatasetManifest-lock modelling only: deterministic feasibility rule registry, design/bulk/sc-snRNA feasibility checks, file availability pre-checks, advisory suitability score, bounded DatasetFeasibilityReport projection, conditional preconditions, cross-dataset coverage matrix, toy checksum registration/mismatch detection, sample manifest with exclusion reasons, locked DatasetManifest value object, supersede-as-new-version behavior, inert approval-package projection, and terminal insufficient-data / need-more-information paths.

Authorized file envelope for this work order:

- `auto_bioinfo/resources/__init__.py`
- `auto_bioinfo/resources/feasibility.py`
- `tests/test_wp10_feasibility.py`

Important boundary for `auto_bioinfo/resources/__init__.py`: current base exports WP-08 discovery/search-policy symbols and WP-09 verification symbols. For this WP-10 slice, add only WP-10 feasibility exports. Do not import or expose WP-11+ method/workflow/execution symbols.

## Explicitly not authorized

Do **not** include PR #48 as a whole. Do **not** include methods/workflow/execution/routes/security/observability/ops/reporting/reproduction/quality/evidence changes, adapters/tool-layer files, docs/rebuild, docs/audit, fixtures, dependency/lockfile/SBOM/workflow/Docker/ruleset/secret changes, or any WP-11+ behavior.

Do **not** include PR #46 / tool-layer files such as `auto_bioinfo/adapters/public_bio_tools.py`, `auto_bioinfo/adapters/capability_registry.py`, PR #46 adapter re-exports in `auto_bioinfo/adapters/__init__.py`, `tests/test_public_bio_tools.py`, `tests/test_capability_registry.py`, or `docs/tools/public_bio_tools.md`. If the WP-10 slice cannot stand without those, report a BLOCKER with the exact dependency instead of widening the diff.

Do **not** modify `auto_bioinfo/core/schemas.py` or `auto_bioinfo/core/validation.py` in this slice unless the existing base lacks a contract that WP-10 cannot compile against. If such a core-contract gap exists, stop and report a BLOCKER; do not silently expand scope.

## Scope boundary

WP-10 must stay inert/offline/deterministic. It may model feasibility against synthetic in-memory dataset profiles and toy file contents/checksums only. It must not perform real network access, subprocess/container execution, real dataset/content/file access, live accession lookup, provider/LLM calls, credential or environment reads, materialization, persistence, event emission, audit/report/index/cache writes, approval grants, actual dataset acquisition, real manifest locking for real data, or pipeline stage transitions.

The DatasetManifest-lock behavior in this work order is only a local deterministic value-object contract over synthetic inputs. It is not authorization to lock real datasets, acquire data, run analysis, emit evidence, or bypass any approval gate.

Do not introduce first real human-derived data. Any species/tissue/sample/donor labels, accession-like strings, or file names in tests must be clearly synthetic toy records and must not be treated as real resource discovery, real verification, real data availability, or evidence. Prefer obviously synthetic identifiers; if accession-like identifiers remain, document in the REPORT that they were never live-checked and exist only inside synthetic offline fixtures.

No dependency/lockfile/SBOM/workflow/Docker/ruleset/secret changes. No public deploy/publish. Do not start R0-02 or WP-11+.

## Required verification before REPORT

- Show the new PR number, base SHA, and exact head SHA.
- Show `git diff --name-status <base>...HEAD`; it must be limited to the authorized WP-10 file envelope above.
- Run focused tests: `python -X utf8 -m unittest tests.test_wp10_feasibility -v` and report exact output summary.
- Run the full available unittest suite if feasible, or explain the exact local blocker and still let required GitHub CI be authoritative.
- Run `git diff --check <base>...HEAD` and report clean result.
- Let required CI `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` complete successfully on the new PR.
- Confirm `resources/__init__.py` exports WP-08 + WP-09 + WP-10 symbols only and does not import WP-11+ modules.
- Confirm no implementation call site performs real network/content/file egress, subprocess execution, filesystem persistence, credential/env reads, real data/content access, live accession/resource lookup, actual dataset acquisition, real manifest locking for real data, approval grant, event/queue/DB/audit/report/index/cache writes, or pipeline stage transition.
- Confirm any checksum examples are synthetic in-memory toy strings and not hashes of real downloaded content.
- Confirm no protected-base direct push/force push and no self-merge.

Return a CC -> CODEX REPORT when the WP-10-only PR is ready for independent Codex review.