"""Deterministic WorkflowPlan + Artifact DAG compiler (WP-12).

Compiles a per-sub-question :class:`~auto_bioinfo.methods.compatibility.MethodPlan`
(with its dataset manifest inputs) into an explicit, acyclic task/artifact DAG:
DataPreparation → Analysis → Review nodes, bound by *artifact ids* (never by path
guessing), with the allowed claim level propagated along every evidence path and
all critical execution fields injected.  The compiled plan is a reused
:class:`~auto_bioinfo.core.schemas.WorkflowPlan` plus immutable TaskPacket and
ArtifactExpectation projections whose content hash can be recomputed (T-12-13).

The compiler is a pure function of its in-memory inputs: no engine, no
subprocess, no scheduling, no clock read, no network, no filesystem effect.  It
never emits a half-finished formal plan — a diagnostic that blocks compilation
yields a ``REPLAN`` (or ``DRAFT_INCOMPLETE``) result carrying actionable
diagnostics, never a partial ``COMPILED`` plan (T-12-15).  Deterministic:
byte-identical inputs → byte-identical plan and plan hash; drafts carry an empty
``created_at``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import CLAIM_LEVELS, WorkflowPlan
from ..core.validation import validate_workflow_plan
from ..methods.compatibility import PLAN_METHOD_NOT_APPLICABLE
from ..methods.contract_registry import MethodRegistry

# --- Bounded compiler result statuses ----------------------------------------
COMPILE_OK = "compiled"
COMPILE_REPLAN = "replan"
COMPILE_DRAFT_INCOMPLETE = "draft_incomplete"
COMPILE_STATUSES = (COMPILE_OK, COMPILE_REPLAN, COMPILE_DRAFT_INCOMPLETE)

# --- Bounded diagnostic codes ------------------------------------------------
DIAG_DAG_CYCLE = "DAG_CYCLE"
DIAG_MISSING_PRODUCER = "MISSING_PRODUCER"
DIAG_ORPHAN_NODE = "ORPHAN_NODE"
DIAG_UNCOVERED_SUBQUESTION = "UNCOVERED_SUBQUESTION"
DIAG_MISSING_EXECUTION_FIELD = "MISSING_EXECUTION_FIELD"
DIAG_CLAIM_LEVEL_VIOLATION = "CLAIM_LEVEL_VIOLATION"
DIAG_INVALID_CLAIM_LEVEL = "INVALID_CLAIM_LEVEL"
DIAG_METHOD_NOT_APPLICABLE = "METHOD_NOT_APPLICABLE"
DIAG_INVALID_PLAN = "INVALID_WORKFLOW_PLAN"
DIAG_NO_ACTIVE_CONTRACT = "NO_ACTIVE_CONTRACT"
DIAG_CODES = (
    DIAG_DAG_CYCLE,
    DIAG_MISSING_PRODUCER,
    DIAG_ORPHAN_NODE,
    DIAG_UNCOVERED_SUBQUESTION,
    DIAG_MISSING_EXECUTION_FIELD,
    DIAG_CLAIM_LEVEL_VIOLATION,
    DIAG_INVALID_CLAIM_LEVEL,
    DIAG_METHOD_NOT_APPLICABLE,
    DIAG_INVALID_PLAN,
    DIAG_NO_ACTIVE_CONTRACT,
)

# Node types (bounded).  Review is never merged with Analysis (T-12-04).
NODE_DATA_PREPARATION = "DataPreparation"
NODE_ANALYSIS = "Analysis"
NODE_REVIEW = "Review"

# The critical execution fields every node's packet must carry (T-12-09).  A
# missing one blocks compilation rather than shipping an unexecutable node.
REQUIRED_EXECUTION_FIELDS = ("resource_estimate", "timeout_seconds", "retry_policy", "network_policy", "write_scope")

COMPILER_VERSION = "wp12-dag-compiler/0.1"


@dataclass(frozen=True)
class ExecutionDefaults:
    """Default execution facts injected into every node (T-12-09).

    A node inherits these unless a per-node override is supplied; every one of
    :data:`REQUIRED_EXECUTION_FIELDS` must resolve to a non-empty value or the
    node is not compilable.
    """

    resource_estimate: dict[str, Any] = field(default_factory=lambda: {"cpu": 1, "memory_mb": 2048})
    timeout_seconds: int = 3600
    retry_policy: dict[str, Any] = field(default_factory=lambda: {"max_attempts": 1, "retry_on": []})
    network_policy: dict[str, Any] = field(default_factory=lambda: {"egress": "deny"})
    write_scope: str = "outputs/"

    def as_fields(self) -> dict[str, Any]:
        return {
            "resource_estimate": dict(self.resource_estimate),
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": dict(self.retry_policy),
            "network_policy": dict(self.network_policy),
            "write_scope": self.write_scope,
        }


@dataclass
class ArtifactExpectation:
    """The declared expectation of one output artifact (T-12-02/13).

    Binds an artifact id to the task that produces it, its declared output name /
    media type / schema, the tasks that consume it, and the hard claim level that
    artifact may support.  Ids, not paths, are the join key.
    """

    artifact_id: str
    output_name: str
    producer_task_id: str
    subquestion_id: str
    media_type: str = ""
    schema_name: str = ""
    allowed_claim_level: str = "descriptive"
    consumed_by_task_ids: list[str] = field(default_factory=list)
    terminal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DagNode:
    """One task node with artifact-id-level input/output ports (T-12-01)."""

    task_id: str
    node_type: str
    subquestion_id: str
    input_artifact_ids: list[str]
    output_artifact_ids: list[str]
    allowed_claim_level: str
    method_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    execution_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompiledWorkflow:
    """The bounded, deterministic result of a compile.

    ``status`` is one of :data:`COMPILE_STATUSES`.  A ``compiled`` result carries a
    valid, acyclic WorkflowPlan, the immutable TaskPacket/ArtifactExpectation
    projections, node annotations, a coverage report, and both a machine JSON and a
    human Markdown rendering of the DAG.  A blocked result carries diagnostics and
    no formal plan (only DRAFT-status data).
    """

    status: str
    workflow_plan: dict[str, Any] | None
    task_packets: list[dict[str, Any]]
    artifact_expectations: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    coverage: dict[str, Any]
    plan_hash: str = ""
    dag_json: dict[str, Any] = field(default_factory=dict)
    dag_markdown: str = ""
    compiler_version: str = COMPILER_VERSION

    @property
    def compiled(self) -> bool:
        return self.status == COMPILE_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "compiler_version": self.compiler_version,
            "workflow_plan": self.workflow_plan,
            "task_packets": list(self.task_packets),
            "artifact_expectations": list(self.artifact_expectations),
            "nodes": list(self.nodes),
            "diagnostics": list(self.diagnostics),
            "coverage": dict(self.coverage),
            "plan_hash": self.plan_hash,
            "dag_json": dict(self.dag_json),
            "dag_markdown": self.dag_markdown,
        }


def _artifact_id(producer_task_id: str, output_name: str) -> str:
    return make_stable_id("artifact_port", {"producer": producer_task_id, "output_name": output_name})


def _node_task_id(node_type: str, subquestion_id: str, method_id: str, salt: str) -> str:
    return make_stable_id("dag_task", {"node_type": node_type, "subquestion_id": subquestion_id, "method_id": method_id, "salt": salt})


def _min_claim(a: str, b: str) -> str:
    if a not in CLAIM_LEVELS:
        return b if b in CLAIM_LEVELS else "descriptive"
    if b not in CLAIM_LEVELS:
        return a
    return min(a, b, key=CLAIM_LEVELS.index)


def _diag(code: str, message: str, *, blocking: bool, task_id: str = "", subquestion_id: str = "") -> dict[str, Any]:
    return {
        "code": code,
        "severity": "blocking" if blocking else "warning",
        "message": message,
        "task_id": task_id,
        "subquestion_id": subquestion_id,
    }


def compile_workflow(
    registry: MethodRegistry,
    plans: list[dict[str, Any]],
    *,
    project_id: str,
    workflow_name: str = "compiled_analysis_workflow",
    execution_defaults: ExecutionDefaults | None = None,
    required_subquestion_ids: list[str] | None = None,
) -> CompiledWorkflow:
    """Compile method plans into a WorkflowPlan + Artifact DAG.

    ``plans`` is a list of ``{"subquestion": {...}, "method_plan": {...},
    "manifest_inputs": [artifact_id, ...]}`` items.  A ``method_not_applicable``
    plan contributes an uncovered sub-question and blocks compilation (T-12-15).
    The returned :class:`CompiledWorkflow` is ``compiled`` only when every check
    passes; otherwise its status is ``replan`` / ``draft_incomplete`` with
    diagnostics and no formal plan.
    """
    defaults = execution_defaults or ExecutionDefaults()
    diagnostics: list[dict[str, Any]] = []
    nodes: list[DagNode] = []
    expectations: dict[str, ArtifactExpectation] = {}
    dependencies: list[list[str]] = []

    covered_subquestions: set[str] = set()

    def _sq_id(item: dict[str, Any]) -> str:
        return str(item.get("subquestion", {}).get("subquestion_id", "") or item.get("method_plan", {}).get("subquestion_id", ""))

    # When the caller does not pin the required set, every planned sub-question is
    # required to have a terminal evidence path.
    if required_subquestion_ids is None:
        all_required = {_sq_id(item) for item in plans if _sq_id(item)}
    else:
        all_required = set(required_subquestion_ids)

    for plan_item in plans:
        method_plan = plan_item.get("method_plan", {})
        manifest_inputs = list(plan_item.get("manifest_inputs", []))
        subquestion_id = _sq_id(plan_item)

        if method_plan.get("status") == PLAN_METHOD_NOT_APPLICABLE or not method_plan.get("primary_method_id"):
            diagnostics.append(
                _diag(
                    DIAG_METHOD_NOT_APPLICABLE,
                    f"sub-question {subquestion_id!r} has no applicable method; cannot compile an analysis node (stop, do not free-write code)",
                    blocking=True,
                    subquestion_id=subquestion_id,
                )
            )
            continue

        method_id = str(method_plan["primary_method_id"])
        contract = registry.active_contract(method_id)
        if contract is None:
            diagnostics.append(
                _diag(DIAG_NO_ACTIVE_CONTRACT, f"no active contract for primary method {method_id!r}", blocking=True, subquestion_id=subquestion_id)
            )
            continue

        # Fail-closed claim-level validation: never compile a formal plan from a
        # claim level we do not recognise.  Every level accepted from the method
        # plan or the contract must be a member of CLAIM_LEVELS, or the whole
        # sub-question is blocked with a bounded diagnostic (no COMPILE_OK, no
        # formal WorkflowPlan with an invalid gate ceiling).
        imposed_claim = method_plan.get("imposed_claim_ceiling")
        contract_claim = contract.get("claim_capability", "descriptive")
        invalid_claim = False
        if imposed_claim not in (None, "") and imposed_claim not in CLAIM_LEVELS:
            diagnostics.append(
                _diag(
                    DIAG_INVALID_CLAIM_LEVEL,
                    f"sub-question {subquestion_id!r} imposed_claim_ceiling {imposed_claim!r} is not a recognised claim level; refusing to compile",
                    blocking=True,
                    subquestion_id=subquestion_id,
                )
            )
            invalid_claim = True
        if contract_claim not in CLAIM_LEVELS:
            diagnostics.append(
                _diag(
                    DIAG_INVALID_CLAIM_LEVEL,
                    f"contract for method {method_id!r} declares claim_capability {contract_claim!r} not in CLAIM_LEVELS; refusing to compile",
                    blocking=True,
                    subquestion_id=subquestion_id,
                )
            )
            invalid_claim = True
        if invalid_claim:
            continue

        allowed_claim = str(imposed_claim or contract_claim)
        exec_fields = defaults.as_fields()

        # 1. DataPreparation node — consumes manifest inputs, produces a prepared input artifact.
        prep_task = _node_task_id(NODE_DATA_PREPARATION, subquestion_id, method_id, "prep")
        prep_output_name = f"prepared_input__{method_id}"
        prep_artifact = _artifact_id(prep_task, prep_output_name)
        nodes.append(
            DagNode(
                task_id=prep_task,
                node_type=NODE_DATA_PREPARATION,
                subquestion_id=subquestion_id,
                input_artifact_ids=list(manifest_inputs),
                output_artifact_ids=[prep_artifact],
                allowed_claim_level=allowed_claim,
                method_id=method_id,
                execution_fields=exec_fields,
            )
        )
        expectations[prep_artifact] = ArtifactExpectation(
            artifact_id=prep_artifact,
            output_name=prep_output_name,
            producer_task_id=prep_task,
            subquestion_id=subquestion_id,
            media_type="text/tab-separated-values",
            schema_name="prepared_input",
            allowed_claim_level=allowed_claim,
        )

        # 2. Analysis node — consumes the prepared artifact, produces contract outputs.
        analysis_task = _node_task_id(NODE_ANALYSIS, subquestion_id, method_id, "analysis")
        contract_outputs = [o for o in contract.get("outputs", []) if isinstance(o, str) and o.strip()] or ["analysis_result"]
        analysis_output_ids: list[str] = []
        for output_name in contract_outputs:
            aid = _artifact_id(analysis_task, output_name)
            analysis_output_ids.append(aid)
            expectations[aid] = ArtifactExpectation(
                artifact_id=aid,
                output_name=output_name,
                producer_task_id=analysis_task,
                subquestion_id=subquestion_id,
                media_type="text/tab-separated-values",
                schema_name=output_name,
                allowed_claim_level=allowed_claim,
            )
        nodes.append(
            DagNode(
                task_id=analysis_task,
                node_type=NODE_ANALYSIS,
                subquestion_id=subquestion_id,
                input_artifact_ids=[prep_artifact],
                output_artifact_ids=analysis_output_ids,
                allowed_claim_level=allowed_claim,
                method_id=method_id,
                params=dict(plan_item.get("method_params", {})),
                execution_fields=exec_fields,
            )
        )
        dependencies.append([analysis_task, prep_task])
        expectations[prep_artifact].consumed_by_task_ids.append(analysis_task)

        # 3. Review/QC node — consumes analysis outputs, produces a terminal review artifact.
        review_task = _node_task_id(NODE_REVIEW, subquestion_id, method_id, "review")
        review_output_name = f"review_report__{method_id}"
        review_artifact = _artifact_id(review_task, review_output_name)
        nodes.append(
            DagNode(
                task_id=review_task,
                node_type=NODE_REVIEW,
                subquestion_id=subquestion_id,
                input_artifact_ids=list(analysis_output_ids),
                output_artifact_ids=[review_artifact],
                allowed_claim_level=allowed_claim,
                method_id=method_id,
                execution_fields=exec_fields,
            )
        )
        expectations[review_artifact] = ArtifactExpectation(
            artifact_id=review_artifact,
            output_name=review_output_name,
            producer_task_id=review_task,
            subquestion_id=subquestion_id,
            media_type="application/json",
            schema_name="review_report",
            allowed_claim_level=allowed_claim,
            terminal=True,
        )
        for aid in analysis_output_ids:
            dependencies.append([review_task, analysis_task])
            expectations[aid].consumed_by_task_ids.append(review_task)
        # De-dupe potential repeated edges (multi-output analysis).
        dependencies = _dedupe_edges(dependencies)

        covered_subquestions.add(subquestion_id)

    # --- structural diagnostics ---------------------------------------------
    diagnostics += _check_execution_fields(nodes)
    diagnostics += _check_producers(nodes, expectations)
    diagnostics += _check_claim_propagation(nodes, expectations)
    diagnostics += _check_coverage(all_required, covered_subquestions)

    task_ids = [n.task_id for n in nodes]
    plan = WorkflowPlan(
        workflow_name=workflow_name,
        task_ids=task_ids,
        dependencies=dependencies,
        expected_inputs={n.task_id: list(n.input_artifact_ids) for n in nodes if n.input_artifact_ids},
        expected_outputs={n.task_id: list(n.output_artifact_ids) for n in nodes if n.output_artifact_ids},
        gates=[{"task_id": n.task_id, "gate": "qc_review", "claim_ceiling": n.allowed_claim_level} for n in nodes if n.node_type == NODE_REVIEW],
        status="draft",
        created_at="",
    )
    plan_dict = plan.to_dict()

    plan_errors = validate_workflow_plan(plan_dict) if task_ids else []
    for err in plan_errors:
        code = DIAG_DAG_CYCLE if "cycle" in err else DIAG_INVALID_PLAN
        diagnostics.append(_diag(code, err, blocking=True))

    coverage = {
        "required_subquestion_ids": sorted(all_required),
        "covered_subquestion_ids": sorted(covered_subquestions),
        "uncovered_subquestion_ids": sorted(all_required - covered_subquestions),
        "fully_covered": all_required <= covered_subquestions and bool(all_required),
    }

    blocking = [d for d in diagnostics if d["severity"] == "blocking"]
    if blocking or not task_ids:
        # No half-finished formal plan: emit REPLAN with a DRAFT-status plan only.
        return CompiledWorkflow(
            status=COMPILE_REPLAN,
            workflow_plan=None,
            task_packets=[],
            artifact_expectations=[e.to_dict() for e in _sorted_expectations(expectations)],
            nodes=[n.to_dict() for n in nodes],
            diagnostics=diagnostics,
            coverage=coverage,
        )

    task_packets = _build_task_packets(nodes, registry)
    dag_json = _machine_json(nodes, dependencies, expectations)
    plan_hash = make_stable_id("workflow_plan_content", {"plan": plan.canonical(), "expectations": dag_json["artifacts"]})

    return CompiledWorkflow(
        status=COMPILE_OK,
        workflow_plan=plan_dict,
        task_packets=task_packets,
        artifact_expectations=[e.to_dict() for e in _sorted_expectations(expectations)],
        nodes=[n.to_dict() for n in nodes],
        diagnostics=diagnostics,
        coverage=coverage,
        plan_hash=plan_hash,
        dag_json=dag_json,
        dag_markdown=_render_markdown(nodes, dependencies, workflow_name),
    )


def _dedupe_edges(edges: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, str]] = set()
    out: list[list[str]] = []
    for edge in edges:
        key = (edge[0], edge[1])
        if key not in seen:
            seen.add(key)
            out.append(list(edge))
    return out


def _sorted_expectations(expectations: dict[str, ArtifactExpectation]) -> list[ArtifactExpectation]:
    for exp in expectations.values():
        exp.consumed_by_task_ids = sorted(set(exp.consumed_by_task_ids))
    return [expectations[k] for k in sorted(expectations)]


def _check_execution_fields(nodes: list[DagNode]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        for f in REQUIRED_EXECUTION_FIELDS:
            value = node.execution_fields.get(f)
            if value in (None, "", {}, []):
                out.append(_diag(DIAG_MISSING_EXECUTION_FIELD, f"node {node.task_id} is missing execution field {f!r}", blocking=True, task_id=node.task_id))
    return out


def _check_producers(nodes: list[DagNode], expectations: dict[str, ArtifactExpectation]) -> list[dict[str, Any]]:
    """Every consumed artifact must have a declared producer or be an external input."""
    produced = {aid for n in nodes for aid in n.output_artifact_ids}
    external_inputs = {aid for n in nodes for aid in n.input_artifact_ids if aid not in produced}
    out: list[dict[str, Any]] = []
    for node in nodes:
        for aid in node.input_artifact_ids:
            if aid not in produced and aid not in external_inputs:
                out.append(_diag(DIAG_MISSING_PRODUCER, f"node {node.task_id} consumes artifact {aid!r} with no producer", blocking=True, task_id=node.task_id))
    # Orphan node: produces nothing and is consumed by nothing (except terminal review).
    consumed = {aid for n in nodes for aid in n.input_artifact_ids}
    for node in nodes:
        if node.node_type == NODE_REVIEW:
            continue
        if node.output_artifact_ids and not any(aid in consumed for aid in node.output_artifact_ids):
            out.append(
                _diag(DIAG_ORPHAN_NODE, f"node {node.task_id} produces artifacts nothing consumes and is not terminal", blocking=False, task_id=node.task_id)
            )
    return out


def _check_claim_propagation(nodes: list[DagNode], expectations: dict[str, ArtifactExpectation]) -> list[dict[str, Any]]:
    """Downstream nodes may not raise the allowed claim level of their inputs."""
    producer_level: dict[str, str] = {}
    for node in nodes:
        for aid in node.output_artifact_ids:
            producer_level[aid] = node.allowed_claim_level
    out: list[dict[str, Any]] = []
    for node in nodes:
        # A node's own level must not exceed the min of its upstream producers.
        upstream_levels = [producer_level[aid] for aid in node.input_artifact_ids if aid in producer_level]
        if upstream_levels:
            ceiling = upstream_levels[0]
            for lvl in upstream_levels[1:]:
                ceiling = _min_claim(ceiling, lvl)
            if (
                node.allowed_claim_level in CLAIM_LEVELS
                and ceiling in CLAIM_LEVELS
                and CLAIM_LEVELS.index(node.allowed_claim_level) > CLAIM_LEVELS.index(ceiling)
            ):
                out.append(
                    _diag(
                        DIAG_CLAIM_LEVEL_VIOLATION,
                        f"node {node.task_id} claim level {node.allowed_claim_level!r} exceeds upstream ceiling {ceiling!r}",
                        blocking=True,
                        task_id=node.task_id,
                    )
                )
    return out


def _check_coverage(required: set[str], covered: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sq in sorted(required - covered):
        out.append(_diag(DIAG_UNCOVERED_SUBQUESTION, f"required sub-question {sq!r} has no terminal evidence path", blocking=True, subquestion_id=sq))
    return out


def _build_task_packets(nodes: list[DagNode], registry: MethodRegistry) -> list[dict[str, Any]]:
    from ..core.schemas import (
        AnalysisTaskPacket,
        DataPreparationTaskPacket,
        ReviewTaskPacket,
    )

    packets: list[dict[str, Any]] = []
    for node in nodes:
        if node.node_type == NODE_DATA_PREPARATION:
            packet = DataPreparationTaskPacket(
                task_id=node.task_id,
                subquestion_id=node.subquestion_id,
                planned_inputs=list(node.input_artifact_ids) or ["external_manifest_input"],
                expected_outputs=list(node.output_artifact_ids),
                preparation_steps=["download", "decompress", "format_convert", "id_map"],
                created_at="",
            ).to_dict()
            packet["execution_fields"] = node.execution_fields
        elif node.node_type == NODE_ANALYSIS:
            contract = registry.active_contract(node.method_id) or {}
            packet = asdict(
                AnalysisTaskPacket(
                    task_id=node.task_id,
                    subquestion_id=node.subquestion_id,
                    expected_inputs=list(node.input_artifact_ids),
                    expected_outputs=list(node.output_artifact_ids),
                    qc_requirements=[q for q in contract.get("required_qc", []) if isinstance(q, str)] or ["execution"],
                    failure_conditions=[c for c in contract.get("forbidden_conditions", []) if isinstance(c, str)] or ["precondition_failed"],
                    created_at="",
                )
            )
            packet["packet_type"] = "AnalysisTaskPacket"
            packet["method_id"] = node.method_id
            packet["params"] = node.params
            packet["allowed_claim_level"] = node.allowed_claim_level
            packet["execution_fields"] = node.execution_fields
        else:  # NODE_REVIEW
            packet = asdict(
                ReviewTaskPacket(
                    task_id=node.task_id,
                    audit_scope=list(node.input_artifact_ids),
                    claim_ceiling=node.allowed_claim_level,
                    required_checks=["claim_ceiling_not_loosened", "outputs_match_expectation", "analysis_not_self_reviewed"],
                    created_at="",
                )
            )
            packet["packet_type"] = "ReviewTaskPacket"
            packet["subquestion_id"] = node.subquestion_id
            packet["execution_fields"] = node.execution_fields
        packets.append(packet)
    return packets


def _machine_json(nodes: list[DagNode], dependencies: list[list[str]], expectations: dict[str, ArtifactExpectation]) -> dict[str, Any]:
    return {
        "nodes": [n.to_dict() for n in nodes],
        "edges": sorted([list(e) for e in dependencies]),
        "artifacts": [expectations[k].to_dict() for k in sorted(expectations)],
        "node_count": len(nodes),
        "edge_count": len(dependencies),
    }


def _render_markdown(nodes: list[DagNode], dependencies: list[list[str]], workflow_name: str) -> str:
    lines = [f"# Workflow DAG: {workflow_name}", "", f"Nodes: {len(nodes)} | Edges: {len(dependencies)}", "", "## Nodes"]
    for node in nodes:
        lines.append(f"- `{node.task_id}` [{node.node_type}] sq={node.subquestion_id} claim<={node.allowed_claim_level}")
    lines.append("")
    lines.append("## Edges (from depends on to)")
    for edge in sorted([list(e) for e in dependencies]):
        lines.append(f"- `{edge[0]}` -> `{edge[1]}`")
    return "\n".join(lines) + "\n"


def affected_subgraph(workflow_plan: dict[str, Any], changed_task_ids: list[str]) -> list[str]:
    """Deterministically compute the tasks affected by a change (T-12-11).

    Returns every descendant (dependent) of any changed task, plus the changed
    tasks themselves — i.e. the tasks whose outputs may need recomputing — sorted.
    A dependency edge ``[from, to]`` means ``from`` depends on ``to``, so ``to``
    changing invalidates ``from``.
    """
    dependents: dict[str, list[str]] = {}
    for edge in workflow_plan.get("dependencies", []):
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            dependents.setdefault(edge[1], []).append(edge[0])
    affected: set[str] = set()
    stack = list(changed_task_ids)
    while stack:
        current = stack.pop()
        if current in affected:
            continue
        affected.add(current)
        stack.extend(dependents.get(current, []))
    return sorted(affected)


__all__ = [
    "COMPILE_OK",
    "COMPILE_REPLAN",
    "COMPILE_DRAFT_INCOMPLETE",
    "COMPILE_STATUSES",
    "DIAG_CODES",
    "NODE_DATA_PREPARATION",
    "NODE_ANALYSIS",
    "NODE_REVIEW",
    "REQUIRED_EXECUTION_FIELDS",
    "COMPILER_VERSION",
    "ExecutionDefaults",
    "ArtifactExpectation",
    "DagNode",
    "CompiledWorkflow",
    "compile_workflow",
    "affected_subgraph",
]
