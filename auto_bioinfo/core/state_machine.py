"""Main state enum, transition registry, and guard interface (WP-04c / T-04-03).

This is the small *domain-layer* state-machine foundation the later control-plane
command slices (T-04-04+) build on. It deliberately does three things and no
more:

1. **A bounded main-state representation** — :class:`MainState`, an enum derived
   from the single existing state table in :mod:`auto_bioinfo.core.state`
   (``STAGES``). It is *not* a second, divergent vocabulary: every member name
   and value is exactly a canonical stage string, so it serialises
   deterministically (``MainState.INTAKE.value == "INTAKE"``) and a plain string
   compares equal to its member (``MainState.INTAKE == "INTAKE"``).

2. **A transition registry** — :class:`TransitionRegistry`, an explicit set of
   allowed ``(source, target)`` edges. It rejects malformed and duplicate
   registrations with stable error *codes* and offers deterministic
   lookup/listing. It carries no command/event/target-state skeleton (that is
   T-04-04); callers register exactly the edges they need.

3. **A guard interface and result object** — :class:`Guard` (a callable
   contract) and :class:`GuardResult` (a structured allow/deny carrying a stable
   :data:`code`, never a bare boolean). :meth:`TransitionRegistry.evaluate`
   returns one of these for any attempted transition, classifying every illegal
   transition with a clear, stable code (unknown source, unknown target,
   unregistered, or guard-denied).

The whole module is pure and side-effect free: nothing here reads or writes a
project directory, so registry/guard checks can never create or modify project
files. The existing write-path guard (``store.validate_transition``) and the
WP-04a/WP-04b command/query slices are untouched — this is an additive,
code-classifying layer beside them, not a replacement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .state import STAGES

# --- Stable error / outcome codes -------------------------------------------
# These strings are part of the module's contract: callers and tests switch on
# them, so they must stay stable. ``CODE_ALLOWED`` is the single success code;
# the rest each name one way a transition is illegal.
CODE_ALLOWED = "ALLOWED"
CODE_UNKNOWN_SOURCE_STATE = "UNKNOWN_SOURCE_STATE"
CODE_UNKNOWN_TARGET_STATE = "UNKNOWN_TARGET_STATE"
CODE_UNREGISTERED_TRANSITION = "UNREGISTERED_TRANSITION"
CODE_DUPLICATE_TRANSITION = "DUPLICATE_TRANSITION"
CODE_MALFORMED_TRANSITION = "MALFORMED_TRANSITION"
CODE_GUARD_DENIED = "GUARD_DENIED"
CODE_MALFORMED_GUARD_RESULT = "MALFORMED_GUARD_RESULT"

# Every code this module can emit, for exhaustive testing/validation.
ERROR_CODES = (
    CODE_UNKNOWN_SOURCE_STATE,
    CODE_UNKNOWN_TARGET_STATE,
    CODE_UNREGISTERED_TRANSITION,
    CODE_DUPLICATE_TRANSITION,
    CODE_MALFORMED_TRANSITION,
    CODE_GUARD_DENIED,
    CODE_MALFORMED_GUARD_RESULT,
)


# --- Bounded main-state enum -------------------------------------------------
# Derived from the single canonical state table so the enum can never drift from
# ``state.STAGES``. ``type=str`` makes each member a ``str`` subclass: it
# serialises to its canonical value and compares equal to the plain string.
MainState = Enum("MainState", {name: name for name in STAGES}, type=str)
MainState.__doc__ = "A bounded main project state; every member mirrors a canonical stage in state.STAGES."


def is_main_state(value: Any) -> bool:
    """True iff ``value`` names a known main state (enum member or its string)."""
    if isinstance(value, MainState):
        return True
    return isinstance(value, str) and value in STAGES


def coerce_main_state(value: Any) -> MainState:
    """Return the :class:`MainState` for ``value`` or raise :class:`UnknownStateError`.

    Accepts an existing member or its canonical string; anything else fails
    closed with the stable :data:`CODE_UNKNOWN_SOURCE_STATE`-style classification
    so callers never silently coerce an unknown stage.
    """
    if isinstance(value, MainState):
        return value
    if isinstance(value, str) and value in STAGES:
        return MainState(value)
    raise UnknownStateError(f"unknown main state: {value!r}", code=CODE_UNKNOWN_SOURCE_STATE, source=str(value))


def serialize_main_state(value: MainState | str) -> str:
    """Return the canonical wire string for a main state (deterministic)."""
    return coerce_main_state(value).value


def validate_main_state(value: Any, label: str = "state") -> list[str]:
    """Return a list of human-readable errors if ``value`` is not a main state.

    Mirrors the ``list[str]`` validator convention used across the core (see
    :mod:`auto_bioinfo.core.validation`); an empty list means valid.
    """
    if is_main_state(value):
        return []
    return [f"{label} is not a known main state: {value!r}"]


# --- Typed errors with stable codes -----------------------------------------


class StateMachineError(Exception):
    """Base for state-machine failures; carries a stable :attr:`code`.

    Every illegal transition or bad registration raises (or is reported as) one
    of these so the failure is classified by a stable code rather than only a
    prose message.
    """

    code: str = ""

    def __init__(self, message: str, *, code: str = "", source: str = "", target: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.source = source
        self.target = target


class UnknownStateError(StateMachineError):
    """A referenced state is not a known main state."""


class TransitionRegistrationError(StateMachineError):
    """A transition could not be registered (malformed or duplicate)."""


class IllegalTransitionError(StateMachineError):
    """An attempted transition is not allowed (unregistered or guard-denied)."""


# --- Guard interface and result object --------------------------------------


@dataclass(frozen=True)
class GuardResult:
    """The structured outcome of a transition check.

    ``allowed`` is the decision; ``code`` is a stable classification
    (:data:`CODE_ALLOWED` when allowed, otherwise one of :data:`ERROR_CODES`);
    ``detail`` is a human-readable explanation; ``source``/``target`` echo the
    edge that was checked. This is intentionally richer than a bare boolean so a
    denial always carries a machine-stable reason.
    """

    allowed: bool
    code: str
    detail: str = ""
    source: str = ""
    target: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "code": self.code,
            "detail": self.detail,
            "source": self.source,
            "target": self.target,
        }

    def raise_for_denied(self) -> None:
        """Raise :class:`IllegalTransitionError` if this result is a denial."""
        if not self.allowed:
            raise IllegalTransitionError(self.detail or self.code, code=self.code, source=self.source, target=self.target)


def allow(source: str = "", target: str = "", detail: str = "") -> GuardResult:
    """Build an allowing :class:`GuardResult` (stable :data:`CODE_ALLOWED`)."""
    return GuardResult(allowed=True, code=CODE_ALLOWED, detail=detail, source=source, target=target)


def deny(code: str, detail: str = "", source: str = "", target: str = "") -> GuardResult:
    """Build a denying :class:`GuardResult` with an explicit stable ``code``."""
    return GuardResult(allowed=False, code=code, detail=detail, source=source, target=target)


@runtime_checkable
class Guard(Protocol):
    """A transition guard: given the edge and a context, return a structured
    decision.

    A guard must return a :class:`GuardResult`, never a bare boolean, so its
    denial reason is always a stable code. A guard that denies without naming a
    more specific code should use :data:`CODE_GUARD_DENIED`.
    """

    def __call__(self, transition: Transition, context: Mapping[str, Any]) -> GuardResult: ...


@dataclass(frozen=True)
class Transition:
    """A registered allowed edge between two main states.

    ``source``/``target`` are canonical stage strings; ``label`` is an optional
    human name; ``guard`` is an optional :class:`Guard` consulted by
    :meth:`TransitionRegistry.evaluate` after the edge is found to be registered.
    """

    source: str
    target: str
    label: str = ""
    guard: Guard | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.target)


# --- Transition registry -----------------------------------------------------


class TransitionRegistry:
    """A registry of allowed main-state transitions with deterministic lookup.

    The registry validates every registration against the bounded main-state
    vocabulary and rejects malformed or duplicate edges with stable codes. It
    holds no project state and performs no I/O — it is a pure description of
    which edges are allowed, plus their optional guards.
    """

    def __init__(self) -> None:
        self._transitions: dict[tuple[str, str], Transition] = {}

    # -- registration --------------------------------------------------------

    def register(self, source: Any, target: Any, *, label: str = "", guard: Guard | None = None) -> Transition:
        """Register an allowed ``source -> target`` edge and return it.

        Raises :class:`TransitionRegistrationError` with
        :data:`CODE_MALFORMED_TRANSITION` when either endpoint is not a known
        main state or the edge is a self-loop (the canonical table has none and
        the write-path guard rejects them), and with
        :data:`CODE_DUPLICATE_TRANSITION` when the same edge is registered twice.
        """
        if not is_main_state(source):
            raise TransitionRegistrationError(
                f"cannot register transition: unknown source state {source!r}",
                code=CODE_MALFORMED_TRANSITION,
                source=str(source),
                target=str(target),
            )
        if not is_main_state(target):
            raise TransitionRegistrationError(
                f"cannot register transition: unknown target state {target!r}",
                code=CODE_MALFORMED_TRANSITION,
                source=str(source),
                target=str(target),
            )
        src = serialize_main_state(source)
        tgt = serialize_main_state(target)
        if src == tgt:
            raise TransitionRegistrationError(
                f"cannot register self-loop transition {src!r} -> {tgt!r}",
                code=CODE_MALFORMED_TRANSITION,
                source=src,
                target=tgt,
            )
        if (src, tgt) in self._transitions:
            raise TransitionRegistrationError(
                f"transition already registered: {src!r} -> {tgt!r}",
                code=CODE_DUPLICATE_TRANSITION,
                source=src,
                target=tgt,
            )
        transition = Transition(source=src, target=tgt, label=label, guard=guard)
        self._transitions[(src, tgt)] = transition
        return transition

    @classmethod
    def from_table(cls, table: Mapping[str, Iterable[str]], *, guard: Guard | None = None) -> TransitionRegistry:
        """Build a registry from a ``{source: [targets]}`` adjacency mapping.

        A convenience for deriving a registry from an existing state table (e.g.
        ``state.LINEAR_NEXT``) so the abstraction can be exercised against the
        canonical edges without hand-listing them. Every edge is registered
        through :meth:`register`, so the table is validated edge-for-edge and
        any malformed, self-loop, or duplicate edge fails closed with the same
        stable code :meth:`register` would raise — an input table is never
        normalised into success.

        The canonical table this is built from (``state.LINEAR_NEXT``) contains
        no self-loops, so no edge is silently dropped here; a self-loop in an
        input table is therefore a genuine malformation and is rejected rather
        than skipped. (If a future canonical source ever introduces a deliberate
        same-stage no-op, strip it explicitly at the call site before calling
        ``from_table`` instead of weakening this strictness.)
        """
        registry = cls()
        for source, targets in table.items():
            for target in targets:
                registry.register(source, target, guard=guard)
        return registry

    # -- deterministic lookup / listing -------------------------------------

    def is_registered(self, source: Any, target: Any) -> bool:
        """True iff ``source -> target`` is a registered edge."""
        if not (is_main_state(source) and is_main_state(target)):
            return False
        return (serialize_main_state(source), serialize_main_state(target)) in self._transitions

    def get(self, source: Any, target: Any) -> Transition | None:
        """Return the registered :class:`Transition`, or ``None`` if absent."""
        if not (is_main_state(source) and is_main_state(target)):
            return None
        return self._transitions.get((serialize_main_state(source), serialize_main_state(target)))

    def targets(self, source: Any) -> list[str]:
        """Return the allowed target states for ``source``, sorted (deterministic)."""
        if not is_main_state(source):
            return []
        src = serialize_main_state(source)
        return sorted(tgt for (s, tgt) in self._transitions if s == src)

    def sources(self) -> list[str]:
        """Return every source state with at least one edge, sorted."""
        return sorted({s for (s, _t) in self._transitions})

    def transitions(self) -> list[Transition]:
        """Return all transitions in a deterministic ``(source, target)`` order."""
        return [self._transitions[key] for key in sorted(self._transitions)]

    def __len__(self) -> int:
        return len(self._transitions)

    def __contains__(self, edge: object) -> bool:
        if not (isinstance(edge, tuple) and len(edge) == 2):
            return False
        return self.is_registered(edge[0], edge[1])

    # -- evaluation ----------------------------------------------------------

    def evaluate(self, source: Any, target: Any, context: Mapping[str, Any] | None = None) -> GuardResult:
        """Classify the attempted ``source -> target`` transition (no side effects).

        Returns an allowing :class:`GuardResult` only when both endpoints are
        known main states, the edge is registered, and the edge's guard (if any)
        allows it. Otherwise returns a denying result carrying the stable code
        that names *why* it is illegal:

        - :data:`CODE_UNKNOWN_SOURCE_STATE` / :data:`CODE_UNKNOWN_TARGET_STATE`
        - :data:`CODE_UNREGISTERED_TRANSITION`
        - :data:`CODE_GUARD_DENIED` (or a more specific code the guard returns)
        - :data:`CODE_MALFORMED_GUARD_RESULT` when a guard returns anything
          other than a :class:`GuardResult` (e.g. a bare ``bool``); the bad
          return is never trusted and never raises a bare ``AttributeError``.
        """
        ctx: Mapping[str, Any] = context or {}
        src_str = str(source.value if isinstance(source, MainState) else source)
        tgt_str = str(target.value if isinstance(target, MainState) else target)
        if not is_main_state(source):
            return deny(CODE_UNKNOWN_SOURCE_STATE, f"unknown source state {source!r}", source=src_str, target=tgt_str)
        if not is_main_state(target):
            return deny(CODE_UNKNOWN_TARGET_STATE, f"unknown target state {target!r}", source=src_str, target=tgt_str)
        src = serialize_main_state(source)
        tgt = serialize_main_state(target)
        transition = self._transitions.get((src, tgt))
        if transition is None:
            return deny(CODE_UNREGISTERED_TRANSITION, f"transition not registered: {src!r} -> {tgt!r}", source=src, target=tgt)
        if transition.guard is not None:
            result = transition.guard(transition, ctx)
            if not isinstance(result, GuardResult):
                # A guard must return a structured GuardResult, never a bare
                # bool/None/other. Fail closed with a stable code instead of
                # trusting the value (which would raise a bare AttributeError on
                # ``.allowed``).
                return deny(
                    CODE_MALFORMED_GUARD_RESULT,
                    f"guard for transition {src!r} -> {tgt!r} returned {type(result).__name__}, expected GuardResult",
                    source=src,
                    target=tgt,
                )
            if not result.allowed:
                # Normalise a guard denial that omitted a code, and pin the edge.
                code = result.code or CODE_GUARD_DENIED
                return deny(code, result.detail or f"guard denied transition {src!r} -> {tgt!r}", source=src, target=tgt)
        return allow(source=src, target=tgt, detail=transition.label)

    def assert_allowed(self, source: Any, target: Any, context: Mapping[str, Any] | None = None) -> Transition:
        """Raise :class:`IllegalTransitionError` unless the transition is allowed.

        The raised error carries the same stable ``code`` :meth:`evaluate`
        would have reported. Returns the registered :class:`Transition` on
        success, for callers that want a raise-style API instead of a result
        object.
        """
        result = self.evaluate(source, target, context)
        result.raise_for_denied()
        transition = self.get(source, target)
        assert transition is not None  # guaranteed by an allowing result
        return transition
