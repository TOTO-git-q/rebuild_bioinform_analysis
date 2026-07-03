# WP-27 — Operator & Incident Runbook

Status: offline runbook (T-27-03, T-27-07). It maps common conditions to the
deterministic recovery primitives already implemented in `auto_bioinfo/ops` and
`auto_bioinfo/security`. Every step is inert: it computes a decision value; it
does not itself run, deploy, retry, or delete anything.

---

## 1. Diagnosing "where is a project and why is it stuck?"

Use the observability run panel over the project's event list (no server login
needed):

- `observability.run_panel.project_status(events)` → current stage, whether it is
  terminal/paused, the waiting reason, and the next action.
- `observability.run_panel.task_attempts(events)` → each task attempt, with its
  outcome and retry reason.
- `observability.run_panel.review_queue(events)` → what is still awaiting review.
- `observability.audit_query.query_audit(events, filter)` → filtered, redacted
  audit trail (by actor / type / stage / object / tool-call dimensions).

## 2. Incident: transient failure (network, rate limit, worker crash)

1. Classify: `ops.failure_taxonomy.classify_error_code(code)`.
2. If the class is retryable, decide the bounded retry:
   `ops.retry_policy.decide_retry(request, policy=..., budget=...)`.
   - `retry` → schedule the next attempt after `delay_seconds`.
   - `exhausted` / `escalate` → follow `resolution_path` (never retry forever).
3. A worker crash mid-task is `WORKER_INTERRUPTED` (retryable, idempotent re-run).

## 3. Incident: a node failed but siblings are fine

`ops.rerun_planner.plan_partial_failure(graph, failed_nodes)` isolates the
failure: only descendants of the failed node(s) are `blocked`; every independent
path stays `continuable`. Unrelated work is never cancelled.

## 4. Incident: inputs/versions changed — minimal rerun

`ops.rerun_planner.plan_rerun(graph, changed_nodes)` returns exactly the
`invalidated` subgraph (the changed nodes + their correct descendants) to re-run;
everything else is `preserved`. No full re-run.

## 5. Incident: a scientific/design failure (cannot be retried)

- `RESOURCE_EXHAUSTED` / `VALIDATION_FAILED` → replan:
  `ops.replan.plan_replan(request)` (the prior plan is preserved for audit).
- A changed scope/architecture/data/method/risk/acceptance assumption →
  `ops.replan.evaluate_reconfirm(changes)`; the new path may not execute until a
  human re-confirms.
- Legitimate dead-end (insufficient data, method not applicable, conflicting
  evidence) → `ops.replan.decide_terminal(request)`; a terminal requires a reason
  **and** evidence, so the system never "stops" silently or fabricates a result.

## 6. Incident: suspected secret leak / wrong data egress

- Scan an outbound payload: `security.secret_reference.scan_payload_for_secrets`;
  `assert_no_plaintext_secret` blocks a payload carrying plaintext (references
  only ever leave the boundary).
- Check external send of fields: `security.data_egress_policy.evaluate_external_send`
  (restricted fields are blocked; maskable fields are redacted).
- Check an outbound host: `security.domain_allowlist.evaluate_egress`
  (unauthorised host/protocol/port/task-type and adversarial URIs fail closed).

## 7. Incident: malicious file / path traversal / unauthorised URI

- Path-bearing or credential-bearing hosts and raw IP literals are refused by
  `domain_allowlist.evaluate_egress` with a specific reason code.
- Cross-project access is refused by `security.rbac_hardening.evaluate_cross_project`;
  self-review/self-approval by `evaluate_separation_of_duties`.

## 8. Human override boundary

A reviewer override goes through `ops.replan.evaluate_override`. It may adjust
only policy-permitted items; it can **never** fabricate a `PASS` or delete the
original finding. The finding is always preserved.

## 9. Recovery verification

After any recovery action, re-run the run panel (section 1) to confirm the
project reached a consistent stage, and re-run the audit query to confirm the
recovery is recorded. No duplicate formal Artifact/Claim should appear — the
event log's idempotency key (`core.store.append_event`) dedupes true retries.
