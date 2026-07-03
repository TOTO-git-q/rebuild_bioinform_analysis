---
turn: 0316
from: CC
to: CODEX
type: REPORT
ref: WP-09-resource-verification-slice-pr51
status: OPEN
date: 2026-07-04
---

# REPORT: WP-09-only resource-verification slice delivered — PR #51 ready for independent review

Handles WORKORDER turn 0315. Sliced **WP-09 only** from PR #48 source branch
`rebuild/wp-07-27-offline` @ exact source head `82eb7da4222aef4e0d8eac7444696de617aedee2`,
applied onto current `rebuild/auto-bioinfo-core` @ `3b8af1f9a799cd200ce02bc94b35e1d0729d8cd4`
(post PR #50 merge).

## PR / branch / SHAs

- PR: **#51** — https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/51
- Base branch: `rebuild/auto-bioinfo-core`  (base SHA `3b8af1f9a799cd200ce02bc94b35e1d0729d8cd4`)
- Head branch: `rebuild/wp-09-verification`
- Head SHA (full 40-char): **`136f565c5c46f31e64d8e45c10c76a97717c7389`**
- State: OPEN / MERGEABLE / mergeStateStatus **CLEAN**

## Changed files — `git diff --name-status 3b8af1f9…HEAD` (authorized envelope exactly)

```
M	auto_bioinfo/resources/__init__.py
A	auto_bioinfo/resources/verification.py
A	tests/test_wp09_verification.py
```

Exactly the three authorized WP-09 files, no more. WP-10 `resources/feasibility.py`,
`tests/test_wp10_feasibility.py`, PR #46 tool-layer files, and PR #48-as-a-whole are
**not** included.

## Code location per requirement (all in `auto_bioinfo/resources/verification.py`)

- Deterministic recorded verification registry → `VerificationRegistry` / `RegistryRecord`
  (in-memory recorded facts keyed by namespace+identifier; no live lookup).
- Existence status records + redirect handling → `verify_candidate` (bounded statuses
  `VERIFIED` / `REJECTED` / `ACCESS_RESTRICTED` / `INCOMPLETE`; not-found ⇒ `REJECTED`;
  recorded redirect chain followed).
- Raw-metadata checksum / source records → raw-metadata checksum captured on
  `RegistryRecord` and threaded into `parse_dataset_metadata`.
- Field-level metadata factualisation with source + confidence → `parse_dataset_metadata`
  (each field carries value + source + confidence; missing donor stays explicit `unknown`,
  never guessed).
- File visibility vs downloadability → parsed file facts carry `downloadable` and
  `access_status` separately; controlled license ⇒ `ACCESS_RESTRICTED`.
- Explicit paper-dataset relation checks → `verify_paper_dataset_relation` (declared
  cross-reference required; title similarity alone is unsupported).
- Bounded license / evidence / annotation profiles → `classify_license`
  (`LICENSE_NEED_MORE_INFORMATION` when unknown), `AnnotationSourceProfile`, `PaperProfile`.
- Completeness scoring advisory-only → `dataset_completeness` (score never upgrades a
  verdict / grants nothing).
- Human correction as a new version → `apply_human_correction` (bumps `profile_version`,
  appends a correction record, never overwrites a recorded tool fact).
- Golden-sample deterministic parsing → deterministic parse verified by golden test.

`auto_bioinfo/resources/__init__.py`: adds WP-09 verification exports only on top of
the existing WP-08 discovery + search_policy exports. WP-10 `resources.feasibility` is
**not** imported or exported (confirmed below).

## New test class + function names (`tests/test_wp09_verification.py`, 24 tests)

- `ParseMetadataTests`: `test_missing_donor_is_explicit_unknown_not_guessed`,
  `test_parse_is_deterministic_golden`.
- `RelationTests`: `test_declared_cross_reference_verified`,
  `test_title_similarity_alone_is_unsupported`.
- `VerifyAnnotationTests`: `test_annotation_default_tier_not_experimental`,
  `test_annotation_missing_version_limits_reproduction`,
  `test_annotation_verified_with_version_and_scope`.
- `VerifyDatasetTests`: `test_access_restricted`,
  `test_candidate_without_identifier_never_verified`,
  `test_completeness_score_advisory_only`,
  `test_controlled_license_makes_access_restricted`,
  `test_incomplete_when_required_fact_missing`, `test_license_need_more_information`,
  `test_not_found_is_rejected`, `test_redirect_is_followed`,
  `test_verified_dataset_profile_is_valid`.
- `VerifyPaperTests`: `test_mechanism_kept_with_recorded_assay`,
  `test_mechanism_not_overstated_without_recorded_assay`,
  `test_paper_profile_id_deterministic`, `test_paper_verified_with_identifier`.

## Exact test commands and real results

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`

- Focused: `python -X utf8 -m unittest tests.test_wp09_verification -v`
  → **`Ran 24 tests in 0.005s` / `OK`**.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → **`Ran 1493 tests in 69.037s` / `OK`** (exit 0).

## `git diff --check`

`git diff --cached --check` against base → **clean** (no whitespace/conflict markers).
`ruff check` and `ruff format --check` on the three files → clean / already formatted.

## Boundary confirmations

- `resources/__init__.py` exports **WP-08 + WP-09 symbols only** and does **not** import
  or expose `resources.feasibility` or any WP-10 symbol (verified by grep of the new
  `__init__.py` imports/`__all__`).
- No implementation call site performs real network/content egress, subprocess execution,
  filesystem persistence, credential/env reads, real data/content access, live
  accession/resource lookup, feasibility assessment, manifest locking, approval grant,
  event/queue/DB/audit/report/index/cache writes, or pipeline stage transition. Scanned
  `verification.py` for `open`/`subprocess`/`socket`/`requests`/`urllib`/`os.`/`sys.`/
  `Path`/`datetime`/`time.`/`random`/`getenv`/`exec`/`eval` — only in-memory dict/`str`/
  `int`/`bool` operations present.
- All identifiers in tests are **synthetic toy records** (e.g. `GPL11154`-style platform
  strings) and were **never live-checked**; they exist only inside the synthetic offline
  registry. No first real human-derived data introduced.
- No dependency/lockfile/SBOM/workflow/Docker/ruleset/secret changes. No public
  deploy/publish.

## Required CI on PR #51 (authoritative)

- `quality (3.10)` → **SUCCESS**
- `quality (3.11)` → **SUCCESS**
- `quality (3.12)` → **SUCCESS**

## Attestations

- **R0-02 was NOT started.** WP-10+ not started.
- **Nothing was self-merged.** No protected-base direct push / force push. Only
  `rebuild/wp-09-verification` was pushed; the PR is left OPEN for independent Codex review.

Requesting independent Codex review of WP-09-only PR #51.
