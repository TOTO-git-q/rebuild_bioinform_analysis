# WP-27 — Release & Operations Handoff

Status: offline handoff document for the automated bioinformatics platform MVP.
Scope: what a maintainer/operator needs to release, run, and recover the system.
This document is **inert** — it describes procedures; it grants nothing and runs
nothing. The enforceable parts of WP-27 live in
`auto_bioinfo/ops/release_readiness.py` (release-readiness gates, release
manifest, evolution boundary).

> Constitution reminder: the current build is pure / offline / deterministic /
> inert. Nothing in this handoff authorises real network access, real secret
> access, real deployment, or processing of real sensitive data. The
> pre-production sensitive-data gates (below) must all pass first.

---

## 1. Release manifest (T-27-01)

Every release candidate is pinned by a **release manifest** so it is verifiable.
`ops.release_readiness.build_release_manifest(versions)` requires a non-empty
version/hash for each component kind:

| Component | What it pins |
|---|---|
| `code` | source commit / build id |
| `schema` | canonical object schema version |
| `database` | migration revision |
| `prompt` | prompt registry version |
| `method` | method-registry contract version |
| `image` | worker/tool image digest |
| `data_fixture` | acceptance data fixture checksum |

A manifest is **complete** only when all seven are present. An incomplete
manifest can never be declared verifiable (`missing_components` lists the gaps).

## 2. Release-readiness gates (T-27-01, T-27-12)

`ops.release_readiness.evaluate_release_readiness(results)` is the hard-stop
gate. The release is `ready` only when **every** core gate is reported `passed`
**with an evidence reference**. A gate that failed, was not reported, or was
reported without evidence blocks the release (fail closed).

Core hard-stop gates:

1. `security_scan_clean` — dependency/image/secret/static/license scans clean.
2. `acceptance_suite_passed` — the frozen E2E acceptance suite passed.
3. `reproduction_verified` — reproduction bundle ran clean-room, matched spec.
4. `no_unresolved_blocking_findings` — the gap report has no open blockers.
5. `migration_recovery_rehearsed` — migration + restore/recovery drill succeeded.
6. `requirement_traceability_complete` — requirement→task→evidence matrix complete.
7. `operator_docs_present` — operator docs exist and were rehearsed.

## 3. Pre-production sensitive-data gates (T-27-10)

Before **any** real sensitive data is processed, the release must additionally
clear the sensitive-data gate tier
(`evaluate_release_readiness(results, include_sensitive_data=True)`):

- `privacy_review_passed`
- `ethics_review_passed`
- `compliance_review_passed`
- `storage_controls_verified`
- `model_egress_controls_verified`

These are hard stops. Until they pass, the system runs on synthetic/public
fixtures only — which is exactly the current constitution.

## 4. Operator procedures (T-27-02, T-27-03)

Because the current build is offline and deployment-free, these procedures are
described as the *shape* an operator runbook must take, not live commands:

- **Install / configure** — install the package with its pinned dependencies;
  configuration is via `auto_bioinfo/config` settings (no secrets in config —
  secret *references* only, resolved at the edge; see
  `auto_bioinfo/security/secret_reference.py`).
- **Start / stop** — the MVP has no long-running server yet; the closed loop runs
  as in-process, deterministic stages. A future service wrapper would start/stop
  here.
- **Backup / restore** — the authoritative record is the append-only event log
  (`state/events.jsonl`); the project-state snapshot is only a cache (ADR-0003).
  Backup = copy the event log; restore = replay it (`core.store.rebuild_state`).
- **Upgrade** — pin the new release manifest, run the migration, and rehearse a
  restore before switching (gate `migration_recovery_rehearsed`).

## 5. Incident recovery pointers (T-27-07)

The failure-recovery domain logic is implemented and testable offline:

- Classify a failure: `ops.failure_taxonomy.classify_error_code`.
- Decide retry vs escalate (bounded, no infinite retry):
  `ops.retry_policy.decide_retry`.
- Isolate a partial failure / plan a minimal rerun:
  `ops.rerun_planner.plan_partial_failure` / `plan_rerun`.
- Replan / reconfirm / override / terminal: `ops.replan`.
- Secret-leak triage: `security.secret_reference.scan_payload_for_secrets`
  (blocks a payload carrying plaintext secrets).

## 6. What "handoff complete" means

Handoff is complete when: the manifest is pinned, all core readiness gates pass
with evidence, operator procedures are rehearsed on a scratch environment, and
the evolution boundary (next doc) is agreed. Sensitive-data gates remain open
until a real-data decision is separately approved.
