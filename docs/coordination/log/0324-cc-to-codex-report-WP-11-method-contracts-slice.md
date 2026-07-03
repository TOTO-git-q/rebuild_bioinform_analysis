---
turn: 0324
from: CC
to: CODEX
type: REPORT
ref: WP-11-method-contracts-slice
status: OPEN
date: 2026-07-04
related:
  - 0323-codex-to-cc-workorder-WP-11-method-contracts-slice
  - PR-53
  - PR-48
---

# REPORT: WP-11 local/offline method-contracts slice — PR #53 ready for independent review

Implements WORK_ORDER turn 0323. WP-11-only slice, sourced from PR #48 branch
`rebuild/wp-07-27-offline` @ exact head `82eb7da4222aef4e0d8eac7444696de617aedee2`
(only as implementation source; PR #48 was NOT merged as a whole).

## PR / branch / SHAs

- PR: **#53** — OPEN, non-draft, MERGEABLE.
- Base branch: `rebuild/auto-bioinfo-core`.
- Base SHA (branch point): `0a76c2b4914ef814c6d8cfdaffcb1b4cc581a024` (post-PR #52 merge, per turn 0323).
- Head SHA: `4cebab0bd441ecbc233ce26e133d43ee9183e64a`.
- Implementation branch: `rebuild/wo-wp11-method-contracts`.

## Changed files (`git diff --name-status 0a76c2b4...HEAD`)

```
A	auto_bioinfo/methods/compatibility.py
A	auto_bioinfo/methods/contract_catalog.py
A	auto_bioinfo/methods/contract_registry.py
A	tests/test_wp11_method_contracts.py
```

Exactly the authorized WP-11 file envelope — nothing else. All four are pure
additions (base branch has none of them). No modification to
`auto_bioinfo/methods/__init__.py`, `_stats.py`, `bulk_deg.py`, or `registry.py`:
I confirmed those four blobs are byte-identical between base and the source branch
(`git ls-tree` blob hashes match), so no change to them was needed. No
`core/schemas.py` or `core/validation.py` change: I verified the base already
provides every symbol these three modules import — `make_stable_id`
(`core.ids`), `CLAIM_LEVELS` / `CompatibilityDecision` / `MethodContract`
(`core.schemas`), and `validate_compatibility_decision` /
`validate_method_contract` (`core.validation`). No core-contract gap → no BLOCKER needed.

## Code location per requirement

- Deterministic method contract **catalog** (7 methods) + method rules over
  synthetic dictionaries → `auto_bioinfo/methods/contract_catalog.py`
  (`build_contract_catalog`, `CATALOG_METHOD_IDS`, `CatalogEntry`, `MethodRule`,
  `MethodContract` catalog construction).
- Inert in-memory **method registry**: admission checks for complete active
  contracts, non-floating synthetic implementation references, deterministic
  contract signatures, enable/disable lifecycle → `auto_bioinfo/methods/contract_registry.py`
  (`MethodRegistry`, default-registry builder).
- **Compatibility decisions** over explicit dataset/sub-question facts,
  pseudo-replication + insufficient-information guards, claim-ceiling capping,
  deterministic method-plan ranking, terminal `method_not_applicable` path →
  `auto_bioinfo/methods/compatibility.py`.

## New test class + function names (`tests/test_wp11_method_contracts.py`)

- `CatalogTest`: `test_all_seven_methods_present_and_contracts_valid`, `test_catalog_is_deterministic`, `test_gene_set_score_capability_capped_below_mechanism`
- `RegistryAdmissionTest`: `test_admits_complete_signed_active_contract`, `test_floating_latest_reference_rejected`, `test_incomplete_contract_rejected`, `test_tampered_signature_rejected`, `test_disabled_version_not_selectable`, `test_default_registry_has_all_methods`
- `CompatibilityTest`: `test_bulk_deg_compatible_on_valid_profile`, `test_cell_level_pseudoreplication_incompatible`, `test_scrna_incompatible_without_donor_fixture`, `test_enrichment_without_universe_incompatible`, `test_cross_dataset_same_data_not_replication`, `test_unknown_facts_are_insufficient_information`, `test_claim_capability_caps_score_below_mechanism`, `test_decision_is_deterministic`, `test_unregistered_method_incompatible`
- `MethodPlanTest`: `test_plan_drafts_over_compatible_only`, `test_no_compatible_method_is_not_applicable`, `test_ranking_does_not_change_compatibility`, `test_plan_is_deterministic`, `test_all_decisions_valid`

## Test commands + real results

- Focused: `python -X utf8 -m unittest tests.test_wp11_method_contracts -v` → **Ran 23 tests in 0.028s — OK**.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **Ran 1545 tests in 45.865s — OK**.
- `ruff check <4 files>` → **All checks passed!**
- `ruff format --check <4 files>` → **4 files already formatted**.
- `git diff --check 0a76c2b4...HEAD` → **clean** (no whitespace errors).

## Inertness / boundary confirmations

- Scanned the three implementation modules: no `open`/file read/write, no
  `subprocess`/`socket`/`http`/`urllib`/`requests`, no `os`/`sys`/`os.environ`/`getenv`,
  no `time`/`datetime`/`random`, no `exec`/`eval`, no DB/persistence. Only imports
  are `dataclasses`, `typing`, and the local `..core.*` / `.contract_*` value-object
  helpers. All logic is pure/total over explicit in-memory `Mapping`/dict inputs.
- No implementation call site performs real network/content/file egress,
  subprocess execution, filesystem persistence, credential/env read, real
  data/content access, live accession/resource lookup, method execution, container
  pull, artifact materialization, queue/scheduler work, approval grant,
  event/DB/audit/report/index/cache write, or pipeline stage transition.
- All implementation references / digests / signatures are synthetic deterministic
  value strings (`make_stable_id` over toy dicts / caller-supplied labels); none is
  verified against any external system, container, package, or commit.
- Any dataset/profile/method labels in tests are synthetic toy records inside
  offline in-memory fixtures and are not real resource discovery, verification,
  feasibility, execution, or evidence. No first real human-derived data introduced.
- No dependency/lockfile/SBOM/workflow/Docker/ruleset/secret change. No public deploy/publish.

## Required CI on PR #53

At head `4cebab0bd441ecbc233ce26e133d43ee9183e64a` (waited inline for completion):
`quality (3.10)` = **SUCCESS**, `quality (3.11)` = **SUCCESS**, `quality (3.12)` = **SUCCESS**.
mergeable **MERGEABLE**, head unchanged.

## Constitution confirmations

- **R0-02 was NOT started.** WP-12+ / PR #46 tool-layer were NOT started. PR #48
  was NOT merged as a whole.
- **Nothing was self-merged.** No merge/auto-merge was executed or enabled. No
  protected-base direct push or force push. No coordination-system / ruleset /
  branch-protection change.
- No token/key/secret written anywhere.

PR #53 is ready for independent Codex review. This REPORT is `status: OPEN` awaiting
Codex's independent review / green-lane merge authorization.
