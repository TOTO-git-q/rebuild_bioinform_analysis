"""Deterministic, read-only audit query API over the event log (WP-24 / T-24-07..T-24-11).

The requirement spec asks that an operator be able to answer *"what happened, who
did it, with which tool/prompt/version, and which of it is still awaiting review?"*
**without logging into a server to grep files** — from the append-only event log
alone, as a deterministic query, with sensitive payload never leaking into the
answer.

This module is that query layer, but kept **pure and offline**: it operates over
an in-memory list of event dicts (exactly the shape
:func:`auto_bioinfo.core.events.build_event` produces and
:func:`auto_bioinfo.core.store.load_events` returns), never touches the
filesystem, a socket, or the clock, and never mutates the events.  It is strictly
*read model* — it creates, advances, or persists nothing.  Every projection is
redacted through :func:`auto_bioinfo.observability.redaction.redact` so a secret
that somehow reached an event payload cannot escape through an audit answer.

Design constraints (WP-24), mirroring the WP-04b query-layer house style:

- **Pure and deterministic.** Every function is a total function of its explicit
  in-memory ``events`` input plus explicit filter facts.  Ordering is the
  append-only log order (stable for a given log); pagination selects a stable
  window.  Byte-identical input yields a byte-identical projection.
- **Fail closed on bad input.** Bad pagination or a non-list events input raises
  :class:`AuditQueryError`; a malformed individual event is skipped-with-reason
  rather than crashing the whole query, and reported in ``skipped``.
- **Redacted by construction.** No projection ever carries a raw sensitive value;
  the full payload is only ever exposed through the redacting projection.
- **Bounded filter surface.** Filters are an explicit :class:`AuditFilter` value;
  callers compose the fields they need (project / actor / event-type / stage /
  object-type / tool / provider / prompt-version / payload-contains).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .redaction import redact

# The canonical event fields this query layer reads (a subset of build_event's
# output).  An event missing any of these required identity fields is malformed.
_REQUIRED_EVENT_FIELDS = ("event_id", "project_id", "event_type", "actor", "created_at", "previous_stage", "next_stage")

# Payload keys that carry the tool/agent-call audit dimensions (T-24-09).  A query
# may filter on any of these when the event payload records them.
TOOL_CALL_KEYS = ("tool", "provider", "prompt", "prompt_version", "model", "tool_version")


class AuditQueryError(RuntimeError):
    """An audit query could not be answered (bad input or bad pagination)."""


@dataclass(frozen=True)
class AuditFilter:
    """A bounded, composable set of audit filter facts (all optional, all ANDed).

    - ``project_id`` — restrict to one project;
    - ``actor`` — restrict to one actor;
    - ``event_type`` / ``event_types`` — a single type or a set of types;
    - ``previous_stage`` / ``next_stage`` — restrict by transition endpoints;
    - ``object_type`` / ``object_id`` — an event must reference a matching object;
    - ``tool`` / ``provider`` / ``prompt_version`` — tool/agent-call dimensions
      matched against the event payload (T-24-09);
    - ``payload_contains`` — an explicit ``{key: value}`` mapping every entry of
      which must equal the event payload's value at that key.

    An empty filter matches every well-formed event.
    """

    project_id: str | None = None
    actor: str | None = None
    event_type: str | None = None
    event_types: frozenset[str] | None = None
    previous_stage: str | None = None
    next_stage: str | None = None
    object_type: str | None = None
    object_id: str | None = None
    tool: str | None = None
    provider: str | None = None
    prompt_version: str | None = None
    payload_contains: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "actor": self.actor,
            "event_type": self.event_type,
            "event_types": sorted(self.event_types) if self.event_types is not None else None,
            "previous_stage": self.previous_stage,
            "next_stage": self.next_stage,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "tool": self.tool,
            "provider": self.provider,
            "prompt_version": self.prompt_version,
            "payload_contains": dict(self.payload_contains) if isinstance(self.payload_contains, Mapping) else None,
        }


@dataclass(frozen=True)
class AuditRecord:
    """One event projected to its stable, redacted audit fields.

    ``seq`` is the event's absolute 0-based position in the log so records stay
    identifiable across pages.  ``payload`` is the redacted payload projection;
    the raw value is never exposed.
    """

    seq: int
    event_id: str
    project_id: str
    event_type: str
    actor: str
    created_at: str
    previous_stage: str
    next_stage: str
    message: str
    object_refs: list[dict[str, Any]] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "event_id": self.event_id,
            "project_id": self.project_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "created_at": self.created_at,
            "previous_stage": self.previous_stage,
            "next_stage": self.next_stage,
            "message": self.message,
            "object_refs": [dict(ref) for ref in self.object_refs],
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class SkippedEvent:
    """An event that could not be projected, with the reason (fail-closed report)."""

    seq: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "reason": self.reason}


@dataclass(frozen=True)
class AuditPage:
    """A deterministic slice of a filtered, ordered audit result set."""

    records: tuple[AuditRecord, ...]
    total: int
    limit: int | None
    offset: int
    skipped: tuple[SkippedEvent, ...] = ()

    @property
    def returned(self) -> int:
        return len(self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "returned": self.returned,
            "skipped": [s.to_dict() for s in self.skipped],
        }


def _is_malformed(event: Any) -> str | None:
    if not isinstance(event, Mapping):
        return "event is not a mapping"
    missing = [f for f in _REQUIRED_EVENT_FIELDS if f not in event]
    if missing:
        return f"missing required fields: {', '.join(missing)}"
    return None


def _payload_of(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _matches(event: Mapping[str, Any], flt: AuditFilter) -> bool:
    """True iff ``event`` satisfies every set filter field (all ANDed)."""
    if flt.project_id is not None and event.get("project_id") != flt.project_id:
        return False
    if flt.actor is not None and event.get("actor") != flt.actor:
        return False
    if flt.event_type is not None and event.get("event_type") != flt.event_type:
        return False
    if flt.event_types is not None and event.get("event_type") not in flt.event_types:
        return False
    if flt.previous_stage is not None and event.get("previous_stage") != flt.previous_stage:
        return False
    if flt.next_stage is not None and event.get("next_stage") != flt.next_stage:
        return False
    if flt.object_type is not None or flt.object_id is not None:
        refs = event.get("object_refs") or []
        if not isinstance(refs, Sequence):
            return False
        matched = False
        for ref in refs:
            if not isinstance(ref, Mapping):
                continue
            if flt.object_type is not None and ref.get("object_type") != flt.object_type:
                continue
            if flt.object_id is not None and ref.get("object_id") != flt.object_id:
                continue
            matched = True
            break
        if not matched:
            return False
    payload = _payload_of(event)
    if flt.tool is not None and payload.get("tool") != flt.tool:
        return False
    if flt.provider is not None and payload.get("provider") != flt.provider:
        return False
    if flt.prompt_version is not None and payload.get("prompt_version") != flt.prompt_version:
        return False
    if flt.payload_contains is not None:
        for key, value in flt.payload_contains.items():
            if payload.get(key) != value:
                return False
    return True


def _project(seq: int, event: Mapping[str, Any]) -> AuditRecord:
    """Project one event to a redacted :class:`AuditRecord`."""
    redacted_payload = redact(_payload_of(event))
    redacted_message = redact(str(event.get("message", "")))
    refs = event.get("object_refs") or []
    object_refs = [dict(ref) for ref in refs if isinstance(ref, Mapping)]
    return AuditRecord(
        seq=seq,
        event_id=str(event.get("event_id", "")),
        project_id=str(event.get("project_id", "")),
        event_type=str(event.get("event_type", "")),
        actor=str(event.get("actor", "")),
        created_at=str(event.get("created_at", "")),
        previous_stage=str(event.get("previous_stage", "")),
        next_stage=str(event.get("next_stage", "")),
        message=redacted_message if isinstance(redacted_message, str) else "",
        object_refs=object_refs,
        payload=redacted_payload if isinstance(redacted_payload, dict) else {},
    )


def _validate_pagination(limit: int | None, offset: int) -> None:
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise AuditQueryError(f"offset must be a non-negative int, got {offset!r}")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        raise AuditQueryError(f"limit must be None or a non-negative int, got {limit!r}")


def query_audit(events: Any, flt: AuditFilter | None = None, *, limit: int | None = None, offset: int = 0) -> AuditPage:
    """Return a deterministic, redacted, paginated audit projection of ``events``.

    ``events`` is an in-memory list of event dicts (append-only log order).  A
    malformed event is not silently dropped: it is skipped and reported in
    ``skipped`` with a reason, so a corrupt record can never masquerade as "no
    matching audit trail".  Filtering is applied over the well-formed events in
    log order, then ``limit``/``offset`` select a stable window.
    """
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise AuditQueryError("events must be a sequence of event mappings")
    _validate_pagination(limit, offset)
    active = flt if isinstance(flt, AuditFilter) else AuditFilter()

    matched: list[AuditRecord] = []
    skipped: list[SkippedEvent] = []
    for seq, event in enumerate(events):
        malformed = _is_malformed(event)
        if malformed is not None:
            skipped.append(SkippedEvent(seq=seq, reason=malformed))
            continue
        if _matches(event, active):
            matched.append(_project(seq, event))

    total = len(matched)
    window = matched[offset:] if limit is None else matched[offset : offset + limit]
    return AuditPage(records=tuple(window), total=total, limit=limit, offset=offset, skipped=tuple(skipped))


def query_tool_calls(events: Any, *, provider: str | None = None, tool: str | None = None, prompt_version: str | None = None) -> AuditPage:
    """Convenience audit query for tool/agent calls filtered by provider/tool/version (T-24-09).

    Restricts to events whose payload records at least one tool-call dimension in
    :data:`TOOL_CALL_KEYS`, then applies the provider/tool/prompt-version filter.
    Read-only, redacted, and deterministic like :func:`query_audit`.
    """
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise AuditQueryError("events must be a sequence of event mappings")
    flt = AuditFilter(provider=provider, tool=tool, prompt_version=prompt_version)
    page = query_audit(events, flt)
    # keep only records that actually carry a tool-call dimension
    tool_records = tuple(r for r in page.records if any(key in r.payload for key in TOOL_CALL_KEYS))
    return AuditPage(records=tool_records, total=len(tool_records), limit=None, offset=0, skipped=page.skipped)


def audit_summary(events: Any) -> dict[str, Any]:
    """A deterministic count summary of a log: totals by event_type and by actor.

    A read-only roll-up an operator can glance at; malformed events are counted
    under ``skipped`` rather than crashing the summary.
    """
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise AuditQueryError("events must be a sequence of event mappings")
    by_type: dict[str, int] = {}
    by_actor: dict[str, int] = {}
    skipped = 0
    total = 0
    for event in events:
        if _is_malformed(event) is not None:
            skipped += 1
            continue
        total += 1
        etype = str(event.get("event_type", ""))
        actor = str(event.get("actor", ""))
        by_type[etype] = by_type.get(etype, 0) + 1
        by_actor[actor] = by_actor.get(actor, 0) + 1
    return {
        "total": total,
        "skipped": skipped,
        "by_event_type": dict(sorted(by_type.items())),
        "by_actor": dict(sorted(by_actor.items())),
    }


__all__ = [
    "TOOL_CALL_KEYS",
    "AuditQueryError",
    "AuditFilter",
    "AuditRecord",
    "SkippedEvent",
    "AuditPage",
    "query_audit",
    "query_tool_calls",
    "audit_summary",
]
