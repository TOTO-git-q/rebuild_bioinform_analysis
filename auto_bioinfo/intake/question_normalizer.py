"""Local deterministic Question Normalizer command contract (WP-06d / T-06-04).

The fourth *local* intake slice.  Where
:mod:`auto_bioinfo.intake.support_scope` (WP-06a) answers *"is this request
something this system may even attempt to plan?"*,
:mod:`auto_bioinfo.intake.multi_question` (WP-06b) answers *"does this single
request bundle more than one research question?"*, and
:mod:`auto_bioinfo.intake.policy_builder` (WP-06c) answers *"what is the initial
governance policy, and when must a human decide first?"*, this module answers the
next bounded question — *"given an in-scope single request and a usable initial
policy, what inert ``ResearchSpec`` draft can a deterministic offline normalizer
produce, while preserving the exact original text?"* — **before any ontology
scope resolution, dataset/literature search, approval grant, event emission, or
execution path can start**.

It is the local/offline slice of T-06-04 only.  The architecture's "Question
Normalizer command / Agent call" is realised here as a *deterministic in-process
fake/offline adapter* (:class:`OfflineQuestionNormalizerAdapter`): it is "rules
first", and a real external LLM/provider, if ever used later, would only
*suggest* — it is **not** used or authorised here.

Design constraints (WP-06d), mirroring the WP-06a/WP-06b/WP-06c/WP-04 contract
style:

- **Pure and deterministic.** :func:`normalize_question`, the offline adapter, and
  every helper is a total function of its explicit in-memory inputs.  There is no
  I/O whatsoever: no file access, no network/socket, no environment/credential
  inspection, **no real clock read**, no LLM / provider / model / SDK / tool call,
  no content egress, no subprocess, no threads, scheduler, queue, outbox, DB,
  event, audit log, report/index/cache, or any process side effect.  Inputs are
  never mutated in place.  The produced draft carries an empty ``created_at`` (no
  wall-clock timestamp), so two byte-identical inputs always yield a byte-identical
  result.
- **Reuse the upstream intake gates.** :func:`normalize_question` first defers to
  :func:`assess_intake` (which itself defers to :func:`classify_support_scope`).
  Any support-scope stop is preserved as a stop and produces **no** draft; a
  multi-question / split-suggestion request stays human-review oriented and is
  **never** auto-split into child projects; a needs-clarification request stays
  paused.  Only an in-scope, single-question request proceeds to the policy gate.
- **Fail closed on policy.** A missing policy, an inert *approval-needed*
  policy-builder result, a malformed/tampered policy, or a non-permitted (e.g.
  ``REAL``) execution mode each stays inert and **never** becomes an approval and
  **never** produces a draft.  A malformed truthy value such as the bool ``True``,
  the int ``1``, or the string ``"true"`` supplied where a policy is expected
  fails closed rather than being treated as a policy.
- **Preserve original facts.** When a draft is created it preserves *both* the
  exact original request text (verbatim, with its content hash) *and* a
  deterministic normalized-text representation, via the canonical
  :class:`OriginalRequest` ``with_normalized_text`` contract.  Unknown
  organism/tissue/condition/comparison facts are surfaced as ``open_questions`` or
  left as empty fields — they are **never** silently guessed.
- **Inert result only.** The outcome is reviewable data: a bounded
  :class:`QuestionNormalizationResult` carrying a ``ResearchSpec`` draft
  projection (``status == "draft"``), the preserved original/normalized request,
  the upstream assessment, and the considered policy.  It is **never** persisted,
  versioned, emitted as an event, enqueued, sent to a human or an external
  service, treated as authorization, or used to unblock any downstream workflow.
- **Bounded vocabulary.** The status is one of exactly five values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.

This module defines a *command contract* only.  It does not resolve scope /
ontology, build a ``ScopeBundle`` / persisted ``AmbiguityReport``, run an Approval
lifecycle, persist a version, emit an event, search any dataset/literature/API,
create a child project, run any pipeline stage transition, or perform scientific
analysis — those remain out of scope for T-06-04 (see WP-06e+ / T-06-05+).  A
``draft_created`` result is an inert reviewable draft, never a grant to execute.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.ids import hash_payload
from ..core.schemas import OriginalRequest, ProjectPolicy, ResearchSpec
from ..core.validation import validate_project_policy
from .multi_question import IntakeAssessment, assess_intake
from .policy_builder import PERMITTED_EXECUTION_MODES, PolicyBuildOutcome

# --- Bounded result statuses -------------------------------------------------
# Exactly five.  ``draft_created`` is the single proceed-with-data outcome (an
# inert ``ResearchSpec`` draft).  The other four are fail-closed / paused
# outcomes, none of which produce a draft.
STATUS_DRAFT_CREATED = "draft_created"
STATUS_STOPPED_BY_SUPPORT_SCOPE = "stopped_by_support_scope"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"
STATUS_APPROVAL_NEEDED = "approval_needed"
STATUS_REJECTED_MALFORMED = "rejected_malformed"

STATUSES = (
    STATUS_DRAFT_CREATED,
    STATUS_STOPPED_BY_SUPPORT_SCOPE,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_APPROVAL_NEEDED,
    STATUS_REJECTED_MALFORMED,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# draft_created:
CODE_DRAFT_CREATED = "NORMALIZE_DRAFT_CREATED"
# stopped_by_support_scope (preserves any WP-06a support-scope stop, including a
# malformed request):
CODE_STOPPED_BY_SUPPORT_SCOPE = "NORMALIZE_STOPPED_BY_SUPPORT_SCOPE"
# needs_clarification (human review; never auto-split / never a child project):
CODE_MULTI_QUESTION_REQUIRES_REVIEW = "NORMALIZE_MULTI_QUESTION_REQUIRES_REVIEW"
CODE_NEEDS_CLARIFICATION = "NORMALIZE_NEEDS_CLARIFICATION"
# approval_needed (the policy stays inert; never becomes an approval):
CODE_POLICY_MISSING = "NORMALIZE_POLICY_MISSING"
CODE_POLICY_APPROVAL_NEEDED = "NORMALIZE_POLICY_APPROVAL_NEEDED"
# rejected_malformed (fail closed on a malformed / non-permitted policy):
CODE_POLICY_MALFORMED = "NORMALIZE_POLICY_MALFORMED"
CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED = "NORMALIZE_POLICY_EXECUTION_MODE_NOT_PERMITTED"
CODE_PROJECT_ID_MALFORMED = "NORMALIZE_PROJECT_ID_MALFORMED"

REASON_CODES = (
    CODE_DRAFT_CREATED,
    CODE_STOPPED_BY_SUPPORT_SCOPE,
    CODE_MULTI_QUESTION_REQUIRES_REVIEW,
    CODE_NEEDS_CLARIFICATION,
    CODE_POLICY_MISSING,
    CODE_POLICY_APPROVAL_NEEDED,
    CODE_POLICY_MALFORMED,
    CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED,
    CODE_PROJECT_ID_MALFORMED,
)

# The status each reason code resolves to, so a future adapter can map a code to a
# status without re-deriving it.
_CODE_STATUS = {
    CODE_DRAFT_CREATED: STATUS_DRAFT_CREATED,
    CODE_STOPPED_BY_SUPPORT_SCOPE: STATUS_STOPPED_BY_SUPPORT_SCOPE,
    CODE_MULTI_QUESTION_REQUIRES_REVIEW: STATUS_NEEDS_CLARIFICATION,
    CODE_NEEDS_CLARIFICATION: STATUS_NEEDS_CLARIFICATION,
    CODE_POLICY_MISSING: STATUS_APPROVAL_NEEDED,
    CODE_POLICY_APPROVAL_NEEDED: STATUS_APPROVAL_NEEDED,
    CODE_POLICY_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED: STATUS_REJECTED_MALFORMED,
    CODE_PROJECT_ID_MALFORMED: STATUS_REJECTED_MALFORMED,
}

# The single status the produced draft carries; the command may never produce a
# resolved/locked spec.
DRAFT_STATUS = "draft"

# --- Deterministic, no-guess extraction --------------------------------------
# Conservative lexical extractors mirroring the "no business preset" rule of
# :class:`~auto_bioinfo.adapters.offline_planner.OfflineDeterministicPlanner`:
# they recognise only what the text explicitly states and record everything else
# as an ``open_question`` rather than inventing an organism, tissue, or contrast.
_VS_RE = re.compile(r"\b([\w-]+)\s+(?:vs\.?|versus)\s+([\w-]+)\b", re.IGNORECASE)
_BETWEEN_RE = re.compile(r"\bbetween\s+([\w-]+)\s+and\s+([\w-]+)\b", re.IGNORECASE)
# Neutral, explicitly-named organisms only; absence is left empty, never guessed.
_KNOWN_ORGANISMS = ("human", "mouse", "rat")


def _normalize_text(text: str) -> str:
    """Return a deterministic normalized view of ``text``.

    The normalisation is intentionally tiny and lossless-in-meaning: it strips
    leading/trailing whitespace and collapses every internal run of whitespace
    (spaces, tabs, newlines) to a single space.  It does **not** rewrite, drop, or
    reorder any word, lower-case content, or expand abbreviations — the exact
    original text is preserved separately and is the authority.  Being a pure
    function of ``text``, it is byte-deterministic.
    """
    return " ".join(text.split())


def _extract_comparison(text: str) -> list[str]:
    """Return an explicit two-group comparison from ``text``, else an empty list.

    Recognises only an explicit ``X vs Y`` / ``X versus Y`` or ``between X and Y``
    phrasing.  Anything else yields ``[]`` (surfaced as an open question); a
    comparison is never invented.
    """
    for regex in (_BETWEEN_RE, _VS_RE):
        match = regex.search(text)
        if match:
            return [match.group(1), match.group(2)]
    return []


def _detect_organism(text: str) -> str:
    """Return an explicitly-named known organism, else ``""`` (never guessed)."""
    for organism in _KNOWN_ORGANISMS:
        if re.search(rf"\b{organism}\b", text, re.IGNORECASE):
            return organism
    return ""


class OfflineQuestionNormalizerAdapter:
    """The deterministic in-process fake/offline "Agent call".

    This stands in for the architecture's LLM-backed Question Normalizer agent.
    It is intentionally rule-based and offline: :meth:`draft_research_spec` is a
    pure function of ``project_id`` and the already-normalized text, performs no
    network/socket call, no environment/credential read, no provider/SDK/model
    call, no clock read, and no randomness, and so the same input always yields
    the same draft.  It follows the "no business preset" rule — it extracts only
    what the text explicitly states and records every unknown organism / tissue /
    condition / comparison fact as an ``open_question`` rather than inventing one.
    """

    def draft_research_spec(self, project_id: str, normalized_text: str) -> dict[str, Any]:
        """Produce an inert :class:`ResearchSpec` *draft* projection.

        ``status`` is fixed to :data:`DRAFT_STATUS` and ``created_at`` is left
        empty (no wall-clock timestamp), so the draft is byte-deterministic and
        inert.  The draft is reviewable data only: it executes nothing, persists
        nothing, and grants nothing.
        """
        comparison = _extract_comparison(normalized_text)
        organism = _detect_organism(normalized_text)

        open_questions: list[str] = []
        if not comparison:
            open_questions.append("No explicit comparison groups detected in the request; left empty rather than assumed.")
        if not organism:
            open_questions.append("Organism not explicitly stated; left empty rather than assumed.")
        # Tissue/context is never extracted by this offline normalizer; it is left
        # for a later scope-resolution step rather than guessed here.
        open_questions.append("Tissue / context not extracted by the offline normalizer; left empty pending scope resolution.")

        spec = ResearchSpec(
            project_id=project_id,
            research_question=normalized_text,
            status=DRAFT_STATUS,
            created_at="",  # inert, deterministic — the draft carries no wall-clock timestamp
            organism=organism,
            condition_or_phenotype=" vs ".join(comparison) if comparison else "",
            comparison_groups=comparison,
            # An expression/intake-level question cannot, on its own, exceed
            # association level; this is the conservative ceiling, not a guess.
            max_claim_level="association",
            claim_ceiling="association",
            assumptions=[],
            open_questions=open_questions,
        )
        return spec.to_dict()


@dataclass(frozen=True)
class QuestionNormalizationResult:
    """The deterministic, reason-coded outcome of a Question Normalizer command.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  Exactly one proceed outcome (``draft_created``)
    carries a ``research_spec`` draft projection and the preserved
    ``original_request`` (verbatim original text + content hash + deterministic
    normalized text); every other (fail-closed / paused) outcome leaves both
    ``None``.  ``assessment`` preserves the upstream :class:`IntakeAssessment`
    projection verbatim (so any support-scope stop or multi-question signal is
    carried through and never hidden).  ``policy`` records the considered policy
    projection (the built policy for a draft, else ``None``), and
    ``approval_request`` carries an inert approval-needed projection when the
    policy fails closed to approval.  ``binding`` records the exact facts
    considered so the decision can be audited.  The result is inert reviewable
    data: it is never persisted, emitted, sent out, or treated as authorization.
    """

    status: str
    reason_code: str
    message: str
    research_spec: dict[str, Any] | None = None
    original_request: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    approval_request: dict[str, Any] | None = None
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def draft_created(self) -> bool:
        """The single proceed-with-data outcome (an inert ``ResearchSpec`` draft)."""
        return self.status == STATUS_DRAFT_CREATED

    @property
    def needs_clarification(self) -> bool:
        """A legitimate-but-paused outcome; the request is never auto-split."""
        return self.status == STATUS_NEEDS_CLARIFICATION

    @property
    def approval_needed(self) -> bool:
        """The fail-closed outcome for a missing / approval-needed policy."""
        return self.status == STATUS_APPROVAL_NEEDED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the result (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "draft_created": self.draft_created,
            "needs_clarification": self.needs_clarification,
            "approval_needed": self.approval_needed,
            "research_spec": copy.deepcopy(self.research_spec) if self.research_spec is not None else None,
            "original_request": copy.deepcopy(self.original_request) if self.original_request is not None else None,
            "assessment": copy.deepcopy(self.assessment) if self.assessment is not None else None,
            "policy": copy.deepcopy(self.policy) if self.policy is not None else None,
            "approval_request": copy.deepcopy(self.approval_request) if self.approval_request is not None else None,
            "binding": copy.deepcopy(self.binding),
        }


def _original_text(request: Any) -> str | None:
    """Return the request's original text for an accepted shape, else ``None``.

    Mirrors the shapes :func:`classify_support_scope` accepts (an
    :class:`OriginalRequest`, a bare ``str``, or a mapping with a string
    ``original_text``).  The request value is only read, never mutated.
    """
    if isinstance(request, OriginalRequest):
        text: Any = request.original_text
    elif isinstance(request, str):
        text = request
    elif isinstance(request, Mapping):
        text = request.get("original_text")
    else:
        return None
    return text if isinstance(text, str) else None


def _preserve_request(request: Any, *, project_id: str, request_id: str, original_text: str, normalized_text: str) -> dict[str, Any]:
    """Build a verbatim-preserving original-request projection.

    Uses the canonical :class:`OriginalRequest` contract so the exact original
    text and its content hash are preserved and a separate ``normalized_text`` is
    attached without ever touching the original.  When the caller already supplied
    an :class:`OriginalRequest`, its verbatim fields are preserved (its own
    ``submitted_at`` included); otherwise a clock-free request object is
    constructed (``submitted_at=""``) so the projection stays deterministic.  The
    caller's object is never mutated — :meth:`OriginalRequest.with_normalized_text`
    returns a fresh dict.
    """
    if isinstance(request, OriginalRequest):
        return request.with_normalized_text(normalized_text)
    constructed = OriginalRequest(
        project_id=project_id,
        original_text=original_text,
        request_id=request_id,
        submitted_at="",  # clock-free: the projection must be deterministic
    )
    return constructed.with_normalized_text(normalized_text)


def _resolve_policy(policy: Any) -> tuple[dict[str, Any] | None, tuple[str, str, dict[str, Any] | None] | None]:
    """Resolve the policy input; return ``(policy_dict, error)``.

    On success returns ``(policy_dict, None)`` for a usable *built* policy.  On a
    fail-closed condition returns ``(None, (code, message, approval_request))``
    where ``approval_request`` is an inert approval-needed projection (only for a
    policy-builder approval-needed result) or ``None``.

    Accepted inputs: a :class:`PolicyBuildOutcome` (the WP-06c policy-builder
    result), a :class:`ProjectPolicy`, or a policy ``Mapping`` (a
    ``ProjectPolicy.to_dict`` projection).  ``None`` is a missing policy.
    Anything else — including a malformed truthy value such as the bool ``True``,
    the int ``1``, or the string ``"true"`` — fails closed as malformed.
    """
    if policy is None:
        return (None, (CODE_POLICY_MISSING, "no policy supplied; a usable initial policy is required before a draft can be created", None))

    if isinstance(policy, PolicyBuildOutcome):
        if policy.approval_needed:
            return (
                None,
                (
                    CODE_POLICY_APPROVAL_NEEDED,
                    f"policy build requires human approval first ({policy.reason_code}); the request stays inert and no draft is created",
                    copy.deepcopy(policy.approval_request) if policy.approval_request is not None else None,
                ),
            )
        if not policy.built or policy.policy is None:
            return (None, (CODE_POLICY_MALFORMED, f"policy build did not produce a usable policy ({policy.reason_code})", None))
        policy_dict: dict[str, Any] = dict(policy.policy)
    elif isinstance(policy, ProjectPolicy):
        policy_dict = policy.to_dict()
    elif isinstance(policy, Mapping):
        # ``Mapping`` only (a dict-like ProjectPolicy projection).  A bare bool /
        # int / str / list supplied where a policy is expected is NOT a mapping and
        # falls through to the malformed branch below.
        policy_dict = dict(policy)
    else:
        return (None, (CODE_POLICY_MALFORMED, f"policy must be a PolicyBuildOutcome, a ProjectPolicy, or a policy mapping, not {type(policy).__name__}", None))

    # Validate the resolved policy with the existing WP-06c validator (required
    # fields, bounded execution mode / automation level / version, tamper-evident
    # id/hash).  A malformed/tampered policy fails closed.
    errors = validate_project_policy(policy_dict)
    if errors:
        return (None, (CODE_POLICY_MALFORMED, "; ".join(errors), None))

    # The normalizer is an inert, non-real slice; a REAL execution mode is a hard
    # stop it may never operate under, so it fails closed rather than draft under
    # a real-execution policy.
    if policy_dict.get("execution_mode") not in PERMITTED_EXECUTION_MODES:
        return (
            None,
            (
                CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED,
                f"policy execution_mode {policy_dict.get('execution_mode')!r} is not permitted for the offline normalizer (must be one of {PERMITTED_EXECUTION_MODES})",
                None,
            ),
        )

    return (policy_dict, None)


def normalize_question(
    request: Any,
    policy: Any,
    *,
    project_id: str,
    request_id: str = "",
    caller_facts: Mapping[str, Any] | None = None,
    adapter: OfflineQuestionNormalizerAdapter | None = None,
) -> QuestionNormalizationResult:
    """Run the local/offline Question Normalizer command, fail-closed.

    A pure, deterministic function returning a bounded
    :class:`QuestionNormalizationResult` (it never raises for a domain condition,
    never mutates its inputs, and performs no I/O, clock read, LLM/provider call,
    persistence, event emission, approval grant, or content egress).  ``request``
    is an :class:`OriginalRequest`, a bare ``str``, or a mapping with an
    ``original_text`` string; ``policy`` is a :class:`PolicyBuildOutcome`, a
    :class:`ProjectPolicy`, a policy mapping, or ``None``.  Precedence — the
    intake scope gate first, then the policy gate, so any uncertainty fails closed
    and no draft is created unless every gate passes:

    1. **Project id** — an invalid ``project_id`` → ``rejected_malformed``.
    2. **Support scope / multi-question** (reusing WP-06a/WP-06b via
       :func:`assess_intake`):
       - a support-scope stop (malformed / out-of-scope / unsupported-external /
         hard-stop request) → ``stopped_by_support_scope``, no draft;
       - a multi-question request → ``needs_clarification`` (human review), no
         draft, **never** an auto-split / child project;
       - a needs-clarification request → ``needs_clarification``, no draft.
    3. **Policy** (reusing WP-06c via :func:`validate_project_policy`):
       - missing → ``approval_needed`` (:data:`CODE_POLICY_MISSING`);
       - an approval-needed policy-builder result → ``approval_needed``, carrying
         the inert approval projection (never granted);
       - a malformed/tampered/non-permitted (e.g. ``REAL``) policy →
         ``rejected_malformed``.
    4. Otherwise run the deterministic offline adapter to produce an inert
       ``ResearchSpec`` draft (``status == "draft"``) that preserves both the
       exact original text and a deterministic normalized text → ``draft_created``.
    """
    binding: dict[str, Any] = {
        "project_id": project_id,
        "request_id": request_id,
        "input_kind": type(request).__name__,
        "policy_kind": type(policy).__name__,
    }

    def _result(
        code: str, message: str, *, assessment: dict[str, Any] | None = None, approval_request: dict[str, Any] | None = None
    ) -> QuestionNormalizationResult:
        return QuestionNormalizationResult(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            assessment=assessment,
            approval_request=approval_request,
            binding=dict(binding),
        )

    # 1. Project id must be a valid identifier (fail closed before anything else).
    from ..core import common

    if common.validate_identifier(project_id, "project_id"):
        return _result(CODE_PROJECT_ID_MALFORMED, "project_id is missing or not a valid identifier (lowercase token, no whitespace)")

    # 2. Support scope / multi-question gate (WP-06a + WP-06b).
    assessment: IntakeAssessment = assess_intake(request, caller_facts=caller_facts)
    assessment_dict = assessment.to_dict()
    binding["support_scope_classification"] = assessment.support_scope.get("classification")
    binding["assessment"] = assessment.assessment

    if not assessment.generated:
        # A support-scope stop was preserved (no assessment generated).
        return _result(
            CODE_STOPPED_BY_SUPPORT_SCOPE,
            f"intake support scope stopped the request ({assessment.support_scope.get('reason_code')}); no research-spec draft created",
            assessment=assessment_dict,
        )
    if assessment.multi_question:
        return _result(
            CODE_MULTI_QUESTION_REQUIRES_REVIEW,
            "request appears to contain multiple research questions; it requires human review and is not auto-split or drafted",
            assessment=assessment_dict,
        )
    if assessment.needs_clarification:
        return _result(
            CODE_NEEDS_CLARIFICATION,
            "request needs human clarification before a draft can be created; it is not drafted",
            assessment=assessment_dict,
        )

    # 3. Policy gate (WP-06c). Fail closed on missing / approval-needed / malformed.
    policy_dict, policy_error = _resolve_policy(policy)
    if policy_error is not None:
        code, message, approval_request = policy_error
        return _result(code, message, assessment=assessment_dict, approval_request=approval_request)
    assert policy_dict is not None

    # 4. Produce the inert draft via the deterministic offline adapter.
    original_text = _original_text(request)
    # Support scope already validated the text is a printable string; fall back to
    # a bounded empty string only for defensive safety.
    original_text = original_text if isinstance(original_text, str) else ""
    normalized_text = _normalize_text(original_text)

    normalizer = adapter or OfflineQuestionNormalizerAdapter()
    research_spec = normalizer.draft_research_spec(project_id, normalized_text)
    original_request = _preserve_request(
        request,
        project_id=project_id,
        request_id=request_id,
        original_text=original_text,
        normalized_text=normalized_text,
    )

    binding["normalized_text"] = normalized_text
    binding["original_text_sha256"] = hash_payload(original_text)
    binding["research_spec_id"] = research_spec.get("research_spec_id")
    binding["policy_execution_mode"] = policy_dict.get("execution_mode")
    binding["policy_data_sensitivity"] = policy_dict.get("data_sensitivity")

    return QuestionNormalizationResult(
        status=STATUS_DRAFT_CREATED,
        reason_code=CODE_DRAFT_CREATED,
        message="offline question normalizer produced an inert research-spec draft preserving the original and normalized text",
        research_spec=research_spec,
        original_request=original_request,
        assessment=assessment_dict,
        policy=copy.deepcopy(policy_dict),
        binding=dict(binding),
    )


__all__ = [
    "STATUS_DRAFT_CREATED",
    "STATUS_STOPPED_BY_SUPPORT_SCOPE",
    "STATUS_NEEDS_CLARIFICATION",
    "STATUS_APPROVAL_NEEDED",
    "STATUS_REJECTED_MALFORMED",
    "STATUSES",
    "CODE_DRAFT_CREATED",
    "CODE_STOPPED_BY_SUPPORT_SCOPE",
    "CODE_MULTI_QUESTION_REQUIRES_REVIEW",
    "CODE_NEEDS_CLARIFICATION",
    "CODE_POLICY_MISSING",
    "CODE_POLICY_APPROVAL_NEEDED",
    "CODE_POLICY_MALFORMED",
    "CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED",
    "CODE_PROJECT_ID_MALFORMED",
    "REASON_CODES",
    "DRAFT_STATUS",
    "OfflineQuestionNormalizerAdapter",
    "QuestionNormalizationResult",
    "normalize_question",
]
