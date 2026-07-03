"""Local deterministic Evidence Planning command contract (WP-07 / T-07-06..08).

The first *local/offline* planning slice.  Where the intake slices
(:mod:`auto_bioinfo.intake.scope_resolver` and its siblings) answer *"what inert
draft can a deterministic offline resolver propose from the explicit facts?"*,
this module answers the next bounded question — *"given one inert draft
``SubQuestion`` (and optionally its parent ``ResearchSpec`` for the claim
ceiling), what inert ``EvidencePlan`` projection — evidence axes, a capped claim
level, a minimum-replication descriptor, and, crucially, a **negative** and a
**conflicting** evidence strategy plus a legal fallback/stop exit — can a
deterministic offline planner draft from the sub-question's **explicit** evidence
intent alone?"* — **before any real dataset/literature search, ontology
resolution, approval grant, event emission, or execution path can start**.

It is the local/offline slice of T-07-06, T-07-07 and T-07-08 only.  The
architecture's "evidence planner" is realised here as a *deterministic in-process
offline component* over a tiny, public, clearly-synthetic mapping from a generic
evidence-intent token to generic evidence-axis descriptors: it is "rules first",
claims **no** authority, names **no** real dataset / database / accession / PMID /
DOI, and a real planning service, if ever used later, would only *suggest* — none
is used or authorised here.

Design constraints (WP-07), mirroring the intake contract style:

- **Pure and deterministic.** :func:`plan_evidence` and every helper is a total
  function of its explicit in-memory inputs.  There is no I/O whatsoever: no file
  access, no network/socket, no environment/credential inspection, **no clock
  read**, no LLM / provider / model / SDK / tool / ontology / search call, no
  content egress, no subprocess, no threads, scheduler, queue, outbox, DB, event,
  audit log, report/index/cache, or any process side effect.  Inputs are never
  mutated in place.  A produced ``EvidencePlan`` projection carries an empty
  ``created_at`` (no wall-clock timestamp), so byte-identical inputs always yield a
  byte-identical result.
- **No-guess planning, no positive-only plan.** Evidence axes are derived **only**
  from the sub-question's explicit ``evidence_type`` / ``purpose`` (or a
  caller-supplied, equally-synthetic directive); a sub-question stating no evidence
  intent yields ``missing_required_field`` rather than a fabricated axis.  A plan
  that would define **only** positive evidence — missing a negative *or* a
  conflicting-evidence strategy — is rejected (``positive_only_rejected``); a plan
  with no stop condition and no legal fallback exit is rejected
  (``no_stop_condition``).  Every required field must have explicit content.
- **Inert, non-authoritative result only.** The outcome is reviewable data: a
  bounded :class:`EvidencePlanResult` carrying an in-memory ``EvidencePlan`` *draft*
  projection (``status == "draft"``).  It is **never** persisted, versioned, emitted
  as an event, enqueued, sent to a human or an external service, marked
  authoritative, or treated as an approval or a grant to execute.  It names no real
  data source of any kind.
- **Bounded vocabulary.** The status is one of exactly five values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.

This module defines a *command contract* only.  It does not search any dataset /
literature / API, resolve any ontology, persist or version an ``EvidencePlan``,
run an Approval lifecycle, emit an event, run any pipeline stage transition, or
perform scientific analysis — those remain out of scope for T-07-06..08.  An
``evidence_plan_drafted`` result is an inert reviewable projection, never a grant
to execute.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core import common
from ..core.ids import normalize_id_text
from ..core.schemas import CLAIM_LEVELS, EvidencePlan, ResearchSpec, SubQuestion
from ..core.validation import validate_evidence_plan

# --- Bounded result statuses -------------------------------------------------
# Exactly five.  ``evidence_plan_drafted`` is the single proceed-with-data outcome
# (an inert ``EvidencePlan`` draft projection).  The other four are fail-closed
# outcomes, none of which produce a plan.
STATUS_EVIDENCE_PLAN_DRAFTED = "evidence_plan_drafted"
STATUS_POSITIVE_ONLY_REJECTED = "positive_only_rejected"
STATUS_MISSING_REQUIRED_FIELD = "missing_required_field"
STATUS_NO_STOP_CONDITION = "no_stop_condition"
STATUS_REJECTED_MALFORMED = "rejected_malformed"

STATUSES = (
    STATUS_EVIDENCE_PLAN_DRAFTED,
    STATUS_POSITIVE_ONLY_REJECTED,
    STATUS_MISSING_REQUIRED_FIELD,
    STATUS_NO_STOP_CONDITION,
    STATUS_REJECTED_MALFORMED,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# evidence_plan_drafted:
CODE_EVIDENCE_PLAN_DRAFTED = "EVIDENCE_PLAN_DRAFTED"
# positive_only_rejected (T-07-07: a plan defining only positive evidence, i.e.
# missing a negative and/or a conflicting-evidence strategy, is not allowed):
CODE_POSITIVE_ONLY_REJECTED = "EVIDENCE_POSITIVE_ONLY_REJECTED"
# missing_required_field (T-07-06: a required plan field has no explicit content):
CODE_MISSING_EVIDENCE_AXIS = "EVIDENCE_MISSING_AXIS"
CODE_MISSING_REQUIRED_FIELD = "EVIDENCE_MISSING_REQUIRED_FIELD"
# no_stop_condition (T-07-08: no stop condition / no legal fallback exit):
CODE_NO_STOP_CONDITION = "EVIDENCE_NO_STOP_CONDITION"
# rejected_malformed (fail closed on a malformed sub-question / spec / directive):
CODE_SUBQUESTION_MALFORMED = "EVIDENCE_SUBQUESTION_MALFORMED"
CODE_SPEC_MALFORMED = "EVIDENCE_SPEC_MALFORMED"
CODE_CLAIM_LEVEL_MALFORMED = "EVIDENCE_CLAIM_LEVEL_MALFORMED"
CODE_DIRECTIVE_MALFORMED = "EVIDENCE_DIRECTIVE_MALFORMED"
CODE_PLAN_INVALID = "EVIDENCE_PLAN_INVALID"

REASON_CODES = (
    CODE_EVIDENCE_PLAN_DRAFTED,
    CODE_POSITIVE_ONLY_REJECTED,
    CODE_MISSING_EVIDENCE_AXIS,
    CODE_MISSING_REQUIRED_FIELD,
    CODE_NO_STOP_CONDITION,
    CODE_SUBQUESTION_MALFORMED,
    CODE_SPEC_MALFORMED,
    CODE_CLAIM_LEVEL_MALFORMED,
    CODE_DIRECTIVE_MALFORMED,
    CODE_PLAN_INVALID,
)

# The status each reason code resolves to, so a future adapter can map a code to a
# status without re-deriving it.
_CODE_STATUS = {
    CODE_EVIDENCE_PLAN_DRAFTED: STATUS_EVIDENCE_PLAN_DRAFTED,
    CODE_POSITIVE_ONLY_REJECTED: STATUS_POSITIVE_ONLY_REJECTED,
    CODE_MISSING_EVIDENCE_AXIS: STATUS_MISSING_REQUIRED_FIELD,
    CODE_MISSING_REQUIRED_FIELD: STATUS_MISSING_REQUIRED_FIELD,
    CODE_NO_STOP_CONDITION: STATUS_NO_STOP_CONDITION,
    CODE_SUBQUESTION_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_SPEC_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_CLAIM_LEVEL_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_DIRECTIVE_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_PLAN_INVALID: STATUS_REJECTED_MALFORMED,
}

# The single status the produced plan carries; the command may never produce a
# locked/authoritative evidence plan.
DRAFT_STATUS = "draft"

# The most restrictive claim level; the fallback route downgrades to this.
_FLOOR_CLAIM_LEVEL = CLAIM_LEVELS[0]

# --- Tiny synthetic, offline evidence-intent vocabulary ----------------------
# PUBLIC, TEST-ONLY, NON-SENSITIVE, SYNTHETIC.  This is NOT a catalogue of real
# datasets/databases and carries NO real identifiers.  It maps a *generic evidence
# intent token* the sub-question already stated (e.g. "transcriptomic") onto one or
# more *generic evidence-axis descriptors* (e.g. "transcriptomic_differential").
# The axes name evidence TYPES / analysis axes only — never a real dataset,
# accession, PMID, or DOI.  An unrecognised-but-non-empty intent is normalised to a
# single generic axis rather than dropped or invented; only a wholly absent intent
# fails closed.  A caller may pass its own equally-synthetic axes via a directive.
SYNTHETIC_EVIDENCE_AXES: dict[str, tuple[str, ...]] = {
    "transcriptomic": ("transcriptomic_differential", "transcriptomic_baseline"),
    "expression": ("transcriptomic_differential", "transcriptomic_baseline"),
    "differential_expression": ("transcriptomic_differential",),
    "coexpression": ("coexpression_network",),
    "co_expression": ("coexpression_network",),
    "genomic": ("genomic_variant_association",),
    "variant": ("genomic_variant_association",),
    "proteomic": ("proteomic_abundance",),
    "epigenomic": ("epigenomic_regulatory",),
    "association": ("statistical_association",),
    "literature": ("literature_corroboration",),
}

# Generic, dataset-free default strategy descriptors.  These are analysis-strategy
# axes, not real sources.
_DEFAULT_NEGATIVE_STRATEGY = "seek_and_report_absence_of_effect_as_informative_negative_evidence"
_DEFAULT_CONFLICTING_STRATEGY = "record_conflicting_findings_and_hold_claim_pending_reconciliation"


@dataclass(frozen=True)
class _PlanFacts:
    """The explicit, already-extracted planning facts (never inferred)."""

    research_spec_id: str
    subquestion_id: str
    evidence_type: str
    purpose: str
    subquestion_claim_ceiling: str


@dataclass(frozen=True)
class EvidencePlanResult:
    """The deterministic, reason-coded outcome of an Evidence Planning command.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  The single proceed outcome (``evidence_plan_drafted``)
    carries an ``evidence_plan`` draft projection; every fail-closed outcome carries
    ``None``.  ``negative_evidence_strategy``, ``conflicting_evidence_strategy`` and
    ``fallback_route`` are surfaced explicitly (in addition to being embedded in the
    plan) so a caller can confirm the T-07-07 / T-07-08 guarantees on a drafted plan
    without re-parsing it.  ``binding`` records the exact facts considered so the
    decision can be audited.  The result is inert reviewable data: it is never
    persisted, versioned, emitted, sent out, marked authoritative, or treated as
    authorization.
    """

    status: str
    reason_code: str
    message: str
    evidence_plan: dict[str, Any] | None = None
    negative_evidence_strategy: str = ""
    conflicting_evidence_strategy: str = ""
    fallback_route: str = ""
    subquestion: dict[str, Any] | None = None
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def plan_drafted(self) -> bool:
        """The single proceed-with-data outcome (an inert ``EvidencePlan`` draft)."""
        return self.status == STATUS_EVIDENCE_PLAN_DRAFTED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the result (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "plan_drafted": self.plan_drafted,
            "evidence_plan": copy.deepcopy(self.evidence_plan) if self.evidence_plan is not None else None,
            "negative_evidence_strategy": self.negative_evidence_strategy,
            "conflicting_evidence_strategy": self.conflicting_evidence_strategy,
            "fallback_route": self.fallback_route,
            "subquestion": copy.deepcopy(self.subquestion) if self.subquestion is not None else None,
            "binding": copy.deepcopy(self.binding),
        }


def _subquestion_dict(subquestion: Any) -> dict[str, Any] | None:
    """Return a draft ``SubQuestion`` projection for an accepted shape, else ``None``.

    Accepts a :class:`SubQuestion` or a mapping projection of one; the value is only
    read, never mutated.
    """
    if isinstance(subquestion, SubQuestion):
        return subquestion.to_dict()
    if isinstance(subquestion, Mapping):
        return dict(subquestion)
    return None


def _spec_ceiling(spec: Any) -> tuple[str | None, str | None]:
    """Return ``(ceiling, error)`` — the parent claim ceiling from an optional spec.

    ``None`` spec means no parent cap.  A :class:`ResearchSpec` or a mapping
    projection contributes its ``claim_ceiling`` (falling back to ``max_claim_level``);
    an invalid claim level fails closed.  Any other type is malformed.
    """
    if spec is None:
        return (None, None)
    if isinstance(spec, ResearchSpec):
        spec_dict: Mapping[str, Any] = spec.to_dict()
    elif isinstance(spec, Mapping):
        spec_dict = spec
    else:
        return (None, CODE_SPEC_MALFORMED)
    ceiling = spec_dict.get("claim_ceiling") or spec_dict.get("max_claim_level")
    if ceiling is None:
        return (None, None)
    if ceiling not in CLAIM_LEVELS:
        return (None, CODE_CLAIM_LEVEL_MALFORMED)
    return (str(ceiling), None)


def _cap_claim_level(subquestion_ceiling: str, spec_ceiling: str | None) -> str:
    """The most restrictive of the sub-question and parent-spec claim ceilings."""
    candidates = [subquestion_ceiling]
    if spec_ceiling is not None:
        candidates.append(spec_ceiling)
    return min(candidates, key=CLAIM_LEVELS.index)


def _derive_axes(evidence_type: str, purpose: str) -> list[str]:
    """Derive generic evidence-axis descriptors from the explicit intent only.

    A recognised intent maps to the synthetic axis descriptors; an unrecognised but
    non-empty intent is normalised to one generic descriptor; a wholly empty intent
    yields no axis (the caller then fails closed).  Nothing is invented and no real
    dataset is ever named.
    """
    for token in (evidence_type, purpose):
        key = normalize_id_text(token)
        if not key:
            continue
        if key in SYNTHETIC_EVIDENCE_AXES:
            return list(SYNTHETIC_EVIDENCE_AXES[key])
        return [f"{key}_evidence"]
    return []


def _default_minimum_replication() -> dict[str, Any]:
    """A generic, dataset-free minimum-replication descriptor."""
    return {
        "minimum_independent_sources": 2,
        "requirement": "at_least_two_independent_evidence_axes_or_sources_before_claim_is_upheld",
        "descriptor_only": True,
    }


def _stop_conditions_and_fallback(subquestion_id: str) -> tuple[list[str], str]:
    """Generic stop conditions plus the legal fallback exit (T-07-08).

    The fallback route is a legal exit for the "data insufficient" case: downgrade
    the claim to the floor level, and if there is no usable evidence at all mark the
    sub-question not-answerable.  Both are generic descriptors, never a real action.
    """
    fallback = f"insufficient_evidence -> downgrade_claim_to_{_FLOOR_CLAIM_LEVEL}; no_usable_evidence -> mark_subquestion_not_answerable"
    stop_conditions = [
        f"insufficient_evidence_for_planned_axes -> downgrade_claim_to_{_FLOOR_CLAIM_LEVEL}",
        "no_usable_evidence_axis -> mark_subquestion_not_answerable_and_stop",
        "conflicting_evidence_unreconcilable -> hold_claim_and_escalate_for_human_review",
    ]
    return (stop_conditions, fallback)


def _plan_content_from_directive(directive: Mapping[str, Any], facts: _PlanFacts) -> dict[str, Any]:
    """Read plan content from a caller-supplied, equally-synthetic directive.

    A directive lets a caller express exactly what the plan should contain so the
    fail-closed guarantees (positive-only, no-stop-condition, missing-field) can be
    exercised without a network or model.  Absent keys fall back to the deterministic
    default content; explicitly-blank keys are honoured verbatim (that is how a
    caller expresses e.g. a forbidden positive-only plan).  A directive never names a
    real dataset.
    """
    axes = directive.get("evidence_axes")
    if not isinstance(axes, list):
        axes = _derive_axes(facts.evidence_type, facts.purpose)
    negative = directive.get("negative_evidence_strategy", _DEFAULT_NEGATIVE_STRATEGY)
    conflicting = directive.get("conflicting_evidence_strategy", _DEFAULT_CONFLICTING_STRATEGY)
    default_stops, default_fallback = _stop_conditions_and_fallback(facts.subquestion_id)
    stop_conditions = directive.get("stop_conditions")
    if not isinstance(stop_conditions, list):
        stop_conditions = default_stops
    fallback = directive.get("fallback_route", default_fallback)
    minimum_replication = directive.get("minimum_replication")
    if not isinstance(minimum_replication, dict):
        minimum_replication = _default_minimum_replication()
    planned_gaps = directive.get("planned_gaps")
    if not isinstance(planned_gaps, list):
        planned_gaps = []
    return {
        "evidence_axes": [str(a) for a in axes],
        "negative_evidence_strategy": str(negative or ""),
        "conflicting_evidence_strategy": str(conflicting or ""),
        "stop_conditions": [str(s) for s in stop_conditions],
        "fallback_route": str(fallback or ""),
        "minimum_replication": dict(minimum_replication),
        "planned_gaps": [str(g) for g in planned_gaps],
    }


def _plan_content_default(facts: _PlanFacts) -> dict[str, Any]:
    """The deterministic complete plan content synthesised from the explicit facts."""
    stop_conditions, fallback = _stop_conditions_and_fallback(facts.subquestion_id)
    return {
        "evidence_axes": _derive_axes(facts.evidence_type, facts.purpose),
        "negative_evidence_strategy": _DEFAULT_NEGATIVE_STRATEGY,
        "conflicting_evidence_strategy": _DEFAULT_CONFLICTING_STRATEGY,
        "stop_conditions": stop_conditions,
        "fallback_route": fallback,
        "minimum_replication": _default_minimum_replication(),
        "planned_gaps": [],
    }


def plan_evidence(subquestion: Any, spec: Any = None, *, directive: Mapping[str, Any] | None = None) -> EvidencePlanResult:
    """Run the local/offline Evidence Planning command, fail-closed.

    A pure, deterministic function returning a bounded :class:`EvidencePlanResult`
    (it never raises for a domain condition, never mutates its inputs, and performs
    no I/O, clock read, LLM/provider/ontology/search call, persistence, event
    emission, approval grant, or content egress).

    ``subquestion`` is a :class:`SubQuestion` or a mapping projection of one; ``spec``
    is an optional parent :class:`ResearchSpec` / mapping supplying the claim ceiling.
    ``directive`` is an optional caller-supplied, equally-synthetic mapping expressing
    the intended plan content (used to exercise the fail-closed guarantees); when
    omitted the planner synthesises a complete default plan from the explicit facts.

    Order of gates (each fails closed, in order):

    1. **Sub-question / spec / directive shape** — a malformed input →
       ``rejected_malformed``.
    2. **Explicit evidence axis** (T-07-06) — no derivable evidence axis →
       ``missing_required_field``.
    3. **Required fields** (T-07-06) — a blank ``minimum_replication`` /
       ``max_claim_level`` / ``subquestion_ids`` →  ``missing_required_field``.
    4. **Negative + conflicting strategy** (T-07-07) — a plan defining only positive
       evidence → ``positive_only_rejected``.
    5. **Stop condition + fallback** (T-07-08) — no stop condition and no legal
       fallback exit → ``no_stop_condition``.
    6. Otherwise build the inert ``EvidencePlan`` draft (``evidence_plan_drafted``);
       a self-produced plan that fails :func:`validate_evidence_plan` fails closed.
    """
    binding: dict[str, Any] = {
        "subquestion_kind": type(subquestion).__name__,
        "spec_kind": type(spec).__name__,
        "directive_kind": type(directive).__name__,
    }

    def _result(
        code: str,
        message: str,
        *,
        evidence_plan: dict[str, Any] | None = None,
        negative_evidence_strategy: str = "",
        conflicting_evidence_strategy: str = "",
        fallback_route: str = "",
        subquestion_dict: dict[str, Any] | None = None,
    ) -> EvidencePlanResult:
        return EvidencePlanResult(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            evidence_plan=evidence_plan,
            negative_evidence_strategy=negative_evidence_strategy,
            conflicting_evidence_strategy=conflicting_evidence_strategy,
            fallback_route=fallback_route,
            subquestion=subquestion_dict,
            binding=dict(binding),
        )

    # 1. Sub-question shape.
    subquestion_dict = _subquestion_dict(subquestion)
    if subquestion_dict is None:
        return _result(CODE_SUBQUESTION_MALFORMED, f"subquestion must be a SubQuestion or a mapping, not {type(subquestion).__name__}")

    research_spec_id = subquestion_dict.get("research_spec_id", "")
    if common.validate_identifier(research_spec_id, "research_spec_id"):
        return _result(
            CODE_SUBQUESTION_MALFORMED, "subquestion is missing a valid research_spec_id; cannot anchor an evidence plan", subquestion_dict=subquestion_dict
        )

    subquestion_id = subquestion_dict.get("subquestion_id", "")
    if not isinstance(subquestion_id, str) or not subquestion_id.strip():
        # A mapping projection may omit the derived id; synthesise the plan without a
        # link only if a valid id is present, else fail closed (the link is required).
        return _result(CODE_SUBQUESTION_MALFORMED, "subquestion is missing a subquestion_id to link the plan back to", subquestion_dict=subquestion_dict)

    subquestion_ceiling = subquestion_dict.get("claim_ceiling", "association")
    if subquestion_ceiling not in CLAIM_LEVELS:
        return _result(
            CODE_CLAIM_LEVEL_MALFORMED,
            f"subquestion claim_ceiling {subquestion_ceiling!r} is not a valid claim level",
            subquestion_dict=subquestion_dict,
        )

    # Spec ceiling (optional parent cap).
    spec_ceiling, spec_error = _spec_ceiling(spec)
    if spec_error is not None:
        message = "spec is not a ResearchSpec or a mapping" if spec_error == CODE_SPEC_MALFORMED else "spec claim ceiling is not a valid claim level"
        return _result(spec_error, message, subquestion_dict=subquestion_dict)

    # Directive shape (optional).
    if directive is not None and not isinstance(directive, Mapping):
        return _result(CODE_DIRECTIVE_MALFORMED, f"directive must be a mapping, not {type(directive).__name__}", subquestion_dict=subquestion_dict)

    facts = _PlanFacts(
        research_spec_id=str(research_spec_id),
        subquestion_id=str(subquestion_id).strip(),
        evidence_type=str(subquestion_dict.get("evidence_type", "") or ""),
        purpose=str(subquestion_dict.get("purpose", "") or ""),
        subquestion_claim_ceiling=str(subquestion_ceiling),
    )
    max_claim_level = _cap_claim_level(facts.subquestion_claim_ceiling, spec_ceiling)

    content = _plan_content_from_directive(directive, facts) if directive is not None else _plan_content_default(facts)

    binding["research_spec_id"] = facts.research_spec_id
    binding["subquestion_id"] = facts.subquestion_id
    binding["evidence_type"] = facts.evidence_type
    binding["subquestion_claim_ceiling"] = facts.subquestion_claim_ceiling
    binding["spec_claim_ceiling"] = spec_ceiling
    binding["max_claim_level"] = max_claim_level
    binding["evidence_axes"] = list(content["evidence_axes"])

    negative = content["negative_evidence_strategy"]
    conflicting = content["conflicting_evidence_strategy"]
    fallback = content["fallback_route"]
    stop_conditions = [s for s in content["stop_conditions"] if s.strip()]

    # 2. Explicit evidence axis (T-07-06): at least one derivable axis.
    axes = [a for a in content["evidence_axes"] if a.strip()]
    if not axes:
        return _result(
            CODE_MISSING_EVIDENCE_AXIS,
            "subquestion states no explicit evidence_type/purpose and no directive axis; no evidence axis could be derived",
            subquestion_dict=subquestion_dict,
        )

    # 3. Required fields (T-07-06): explicit minimum_replication + a valid claim level.
    if not isinstance(content["minimum_replication"], dict) or not content["minimum_replication"]:
        return _result(CODE_MISSING_REQUIRED_FIELD, "evidence plan is missing an explicit minimum_replication descriptor", subquestion_dict=subquestion_dict)
    if max_claim_level not in CLAIM_LEVELS:
        return _result(CODE_MISSING_REQUIRED_FIELD, "evidence plan has no valid max_claim_level", subquestion_dict=subquestion_dict)

    # 4. Negative + conflicting strategy (T-07-07): a positive-only plan is rejected.
    if not negative.strip() or not conflicting.strip():
        return _result(
            CODE_POSITIVE_ONLY_REJECTED,
            "evidence plan defines only positive evidence; a negative AND a conflicting-evidence strategy are both required",
            subquestion_dict=subquestion_dict,
        )

    # 5. Stop condition + fallback (T-07-08): a legal exit is required.
    if not stop_conditions and not fallback.strip():
        return _result(
            CODE_NO_STOP_CONDITION,
            "evidence plan has no stop condition and no legal fallback exit for the data-insufficient case",
            subquestion_dict=subquestion_dict,
        )

    # The conflicting-evidence strategy and the fallback route are recorded inside
    # the plan's planned_gaps / stop_conditions (the EvidencePlan schema has no
    # dedicated field), so the T-07-07 / T-07-08 guarantees survive serialisation.
    planned_gaps = list(content["planned_gaps"])
    conflicting_gap = f"conflicting_evidence_strategy: {conflicting}"
    if conflicting_gap not in planned_gaps:
        planned_gaps.append(conflicting_gap)
    plan_stop_conditions = list(stop_conditions)
    fallback_entry = f"fallback_route: {fallback}"
    if fallback.strip() and fallback_entry not in plan_stop_conditions:
        plan_stop_conditions.append(fallback_entry)

    plan = EvidencePlan(
        research_spec_id=facts.research_spec_id,
        evidence_axes=list(axes),
        max_claim_level=max_claim_level,
        subquestion_ids=[facts.subquestion_id],
        planned_gaps=planned_gaps,
        stop_conditions=plan_stop_conditions,
        minimum_replication=dict(content["minimum_replication"]),
        negative_evidence_strategy=negative,
        status=DRAFT_STATUS,
        created_at="",  # inert, deterministic — no wall-clock timestamp
    ).to_dict()

    # 6. Defensive self-check: a self-produced plan must be internally valid.
    errors = validate_evidence_plan(plan)
    if errors:
        return _result(CODE_PLAN_INVALID, "offline planner produced an invalid evidence plan: " + "; ".join(errors), subquestion_dict=subquestion_dict)

    binding["evidence_plan_id"] = plan.get("evidence_plan_id")
    return _result(
        CODE_EVIDENCE_PLAN_DRAFTED,
        "offline planner produced an inert evidence-plan draft with a negative + conflicting strategy and a legal fallback exit",
        evidence_plan=plan,
        negative_evidence_strategy=negative,
        conflicting_evidence_strategy=conflicting,
        fallback_route=fallback,
        subquestion_dict=subquestion_dict,
    )


__all__ = [
    "STATUS_EVIDENCE_PLAN_DRAFTED",
    "STATUS_POSITIVE_ONLY_REJECTED",
    "STATUS_MISSING_REQUIRED_FIELD",
    "STATUS_NO_STOP_CONDITION",
    "STATUS_REJECTED_MALFORMED",
    "STATUSES",
    "CODE_EVIDENCE_PLAN_DRAFTED",
    "CODE_POSITIVE_ONLY_REJECTED",
    "CODE_MISSING_EVIDENCE_AXIS",
    "CODE_MISSING_REQUIRED_FIELD",
    "CODE_NO_STOP_CONDITION",
    "CODE_SUBQUESTION_MALFORMED",
    "CODE_SPEC_MALFORMED",
    "CODE_CLAIM_LEVEL_MALFORMED",
    "CODE_DIRECTIVE_MALFORMED",
    "CODE_PLAN_INVALID",
    "REASON_CODES",
    "DRAFT_STATUS",
    "SYNTHETIC_EVIDENCE_AXES",
    "EvidencePlanResult",
    "plan_evidence",
]
