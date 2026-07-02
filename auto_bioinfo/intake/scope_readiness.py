"""Local deterministic scope-readiness preflight (WP-06f / T-06-06).

The sixth *local* intake slice.  Where
:mod:`auto_bioinfo.intake.scope_resolver` (WP-06e) answers *"given an inert draft
and a usable policy, what inert ``ScopeBundle`` / ``AmbiguityReport`` draft
projection can a deterministic offline resolver propose from the explicit facts?"*,
this module answers the next bounded question — *"is that already-inert scope
resolution output internally consistent enough to hand to a human reviewer, or
must it stay paused / be rejected, and why?"* — **before any real ontology
resolution, dataset/literature search, approval grant, event emission, persistence,
or pipeline stage transition can start**.

It is the local/offline slice of T-06-06 only.  It is a pure *status / consistency
projection* over the already-inert WP-06e output: it runs no resolver, contacts no
ontology / search / provider / network, persists nothing, emits no event, grants no
approval, splits no request, creates no child project, and never authorises
execution.  A ``ready_for_review`` verdict is an inert reviewable signal that a
human may look at the draft — it is **never** a grant to execute.

Design constraints (WP-06f), mirroring the WP-06a..06e contract style:

- **Pure and deterministic.** :func:`assess_scope_readiness` and every helper is a
  total function of its explicit in-memory inputs.  There is no I/O whatsoever: no
  file access, no network/socket, no environment/credential inspection, no clock
  read, no LLM / provider / model / SDK / ontology / search call, no content
  egress, no subprocess, no threads, scheduler, queue, outbox, DB, event, audit
  log, report/index/cache, or any process side effect.  Inputs are never mutated in
  place; exposed projections are defensive copies.  Byte-identical inputs always
  yield a byte-identical result.
- **Judge, never re-resolve.** This layer does **not** re-run the offline resolver
  or invent any scope.  It reads the WP-06e :class:`ScopeResolutionResult` (or a
  faithful mapping projection of one) and decides readiness from it, re-validating
  every claimed projection.
- **Preserve every upstream gate.** A WP-06e support-scope stop stays a stop
  (``stopped_by_upstream_gate``); a multi-question / needs-clarification outcome
  stays human-review oriented and never becomes ready (``clarification_required``);
  a missing / approval-needed / malformed policy stays inert
  (``approval_needed``); a non-``scope_draft_created`` scope outcome never becomes
  ready.
- **No-guess consistency.**  A ``scope_draft_created`` resolution only becomes
  ``ready_for_review`` when it survives every consistency check without guessing:
  the ``ScopeBundle`` / ``AmbiguityReport`` must remain ``draft`` / non-authoritative
  review projections that individually validate; the research-spec / bundle /
  report identifiers must match (and, when a ``source`` is supplied, match its
  draft id too); every populated scope axis value must be traceable to an explicit
  draft fact via the exact WP-06e production path (never fabricated); an explicit
  draft fact that did not reach an axis must survive as an ``open`` ambiguity rather
  than silently disappearing; and an empty / wholly-unknown scope can never become
  ready.  Any failure fails closed to ``rejected_inconsistent`` with a stable
  reason code.
- **Bounded vocabulary.** The status is one of exactly five values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.

This module produces reviewable data only.  It does not persist, version, emit,
enqueue, send out, mark authoritative, approve, or unblock any downstream workflow
or pipeline stage — those remain out of scope for T-06-06 (see WP-06g+ /
T-06-07+).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core import common
from ..core.validation import validate_ambiguity_report, validate_scope_bundle
from .question_normalizer import (
    STATUS_DRAFT_CREATED as NORMALIZE_STATUS_DRAFT_CREATED,
)
from .question_normalizer import (
    QuestionNormalizationResult,
)
from .scope_resolver import (
    DEFAULT_VOCABULARY,
    DRAFT_STATUS,
    ScopeResolutionResult,
    ScopeVocabulary,
    _CODE_STATUS as SCOPE_CODE_STATUS,
    _facts_from_spec,
)
from .scope_resolver import (
    STATUS_APPROVAL_NEEDED as SCOPE_STATUS_APPROVAL_NEEDED,
)
from .scope_resolver import (
    STATUS_NEEDS_CLARIFICATION as SCOPE_STATUS_NEEDS_CLARIFICATION,
)
from .scope_resolver import (
    STATUS_REJECTED_MALFORMED as SCOPE_STATUS_REJECTED_MALFORMED,
)
from .scope_resolver import (
    STATUS_SCOPE_DRAFT_CREATED as SCOPE_STATUS_DRAFT_CREATED,
)
from .scope_resolver import (
    STATUS_STOPPED_BY_SUPPORT_SCOPE as SCOPE_STATUS_STOPPED_BY_SUPPORT_SCOPE,
)
from .scope_resolver import (
    STATUS_UNSUPPORTED_SCOPE as SCOPE_STATUS_UNSUPPORTED_SCOPE,
)
from .scope_resolver import (
    STATUSES as SCOPE_STATUSES,
)

# --- Bounded readiness statuses ----------------------------------------------
# Exactly five.  ``ready_for_review`` is the single "a human may review this draft"
# outcome; the other four are paused / fail-closed outcomes, none of which is a
# grant to review a fabricated scope or to execute.
STATUS_READY_FOR_REVIEW = "ready_for_review"
STATUS_CLARIFICATION_REQUIRED = "clarification_required"
STATUS_STOPPED_BY_UPSTREAM_GATE = "stopped_by_upstream_gate"
STATUS_APPROVAL_NEEDED = "approval_needed"
STATUS_REJECTED_INCONSISTENT = "rejected_inconsistent"

STATUSES = (
    STATUS_READY_FOR_REVIEW,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_STOPPED_BY_UPSTREAM_GATE,
    STATUS_APPROVAL_NEEDED,
    STATUS_REJECTED_INCONSISTENT,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# ready_for_review:
CODE_READY_FOR_REVIEW = "READINESS_READY_FOR_REVIEW"
# clarification_required (the scope stays paused; never auto-resolved / auto-split):
CODE_OPEN_AMBIGUITY = "READINESS_OPEN_AMBIGUITY"
CODE_UNSUPPORTED_SCOPE = "READINESS_UNSUPPORTED_SCOPE"
# stopped_by_upstream_gate (preserves any WP-06a support-scope stop):
CODE_STOPPED_BY_UPSTREAM_GATE = "READINESS_STOPPED_BY_UPSTREAM_GATE"
# approval_needed (the policy stays inert; never becomes an approval):
CODE_APPROVAL_NEEDED = "READINESS_APPROVAL_NEEDED"
# rejected_inconsistent (fail closed on a malformed / inconsistent resolution):
CODE_PROJECT_ID_MALFORMED = "READINESS_PROJECT_ID_MALFORMED"
CODE_RESOLUTION_MALFORMED = "READINESS_RESOLUTION_MALFORMED"
CODE_UPSTREAM_REJECTED = "READINESS_UPSTREAM_REJECTED"
CODE_MISSING_PROJECTION = "READINESS_MISSING_PROJECTION"
CODE_SCOPE_BUNDLE_INVALID = "READINESS_SCOPE_BUNDLE_INVALID"
CODE_AMBIGUITY_REPORT_INVALID = "READINESS_AMBIGUITY_REPORT_INVALID"
CODE_NON_DRAFT_PROJECTION = "READINESS_NON_DRAFT_PROJECTION"
CODE_AUTHORITATIVE_PROJECTION = "READINESS_AUTHORITATIVE_PROJECTION"
CODE_IDENTIFIER_MISMATCH = "READINESS_IDENTIFIER_MISMATCH"
CODE_SOURCE_MISMATCH = "READINESS_SOURCE_MISMATCH"
CODE_UNTRACEABLE_SCOPE = "READINESS_UNTRACEABLE_SCOPE"
CODE_DROPPED_UNKNOWN_AXIS = "READINESS_DROPPED_UNKNOWN_AXIS"
CODE_EMPTY_SCOPE = "READINESS_EMPTY_SCOPE"

REASON_CODES = (
    CODE_READY_FOR_REVIEW,
    CODE_OPEN_AMBIGUITY,
    CODE_UNSUPPORTED_SCOPE,
    CODE_STOPPED_BY_UPSTREAM_GATE,
    CODE_APPROVAL_NEEDED,
    CODE_PROJECT_ID_MALFORMED,
    CODE_RESOLUTION_MALFORMED,
    CODE_UPSTREAM_REJECTED,
    CODE_MISSING_PROJECTION,
    CODE_SCOPE_BUNDLE_INVALID,
    CODE_AMBIGUITY_REPORT_INVALID,
    CODE_NON_DRAFT_PROJECTION,
    CODE_AUTHORITATIVE_PROJECTION,
    CODE_IDENTIFIER_MISMATCH,
    CODE_SOURCE_MISMATCH,
    CODE_UNTRACEABLE_SCOPE,
    CODE_DROPPED_UNKNOWN_AXIS,
    CODE_EMPTY_SCOPE,
)

# The status each reason code resolves to, so a future adapter can map a code to a
# status without re-deriving it.
_CODE_STATUS = {
    CODE_READY_FOR_REVIEW: STATUS_READY_FOR_REVIEW,
    CODE_OPEN_AMBIGUITY: STATUS_CLARIFICATION_REQUIRED,
    CODE_UNSUPPORTED_SCOPE: STATUS_CLARIFICATION_REQUIRED,
    CODE_STOPPED_BY_UPSTREAM_GATE: STATUS_STOPPED_BY_UPSTREAM_GATE,
    CODE_APPROVAL_NEEDED: STATUS_APPROVAL_NEEDED,
    CODE_PROJECT_ID_MALFORMED: STATUS_REJECTED_INCONSISTENT,
    CODE_RESOLUTION_MALFORMED: STATUS_REJECTED_INCONSISTENT,
    CODE_UPSTREAM_REJECTED: STATUS_REJECTED_INCONSISTENT,
    CODE_MISSING_PROJECTION: STATUS_REJECTED_INCONSISTENT,
    CODE_SCOPE_BUNDLE_INVALID: STATUS_REJECTED_INCONSISTENT,
    CODE_AMBIGUITY_REPORT_INVALID: STATUS_REJECTED_INCONSISTENT,
    CODE_NON_DRAFT_PROJECTION: STATUS_REJECTED_INCONSISTENT,
    CODE_AUTHORITATIVE_PROJECTION: STATUS_REJECTED_INCONSISTENT,
    CODE_IDENTIFIER_MISMATCH: STATUS_REJECTED_INCONSISTENT,
    CODE_SOURCE_MISMATCH: STATUS_REJECTED_INCONSISTENT,
    CODE_UNTRACEABLE_SCOPE: STATUS_REJECTED_INCONSISTENT,
    CODE_DROPPED_UNKNOWN_AXIS: STATUS_REJECTED_INCONSISTENT,
    CODE_EMPTY_SCOPE: STATUS_REJECTED_INCONSISTENT,
}

# The one status the reviewed scope-bundle / ambiguity-report projections must
# carry; a readiness verdict may never confirm a resolved / locked / authoritative
# scope.
REQUIRED_PROJECTION_STATUS = DRAFT_STATUS

# Keys / flags whose presence (or truthiness) would make a projection look
# authoritative — a real ontology identifier or a lock/authority marker.  A
# readiness verdict must reject an authoritative-looking scope draft rather than
# review it as if it were inert.
FORBIDDEN_PROJECTION_KEYS = ("ontology_id", "mapped_id")
FORBIDDEN_AUTHORITY_FLAGS = ("authoritative", "locked", "resolved_authoritative", "is_authoritative")

# The scope axes a bundle carries, paired with the draft fact each is produced from
# on the exact WP-06e path.
_SCOPE_AXES = ("species", "tissues", "conditions", "comparisons")

# The exact bounded ``(status, reason_code)`` pairs WP-06e can emit, derived from
# the resolver's own code→status map so the two vocabularies cannot drift.  A
# readiness verdict fails closed on any pair outside this set: a tampered / faithful-
# looking projection cannot smuggle an out-of-vocabulary reason code, nor pair a
# real status with a reason code it never legitimately carries (in particular, a
# ``scope_draft_created`` status only ever pairs with ``SCOPE_DRAFT_CREATED``).
_VALID_UPSTREAM_PAIRS = frozenset((status, code) for code, status in SCOPE_CODE_STATUS.items())


@dataclass(frozen=True)
class ScopeReadinessResult:
    """The deterministic, reason-coded outcome of a scope-readiness preflight.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  The single ``ready_for_review`` outcome means the inert
    scope-resolution output is internally consistent enough for a human to review;
    it is never a grant to execute.  ``scope_bundle`` / ``ambiguity_report`` /
    ``research_spec`` carry defensive copies of the reviewed inert projections (when
    present).  ``upstream_status`` / ``upstream_reason_code`` record the WP-06e
    scope-resolution verdict this readiness verdict was derived from.
    ``findings`` records the consistency observations behind the verdict so it can
    be audited.  ``binding`` records the exact facts considered.  The result is
    inert reviewable data: it is never persisted, versioned, emitted, sent out,
    marked authoritative, or treated as authorization.
    """

    status: str
    reason_code: str
    message: str
    scope_bundle: dict[str, Any] | None = None
    ambiguity_report: dict[str, Any] | None = None
    research_spec: dict[str, Any] | None = None
    upstream_status: str = ""
    upstream_reason_code: str = ""
    findings: tuple[str, ...] = ()
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        """The single "a human may review this draft" outcome (never a grant to run)."""
        return self.status == STATUS_READY_FOR_REVIEW

    @property
    def clarification_required(self) -> bool:
        """A legitimate-but-paused outcome; the scope is never auto-resolved."""
        return self.status == STATUS_CLARIFICATION_REQUIRED

    @property
    def approval_needed(self) -> bool:
        """The fail-closed outcome for a missing / approval-needed policy."""
        return self.status == STATUS_APPROVAL_NEEDED

    @property
    def rejected(self) -> bool:
        """A malformed / internally inconsistent resolution output fails closed here."""
        return self.status == STATUS_REJECTED_INCONSISTENT

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
            "ready": self.ready,
            "clarification_required": self.clarification_required,
            "approval_needed": self.approval_needed,
            "rejected": self.rejected,
            "scope_bundle": copy.deepcopy(self.scope_bundle) if self.scope_bundle is not None else None,
            "ambiguity_report": copy.deepcopy(self.ambiguity_report) if self.ambiguity_report is not None else None,
            "research_spec": copy.deepcopy(self.research_spec) if self.research_spec is not None else None,
            "open_questions": list(self.open_questions),
            "upstream_status": self.upstream_status,
            "upstream_reason_code": self.upstream_reason_code,
            "findings": list(self.findings),
            "binding": copy.deepcopy(self.binding),
        }


def _ci(value: Any) -> str:
    """Case-insensitive, whitespace-trimmed view of a string-ish value."""
    return str(value or "").strip().lower() if isinstance(value, str) else ""


def _projection_fields(resolution: Any) -> dict[str, Any] | None:
    """Read the fields this preflight judges from a scope-resolution outcome.

    Accepts a :class:`ScopeResolutionResult` or a faithful mapping projection of
    one (its ``to_dict()`` output).  The value is only read, never mutated; returns
    ``None`` for any other shape (fail closed as malformed).
    """
    if isinstance(resolution, ScopeResolutionResult):
        return {
            "status": resolution.status,
            "reason_code": resolution.reason_code,
            "scope_bundle": copy.deepcopy(resolution.scope_bundle),
            "ambiguity_report": copy.deepcopy(resolution.ambiguity_report),
            "research_spec": copy.deepcopy(resolution.research_spec),
        }
    if isinstance(resolution, Mapping):
        status = resolution.get("status")
        if status not in SCOPE_STATUSES:
            return None
        return {
            "status": status,
            "reason_code": str(resolution.get("reason_code", "") or ""),
            "scope_bundle": copy.deepcopy(resolution.get("scope_bundle")) if isinstance(resolution.get("scope_bundle"), Mapping) else None,
            "ambiguity_report": copy.deepcopy(resolution.get("ambiguity_report")) if isinstance(resolution.get("ambiguity_report"), Mapping) else None,
            "research_spec": copy.deepcopy(resolution.get("research_spec")) if isinstance(resolution.get("research_spec"), Mapping) else None,
        }
    return None


def _source_spec_id(source: Any) -> tuple[str | None, str | None]:
    """Return ``(research_spec_id, error_code)`` for an optional source.

    ``source`` is an optional :class:`QuestionNormalizationResult`, draft
    ``ResearchSpec`` / mapping projection, used only to cross-check that the
    reviewed scope resolution belongs to the same inert draft.  ``research_spec_id``
    is ``None`` when the source carries no usable draft id; ``error_code`` is set
    when the source itself is inconsistent with a reviewable draft.
    """
    if source is None:
        return (None, None)
    if isinstance(source, QuestionNormalizationResult):
        if source.status != NORMALIZE_STATUS_DRAFT_CREATED:
            # A non-draft normalizer source paired with a scope resolution cannot be
            # cross-checked as the same reviewable draft.
            return (None, CODE_SOURCE_MISMATCH)
        spec = source.research_spec if isinstance(source.research_spec, Mapping) else None
        if not spec:
            return (None, CODE_SOURCE_MISMATCH)
        return (str(spec.get("research_spec_id", "") or ""), None)
    # A draft ResearchSpec object or a mapping projection of one.
    spec_dict: Mapping[str, Any] | None
    to_dict = getattr(source, "to_dict", None)
    if callable(to_dict):
        candidate = to_dict()
        spec_dict = candidate if isinstance(candidate, Mapping) else None
    elif isinstance(source, Mapping):
        spec_dict = source
    else:
        spec_dict = None
    if spec_dict is None:
        return (None, CODE_SOURCE_MISMATCH)
    status = spec_dict.get("status", DRAFT_STATUS)
    if status not in ("", DRAFT_STATUS):
        # A locked / resolved source spec is not an inert draft to make ready.
        return (None, CODE_SOURCE_MISMATCH)
    return (str(spec_dict.get("research_spec_id", "") or ""), None)


def _authoritative_findings(projection: Mapping[str, Any], label: str) -> list[str]:
    """Findings if a projection carries a real id or a truthy authority flag anywhere.

    The scan is **deep**: an authoritative-looking identifier (``ontology_id`` /
    ``mapped_id``) or a truthy authority flag must fail closed whether it sits at the
    top level of the projection or is nested inside an ambiguity item, a
    bundle/report sub-structure, or any list therein.  A review projection must stay
    inert draft data end to end, so an authoritative marker smuggled into a nested
    item is just as disqualifying as one at the root.
    """
    findings: list[str] = []
    _scan_authoritative(projection, label, findings)
    return findings


def _scan_authoritative(node: Any, label: str, findings: list[str]) -> None:
    """Recursively collect authority/id violations found under ``node``.

    Read-only walk over the already-copied projection: descends into every nested
    mapping and list/tuple so no nesting depth can hide a forbidden identifier or a
    truthy authority-like flag.
    """
    if isinstance(node, Mapping):
        for key in FORBIDDEN_PROJECTION_KEYS:
            if str(node.get(key, "") or "").strip():
                findings.append(f"{label} carries a forbidden authoritative field {key!r}; a review projection must not carry a real identifier")
        for flag in FORBIDDEN_AUTHORITY_FLAGS:
            if flag in node and bool(node.get(flag)):
                findings.append(f"{label} sets authority flag {flag!r} truthy; a review projection must stay non-authoritative")
        for value in node.values():
            _scan_authoritative(value, label, findings)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _scan_authoritative(value, label, findings)


def _axis_traceable(axis: str, value: str, facts: Any, vocab: ScopeVocabulary) -> bool:
    """Whether an axis value could have been produced by the exact WP-06e path.

    The vocabulary is a *recognition* aid only; every value must also trace to an
    explicit draft fact.  Species/tissue must be the explicit, recognised organism/
    tissue; a comparison must be an explicit comparison group; a condition must be
    an explicit comparison group or the explicit condition fact, recognised by the
    synthetic condition vocabulary.  Nothing is accepted that the draft did not
    state, and nothing is accepted that WP-06e would not have classified onto that
    axis.
    """
    v = _ci(value)
    groups = {_ci(g) for g in facts.comparison_groups}
    if axis == "species":
        return bool(v) and v == _ci(facts.organism) and vocab.knows_species(value)
    if axis == "tissues":
        return bool(v) and v == _ci(facts.tissue) and vocab.knows_tissue(value)
    if axis == "comparisons":
        return v in groups
    if axis == "conditions":
        return (v in groups or v == _ci(facts.condition)) and vocab.knows_condition(value)
    return False


def assess_scope_readiness(
    resolution: Any,
    source: Any = None,
    *,
    project_id: str,
    vocabulary: ScopeVocabulary | None = None,
) -> ScopeReadinessResult:
    """Run the local/offline scope-readiness preflight, fail-closed.

    A pure, deterministic function returning a bounded
    :class:`ScopeReadinessResult` (it never raises for a domain condition, never
    mutates its inputs, and performs no I/O, clock read, LLM/provider/ontology/
    search call, persistence, event emission, approval grant, or content egress).

    ``resolution`` is the already-inert WP-06e output being judged: a
    :class:`ScopeResolutionResult` or a faithful mapping projection of one (its
    ``to_dict()``).  ``source`` is an optional :class:`QuestionNormalizationResult`
    or draft ``ResearchSpec`` / mapping used only to cross-check that the resolution
    belongs to the same inert draft.  ``vocabulary`` must be the same synthetic
    vocabulary WP-06e resolved against, so traceability mirrors the exact production
    path.

    Precedence (fail closed at the first uncertainty; a scope only becomes
    ``ready_for_review`` when every check passes):

    1. **Project id** — an invalid ``project_id`` → ``rejected_inconsistent``.
    2. **Resolution shape** — anything that is not a ``ScopeResolutionResult`` or a
       faithful mapping projection → ``rejected_inconsistent``.
    3. **Upstream gate** — a non-``scope_draft_created`` resolution is carried
       through as the corresponding readiness pause: a support-scope stop stays
       ``stopped_by_upstream_gate``; a needs-clarification / unsupported scope stays
       ``clarification_required``; a missing / approval-needed policy stays
       ``approval_needed``; an upstream malformed reject stays
       ``rejected_inconsistent``.
    4. **Consistency** (``scope_draft_created`` only) — the bundle / report must be
       present, individually valid, ``draft``-status, non-authoritative; the
       research-spec / bundle / report ids must match (and match ``source`` when
       supplied); every populated axis value must be traceable to an explicit draft
       fact via the WP-06e path; an explicit draft fact that did not reach an axis
       must survive as an ``open`` ambiguity; and an empty scope can never be ready.
       Otherwise ``rejected_inconsistent`` with a specific reason code.
    """
    binding: dict[str, Any] = {
        "project_id": project_id,
        "resolution_kind": type(resolution).__name__,
        "source_kind": type(source).__name__,
    }

    def _result(
        code: str,
        message: str,
        *,
        scope_bundle: dict[str, Any] | None = None,
        ambiguity_report: dict[str, Any] | None = None,
        research_spec: dict[str, Any] | None = None,
        upstream_status: str = "",
        upstream_reason_code: str = "",
        findings: tuple[str, ...] = (),
    ) -> ScopeReadinessResult:
        return ScopeReadinessResult(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            scope_bundle=scope_bundle,
            ambiguity_report=ambiguity_report,
            research_spec=research_spec,
            upstream_status=upstream_status,
            upstream_reason_code=upstream_reason_code,
            findings=findings,
            binding=dict(binding),
        )

    # 1. Project id must be a valid identifier (fail closed before anything else).
    if common.validate_identifier(project_id, "project_id"):
        return _result(CODE_PROJECT_ID_MALFORMED, "project_id is missing or not a valid identifier (lowercase token, no whitespace)")

    # 2. The resolution must be a readable scope-resolution outcome.
    fields = _projection_fields(resolution)
    if fields is None:
        return _result(
            CODE_RESOLUTION_MALFORMED,
            f"resolution must be a ScopeResolutionResult or a faithful scope-resolution mapping projection, not {type(resolution).__name__}",
        )

    upstream_status = str(fields["status"])
    upstream_reason = str(fields["reason_code"])
    scope_bundle = fields["scope_bundle"]
    ambiguity_report = fields["ambiguity_report"]
    research_spec = fields["research_spec"]
    binding["upstream_status"] = upstream_status
    binding["upstream_reason_code"] = upstream_reason

    def _pass_through(code: str, message: str) -> ScopeReadinessResult:
        return _result(
            code,
            message,
            scope_bundle=scope_bundle,
            ambiguity_report=ambiguity_report,
            research_spec=research_spec,
            upstream_status=upstream_status,
            upstream_reason_code=upstream_reason,
        )

    # 2b. The upstream status/reason_code pair must be a bounded WP-06e outcome.
    # A faithful projection cannot pair a real status with an out-of-vocabulary or
    # mismatched reason code (e.g. a ``scope_draft_created`` status carrying anything
    # but ``SCOPE_DRAFT_CREATED``); such a pair fails closed rather than being judged.
    if (upstream_status, upstream_reason) not in _VALID_UPSTREAM_PAIRS:
        return _pass_through(
            CODE_RESOLUTION_MALFORMED,
            f"upstream status/reason_code pair ({upstream_status!r}, {upstream_reason!r}) is not a bounded WP-06e scope-resolution outcome; scope is not ready",
        )

    # 3. Carry a non-``scope_draft_created`` upstream verdict through verbatim.
    if upstream_status != SCOPE_STATUS_DRAFT_CREATED:
        if upstream_status == SCOPE_STATUS_STOPPED_BY_SUPPORT_SCOPE:
            return _pass_through(CODE_STOPPED_BY_UPSTREAM_GATE, f"upstream support-scope gate stopped the request ({upstream_reason}); scope is not ready")
        if upstream_status == SCOPE_STATUS_NEEDS_CLARIFICATION:
            return _pass_through(CODE_OPEN_AMBIGUITY, f"upstream scope resolution needs clarification ({upstream_reason}); scope stays paused and is not ready")
        if upstream_status == SCOPE_STATUS_UNSUPPORTED_SCOPE:
            return _pass_through(
                CODE_UNSUPPORTED_SCOPE, f"upstream scope resolution found an unsupported scope ({upstream_reason}); it stays an open ambiguity and is not ready"
            )
        if upstream_status == SCOPE_STATUS_APPROVAL_NEEDED:
            return _pass_through(CODE_APPROVAL_NEEDED, f"upstream policy gate requires human approval first ({upstream_reason}); scope is inert and not ready")
        if upstream_status == SCOPE_STATUS_REJECTED_MALFORMED:
            return _pass_through(CODE_UPSTREAM_REJECTED, f"upstream scope resolution rejected the request as malformed ({upstream_reason}); scope is not ready")
        # Any other bounded scope status is still not a draft, so it is not ready.
        return _pass_through(CODE_RESOLUTION_MALFORMED, f"upstream scope status {upstream_status!r} is not a draft-created outcome; scope is not ready")

    # 4. A ``scope_draft_created`` resolution must survive every consistency check.
    if not isinstance(scope_bundle, Mapping) or not isinstance(ambiguity_report, Mapping):
        return _pass_through(CODE_MISSING_PROJECTION, "a scope_draft_created resolution must carry both a scope_bundle and an ambiguity_report projection")
    if not isinstance(research_spec, Mapping):
        return _pass_through(CODE_MISSING_PROJECTION, "a scope_draft_created resolution must carry the considered draft research_spec to verify traceability")

    findings: list[str] = []

    # 4a0. An empty / wholly-unknown scope can never be ready (a specific reason
    # before the generic bundle validation, which would also reject it).
    if not any(isinstance(scope_bundle.get(axis), list) and any(isinstance(v, str) and v.strip() for v in scope_bundle.get(axis)) for axis in _SCOPE_AXES):
        return _pass_through(CODE_EMPTY_SCOPE, "scope_bundle has no populated axis; an empty or wholly-unknown scope can never be ready")

    # 4a. Each projection must individually validate as a well-formed object.
    bundle_errors = validate_scope_bundle(dict(scope_bundle))
    if bundle_errors:
        return _pass_through(CODE_SCOPE_BUNDLE_INVALID, "scope_bundle projection is not internally valid: " + "; ".join(bundle_errors))
    report_errors = validate_ambiguity_report(dict(ambiguity_report))
    if report_errors:
        return _pass_through(CODE_AMBIGUITY_REPORT_INVALID, "ambiguity_report projection is not internally valid: " + "; ".join(report_errors))

    # 4b. Both projections must remain inert ``draft`` review projections.
    if str(scope_bundle.get("status")) != REQUIRED_PROJECTION_STATUS or str(ambiguity_report.get("status")) != REQUIRED_PROJECTION_STATUS:
        return _pass_through(
            CODE_NON_DRAFT_PROJECTION,
            f"scope_bundle/ambiguity_report must both stay {REQUIRED_PROJECTION_STATUS!r} projections (got bundle={scope_bundle.get('status')!r}, report={ambiguity_report.get('status')!r})",
        )
    auth = _authoritative_findings(scope_bundle, "scope_bundle") + _authoritative_findings(ambiguity_report, "ambiguity_report")
    if auth:
        return _pass_through(CODE_AUTHORITATIVE_PROJECTION, "; ".join(auth))

    # 4c. Identifiers must match across research_spec / bundle / report (and source).
    spec_id = str(research_spec.get("research_spec_id", "") or "")
    bundle_id = str(scope_bundle.get("research_spec_id", "") or "")
    report_id = str(ambiguity_report.get("research_spec_id", "") or "")
    binding["research_spec_id"] = spec_id
    if not spec_id or common.validate_identifier(spec_id, "research_spec_id"):
        return _pass_through(CODE_IDENTIFIER_MISMATCH, "draft research_spec_id is missing or not a valid identifier; cannot anchor a scope readiness verdict")
    if bundle_id != spec_id or report_id != spec_id:
        return _pass_through(
            CODE_IDENTIFIER_MISMATCH,
            f"scope projection identifiers disagree (research_spec={spec_id!r}, scope_bundle={bundle_id!r}, ambiguity_report={report_id!r})",
        )
    source_id, source_error = _source_spec_id(source)
    if source_error is not None:
        return _pass_through(source_error, "the supplied source is not an inert draft matching this scope resolution")
    if source_id is not None:
        binding["source_research_spec_id"] = source_id
        if source_id and source_id != spec_id:
            return _pass_through(CODE_SOURCE_MISMATCH, f"source draft id {source_id!r} does not match the resolved scope draft id {spec_id!r}")

    # 4d. Traceability + no-silent-drop over the explicit draft facts.
    vocab = vocabulary if isinstance(vocabulary, ScopeVocabulary) else DEFAULT_VOCABULARY
    facts = _facts_from_spec(research_spec)
    open_subjects = {_ci(item.get("subject")) for item in ambiguity_report.get("items", []) if str(item.get("status")) == "open"}
    binding["open_ambiguity_subjects"] = sorted(open_subjects)

    for axis in _SCOPE_AXES:
        values = scope_bundle.get(axis) or []
        if not isinstance(values, list):
            return _pass_through(CODE_SCOPE_BUNDLE_INVALID, f"scope_bundle axis {axis!r} must be a list")
        for value in values:
            if not _axis_traceable(axis, value, facts, vocab):
                return _pass_through(
                    CODE_UNTRACEABLE_SCOPE,
                    f"scope_bundle {axis} value {value!r} is not traceable to an explicit draft fact via the WP-06e path; it must not appear on a ready scope",
                )

    # An explicit draft fact that did not reach an axis must survive as an open
    # ambiguity rather than silently disappearing.
    bundle_species = {_ci(v) for v in (scope_bundle.get("species") or [])}
    bundle_tissues = {_ci(v) for v in (scope_bundle.get("tissues") or [])}
    bundle_conditions = {_ci(v) for v in (scope_bundle.get("conditions") or [])}
    bundle_comparisons = {_ci(v) for v in (scope_bundle.get("comparisons") or [])}

    if _ci(facts.organism) and _ci(facts.organism) not in bundle_species and "organism" not in open_subjects:
        return _pass_through(CODE_DROPPED_UNKNOWN_AXIS, "the draft states an organism that is neither on the species axis nor kept as an open ambiguity")
    if _ci(facts.tissue) and _ci(facts.tissue) not in bundle_tissues and "tissue" not in open_subjects:
        return _pass_through(CODE_DROPPED_UNKNOWN_AXIS, "the draft states a tissue that is neither on the tissues axis nor kept as an open ambiguity")
    if _ci(facts.condition) and _ci(facts.condition) not in bundle_conditions and "condition" not in open_subjects:
        return _pass_through(CODE_DROPPED_UNKNOWN_AXIS, "the draft states a condition that is neither on the conditions axis nor kept as an open ambiguity")
    for group in facts.comparison_groups:
        g = _ci(group)
        if g and g not in bundle_comparisons and g not in bundle_conditions and "comparison" not in open_subjects and "condition" not in open_subjects:
            return _pass_through(
                CODE_DROPPED_UNKNOWN_AXIS, f"the draft states comparison group {group!r} that neither reached a scope axis nor stayed an open ambiguity"
            )

    binding["scope_axes_populated"] = {axis: bool(scope_bundle.get(axis)) for axis in _SCOPE_AXES}
    binding["open_ambiguity_count"] = len(open_subjects)
    findings.append("scope draft is internally consistent, non-authoritative, id-matched, fully traceable, and preserves every unknown as an open ambiguity")

    return _result(
        CODE_READY_FOR_REVIEW,
        "scope resolution is internally consistent and inert; the draft is ready for human review only (not an authorization to execute)",
        scope_bundle=scope_bundle,
        ambiguity_report=ambiguity_report,
        research_spec=research_spec,
        upstream_status=upstream_status,
        upstream_reason_code=upstream_reason,
        findings=tuple(findings),
    )


__all__ = [
    "STATUS_READY_FOR_REVIEW",
    "STATUS_CLARIFICATION_REQUIRED",
    "STATUS_STOPPED_BY_UPSTREAM_GATE",
    "STATUS_APPROVAL_NEEDED",
    "STATUS_REJECTED_INCONSISTENT",
    "STATUSES",
    "CODE_READY_FOR_REVIEW",
    "CODE_OPEN_AMBIGUITY",
    "CODE_UNSUPPORTED_SCOPE",
    "CODE_STOPPED_BY_UPSTREAM_GATE",
    "CODE_APPROVAL_NEEDED",
    "CODE_PROJECT_ID_MALFORMED",
    "CODE_RESOLUTION_MALFORMED",
    "CODE_UPSTREAM_REJECTED",
    "CODE_MISSING_PROJECTION",
    "CODE_SCOPE_BUNDLE_INVALID",
    "CODE_AMBIGUITY_REPORT_INVALID",
    "CODE_NON_DRAFT_PROJECTION",
    "CODE_AUTHORITATIVE_PROJECTION",
    "CODE_IDENTIFIER_MISMATCH",
    "CODE_SOURCE_MISMATCH",
    "CODE_UNTRACEABLE_SCOPE",
    "CODE_DROPPED_UNKNOWN_AXIS",
    "CODE_EMPTY_SCOPE",
    "REASON_CODES",
    "REQUIRED_PROJECTION_STATUS",
    "FORBIDDEN_PROJECTION_KEYS",
    "FORBIDDEN_AUTHORITY_FLAGS",
    "ScopeReadinessResult",
    "assess_scope_readiness",
]
