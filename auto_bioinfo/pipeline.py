"""The single production orchestrator for the auto-bioinfo closed loop.

``run()`` drives a project from a natural-language question all the way to a
reproduction bundle, advancing the canonical state machine one guarded step at a
time.  Every step (a) loads its inputs from the persisted state, (b) does its
work through an injected port, (c) writes typed objects, and (d) records an
explicit event/handoff before transitioning.  Because each step is guarded by the
current stage and writes idempotently, ``run()`` is also ``resume()``: calling it
again continues from wherever the project stopped.

This is the adapter the original ``canonical`` control plane never had — it
connects the planning front-half (which previously stopped at ``TASKS_READY``)
to *real* execution, QC, evidence, claims, alignment, reporting and reproduction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .adapters.fixture_resources import FixtureResourceAdapter
from .adapters.offline_planner import OfflineDeterministicPlanner
from .core.artifacts import build_artifact_manifest, load_artifact_registry, validate_artifact_for_evidence, write_artifact_manifest
from .core.handoff import build_handoff, write_handoff
from .core.agent_protocol import validate_agent_handoff
from .core.alignment_auditor import audit_question_alignment
from .core.ids import make_stable_id
from .core.provenance import (
    authoritative_release,
    build_project_policy,
    evaluate_scientific_eligibility,
    is_eligible,
    validate_provenance,
    verify_project_policy_integrity,
    validate_real_mode_dataset,
)
from .core.store import init_project_state, load_project_state, transition_state
from .core.task_packets import build_analysis_task_packet, build_review_task_packet, validate_task_packets
from .core.validation import validate_no_unknown_verified_dataset
from .evidence.synthesis import build_evidence_item, synthesize_claims
from .execution.objects import object_ref, read_object, write_object
from .execution.runs import (
    load_claims,
    load_evidence_items,
    load_qc_reports,
    write_claim,
    write_evidence_item,
    write_qc_report,
    write_task_run,
)
from .methods.registry import compatibility_decision, get_method
from .quality.qc_engine import run_four_layer_qc
from .report import build_final_report
from .reproduction.bundle import build_reproduction_bundle


class PipelineError(RuntimeError):
    """Raised on an unrecoverable, non-scientific failure (bad inputs/config)."""


class Pipeline:
    def __init__(self, *, planner: Any = None, resources: Any = None) -> None:
        self.planner = planner or OfflineDeterministicPlanner()
        self.resources = resources or FixtureResourceAdapter()

    # -- public API ----------------------------------------------------------

    def run(self, project_dir: str | Path, question: str | None = None, execution_mode: str = "DEMO") -> dict[str, Any]:
        project_dir = Path(project_dir)
        state_file = project_dir / "state" / "project_state.json"
        if not state_file.exists():
            if not question:
                raise PipelineError("a question is required to start a new project")
            # The immutable ProjectPolicy is the authoritative source of mode.
            policy = build_project_policy(project_dir.name, execution_mode)
            write_object(project_dir, "project_policy", policy)
            init_project_state(project_dir, question, execution_mode=execution_mode, project_policy_ref=policy["project_policy_id"])
        # The ProjectPolicy is immutable: recompute its integrity (hash/id) and
        # require ProjectState to agree, so editing either file is detected.
        policy = read_object(project_dir, "project_policy", {})
        integrity = verify_project_policy_integrity(policy, load_project_state(project_dir))
        if integrity:
            raise PipelineError(f"project policy integrity failure: {integrity}")

        # Drive guarded steps until a terminal/paused stage is reached.
        steps: list[tuple[str, Callable[[Path], None]]] = [
            ("INTAKE", self._normalize_question),
            ("QUESTION_RESOLVED", self._resolve_scope),
            ("SCOPE_RESOLVED", self._plan_evidence),
            ("EVIDENCE_PLANNED", self._discover_resources),
            ("RESOURCES_DISCOVERED", self._lock_datasets),
            ("DATASETS_LOCKED", self._compile_workflow),
            ("WORKFLOW_COMPILED", self._authorize),
            ("TASKS_READY", self._execute),
            ("TASKS_RUNNING", self._run_qc),
            ("QC_COMPLETED", self._synthesize_evidence),
            ("EVIDENCE_SYNTHESIZED", self._audit_alignment),
            ("ALIGNMENT_AUDITED", self._build_report),
            ("REPORT_READY", self._build_bundle),
            ("REPRODUCTION_BUNDLE_READY", self._complete),
        ]
        guard = 0
        while guard < 100:
            guard += 1
            stage = load_project_state(project_dir)["current_stage"]
            handler = dict(steps).get(stage)
            if handler is None:
                break  # terminal or paused (HUMAN_REVIEW_REQUIRED / COMPLETED / ...)
            before = stage
            handler(project_dir)
            after = load_project_state(project_dir)["current_stage"]
            if after == before:
                break  # handler chose to stop without advancing
        return self.inspect(project_dir)

    resume = run  # resume is just run() from the persisted stage.

    def inspect(self, project_dir: str | Path) -> dict[str, Any]:
        project_dir = Path(project_dir)
        state = load_project_state(project_dir)
        claims = load_claims(project_dir)
        evidence_items = load_evidence_items(project_dir)
        # Authoritative eligibility gate: recompute from the persisted decision +
        # active policy; never trust the cached flag on a Claim/EvidenceItem.
        release = authoritative_release(
            read_object(project_dir, "scientific_eligibility_decision", {}),
            policy=read_object(project_dir, "project_policy", {}),
            claims=claims,
            evidence_items=evidence_items,
        )
        return {
            "project_id": state["project_id"],
            "current_stage": state["current_stage"],
            "stage_history": state.get("stage_history", []),
            "execution_mode": state.get("execution_mode", "DEMO"),
            "release_status": release["release_status"],
            "scientific_output_eligible": release["scientific_output_eligible"],
            "research_spec": read_object(project_dir, "research_spec", {}),
            "claims": claims,
            "evidence_items": evidence_items,
            "qc_reports": load_qc_reports(project_dir),
            "artifacts": load_artifact_registry(project_dir),
            "alignment": read_object(project_dir, "question_alignment_report", {}),
            "final_report": read_object(project_dir, "final_report_manifest", {}),
            "reproduction_bundle": read_object(project_dir, "reproduction_bundle_manifest", {}),
        }

    # -- stage handlers ------------------------------------------------------

    def _normalize_question(self, project_dir: Path) -> None:
        question = load_project_state(project_dir).get("user_question", "")
        spec = self.planner.normalize_question(project_dir.name, question)
        subs = self.planner.decompose(spec)
        rs_ref = write_object(project_dir, "research_spec", spec)
        write_object(project_dir, "subquestions", subs)
        self._handoff(project_dir, "question_normalizer", "scope_resolver", [], [rs_ref], "descriptive")
        self._advance(project_dir, "QUESTION_RESOLVED", "question_normalizer", [rs_ref], "Normalized question into ResearchSpec + SubQuestions.")

    def _resolve_scope(self, project_dir: Path) -> None:
        spec = read_object(project_dir, "research_spec")
        subs = read_object(project_dir, "subquestions")
        scope = self.planner.resolve_scope(spec, subs)
        ref = write_object(project_dir, "scope_bundle", scope)
        self._handoff(project_dir, "scope_resolver", "evidence_plan_builder", [], [ref], "descriptive")
        self._advance(project_dir, "SCOPE_RESOLVED", "scope_resolver", [ref], "Resolved scope bundle.")

    def _plan_evidence(self, project_dir: Path) -> None:
        spec = read_object(project_dir, "research_spec")
        subs = read_object(project_dir, "subquestions")
        plan = self.planner.plan_evidence(spec, subs)
        ref = write_object(project_dir, "evidence_plan", plan)
        self._handoff(project_dir, "evidence_plan_builder", "resource_discovery_agent", [], [ref], "association")
        self._advance(project_dir, "EVIDENCE_PLANNED", "evidence_plan_builder", [ref], "Built evidence plan.")

    def _discover_resources(self, project_dir: Path) -> None:
        spec = read_object(project_dir, "research_spec")
        plan = read_object(project_dir, "evidence_plan")
        execution_mode = self._execution_mode(project_dir)
        candidates = self.resources.discover(spec, plan)
        # Hard guard: a verified dataset may never come from a mock/placeholder source.
        for c in candidates:
            errors = validate_no_unknown_verified_dataset(c)
            errors += validate_provenance(c)
            if errors:
                raise PipelineError(f"resource discovery produced an invalid/ inconsistent dataset: {errors}")
            # R0-01: a REAL run may not be backed by a synthetic fixture; stop
            # conservatively *before* any dataset is locked.
            policy_errors = validate_real_mode_dataset(c, execution_mode)
            if policy_errors:
                write_object(project_dir, "policy_failure", {"failure_class": "POLICY_FAILURE", "reasons": policy_errors, "candidate": c.get("resource_candidate_id", "")})
                self._advance(project_dir, "FAILED", "policy_gate", [], f"POLICY_FAILURE: {policy_errors}")
                return
        profile = self.resources.profile(candidates[0])
        write_object(project_dir, "resource_candidates", candidates)
        ref = write_object(project_dir, "dataset_profile", profile)
        self._handoff(project_dir, "resource_discovery_agent", "method_adapter_workorder_compiler", [], [ref], "association")
        self._advance(project_dir, "RESOURCES_DISCOVERED", "resource_discovery_agent", [ref], "Discovered + profiled a verified dataset.")

    def _lock_datasets(self, project_dir: Path) -> None:
        profile = read_object(project_dir, "dataset_profile")
        subs = read_object(project_dir, "subquestions")
        inputs_dir = project_dir / "state" / "inputs"
        files = self.resources.materialize(profile, str(inputs_dir))
        checksums = {name: build_artifact_manifest(project_dir, Path(path).relative_to(project_dir), producer="resource_discovery_agent", artifact_type="input_dataset", expected_by_task_ids=[], supports_subquestion_ids=[])["checksum_sha256"] for name, path in files.items()}
        manifest = {
            "dataset_manifest_id": make_stable_id("dataset_manifest", {"dataset_id": profile["dataset_id"], "checksums": checksums}),
            "dataset_id": profile["dataset_id"],
            "accession": profile.get("accession", ""),
            "source_status": profile.get("source_status", ""),
            "samples": [{"group": g, "n": n} for g, n in profile.get("group_sizes", {}).items()],
            "excluded_samples": [],
            "file_checksums": checksums,
            "materialized_files": {name: str(Path(path).relative_to(project_dir)) for name, path in files.items()},
            "supports_subquestion_ids": [s["subquestion_id"] for s in subs],
            "known_limitations": profile.get("known_limitations", []),
            "manifest_version": 1,
            "locked": True,
            "status": "locked",
        }
        ref = write_object(project_dir, "dataset_manifest", manifest)
        self._advance(project_dir, "DATASETS_LOCKED", "resource_discovery_agent", [ref], "Locked dataset manifest with file checksums.")

    def _compile_workflow(self, project_dir: Path) -> None:
        profile = read_object(project_dir, "dataset_profile")
        subs = read_object(project_dir, "subquestions")
        ceiling = read_object(project_dir, "evidence_plan").get("max_claim_level", "association")
        decision = compatibility_decision("bulk_deg", profile)
        write_object(project_dir, "compatibility_decision", decision)
        if not decision["compatible"]:
            self._advance(project_dir, "METHOD_NOT_APPLICABLE", "method_adapter_workorder_compiler", [], f"No compatible method: {decision['reason']}")
            return
        analysis = build_analysis_task_packet(
            subquestion_id=subs[0]["subquestion_id"],
            method_name="bulk_deg",
            expected_inputs=["counts", "samples"],
            expected_outputs=["deg_results_table"],
            qc_requirements=["execution", "data", "statistical", "biological"],
            failure_conditions=["minimum_design_not_met", "missing_input_file"],
        )
        review = build_review_task_packet(
            subquestion_id=subs[0]["subquestion_id"],
            audit_scope=["task_run", "artifact_manifest", "qc_report"],
            claim_ceiling=ceiling,
            required_checks=["claim_ceiling_not_loosened", "only_qc_passed_artifacts_become_evidence"],
        )
        packets = [analysis, review]
        errors = validate_task_packets(packets)
        if errors:
            raise PipelineError("; ".join(errors))
        workflow = {
            "workflow_plan_id": make_stable_id("workflow_plan", {"project_id": project_dir.name, "task_ids": [p["task_id"] for p in packets]}),
            "workflow_name": "bulk_deg_vertical_slice",
            "task_ids": [p["task_id"] for p in packets],
            "analysis_method": "bulk_deg",
            "method_contract_id": decision["method_contract_id"],
            "status": "compiled",
        }
        write_object(project_dir, "workflow_plan", workflow)
        write_object(project_dir, "task_packets", packets)
        self._advance(project_dir, "WORKFLOW_COMPILED", "method_adapter_workorder_compiler", [object_ref(project_dir, "workflow_plan")], "Compiled workflow + task packets.")

    def _authorize(self, project_dir: Path) -> None:
        wf_ref = object_ref(project_dir, "workflow_plan")
        self._handoff(project_dir, "method_adapter_workorder_compiler", "result_auditor", [], [wf_ref], "association")
        self._advance(project_dir, "TASKS_READY", "method_adapter_workorder_compiler", [wf_ref], "Execution authorized; task packets ready.")

    def _execute(self, project_dir: Path) -> None:
        manifest = read_object(project_dir, "dataset_manifest")
        packets = read_object(project_dir, "task_packets")
        analysis = next(p for p in packets if p.get("packet_type") == "AnalysisTaskPacket")
        method = get_method("bulk_deg")
        inputs = {name: str(project_dir / rel) for name, rel in manifest["materialized_files"].items()}
        out_dir = project_dir / "state" / "runs" / analysis["task_id"]
        result = method.run(inputs=inputs, params={}, out_dir=str(out_dir))

        if result["status"] != "succeeded":
            # Conservative stop: design not met → INSUFFICIENT_DATA, not a fabricated result.
            result["task_id"] = analysis["task_id"]
            write_object(project_dir, "method_result", result)
            self._advance(project_dir, "INSUFFICIENT_DATA", "analysis_worker", [], f"Analysis stopped: {result.get('reason')}")
            return

        task_run_id = make_stable_id("task_run", {"task_id": analysis["task_id"], "output": result["output_path"]})
        result["task_id"] = analysis["task_id"]
        result["task_run_id"] = task_run_id
        write_object(project_dir, "method_result", result)
        rel_out = Path(result["output_path"]).relative_to(project_dir)
        artifact = build_artifact_manifest(
            project_dir,
            rel_out,
            producer="analysis_worker",
            artifact_type="deg_results_table",
            expected_by_task_ids=[analysis["task_id"]],
            supports_subquestion_ids=[analysis["subquestion_id"]],
            producer_run_id=task_run_id,
            qc_status="pending",
        )
        write_object(project_dir, "pending_artifact", artifact)
        task_run = {
            "task_run_id": task_run_id,
            "task_id": analysis["task_id"],
            "result_status": result["status"],
            "method_id": result["method_id"],
            "method_version": result["version"],
            "params": result["params"],
            "software_versions": result["software_versions"],
            "artifact_refs": [artifact["artifact_id"]],
            "n_significant": result["n_significant"],
            "status": "recorded",
        }
        write_task_run(project_dir, task_run)
        self._advance(project_dir, "TASKS_RUNNING", "analysis_worker", [], "Executed bulk_deg; produced DEG artifact.")

    def _run_qc(self, project_dir: Path) -> None:
        result = read_object(project_dir, "method_result")
        profile = read_object(project_dir, "dataset_profile")
        artifact = read_object(project_dir, "pending_artifact")
        contract = get_method("bulk_deg").contract()
        report = run_four_layer_qc(method_result=result, dataset_profile=profile, artifact_manifest=artifact, contract=contract)
        write_qc_report(project_dir, report)
        # Finalize and register the artifact with its QC status.
        artifact["qc_status"] = "pass" if report["overall_status"] in {"pass", "pass_with_warnings"} else "fail"
        write_artifact_manifest(project_dir, artifact)
        write_object(project_dir, "registered_artifact", artifact)
        self._advance(project_dir, "QC_COMPLETED", "result_auditor", [], f"Four-layer QC complete: {report['decision']}.")

    def _synthesize_evidence(self, project_dir: Path) -> None:
        artifact = read_object(project_dir, "registered_artifact")
        result = read_object(project_dir, "method_result")
        profile = read_object(project_dir, "dataset_profile")
        scope = read_object(project_dir, "scope_bundle")
        subs = read_object(project_dir, "subquestions")
        ceiling = read_object(project_dir, "research_spec").get("claim_ceiling", "association")
        contract = get_method("bulk_deg").contract()

        gate_errors = validate_artifact_for_evidence(artifact)
        if gate_errors or artifact.get("qc_status") != "pass":
            # No admissible evidence → stop safely.
            self._advance(project_dir, "INSUFFICIENT_DATA", "result_auditor", [], f"No QC-passed artifact for evidence: {gate_errors or artifact.get('qc_status')}")
            return

        # R0-01: recompute scientific eligibility from the source objects (never
        # trust an eligible flag already on an object).  In DEMO/TEST this is
        # INELIGIBLE, so the loop still completes but produces *demonstration*
        # evidence/claims that can never enter the formal scientific pool.
        policy = read_object(project_dir, "project_policy", {})
        decision = evaluate_scientific_eligibility(
            execution_mode=policy.get("execution_mode", "DEMO"),
            source_class=profile.get("source_class", "LEGACY_UNKNOWN"),
            retrieval_mode=profile.get("retrieval_mode", "LOCAL_CACHE"),
            verification_level=profile.get("verification_level", "UNVERIFIED"),
            qc_status=artifact.get("qc_status", ""),
            evaluated_input_refs=[artifact.get("artifact_id", ""), profile.get("dataset_profile_id", "")],
            evaluated_input_hashes=[artifact.get("checksum_sha256", "")],
            policy_id=policy.get("project_policy_id", ""),
            policy_version=policy.get("policy_version", 1),
        )
        write_object(project_dir, "scientific_eligibility_decision", decision)

        evidence = build_evidence_item(
            deg_table_path=str(project_dir / artifact["path"]),
            method_result=result,
            artifact_manifest=artifact,
            qc_report=read_object_latest_qc(project_dir),
            dataset_profile=profile,
            scope_bundle=scope,
            subquestion_ids=[s["subquestion_id"] for s in subs],
            contract=contract,
            project_ceiling=ceiling,
            eligibility_decision=decision,
        )
        write_evidence_item(project_dir, evidence)
        claims = synthesize_claims(evidence_items=[evidence], research_spec=read_object(project_dir, "research_spec"), scope_bundle=scope, project_ceiling=ceiling, eligibility_decision=decision)
        for claim in claims:
            write_claim(project_dir, claim)
        ev_ref = {"object_type": "EvidenceItem", "object_id": evidence["evidence_item_id"], "audit_status": "audited"}
        self._handoff(project_dir, "result_auditor", "evidence_synthesizer_reporter", [], [], "association", evidence_refs=[ev_ref])
        self._advance(project_dir, "EVIDENCE_SYNTHESIZED", "result_auditor", [], f"Synthesized {len(claims)} claim(s) from audited evidence.")

    def _audit_alignment(self, project_dir: Path) -> None:
        report = audit_question_alignment(
            research_spec=read_object(project_dir, "research_spec"),
            subquestions=read_object(project_dir, "subquestions"),
            scope_bundle=read_object(project_dir, "scope_bundle"),
            evidence_item_refs=load_evidence_items(project_dir),
            claims=load_claims(project_dir),
            artifact_manifests=load_artifact_registry(project_dir),
            qc_reports=load_qc_reports(project_dir),
            max_claim_level=read_object(project_dir, "research_spec").get("claim_ceiling", "association"),
        )
        write_object(project_dir, "question_alignment_report", report)
        self._advance(project_dir, "ALIGNMENT_AUDITED", "evidence_synthesizer_reporter", [], f"Alignment audit decision: {report['final_decision']}.")
        if report["final_decision"] != "approve":
            # Blocking issue: do not emit a clean report; pause for a human.
            self._advance(project_dir, "HUMAN_REVIEW_REQUIRED", "evidence_synthesizer_reporter", [], f"Alignment not approved ({report['final_decision']}); human review required.")

    def _build_report(self, project_dir: Path) -> None:
        manifest = build_final_report(project_dir)
        write_object(project_dir, "final_report_manifest", manifest)
        self._advance(project_dir, "REPORT_READY", "evidence_synthesizer_reporter", [object_ref(project_dir, "final_report_manifest")], "Built final report from approved claims.")

    def _build_bundle(self, project_dir: Path) -> None:
        manifest = build_reproduction_bundle(project_dir)
        write_object(project_dir, "reproduction_bundle_manifest", manifest)
        self._advance(project_dir, "REPRODUCTION_BUNDLE_READY", "evidence_synthesizer_reporter", [object_ref(project_dir, "reproduction_bundle_manifest")], "Built reproduction bundle with checksums.")

    def _complete(self, project_dir: Path) -> None:
        self._advance(project_dir, "COMPLETED", "system", [], "Closed loop completed end-to-end.")

    # -- helpers -------------------------------------------------------------

    def _execution_mode(self, project_dir: Path) -> str:
        """Authoritative execution mode comes from the immutable ProjectPolicy."""
        policy = read_object(project_dir, "project_policy", {})
        return policy.get("execution_mode", "DEMO")

    def _advance(self, project_dir: Path, next_stage: str, actor: str, object_refs: list[dict[str, Any]], message: str) -> None:
        transition_state(project_dir, next_stage, next_stage, actor, object_refs, message)

    def _handoff(self, project_dir: Path, from_agent: str, to_agent: str, input_refs: list[dict[str, Any]], output_refs: list[dict[str, Any]], ceiling: str, evidence_refs: list[dict[str, Any]] | None = None) -> None:
        handoff = build_handoff(
            project_id=project_dir.name,
            from_agent=from_agent,
            to_agent=to_agent,
            input_object_refs=input_refs,
            output_object_refs=output_refs,
            evidence_refs=evidence_refs or [],
            max_allowed_claim=ceiling,
            claim_ceiling_reason=f"{from_agent} hands off within the project claim ceiling.",
        )
        validation = validate_agent_handoff(handoff, from_agent, to_agent)
        if validation["status"] == "invalid":
            raise PipelineError(f"invalid handoff {from_agent}->{to_agent}: {validation['errors']}")
        write_handoff(project_dir, handoff)


def read_object_latest_qc(project_dir: str | Path) -> dict[str, Any]:
    reports = load_qc_reports(project_dir)
    return reports[-1] if reports else {}


def run(project_dir: str | Path, question: str | None = None) -> dict[str, Any]:
    """Convenience entry: run (or resume) the closed loop for a project."""
    return Pipeline().run(project_dir, question)
