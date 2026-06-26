from __future__ import annotations

from typing import Any

from .ids import hash_payload, make_stable_id
from .schemas import CANONICAL_SCHEMA_VERSION, now_iso


def build_event(
    *,
    project_id: str,
    event_type: str,
    actor: str,
    previous_stage: str,
    next_stage: str,
    object_refs: list[dict[str, Any]] | None = None,
    message: str = "",
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    payload_data = payload or {}
    created_at = now_iso()
    payload_hash = hash_payload(
        {
            "project_id": project_id,
            "event_type": event_type,
            "actor": actor,
            "previous_stage": previous_stage,
            "next_stage": next_stage,
            "object_refs": object_refs or [],
            "message": message,
            "payload": payload_data,
        }
    )
    event_id = make_stable_id(
        "event",
        {
            "project_id": project_id,
            "event_type": event_type,
            "created_at": created_at,
            "payload_hash": payload_hash,
        },
    )
    event = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "event_id": event_id,
        "project_id": project_id,
        "event_type": event_type,
        "actor": actor,
        "created_at": created_at,
        "previous_stage": previous_stage,
        "next_stage": next_stage,
        "object_refs": object_refs or [],
        "message": message,
        "payload_hash": payload_hash,
        "payload": payload_data,
    }
    # An explicit, caller-supplied dedup token: it is decoupled from
    # ``created_at`` and the content hash so a deliberate retry of "the same
    # logical event" can be recognised even when the wall clock has moved on.
    # Events built without a key keep the historical shape exactly (no extra
    # field), so existing logs and callers are byte-for-byte unaffected.
    if idempotency_key is not None:
        event["idempotency_key"] = idempotency_key
    return event
