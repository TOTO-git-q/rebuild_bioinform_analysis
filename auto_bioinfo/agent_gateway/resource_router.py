"""Deterministic, metadata-only biomedical resource router (WP-28B1).

Given bounded *task facts* (which agent, for what purpose, with what modality /
evidence needs, preferences, approval facts and risk ceiling), decide **which
registered actions are admissible** — and record, for every candidate that was
not selected, a stable machine-readable reason.

This is the project-native, clean-room translation of the "bounded resource
retrieval" concept described in ``docs/architecture/biomni_cleanroom_integration.md``.
The concept is reimplemented against this repository's own contracts; nothing is
imported from, or delegated to, a reference implementation.

Hard boundaries
---------------

* **Retrieval is not execution.**  Selecting an action id grants nothing.  The
  router never invokes a handler (the registry holds none), never opens a
  socket, spawns a subprocess, imports MCP, calls an LLM or an embedding model,
  touches pandas/numpy, reads the filesystem, the clock, or the environment, and
  never mutates its inputs or any project state.
* **Retrieval is not evidence.**  A :class:`RouteTrace` is not a verification, a
  dataset lock, an approval, a claim, or an authorization to export.  Those
  facts are stamped ``False`` on every trace so no downstream reader can infer
  otherwise.
* **Pure and deterministic.**  A trace is a total function of the registry plus
  the request.  Ordering is stable (action id), reason codes are stable, and the
  same request always yields an identical trace and ``trace_id``.
* **Fail closed, no fallback.**  A malformed request or an unknown
  agent/purpose/connector/category/risk/output-kind raises
  :class:`RouteRequestError` — the router never guesses a "closest" action, and
  an empty selection is an honest answer, never a reason to relax a boundary.

Enforced boundaries (all four, independently)
---------------------------------------------

1. **AgentSpec allowlist** — the agent must exist, must be named in the action's
   ``allowed_agent_ids``, and must still hold the action's
   ``required_agent_tool`` grant in its own :class:`AgentSpec`.
2. **Claim ceiling** — an action may never exceed the requesting agent's
   ``max_claim_level``, and an action whose ceiling is below the task's
   ``required_claim_level`` cannot be selected to support that task.
3. **Risk / approval** — an action above the request's ``max_risk_level`` is
   rejected; an action needing approval is rejected unless the caller presents
   the matching gate as an *already granted* fact; an action needing a live
   executor is rejected unless the caller states one is available.
4. **Verification** — a task that needs a verified source or a scientifically
   eligible action cannot be served by today's unverified offline planners, and
   the router says so as an explicit capability gap rather than pretending.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..core.agent_specs import build_agent_specs
from ..core.ids import make_stable_id
from ..core.schemas import CLAIM_LEVELS
from .action_registry import (
    CATEGORIES,
    CONNECTOR_IDS,
    OUTPUT_RECORD_KINDS,
    PURPOSES,
    RISK_LEVELS,
    VERIFIED_STATUSES,
    ActionDescriptor,
    ActionRegistry,
)

# --- Bounds (fail-closed; an over-long request is malformed, never truncated) --
MAX_ID_LENGTH = 200
MAX_REQUEST_LIST_ITEMS = 64


class RouteRequestError(ValueError):
    """Raised when task facts are malformed or reference something unknown."""


# --- Stable rejection reason codes -------------------------------------------
# Callers branch on these, never on prose, so they must stay stable.
CODE_AGENT_NOT_ALLOWED = "ROUTE_AGENT_NOT_ALLOWED"
CODE_AGENT_TOOL_NOT_GRANTED = "ROUTE_AGENT_TOOL_NOT_GRANTED"
CODE_AGENT_CLAIM_CEILING_EXCEEDED = "ROUTE_AGENT_CLAIM_CEILING_EXCEEDED"
CODE_CLAIM_LEVEL_UNSUPPORTED = "ROUTE_CLAIM_LEVEL_UNSUPPORTED"
CODE_PURPOSE_MISMATCH = "ROUTE_PURPOSE_MISMATCH"
CODE_OUTPUT_KIND_MISMATCH = "ROUTE_OUTPUT_KIND_MISMATCH"
CODE_CONNECTOR_NOT_PREFERRED = "ROUTE_CONNECTOR_NOT_PREFERRED"
CODE_CATEGORY_NOT_PREFERRED = "ROUTE_CATEGORY_NOT_PREFERRED"
CODE_RISK_ABOVE_MAX = "ROUTE_RISK_ABOVE_MAX"
CODE_APPROVAL_MISSING = "ROUTE_APPROVAL_MISSING"
CODE_LIVE_EXECUTOR_UNAVAILABLE = "ROUTE_LIVE_EXECUTOR_UNAVAILABLE"
CODE_VERIFICATION_INSUFFICIENT = "ROUTE_VERIFICATION_INSUFFICIENT"
CODE_NOT_SCIENTIFIC_OUTPUT_ELIGIBLE = "ROUTE_NOT_SCIENTIFIC_OUTPUT_ELIGIBLE"

REASON_CODES = (
    CODE_AGENT_CLAIM_CEILING_EXCEEDED,
    CODE_AGENT_NOT_ALLOWED,
    CODE_AGENT_TOOL_NOT_GRANTED,
    CODE_APPROVAL_MISSING,
    CODE_CATEGORY_NOT_PREFERRED,
    CODE_CLAIM_LEVEL_UNSUPPORTED,
    CODE_CONNECTOR_NOT_PREFERRED,
    CODE_LIVE_EXECUTOR_UNAVAILABLE,
    CODE_NOT_SCIENTIFIC_OUTPUT_ELIGIBLE,
    CODE_OUTPUT_KIND_MISMATCH,
    CODE_PURPOSE_MISMATCH,
    CODE_RISK_ABOVE_MAX,
    CODE_VERIFICATION_INSUFFICIENT,
)

# --- Stable capability-gap codes ---------------------------------------------
# A gap is the router being explicit that the *project* cannot serve a need —
# as opposed to a per-action rejection.  Naming the gap is how a missing
# capability stays visible instead of being silently routed around.
GAP_NO_ACTION_FOR_PURPOSE = "GAP_NO_ACTION_FOR_PURPOSE"
GAP_NO_ACTION_FOR_OUTPUT_KIND = "GAP_NO_ACTION_FOR_OUTPUT_KIND"
GAP_NO_VERIFIED_ACTION = "GAP_NO_VERIFIED_ACTION"
GAP_NO_SCIENTIFICALLY_ELIGIBLE_ACTION = "GAP_NO_SCIENTIFICALLY_ELIGIBLE_ACTION"
GAP_CONNECTOR_INVENTORY_ONLY = "GAP_CONNECTOR_INVENTORY_ONLY"
GAP_NO_ADMISSIBLE_ACTION = "GAP_NO_ADMISSIBLE_ACTION"

CAPABILITY_GAP_CODES = (
    GAP_CONNECTOR_INVENTORY_ONLY,
    GAP_NO_ACTION_FOR_OUTPUT_KIND,
    GAP_NO_ACTION_FOR_PURPOSE,
    GAP_NO_ADMISSIBLE_ACTION,
    GAP_NO_SCIENTIFICALLY_ELIGIBLE_ACTION,
    GAP_NO_VERIFIED_ACTION,
)


@dataclass(frozen=True)
class RouteRequest:
    """Bounded task facts.  Inert data; the router never mutates it.

    ``approved_gates`` records approvals that a caller asserts were *already*
    granted elsewhere.  Presenting a gate here is a fact about the world, not a
    request for one: the router grants no approval and escalates nothing.
    """

    agent_id: str
    purpose: str
    required_output_record_kinds: tuple[str, ...] = ()
    preferred_connector_ids: tuple[str, ...] = ()
    preferred_categories: tuple[str, ...] = ()
    approved_gates: tuple[str, ...] = ()
    live_executor_available: bool = False
    requires_verified_source: bool = False
    requires_scientific_output_eligible: bool = False
    required_claim_level: str = CLAIM_LEVELS[0]
    max_risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "purpose": self.purpose,
            "required_output_record_kinds": list(self.required_output_record_kinds),
            "preferred_connector_ids": list(self.preferred_connector_ids),
            "preferred_categories": list(self.preferred_categories),
            "approved_gates": list(self.approved_gates),
            "live_executor_available": self.live_executor_available,
            "requires_verified_source": self.requires_verified_source,
            "requires_scientific_output_eligible": self.requires_scientific_output_eligible,
            "required_claim_level": self.required_claim_level,
            "max_risk_level": self.max_risk_level,
        }


@dataclass(frozen=True)
class RejectedCandidate:
    """One action that was considered and refused, with a stable reason code."""

    action_id: str
    reason_code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"action_id": self.action_id, "reason_code": self.reason_code, "detail": self.detail}


@dataclass(frozen=True)
class RouteTrace:
    """Immutable, JSON-safe record of one routing decision.

    The four ``grants_*`` / ``is_*`` facts are constants, not computed: a trace
    is *never* retrieval, execution, evidence, a dataset lock, or a claim.  They
    are stamped explicitly so an auditor reading a stored trace cannot infer
    authority that was never granted.
    """

    trace_id: str
    agent_id: str
    purpose: str
    selected_action_ids: tuple[str, ...]
    rejected: tuple[RejectedCandidate, ...]
    capability_gaps: tuple[str, ...]
    reserved_approval_gates: tuple[str, ...]
    requires_live_executor: bool
    request: RouteRequest
    notes: tuple[str, ...] = field(default_factory=tuple)

    # Invariants of this slice — retrieval implies nothing.
    is_retrieval: bool = False
    is_execution: bool = False
    is_evidence: bool = False
    grants_dataset_lock: bool = False
    grants_claim: bool = False
    grants_export_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "purpose": self.purpose,
            "selected_action_ids": list(self.selected_action_ids),
            "rejected": [r.to_dict() for r in self.rejected],
            "capability_gaps": list(self.capability_gaps),
            "reserved_approval_gates": list(self.reserved_approval_gates),
            "requires_live_executor": self.requires_live_executor,
            "request": self.request.to_dict(),
            "notes": list(self.notes),
            "is_retrieval": self.is_retrieval,
            "is_execution": self.is_execution,
            "is_evidence": self.is_evidence,
            "grants_dataset_lock": self.grants_dataset_lock,
            "grants_claim": self.grants_claim,
            "grants_export_authority": self.grants_export_authority,
        }


# --- Request validation (fail closed) ----------------------------------------


def _validate_str_tuple(value: Any, field_name: str, allowed: Sequence[str] | None) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise RouteRequestError(f"{field_name}: must be a tuple of strings")
    if len(value) > MAX_REQUEST_LIST_ITEMS:
        raise RouteRequestError(f"{field_name}: exceeds {MAX_REQUEST_LIST_ITEMS} items")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RouteRequestError(f"{field_name}: every item must be a non-empty string")
        if len(item) > MAX_ID_LENGTH:
            raise RouteRequestError(f"{field_name}: item exceeds {MAX_ID_LENGTH} characters")
        if allowed is not None and item not in allowed:
            raise RouteRequestError(f"{field_name}: unknown value {item!r}")
    return value


def validate_route_request(request: Any, agents: Mapping[str, Any]) -> RouteRequest:
    """Validate task facts; raise :class:`RouteRequestError` on anything unknown."""
    if not isinstance(request, RouteRequest):
        raise RouteRequestError("request: must be a RouteRequest")
    if not isinstance(request.agent_id, str) or not request.agent_id.strip():
        raise RouteRequestError("agent_id: must be a non-empty string")
    if request.agent_id not in agents:
        raise RouteRequestError(f"agent_id: unknown agent {request.agent_id!r}")
    if request.purpose not in PURPOSES:
        raise RouteRequestError(f"purpose: must be one of {', '.join(PURPOSES)} (got {request.purpose!r})")
    if request.max_risk_level not in RISK_LEVELS:
        raise RouteRequestError(f"max_risk_level: must be one of {', '.join(RISK_LEVELS)}")
    if request.required_claim_level not in CLAIM_LEVELS:
        raise RouteRequestError(f"required_claim_level: must be one of {', '.join(CLAIM_LEVELS)}")
    for field_name in ("live_executor_available", "requires_verified_source", "requires_scientific_output_eligible"):
        if not isinstance(getattr(request, field_name), bool):
            raise RouteRequestError(f"{field_name}: must be a bool")
    _validate_str_tuple(request.required_output_record_kinds, "required_output_record_kinds", OUTPUT_RECORD_KINDS)
    _validate_str_tuple(request.preferred_connector_ids, "preferred_connector_ids", CONNECTOR_IDS)
    _validate_str_tuple(request.preferred_categories, "preferred_categories", CATEGORIES)
    _validate_str_tuple(request.approved_gates, "approved_gates", None)
    return request


# --- Router ------------------------------------------------------------------


class ResourceRouter:
    """Pure metadata router over an :class:`ActionRegistry`.  Holds no capability."""

    def __init__(self, registry: ActionRegistry) -> None:
        if not isinstance(registry, ActionRegistry):
            raise RouteRequestError("registry: must be an ActionRegistry")
        self._registry = registry

    def route(self, request: RouteRequest) -> RouteTrace:
        """Return the deterministic :class:`RouteTrace` for these task facts."""
        agents = build_agent_specs()
        request = validate_route_request(request, agents)
        agent_spec = agents[request.agent_id]

        selected: list[str] = []
        rejected: list[RejectedCandidate] = []
        for action in sorted(self._registry.list_action_ids()):
            descriptor = self._registry.get(action)
            reason = self._reject_reason(descriptor, request, agent_spec)
            if reason is None:
                selected.append(descriptor.action_id)
            else:
                rejected.append(RejectedCandidate(descriptor.action_id, reason[0], reason[1]))

        gaps = self._capability_gaps(request, selected)
        chosen = [self._registry.get(aid) for aid in selected]
        reserved_gates = tuple(sorted({d.approval_gate for d in chosen if d.approval_gate}))
        notes = (
            "Selection is discovery metadata only: no action was executed, no data retrieved, no claim supported.",
            "Every selected action is an unverified offline query planner; a plan is not evidence.",
        )
        trace_id = make_stable_id(
            "resource_route",
            {"request": request.to_dict(), "selected": selected, "rejected": [r.to_dict() for r in rejected], "gaps": list(gaps)},
        )
        return RouteTrace(
            trace_id=trace_id,
            agent_id=request.agent_id,
            purpose=request.purpose,
            selected_action_ids=tuple(selected),
            rejected=tuple(rejected),
            capability_gaps=gaps,
            reserved_approval_gates=reserved_gates,
            requires_live_executor=any(d.requires_live_executor for d in chosen),
            request=request,
            notes=notes,
        )

    def _reject_reason(self, d: ActionDescriptor, r: RouteRequest, agent_spec: Mapping[str, Any]) -> tuple[str, str] | None:
        """First matching rejection (code, detail), or ``None`` if admissible.

        Order matters only for which single reason is reported; every check is
        independent and each one alone is sufficient to refuse.
        """
        # 1. AgentSpec allowlist — membership *and* the underlying tool grant.
        if r.agent_id not in d.allowed_agent_ids:
            return (CODE_AGENT_NOT_ALLOWED, f"agent {r.agent_id!r} is not in this action's allowlist")
        if d.required_agent_tool not in agent_spec["allowed_tools"]:
            return (CODE_AGENT_TOOL_NOT_GRANTED, f"agent {r.agent_id!r} does not hold tool grant {d.required_agent_tool!r}")

        # 2. Claim ceilings, in both directions.
        if CLAIM_LEVELS.index(d.max_claim_level) > CLAIM_LEVELS.index(agent_spec["max_claim_level"]):
            return (CODE_AGENT_CLAIM_CEILING_EXCEEDED, f"action ceiling {d.max_claim_level!r} exceeds the agent's ceiling")
        if CLAIM_LEVELS.index(d.max_claim_level) < CLAIM_LEVELS.index(r.required_claim_level):
            return (CODE_CLAIM_LEVEL_UNSUPPORTED, f"action ceiling {d.max_claim_level!r} cannot support required {r.required_claim_level!r}")

        # 3. Purpose / modality / preferences.
        if r.purpose not in d.compatible_purposes:
            return (CODE_PURPOSE_MISMATCH, f"action does not declare purpose {r.purpose!r}")
        if r.required_output_record_kinds and d.output_record_kind not in r.required_output_record_kinds:
            return (CODE_OUTPUT_KIND_MISMATCH, f"action yields {d.output_record_kind!r}, not a required kind")
        if r.preferred_connector_ids and d.connector_id not in r.preferred_connector_ids:
            return (CODE_CONNECTOR_NOT_PREFERRED, f"connector {d.connector_id!r} is not among the preferred connectors")
        if r.preferred_categories and d.category not in r.preferred_categories:
            return (CODE_CATEGORY_NOT_PREFERRED, f"category {d.category!r} is not among the preferred categories")

        # 4. Risk / approval / live-executor facts.
        if RISK_LEVELS.index(d.risk_level) > RISK_LEVELS.index(r.max_risk_level):
            return (CODE_RISK_ABOVE_MAX, f"risk {d.risk_level!r} exceeds the request ceiling {r.max_risk_level!r}")
        if d.requires_approval and d.approval_gate not in r.approved_gates:
            return (CODE_APPROVAL_MISSING, f"approval gate {d.approval_gate!r} has not been granted")
        if d.requires_live_executor and not r.live_executor_available:
            return (CODE_LIVE_EXECUTOR_UNAVAILABLE, "action needs a live executor, which the request states is unavailable")

        # 5. Verification / scientific-eligibility boundaries.
        if r.requires_verified_source and d.verification_status not in VERIFIED_STATUSES:
            return (CODE_VERIFICATION_INSUFFICIENT, f"verification status {d.verification_status!r} does not meet the requirement")
        if r.requires_scientific_output_eligible and not d.scientific_output_eligible:
            return (CODE_NOT_SCIENTIFIC_OUTPUT_ELIGIBLE, "action output is not eligible to back a scientific claim")
        return None

    def _capability_gaps(self, r: RouteRequest, selected: Sequence[str]) -> tuple[str, ...]:
        """Name what the project genuinely cannot do for this request."""
        gaps: set[str] = set()
        all_actions = [self._registry.get(aid) for aid in self._registry.list_action_ids()]

        if not any(r.purpose in a.compatible_purposes for a in all_actions):
            gaps.add(GAP_NO_ACTION_FOR_PURPOSE)
        if r.required_output_record_kinds and not any(a.output_record_kind in r.required_output_record_kinds for a in all_actions):
            gaps.add(GAP_NO_ACTION_FOR_OUTPUT_KIND)
        if r.requires_verified_source and not any(a.verification_status in VERIFIED_STATUSES for a in all_actions):
            gaps.add(GAP_NO_VERIFIED_ACTION)
        if r.requires_scientific_output_eligible and not any(a.scientific_output_eligible for a in all_actions):
            gaps.add(GAP_NO_SCIENTIFICALLY_ELIGIBLE_ACTION)
        for connector_id in r.preferred_connector_ids:
            if not self._registry.connector_action_ids(connector_id):
                gaps.add(GAP_CONNECTOR_INVENTORY_ONLY)
        if not selected:
            gaps.add(GAP_NO_ADMISSIBLE_ACTION)
        return tuple(sorted(gaps))


def build_default_resource_router(registry: ActionRegistry | None = None) -> ResourceRouter:
    """Return a router over the default registry (the 12 offline planners)."""
    if registry is None:
        from .action_registry import build_default_action_registry

        registry = build_default_action_registry()
    return ResourceRouter(registry)


def route_actions(registry: ActionRegistry, request: RouteRequest) -> RouteTrace:
    """Convenience one-shot: route ``request`` against ``registry``."""
    return ResourceRouter(registry).route(request)


__all__: Iterable[str] = (
    "CAPABILITY_GAP_CODES",
    "REASON_CODES",
    "RejectedCandidate",
    "ResourceRouter",
    "RouteRequest",
    "RouteRequestError",
    "RouteTrace",
    "build_default_resource_router",
    "route_actions",
    "validate_route_request",
)
