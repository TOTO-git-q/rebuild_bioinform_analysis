"""Local deterministic multi-research-question detection (WP-06b / T-06-02).

The second *local* intake slice.  Where :mod:`auto_bioinfo.intake.support_scope`
(WP-06a) answers *"is this request something this system may even attempt to
plan?"*, this module answers the next bounded question — *"does this single
request appear to bundle more than one research question, and if so what inert
split suggestions could a human review?"* — **before any question normalisation,
ontology scope resolution, dataset/literature search, ResearchSpec creation, or
execution path can start**.

It is deliberately tiny and "deterministic rules first": an LLM, if ever used
later, would only *suggest* at most, and is **not** used or authorised here.

Design constraints (WP-06b), mirroring the WP-06a / WP-04 contract style:

- **Pure and deterministic.** :func:`assess_intake` and every helper is a total
  function of its explicit in-memory inputs.  There is no I/O whatsoever: no file
  access, no network, no environment inspection, **no real clock**, no LLM /
  provider / model call, no content egress, no threads, scheduler, queue, DB,
  outbox, or process side effect.  Inputs are never mutated in place.
- **Never auto-split.** This is the hard boundary of T-06-02: the assessment may
  *suggest* a split for human review, but it **never** creates a sub-request, a
  child project, a project id, a ``ResearchSpec``, a ``SubQuestion``, a task, an
  event, a file, a queue message, a DB row, or any executable plan.  A
  :class:`SplitSuggestion` is an inert bounded text snippet/label/reason and
  nothing more.
- **Preserve original text.** The request text is never rewritten, normalised, or
  deleted, and ambiguity is never hidden.  A split *suggestion* snippet is a
  bounded slice of the original text shown verbatim for human review; the request
  itself is only read.
- **Fail closed via support scope.** :func:`assess_intake` first defers to
  :func:`classify_support_scope`.  If that support-scope decision is anything
  other than ``supported`` or ``needs_clarification`` (i.e. a malformed,
  out-of-scope, unsupported-external-action, or unsupported-non-bioinformatics
  stop, including every governance / real-human-data hard stop), the assessment
  preserves that stop and generates **no** split artifacts.
- **Bounded vocabulary.** The assessment is one of exactly four values
  (:data:`ASSESSMENTS`) and the reason is one of a small, stable set of codes
  (:data:`ASSESSMENT_REASON_CODES`).  Callers branch on the machine-readable
  code, never the human message.

This module defines a *detection / suggestion contract* only.  It does not
normalise the question, build a ``ResearchSpec`` / ``AmbiguityReport`` /
``ScopeBundle``, call a Question Normalizer / Scope Resolver / Agent /
PromptRegistry prompt, resolve an ontology, search any dataset/literature/API,
create an approval, emit an event, or persist anything — those remain out of
scope (see WP-06c+).  An :class:`IntakeAssessment` is an inert advisory value,
never a grant to execute and never an automatic split.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.schemas import OriginalRequest
from .support_scope import IntakeDecision, classify_support_scope

# --- Bounds ------------------------------------------------------------------
# At most this many inert split suggestions are returned; a pathological input
# with very many boundaries cannot inflate the assessment without bound.
MAX_SPLIT_SUGGESTIONS = 8
# Each suggestion snippet is capped (and ellipsised when truncated) so the
# assessment stays bounded even for a long request.
MAX_SNIPPET_LENGTH = 280
# Marker lists recorded in the audit binding are capped likewise.
_MAX_BINDING_MARKERS = 32
# Two or more question marks is treated as a multi-question signal.
MIN_QUESTION_MARKS = 2
# Two or more distinct analysis topics (as detected by WP-06a) is a signal.
MIN_DISTINCT_TOPICS = 2

# --- Deterministic separator markers -----------------------------------------
# *Strong* separators rarely occur inside a single bioinformatics question and so
# are treated as a multi-question signal on their own.  They are also the only
# tokens used to cut inert split-suggestion snippets.  Kept conservative on
# purpose: ambiguous conjunctions such as a bare "and"/"both"/"then" are NOT here
# because they routinely appear inside one question ("treated and control",
# "both groups", "align then count").
_STRONG_SEPARATOR_MARKERS = (
    "and also",
    "separately",
    "as well as",
    "in addition to",
    "additionally",
    "as a separate",
    "second question",
    "another question",
)
# *Weak* sequence markers are recorded in the binding for a human reviewer but are
# never, on their own, treated as a multi-question signal (they too often mark a
# single ordered pipeline rather than two distinct questions).
_WEAK_SEQUENCE_MARKERS = (
    "then",
    "both",
    "afterwards",
    "after that",
    "next",
)

# A boundary is a question mark or any strong separator.  Used only to cut inert
# suggestion snippets out of the *original* text; the request itself is untouched.
_BOUNDARY_RE = re.compile(
    r"\?|" + r"|".join(re.escape(m) for m in _STRONG_SEPARATOR_MARKERS),
    re.IGNORECASE,
)

# --- Bounded assessment vocabulary -------------------------------------------
ASSESS_SINGLE_QUESTION = "single_question"
ASSESS_MULTI_QUESTION = "multi_question"
ASSESS_NEEDS_CLARIFICATION = "needs_clarification"
ASSESS_NOT_GENERATED = "not_generated"

ASSESSMENTS = (
    ASSESS_SINGLE_QUESTION,
    ASSESS_MULTI_QUESTION,
    ASSESS_NEEDS_CLARIFICATION,
    ASSESS_NOT_GENERATED,
)

# --- Stable reason codes -----------------------------------------------------
CODE_SINGLE_QUESTION = "INTAKE_ASSESS_SINGLE_QUESTION"
CODE_MULTI_QUESTION = "INTAKE_ASSESS_MULTI_QUESTION"
CODE_NEEDS_CLARIFICATION = "INTAKE_ASSESS_NEEDS_CLARIFICATION"
CODE_STOPPED_BY_SUPPORT_SCOPE = "INTAKE_ASSESS_STOPPED_BY_SUPPORT_SCOPE"

ASSESSMENT_REASON_CODES = (
    CODE_SINGLE_QUESTION,
    CODE_MULTI_QUESTION,
    CODE_NEEDS_CLARIFICATION,
    CODE_STOPPED_BY_SUPPORT_SCOPE,
)

# The assessment value each reason code resolves to.
_ASSESS_CODE_CLASS = {
    CODE_SINGLE_QUESTION: ASSESS_SINGLE_QUESTION,
    CODE_MULTI_QUESTION: ASSESS_MULTI_QUESTION,
    CODE_NEEDS_CLARIFICATION: ASSESS_NEEDS_CLARIFICATION,
    CODE_STOPPED_BY_SUPPORT_SCOPE: ASSESS_NOT_GENERATED,
}


# --- Small, pure predicates --------------------------------------------------


def _matches(lowered: str, markers: tuple[str, ...]) -> list[str]:
    """Return the sorted, de-duplicated, bounded markers present in ``lowered``."""
    return sorted({m for m in markers if m in lowered})[:_MAX_BINDING_MARKERS]


def _request_text(request: Any) -> str | None:
    """Return the request's text for an accepted shape, else ``None``.

    Mirrors the shapes :func:`classify_support_scope` accepts (an
    :class:`OriginalRequest`, a bare ``str``, or a mapping with a string
    ``original_text``).  Only used to cut inert suggestion snippets *after* the
    support-scope decision has already confirmed the text is a valid printable
    string; the request value is only read, never mutated.
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


def _split_suggestions(text: str) -> tuple[SplitSuggestion, ...]:
    """Cut bounded, inert candidate snippets out of the *original* text.

    Splits on question marks and strong separators only.  Each snippet is a
    verbatim, whitespace-trimmed, length-capped slice of the original text — never
    a rewritten, normalised, or executable artifact.  Returns at most
    :data:`MAX_SPLIT_SUGGESTIONS` suggestions; an empty tuple when no clean
    boundary exists (a multi-question request can still be flagged on topic count
    alone, with no snippet to offer).
    """
    segments = [seg.strip() for seg in _BOUNDARY_RE.split(text)]
    segments = [seg for seg in segments if seg]
    # Only worth suggesting a split when the boundaries actually carve the text
    # into more than one non-empty part; a single part is just the whole request.
    if len(segments) < 2:
        return ()
    suggestions: list[SplitSuggestion] = []
    for index, segment in enumerate(segments[:MAX_SPLIT_SUGGESTIONS]):
        snippet = segment
        if len(snippet) > MAX_SNIPPET_LENGTH:
            snippet = snippet[: MAX_SNIPPET_LENGTH - 1].rstrip() + "…"
        suggestions.append(
            SplitSuggestion(
                index=index,
                label=f"candidate-{index + 1}",
                snippet=snippet,
                reason="candidate distinct research question for human review; not an automatic split",
            )
        )
    return tuple(suggestions)


# --- Inert split suggestion --------------------------------------------------


@dataclass(frozen=True)
class SplitSuggestion:
    """An inert, bounded split suggestion for human review.

    It is *only* text: an ordinal ``index``, a short ``label``, a verbatim bounded
    ``snippet`` of the original request, and a human ``reason``.  It is **not** an
    :class:`OriginalRequest`, a sub-request, a project id, a ``ResearchSpec``, a
    ``SubQuestion``, a task, an event, a file, a queue message, or any executable
    plan, and it carries no authority to split or execute anything.
    """

    index: int
    label: str
    snippet: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the suggestion (stable key order)."""
        return {
            "index": self.index,
            "label": self.label,
            "snippet": self.snippet,
            "reason": self.reason,
        }


# --- The deterministic intake assessment -------------------------------------


@dataclass(frozen=True)
class IntakeAssessment:
    """The deterministic, reason-coded outcome of a multi-question assessment.

    ``assessment`` is one of :data:`ASSESSMENTS`; ``reason_code`` is one of
    :data:`ASSESSMENT_REASON_CODES`.  ``support_scope`` preserves the upstream
    :class:`IntakeDecision` projection verbatim, so any support-scope stop is
    carried through and never hidden.  ``split_suggestions`` is a (possibly empty)
    tuple of inert :class:`SplitSuggestion` values — present only for a
    ``multi_question`` assessment and never an automatic split.  ``binding``
    records the exact facts considered so the assessment can be audited.  The
    assessment is an inert advisory value: it stores no claim, never authorises
    execution, and never creates a sub-request or child project.
    """

    assessment: str
    reason_code: str
    message: str
    support_scope: dict[str, Any]
    split_suggestions: tuple[SplitSuggestion, ...] = ()
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def multi_question(self) -> bool:
        """True iff the request appears to bundle more than one research question."""
        return self.assessment == ASSESS_MULTI_QUESTION

    @property
    def needs_clarification(self) -> bool:
        """A legitimate-but-paused outcome; the request is never auto-split."""
        return self.assessment == ASSESS_NEEDS_CLARIFICATION

    @property
    def generated(self) -> bool:
        """False iff support scope stopped the request before any assessment."""
        return self.assessment != ASSESS_NOT_GENERATED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the assessment (stable key order)."""
        return {
            "assessment": self.assessment,
            "reason_code": self.reason_code,
            "message": self.message,
            "multi_question": self.multi_question,
            "needs_clarification": self.needs_clarification,
            "generated": self.generated,
            "support_scope": dict(self.support_scope),
            "split_suggestions": [s.to_dict() for s in self.split_suggestions],
            "binding": dict(self.binding),
        }


def assess_intake(request: Any, *, caller_facts: Mapping[str, Any] | None = None) -> IntakeAssessment:
    """Assess whether a request bundles multiple research questions, fail-closed.

    A pure, deterministic function returning a bounded :class:`IntakeAssessment`
    (it never raises for a domain condition, never mutates its inputs, never
    splits the request, and performs no I/O, clock read, LLM/provider call, or
    content egress).  Steps:

    1. **Support scope first.** Defer to :func:`classify_support_scope`.  If its
       decision is anything other than ``supported`` or ``needs_clarification``
       (every malformed / out-of-scope / unsupported-external-action /
       unsupported-non-bioinformatics / hard-stop outcome), preserve that stop:
       return ``not_generated`` (:data:`CODE_STOPPED_BY_SUPPORT_SCOPE`) with **no**
       split suggestions.
    2. **Detect.** Otherwise, deterministically look for multi-question signals in
       the original text: two or more question marks, a strong explicit separator
       (e.g. ``and also`` / ``separately`` / ``as well as``), and/or two or more
       distinct analysis topics (reusing the WP-06a topic detection).
    3. **Classify.**

       - any multi-question signal → ``multi_question``
         (:data:`CODE_MULTI_QUESTION`) with inert, bounded split *suggestions*
         (never an automatic split);
       - else, if support scope already flagged ``needs_clarification`` →
         ``needs_clarification`` (:data:`CODE_NEEDS_CLARIFICATION`), no split;
       - else → ``single_question`` (:data:`CODE_SINGLE_QUESTION`), no split.
    """
    support = classify_support_scope(request, caller_facts=caller_facts)
    support_dict = support.to_dict()

    def _build(code: str, message: str, *, signals: dict[str, Any], suggestions: tuple[SplitSuggestion, ...] = ()) -> IntakeAssessment:
        binding: dict[str, Any] = {
            "support_scope_classification": support.classification,
            "support_scope_reason_code": support.reason_code,
            "input_kind": support.binding.get("input_kind"),
            "text_length": support.binding.get("text_length"),
            "detected_topics": list(support.binding.get("detected_topics", [])),
            "signals": signals,
            "suggestion_count": len(suggestions),
        }
        return IntakeAssessment(
            assessment=_ASSESS_CODE_CLASS[code],
            reason_code=code,
            message=message,
            support_scope=support_dict,
            split_suggestions=suggestions,
            binding=binding,
        )

    # 1. Preserve any support-scope stop (anything that is neither a proceed nor a
    #    legitimate paused-for-clarification outcome). No assessment is generated.
    if not (support.supported or support.needs_clarification):
        return _build(
            CODE_STOPPED_BY_SUPPORT_SCOPE,
            f"intake support scope stopped the request ({support.reason_code}); no multi-question assessment generated",
            signals={},
        )

    # 2. Detect multi-question signals from the original text. The text is a valid
    #    printable string here (support scope already validated it); fall back to a
    #    bounded empty string only for defensive safety.
    text = _request_text(request) or ""
    lowered = text.lower()
    question_mark_count = text.count("?")
    strong_separators = _matches(lowered, _STRONG_SEPARATOR_MARKERS)
    weak_sequence_markers = _matches(lowered, _WEAK_SEQUENCE_MARKERS)
    detected_topics = list(support.binding.get("detected_topics", []))

    multiple_question_marks = question_mark_count >= MIN_QUESTION_MARKS
    multiple_topics = len(detected_topics) >= MIN_DISTINCT_TOPICS
    has_strong_separator = bool(strong_separators)

    signals = {
        "question_mark_count": question_mark_count,
        "multiple_question_marks": multiple_question_marks,
        "multiple_topics": multiple_topics,
        "strong_separators": strong_separators,
        "has_strong_separator": has_strong_separator,
        "weak_sequence_markers": weak_sequence_markers,
    }

    # 3. Classify (multi-question first; never auto-split).
    if multiple_question_marks or multiple_topics or has_strong_separator:
        suggestions = _split_suggestions(text)
        return _build(
            CODE_MULTI_QUESTION,
            "request appears to contain multiple research questions; inert split suggestions are offered for human review (it is not auto-split)",
            signals=signals,
            suggestions=suggestions,
        )
    if support.needs_clarification:
        return _build(
            CODE_NEEDS_CLARIFICATION,
            "request needs human clarification before planning; it is not auto-split",
            signals=signals,
        )
    return _build(
        CODE_SINGLE_QUESTION,
        "request appears to be a single research question; no split suggested",
        signals=signals,
    )


__all__ = [
    "MAX_SPLIT_SUGGESTIONS",
    "MAX_SNIPPET_LENGTH",
    "MIN_QUESTION_MARKS",
    "MIN_DISTINCT_TOPICS",
    "ASSESS_SINGLE_QUESTION",
    "ASSESS_MULTI_QUESTION",
    "ASSESS_NEEDS_CLARIFICATION",
    "ASSESS_NOT_GENERATED",
    "ASSESSMENTS",
    "CODE_SINGLE_QUESTION",
    "CODE_MULTI_QUESTION",
    "CODE_NEEDS_CLARIFICATION",
    "CODE_STOPPED_BY_SUPPORT_SCOPE",
    "ASSESSMENT_REASON_CODES",
    "SplitSuggestion",
    "IntakeAssessment",
    "IntakeDecision",
    "assess_intake",
]
