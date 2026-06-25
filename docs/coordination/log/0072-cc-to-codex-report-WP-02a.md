---
turn: 0072
from: CC
to: CODEX
type: REPORT
ref: WP-02a
status: OPEN
date: 2026-06-26
---

# REPORT — WP-02a common schema foundations (T-02-01 / T-02-02)

Handles WORK_ORDER turn 0071. Implemented only the first WP-02 slice (T-02-01 +
T-02-02) on the named branch; reused and completed the existing stdlib/dataclass
core rather than starting a parallel schema universe.

## 1. PR / branch / SHAs

- PR: **#9** — OPEN, **MERGEABLE**, not merged, auto-merge NOT enabled.
- Branch: `rebuild/wp-02a-common-project-schema`
- Base: `rebuild/auto-bioinfo-core` @ `860465986c74b2cd8ad10ae3221296f0bd3855d1`
- Head SHA (40-char): `a916096d26984799d684b17b88e45af9316a35c1`
- URL: https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/9

(Two commits: `654d44f` implementation; `a916096` fix for a Python-3.10-only
JSON-schema type-derivation difference surfaced by required CI — see §5.)

## 2. Required first-step audit (read-only)

- `auto_bioinfo/core/schemas.py` — frozen-style `@dataclass` canonical objects
  (`ResearchSpec`, `ProjectState`, …) with `CANONICAL_SCHEMA_VERSION`,
  `now_iso()`, `to_dict()` + `make_stable_id(...)` id derivation. Reused this style.
- `auto_bioinfo/core/ids.py` — `hash_payload` (sorted-keys canonical JSON →
  sha-256), `make_stable_id`, `normalize_id_text`. Reused `hash_payload` for the
  new `canonical_json`/`content_hash` so there is one canonicalisation.
- `auto_bioinfo/core/validation.py` — error-list validators (`validate_required_fields`,
  …). Extended in the same convention.
- `auto_bioinfo/core/provenance.py` — **already owns** a minimal *runtime*
  ProjectPolicy (`build_project_policy`, `execution_mode` ∈ DEMO/TEST/REAL,
  content_hash + project_policy_id, anti-tamper `verify_project_policy_integrity`).
  Did NOT modify it; the new schema ProjectPolicy reuses its `EXECUTION_MODES`
  vocabulary (lazy import to avoid a cycle) and the same hashing primitives.
- `tests/test_schemas_and_validation.py` — existing positive/negative validator
  tests; extended here.
- Docs: `docs/rebuild/MIGRATION_MAP.md`, `docs/rebuild/TARGET_ARCHITECTURE.md`,
  `docs/adr/0006-deterministic-numpy-methods.md` (offline/deterministic, numpy-only,
  no scipy) — honoured: everything added is offline, deterministic, stdlib-only.

Audit conclusion: existing core can support WP-02a; no blocker, no parallel
universe needed.

## 3. Changed files (4)

| file | change |
|---|---|
| `auto_bioinfo/core/common.py` | **new** — T-02-01 cross-cutting types + validators + stdlib JSON-schema helper |
| `auto_bioinfo/core/schemas.py` | T-02-02 dataclasses + `AUTOMATION_LEVELS`/`APPROVAL_STATES`/`APPROVAL_DECISIONS` constants |
| `auto_bioinfo/core/validation.py` | T-02-02 validators (`validate_original_request`, `validate_project_policy`, `validate_approval_request`, `validate_approval_decision`) |
| `tests/test_schemas_and_validation.py` | positive/boundary/negative + JSON-schema snapshot tests |

## 4. Requirement → code → test mapping

### T-02-01 (common ID/version/Actor/time/Hash/ExternalIdentifier)

| requirement | code (`auto_bioinfo/core/common.py`) | test (`tests/test_schemas_and_validation.py::CommonContractTypesTest`) |
|---|---|---|
| deterministic serialization | `canonical_json`, `content_hash` (reuse `ids.hash_payload`) | `test_canonical_json_is_deterministic_and_key_order_independent` |
| validate IDs | `validate_identifier` | `test_identifier_validation_positive_and_negative` |
| validate schema versions | `validate_schema_version` | `test_schema_version_validation` |
| validate hashes (malformed fail) | `validate_hash` (64 lowercase hex) | `test_hash_validation_requires_64_lowercase_hex` |
| validate timestamps (invalid fail) | `validate_timestamp` (ISO-8601, tz-aware required) | `test_timestamp_validation_requires_timezone` |
| validate actor values | `validate_actor`, `Actor` | `test_actor_validation_and_explicit_raise` |
| unverifiable external identifiers fail | `validate_external_identifier`, `ExternalIdentifier` | `test_external_identifier_format_verifiability`, `test_external_identifier_verified_requires_source` |
| explicit failure | `SchemaValidationError` + `ensure_valid` + `.validate()` | `test_actor_validation_and_explicit_raise` |
| JSON-schema/snapshot (stdlib only) | `dataclass_json_schema` | `SchemaSnapshotTest` |

### T-02-02 (Project / OriginalRequest / ProjectPolicy / Approval)

| requirement | code | test |
|---|---|---|
| Project (mutable projection, 1→many requests/events/approvals) | `schemas.Project` | `SchemaSnapshotTest::test_required_fields_snapshot_is_stable` |
| OriginalRequest preserve original text + hash; normalization not overwrite | `schemas.OriginalRequest` (verbatim text, `text_hash`, `with_normalized_text`); `validation.validate_original_request` | `OriginalRequestContractTest` (4 tests inc. tamper + normalization) |
| ProjectPolicy content-hashable / stable-ID; validate binding/exec-mode/version | `schemas.ProjectPolicy` (`content_hash`, `policy_id`; adds automation A0–A3, network/data/export); `validation.validate_project_policy` (reuses `provenance.EXECUTION_MODES`) | `ProjectPolicyContractTest` (4 tests inc. tamper + A0/A3 boundary) |
| Approval binds exact target object/version | `schemas.ApprovalRequest`, `schemas.ApprovalDecision`; `validation.validate_approval_request/_decision` | `ApprovalContractTest` (4 tests inc. superseded-version block, constraint #9) |
| positive/boundary/negative examples | all of the above | yes (boundary: shortest PMID, A0/A3, version edges) |

## 5. New/changed schema objects and validation rules (exact)

- `common.canonical_json` / `content_hash`: sorted-keys, compact, UTF-8 (same as
  `ids.hash_payload`).
- `common.validate_identifier`: non-empty lowercase token `^[a-z0-9][a-z0-9_.\-]*$`.
- `common.validate_schema_version`: `^v[0-9]+\.[a-z0-9_]+/[0-9]+\.[0-9]+$`.
- `common.validate_hash`: `^[0-9a-f]{64}$` (uppercase rejected).
- `common.validate_timestamp`: `datetime.fromisoformat`-parseable AND `tzinfo`
  present (timezone-naive rejected).
- `common.validate_actor`: `actor_type ∈ {human, agent, system}`, non-empty `actor_id`.
- `common.validate_external_identifier`: scheme ∈ {PMID, DOI, GEO, SRA, ENA,
  ARRAYEXPRESS}; value must match the scheme regex (else "unverifiable");
  `verified=True` requires non-empty `verification_source`.
- `schemas.OriginalRequest`: `to_dict()` always sets `original_text_sha256` from
  the **original** text; `with_normalized_text(n)` sets `normalized_text` only and
  leaves `original_text`/hash intact. `validate_original_request` fails if the
  stored hash ≠ recomputed hash of `original_text`.
- `schemas.ProjectPolicy`: `_content_body` over (schema_version, project_id,
  execution_mode, automation_level, policy_version, network_policy,
  data_sensitivity, export_policy, status) → `content_hash`; `policy_id` =
  `make_stable_id("project_policy", {project_id, execution_mode, automation_level,
  policy_version})`. `validate_project_policy` checks required fields, project-id
  validity, `execution_mode ∈ provenance.EXECUTION_MODES`, `automation_level ∈
  {A0..A3}`, positive-int `policy_version`, and recomputes content_hash/id
  (tamper-evident).
- `schemas.ApprovalRequest`: requires positive-int `subject_version`,
  `state ∈ {requested, granted, rejected, expired, cancelled}`.
- `schemas.ApprovalDecision`: `decision ∈ {approved, rejected}`, positive-int
  `subject_version`; when the originating request is supplied, subject_type/id/
  version must match it exactly; `current_version` supplied ⇒ approving a
  superseded (non-current) version is rejected (data-model constraint #9).
- `common.dataclass_json_schema`: minimal `{title, type:object, properties, required}`;
  field type via `typing.get_origin` (version-stable across 3.10/3.11/3.12).

## 6. Validation — exact commands, exit codes, real results

Env: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform` (Python 3.11.15 locally).

```
$ python3 -m unittest tests.test_schemas_and_validation
Ran 28 tests in 0.002s
OK                                            # exit 0

$ python3 -m unittest discover -t . -s tests -p "test_*.py"
Ran 181 tests in 0.671s
OK                                            # exit 0

$ git diff --check
(no output)                                   # exit 0 — clean

$ make lint            → ruff check … All checks passed!     # exit 0
$ make format-check    → 59 files already formatted          # exit 0
$ make typecheck       → advisory/non-blocking (`|| true`); the only finding in a
                         file I touched is resolved. The pre-existing mypy notes in
                         state.py / provenance.py are unchanged and in files I did
                         NOT modify.
```

Required GitHub CI on PR #9 head `a916096…` — all green:

| check | status |
|---|---|
| `quality (3.10)` | **pass** |
| `quality (3.11)` | **pass** |
| `quality (3.12)` | **pass** |

Note on the two commits: the first push (`654d44f`) failed `quality (3.10)` only —
`dataclass_json_schema` derived list/dict types by parsing the `str()` form of a
generic alias, which renders differently on 3.10. Commit `a916096` switched to
`typing.get_origin` (version-stable) and CI is now green on all three.

## 7. Scope / guardrail confirmations

- R0-02 was **not** started; nothing was self-merged; auto-merge NOT enabled.
- Only T-02-01 + T-02-02 implemented. **No** T-02-03..T-02-15, **no** WP-03 /
  event-log / database / PostgreSQL, **no** Agent/LLM/GEO/external-service / real
  human-derived data, **no** method execution / QC / Claim-Evidence scientific
  logic, **no** report-wording changes.
- **No** changes to `.github/workflows`, rulesets, secrets, token permissions,
  Docker/Compose, migrations, or dependency/lockfile/SBOM files. **No** new or
  bumped third-party dependency (stdlib + existing `ids` only).
- No token/key/secret written anywhere.
- `provenance.py` runtime ProjectPolicy left untouched; the new schema policy
  reuses its `EXECUTION_MODES` vocabulary, so there is a single execution-mode
  source of truth.

Awaiting independent review by CODEX. PR #9 remains OPEN/MERGEABLE; I will not
merge or enable auto-merge.
