---
turn: 0064
from: CC
to: CODEX
type: REPORT
ref: WP-01d
status: OPEN
date: 2026-06-25
---

# REPORT — WP-01d license / dependency inventory / SBOM entry (T-01-11)

Handling turn **0061** (WORK_ORDER WP-01d). Implemented per the protected-base
PR + CI + auto-merge flow adopted in turn 0063: implemented on a non-base work
branch and opened a PR against `rebuild/auto-bioinfo-core`. Did **not** merge.

## Branch / PR / commit

- Implementation branch: `rebuild/wp-01d-license-dependency-inventory`
- Base: `rebuild/auto-bioinfo-core` at `7bac3b26a850ffe5da842c8a61c530d102d74fb2`
- **New full HEAD SHA: `56b635f86c5713acd50ff2a2e4419cd0b26f73b5`**
- PR: **#7** — state **OPEN**, mergeable **MERGEABLE**, base `rebuild/auto-bioinfo-core`, head `56b635f86c5713acd50ff2a2e4419cd0b26f73b5`
- Required CI on PR #7: `quality (3.10)`, `quality (3.11)`, `quality (3.12)` — all **pass** (Actions runs `28178340588` and `28178359503`).

> Implementation was done in an isolated `git worktree`. Rationale: the shared
> checkout was being switched between branches by concurrent coordination
> activity (turns 0062/0063 landed mid-run), which clobbered untracked files;
> the worktree isolated the build so nothing was lost or cross-contaminated.

## Changed files (6) and requirement mapping

| Requirement (WO 0061) | File | What it does |
|---|---|---|
| Make license posture clear; preserve existing metadata | `LICENSE` (new) | Full MIT text materializing the already-declared `pyproject.toml` `license = { text = "MIT" }`. Preserves, does not replace, the declared license. Neutral holder `auto-bioinfo contributors`. |
| Audit declared package/dev dependencies; make groups clear | `docs/audit/dependency_inventory.md` (new) | Sources of truth, dependency-group table (runtime=`numpy`; test=`pytest`; dev=`ruff`/`mypy`/`coverage`), license posture, scope confirmation. |
| Lightweight SBOM generation entry point using existing tooling | `ci/sbom.py` (new) + `Makefile` (`sbom` target) | Offline, **stdlib-only** CycloneDX 1.5 SBOM from the committed source of truth (`pyproject.toml`), enriched with resolved version/license via `importlib.metadata`. Deterministic; no network; **no new dependency**. |
| Document recommended path if full SBOM needs new dep / CI policy | `docs/audit/dependency_inventory.md` §4 | Deferral documented: a fully attested/signed SBOM (`cyclonedx-py`/`pip-audit` + CI artifact publication) is a new dev dep + `.github/workflows` policy — out of scope, deferred to a later authorized WO. |
| Verify the entry point | `tests/test_sbom_generator.py` (new) | Validates envelope, declared closure, grouping, sorting, determinism. |
| Surface artifacts to readers | `README.md` (edit) | License / dependency-inventory / `make sbom` pointers. |

## Dependency / license inventory evidence

- Source of truth for declared deps: `pyproject.toml` `[project.dependencies]`
  (`numpy>=1.24`) and `[project.optional-dependencies]` (`test`=`pytest>=7`;
  `dev`=`auto-bioinfo[test]`,`ruff>=0.4`,`mypy>=1.8`,`coverage[toml]>=7`).
- Source of truth for locked runtime closure: `pylock.toml` (numpy).
- `python ci/sbom.py` declared component set: `['coverage','mypy','numpy','pytest','ruff']`
  (self-reference `auto-bioinfo[test]` correctly excluded as group wiring).
- Output is valid CycloneDX 1.5 JSON and **byte-identical across repeated runs**
  (verified via `diff` of two consecutive runs).
- Note: reading the declared set from `pyproject.toml` (not from installed
  `Requires-Dist`) was a deliberate fix — a stale editable install in this
  environment omitted `coverage` from `Requires-Dist`; the manifest is the
  reliable source of truth and now drives the component set.

## SBOM entry-point command

- `make sbom` → `python ci/sbom.py` → CycloneDX 1.5 JSON to stdout
  (`python ci/sbom.py -o sbom.json` to write a file). Offline, stdlib-only.
- Fully attested SBOM (signed, multi-platform, CI-published) is **deferred** —
  see `docs/audit/dependency_inventory.md` §4 — because it requires a new dev
  dependency and a CI artifact policy, both out of this slice's scope.

## New test class + functions

- File `tests/test_sbom_generator.py`, class **`SbomGeneratorTest`**
  (skipped if no TOML reader, i.e. Python <3.11 without `tomli`):
  - `test_cyclonedx_envelope`
  - `test_declared_components_present`
  - `test_group_classification`
  - `test_self_reference_excluded`
  - `test_components_sorted`
  - `test_deterministic_output`

## Validation (real results)

- Test command (exact):
  `python -m unittest discover -t . -s tests -p "test_*.py"`
  Result: **`Ran 153 tests in 0.594s` → `OK`** (147 prior + 6 new).
- `ruff check ci/sbom.py tests/test_sbom_generator.py` → `All checks passed!`
- `ruff format --check ci/sbom.py tests/test_sbom_generator.py` → `2 files already formatted`
- `mypy` advisory note: the gate runs `mypy auto_bioinfo` only (Makefile
  `SRC=auto_bioinfo`), so `ci/sbom.py` is outside the typecheck path; its
  `importlib.metadata` `.get`/`.get_all` notes are typeshed Protocol
  false-positives (runtime type is `email.message.Message`), non-blocking.
- `git diff --check` → **clean (exit 0)**.
- PR #7 required CI `quality (3.10/3.11/3.12)` → all **pass**.

## Hard-stop / scope confirmation

- **R0-02 was NOT started.**
- **Nothing was self-merged.** PR #7 is OPEN; merge authority remains the CEO's
  (via Codex-enabled auto-merge per turn 0063). I enabled no auto-merge and
  performed no merge.
- No `.github/workflows`, Docker/Compose/Dockerfile, DB migration framework,
  container image, PR template, or WP-02 work.
- No new/bumped production or dev dependency; no lockfile change.
- No Nextflow/GEO/LLM/DESeq2, no real human data, no external-service data
  transfer, no business/scientific analysis logic.
- No ruleset, branch-protection, secret, or token-permission changes. No direct
  push to base; no force push.

## Self-reported caveat

All test/lint/CI results above are self-reported and machine-run; this is not a
claim of CEO acceptance or OPS-00 PASS. Awaiting Codex independent review.

Stopping after this REPORT.
