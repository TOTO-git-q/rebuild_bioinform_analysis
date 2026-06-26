"""Transition definition skeletons for the main states (WP-04d / T-04-04).

This module adds the next thin, metadata-only layer on top of the WP-04c
state-machine foundation (:mod:`auto_bioinfo.core.state_machine`). Where WP-04c
answered *"is this ``source -> target`` edge allowed?"*, T-04-04 records, for the
canonical main-state path, *which command drives an edge and which event it
emits* — as inert **skeletons**, not executable handlers.

A :class:`TransitionDefinition` is a pure record carrying:

- ``source`` / ``target`` — canonical stage strings (from
  :data:`auto_bioinfo.core.state.STAGES`), never a divergent vocabulary;
- a :class:`CommandSkeleton` (``id`` + ``type``) — the *intent* that would
  drive the edge;
- an :class:`EventSkeleton` (``id`` + ``type``) — the *fact* that would be
  emitted;
- an optional ``guard_ref`` — a hook name reserved for a later slice's guard
  wiring (metadata only; no guard is executed here).

There are deliberately **no** command handlers, no command execution, no event
emission, and no I/O. Listing, lookup, and validation are all pure functions of
in-memory records, so nothing here can create or modify a project file.

:class:`TransitionDefinitionRegistry` is the deterministic registry/list/lookup
container. Every registration is validated against a WP-04c
:class:`~auto_bioinfo.core.state_machine.TransitionRegistry` (the source of
truth for which edges exist) and fails closed with a stable error *code* on any
malformed entry: unknown states, an edge the transition registry does not
accept (``target mismatch``), a duplicate edge, a duplicate command id, a
duplicate event id, or a blank/malformed field.

:func:`build_main_path_definitions` assembles the canonical skeleton: one
definition per forward edge of :data:`auto_bioinfo.core.state.MAIN_SEQUENCE`
(the happy-path main-state spine). It invents no states and pads nothing — the
state set and the allowed edges both come from the existing tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state import LINEAR_NEXT, MAIN_SEQUENCE
from .state_machine import (
    StateMachineError,
    TransitionRegistry,
    is_main_state,
    serialize_main_state,
)

# --- Stable error codes ------------------------------------------------------
# Part of this module's contract: callers and tests switch on these strings, so
# they must stay stable. They are deliberately distinct from the WP-04c
# state-machine codes so a *definition* failure is never confused with an *edge*
# failure.
CODE_DEF_UNKNOWN_SOURCE_STATE = "DEF_UNKNOWN_SOURCE_STATE"
CODE_DEF_UNKNOWN_TARGET_STATE = "DEF_UNKNOWN_TARGET_STATE"
CODE_DEF_TARGET_MISMATCH = "DEF_TARGET_MISMATCH"
CODE_DEF_DUPLICATE_EDGE = "DEF_DUPLICATE_EDGE"
CODE_DEF_DUPLICATE_COMMAND_ID = "DEF_DUPLICATE_COMMAND_ID"
CODE_DEF_DUPLICATE_EVENT_ID = "DEF_DUPLICATE_EVENT_ID"
CODE_DEF_BLANK_ID = "DEF_BLANK_ID"
CODE_DEF_MALFORMED = "DEF_MALFORMED"

# Every code registration can fail with, for exhaustive testing/validation.
DEFINITION_ERROR_CODES = (
    CODE_DEF_UNKNOWN_SOURCE_STATE,
    CODE_DEF_UNKNOWN_TARGET_STATE,
    CODE_DEF_TARGET_MISMATCH,
    CODE_DEF_DUPLICATE_EDGE,
    CODE_DEF_DUPLICATE_COMMAND_ID,
    CODE_DEF_DUPLICATE_EVENT_ID,
    CODE_DEF_BLANK_ID,
    CODE_DEF_MALFORMED,
)

# Default skeleton "type" tags. They classify the *kind* of artefact a later
# slice would build; they carry no executable behaviour.
COMMAND_TYPE = "command"
EVENT_TYPE = "event"


class TransitionDefinitionError(StateMachineError):
    """A transition definition could not be registered (malformed/duplicate/mismatch).

    Reuses the WP-04c :class:`~auto_bioinfo.core.state_machine.StateMachineError`
    base so it carries the same stable :attr:`code` / ``source`` / ``target``
    contract, but is a distinct type so callers can catch definition failures
    specifically.
    """


# --- Inert command / event skeletons ----------------------------------------


@dataclass(frozen=True)
class CommandSkeleton:
    """The *intent* that would drive a transition — id + type, nothing more.

    This is a placeholder: it names a command but holds no handler, payload
    schema, or execution semantics. Those belong to a later slice (explicitly
    out of scope for T-04-04).
    """

    id: str
    type: str = COMMAND_TYPE

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type}


@dataclass(frozen=True)
class EventSkeleton:
    """The *fact* a transition would emit — id + type, nothing more.

    A placeholder mirroring :class:`CommandSkeleton`: it names an event but
    carries no payload, no emission, and no persistence.
    """

    id: str
    type: str = EVENT_TYPE

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type}


@dataclass(frozen=True)
class TransitionDefinition:
    """A metadata-only record binding an edge to a command + event skeleton.

    ``source``/``target`` are canonical stage strings; ``command``/``event`` are
    inert skeletons; ``guard_ref`` is an optional hook name reserved for a later
    guard-wiring slice (no guard is consulted here); ``label`` is an optional
    human description. The record executes nothing and touches no I/O.
    """

    source: str
    target: str
    command: CommandSkeleton
    event: EventSkeleton
    guard_ref: str = ""
    label: str = ""

    @property
    def edge(self) -> tuple[str, str]:
        return (self.source, self.target)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, fully-ordered dict for serialisation."""
        return {
            "source": self.source,
            "target": self.target,
            "command": self.command.to_dict(),
            "event": self.event.to_dict(),
            "guard_ref": self.guard_ref,
            "label": self.label,
        }


def _clean_id(value: Any) -> str | None:
    """Return a stripped non-blank id, or ``None`` if ``value`` is not one.

    Treats a non-string or a blank/whitespace-only string as "not an id" so the
    caller can fail closed with a stable code instead of storing junk.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


# --- Deterministic registry --------------------------------------------------


class TransitionDefinitionRegistry:
    """A deterministic registry of :class:`TransitionDefinition` records.

    Construction requires a WP-04c
    :class:`~auto_bioinfo.core.state_machine.TransitionRegistry`: it is the
    single source of truth for which ``source -> target`` edges exist, so a
    definition can only be registered for an edge that registry already accepts.
    The container holds no project state and performs no I/O.
    """

    def __init__(self, transition_registry: TransitionRegistry) -> None:
        if not isinstance(transition_registry, TransitionRegistry):
            raise TransitionDefinitionError(
                f"a TransitionRegistry is required, got {type(transition_registry).__name__}",
                code=CODE_DEF_MALFORMED,
            )
        self._registry = transition_registry
        self._defs: dict[tuple[str, str], TransitionDefinition] = {}
        self._command_ids: dict[str, tuple[str, str]] = {}
        self._event_ids: dict[str, tuple[str, str]] = {}

    # -- registration --------------------------------------------------------

    def register(self, definition: TransitionDefinition) -> TransitionDefinition:
        """Register a fully-formed :class:`TransitionDefinition` and return the
        normalised record.

        Fails closed with :class:`TransitionDefinitionError` (stable
        :data:`DEFINITION_ERROR_CODES`) when the definition is malformed, names
        an unknown state, names an edge the transition registry does not accept,
        carries a blank command/event id, or duplicates an already-registered
        edge / command id / event id. Nothing is mutated on failure.
        """
        if not isinstance(definition, TransitionDefinition):
            raise TransitionDefinitionError(
                f"expected a TransitionDefinition, got {type(definition).__name__}",
                code=CODE_DEF_MALFORMED,
            )
        if not isinstance(definition.command, CommandSkeleton) or not isinstance(definition.event, EventSkeleton):
            raise TransitionDefinitionError(
                "definition.command must be a CommandSkeleton and definition.event an EventSkeleton",
                code=CODE_DEF_MALFORMED,
                source=str(definition.source),
                target=str(definition.target),
            )

        command_id = _clean_id(definition.command.id)
        event_id = _clean_id(definition.event.id)
        if command_id is None:
            raise TransitionDefinitionError(
                "command id must be a non-blank string",
                code=CODE_DEF_BLANK_ID,
                source=str(definition.source),
                target=str(definition.target),
            )
        if event_id is None:
            raise TransitionDefinitionError(
                "event id must be a non-blank string",
                code=CODE_DEF_BLANK_ID,
                source=str(definition.source),
                target=str(definition.target),
            )
        if not _clean_id(definition.command.type) or not _clean_id(definition.event.type):
            raise TransitionDefinitionError(
                "command type and event type must be non-blank strings",
                code=CODE_DEF_MALFORMED,
                source=str(definition.source),
                target=str(definition.target),
            )

        if not is_main_state(definition.source):
            raise TransitionDefinitionError(
                f"unknown source state {definition.source!r}",
                code=CODE_DEF_UNKNOWN_SOURCE_STATE,
                source=str(definition.source),
                target=str(definition.target),
            )
        if not is_main_state(definition.target):
            raise TransitionDefinitionError(
                f"unknown target state {definition.target!r}",
                code=CODE_DEF_UNKNOWN_TARGET_STATE,
                source=str(definition.source),
                target=str(definition.target),
            )
        src = serialize_main_state(definition.source)
        tgt = serialize_main_state(definition.target)

        # The edge must be one the WP-04c transition registry accepts; a
        # definition can never describe an edge the state machine forbids.
        if not self._registry.is_registered(src, tgt):
            raise TransitionDefinitionError(
                f"edge {src!r} -> {tgt!r} is not accepted by the transition registry",
                code=CODE_DEF_TARGET_MISMATCH,
                source=src,
                target=tgt,
            )

        if (src, tgt) in self._defs:
            raise TransitionDefinitionError(
                f"transition definition already registered for edge {src!r} -> {tgt!r}",
                code=CODE_DEF_DUPLICATE_EDGE,
                source=src,
                target=tgt,
            )
        if command_id in self._command_ids:
            raise TransitionDefinitionError(
                f"duplicate command id {command_id!r} (already bound to {self._command_ids[command_id]})",
                code=CODE_DEF_DUPLICATE_COMMAND_ID,
                source=src,
                target=tgt,
            )
        if event_id in self._event_ids:
            raise TransitionDefinitionError(
                f"duplicate event id {event_id!r} (already bound to {self._event_ids[event_id]})",
                code=CODE_DEF_DUPLICATE_EVENT_ID,
                source=src,
                target=tgt,
            )

        normalised = TransitionDefinition(
            source=src,
            target=tgt,
            command=CommandSkeleton(id=command_id, type=definition.command.type),
            event=EventSkeleton(id=event_id, type=definition.event.type),
            guard_ref=definition.guard_ref,
            label=definition.label,
        )
        self._defs[(src, tgt)] = normalised
        self._command_ids[command_id] = (src, tgt)
        self._event_ids[event_id] = (src, tgt)
        return normalised

    def define(
        self,
        source: Any,
        target: Any,
        *,
        command_id: str,
        event_id: str,
        command_type: str = COMMAND_TYPE,
        event_type: str = EVENT_TYPE,
        guard_ref: str = "",
        label: str = "",
    ) -> TransitionDefinition:
        """Build a :class:`TransitionDefinition` from primitives and register it.

        A convenience over :meth:`register` for callers that do not want to
        construct the skeleton dataclasses by hand. All the same validation and
        stable error codes apply.
        """
        return self.register(
            TransitionDefinition(
                source=source,
                target=target,
                command=CommandSkeleton(id=command_id, type=command_type),
                event=EventSkeleton(id=event_id, type=event_type),
                guard_ref=guard_ref,
                label=label,
            )
        )

    # -- deterministic lookup / listing -------------------------------------

    def definitions(self) -> list[TransitionDefinition]:
        """Return all definitions in deterministic ``(source, target)`` order."""
        return [self._defs[key] for key in sorted(self._defs)]

    def edges(self) -> list[tuple[str, str]]:
        """Return every defined ``(source, target)`` edge, sorted."""
        return sorted(self._defs)

    def get(self, source: Any, target: Any) -> TransitionDefinition | None:
        """Return the definition for an edge, or ``None`` if absent."""
        if not (is_main_state(source) and is_main_state(target)):
            return None
        return self._defs.get((serialize_main_state(source), serialize_main_state(target)))

    def by_command_id(self, command_id: str) -> TransitionDefinition | None:
        """Return the definition whose command has ``command_id``, or ``None``."""
        edge = self._command_ids.get(command_id)
        return self._defs.get(edge) if edge is not None else None

    def by_event_id(self, event_id: str) -> TransitionDefinition | None:
        """Return the definition whose event has ``event_id``, or ``None``."""
        edge = self._event_ids.get(event_id)
        return self._defs.get(edge) if edge is not None else None

    def command_ids(self) -> list[str]:
        """Return every registered command id, sorted (deterministic)."""
        return sorted(self._command_ids)

    def event_ids(self) -> list[str]:
        """Return every registered event id, sorted (deterministic)."""
        return sorted(self._event_ids)

    def to_table(self) -> list[dict[str, Any]]:
        """Return a deterministic, serialisable list of every definition."""
        return [d.to_dict() for d in self.definitions()]

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, edge: object) -> bool:
        if not (isinstance(edge, tuple) and len(edge) == 2):
            return False
        return self.get(edge[0], edge[1]) is not None


# --- Canonical main-state-path skeleton -------------------------------------


def build_main_path_definitions(transition_registry: TransitionRegistry | None = None) -> TransitionDefinitionRegistry:
    """Build the canonical transition-definition skeleton for the main-state path.

    Registers one :class:`TransitionDefinition` per *forward* edge of
    :data:`auto_bioinfo.core.state.MAIN_SEQUENCE` — the happy-path spine that
    advances ``INTAKE -> ... -> COMPLETED``. Each definition carries a command
    skeleton (the intent to advance) and an event skeleton (the fact of entry);
    every target is, by construction, an edge the WP-04c transition registry
    accepts.

    The state set and the allowed edges both come from the existing canonical
    tables: no state is invented and the set is never padded. ``COMPLETED`` is a
    terminal, so it has no outgoing forward edge; the side/terminal edges
    (human-review, safe-stops) are intentionally out of this minimal slice and
    left to a later WP.

    Passing an explicit ``transition_registry`` is supported for testing; by
    default one is derived from :data:`auto_bioinfo.core.state.LINEAR_NEXT`.
    """
    registry = transition_registry or TransitionRegistry.from_table(LINEAR_NEXT)
    definitions = TransitionDefinitionRegistry(registry)
    for source, target in zip(MAIN_SEQUENCE, MAIN_SEQUENCE[1:], strict=False):
        definitions.define(
            source,
            target,
            command_id=f"CMD_ADVANCE_TO_{target}",
            event_id=f"EVT_{target}_ENTERED",
            label=f"advance {source} -> {target}",
        )
    return definitions
