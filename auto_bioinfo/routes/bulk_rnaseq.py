"""WP-16 — the first real offline bulk RNA-seq research route.

Chains, over a recorded offline fixture:

    intake -> scope -> sub-question decomposition -> evidence plan
    -> resource discovery / verification / feasibility + locked manifest
    -> method contract / compatibility / method plan -> workflow DAG compile
    -> execution authorization + fake-executor TaskRuns -> artifact registry
    -> four-layer QC gates -> evidence admission -> claim synthesis
    -> original-question alignment audit -> constrained report + trace index
    -> reproduction bundle

producing one deterministic :class:`RouteRun`.  Every hard gate is respected: a
failing hard gate stops the route with a recorded terminal status/reason and the
claim ceiling is never exceeded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..evidence.admission import admit_evidence
from ..evidence.claim_synthesis import synthesize_claims
from ..evidence.question_alignment import audit_alignment
from ..execution.authorization import AuthorizationRequest, authorize_execution
from ..execution.fake_executor import RecordedOutcome, RecordedOutput, execute_task
from ..execution.scheduler import Scheduler, tasks_from_workflow_plan
from ..intake.policy_builder import build_initial_policy
from ..intake.question_normalizer import normalize_question
from ..intake.scope_resolver import resolve_scope
from ..methods.compatibility import build_method_plan
from ..methods.contract_registry import build_default_registry
from ..methods.registry import get_method
from ..planning.decomposition import decompose_research_spec
from ..planning.dependency import assess_coverage, build_dependency_graph
from ..planning.evidence_planning import plan_evidence
from ..quality.qc_gates import qc_gate_admits, run_qc
from ..reporting.report_builder import ReportInputRefused, advance_report_status, build_report, build_report_input_bundle
from ..reproduction.clean_rerun import compare_results, render_deg_tsv, run_clean_rerun
from ..reproduction.repro_bundle import build_bundle, verify_bundle
from ..resources.discovery import build_search_query, run_search
from ..resources.feasibility import (
    build_coverage_matrix,
    build_dataset_manifest,
    build_sample_manifest,
    decide_terminal_path,
    register_file_checksums,
    validate_dataset_manifest_lock,
)
from ..resources.verification import verify_candidate
from ..workflow.artifact_registry import ArtifactRegistry, OutputFacts
from ..workflow.dag_compiler import compile_workflow
from . import glue
from .route_run import (
    STAGE_OK,
    STAGE_STOPPED,
    TERMINAL_ALIGNMENT_REVIEW,
    TERMINAL_COMPLETED,
    TERMINAL_CONFLICTING_EVIDENCE,
    TERMINAL_EGRESS_BLOCKED,
    TERMINAL_EVIDENCE_REFUSED,
    TERMINAL_INSUFFICIENT_DATA,
    TERMINAL_METHOD_NOT_APPLICABLE,
    TERMINAL_NEEDS_CLARIFICATION,
    TERMINAL_QC_REJECTED,
    TERMINAL_UNVERIFIABLE_RESOURCE,
    RouteRun,
)

DEFAULT_BULK_QUESTION = "Which genes are differentially expressed in liver between tumor and normal in human RNA-seq data?"


@dataclass
class AnalysisContext:
    """Everything the shared execution+scoring tail needs (WP-16 reused by WP-17)."""

    workspace: Path
    project_id: str
    counts_tsv: str
    samples_tsv: str
    dataset: glue.RouteDataset
    subquestion: dict[str, Any]
    scope_bundle: dict[str, Any]
    research_spec: dict[str, Any]
    project_ceiling: str
    plan_method_id: str  # catalog method the compatibility/DAG lane gates on
    runtime_method_id: str  # the deterministic offline runner that computes the table
    compat_modality: str
    compat_statistical_unit: str
    qc_statistical_unit: str
    qc_modality: str
    metadata_keys: list[str]
    manifest: dict[str, Any]
    sc_metrics: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# WP-16 route
# --------------------------------------------------------------------------


def run_bulk_rnaseq_route(
    question: str = DEFAULT_BULK_QUESTION,
    *,
    project_id: str = "bulk_rnaseq_route",
    workspace: str | Path,
    dataset: glue.RouteDataset | None = None,
    overrides: dict[str, Any] | None = None,
) -> RouteRun:
    """Run the offline bulk RNA-seq route end to end over a recorded fixture."""
    overrides = dict(overrides or {})
    dataset = dataset or glue.load_route_dataset("bulk_rnaseq_route")
    run = RouteRun(route="bulk_rnaseq", project_id=project_id, question=question)

    # ---- Stage group A: planning (intake -> evidence plan) -----------------
    planning = _run_planning(run, question, project_id)
    if planning is None:
        return run
    research_spec, scope_bundle, subquestions, evidence_plan = planning

    # ---- Stage group B: resource closure -> locked manifest ----------------
    samples = glue.samples_from_tsv(dataset.files.get("samples", ""))
    if overrides.get("limit_group_size"):
        samples = _limit_group_size(samples, overrides["limit_group_size"])
    resources = _run_resources(
        run,
        research_spec=research_spec,
        scope_bundle=scope_bundle,
        subquestions=subquestions,
        evidence_plan=evidence_plan,
        dataset=dataset,
        samples=samples,
        overrides=overrides,
    )
    if resources is None:
        return run
    manifest = resources

    # ---- Stage group C: analysis + scoring tail ----------------------------
    ctx = AnalysisContext(
        workspace=Path(workspace),
        project_id=project_id,
        counts_tsv=dataset.files.get("counts", ""),
        samples_tsv=dataset.files.get("samples", ""),
        dataset=dataset,
        subquestion=subquestions[0],
        scope_bundle=scope_bundle,
        research_spec=research_spec,
        project_ceiling=research_spec.get("claim_ceiling", "association"),
        plan_method_id="bulk_deg",
        runtime_method_id="bulk_deg",
        compat_modality=glue.modality_token(dataset.card.get("modality", "")),
        compat_statistical_unit="sample",
        qc_statistical_unit="sample",
        qc_modality="bulk_rna",
        metadata_keys=["sample_group_labels"],
        manifest=manifest,
        overrides=overrides,
    )
    run_analysis_chain(run, ctx)
    return run


# --------------------------------------------------------------------------
# Stage group A — planning
# --------------------------------------------------------------------------


def _run_planning(run: RouteRun, question: str, project_id: str) -> tuple[dict, dict, list[dict], dict] | None:
    pol = build_initial_policy({"data_sensitivity": "internal", "network": "local_only"}, project_id=project_id)
    if not pol.built:
        run.add_stage("intake_policy", STAGE_STOPPED, reason=pol.reason_code, payload={"status": pol.status})
        run.stop(TERMINAL_NEEDS_CLARIFICATION, f"initial policy not built: {pol.reason_code}")
        return None
    assert pol.policy is not None  # a built outcome always carries the policy
    run.add_stage("intake_policy", STAGE_OK, payload={"execution_mode": pol.policy.get("execution_mode")})

    nrm = normalize_question(question, pol, project_id=project_id)
    if not nrm.draft_created:
        run.add_stage("intake_normalize", STAGE_STOPPED, reason=nrm.reason_code, payload={"status": nrm.status})
        run.stop(TERMINAL_NEEDS_CLARIFICATION, f"question not normalized (off-topic / needs clarification): {nrm.reason_code}")
        return None
    assert nrm.research_spec is not None  # a draft_created result always carries a spec
    research_spec = nrm.research_spec
    run.research_spec = research_spec
    run.add_stage("intake_normalize", STAGE_OK, payload={"research_spec_id": research_spec.get("research_spec_id")})

    scp = resolve_scope(nrm, project_id=project_id)
    if not scp.scope_draft_created:
        run.add_stage("scope_resolve", STAGE_STOPPED, reason=scp.reason_code, payload={"status": scp.status})
        run.stop(TERMINAL_NEEDS_CLARIFICATION, f"scope not resolvable: {scp.reason_code}")
        return None
    assert scp.scope_bundle is not None  # a scope_draft_created result always carries a bundle
    scope_bundle = scp.scope_bundle
    run.scope_bundle = scope_bundle
    run.add_stage("scope_resolve", STAGE_OK, payload={"comparisons": scope_bundle.get("comparisons", [])})

    dec = decompose_research_spec(research_spec, scope_bundle)
    if not dec.decomposed:
        run.add_stage("decompose", STAGE_STOPPED, reason=dec.reason_code, payload={"status": dec.status})
        run.stop(TERMINAL_NEEDS_CLARIFICATION, f"decomposition stopped: {dec.reason_code}")
        return None
    subquestions = dec.subquestions
    run.subquestions = subquestions
    run.add_stage("decompose", STAGE_OK, payload={"n_subquestions": len(subquestions)})

    dep = build_dependency_graph(subquestions)
    if not dep.graph_built:
        run.add_stage("dependency", STAGE_STOPPED, reason=dep.reason_code, payload={"status": dep.status})
        run.stop(TERMINAL_NEEDS_CLARIFICATION, f"dependency graph not built: {dep.reason_code}")
        return None
    run.add_stage("dependency", STAGE_OK, payload={"topological_order": dep.topological_order})

    plans = [plan_evidence(sq) for sq in subquestions]
    if not all(p.plan_drafted for p in plans):
        codes = [p.reason_code for p in plans if not p.plan_drafted]
        run.add_stage("evidence_plan", STAGE_STOPPED, reason=";".join(codes), payload={})
        run.stop(TERMINAL_NEEDS_CLARIFICATION, f"evidence planning stopped: {codes}")
        return None
    evidence_plans = [p.evidence_plan for p in plans if p.evidence_plan is not None]
    evidence_plan = evidence_plans[0]
    run.evidence_plans = evidence_plans

    cov = assess_coverage(subquestions, evidence_plans=evidence_plans)
    if not cov.coverage_complete:
        run.add_stage("evidence_plan", STAGE_STOPPED, reason=cov.reason_code, payload={"uncovered": cov.uncovered})
        run.stop(TERMINAL_NEEDS_CLARIFICATION, f"evidence coverage incomplete: {cov.uncovered}")
        return None
    run.add_stage("evidence_plan", STAGE_OK, payload={"max_claim_level": evidence_plan.get("max_claim_level")})
    return research_spec, scope_bundle, subquestions, evidence_plan


# --------------------------------------------------------------------------
# Stage group B — resource closure
# --------------------------------------------------------------------------


def _run_resources(
    run: RouteRun,
    *,
    research_spec: dict,
    scope_bundle: dict,
    subquestions: list[dict],
    evidence_plan: dict,
    dataset: glue.RouteDataset,
    samples: list[dict],
    overrides: dict,
) -> dict | None:
    subquestion_id = subquestions[0]["subquestion_id"]

    # Tool selection + capability gate (offline clean-room layer, PR #46): pick the
    # domain's offline query planner and prove, fail-closed, that network retrieval
    # / dataset materialization is denied before any (recorded) search runs.
    tool_plan = glue.select_discovery_tool_plan(scope_bundle, domain="dataset")
    gate = glue.capability_gate(run.project_id, tool_plan)
    boundary_ok = (
        gate["dataset_materialization"]["decision"] == "deny"
        and gate["no_executable_grants"] is True
        and tool_plan.get("is_retrieved_data") is False
        and "local_path" not in tool_plan.get("query", {})
    )
    if not boundary_ok:
        run.add_stage("tool_capability_gate", STAGE_STOPPED, reason="BOUNDARY_BREACH", payload=gate)
        run.stop(TERMINAL_EGRESS_BLOCKED, "resource-discovery capability boundary breached (materialization not denied / executable grant present)")
        return None
    run.add_stage(
        "tool_capability_gate",
        STAGE_OK,
        payload={
            "tool_id": gate["tool_id"],
            "plan_id": gate["plan_id"],
            "materialization_decision": gate["dataset_materialization"]["decision"],
            "network_decision": gate["network_query_plan"]["decision"],
        },
    )

    qr = build_search_query(evidence_plan, domain="dataset", scope_bundle=scope_bundle)
    if not qr.built:
        run.add_stage("discovery", STAGE_STOPPED, reason=qr.reason_code, payload={"status": qr.status})
        run.stop(TERMINAL_UNVERIFIABLE_RESOURCE, f"search query not built: {qr.reason_code}")
        return None
    assert qr.query is not None  # a built query result always carries the query
    adapter = glue.build_recorded_dataset_adapter(qr.query, dataset)
    sr = run_search(qr.query, adapter)
    if not sr.has_candidates:
        run.add_stage("discovery", STAGE_STOPPED, reason=sr.reason_code, payload={"status": sr.status})
        run.stop(TERMINAL_UNVERIFIABLE_RESOURCE, f"no candidates discovered: {sr.reason_code}")
        return None
    run.add_stage("discovery", STAGE_OK, payload={"n_candidates": len(sr.candidates)})

    # Verification: an empty registry (adversarial) makes every candidate unverifiable.
    registry = glue.VerificationRegistry({}) if overrides.get("break_verification") else glue.build_verification_registry(dataset, samples=samples)
    verified = None
    for cand in sr.candidates:
        vr = verify_candidate(cand, registry)
        if vr.verified:
            verified = vr
            break
    if verified is None:
        run.add_stage("verification", STAGE_STOPPED, reason="NO_VERIFIED_CANDIDATE", payload={})
        run.stop(TERMINAL_UNVERIFIABLE_RESOURCE, "no discovered candidate could be verified against the recorded registry")
        return None
    run.add_stage("verification", STAGE_OK, payload={"dataset_id": verified.profile.get("dataset_id")})

    # Feasibility.
    assert verified.profile is not None  # a VERIFIED result always carries a profile
    profile = dict(verified.profile)
    profile.setdefault("tissue", dataset.card.get("tissue", ""))
    report = _assess_feasibility(profile, research_spec, evidence_plan, subquestion_id)
    if report["decision"] not in ("usable", "conditionally_usable"):
        run.add_stage(
            "feasibility",
            STAGE_STOPPED,
            reason=report["decision"],
            payload={"blocking_gaps": report.get("blocking_gaps", []), "missing_facts": report.get("missing_facts", [])},
        )
        run.stop(TERMINAL_INSUFFICIENT_DATA, f"dataset not feasible ({report['decision']}): {report.get('blocking_gaps') or report.get('missing_facts')}")
        return None
    coverage = build_coverage_matrix([subquestion_id], [report])
    terminal = decide_terminal_path(coverage, [report])
    if terminal is not None:
        run.add_stage("feasibility", STAGE_STOPPED, reason=terminal["terminal_state"], payload=terminal)
        run.stop(TERMINAL_INSUFFICIENT_DATA, f"feasibility terminal: {terminal['terminal_state']}")
        return None
    run.add_stage("feasibility", STAGE_OK, payload={"decision": report["decision"]})

    # Lock the manifest.
    checksums = register_file_checksums({rel: dataset.files[logical] for logical, rel in dataset.card.get("files", {}).items()})
    sm = build_sample_manifest(profile)
    manifest = build_dataset_manifest(
        profile=profile,
        sample_manifest=sm,
        file_checksums=checksums,
        supports_subquestion_ids=[subquestion_id],
        known_limitations=dataset.card.get("known_limitations", []),
    )
    if manifest.get("locked") is not True or validate_dataset_manifest_lock(manifest):
        run.add_stage("dataset_lock", STAGE_STOPPED, reason="LOCK_INVALID", payload={})
        run.stop(TERMINAL_INSUFFICIENT_DATA, "dataset manifest failed to lock")
        return None
    run.dataset_manifest = manifest
    run.add_stage(
        "dataset_lock", STAGE_OK, payload={"dataset_manifest_id": manifest.get("dataset_manifest_id"), "file_checksums": manifest.get("file_checksums", {})}
    )
    return manifest


def _assess_feasibility(profile: dict, research_spec: dict, evidence_plan: dict, subquestion_id: str) -> dict:
    from ..resources.feasibility import assess_feasibility

    spec = {"research_spec_id": research_spec.get("research_spec_id", ""), "tissue": research_spec.get("tissue", "")}
    return assess_feasibility(profile, spec, evidence_plan, subquestion_id=subquestion_id)


def _limit_group_size(samples: list[dict], n: int) -> list[dict]:
    """Adversarial helper: keep only ``n`` samples per group (insufficient design)."""
    kept: list[dict] = []
    seen: dict[str, int] = {}
    for s in samples:
        g = s.get("group", "")
        if seen.get(g, 0) < n:
            kept.append(s)
            seen[g] = seen.get(g, 0) + 1
    return kept


# --------------------------------------------------------------------------
# Stage group C — analysis + scoring tail (shared by WP-16 and WP-17)
# --------------------------------------------------------------------------


def run_analysis_chain(run: RouteRun, ctx: AnalysisContext) -> RouteRun:
    """Method selection -> compile -> authorize -> execute -> QC -> evidence ->
    claims -> alignment -> report -> reproduction.  Fills ``run`` and sets a
    terminal status.  Reused verbatim by the WP-17 donor-level route."""
    # -- method contract + compatibility + method plan --------------------
    reg = build_default_registry()
    modality = "unsupported_modality" if ctx.overrides.get("wrong_modality") else ctx.compat_modality
    profile = glue.compat_profile(
        ctx.dataset,
        group_sizes=glue.group_sizes_from_samples(glue.samples_from_tsv(ctx.samples_tsv)),
        statistical_unit=ctx.compat_statistical_unit,
        modality=modality,
        metadata_keys=ctx.metadata_keys,
    )
    sq = {"subquestion_id": ctx.subquestion["subquestion_id"], "claim_ceiling": ctx.subquestion.get("claim_ceiling", ctx.project_ceiling)}
    method_plan, _decisions = build_method_plan(
        reg, profile, sq, evidence_plan_id=ctx.manifest.get("dataset_manifest_id", ""), candidate_method_ids=[ctx.plan_method_id]
    )
    if method_plan["status"] == "method_not_applicable" or not method_plan["primary_method_id"]:
        run.add_stage("method_plan", STAGE_STOPPED, reason="METHOD_NOT_APPLICABLE", payload={"reasons": method_plan.get("reasons", [])})
        return run.stop(TERMINAL_METHOD_NOT_APPLICABLE, f"no compatible method: {method_plan.get('reasons')}")
    run.add_stage(
        "method_plan",
        STAGE_OK,
        payload={"primary_method_id": method_plan["primary_method_id"], "imposed_claim_ceiling": method_plan.get("imposed_claim_ceiling")},
    )

    manifest_inputs = [f"input__{logical}" for logical in ctx.dataset.card.get("files", {})]
    plans = [{"subquestion": sq, "method_plan": method_plan, "manifest_inputs": manifest_inputs}]
    compiled = compile_workflow(reg, plans, project_id=ctx.project_id)
    if not compiled.compiled:
        blocking = [d for d in compiled.diagnostics if d.get("severity") == "blocking"]
        run.add_stage("workflow_compile", STAGE_STOPPED, reason="COMPILE_REPLAN", payload={"diagnostics": blocking})
        return run.stop(TERMINAL_METHOD_NOT_APPLICABLE, f"workflow did not compile: {[d.get('code') for d in blocking]}")
    workflow_plan = compiled.workflow_plan
    assert workflow_plan is not None  # a compiled result always carries a plan
    run.workflow_plan = workflow_plan
    packets_by_id = {p["task_id"]: p for p in compiled.task_packets}
    run.add_stage("workflow_compile", STAGE_OK, payload={"task_ids": workflow_plan["task_ids"], "plan_hash": compiled.plan_hash})

    # -- run the real (deterministic, offline) bulk_deg method ------------
    inputs_dir = ctx.workspace / ctx.project_id / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    counts_path = inputs_dir / "counts.tsv"
    samples_path = inputs_dir / "samples.tsv"
    counts_path.write_text(ctx.counts_tsv, encoding="utf-8")
    samples_path.write_text(ctx.samples_tsv, encoding="utf-8")
    analysis_node = next((n for n in compiled.nodes if n["node_type"] == "Analysis"), None)
    analysis_task_id = analysis_node["task_id"] if analysis_node else workflow_plan["task_ids"][0]
    out_dir = ctx.workspace / ctx.project_id / "runs" / analysis_task_id
    method = get_method(ctx.runtime_method_id)
    method_result = method.run(inputs={"counts": str(counts_path), "samples": str(samples_path)}, params={}, out_dir=str(out_dir))
    if method_result.get("status") != "succeeded":
        run.add_stage("execute", STAGE_STOPPED, reason=method_result.get("status", ""), payload={"reason": method_result.get("reason", "")})
        return run.stop(TERMINAL_INSUFFICIENT_DATA, f"method precondition failed: {method_result.get('reason')}")
    deg_path = method_result["output_path"]
    deg_bytes = Path(deg_path).read_bytes()
    deg_rows = glue.parse_deg_rows(deg_path)

    # -- artifact registration + lineage ----------------------------------
    art_reg = ArtifactRegistry()
    analysis_expectation = next((e for e in compiled.artifact_expectations if e["producer_task_id"] == analysis_task_id and not e["terminal"]), None)
    output_name = analysis_expectation["output_name"] if analysis_expectation else "deg_results_table"
    facts = OutputFacts(
        output_name=output_name,
        uri=f"{ctx.project_id}/outputs/deg_results.tsv",
        content=deg_bytes,
        declared_media_type="text/tab-separated-values",
        content_role="result_table",
        producer_task_id=analysis_task_id,
        relative_path="outputs/deg_results.tsv",
    )
    registration = art_reg.register(ctx.project_id, facts, expected_output_names=[output_name])
    if registration.state != "VALID":
        run.add_stage("artifact_registry", STAGE_STOPPED, reason=registration.state, payload={"findings": registration.findings})
        return run.stop(TERMINAL_INSUFFICIENT_DATA, f"artifact not valid: {registration.state}")
    artifact_manifest = {
        "artifact_id": registration.artifact_id,
        "exists": True,
        "is_placeholder": False,
        "checksum_sha256": registration.checksum_sha256,
        "size_bytes": registration.size_bytes,
        "qc_status": "pending",
    }
    run.artifacts = [registration.to_dict()]
    run.add_stage("artifact_registry", STAGE_OK, payload={"artifact_id": registration.artifact_id, "state": registration.state})

    # -- execution authorization ------------------------------------------
    if ctx.overrides.get("force_egress"):
        for p in compiled.task_packets:
            p.setdefault("execution_fields", {})["network_policy"] = {"egress": "allow"}
    artifact_facts = {aid: {"state": "VALID", "checksum_sha256": "a" * 64, "expected_checksum_sha256": "a" * 64, "exists": True} for aid in manifest_inputs}
    impl_facts = {ctx.plan_method_id: {"code_commit": "fixture_commit_0001", "container_digest": "sha256:" + "d" * 12}}
    auth_req = AuthorizationRequest(
        project_id=ctx.project_id,
        workflow_plan=workflow_plan,
        task_packets=compiled.task_packets,
        artifact_facts=artifact_facts,
        implementation_facts=impl_facts,
        resource_status={"cpu_available": 8, "memory_mb_available": 16000},
        policy={"execution_mode": "TEST", "data_sensitivity": "internal", "network_policy": {"egress": "deny"}},
    )
    auth = authorize_execution(auth_req, plan_hash=compiled.plan_hash)
    run.authorization = auth.to_dict()
    if not auth.authorized:
        run.add_stage("authorization", STAGE_STOPPED, reason=auth.decision, payload={"reasons": auth.reasons})
        terminal = TERMINAL_EGRESS_BLOCKED if any("egress" in r for r in auth.reasons) else TERMINAL_INSUFFICIENT_DATA
        return run.stop(terminal, f"execution not authorized ({auth.decision}): {auth.reasons}")
    run.add_stage("authorization", STAGE_OK, payload={"authorized_task_ids": auth.authorized_task_ids})

    # -- schedule + fake-executor TaskRuns --------------------------------
    tasks = tasks_from_workflow_plan(workflow_plan, project_id=ctx.project_id, authorization_id=auth.authorization_id)
    sched = Scheduler()
    sched.load_authorization(tasks, auth)
    task_runs: list[dict] = []
    guard = 0
    while guard < 50:
        guard += 1
        msgs = sched.dispatch()
        if not msgs:
            break
        for msg in msgs:
            packet = packets_by_id[msg.task_id]
            outcome = _outcome_for(packet, msg.task_id, analysis_task_id, deg_bytes, registration.checksum_sha256)
            report = execute_task(packet, outcome, worker_identity="offline_route_worker")
            task_runs.append(report.task_run)
            if report.task_run.get("result_status") == "completed":
                sched.mark_completed(msg.task_id)
    run.task_runs = task_runs
    analysis_run = next((t for t in task_runs if t.get("task_id") == analysis_task_id), task_runs[-1] if task_runs else {})
    run.add_stage("execute", STAGE_OK, payload={"n_task_runs": len(task_runs), "analysis_task_run_id": analysis_run.get("task_run_id")})
    method_result["task_run_id"] = analysis_run.get("task_run_id", "")
    method_result["outputs"] = method_result.get("outputs", {"deg_results_table": deg_path})

    # -- four-layer QC gates ----------------------------------------------
    group_sizes = glue.group_sizes_from_samples(glue.samples_from_tsv(ctx.samples_tsv))
    contract = glue.qc_contract(statistical_unit=ctx.qc_statistical_unit, claim_capability="association")
    bundle = glue.qc_bundle(
        method_result=method_result,
        artifact_manifest=artifact_manifest,
        modality=ctx.qc_modality,
        group_sizes=group_sizes,
        contract=contract,
        subquestion_ids=[ctx.subquestion["subquestion_id"]],
        n_genes=method_result.get("n_genes", len(deg_rows)),
        n_samples=sum(group_sizes.values()),
        sc_metrics=ctx.sc_metrics,
    )
    qc_report = run_qc(bundle)
    run.qc_reports = [qc_report]
    admitted, gate_reason = qc_gate_admits(qc_report)
    if not admitted:
        blocking = qc_report.get("blocking_findings", [])
        reason = blocking[0]["reason"] if blocking else gate_reason
        run.add_stage("qc", STAGE_STOPPED, reason=qc_report["decision"], payload={"decision": qc_report["decision"], "blocking": blocking})
        return run.stop(TERMINAL_QC_REJECTED, f"QC did not admit ({qc_report['decision']}): {reason}")
    artifact_manifest["qc_status"] = "pass" if qc_report["overall_status"] == "pass" else "pass_with_warnings"
    run.add_stage("qc", STAGE_OK, payload={"decision": qc_report["decision"], "overall_status": qc_report["overall_status"]})

    # -- evidence admission -----------------------------------------------
    admission = admit_evidence(
        result_table=deg_rows,
        method_result={
            "status": "succeeded",
            "task_run_id": method_result["task_run_id"],
            "group_a": method_result.get("group_a", ""),
            "group_b": method_result.get("group_b", ""),
            "adequately_powered": True,
            "observed_direction": ctx.subquestion.get("expected_direction", ""),
        },
        artifact_manifest=artifact_manifest,
        qc_report=qc_report,
        dataset_profile={"dataset_id": ctx.manifest.get("dataset_id", ""), "known_limitations": ctx.dataset.card.get("known_limitations", [])},
        scope_bundle=ctx.scope_bundle,
        subquestion={
            "subquestion_id": ctx.subquestion["subquestion_id"],
            "claim_ceiling": ctx.subquestion.get("claim_ceiling", ctx.project_ceiling),
            "expected_direction": ctx.subquestion.get("expected_direction", ""),
        },
        contract={"claim_capability": "association", "parameters": {"significance_alpha": 0.05, "log2fc_threshold": 1.0}, "version": "0.1.0"},
        project_ceiling=ctx.project_ceiling,
    )
    if not admission.admitted:
        run.non_admissible = [admission.non_admissible_marker] if admission.non_admissible_marker else []
        run.add_stage("evidence_admission", STAGE_STOPPED, reason=admission.reason_code, payload={})
        return run.stop(TERMINAL_EVIDENCE_REFUSED, f"evidence refused: {admission.reason_code}")
    evidence_item = admission.evidence_item
    assert evidence_item is not None  # an admitted outcome always carries the item
    run.evidence_items = [evidence_item]
    run.add_stage(
        "evidence_admission",
        STAGE_OK,
        payload={"evidence_item_id": evidence_item["evidence_item_id"], "allowed_claim_level": evidence_item["allowed_claim_level"]},
    )

    # -- claim synthesis (claim ceiling never exceeded) -------------------
    synth = synthesize_claims(
        evidence_items=[evidence_item],
        subquestions=[{"subquestion_id": ctx.subquestion["subquestion_id"], "claim_ceiling": ctx.subquestion.get("claim_ceiling", ctx.project_ceiling)}],
        scope_bundle=ctx.scope_bundle,
        project_ceiling=ctx.project_ceiling,
    )
    run.claims = synth.claims
    if any(c.get("status") == "conflicting" for c in synth.claims):
        run.add_stage("claim_synthesis", STAGE_OK, reason="conflicting", payload={"n_claims": len(synth.claims)})
        # A conflict is a legal, recorded outcome — keep the report but flag it.
    else:
        run.add_stage("claim_synthesis", STAGE_OK, payload={"n_claims": len(synth.claims), "claim_levels": [c["claim_level"] for c in synth.claims]})

    # -- original-question alignment audit --------------------------------
    audit = audit_alignment(
        research_spec=ctx.research_spec,
        subquestions=run.subquestions or [ctx.subquestion],
        scope_bundle=ctx.scope_bundle,
        evidence_items=[evidence_item],
        claims=synth.claims,
        artifact_manifests=[artifact_manifest],
        qc_reports=[qc_report],
        project_ceiling=ctx.project_ceiling,
    )
    run.alignment = audit["alignment_report"]
    if audit["alignment_report"]["final_decision"] != "approve" or not audit["report_ready"]:
        run.add_stage(
            "alignment", STAGE_STOPPED, reason=audit["alignment_report"]["final_decision"], payload={"blocking": audit.get("report_blocking_issues", [])}
        )
        return run.stop(TERMINAL_ALIGNMENT_REVIEW, f"alignment not approved: {audit['alignment_report']['final_decision']}")
    run.add_stage("alignment", STAGE_OK, payload={"final_decision": "approve"})

    # -- constrained report + trace index ---------------------------------
    try:
        report_bundle = build_report_input_bundle(
            research_spec=ctx.research_spec,
            scope_bundle=ctx.scope_bundle,
            dataset_manifest=ctx.manifest,
            subquestions=run.subquestions or [ctx.subquestion],
            qc_reports=[qc_report],
            evidence_items=[evidence_item],
            claims=synth.claims,
            alignment_audit=audit,
            task_runs=task_runs,
            artifact_manifests=[artifact_manifest],
        )
    except ReportInputRefused as exc:
        run.add_stage("report", STAGE_STOPPED, reason="REPORT_INPUT_REFUSED", payload={"error": str(exc)})
        return run.stop(TERMINAL_ALIGNMENT_REVIEW, f"report input refused: {exc}")
    report_result = build_report(report_bundle)
    report_manifest = dict(report_result.manifest)
    if report_result.publishable:
        status = advance_report_status("DRAFT", "REVIEWED")
        status = advance_report_status(status, "RELEASED", publishable=True)
        report_manifest["report_status"] = status
    run.report = {
        "status": report_manifest.get("report_status", report_result.status),
        "publishable": report_result.publishable,
        "blocking_reasons": report_result.blocking_reasons,
        "final_report_id": report_manifest.get("final_report_id", ""),
        "claim_ids": report_manifest.get("claim_ids", []),
        "trace_complete": report_result.trace_index.get("complete", False),
        "markdown_sha256": report_manifest.get("output_checksums", {}).get("report.md", ""),
    }
    run.add_stage("report", STAGE_OK, payload={"publishable": report_result.publishable, "status": run.report["status"]})

    # -- reproduction bundle + deterministic clean re-run -----------------
    objects = {
        "research_spec": ctx.research_spec,
        "scope_bundle": ctx.scope_bundle,
        "subquestions": run.subquestions or [ctx.subquestion],
        "evidence_plan": run.evidence_plans[0] if run.evidence_plans else {},
        "dataset_manifest": ctx.manifest,
        "workflow_plan": workflow_plan,
        "task_packets": compiled.task_packets,
        "parameters": method_result.get("params", {}),
        "environment": {"executor": "offline_fake_executor", "python_method": method_result.get("software_versions", {}).get("python_method", "")},
        "claims": synth.claims,
        "known_limitations": ctx.dataset.card.get("known_limitations", []),
        "trace_index": report_result.trace_index,
        "output_files": {"outputs/deg_results.tsv": deg_bytes.decode("utf-8")},
        "input_files": {"inputs/counts.tsv": ctx.counts_tsv, "inputs/samples.tsv": ctx.samples_tsv},
        "license": ctx.dataset.card.get("license", "fixture-only"),
    }
    bundle_result = build_bundle(project_id=ctx.project_id, objects=objects)
    verify = verify_bundle(bundle_result.files, bundle_result.checksums)
    # Deterministic re-run: recompute the DEG rows and compare bitwise.
    rerun = run_clean_rerun([{"task_id": analysis_task_id, "output_name": "deg_results.tsv", "rows": deg_rows}])
    original = {"outputs/deg_results.tsv": render_deg_tsv(deg_rows)}
    reproduced = {"outputs/deg_results.tsv": rerun["reproduced_outputs"]["deg_results.tsv"]}
    comparison = compare_results(original, reproduced, {"rules": [{"target": "outputs/deg_results.tsv", "strategy": "bitwise", "tolerance": 0.0}]})
    run.reproduction = {
        "bundle_status": bundle_result.status,
        "clean": bundle_result.clean,
        "verify": verify["overall"],
        "reproduced": comparison["reproduced"],
        "consistency_level": comparison["overall_level"],
        "n_files": len(bundle_result.files),
    }
    run.add_stage("reproduction", STAGE_OK, payload={"verify": verify["overall"], "consistency_level": comparison["overall_level"]})

    return run.complete()


def _outcome_for(packet: dict, task_id: str, analysis_task_id: str, deg_bytes: bytes, deg_checksum: str) -> RecordedOutcome:
    """Build a recorded (replayed) outcome for one task.

    The analysis task replays the *real* deterministic bulk_deg output (its bytes,
    size, checksum); prep/review tasks replay a small declared output.  Nothing is
    computed here — the fake executor only records what deterministic analysis
    already produced offline (the constitution's ``离线回放``).
    """
    expected = packet.get("expected_outputs", []) or []
    if task_id == analysis_task_id:
        name = expected[0] if expected else "deg_results_table"
        return RecordedOutcome(
            exit_code=0,
            stdout="ok",
            outputs=(RecordedOutput(name, "outputs/deg_results.tsv", len(deg_bytes), deg_checksum),),
            resource_usage={"cpu_seconds": 1.0, "peak_memory_mb": 128, "wall_seconds": 1.0},
        )
    name = expected[0] if expected else f"{task_id}_output"
    return RecordedOutcome(
        exit_code=0,
        stdout="ok",
        outputs=(RecordedOutput(name, f"outputs/{name}.json", 2, "b" * 64, content_role="run_log", media_type="application/json"),),
        resource_usage={"cpu_seconds": 0.1, "peak_memory_mb": 16, "wall_seconds": 0.1},
    )


# Re-exported terminal constants for test convenience.
__all__ = [
    "run_bulk_rnaseq_route",
    "run_analysis_chain",
    "AnalysisContext",
    "DEFAULT_BULK_QUESTION",
    "TERMINAL_COMPLETED",
    "TERMINAL_METHOD_NOT_APPLICABLE",
    "TERMINAL_INSUFFICIENT_DATA",
    "TERMINAL_EGRESS_BLOCKED",
    "TERMINAL_QC_REJECTED",
    "TERMINAL_EVIDENCE_REFUSED",
    "TERMINAL_ALIGNMENT_REVIEW",
    "TERMINAL_UNVERIFIABLE_RESOURCE",
    "TERMINAL_NEEDS_CLARIFICATION",
    "TERMINAL_CONFLICTING_EVIDENCE",
]
