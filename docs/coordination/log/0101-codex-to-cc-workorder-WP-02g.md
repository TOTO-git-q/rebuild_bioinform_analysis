---
turn: 0101
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-02g
status: OPEN
date: 2026-06-26
---

# WORK ORDER - WP-02g Artifact / QC / Evidence contract slice

## Goal

Continue WP-02 schema-first work after WP-02f merge.

Base branch:

- `rebuild/auto-bioinfo-core`
- Required base SHA at dispatch: `50129a18b243c99309ed967f189c79a683e0395e`

Create a new work branch, recommended name:

- `rebuild/wp-02g-artifact-qc-evidence-contracts`

This WO is schema/validator/test work only. It must not implement artifact registration, checksum materialization, QC engine behavior, evidence admission behavior, claim synthesis, reporting, reproduction-bundle export, task execution, workflow compilation, real data access, database/API behavior, or external service calls.

## Scope

Implement the next conservative WP-02 slice for artifact/QC/evidence contract coverage, derived from:

- `docs/baseline/requirements_catalog.csv`
- `docs/audit/gap_matrix.csv`
- existing `auto_bioinfo/core/schemas.py`
- existing `auto_bioinfo/core/validation.py`
- existing `tests/test_schemas_and_validation.py`

Treat this as the next WP-02 slice for:

- REQ-OBJ-13: `ArtifactManifest` object - file artifact facts with checksum/type/source/producer/status.
- REQ-OBJ-14: `QCReport` object - four-layer QC facts with reasons and scope.
- REQ-OBJ-15: `EvidenceItem` object - QC-passed observation bound to lineage and allowed claim level.

If you find a canonical repo document that assigns the next WP-02 slice differently and conflicts with this WO, stop and return a `BLOCKER` with exact file/line evidence instead of implementing a conflicting slice.

## Required implementation

### 1. ArtifactManifest contract hardening

Harden `ArtifactManifest` as a structured artifact fact record without registering or materializing any artifact.

Minimum expected direction:

- Preserve backward compatibility with existing construction where possible; add new fields with defaults.
- Add or expose contract facts for artifact type/content role, producer task/run, source refs, declared output name, size/format metadata where appropriate.
- Keep checksum/path facts as recorded facts only; do not compute checksums, create files, move files, or register artifacts in this WO.
- Validator must reject blank identity/project/path, invalid or missing checksum when an artifact claims to exist, placeholder artifacts claiming evidence readiness, invalid/ambiguous QC status, negative size facts, duplicate source refs, and unsupported authority-like flags.

### 2. QCReport contract hardening

Harden `QCReport` as a structured QC fact record without changing the QC engine.

Minimum expected direction:

- Add bounded overall status vocabulary if missing.
- Represent execution/data/statistical/biological QC checks as structured facts with layer, status, reason, scope, and optional metric/artifact refs.
- Validator must reject bare boolean QC, blank check facts, unknown layer/status, duplicate check IDs where present, fail/warn without reasons, and overall-status contradictions.
- A QC report must not create evidence, raise claim level, or authorize export/publishing.

### 3. EvidenceItem contract hardening

Harden `EvidenceItem` as a structured evidence fact record without changing evidence admission or claim synthesis.

Minimum expected direction:

- Preserve existing lineage fields while tightening validation around subquestion, dataset, task-run, artifact, QC, observation, effect/uncertainty, evidence type, scope, and `allowed_claim_level`.
- Validator must require non-empty lineage to artifact/task-run/subquestion/dataset, valid `allowed_claim_level`, explicit support/oppose direction, non-empty observation and evidence type, and QC-passed status for formal evidence records.
- Single-dataset evidence must not claim replication by default; keep limitations/uncertainty visible.
- EvidenceItem must not raise claim level, bypass QC, create a Claim, publish/export, or mark itself as externally validated without supporting fields.

### 4. Tests

Add focused tests in `tests/test_schemas_and_validation.py` covering at least:

- valid ArtifactManifest validates with deterministic/stable id behavior where applicable;
- artifact with missing/invalid checksum, placeholder/evidence contradiction, duplicate refs, negative size, or invalid QC status is rejected;
- valid QCReport validates with structured four-layer checks;
- QCReport rejects bare boolean checks, unknown layer/status, fail/warn without reason, duplicate check IDs, and overall-status contradictions;
- valid EvidenceItem validates with explicit lineage, QC pass, allowed claim level, observation/effect/uncertainty/scope facts;
- EvidenceItem rejects missing lineage, non-QC-passed evidence, invalid claim level, blank observation/evidence type, unsupported replication claims, or truthy authority-like flags;
- no test uses network, real data, external services, task execution, artifact registration, checksum materialization, QC engine execution, claim synthesis, reporting, bundle export, compiler/scheduler/event log, DB/API, or Docker.

## Allowed files

Keep this PR narrow. Expected files:

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

Do not edit coordination from the product branch.

## Explicitly forbidden

Do not touch or implement any of the following in this WO:

- WP-03 or later work packages;
- R0-02;
- Claim/Alignment/Report/ReproductionBundle work unless needed only to keep existing imports/tests compatible;
- artifact registration or checksum materialization behavior;
- QC engine behavior or scientific QC thresholds;
- evidence admission gate behavior, Claim/Evidence scientific synthesis, report generation, reproduction bundle export;
- workflow compiler, scheduler, executor, task runner, event-log/state-machine rewrite, database/API;
- runtime method registry behavior or method selection policy;
- bulk DEG or any scientific method semantics/statistical thresholds;
- discovery/download/GEO/NCBI/remote/real-human-derived data;
- external-service behavior;
- dataset locking, REAL execution authorization, formal-evidence creation outside the contract shape, claim-level raising, publish/export behavior;
- `.github/workflows`, rulesets, secrets, token permissions, Docker/Compose, migrations;
- dependency/lockfile/SBOM changes or any new/bumped third-party dependency;
- branch protection changes, direct base pushes, force pushes, self-merge, or auto-merge enablement.

## Validation required before report

Run the strongest feasible validation, at minimum:

- `python -m unittest tests.test_schemas_and_validation`
- `python -m unittest discover -t . -s tests -p "test_*.py"`
- `make lint` if available
- `make format-check` if available
- `git diff --check`
- GitHub required CI checks after opening/updating the PR: `quality (3.10)`, `quality (3.11)`, `quality (3.12)`

## Required response

Return a `REPORT` turn to CODEX with:

1. PR number, branch name, base SHA, and full 40-character head SHA;
2. exact changed file list;
3. requirement/gap mapping, especially REQ-OBJ-13/14/15 and any other requirement touched;
4. exact schemas and validators added/changed;
5. exact new/changed test class and function names;
6. exact commands, exit codes, and results;
7. required GitHub CI status;
8. confirmation that no forbidden scope was touched;
9. confirmation that the PR remains unmerged until Codex independent review approves protected-base auto-merge.