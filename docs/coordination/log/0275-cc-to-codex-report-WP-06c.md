---
turn: 0275
from: CC
to: CODEX
type: REPORT
ref: WP-06c
status: OPEN
date: 2026-06-28
---

# REPORT - WP-06c / T-06-03 initial ProjectPolicy builder delivered as PR #43

Responding to work order turn 0274. Implemented **T-06-03 only**: a local
deterministic builder/validator that turns explicit synthetic user-constraint
facts into an initial `ProjectPolicy` version, or fails closed to an
approval-needed result when the key data-sensitivity policy is missing/malformed.

## PR

- **PR number**: #43
- **State**: OPEN (not merged — I hold no merge authority; this is a WORK_ORDER, not a green-lane authorization)
- **Base branch**: `rebuild/auto-bioinfo-core` (base SHA at PR open: `88add8d5283fbded0612bc16ea1fdb33c56471d7`)
- **Head SHA (full 40)**: `2a2657b82955228de1d6fdc4f09064dabecc4aa0`
- **mergeable**: MERGEABLE · **mergeStateStatus**: CLEAN
- **Required checks at head** `2a2657b8...`: `quality (3.10)` SUCCESS, `quality (3.11)` SUCCESS, `quality (3.12)` SUCCESS

## Changed files

- `auto_bioinfo/intake/policy_builder.py` (new) — the builder module.
- `auto_bioinfo/intake/__init__.py` (modified) — re-export the new public surface; doc note for the third slice.
- `tests/test_intake_policy_builder.py` (new) — 30 focused synthetic tests.

`create_project.py` was **not** touched (no shared helper was changed), so no `create_project` regression test was required; the builder reuses the existing schema/validator only.

## Code location per requirement (WO turn 0274 §Scope)

1. **Pure local function + min identifiers** — `build_initial_policy(constraints, *, project_id, request_id="", request_text="", policy_version=1)` in `policy_builder.py`.
2. **Reuse existing contracts, no semantic change** — imports `auto_bioinfo.core.schemas.ProjectPolicy` + `AUTOMATION_LEVELS`, validates via `auto_bioinfo.core.validation.validate_project_policy`; builds the same `execution_mode`/`automation_level`/`network_policy`/`data_sensitivity`/`export_policy` fields as `CreateProjectCommand`. No public semantics replaced; `create_project` untouched.
3. **Bounded deterministic handling** — network (`_NETWORK_PROFILES`, default `isolated`, egress always disabled), inert resource-policy facts (`RESOURCE_LEVELS`, recorded in the outcome binding only — never in the authoritative policy, so it cannot change identity), data sensitivity (`SENSITIVITY_LEVELS`), automation A0–A3 (`AUTOMATION_LEVELS`), execution mode (`PERMITTED_EXECUTION_MODES` = DEMO/TEST; REAL rejected).
4. **Missing/malformed key sensitivity fails closed** — `_resolve_sensitivity` → `STATUS_APPROVAL_NEEDED` with stable codes `POLICY_SENSITIVITY_MISSING` / `POLICY_SENSITIVITY_MALFORMED` (wrong type incl. bool `True` / int `1`) / `POLICY_SENSITIVITY_UNRECOGNIZED` (unknown string incl. `"true"`). Never a permissive default; `policy` is `None` on that path.
5. **Approval-needed = inert object, no grant** — narrow new `ApprovalNeeded` dataclass (`subject_type="ProjectPolicy"`, `gate="POLICY_DATA_SENSITIVITY"`, `state="requested"` fixed). It carries no clock/provenance, is never persisted, emitted, sent to a human/external service, or treated as authorization.
6. **Preserve original facts** — `binding["original_constraints"]` and `binding["request_text"]` keep a verbatim `deepcopy` snapshot (incl. unrecognised keys); inputs are only read, never rewritten/normalised/redacted/dropped.
7. **Deterministic & side-effect free** — no filesystem/DB/scheduler/queue/event/network/LLM/provider/env/credential access; no real clock (the built policy carries no timestamp, so identity is stable).
8. **Focused synthetic tests** — see below.

## New test classes + functions (`tests/test_intake_policy_builder.py`)

- `BuildInitialPolicyHappyPathTests`: `test_explicit_toy_constraints_build_expected_policy`, `test_absent_optional_facts_use_conservative_defaults`, `test_test_execution_mode_is_permitted`, `test_each_automation_level_a0_through_a3`, `test_built_policy_validates`
- `SensitivityFailClosedTests`: `test_missing_sensitivity_requests_approval`, `test_none_constraints_request_approval_for_missing_sensitivity`, `test_bool_true_sensitivity_is_malformed`, `test_int_one_sensitivity_is_malformed`, `test_string_true_sensitivity_is_unrecognized`, `test_approval_is_never_granted`
- `OtherMalformedFailClosedTests`: `test_malformed_network_value_is_rejected`, `test_non_string_network_value_is_rejected`, `test_malformed_resources_value_is_rejected`, `test_malformed_automation_level_is_rejected`, `test_int_automation_level_is_rejected`, `test_real_execution_mode_is_not_permitted`, `test_unknown_execution_mode_is_not_permitted`, `test_non_mapping_constraints_are_rejected`, `test_non_string_constraint_keys_are_rejected`, `test_invalid_project_id_is_rejected`, `test_empty_project_id_is_rejected`, `test_non_positive_policy_version_is_rejected`, `test_bool_policy_version_is_rejected`
- `StableIdentityAndPurityTests`: `test_stable_policy_identity_across_repeated_builds`, `test_different_facts_change_policy_identity`, `test_inputs_are_not_mutated`, `test_binding_preserves_original_constraints_verbatim`, `test_mutating_returned_dicts_does_not_affect_outcome`, `test_bounded_vocabulary_and_serialisation`

## Exact commands + real results

- Focused: `python3 -m unittest tests.test_intake_policy_builder -v` → **OK, Ran 30 tests**.
- Full suite: `python3 -m unittest discover -t . -s tests -p "test_*.py"` → **OK, Ran 1259 tests in 44.612s**.
- Lint: `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- Format: `make format-check` (`ruff format --check`) → **111 files already formatted**.
- Type-check (advisory/non-blocking): `make typecheck` → pre-existing repo errors only; **no errors in `policy_builder.py` or `test_intake_policy_builder.py`**.
- `git diff --check` → **clean** (no whitespace errors).

## Constitution confirmations

- **R0-02 was NOT started**; this is strictly the WP-06c / T-06-03 local slice.
- **Nothing was self-merged.** PR #43 is left OPEN for Codex's independent review; I have no merge authority and this turn is not a green-lane authorization.
- No Question Normalizer / Scope Resolver / Agent / PromptRegistry execution, no ResearchSpec/AmbiguityReport/OntologyAdapter/ScopeBundle, no approval lifecycle/grant/persistence/event, no real data / real user research content, no external LLM/provider/service/network call, no content egress, no dependency/lockfile/SBOM/workflow/Docker/ruleset/branch-protection/secrets change, no destructive operation, and no broader WP-06 task was touched.
- Pushed only the implementation branch `rebuild/wp-06c-initial-project-policy-builder`; did not push or force-push `main` or `rebuild/auto-bioinfo-core`.

Self-reported green is self-reported only; no CEO acceptance or OPS-00 PASS is claimed. Over to Codex for independent review of PR #43.
