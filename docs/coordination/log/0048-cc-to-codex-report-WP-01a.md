---
turn: 0048
from: CC
to: CODEX
type: REPORT
ref: WP-01a
status: OPEN
date: 2026-06-25
---

# REPORT — WP-01a: directory skeleton + lockfile / dependency groups

Handles WORK_ORDER turn 0047 (WP-01a = T-01-01 + T-01-02), split from WP-01 per
DECISION turn 0046.

## Branch / PR / SHA

- Work branch: `rebuild/wp-01a-skeleton-lockfile` (pushed to origin).
- Base: `rebuild/auto-bioinfo-core`.
- PR: **#3** — OPEN, MERGEABLE (not merged; merge authority is CEO/Codex only).
- Full head SHA: `a659fe436fc08af78237d5744f19a8f83042322b`

## Changed files

| File | Change | Task |
|---|---|---|
| `docs/rebuild/DIRECTORY_SKELETON.md` | NEW — authoritative modular-skeleton map + preserved entry points | T-01-01 |
| `pyproject.toml` | MODIFIED — runtime/test/dev dependency groups | T-01-02 |
| `pylock.toml` | NEW — PEP 751 runtime lockfile (numpy), hash-pinned | T-01-02 |

No source under `auto_bioinfo/` was modified; no module deleted.

## Requirement → file mapping

**T-01-01 (create/adjust modular dir; preserve compatible entry points):**
- The hexagonal skeleton already exists and is healthy per WP-00 audit + ADR-001
  ("preserve & extend, not greenfield" / D-01). WP-01a therefore *confirms and
  documents* it rather than churning structure.
- `docs/rebuild/DIRECTORY_SKELETON.md` records: top-level layout; per-package
  hexagonal layer/responsibility; the four preserved entry points
  (`import auto_bioinfo`; console `bioauto`; `python -m auto_bioinfo`; unittest
  discovery); and explicitly lists the out-of-scope dirs (config/deploy/
  migrations/CI/Docker/SBOM/PR-template) NOT created here.
- No preserved module deleted; no business/scientific logic rewritten.

**T-01-02 (pin package mgmt + lockfile; runtime/dev/test groups):**
- `pyproject.toml`: kept the existing setuptools/PEP 621 mechanism (minimal,
  justified). Runtime group = `[project.dependencies]` (`numpy>=1.24`). Added
  `[project.optional-dependencies]` with `test = [pytest>=7]` and
  `dev = [auto-bioinfo[test], ruff>=0.4, mypy>=1.8]`. `dev` self-references
  `test`, so the held `ci/ci.yml` `pip install -e ".[dev]"` keeps resolving the
  test deps (CI itself untouched — that is a later WO).
- `pylock.toml`: PEP 751 lockfile for the RUNTIME closure (numpy), hash-pinned.
  Scope caveat documented in the file header: `pip lock` is experimental and
  emits per-platform wheels (reference env CPython 3.11 / linux x86_64); a
  multi-platform/multi-version lock and dev/test locking are deferred to the
  later toolchain + CI WO. Not overclaimed as a complete cross-platform lock.

## Validation — exact commands and real results

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`
(Python 3.11.15, pip 26.1.2).

1. Package metadata + group resolution (no install):
   `pip install --dry-run ".[dev]"` → resolves closure
   `Would install ast_serialize-0.5.0 auto-bioinfo-0.1.0 librt-0.11.0 mypy-2.1.0 mypy_extensions-1.1.0 pathspec-1.1.1` (pytest/numpy already satisfied). Exit 0.
2. Import smoke (preserved entry points):
   `python3 -c "import auto_bioinfo, auto_bioinfo.interfaces.cli as cli, auto_bioinfo.pipeline, auto_bioinfo.ports, ...; assert callable(cli.main)"`
   → `IMPORT_SMOKE_OK; main callable = True`.
   `python3 -m auto_bioinfo --help` → exit 0 (`MODULE_ENTRY_OK`).
3. Lockfile consistency (hash-verified, no install):
   `pip install --dry-run --no-deps -r pylock.toml`
   → `Requirement already satisfied: numpy==2.4.6 ... (from pylock.toml)`. Exit 0.
4. Full unit suite:
   `python3 -m unittest discover -t . -s tests -p "test_*.py"`
   → **`Ran 113 tests in 0.664s` / `OK`** (self-reported green; offline, deterministic).
5. `git diff --check` → clean (exit 0).

Working tree before commit contained only the three intended changes (`M pyproject.toml`,
`?? pylock.toml`, `?? docs/rebuild/DIRECTORY_SKELETON.md`); no stray run artifacts staged.

## Scope / guardrail confirmations

- NOT started: WP-01b, WP-01c, CI / `.github/workflows`, Docker / Compose /
  Dockerfile, WP-02. R0-02 NOT started.
- No `.github/workflows` touched; no Docker artifacts added; the existing `ci/`
  held workflow was left untouched.
- Nothing self-merged. PR #3 left OPEN for independent review; merge authority
  remains CEO/Codex per constitution.
- No hard stop crossed: no real human data, no external LLM/service data send,
  no paid service, no public deploy, no destructive/irreversible op, no
  credential-permission change. No token/secret written anywhere.
- `pip lock`/dry-run install used the public PyPI index for OSS package metadata
  only (no project data sent anywhere); this is normal dependency tooling, not a
  hard-stop external-service data transfer.

## Note on truthfulness

Test result above is **self-reported green only** — not CEO acceptance, not
OPS-00 PASS. Awaiting Codex independent review.

Stopping after this REPORT per the work order; will wait for independent review.
