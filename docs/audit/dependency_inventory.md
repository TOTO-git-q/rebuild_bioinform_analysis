# Dependency & License Inventory — WP-01d / T-01-11

> Auditable inventory of the project's declared dependency groups, the license
> posture of the project and its dependencies, and the SBOM entry point. Built
> from base commit `7bac3b26a850ffe5da842c8a61c530d102d74fb2`.
>
> **Discipline:** every row below is read from a committed source-of-truth file
> (no guessing). The sources of truth are `pyproject.toml` (declared groups +
> license metadata), `pylock.toml` (locked runtime closure), and `LICENSE`
> (the materialized project license). Transitive versions/licenses are resolved
> at generation time from installed package metadata by `ci/sbom.py`.

## 1. Sources of truth

| Artifact | File | What it declares |
|---|---|---|
| Project metadata + dependency groups | `pyproject.toml` | `[project.dependencies]` (runtime), `[project.optional-dependencies].test` / `.dev`, and `license = { text = "MIT" }` |
| Runtime lockfile | `pylock.toml` | PEP 751 lock of the runtime closure (numpy) for the reference environment; experimental, single-platform (see file header) |
| Project license | `LICENSE` | Full MIT license text, materializing the `pyproject.toml` license metadata (added in this slice; see §3) |
| SBOM entry point | `ci/sbom.py` + `make sbom` | Minimal offline CycloneDX SBOM of the declared closure (see §4) |

## 2. Declared dependency groups

Groups are declared in `pyproject.toml` by WP-01a (T-01-02) and WP-01c
(T-01-07); this slice only inventories and documents them — it does **not** add,
remove, or bump any dependency.

| Group | Member (constraint) | Why it exists | Network at run time? |
|---|---|---|---|
| **runtime** (`[project.dependencies]`) | `numpy>=1.24` | The only thing the production closed-loop needs at run time (deterministic DEG math, ADR-0006). | No |
| **test** (`[project.optional-dependencies].test`) | `pytest>=7` | Test-runner availability only. The canonical runner is stdlib `unittest`; pytest is an alternate front-end. | No |
| **dev** (`[project.optional-dependencies].dev`) | `auto-bioinfo[test]`, `ruff>=0.4`, `mypy>=1.8`, `coverage[toml]>=7` | Local + CI quality gate (lint/format/type/coverage). `dev` includes `test`, so `pip install .[dev]` also installs the test deps. | No |

Notes:
- The runtime closure is intentionally tiny (numpy only). Heavier infrastructure
  (PostgreSQL / MinIO / Nextflow / network LLM) stays behind reserved `Protocol`
  ports (`auto_bioinfo/ports/`) and is **not** a declared dependency at this
  stage — so it is correctly absent from this inventory and from the SBOM.
- `pylock.toml` locks the runtime closure only; dev/test tooling is declared as
  version ranges (not locked) per its header. A multi-platform / multi-version
  lock is deferred to a later, separately authorized work order.

## 3. License posture

- **Project license: MIT.** Declared in `pyproject.toml`
  (`license = { text = "MIT" }`) since WP-01a. Before this slice there was no
  top-level `LICENSE` file, so the declaration was not materialized as
  distributable license text.
- **This slice adds `LICENSE`** containing the standard MIT text, matching the
  already-declared metadata. The existing metadata was **preserved, not
  replaced** — the file makes the declared posture explicit and auditable.
  The copyright line uses the neutral holder `auto-bioinfo contributors`
  (no specific legal entity is asserted); a maintainer may refine the holder
  without changing the license choice.
- **Dependency licenses.** All declared dependencies are permissive OSI licenses
  (numpy: BSD-3-Clause; pytest: MIT; ruff: MIT; mypy: MIT; coverage: Apache-2.0).
  These are best-effort, resolved from installed metadata by `ci/sbom.py` at
  generation time and reported per-component in the SBOM; treat the generated
  SBOM as the live source for exact resolved versions and license strings.
- **No copyleft / no new license obligation** is introduced by this slice.

## 4. SBOM entry point

A lightweight, fully offline SBOM entry point is provided so the dependency
closure can be exported in a standard, machine-readable format **without adding
any dependency**:

```bash
make sbom                 # CycloneDX 1.5 JSON to stdout
python ci/sbom.py -o sbom.json
```

`ci/sbom.py`:
- Uses the **standard library only**, on every supported Python
  (`importlib.metadata`, `json`, `re`, plus `tomllib` on 3.11+). It never touches
  the network; inputs are the committed `pyproject.toml` plus package metadata
  already installed locally.
- Reads the **declared** closure from the committed source of truth,
  `pyproject.toml` (`[project.dependencies]` + `[project.optional-dependencies]`),
  so the component set cannot silently drift with a stale editable install.
  Installed metadata only enriches each component with its *resolved* version and
  license (best-effort; `UNKNOWN`/version-less when a dependency is not installed).
- Is **deterministic**: components are sorted and no wall-clock timestamp is
  embedded, so repeated runs against the same inputs are byte-identical
  (consistent with the reproduction-bundle guarantee).
- Reads `pyproject.toml` with stdlib `tomllib` on Python 3.11+ (the reference
  environment). On Python 3.10 — where `tomllib` does not exist — it falls back
  to a tiny built-in parser that understands **only** the two dependency fields
  it reads (`[project].dependencies` and `[project.optional-dependencies]`), so
  it stays standard-library-only and adds **no** dependency across the project's
  declared `requires-python = ">=3.10"` range. No third-party TOML reader (e.g.
  `tomli`) is imported. The fallback is verified equivalent to `tomllib` on the
  real `pyproject.toml` by `tests/test_sbom_generator.py`
  (`FallbackTomlParserTest`), which runs without skipping on every interpreter.

### Recommended path for a fully attested SBOM (deferred)

This slice stops at a lightweight entry point on purpose. A production-grade SBOM
would add scope that is explicitly out of this work order:

- A dedicated generator (e.g. `cyclonedx-py` or `pip-audit`) is a **new
  dev dependency** and a **supply-chain change**.
- Publishing/signing the SBOM as a CI artifact is a **`.github/workflows` + CI
  artifact policy** change.

Both are deferred to a later, separately authorized work order. Until then,
`make sbom` covers the offline, repo-local inventory need without expanding the
dependency surface or the CI policy.

## 5. Scope confirmation

This slice changed only: `LICENSE`, `ci/sbom.py`,
`tests/test_sbom_generator.py`, `Makefile` (added `sbom` target),
`docs/audit/dependency_inventory.md` (this file), and `README.md`
(doc pointers). It did **not** change `.github/workflows`, Docker/Compose,
database migrations, the PR template, WP-02, any product/scientific logic, any
declared dependency version, rulesets, secrets, or real-data/external-service
paths.
