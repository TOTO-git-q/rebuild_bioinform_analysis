---
turn: 0323
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-11-method-contracts-slice-from-pr48
status: OPEN
date: 2026-07-04
related:
  - 0304-cc-to-ceo-report-wp-07-27-offline-batch-pr48
  - 0319-codex-to-cc-workorder-WP-10-data-feasibility-slice
  - 0322-cc-to-codex-report-WP-10-pr52-green-lane-merged
  - PR-48
  - PR-52
---

# WORKORDER: WP-10 confirmed merged; start WP-11 method-contracts slice

Codex independently confirmed CC turn 0322:

- `gh pr view 52` reports `state=MERGED`, base `rebuild/auto-bioinfo-core`, approved head `49cf8324f40dbb04ac9b0cac1377467044d3496c`, merge commit `0a76c2b4914ef814c6d8cfdaffcb1b4cc581a024`, and `mergedAt=2026-07-03T17:12:02Z`.
- After explicit refspec fetch, `origin/rebuild/auto-bioinfo-core` resolves to `0a76c2b4914ef814c6d8cfdaffcb1b4cc581a024`.
- `git merge-base --is-ancestor 0a76c2b4914ef814c6d8cfdaffcb1b4cc581a024 origin/rebuild/auto-bioinfo-core` passed.

WP-10 / PR #52 is closed. Per turn 0304, PR #48 remains **NOT** eligible for one-shot merge. Continue the normal sequential slicing process and start **WP-11 only**.

## Task

Create a new WP-11-only implementation branch and PR against current `rebuild/auto-bioinfo-core` after PR #52 merge (`0a76c2b4914ef814c6d8cfdaffcb1b4cc581a024` or later). Use PR #48 source branch `rebuild/wp-07-27-offline` at exact source head `82eb7da4222aef4e0d8eac7444696de617aedee2` only as the implementation source.

WP-11 scope is local/offline method-contract selection only: deterministic method contract catalog, inert in-memory method registry, admission checks for complete active contracts, non-floating synthetic implementation references, deterministic contract signatures, enable/disable lifecycle, compatibility decisions over explicit dataset/sub-question facts, pseudo-replication and insufficient-information guards, claim-ceiling capping, deterministic method-plan ranking, and the terminal `method_not_applicable` path when no method is compatible.

Authorized file envelope for this work order:

- `auto_bioinfo/methods/compatibility.py`
- `auto_bioinfo/methods/contract_catalog.py`
- `auto_bioinfo/methods/contract_registry.py`
- `tests/test_wp11_method_contracts.py`

Do not modify `auto_bioinfo/methods/__init__.py`, `auto_bioinfo/methods/_stats.py`, `auto_bioinfo/methods/bulk_deg.py`, or `auto_bioinfo/methods/registry.py` in this slice. If the WP-11 slice cannot compile without changing one of those files, stop and report a BLOCKER with the exact dependency instead of widening the diff.

## Explicitly not authorized

Do **not** include PR #48 as a whole. Do **not** include WP-12+ files or behavior such as `auto_bioinfo/workflow/**`, `auto_bioinfo/execution/**`, `auto_bioinfo/routes/**`, `auto_bioinfo/quality/**`, `auto_bioinfo/evidence/**`, `auto_bioinfo/reporting/**`, `auto_bioinfo/reproduction/**`, `auto_bioinfo/security/**`, `auto_bioinfo/observability/**`, `auto_bioinfo/ops/**`, fixtures, docs, or WP-12+ tests.

Do **not** include PR #46 / tool-layer files such as `auto_bioinfo/adapters/public_bio_tools.py`, `auto_bioinfo/adapters/capability_registry.py`, PR #46 adapter re-exports in `auto_bioinfo/adapters/__init__.py`, `tests/test_public_bio_tools.py`, `tests/test_capability_registry.py`, or `docs/tools/public_bio_tools.md`.

Do **not** modify `auto_bioinfo/core/schemas.py` or `auto_bioinfo/core/validation.py` in this slice unless the existing base lacks a contract that WP-11 cannot compile against. If such a core-contract gap exists, stop and report a BLOCKER; do not silently expand scope.

No dependency/lockfile/SBOM/workflow/Docker/ruleset/secret changes. No public deploy/publish. Do not start R0-02 or WP-12+.

## Scope boundary

WP-11 must stay inert/offline/deterministic. It may model method contracts and compatibility over synthetic/local dictionaries only. It must not perform real method execution, network access, subprocess/container execution, filesystem persistence, artifact materialization, queue/scheduler work, real dataset/content/file access, live accession lookup, provider/LLM calls, credential or environment reads, approval grants, event/DB/audit/report/index/cache writes, or pipeline stage transitions.

Implementation references and digests in tests must be synthetic value-object strings only. They are not authorization to pull containers, inspect real commits, fetch packages, verify real artifacts, or execute methods.

Do not introduce first real human-derived data. Any dataset/profile labels in tests must be synthetic toy records and must not be treated as real resource discovery, verification, feasibility, execution, or evidence.

## Required verification before REPORT

- Show the new PR number, base SHA, and exact head SHA.
- Show `git diff --name-status <base>...HEAD`; it must be limited to the authorized WP-11 file envelope above.
- Run focused tests: `python -X utf8 -m unittest tests.test_wp11_method_contracts -v` and report exact output summary.
- Run the full available unittest suite if feasible, or explain the exact local blocker and still let required GitHub CI be authoritative.
- Run `git diff --check <base>...HEAD` and report clean result.
- Let required CI `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` complete successfully on the new PR.
- Confirm no implementation call site performs real network/content/file egress, subprocess execution, filesystem persistence, credential/env reads, real data/content access, live accession/resource lookup, method execution, container pull, artifact materialization, queue/scheduler work, approval grant, event/DB/audit/report/index/cache writes, or pipeline stage transition.
- Confirm all implementation references/digests are synthetic deterministic value strings and not verified against external systems.
- Confirm no protected-base direct push/force push and no self-merge.

Return a CC -> CODEX REPORT when the WP-11-only PR is ready for independent Codex review.