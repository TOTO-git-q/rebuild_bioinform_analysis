from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import build_event
from .state import STAGES, TERMINAL_STAGES, allowed_next_stages, build_initial_state, with_stage

# The event log is only trustworthy if its first record is the canonical project
# initialization event; replay is anchored to this type so a forged/corrupt log
# cannot seed an arbitrary projection.
PROJECT_INITIALIZED_EVENT = "PROJECT_STATE_INITIALIZED"
LEGACY_MIGRATION_EVENT = "LEGACY_PROJECT_MIGRATED"

# Sentinel marking a field present on only one side of a projection comparison
# (see ``verify_projection``); distinct from a real ``None`` value.
_ABSENT = object()


def _v5_dir(project_dir: str | Path) -> Path:
    path = Path(project_dir) / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(project_dir: str | Path) -> Path:
    return _v5_dir(project_dir) / "project_state.json"


def _events_path(project_dir: str | Path) -> Path:
    return _v5_dir(project_dir) / "events.jsonl"


def init_project_state(project_dir: str | Path, user_question: str, *, execution_mode: str = "DEMO", project_policy_ref: str = "") -> dict[str, Any]:
    project_id = Path(project_dir).name
    state = build_initial_state(project_id=project_id, user_question=user_question, execution_mode=execution_mode, project_policy_ref=project_policy_ref)
    _write_state(project_dir, state)
    event = build_event(
        project_id=project_id,
        event_type="PROJECT_STATE_INITIALIZED",
        actor="system",
        previous_stage="",
        next_stage="INTAKE",
        object_refs=[{"object_type": "ProjectState", "object_id": state["project_state_id"]}],
        message="Initialized canonical v5 project state.",
        payload={"user_question": user_question, "execution_mode": execution_mode, "project_policy_ref": project_policy_ref},
    )
    append_event(project_dir, event)
    return state


def record_legacy_migration(project_dir: str | Path, policy: dict[str, Any]) -> dict[str, Any]:
    """One-time conservative migration of a pre-R0-01 project (Gate 6).

    Binds the freshly built DEMO ``policy`` to the existing ProjectState: forces
    ``execution_mode=DEMO`` (a legacy project can never be trusted as REAL),
    points ``project_policy_ref`` at the new policy, and stamps the audit marker
    ``migrated_from_legacy`` (mirrors ``provenance.LEGACY_MIGRATION_MARKER``).
    The migration is recorded as an explicit event so it is never silent.
    """
    state = load_project_state(project_dir)
    state["execution_mode"] = "DEMO"
    state["project_policy_ref"] = policy["project_policy_id"]
    state["migrated_from_legacy"] = True
    _write_state(project_dir, state)
    event = build_event(
        project_id=state["project_id"],
        event_type="LEGACY_PROJECT_MIGRATED",
        actor="system",
        previous_stage=state["current_stage"],
        next_stage=state["current_stage"],
        object_refs=[{"object_type": "ProjectPolicy", "object_id": policy["project_policy_id"]}],
        message="Migrated legacy (pre-R0-01) project to a conservative DEMO ProjectPolicy.",
        payload={"execution_mode": "DEMO", "project_policy_ref": policy["project_policy_id"]},
    )
    append_event(project_dir, event)
    return state


def append_event(project_dir: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    required = ["event_id", "project_id", "event_type", "actor", "created_at", "previous_stage", "next_stage", "object_refs", "message", "payload_hash"]
    missing = [field for field in required if field not in event]
    if missing:
        raise ValueError(f"event missing required fields: {', '.join(missing)}")
    # Idempotent append on an explicit ``idempotency_key`` (mirrors the
    # stable-id dedup in ``execution/runs.py``): a duplicate-key re-append adds
    # no second log line and deterministically returns the already-recorded
    # event. Keyless events keep the historical append-always behavior, so the
    # existing init/transition write paths are unchanged.
    #
    # The key must dedupe *true retries only* — it can never mask an
    # inconsistent or corrupt event. So a same-key match is honored only when
    # the existing record is itself well-formed AND the incoming event is
    # logically identical to it; otherwise we fail closed with ``ValueError``
    # rather than silently returning a stale/forged record.
    key = event.get("idempotency_key")
    if key is not None:
        # Identity fields that define "the same logical event"; a same-key
        # event differing on any of these is a conflict, not a retry.
        # ``created_at`` / ``event_id`` are excluded by design — they move with
        # the wall clock, which is exactly why an explicit key exists.
        identity = ["project_id", "event_type", "actor", "previous_stage", "next_stage", "object_refs", "message", "payload_hash", "payload"]
        for existing in load_events(project_dir):
            if existing.get("idempotency_key") != key:
                continue
            existing_missing = [field for field in required if field not in existing]
            if existing_missing:
                raise ValueError(f"idempotency_key {key!r} maps to a malformed existing event missing required fields: {', '.join(existing_missing)}")
            conflicts = [field for field in identity if existing.get(field) != event.get(field)]
            if conflicts:
                raise ValueError(f"idempotency_key {key!r} conflict: incoming event differs from the recorded event on: {', '.join(conflicts)}")
            return existing  # idempotent: identical retry already recorded
    path = _events_path(project_dir)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def transition_state(
    project_dir: str | Path,
    next_stage: str,
    event_type: str,
    actor: str,
    object_refs: list[dict[str, Any]] | None,
    message: str,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    state = load_project_state(project_dir)
    previous_stage = state["current_stage"]
    validate_transition(previous_stage, next_stage, resume=resume)
    if previous_stage == "TASKS_RUNNING" and next_stage == "EVIDENCE_SYNTHESIZED":
        events = load_events(project_dir)
        if not any(event.get("next_stage") == "QC_COMPLETED" or event.get("event_type") == "QC_COMPLETED" for event in events):
            raise ValueError("TASKS_RUNNING cannot transition to EVIDENCE_SYNTHESIZED before QC_COMPLETED event")
    updated = with_stage(state, next_stage)
    _write_state(project_dir, updated)
    event = build_event(
        project_id=updated["project_id"],
        event_type=event_type,
        actor=actor,
        previous_stage=previous_stage,
        next_stage=next_stage,
        object_refs=object_refs or [],
        message=message,
        payload={"project_state_id": updated["project_state_id"]},
    )
    append_event(project_dir, event)
    return updated


def load_project_state(project_dir: str | Path) -> dict[str, Any]:
    path = _state_path(project_dir)
    if not path.exists():
        raise FileNotFoundError(f"project_state.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def rebuild_state(project_dir: str | Path) -> dict[str, Any]:
    """Reconstruct the canonical project state purely from the event log.

    ``state/events.jsonl`` is the authoritative, append-only record; the
    ``project_state.json`` snapshot is only a cache of this projection (ADR-0003).
    Replaying the log here means the state can never be silently rewritten by
    editing the snapshot: ``current_stage`` / ``stage_history`` are derived from
    the stage of each event, and the policy fields are re-applied from the
    ``PROJECT_STATE_INITIALIZED`` / ``LEGACY_PROJECT_MIGRATED`` events.

    ``updated_at`` is pinned to the last event's ``created_at`` so the projection
    is deterministic — the same log always rebuilds to the same value (except
    ``updated_at``, which the live snapshot stamps with its own wall clock).
    """
    events = load_events(project_dir)
    if not events:
        raise ValueError(f"cannot rebuild state: empty event log in {_events_path(project_dir)}")

    # --- Fail closed on a corrupt/forged log -------------------------------
    # The first event must be a well-formed initialization event so the
    # projection can never be seeded from an arbitrary record. Every later
    # event is validated through the same transition guard used on write, so a
    # structurally complete but semantically illegal event (wrong project,
    # unknown stage, illegal edge) is rejected instead of silently applied.
    init_event = events[0]
    if init_event.get("event_type") != PROJECT_INITIALIZED_EVENT:
        raise ValueError(f"corrupt event log: first event must be {PROJECT_INITIALIZED_EVENT}, got {init_event.get('event_type')!r}")
    if init_event.get("previous_stage") != "":
        raise ValueError("corrupt event log: initialization event must have empty previous_stage")
    if init_event.get("next_stage") != "INTAKE":
        raise ValueError("corrupt event log: initialization event must enter INTAKE")
    project_id = init_event.get("project_id")
    if not project_id:
        raise ValueError("corrupt event log: initialization event missing project_id")

    init_payload = init_event.get("payload") or {}
    rebuilt = build_initial_state(
        project_id=project_id,
        user_question=init_payload.get("user_question", ""),
        execution_mode=init_payload.get("execution_mode", "DEMO"),
        project_policy_ref=init_payload.get("project_policy_ref", ""),
    )
    for event in events[1:]:
        payload = event.get("payload") or {}
        if event.get("project_id") != project_id:
            raise ValueError(f"corrupt event log: event project_id {event.get('project_id')!r} does not match {project_id!r}")
        previous_stage = event.get("previous_stage")
        if previous_stage != rebuilt["current_stage"]:
            raise ValueError(f"corrupt event log: event previous_stage {previous_stage!r} does not match current stage {rebuilt['current_stage']!r}")
        next_stage = event.get("next_stage")
        if next_stage not in STAGES:
            raise ValueError(f"corrupt event log: unknown next_stage {next_stage!r}")

        if event.get("event_type") == LEGACY_MIGRATION_EVENT:
            # A conservative in-place migration never advances the stage.
            if next_stage != previous_stage:
                raise ValueError("corrupt event log: legacy migration must not change stage")
            rebuilt["execution_mode"] = payload.get("execution_mode", rebuilt["execution_mode"])
            rebuilt["project_policy_ref"] = payload.get("project_policy_ref", rebuilt["project_policy_ref"])
            rebuilt["migrated_from_legacy"] = True
            continue

        # Reuse the single transition guard instead of a parallel machine, and
        # run it for every non-legacy event — including a forged same-stage
        # no-op the legal write path could never produce (validate_transition
        # rejects self-loops). Only LEGACY_PROJECT_MIGRATED may be a no-op.
        validate_transition(previous_stage, next_stage)
        rebuilt = with_stage(rebuilt, next_stage)
    rebuilt["updated_at"] = events[-1]["created_at"]
    return rebuilt


def load_state(project_dir: str | Path) -> dict[str, Any]:
    """``EventStorePort.load_state``: authoritative state from the event log.

    Always rebuilds from the append-only log rather than trusting the snapshot,
    so a corrupted or stale ``project_state.json`` cannot change the answer.
    """
    return rebuild_state(project_dir)


def verify_projection(project_dir: str | Path) -> list[dict[str, Any]]:
    """Detect drift between the cached snapshot and the event-log projection.

    The ``project_state.json`` snapshot is only a cache of the authoritative log
    (ADR-0003); this compares it field-by-field against the projection rebuilt
    from ``events.jsonl`` and returns a precise list of mismatches — each
    ``{"field", "snapshot", "rebuilt"}`` — so a tampered or stale snapshot is
    reported with the exact diverging fields. A healthy snapshot returns ``[]``.

    Detection only: this never mutates the snapshot, the log, or repairs drift —
    callers decide what to do with the report. ``updated_at`` is excluded
    because the live snapshot legitimately stamps its own wall clock while the
    rebuilt projection pins it to the last event's ``created_at``.
    """
    snapshot = load_project_state(project_dir)
    rebuilt = rebuild_state(project_dir)
    mismatches: list[dict[str, Any]] = []
    fields = (set(snapshot) | set(rebuilt)) - {"updated_at"}
    for field in sorted(fields):
        snapshot_value = snapshot.get(field, _ABSENT)
        rebuilt_value = rebuilt.get(field, _ABSENT)
        if snapshot_value != rebuilt_value:
            mismatches.append(
                {
                    "field": field,
                    "snapshot": None if snapshot_value is _ABSENT else snapshot_value,
                    "rebuilt": None if rebuilt_value is _ABSENT else rebuilt_value,
                }
            )
    return mismatches


def load_events(project_dir: str | Path) -> list[dict[str, Any]]:
    path = _events_path(project_dir)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def validate_transition(previous: str, next: str, *, resume: bool = False) -> None:
    if previous not in STAGES:
        raise ValueError(f"unknown previous stage: {previous}")
    if next not in STAGES:
        raise ValueError(f"unknown next stage: {next}")
    if previous in TERMINAL_STAGES and not resume:
        raise ValueError(f"{previous} is terminal; explicit resume is required")
    if next not in allowed_next_stages(previous):
        raise ValueError(f"illegal transition: {previous} -> {next}")


def _write_state(project_dir: str | Path, state: dict[str, Any]) -> None:
    path = _state_path(project_dir)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
