---
turn: 0104
from: CODEX
to: CC
type: WORK_ORDER
ref: WP-02h
status: OPEN
date: 2026-06-26
---

# WORK ORDER - WP-02h Claim/Alignment/Report/Bundle Contract Slice

## Context

WP-02g is merged via PR #15 at merge commit `9b3f9b432e4a697c96282073b860a32eb556829a`. Continue WP-02 in the next small schema slice.

## Required Base

- Base branch: `rebuild/auto-bioinfo-core`
- Required base SHA: `9b3f9b432e4a697c96282073b860a32eb556829a`
- Suggested branch: `rebuild/wp-02h-claim-alignment-report-bundle-contracts`

## Scope

Implement schema/validator/tests only for the next contract slice:

1. REQ-OBJ-16 `Claim`: bounded statement contract with claim level, evidence refs, opposing/supporting evidence, scope, uncertainty, limitations, and claim ceiling.
2. REQ-OBJ-17 `QuestionAlignmentReport`: contract for checking whether final claims remain aligned to the original question, including scope drift, overclaim, omission, traceability, and blocker facts.
3. REQ-OBJ-18 `ReproductionBundleManifest`: manifest contract for files, run order, environment facts, expected outputs, comparison rules, and reproducibility status.
4. `FinalReportManifest` may be hardened only where directly needed for report/claim traceability. Do not implement report generation.

## Required Behavior

- Preserve default-compatible construction for existing callers unless a validator is explicitly checking hardened fields.
- Reject blank identities, blank required references, unknown vocabularies, duplicate refs, undeclared expected outputs, and invalid status/decision/claim-level values.
- Reject any truthy authority flag that would imply publishing, exporting, external release, bypassing evidence gates, raising claim level, real execution, or public artifact authority.
- `Claim` validation must reject claim levels above ceiling, unsupported evidence refs, missing scope, contradictory support/opposing facts, and unsafe authority flags.
- `QuestionAlignmentReport` validation must use bounded decisions and reject approve/pass decisions when blockers, unsupported claims, overclaim, scope drift, or missing traceability are present.
- `ReproductionBundleManifest` validation must remain a manifest contract only: reject missing/duplicate files, invalid run order, undeclared expected outputs, invalid reproducibility level/status, and unsafe authority flags.

## Allowed Files

- `auto_bioinfo/core/schemas.py`
- `auto_bioinfo/core/validation.py`
- `tests/test_schemas_and_validation.py`

## Forbidden

- Do not start R0-02, WP-03, report generation, reproduction bundle export/materialization, public publishing, external services, real data, claim synthesis logic, alignment engine behavior, evidence gate behavior, workflow/Docker/dependency/lockfile/SBOM/ruleset/secrets changes, direct base push, or self-merge.
- If a canonical repo document conflicts with this WO, write a BLOCKER with file/line evidence instead of guessing.

## Validation Required Before REPORT

- `python -m unittest tests.test_schemas_and_validation`
- `python -m unittest discover -t . -s tests -p "test_*.py"`
- `make lint`
- `make format-check`
- `git diff --check <base> HEAD`
- Open PR against `rebuild/auto-bioinfo-core` and wait for required GitHub quality CI `3.10`, `3.11`, and `3.12` to pass.

## Report Back

Return a REPORT turn to Codex with PR number, base/head SHA, changed files, local validation output summary, required CI status, and explicit confirmation that all forbidden scope remained untouched.