"""The inert ``RouteRun`` result object produced by every route.

A :class:`RouteRun` is a deterministic, offline snapshot of one end-to-end run:
the ordered per-stage outcomes, the produced (inert) scientific objects, and the
terminal status.  It is *data*, never an authorization — it carries no live
handle, mutates nothing, and (like every lane draft) sets no wall-clock field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# -- terminal statuses -------------------------------------------------------
# A route ends in exactly one of these.  COMPLETED is the only "closed loop"
# success; every other status is a *legal, recorded stop* at a hard gate (the
# constitution's "conservative failure" — never a fabricated result).
TERMINAL_COMPLETED = "COMPLETED"
TERMINAL_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
TERMINAL_UNVERIFIABLE_RESOURCE = "UNVERIFIABLE_RESOURCE"
TERMINAL_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
TERMINAL_METHOD_NOT_APPLICABLE = "METHOD_NOT_APPLICABLE"
TERMINAL_EGRESS_BLOCKED = "EGRESS_BLOCKED"
TERMINAL_QC_REJECTED = "QC_REJECTED"
TERMINAL_EVIDENCE_REFUSED = "EVIDENCE_REFUSED"
TERMINAL_CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
TERMINAL_ALIGNMENT_REVIEW = "ALIGNMENT_REVIEW_REQUIRED"

TERMINAL_STATUSES = (
    TERMINAL_COMPLETED,
    TERMINAL_NEEDS_CLARIFICATION,
    TERMINAL_UNVERIFIABLE_RESOURCE,
    TERMINAL_INSUFFICIENT_DATA,
    TERMINAL_METHOD_NOT_APPLICABLE,
    TERMINAL_EGRESS_BLOCKED,
    TERMINAL_QC_REJECTED,
    TERMINAL_EVIDENCE_REFUSED,
    TERMINAL_CONFLICTING_EVIDENCE,
    TERMINAL_ALIGNMENT_REVIEW,
)

# Stage-level outcome vocabulary.
STAGE_OK = "ok"
STAGE_STOPPED = "stopped"


@dataclass
class StageResult:
    """One stage's inert outcome within a route."""

    name: str
    status: str  # STAGE_OK | STAGE_STOPPED
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == STAGE_OK

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "reason": self.reason, "payload": self.payload}


@dataclass
class RouteRun:
    """A deterministic, offline record of one end-to-end route execution."""

    route: str
    project_id: str
    question: str
    terminal_status: str = ""
    reason: str = ""
    stages: list[StageResult] = field(default_factory=list)
    # Inert produced objects (empty until the relevant stage runs).
    research_spec: dict[str, Any] = field(default_factory=dict)
    scope_bundle: dict[str, Any] = field(default_factory=dict)
    subquestions: list[dict[str, Any]] = field(default_factory=list)
    evidence_plans: list[dict[str, Any]] = field(default_factory=list)
    dataset_manifest: dict[str, Any] = field(default_factory=dict)
    workflow_plan: dict[str, Any] = field(default_factory=dict)
    authorization: dict[str, Any] = field(default_factory=dict)
    task_runs: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    qc_reports: list[dict[str, Any]] = field(default_factory=list)
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    non_admissible: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    alignment: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)
    reproduction: dict[str, Any] = field(default_factory=dict)
    concordance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""  # determinism: never a wall-clock read

    # -- helpers -------------------------------------------------------------

    def add_stage(self, name: str, status: str, *, reason: str = "", payload: dict[str, Any] | None = None) -> StageResult:
        result = StageResult(name=name, status=status, reason=reason, payload=payload or {})
        self.stages.append(result)
        return result

    def stop(self, terminal_status: str, reason: str) -> RouteRun:
        self.terminal_status = terminal_status
        self.reason = reason
        return self

    def complete(self) -> RouteRun:
        self.terminal_status = TERMINAL_COMPLETED
        self.reason = "closed loop completed end-to-end over the recorded offline fixture"
        return self

    def stage(self, name: str) -> StageResult | None:
        for s in self.stages:
            if s.name == name:
                return s
        return None

    @property
    def completed(self) -> bool:
        return self.terminal_status == TERMINAL_COMPLETED

    @property
    def stage_names(self) -> list[str]:
        return [s.name for s in self.stages]

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "project_id": self.project_id,
            "question": self.question,
            "terminal_status": self.terminal_status,
            "reason": self.reason,
            "stages": [s.to_dict() for s in self.stages],
            "subquestions": self.subquestions,
            "dataset_manifest": self.dataset_manifest,
            "workflow_plan": self.workflow_plan,
            "authorization": self.authorization,
            "task_runs": self.task_runs,
            "artifacts": self.artifacts,
            "qc_reports": self.qc_reports,
            "evidence_items": self.evidence_items,
            "non_admissible": self.non_admissible,
            "claims": self.claims,
            "alignment": self.alignment,
            "report": self.report,
            "reproduction": self.reproduction,
            "concordance": self.concordance,
            "created_at": self.created_at,
        }
