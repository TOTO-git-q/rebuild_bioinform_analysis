"""Local deterministic Scope Resolver preflight command contract (WP-06e / T-06-05).

The fifth *local* intake slice.  Where
:mod:`auto_bioinfo.intake.support_scope` (WP-06a) answers *"is this request
something this system may even attempt to plan?"*,
:mod:`auto_bioinfo.intake.multi_question` (WP-06b) answers *"does this single
request bundle more than one research question?"*,
:mod:`auto_bioinfo.intake.policy_builder` (WP-06c) answers *"what is the initial
governance policy, and when must a human decide first?"*, and
:mod:`auto_bioinfo.intake.question_normalizer` (WP-06d) answers *"what inert
``ResearchSpec`` draft can a deterministic offline normalizer produce?"*, this
module answers the next bounded question — *"given an inert draft and a usable
policy, what inert ``ScopeBundle`` projection (species/tissue/condition/comparison
axes) can a deterministic offline resolver propose from the **explicit** facts
alone, and what remains an open ambiguity?"* — **before any real ontology
resolution, dataset/literature search, approval grant, event emission, or
execution path can start**.

It is the local/offline slice of T-06-05 only.  The architecture's "Scope
Resolver / Ontology adapter call" is realised here as a *deterministic in-process
fake/offline component* (:class:`OfflineScopeResolverAdapter`) over a tiny,
public, clearly-synthetic fixture vocabulary: it is "rules first", claims **no**
real ontology authority, mints **no** real ontology identifiers, and a real
ontology service / provider / search API, if ever used later, would only
*suggest* — none is used or authorised here.

Design constraints (WP-06e), mirroring the WP-06a/06b/06c/06d contract style:

- **Pure and deterministic.** :func:`resolve_scope`, the offline resolver, and
  every helper is a total function of its explicit in-memory inputs.  There is no
  I/O whatsoever: no file access, no network/socket, no environment/credential
  inspection, **no real clock read**, no LLM / provider / model / SDK / tool /
  ontology / search call, no content egress, no subprocess, no threads, scheduler,
  queue, outbox, DB, event, audit log, report/index/cache, or any process side
  effect.  Inputs are never mutated in place.  Produced ``ScopeBundle`` /
  ``AmbiguityReport`` projections carry an empty ``created_at`` (no wall-clock
  timestamp), so byte-identical inputs always yield a byte-identical result.
- **Reuse the upstream intake gates.** :func:`resolve_scope` preserves every
  WP-06a/06b/06c/06d gate.  When handed a :class:`QuestionNormalizationResult`, a
  non-``draft_created`` upstream outcome (support-scope stop, multi-question /
  needs-clarification, missing / approval-needed policy, malformed) is carried
  through verbatim as the corresponding scope-resolution stop and produces **no**
  scope bundle.  When handed a bare draft ``ResearchSpec`` it re-runs
  :func:`assess_intake` (support scope + multi-question) and the policy gate as
  defence in depth, so a stop / pause / approval / malformed input still fails
  closed here.
- **No-guess resolution.** A scope axis is populated **only** from facts the
  draft explicitly states (an explicitly named organism / comparison group /
  tissue / condition) or that the tiny synthetic fixture vocabulary explicitly
  recognises.  Every unknown organism / tissue / condition / comparison fact stays
  an empty field **and** an ``open`` :class:`AmbiguityReport` item — it is never
  silently inferred, defaulted, or invented.  A draft with **no** explicit usable
  scope fact yields ``needs_clarification`` (the ambiguity stays open), not a
  fabricated bundle.
- **Inert, non-authoritative result only.** The outcome is reviewable data: a
  bounded :class:`ScopeResolutionResult` carrying an in-memory ``ScopeBundle``
  *draft* projection (``status == "draft"``) and an in-memory ``AmbiguityReport``
  *draft* projection (``status == "draft"``) of the open unknowns.  It is **never**
  persisted, versioned, emitted as an event, enqueued, sent to a human or an
  external service, marked authoritative, assigned a real ontology id, treated as
  an approval, or used to unblock any downstream workflow or pipeline stage.  It
  creates no child project and splits nothing.
- **Bounded vocabulary.** The status is one of exactly six values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.

This module defines a *command contract* only.  It does not call a real ontology
service, search any dataset / literature / API, persist or version a
``ScopeBundle`` / ``AmbiguityReport``, run an Approval lifecycle, emit an event,
create a child project, run any pipeline stage transition, or perform scientific
analysis — those remain out of scope for T-06-05 (see WP-06f+ / T-06-06+).  A
``scope_draft_created`` result is an inert reviewable projection, never a grant to
execute.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.schemas import AmbiguityReport, ResearchSpec, ScopeBundle
from ..core.validation import (
    validate_ambiguity_report,
    validate_project_policy,
    validate_scope_bundle,
)
from .multi_question import IntakeAssessment, assess_intake
from .policy_builder import PERMITTED_EXECUTION_MODES, PolicyBuildOutcome
from .question_normalizer import (
    CODE_MULTI_QUESTION_REQUIRES_REVIEW as NORMALIZE_CODE_MULTI_QUESTION,
)
from .question_normalizer import (
    CODE_POLICY_APPROVAL_NEEDED as NORMALIZE_CODE_POLICY_APPROVAL_NEEDED,
)
from .question_normalizer import (
    STATUS_APPROVAL_NEEDED as NORMALIZE_STATUS_APPROVAL_NEEDED,
)
from .question_normalizer import (
    STATUS_DRAFT_CREATED as NORMALIZE_STATUS_DRAFT_CREATED,
)
from .question_normalizer import (
    STATUS_NEEDS_CLARIFICATION as NORMALIZE_STATUS_NEEDS_CLARIFICATION,
)
from .question_normalizer import (
    STATUS_REJECTED_MALFORMED as NORMALIZE_STATUS_REJECTED_MALFORMED,
)
from .question_normalizer import (
    STATUS_STOPPED_BY_SUPPORT_SCOPE as NORMALIZE_STATUS_STOPPED_BY_SUPPORT_SCOPE,
)
from .question_normalizer import (
    QuestionNormalizationResult,
)

# --- Bounded result statuses -------------------------------------------------
# Exactly six.  ``scope_draft_created`` is the single proceed-with-data outcome
# (an inert ``ScopeBundle`` draft projection).  The other five are fail-closed /
# paused outcomes, none of which produce a scope bundle.
STATUS_SCOPE_DRAFT_CREATED = "scope_draft_created"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"
STATUS_STOPPED_BY_SUPPORT_SCOPE = "stopped_by_support_scope"
STATUS_APPROVAL_NEEDED = "approval_needed"
STATUS_UNSUPPORTED_SCOPE = "unsupported_scope"
STATUS_REJECTED_MALFORMED = "rejected_malformed"

STATUSES = (
    STATUS_SCOPE_DRAFT_CREATED,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_STOPPED_BY_SUPPORT_SCOPE,
    STATUS_APPROVAL_NEEDED,
    STATUS_UNSUPPORTED_SCOPE,
    STATUS_REJECTED_MALFORMED,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# scope_draft_created:
CODE_SCOPE_DRAFT_CREATED = "SCOPE_DRAFT_CREATED"
# needs_clarification (ambiguity stays open; never auto-resolved / auto-split):
CODE_NEEDS_CLARIFICATION = "SCOPE_NEEDS_CLARIFICATION"
CODE_MULTI_QUESTION_REQUIRES_REVIEW = "SCOPE_MULTI_QUESTION_REQUIRES_REVIEW"
# stopped_by_support_scope (preserves any WP-06a support-scope stop):
CODE_STOPPED_BY_SUPPORT_SCOPE = "SCOPE_STOPPED_BY_SUPPORT_SCOPE"
# approval_needed (the policy stays inert; never becomes an approval):
CODE_POLICY_MISSING = "SCOPE_POLICY_MISSING"
CODE_POLICY_APPROVAL_NEEDED = "SCOPE_POLICY_APPROVAL_NEEDED"
# unsupported_scope (a well-formed draft naming a scope the offline resolver does
# not support — e.g. an organism outside the synthetic supported vocabulary):
CODE_UNSUPPORTED_SCOPE = "SCOPE_UNSUPPORTED"
# rejected_malformed (fail closed on a malformed spec / policy / id):
CODE_SPEC_MALFORMED = "SCOPE_SPEC_MALFORMED"
CODE_POLICY_MALFORMED = "SCOPE_POLICY_MALFORMED"
CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED = "SCOPE_POLICY_EXECUTION_MODE_NOT_PERMITTED"
CODE_PROJECT_ID_MALFORMED = "SCOPE_PROJECT_ID_MALFORMED"
CODE_UPSTREAM_REJECTED = "SCOPE_UPSTREAM_REJECTED"

REASON_CODES = (
    CODE_SCOPE_DRAFT_CREATED,
    CODE_NEEDS_CLARIFICATION,
    CODE_MULTI_QUESTION_REQUIRES_REVIEW,
    CODE_STOPPED_BY_SUPPORT_SCOPE,
    CODE_POLICY_MISSING,
    CODE_POLICY_APPROVAL_NEEDED,
    CODE_UNSUPPORTED_SCOPE,
    CODE_SPEC_MALFORMED,
    CODE_POLICY_MALFORMED,
    CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED,
    CODE_PROJECT_ID_MALFORMED,
    CODE_UPSTREAM_REJECTED,
)

# The status each reason code resolves to, so a future adapter can map a code to a
# status without re-deriving it.
_CODE_STATUS = {
    CODE_SCOPE_DRAFT_CREATED: STATUS_SCOPE_DRAFT_CREATED,
    CODE_NEEDS_CLARIFICATION: STATUS_NEEDS_CLARIFICATION,
    CODE_MULTI_QUESTION_REQUIRES_REVIEW: STATUS_NEEDS_CLARIFICATION,
    CODE_STOPPED_BY_SUPPORT_SCOPE: STATUS_STOPPED_BY_SUPPORT_SCOPE,
    CODE_POLICY_MISSING: STATUS_APPROVAL_NEEDED,
    CODE_POLICY_APPROVAL_NEEDED: STATUS_APPROVAL_NEEDED,
    CODE_UNSUPPORTED_SCOPE: STATUS_UNSUPPORTED_SCOPE,
    CODE_SPEC_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_POLICY_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED: STATUS_REJECTED_MALFORMED,
    CODE_PROJECT_ID_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_UPSTREAM_REJECTED: STATUS_REJECTED_MALFORMED,
}

# The single status the produced scope bundle / ambiguity report carries; the
# command may never produce a resolved/locked/authoritative scope.
DRAFT_STATUS = "draft"

# --- Tiny synthetic, offline fixture vocabulary ------------------------------
# PUBLIC, TEST-ONLY, NON-SENSITIVE, SYNTHETIC.  These are NOT a real ontology and
# carry NO real identifiers or biological authority.  They only let the offline
# resolver *classify* a fact the draft already stated explicitly (e.g. recognise
# "tumor" as a condition term) so it can place it on an axis; an unrecognised term
# is never dropped or guessed — it stays an open ambiguity.  A caller may pass its
# own equally-synthetic vocabulary via ``vocabulary=``.
SYNTHETIC_SPECIES = ("human", "mouse", "rat")
SYNTHETIC_TISSUES = ("liver", "blood", "brain", "lung", "kidney")
SYNTHETIC_CONDITIONS = (
    "tumor",
    "normal",
    "control",
    "treated",
    "disease",
    "healthy",
    "case",
    "wildtype",
    "mutant",
)


@dataclass(frozen=True)
class ScopeVocabulary:
    """A tiny synthetic, offline term vocabulary for the fake resolver.

    Purely a *recognition* aid: it classifies an explicit draft term onto a scope
    axis.  It is **not** an ontology, holds no identifiers, and confers no
    authority.  All entries are matched case-insensitively against the verbatim
    explicit fact text; nothing is inferred when there is no match.
    """

    species: tuple[str, ...] = SYNTHETIC_SPECIES
    tissues: tuple[str, ...] = SYNTHETIC_TISSUES
    conditions: tuple[str, ...] = SYNTHETIC_CONDITIONS

    def knows_species(self, term: str) -> bool:
        return term.strip().lower() in {s.lower() for s in self.species}

    def knows_tissue(self, term: str) -> bool:
        return term.strip().lower() in {t.lower() for t in self.tissues}

    def knows_condition(self, term: str) -> bool:
        return term.strip().lower() in {c.lower() for c in self.conditions}


DEFAULT_VOCABULARY = ScopeVocabulary()


@dataclass(frozen=True)
class _ResolverFacts:
    """The explicit, already-extracted draft facts handed to the offline resolver.

    Every field is read verbatim from the inert draft; nothing here is inferred.
    """

    research_spec_id: str
    organism: str
    tissue: str
    condition: str
    comparison_groups: tuple[str, ...]


class OfflineScopeResolverAdapter:
    """The deterministic in-process fake/offline "Ontology / Scope Resolver call".

    This stands in for the architecture's ontology-backed Scope Resolver.  It is
    intentionally rule-based and offline: :meth:`resolve` is a pure function of the
    explicit draft facts and a synthetic vocabulary, performs no network/socket
    call, no environment/credential read, no provider/SDK/model/ontology/search
    call, no clock read, and no randomness, so the same input always yields the
    same projection.  It follows the "no business preset" rule — it places a fact
    on a scope axis only when the draft stated it explicitly, and records every
    unknown organism / tissue / condition / comparison fact as an ``open``
    ambiguity item rather than inventing one.  It mints **no** real ontology id and
    marks nothing authoritative.
    """

    def __init__(self, vocabulary: ScopeVocabulary | None = None) -> None:
        self.vocabulary = vocabulary if isinstance(vocabulary, ScopeVocabulary) else DEFAULT_VOCABULARY

    def resolve(self, facts: _ResolverFacts) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
        """Resolve ``facts`` into ``(code, scope_bundle | None, ambiguity_report)``.

        ``code`` is one of :data:`CODE_SCOPE_DRAFT_CREATED`,
        :data:`CODE_NEEDS_CLARIFICATION`, or :data:`CODE_UNSUPPORTED_SCOPE`.  The
        ambiguity report (an in-memory ``AmbiguityReport`` draft projection) is
        always returned so the open unknowns stay explicit even when no bundle is
        produced; the scope bundle is ``None`` unless a draft was created.
        """
        vocab = self.vocabulary
        open_items: list[dict[str, Any]] = []

        # --- Species axis: only an explicitly named organism. ----------------
        species: list[str] = []
        if facts.organism.strip():
            if not vocab.knows_species(facts.organism):
                # A well-formed draft naming an organism the offline resolver does
                # not support: fail closed as unsupported rather than guess or drop.
                return (
                    CODE_UNSUPPORTED_SCOPE,
                    None,
                    self._report(
                        facts.research_spec_id,
                        [
                            self._item(
                                "organism",
                                f"organism {facts.organism!r} is outside the offline resolver's synthetic supported species vocabulary; not resolved",
                            )
                        ],
                    ),
                )
            species = [facts.organism.strip()]
        else:
            open_items.append(self._item("organism", "organism not explicitly stated in the draft; left empty rather than assumed"))

        # --- Comparison + condition axes: only explicit comparison groups. ---
        groups = [g.strip() for g in facts.comparison_groups if isinstance(g, str) and g.strip()]
        distinct_groups = list(dict.fromkeys(groups))  # order-preserving de-dupe
        comparisons: list[str] = []
        conditions: list[str] = []
        if len(distinct_groups) >= 2:
            comparisons = distinct_groups
            for group in distinct_groups:
                if vocab.knows_condition(group):
                    if group not in conditions:
                        conditions.append(group)
                else:
                    open_items.append(
                        self._item(
                            "condition",
                            f"comparison group {group!r} is not in the synthetic condition vocabulary; kept as an explicit comparison label but not confirmed as a known condition",
                        )
                    )
        else:
            open_items.append(self._item("comparison", "no explicit two-group comparison stated in the draft; left empty rather than assumed"))

        # --- Condition axis: the explicit ``condition_or_phenotype`` fact. ----
        # An explicitly stated condition is never dropped: if the synthetic
        # vocabulary recognises it, it is projected onto the conditions axis
        # (without claiming ontology authority); if it is unrecognised, it stays an
        # ``open`` condition ambiguity rather than being silently discarded.
        if facts.condition.strip():
            if vocab.knows_condition(facts.condition):
                condition = facts.condition.strip()
                if condition not in conditions:
                    conditions.append(condition)
            else:
                open_items.append(
                    self._item(
                        "condition",
                        f"condition {facts.condition.strip()!r} is not in the synthetic condition vocabulary; kept open rather than confirmed as a known condition",
                    )
                )

        # --- Tissue axis: only an explicitly named, recognised tissue. -------
        tissues: list[str] = []
        if facts.tissue.strip() and vocab.knows_tissue(facts.tissue):
            tissues = [facts.tissue.strip()]
        else:
            open_items.append(self._item("tissue", "tissue/context not explicitly resolved by the offline resolver; left empty pending later scope resolution"))

        ambiguity_report = self._report(facts.research_spec_id, open_items)

        # A bundle requires at least one explicitly populated axis; with none, the
        # ambiguity stays open and no fabricated bundle is produced.
        if not (species or comparisons or conditions or tissues):
            return (CODE_NEEDS_CLARIFICATION, None, ambiguity_report)

        bundle = ScopeBundle(
            research_spec_id=facts.research_spec_id,
            species=species,
            tissues=tissues,
            conditions=conditions,
            comparisons=comparisons,
            status=DRAFT_STATUS,
            created_at="",  # inert, deterministic — no wall-clock timestamp
        ).to_dict()

        # Defensive self-check: a self-produced bundle must be internally valid; an
        # internally contradictory scope fails closed rather than being emitted.
        if validate_scope_bundle(bundle):
            return (CODE_NEEDS_CLARIFICATION, None, ambiguity_report)

        return (CODE_SCOPE_DRAFT_CREATED, bundle, ambiguity_report)

    @staticmethod
    def _item(subject: str, impact: str) -> dict[str, Any]:
        """An ``open`` ambiguity item (never ``assumed`` — the resolver never
        proceeds on a silent default)."""
        return {"subject": subject, "impact": impact, "status": "open"}

    @staticmethod
    def _report(research_spec_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return AmbiguityReport(
            research_spec_id=research_spec_id,
            items=items,
            status=DRAFT_STATUS,
            created_at="",  # inert, deterministic — no wall-clock timestamp
        ).to_dict()


@dataclass(frozen=True)
class ScopeResolutionResult:
    """The deterministic, reason-coded outcome of a Scope Resolver command.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  Exactly one proceed outcome (``scope_draft_created``)
    carries a ``scope_bundle`` draft projection; every outcome that reaches the
    resolver also carries an ``ambiguity_report`` draft projection of the open
    unknowns, so they stay explicit even when no bundle is produced.
    ``research_spec`` records the considered inert draft, ``original_request`` the
    preserved verbatim original/normalized request (when available from a
    normalizer result), ``assessment`` the upstream intake assessment, ``policy``
    the considered policy projection, and ``approval_request`` an inert
    approval-needed projection when the policy fails closed to approval.
    ``binding`` records the exact facts considered so the decision can be audited.
    The result is inert reviewable data: it is never persisted, versioned, emitted,
    sent out, marked authoritative, or treated as authorization.
    """

    status: str
    reason_code: str
    message: str
    scope_bundle: dict[str, Any] | None = None
    ambiguity_report: dict[str, Any] | None = None
    research_spec: dict[str, Any] | None = None
    original_request: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    approval_request: dict[str, Any] | None = None
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def scope_draft_created(self) -> bool:
        """The single proceed-with-data outcome (an inert ``ScopeBundle`` draft)."""
        return self.status == STATUS_SCOPE_DRAFT_CREATED

    @property
    def needs_clarification(self) -> bool:
        """A legitimate-but-paused outcome; the scope is never auto-resolved."""
        return self.status == STATUS_NEEDS_CLARIFICATION

    @property
    def approval_needed(self) -> bool:
        """The fail-closed outcome for a missing / approval-needed policy."""
        return self.status == STATUS_APPROVAL_NEEDED

    @property
    def unsupported_scope(self) -> bool:
        """A well-formed draft naming a scope the offline resolver cannot support."""
        return self.status == STATUS_UNSUPPORTED_SCOPE

    @property
    def open_questions(self) -> list[str]:
        """The open-ambiguity subjects, for convenient display (never authoritative)."""
        if not self.ambiguity_report:
            return []
        return [str(item.get("subject", "")) for item in self.ambiguity_report.get("items", []) if str(item.get("status")) == "open"]

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the result (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "scope_draft_created": self.scope_draft_created,
            "needs_clarification": self.needs_clarification,
            "approval_needed": self.approval_needed,
            "unsupported_scope": self.unsupported_scope,
            "scope_bundle": copy.deepcopy(self.scope_bundle) if self.scope_bundle is not None else None,
            "ambiguity_report": copy.deepcopy(self.ambiguity_report) if self.ambiguity_report is not None else None,
            "open_questions": list(self.open_questions),
            "research_spec": copy.deepcopy(self.research_spec) if self.research_spec is not None else None,
            "original_request": copy.deepcopy(self.original_request) if self.original_request is not None else None,
            "assessment": copy.deepcopy(self.assessment) if self.assessment is not None else None,
            "policy": copy.deepcopy(self.policy) if self.policy is not None else None,
            "approval_request": copy.deepcopy(self.approval_request) if self.approval_request is not None else None,
            "binding": copy.deepcopy(self.binding),
        }


def _resolve_policy(policy: Any) -> tuple[dict[str, Any] | None, tuple[str, str, dict[str, Any] | None] | None]:
    """Resolve the policy input; return ``(policy_dict, error)``.

    Mirrors the WP-06d policy gate so a bare-draft caller fails closed identically:
    a usable *built* policy resolves to ``(policy_dict, None)``; ``None`` is a
    missing policy; an approval-needed policy-builder result, a malformed/tampered
    policy, or a non-permitted execution mode each fails closed.  A malformed
    truthy value such as the bool ``True``, the int ``1``, or the string ``"true"``
    supplied where a policy is expected is **not** a mapping and fails closed as
    malformed rather than being treated as a policy.
    """
    if policy is None:
        return (None, (CODE_POLICY_MISSING, "no policy supplied; a usable initial policy is required before scope can be resolved", None))

    if isinstance(policy, PolicyBuildOutcome):
        if policy.approval_needed:
            return (
                None,
                (
                    CODE_POLICY_APPROVAL_NEEDED,
                    f"policy build requires human approval first ({policy.reason_code}); the request stays inert and no scope is resolved",
                    copy.deepcopy(policy.approval_request) if policy.approval_request is not None else None,
                ),
            )
        if not policy.built or policy.policy is None:
            return (None, (CODE_POLICY_MALFORMED, f"policy build did not produce a usable policy ({policy.reason_code})", None))
        policy_dict: dict[str, Any] = dict(policy.policy)
    elif isinstance(policy, Mapping):
        policy_dict = dict(policy)
    else:
        # A bare bool / int / str / list supplied where a policy is expected is NOT
        # a mapping and fails closed here.
        return (None, (CODE_POLICY_MALFORMED, f"policy must be a PolicyBuildOutcome or a policy mapping, not {type(policy).__name__}", None))

    errors = validate_project_policy(policy_dict)
    if errors:
        return (None, (CODE_POLICY_MALFORMED, "; ".join(errors), None))

    if policy_dict.get("execution_mode") not in PERMITTED_EXECUTION_MODES:
        return (
            None,
            (
                CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED,
                f"policy execution_mode {policy_dict.get('execution_mode')!r} is not permitted for the offline scope resolver (must be one of {PERMITTED_EXECUTION_MODES})",
                None,
            ),
        )

    return (policy_dict, None)


def _spec_dict(spec: Any) -> dict[str, Any] | None:
    """Return a draft ``ResearchSpec`` projection for an accepted shape, else ``None``.

    Accepts a :class:`ResearchSpec` or a mapping projection of one; the value is
    only read, never mutated.  A spec that is not in ``draft`` status (a locked /
    resolved spec) is rejected by the caller, not coerced here.
    """
    if isinstance(spec, ResearchSpec):
        return spec.to_dict()
    if isinstance(spec, Mapping):
        return dict(spec)
    return None


def _facts_from_spec(spec_dict: Mapping[str, Any]) -> _ResolverFacts:
    """Extract the explicit, verbatim draft facts (never inferred)."""
    organism = spec_dict.get("organism", "")
    tissue = spec_dict.get("tissue", "")
    condition = spec_dict.get("condition_or_phenotype", "")
    groups = spec_dict.get("comparison_groups", [])
    research_spec_id = spec_dict.get("research_spec_id", "")
    return _ResolverFacts(
        research_spec_id=str(research_spec_id or ""),
        organism=str(organism or "") if isinstance(organism, str) else "",
        tissue=str(tissue or "") if isinstance(tissue, str) else "",
        condition=str(condition or "") if isinstance(condition, str) else "",
        comparison_groups=tuple(g for g in groups if isinstance(g, str)) if isinstance(groups, list) else (),
    )


def resolve_scope(
    source: Any,
    policy: Any = None,
    *,
    project_id: str,
    vocabulary: ScopeVocabulary | None = None,
    caller_facts: Mapping[str, Any] | None = None,
) -> ScopeResolutionResult:
    """Run the local/offline Scope Resolver preflight command, fail-closed.

    A pure, deterministic function returning a bounded
    :class:`ScopeResolutionResult` (it never raises for a domain condition, never
    mutates its inputs, and performs no I/O, clock read, LLM/provider/ontology/
    search call, persistence, event emission, approval grant, or content egress).

    ``source`` is either a :class:`QuestionNormalizationResult` (the WP-06d
    normalizer result — its embedded gate outcome, draft, and validated policy are
    reused) or a bare draft ``ResearchSpec`` / mapping projection.  ``policy`` is a
    :class:`PolicyBuildOutcome`, a policy mapping, or ``None`` — it is required and
    re-validated **only** for a bare-draft source; a normalizer result already
    carries its validated policy.  Precedence — the upstream/scope gate first, then
    the policy gate, so any uncertainty fails closed and no scope bundle is created
    unless every gate passes:

    1. **Project id** — an invalid ``project_id`` → ``rejected_malformed``.
    2. **Source**:
       - a non-``draft_created`` :class:`QuestionNormalizationResult` is carried
         through verbatim as the corresponding stop / pause / approval / malformed
         scope outcome (no bundle);
       - a bare draft re-runs :func:`assess_intake` (a support-scope stop →
         ``stopped_by_support_scope``; a multi-question / needs-clarification
         request → ``needs_clarification``) and is rejected if it is not a
         well-formed ``draft``-status spec.
    3. **Policy** (bare-draft source only, reusing WP-06c via
       :func:`validate_project_policy`): missing → ``approval_needed``; an
       approval-needed policy-builder result → ``approval_needed`` (inert); a
       malformed/tampered/non-permitted policy → ``rejected_malformed``.
    4. Otherwise run the deterministic offline resolver to produce an inert
       ``ScopeBundle`` draft from the explicit facts (``scope_draft_created``),
       leave the ambiguity open when no explicit fact exists
       (``needs_clarification``), or fail closed on a scope the resolver does not
       support (``unsupported_scope``).
    """
    binding: dict[str, Any] = {
        "project_id": project_id,
        "source_kind": type(source).__name__,
        "policy_kind": type(policy).__name__,
    }

    def _result(
        code: str,
        message: str,
        *,
        scope_bundle: dict[str, Any] | None = None,
        ambiguity_report: dict[str, Any] | None = None,
        research_spec: dict[str, Any] | None = None,
        original_request: dict[str, Any] | None = None,
        assessment: dict[str, Any] | None = None,
        policy_dict: dict[str, Any] | None = None,
        approval_request: dict[str, Any] | None = None,
    ) -> ScopeResolutionResult:
        return ScopeResolutionResult(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            scope_bundle=scope_bundle,
            ambiguity_report=ambiguity_report,
            research_spec=research_spec,
            original_request=original_request,
            assessment=assessment,
            policy=policy_dict,
            approval_request=approval_request,
            binding=dict(binding),
        )

    # 1. Project id must be a valid identifier (fail closed before anything else).
    from ..core import common

    if common.validate_identifier(project_id, "project_id"):
        return _result(CODE_PROJECT_ID_MALFORMED, "project_id is missing or not a valid identifier (lowercase token, no whitespace)")

    # 2. Resolve the source into a draft spec + the gate context, fail closed.
    spec_dict: dict[str, Any] | None
    assessment_dict: dict[str, Any] | None
    original_request: dict[str, Any] | None
    resolved_policy: dict[str, Any] | None

    if isinstance(source, QuestionNormalizationResult):
        # The normalizer already ran every WP-06a/06b/06c gate; carry a non-draft
        # outcome through verbatim and reuse its validated draft + policy.
        binding["normalizer_status"] = source.status
        binding["normalizer_reason_code"] = source.reason_code
        assessment_dict = copy.deepcopy(source.assessment) if source.assessment is not None else None
        if source.status != NORMALIZE_STATUS_DRAFT_CREATED:
            code = _map_normalizer_stop(source)
            return _result(
                code,
                f"upstream question normalizer did not produce a draft ({source.reason_code}); no scope resolved",
                assessment=assessment_dict,
                approval_request=copy.deepcopy(source.approval_request) if source.approval_request is not None else None,
                policy_dict=copy.deepcopy(source.policy) if source.policy is not None else None,
            )
        spec_dict = copy.deepcopy(source.research_spec) if source.research_spec is not None else None
        original_request = copy.deepcopy(source.original_request) if source.original_request is not None else None
        resolved_policy = copy.deepcopy(source.policy) if source.policy is not None else None
        if not isinstance(spec_dict, Mapping):
            return _result(CODE_SPEC_MALFORMED, "normalizer draft_created result carried no usable research-spec draft", assessment=assessment_dict)
    else:
        # A bare draft spec: re-run the intake gate and the policy gate as defence
        # in depth, then extract the explicit facts.
        spec_dict = _spec_dict(source)
        if spec_dict is None:
            return _result(
                CODE_SPEC_MALFORMED, f"source must be a QuestionNormalizationResult, a ResearchSpec, or a research-spec mapping, not {type(source).__name__}"
            )
        research_question = spec_dict.get("research_question")
        if not isinstance(research_question, str) or not research_question.strip():
            return _result(CODE_SPEC_MALFORMED, "draft spec is missing a non-empty research_question")
        spec_status = spec_dict.get("status", DRAFT_STATUS)
        if spec_status not in ("", DRAFT_STATUS):
            return _result(
                CODE_SPEC_MALFORMED, f"scope can only be resolved from an inert draft spec (status={spec_status!r}); a locked/resolved spec is not accepted"
            )

        assessment: IntakeAssessment = assess_intake(research_question, caller_facts=caller_facts)
        assessment_dict = assessment.to_dict()
        binding["support_scope_classification"] = assessment.support_scope.get("classification")
        binding["assessment"] = assessment.assessment
        if not assessment.generated:
            return _result(
                CODE_STOPPED_BY_SUPPORT_SCOPE,
                f"intake support scope stopped the draft request ({assessment.support_scope.get('reason_code')}); no scope resolved",
                assessment=assessment_dict,
            )
        if assessment.multi_question:
            return _result(
                CODE_MULTI_QUESTION_REQUIRES_REVIEW,
                "draft appears to contain multiple research questions; it requires human review and is not auto-resolved",
                assessment=assessment_dict,
            )
        if assessment.needs_clarification:
            return _result(CODE_NEEDS_CLARIFICATION, "draft needs human clarification before scope can be resolved", assessment=assessment_dict)

        resolved_policy, policy_error = _resolve_policy(policy)
        if policy_error is not None:
            code, message, approval_request = policy_error
            return _result(code, message, assessment=assessment_dict, approval_request=approval_request)
        original_request = None

    assert spec_dict is not None

    # 3. Run the deterministic offline resolver over the explicit draft facts.
    facts = _facts_from_spec(spec_dict)
    if not facts.research_spec_id:
        return _result(
            CODE_SPEC_MALFORMED,
            "draft spec is missing a research_spec_id; cannot anchor a scope projection",
            assessment=assessment_dict,
            research_spec=copy.deepcopy(spec_dict),
        )

    resolver = OfflineScopeResolverAdapter(vocabulary)
    code, scope_bundle, ambiguity_report = resolver.resolve(facts)

    binding["organism"] = facts.organism
    binding["comparison_groups"] = list(facts.comparison_groups)
    binding["tissue"] = facts.tissue
    binding["research_spec_id"] = facts.research_spec_id
    if scope_bundle is not None:
        binding["scope_bundle_id"] = scope_bundle.get("scope_bundle_id")
        binding["scope_axes_populated"] = {axis: bool(scope_bundle.get(axis)) for axis in ("species", "tissues", "conditions", "comparisons")}
    binding["ambiguity_report_id"] = ambiguity_report.get("ambiguity_report_id")
    binding["open_ambiguity_count"] = sum(1 for it in ambiguity_report.get("items", []) if str(it.get("status")) == "open")
    if resolved_policy is not None:
        binding["policy_execution_mode"] = resolved_policy.get("execution_mode")
        binding["policy_data_sensitivity"] = resolved_policy.get("data_sensitivity")

    # Defensive self-check: the open-ambiguity projection must itself be valid.
    if validate_ambiguity_report(ambiguity_report):
        return _result(
            CODE_SPEC_MALFORMED, "offline resolver produced an invalid ambiguity projection", assessment=assessment_dict, research_spec=copy.deepcopy(spec_dict)
        )

    messages = {
        CODE_SCOPE_DRAFT_CREATED: "offline scope resolver produced an inert scope-bundle draft from the explicit facts; unknown facts remain open ambiguities",
        CODE_NEEDS_CLARIFICATION: "draft states no explicit usable scope fact; the scope ambiguity stays open and no bundle is fabricated",
        CODE_UNSUPPORTED_SCOPE: "draft names a scope the offline resolver does not support; failed closed with no bundle",
    }
    return _result(
        code,
        messages[code],
        scope_bundle=scope_bundle,
        ambiguity_report=ambiguity_report,
        research_spec=copy.deepcopy(spec_dict),
        original_request=original_request,
        assessment=assessment_dict,
        policy_dict=resolved_policy,
    )


def _map_normalizer_stop(result: QuestionNormalizationResult) -> str:
    """Map a non-``draft_created`` normalizer outcome to a scope reason code."""
    if result.status == NORMALIZE_STATUS_STOPPED_BY_SUPPORT_SCOPE:
        return CODE_STOPPED_BY_SUPPORT_SCOPE
    if result.status == NORMALIZE_STATUS_NEEDS_CLARIFICATION:
        return CODE_MULTI_QUESTION_REQUIRES_REVIEW if result.reason_code == NORMALIZE_CODE_MULTI_QUESTION else CODE_NEEDS_CLARIFICATION
    if result.status == NORMALIZE_STATUS_APPROVAL_NEEDED:
        return CODE_POLICY_APPROVAL_NEEDED if result.reason_code == NORMALIZE_CODE_POLICY_APPROVAL_NEEDED else CODE_POLICY_MISSING
    if result.status == NORMALIZE_STATUS_REJECTED_MALFORMED:
        return CODE_UPSTREAM_REJECTED
    return CODE_UPSTREAM_REJECTED


__all__ = [
    "STATUS_SCOPE_DRAFT_CREATED",
    "STATUS_NEEDS_CLARIFICATION",
    "STATUS_STOPPED_BY_SUPPORT_SCOPE",
    "STATUS_APPROVAL_NEEDED",
    "STATUS_UNSUPPORTED_SCOPE",
    "STATUS_REJECTED_MALFORMED",
    "STATUSES",
    "CODE_SCOPE_DRAFT_CREATED",
    "CODE_NEEDS_CLARIFICATION",
    "CODE_MULTI_QUESTION_REQUIRES_REVIEW",
    "CODE_STOPPED_BY_SUPPORT_SCOPE",
    "CODE_POLICY_MISSING",
    "CODE_POLICY_APPROVAL_NEEDED",
    "CODE_UNSUPPORTED_SCOPE",
    "CODE_SPEC_MALFORMED",
    "CODE_POLICY_MALFORMED",
    "CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED",
    "CODE_PROJECT_ID_MALFORMED",
    "CODE_UPSTREAM_REJECTED",
    "REASON_CODES",
    "DRAFT_STATUS",
    "SYNTHETIC_SPECIES",
    "SYNTHETIC_TISSUES",
    "SYNTHETIC_CONDITIONS",
    "DEFAULT_VOCABULARY",
    "ScopeVocabulary",
    "OfflineScopeResolverAdapter",
    "ScopeResolutionResult",
    "resolve_scope",
]
