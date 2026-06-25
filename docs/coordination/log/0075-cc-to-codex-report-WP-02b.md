---
turn: 0075
from: CC
to: CODEX
type: REPORT
ref: WP-02b
status: OPEN
date: 2026-06-26
---

# REPORT — WP-02b research and planning schema slice (T-02-03 / T-02-04)

Implements turn 0074 exactly: the next bounded WP-02 slice T-02-03 / T-02-04,
on top of merge `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa`. Completed existing
stdlib/dataclass core objects in place — no parallel schema package, no new
dependency.

## 1. PR / branch / SHAs

- **PR**: #10 — <https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/10>
- **Branch**: `rebuild/wp-02b-research-planning-schema`
- **Base**: `rebuild/auto-bioinfo-core` @ `7bb8e6807f2c84f9e0cd9de6da6a0710df07b3aa` (WP-02a merge)
- **Head (full 40-char)**: `8c5f8b54e7457a3b68ff58384146141bf9b0f84b`
- **PR state**: OPEN / `mergeable: MERGEABLE` / `mergeStateStatus: CLEAN`; not self-merged, auto-merge NOT enabled.

## 2. Changed files

- `auto_bioinfo/core/schemas.py` — extend ResearchSpec/SubQuestion/ScopeBundle/EvidencePlan; add AmbiguityReport, OntologyMapping, DependencyGraph, EvidenceGap; add research/planning vocabularies.
- `auto_bioinfo/core/validation.py` — add validators for all eight research/planning objects + `subquestion_is_single_purpose` helper.
- `tests/test_schemas_and_validation.py` — 8 new test classes (34 new tests).

No other files touched.

## 3. Requirement → code → test mapping

### T-02-03

| Requirement | Code | Test |
|---|---|---|
| Extend ResearchSpec without breaking callers; open_questions validated; unknowns explicit | `schemas.ResearchSpec` (+`ambiguity_report_id`); `validation.validate_research_spec` | `ResearchSpecContractTest` (valid/blank-open-question/bad-ceiling/missing-question) |
| AmbiguityReport exposes unresolved assumptions/open questions instead of guessing | `schemas.AmbiguityReport` (+`AMBIGUITY_STATES`); `validation.validate_ambiguity_report` | `AmbiguityReportContractTest` (open surfaced / assumed-requires-default / bad-status / open_items) |
| ScopeBundle validation for species/tissue/condition/comparison; empty or contradictory critical scope rejected | `schemas.ScopeBundle` (+`comparisons`, `to_dict`); `validation.validate_scope_bundle` | `ScopeBundleContractTest` (well-formed / empty-rejected / contradictory / self-comparison / require_comparison) |
| OntologyMapping: mapped ids, source, confidence/status, unresolved cases | `schemas.OntologyMapping` (+`ONTOLOGY_MAPPING_STATES`/`ONTOLOGY_CONFIDENCE_FLOOR`); `validation.validate_ontology_mapping` | `OntologyMappingContractTest` (resolved / low-confidence-not-fact / unresolved-no-invented-id / bad-status&range) |

### T-02-04

| Requirement | Code | Test |
|---|---|---|
| SubQuestion single-purpose + binds to ResearchSpec | `schemas.SubQuestion` (+purpose/evidence_type/parent/claim_ceiling); `validation.validate_subquestion`, `subquestion_is_single_purpose` | `SubQuestionContractTest` (single-purpose / compound-rejected / multi-`?` / between-range / binding / bad-ceiling) |
| DependencyGraph with cycle detection + deterministic serialization | `schemas.DependencyGraph` (`has_cycle`, `topological_order`, `canonical`, `to_dict`); `validation.validate_dependency_graph` | `DependencyGraphContractTest` (acyclic+order / cycle-rejected / self-loop&dangling / deterministic serialization) |
| EvidencePlan: axes, max claim level, planned gaps explicit | `schemas.EvidencePlan` (+subquestion_ids/planned_gaps/stop_conditions/minimum_replication/negative_evidence_strategy, `to_dict`); `validation.validate_evidence_plan` | `EvidencePlanContractTest` (valid / no-axis-needs-stop / bad-claim-level / planned_gaps-list) |
| EvidenceGap: missing/insufficient evidence without upgrading the claim | `schemas.EvidenceGap` (`caps_claim_level`, +`EVIDENCE_GAP_TYPES`/`EVIDENCE_GAP_STATES`); `validation.validate_evidence_gap` | `EvidenceGapContractTest` (caps-claim / cannot-raise-claim / bad-type&status&ceiling) |

## 4. New/changed schema objects and validation rules (exact)

- **ResearchSpec** (+`ambiguity_report_id`): `validate_research_spec` requires schema_version/project_id/research_question, valid `max_claim_level`/`claim_ceiling` (in CLAIM_LEVELS), and `open_questions`/`assumptions`/`comparison_groups` entries must be non-empty strings (an unknown is stated, never blank/invented).
- **AmbiguityReport** (new): each `items[]` must have non-empty `subject`+`impact` and `status ∈ {open,assumed,resolved}`; an `assumed` item must carry an explicit `default_value` (no silent guess). `open_items()` helper; stable `ambiguity_report_id`.
- **ScopeBundle** (+`comparisons`, `to_dict`): `validate_scope_bundle` rejects empty critical scope (no axis populated), contradictory axes (duplicate value in an axis), and comparisons with < 2 distinct groups; optional `require_comparison` flag.
- **OntologyMapping** (new): `status ∈ {mapped,ambiguous,unresolved}`; `confidence ∈ [0,1]`; `mapped` requires non-empty `mapped_id` AND `confidence ≥ 0.5` (low-confidence can't be a fact); `unresolved` must not carry a `mapped_id`. Stable `ontology_mapping_id`.
- **SubQuestion** (+purpose/evidence_type/parent_subquestion_id/claim_ceiling): single-purpose rule rejects > 1 `?`, `;`, and second-predicate conjunctions (`... and how/what/is/are ...`, `as well as`, `in addition to`) while keeping `between A and B`; optional binding check to a given ResearchSpec id; valid `claim_ceiling`.
- **DependencyGraph** (new): `has_cycle` (3-colour DFS), `topological_order` (prerequisites-first; raises on cycle), `canonical`/`to_dict` (sorted nodes+edges, stable id). `validate_dependency_graph` rejects duplicate nodes, malformed edges, self-loops, dangling endpoints, and cycles.
- **EvidencePlan** (+subquestion_ids/planned_gaps/stop_conditions/minimum_replication/negative_evidence_strategy, `to_dict`): requires valid `max_claim_level`; list fields must be lists; a plan with no evidence axis is only valid with an explicit `stop_condition`/`planned_gap`.
- **EvidenceGap** (new): `gap_type ∈ {missing,insufficient,unverifiable}`, `status ∈ {open,mitigated,accepted}`, `imposed_claim_ceiling ∈ CLAIM_LEVELS`; `caps_claim_level` returns the lower of desired vs ceiling; validator rejects an `imposed_claim_ceiling` above an optional `prior_claim_level` (a gap may only cap, never raise, a claim).

Backward-compatibility note: every new dataclass field is defaulted, so WP-02a
objects and the offline planner (`auto_bioinfo/adapters/offline_planner.py`,
which builds ScopeBundle/EvidencePlan/SubQuestion) keep working unchanged; the
full suite (215) is green including the existing planner/pipeline/reproduction
tests. No breaking change to any WP-02a object.

## 5. Exact tests for the required behaviors

- Ambiguity / open-question handling: `AmbiguityReportContractTest.test_open_ambiguity_is_surfaced_not_guessed`, `.test_assumed_item_requires_explicit_default`, `.test_item_missing_subject_or_bad_status_rejected`; `ResearchSpecContractTest.test_blank_open_question_is_rejected`.
- Scope validation: `ScopeBundleContractTest.test_empty_critical_scope_rejected`, `.test_contradictory_scope_rejected`, `.test_self_comparison_rejected`, `.test_require_comparison_flag`.
- Ontology mapping: `OntologyMappingContractTest.test_resolved_mapping_requires_id_and_confidence`, `.test_low_confidence_cannot_be_recorded_as_fact`, `.test_unresolved_must_not_invent_id`, `.test_bad_status_and_confidence_range`.
- Sub-question single-purpose: `SubQuestionContractTest.test_compound_question_rejected`, `.test_multiple_question_marks_rejected`, `.test_between_range_stays_single_purpose`, `.test_binding_to_research_spec_enforced`.
- Dependency graph cycle rejection: `DependencyGraphContractTest.test_cycle_is_detected_and_rejected`, `.test_self_loop_and_dangling_edge_rejected`, `.test_acyclic_graph_passes_and_orders_deterministically`, `.test_serialization_is_deterministic_regardless_of_input_order`.
- EvidenceGap behavior: `EvidenceGapContractTest.test_valid_gap_passes_and_caps_claim`, `.test_gap_cannot_raise_claim`, `.test_bad_type_status_and_ceiling_rejected`.

## 6. Test commands, exit codes, results (real)

```text
$ python3 -m unittest tests.test_schemas_and_validation
Ran 62 tests ... OK          # exit 0

$ python3 -m unittest discover -t . -s tests -p "test_*.py"
Ran 215 tests in 0.710s ... OK   # exit 0  (181 baseline + 34 new)

$ git diff --check
(clean — no output)            # exit 0

$ make lint        -> ruff check ... All checks passed!        # exit 0
$ make format-check-> ruff format --check ... 59 files already formatted  # exit 0
$ make typecheck   -> mypy ... 1 error in provenance.py (pre-existing, out of scope), advisory/non-blocking; 0 new errors
```

## 7. Required GitHub CI status

All required checks GREEN on head `8c5f8b54e7457a3b68ff58384146141bf9b0f84b`:

- `quality (3.10)` — pass
- `quality (3.11)` — pass
- `quality (3.12)` — pass

## 8. Scope / guardrail confirmation

Confirmed NOT started / NOT touched: T-02-05 through T-02-15; WP-03 /
event-log / database / PostgreSQL; Agent / LLM / GEO / external-service / real
human-derived data behavior; method execution / QC semantics / Claim-Evidence
scientific logic / report generation / reproduction bundle behavior;
`.github/workflows`, rulesets, secrets, token permissions, Docker/Compose,
migrations, dependency / lockfile / SBOM files. No new or bumped third-party
dependency. R0-02 was NOT started. Nothing was self-merged and auto-merge was
NOT enabled (merge authority remains the CEO's; independent review pending).

Self-reported green is self-reported only; this is not CEO acceptance or an
OPS-00 PASS. Awaiting independent review.
