"""Canonical project state machine.

The project state is a *projection* rebuilt from the append-only event log; it is
never the authoritative source on its own (see ``store.py``).  Stages may only
advance along the edges declared in ``LINEAR_NEXT``.  Every non-success outcome
(insufficient data, method not applicable, conflicting evidence, ...) is a first
class terminal stage rather than an ad-hoc exception, so the closed loop can
"stop safely" instead of fabricating a result.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .ids import make_stable_id
from .schemas import CANONICAL_SCHEMA_VERSION, ProjectState, now_iso


# --- Main happy-path stages, in order ---------------------------------------
MAIN_SEQUENCE = [
    "INTAKE",
    "QUESTION_RESOLVED",
    "SCOPE_RESOLVED",
    "EVIDENCE_PLANNED",
    "RESOURCES_DISCOVERED",
    "DATASETS_LOCKED",
    "WORKFLOW_COMPILED",
    "TASKS_READY",
    "TASKS_RUNNING",
    "QC_COMPLETED",
    "EVIDENCE_SYNTHESIZED",
    "ALIGNMENT_AUDITED",
    "REPORT_READY",
    "REPRODUCTION_BUNDLE_READY",
    "COMPLETED",
]

# --- Side / terminal stages -------------------------------------------------
# HUMAN_REVIEW_REQUIRED is a recoverable pause; the rest are legal end states.
SIDE_STAGES = ["HUMAN_REVIEW_REQUIRED"]

LEGAL_TERMINALS = [
    "COMPLETED",
    "INSUFFICIENT_DATA",
    "METHOD_NOT_APPLICABLE",
    "INCONCLUSIVE",
    "CONFLICTING_EVIDENCE",
    "FAILED",
    "CANCELLED",
]

STAGES = MAIN_SEQUENCE + SIDE_STAGES + [s for s in LEGAL_TERMINALS if s not in MAIN_SEQUENCE]

# Stages the loop cannot silently leave; only an explicit resume may.  COMPLETED
# is a clean terminal that is never resumed.
TERMINAL_STAGES = {
    "COMPLETED",
    "INSUFFICIENT_DATA",
    "METHOD_NOT_APPLICABLE",
    "INCONCLUSIVE",
    "CONFLICTING_EVIDENCE",
    "FAILED",
    "CANCELLED",
}

# Conservative-failure terminals reachable from every working stage.  Reaching
# one of these is how the system "stops instead of guessing".
_SAFE_STOPS = ["INSUFFICIENT_DATA", "METHOD_NOT_APPLICABLE", "INCONCLUSIVE", "CONFLICTING_EVIDENCE", "FAILED", "CANCELLED"]


def _dedup(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen.keys())


def _linear_map() -> dict[str, list[str]]:
    edges: dict[str, list[str]] = {}
    for index, stage in enumerate(MAIN_SEQUENCE):
        nxt: list[str] = []
        if index + 1 < len(MAIN_SEQUENCE):
            nxt.append(MAIN_SEQUENCE[index + 1])
        if stage != "COMPLETED":
            nxt.append("HUMAN_REVIEW_REQUIRED")
            nxt.extend(_SAFE_STOPS)
        edges[stage] = _dedup(nxt)
    edges["HUMAN_REVIEW_REQUIRED"] = _dedup([s for s in MAIN_SEQUENCE if s != "INTAKE"] + _SAFE_STOPS)
    for terminal in TERMINAL_STAGES:
        edges.setdefault(terminal, [])
    return edges


LINEAR_NEXT = _linear_map()


def allowed_next_stages(stage: str) -> list[str]:
    return list(LINEAR_NEXT.get(stage, []))


def build_initial_state(project_id: str, user_question: str) -> dict[str, Any]:
    state = ProjectState(project_id=project_id, current_stage="INTAKE", allowed_next_stages=allowed_next_stages("INTAKE"))
    data = asdict(state)
    data["project_state_id"] = make_stable_id("project_state", {"project_id": project_id})
    data["schema_version"] = CANONICAL_SCHEMA_VERSION
    data["updated_at"] = now_iso()
    data["user_question"] = user_question
    data["stage_history"] = ["INTAKE"]
    return data


def with_stage(state: dict[str, Any], next_stage: str) -> dict[str, Any]:
    updated = dict(state)
    updated["current_stage"] = next_stage
    updated["allowed_next_stages"] = allowed_next_stages(next_stage)
    updated["updated_at"] = now_iso()
    history = list(updated.get("stage_history") or [])
    history.append(next_stage)
    updated["stage_history"] = history
    return updated
