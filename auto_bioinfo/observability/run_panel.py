"""Deterministic run-panel projections over the event log (WP-24 / T-24-05..T-24-08).

The requirement spec's observability exit criterion is that, for any project, an
operator can state — without parsing raw logs — *"which stage it is at, why it is
waiting or has failed, what ran, and which results are still awaiting review."*

This module answers that as a family of **pure, read-only projections** over an
in-memory list of event dicts (the shape
:func:`auto_bioinfo.core.events.build_event` produces).  It reads the same
append-only log the canonical state machine does, and derives:

- :func:`project_status` — the current stage, whether it is terminal / a
  recoverable pause, the *waiting reason*, the derived *next action*, the stage
  history, and the last event (T-24-06);
- :func:`task_attempts` — per-task attempt records reconstructed from task events,
  so each attempt (its outcome and, where recorded, its retry reason) is
  distinguishable (T-24-05, T-24-07);
- :func:`review_queue` — the QC / evidence / claim items still awaiting a human
  review decision, derived from approval-request / decision events (T-24-08).

It performs no I/O, no clock read, and no mutation.  It invents no business facts:
every derived field maps to an explicit event or the bounded stage vocabulary in
:mod:`auto_bioinfo.core.state`.  It is deliberately independent of the on-disk
store (it takes events directly) so it stays pure and testable offline.

Design constraints mirror the WP-04b query layer: deterministic, fail-closed on a
corrupt log, bounded status vocabulary, stable projection ordering.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..core.state import MAIN_SEQUENCE, TERMINAL_STAGES

# The single recoverable pause stage (mirrors control_plane.queries).
HUMAN_REVIEW_STAGE = "HUMAN_REVIEW_REQUIRED"
# Safe-stop terminals: every terminal except the clean success.
SAFE_STOP_STAGES = frozenset(TERMINAL_STAGES) - {"COMPLETED"}

# The next-action hint for each working stage — a bounded, static map keyed on the
# canonical stage vocabulary (never free-form business logic).  A terminal stage
# has no next action; a paused stage's action is "a human must act".
_NEXT_ACTION: dict[str, str] = {
    "INTAKE": "resolve the research question",
    "QUESTION_RESOLVED": "resolve the study scope",
    "SCOPE_RESOLVED": "plan the evidence",
    "EVIDENCE_PLANNED": "discover candidate resources",
    "RESOURCES_DISCOVERED": "verify and lock datasets",
    "DATASETS_LOCKED": "compile the workflow",
    "WORKFLOW_COMPILED": "prepare tasks for execution",
    "TASKS_READY": "run the tasks",
    "TASKS_RUNNING": "await task completion / QC",
    "QC_COMPLETED": "synthesize evidence",
    "EVIDENCE_SYNTHESIZED": "audit alignment",
    "ALIGNMENT_AUDITED": "assemble the report",
    "REPORT_READY": "build the reproduction bundle",
    "REPRODUCTION_BUNDLE_READY": "close out the project",
}

# --- Bounded run-status vocabulary (the panel's headline state) --------------
RUN_ACTIVE = "active"
RUN_PAUSED = "paused"  # HUMAN_REVIEW_REQUIRED
RUN_COMPLETED = "completed"
RUN_STOPPED = "stopped"  # a safe-stop terminal (not COMPLETED)
RUN_EMPTY = "empty"  # no events

RUN_STATUSES = (RUN_ACTIVE, RUN_PAUSED, RUN_COMPLETED, RUN_STOPPED, RUN_EMPTY)

# Object types that carry a review decision, for the review-queue projection.
_REVIEWABLE_OBJECT_TYPES = ("QCReport", "EvidenceItem", "Claim", "ApprovalRequest")


class RunPanelError(RuntimeError):
    """A run-panel projection could not be built (corrupt / non-list input)."""


def _require_events(events: Any) -> list[Mapping[str, Any]]:
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise RunPanelError("events must be a sequence of event mappings")
    result: list[Mapping[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            raise RunPanelError("every event must be a mapping")
        result.append(event)
    return result


@dataclass(frozen=True)
class ProjectStatus:
    """The at-a-glance current status of a project, derived from its log."""

    project_id: str
    run_status: str
    current_stage: str
    is_terminal: bool
    is_paused: bool
    waiting_reason: str
    next_action: str
    event_count: int
    stage_history: tuple[str, ...]
    last_event_id: str
    last_event_type: str
    last_created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "run_status": self.run_status,
            "current_stage": self.current_stage,
            "is_terminal": self.is_terminal,
            "is_paused": self.is_paused,
            "waiting_reason": self.waiting_reason,
            "next_action": self.next_action,
            "event_count": self.event_count,
            "stage_history": list(self.stage_history),
            "last_event_id": self.last_event_id,
            "last_event_type": self.last_event_type,
            "last_created_at": self.last_created_at,
        }


def project_status(events: Any) -> ProjectStatus:
    """Project a bounded :class:`ProjectStatus` from an in-memory event list (T-24-06).

    ``current_stage`` is the last event's ``next_stage`` (the log's authoritative
    current stage); ``stage_history`` is the ordered stages entered.  The waiting
    reason and next action are derived from the bounded stage vocabulary: a
    terminal stage waits on nothing (its reason names the terminal), a
    ``HUMAN_REVIEW_REQUIRED`` pause waits on a human, and a working stage's next
    action is its static hint.  An empty log yields ``run_status == "empty"``.
    """
    evs = _require_events(events)
    if not evs:
        return ProjectStatus(
            project_id="",
            run_status=RUN_EMPTY,
            current_stage="",
            is_terminal=False,
            is_paused=False,
            waiting_reason="no events recorded for this project",
            next_action="initialize the project",
            event_count=0,
            stage_history=(),
            last_event_id="",
            last_event_type="",
            last_created_at="",
        )

    last = evs[-1]
    current_stage = str(last.get("next_stage", ""))
    project_id = str(evs[0].get("project_id", ""))
    stage_history = tuple(str(e.get("next_stage", "")) for e in evs if e.get("next_stage"))

    is_terminal = current_stage in TERMINAL_STAGES
    is_paused = current_stage == HUMAN_REVIEW_STAGE

    if current_stage == "COMPLETED":
        run_status = RUN_COMPLETED
        waiting_reason = "project completed cleanly; nothing is pending"
        next_action = ""
    elif current_stage in SAFE_STOP_STAGES:
        run_status = RUN_STOPPED
        waiting_reason = f"project stopped at safe-stop terminal {current_stage!r} without a clean completion"
        next_action = ""
    elif is_paused:
        run_status = RUN_PAUSED
        waiting_reason = "project is paused awaiting a human review decision"
        next_action = "a human reviewer must act to resume"
    else:
        run_status = RUN_ACTIVE
        waiting_reason = f"project is progressing through {current_stage!r}"
        next_action = _NEXT_ACTION.get(current_stage, "advance the pipeline")

    return ProjectStatus(
        project_id=project_id,
        run_status=run_status,
        current_stage=current_stage,
        is_terminal=is_terminal,
        is_paused=is_paused,
        waiting_reason=waiting_reason,
        next_action=next_action,
        event_count=len(evs),
        stage_history=stage_history,
        last_event_id=str(last.get("event_id", "")),
        last_event_type=str(last.get("event_type", "")),
        last_created_at=str(last.get("created_at", "")),
    )


@dataclass(frozen=True)
class TaskAttempt:
    """One reconstructed attempt of a task, distinguishable from its other tries.

    ``attempt`` is the attempt ordinal read from the event payload (defaulting to a
    1-based counter over the task's events when the payload does not record one).
    ``outcome`` is the event type of the attempt's terminal event; ``retry_reason``
    is the recorded reason a retry followed (empty when none).
    """

    task_id: str
    attempt: int
    event_id: str
    event_type: str
    outcome: str
    created_at: str
    retry_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "attempt": self.attempt,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "outcome": self.outcome,
            "created_at": self.created_at,
            "retry_reason": self.retry_reason,
        }


def _task_id_of(event: Mapping[str, Any]) -> str | None:
    """The task/run id an event concerns, from an object_ref or payload, else None."""
    for ref in event.get("object_refs") or []:
        if isinstance(ref, Mapping) and ref.get("object_type") in ("TaskRun", "TaskPacket", "Task"):
            return str(ref.get("object_id", "")) or None
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        for key in ("task_id", "task_run_id", "run_id"):
            if payload.get(key):
                return str(payload[key])
    return None


def task_attempts(events: Any, *, task_id: str | None = None) -> tuple[TaskAttempt, ...]:
    """Reconstruct per-task attempt records so each try is distinguishable (T-24-05/07).

    Scans the log for events that concern a task (via a ``TaskRun``/``TaskPacket``
    object ref or a ``task_id`` payload key) and emits one :class:`TaskAttempt` per
    such event, in log order.  ``attempt`` comes from the payload's ``attempt``
    when present, else a 1-based per-task counter.  Optionally restrict to one
    ``task_id``.  Read-only and deterministic.
    """
    evs = _require_events(events)
    counters: dict[str, int] = {}
    attempts: list[TaskAttempt] = []
    for event in evs:
        tid = _task_id_of(event)
        if tid is None:
            continue
        if task_id is not None and tid != task_id:
            continue
        counters[tid] = counters.get(tid, 0) + 1
        raw_payload = event.get("payload")
        payload: Mapping[str, Any] = raw_payload if isinstance(raw_payload, Mapping) else {}
        recorded_attempt = payload.get("attempt")
        attempt = recorded_attempt if isinstance(recorded_attempt, int) and not isinstance(recorded_attempt, bool) and recorded_attempt >= 1 else counters[tid]
        attempts.append(
            TaskAttempt(
                task_id=tid,
                attempt=attempt,
                event_id=str(event.get("event_id", "")),
                event_type=str(event.get("event_type", "")),
                outcome=str(event.get("event_type", "")),
                created_at=str(event.get("created_at", "")),
                retry_reason=str(payload.get("retry_reason", "")),
            )
        )
    return tuple(attempts)


@dataclass(frozen=True)
class ReviewItem:
    """One object still awaiting a human review decision, projected from the log."""

    object_type: str
    object_id: str
    requested_event_id: str
    requested_at: str
    project_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "object_id": self.object_id,
            "requested_event_id": self.requested_event_id,
            "requested_at": self.requested_at,
            "project_id": self.project_id,
        }


# Event-type substrings that open (request) vs. close (decide) a review.
_REVIEW_REQUEST_MARKERS = ("APPROVAL_REQUESTED", "REVIEW_REQUESTED", "HUMAN_REVIEW_REQUIRED", "QC_REVIEW_REQUESTED")
_REVIEW_DECISION_MARKERS = ("APPROVAL_GRANTED", "APPROVAL_REJECTED", "REVIEW_DECIDED", "APPROVED", "REJECTED")


def _refs_of(event: Mapping[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for ref in event.get("object_refs") or []:
        if isinstance(ref, Mapping) and ref.get("object_id"):
            result.append((str(ref.get("object_type", "")), str(ref.get("object_id", ""))))
    return result


def review_queue(events: Any) -> tuple[ReviewItem, ...]:
    """Project the objects still awaiting a review decision (T-24-08).

    An object referenced by a review-request event (its type carries a
    :data:`_REVIEW_REQUEST_MARKERS` marker) is *pending* until a later
    review-decision event (a :data:`_REVIEW_DECISION_MARKERS` marker) references
    the same object id.  The returned queue is the still-pending items in
    request-log order.  Deterministic and read-only.
    """
    evs = _require_events(events)
    pending: dict[str, ReviewItem] = {}
    order: list[str] = []
    for event in evs:
        etype = str(event.get("event_type", ""))
        is_request = any(marker in etype for marker in _REVIEW_REQUEST_MARKERS)
        is_decision = any(marker in etype for marker in _REVIEW_DECISION_MARKERS)
        if is_request:
            for object_type, object_id in _refs_of(event):
                if object_id not in pending:
                    order.append(object_id)
                pending[object_id] = ReviewItem(
                    object_type=object_type,
                    object_id=object_id,
                    requested_event_id=str(event.get("event_id", "")),
                    requested_at=str(event.get("created_at", "")),
                    project_id=str(event.get("project_id", "")),
                )
        elif is_decision:
            for _object_type, object_id in _refs_of(event):
                pending.pop(object_id, None)
    return tuple(pending[oid] for oid in order if oid in pending)


def run_panel(events: Any) -> dict[str, Any]:
    """Assemble the full deterministic run panel: status + attempts + review queue.

    A single read-only roll-up combining :func:`project_status`,
    :func:`task_attempts`, and :func:`review_queue` for one project's event list.
    """
    status = project_status(events)
    return {
        "status": status.to_dict(),
        "task_attempts": [a.to_dict() for a in task_attempts(events)],
        "review_queue": [r.to_dict() for r in review_queue(events)],
        "main_sequence": list(MAIN_SEQUENCE),
    }


__all__ = [
    "HUMAN_REVIEW_STAGE",
    "SAFE_STOP_STAGES",
    "RUN_ACTIVE",
    "RUN_PAUSED",
    "RUN_COMPLETED",
    "RUN_STOPPED",
    "RUN_EMPTY",
    "RUN_STATUSES",
    "RunPanelError",
    "ProjectStatus",
    "project_status",
    "TaskAttempt",
    "task_attempts",
    "ReviewItem",
    "review_queue",
    "run_panel",
]
