# WP-27 — MVP Evolution Boundary & Hard-Stop Gates

Status: the frozen boundary of the MVP closed loop (T-27-09). This document names
what is **in** the core system and what is deliberately **out**, so a "full
platform" feature can never quietly be treated as part of the closed loop. The
machine-checkable form is `ops.release_readiness.classify_feature`.

---

## 1. In scope — the core closed loop

These capabilities are the MVP. They map to the R1–R6 work packages and are
classified `in_scope`:

- `intake_and_question_resolution`
- `scope_resolution`
- `evidence_planning`
- `resource_discovery_and_locking`
- `workflow_compilation`
- `task_execution_and_qc`
- `evidence_synthesis_and_alignment_audit`
- `reporting_and_reproduction_bundle`
- `approvals_and_gates`
- `failure_recovery_and_replanning`
- `security_and_observability_baseline`

## 2. Out of scope — deferred to a later platform

These are explicitly **not** in the MVP and are classified `out_of_scope`. They
require their own approval and boundary before any work starts:

- `multi_tenant_billing`
- `realtime_collaboration_ui`
- `arbitrary_third_party_plugin_marketplace`
- `auto_publication_submission`
- `self_service_model_finetuning`
- `production_sensitive_data_processing`
- `cross_organization_data_sharing`
- `clinical_decision_support`

## 3. Unknown features default to "unknown" (not "in")

`classify_feature` returns `unknown` for anything not on either list. This is
intentional: a new capability is **never** auto-absorbed into the core loop. It
must be explicitly placed on the in/out list — a decision, not a default.

## 4. Hard-stop gates that freeze the boundary

The evolution boundary is enforced by two hard stops:

1. **Release readiness** — a release cannot ship unless every core gate passes
   with evidence (`evaluate_release_readiness`). See the release/ops handoff doc.
2. **Sensitive-data pre-production gates** — real sensitive-data processing
   (`production_sensitive_data_processing`, which is `out_of_scope`) is blocked
   until the privacy / ethics / compliance / storage / model-egress gates all
   pass (`include_sensitive_data=True`). Until then the system is fixture-only.

## 5. Backlog discipline (T-27-09)

Non-core requests go to a controlled backlog, separated from the core closed
loop. A backlog item is not started by being merely useful; it is started only
after it is placed on the in-scope list through an explicit boundary decision.
This is how the MVP stays a *closed loop* rather than drifting into an unbounded
platform.
