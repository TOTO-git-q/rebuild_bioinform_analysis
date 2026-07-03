"""Local deterministic sub-question decomposition command contract (WP-07 / T-07-01,03,05).

The first *local* research-planning slice.  Where the WP-06 intake modules answer
*"is this request something we may even attempt to plan, and what inert draft
``ResearchSpec`` / ``ScopeBundle`` can a deterministic offline component
propose?"*, this module answers the next bounded question — *"given a frozen
inert draft ``ResearchSpec`` (and, optionally, its resolved ``ScopeBundle``), what
inert draft ``SubQuestion`` projections can a deterministic offline decomposer
derive from the **explicit** facts alone, each expressing exactly one
relationship, none exceeding the parent scope, and each carrying a deterministic
priority, an allowed claim level capped at the parent ceiling, and a coverage
status?"* — **before any real search, dataset/literature acquisition, dependency
planning, approval grant, event emission, persistence, or pipeline transition can
start**.

It is the local/offline slice of T-07-01 (deterministic decomposition rules),
T-07-03 (the single-relationship / scope semantic check) and T-07-05 (priority /
allowed-claim-level / coverage assignment) only.

Design constraints (WP-07), mirroring the WP-06 contract style:

- **Pure and deterministic.** :func:`decompose_research_spec` and every helper is
  a total function of its explicit in-memory inputs.  There is no I/O whatsoever:
  no file access, no network/socket, no environment/credential inspection, **no
  clock read**, no LLM / provider / model / SDK / tool call, no content egress, no
  subprocess, no threads, scheduler, queue, outbox, DB, event, audit log, report
  or cache, or any process side effect.  Inputs are never mutated in place.
  Produced ``SubQuestion`` projections carry an empty ``created_at`` (no wall-clock
  timestamp), so byte-identical inputs always yield a byte-identical result.
- **No-guess decomposition.** A candidate sub-question is derived **only** from
  facts the draft explicitly states — its ``research_question``, its explicit
  ``primary_endpoints`` and its explicit two-group-or-more ``comparison_groups``.
  The decomposer never invents a relationship, a comparison, or a scope the draft
  did not state.  A draft that expresses only a single relationship yields a single
  sub-question (splitting is never forced); a draft that states no explicitly
  decomposable fact yields ``needs_clarification`` (never a fabricated
  sub-question).
- **Single-relationship, scope-bounded semantic check.** Every proposed
  sub-question must express exactly one primary relationship
  (:func:`auto_bioinfo.core.validation.subquestion_is_single_purpose`, reused via
  :func:`auto_bioinfo.core.validation.validate_subquestion`) and its scope must not
  exceed the parent's scope (the parent ``ResearchSpec`` and, when supplied, the
  resolved ``ScopeBundle``).  A compound sub-question that cannot be split, or one
  whose scope exceeds the parent, is **rejected with a reason code** — never
  silently recorded.
- **Ceiling-respecting assignment.** Each sub-question is assigned a deterministic
  ``priority`` (its stable position, lower first), an ``allowed_claim_level`` and a
  ``coverage`` status.  The allowed claim level is capped at the parent draft's
  ``claim_ceiling`` (falling back to ``max_claim_level``) using the
  :data:`auto_bioinfo.core.schemas.CLAIM_LEVELS` ordering: a sub-question whose
  implied claim would exceed the parent ceiling is **capped to the ceiling**
  (recorded), never allowed to exceed it.
- **Inert, non-authoritative result only.** The outcome is reviewable data: a
  bounded :class:`DecompositionResult` carrying in-memory ``SubQuestion`` *draft*
  projections (``status == "draft"``) and their assignment records.  It is
  **never** persisted, versioned, emitted as an event, enqueued, sent to a human or
  an external service, marked authoritative, treated as an approval, or used to
  unblock any downstream workflow or pipeline stage.  It creates no child project
  and splits nothing in the real system.
- **Bounded vocabulary.** The status is one of exactly five values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.

This module defines a *command contract* only.  It does not build a dependency
graph, plan evidence, run any search, persist or version a ``SubQuestion``, run an
Approval lifecycle, emit an event, create a child project, run any pipeline stage
transition, or perform scientific analysis — those remain out of scope for
T-07-01/03/05 (see the rest of WP-07+).  A ``decomposed`` result is an inert
reviewable projection, never a grant to execute.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core import common
from ..core.ids import make_stable_id
from ..core.schemas import CLAIM_LEVELS, ResearchSpec, ScopeBundle, SubQuestion
from ..core.validation import validate_subquestion

# --- Bounded result statuses -------------------------------------------------
# Exactly five.  ``decomposed`` is the single proceed-with-data outcome (inert
# ``SubQuestion`` draft projections).  The other four are fail-closed / paused
# outcomes, none of which produce any sub-question.
STATUS_DECOMPOSED = "decomposed"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"
STATUS_REJECTED_COMPOUND = "rejected_compound"
STATUS_SCOPE_EXCEEDS_PARENT = "scope_exceeds_parent"
STATUS_REJECTED_MALFORMED = "rejected_malformed"

STATUSES = (
    STATUS_DECOMPOSED,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_REJECTED_COMPOUND,
    STATUS_SCOPE_EXCEEDS_PARENT,
    STATUS_REJECTED_MALFORMED,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# decomposed:
CODE_DECOMPOSED = "DECOMP_SUBQUESTIONS_CREATED"
# needs_clarification (nothing explicitly decomposable; never auto-fabricated):
CODE_NEEDS_CLARIFICATION = "DECOMP_NO_DECOMPOSABLE_FACT"
# rejected_compound (a candidate expresses more than one relationship and cannot
# be split deterministically — it is rejected, never silently recorded):
CODE_COMPOUND_SUBQUESTION = "DECOMP_COMPOUND_SUBQUESTION"
# scope_exceeds_parent (a candidate's scope exceeds the parent ResearchSpec /
# resolved ScopeBundle scope):
CODE_SCOPE_EXCEEDS_PARENT = "DECOMP_SCOPE_EXCEEDS_PARENT"
# rejected_malformed (fail closed on a malformed spec / scope / claim level):
CODE_SPEC_MALFORMED = "DECOMP_SPEC_MALFORMED"
CODE_SCOPE_MALFORMED = "DECOMP_SCOPE_MALFORMED"
CODE_CLAIM_LEVEL_MALFORMED = "DECOMP_CLAIM_LEVEL_MALFORMED"
CODE_SUBQUESTION_INVALID = "DECOMP_SUBQUESTION_INVALID"

REASON_CODES = (
    CODE_DECOMPOSED,
    CODE_NEEDS_CLARIFICATION,
    CODE_COMPOUND_SUBQUESTION,
    CODE_SCOPE_EXCEEDS_PARENT,
    CODE_SPEC_MALFORMED,
    CODE_SCOPE_MALFORMED,
    CODE_CLAIM_LEVEL_MALFORMED,
    CODE_SUBQUESTION_INVALID,
)

# The status each reason code resolves to, so a future adapter can map a code to a
# status without re-deriving it.
_CODE_STATUS = {
    CODE_DECOMPOSED: STATUS_DECOMPOSED,
    CODE_NEEDS_CLARIFICATION: STATUS_NEEDS_CLARIFICATION,
    CODE_COMPOUND_SUBQUESTION: STATUS_REJECTED_COMPOUND,
    CODE_SCOPE_EXCEEDS_PARENT: STATUS_SCOPE_EXCEEDS_PARENT,
    CODE_SPEC_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_SCOPE_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_CLAIM_LEVEL_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_SUBQUESTION_INVALID: STATUS_REJECTED_MALFORMED,
}

# The single status the produced sub-questions carry; the command may never
# produce a locked / authoritative sub-question.
DRAFT_STATUS = "draft"

# --- Bounded coverage vocabulary ---------------------------------------------
# How completely each sub-question's relationship is anchored by explicit facts.
COVERAGE_COVERED = "covered"
COVERAGE_PARTIAL = "partial"
COVERAGE_STATUSES = (COVERAGE_COVERED, COVERAGE_PARTIAL)

# The claim level a candidate *implies* before it is capped at the parent ceiling.
# A comparison/differential relationship implies at most an association-level
# claim; a bare descriptive endpoint implies only a descriptive claim.  These are
# never allowed to exceed the parent ceiling (see :func:`_cap_claim_level`).
IMPLIED_COMPARISON_CLAIM = "association"
IMPLIED_DESCRIPTIVE_CLAIM = "descriptive"

# The default parent ceiling when the draft states none.
DEFAULT_CLAIM_CEILING = "association"


@dataclass(frozen=True)
class _Candidate:
    """A deterministic candidate sub-question derived from the explicit facts.

    Every field is derived only from facts the draft explicitly states; nothing
    here is inferred or invented.
    """

    question: str
    purpose: str
    evidence_type: str
    groups: tuple[str, ...]
    implied_claim: str
    coverage: str


@dataclass(frozen=True)
class DecompositionResult:
    """The deterministic, reason-coded outcome of a decomposition command.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  Exactly one proceed outcome (``decomposed``) carries
    non-empty ``subquestions`` (inert ``SubQuestion`` draft projections) and
    ``assignments`` (the per-sub-question priority / allowed_claim_level / coverage
    records).  ``research_spec`` records the considered inert draft,
    ``parent_claim_ceiling`` the ceiling every allowed claim level was capped
    against, ``coverage`` the overall coverage summary, and ``capped`` whether any
    sub-question's implied claim was capped down to the ceiling.  ``binding``
    records the exact facts considered so the decision can be audited.  The result
    is inert reviewable data: it is never persisted, versioned, emitted, sent out,
    marked authoritative, or treated as authorization.
    """

    status: str
    reason_code: str
    message: str
    subquestions: list[dict[str, Any]] = field(default_factory=list)
    assignments: list[dict[str, Any]] = field(default_factory=list)
    research_spec: dict[str, Any] | None = None
    parent_claim_ceiling: str = ""
    coverage: str = ""
    capped: bool = False
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def decomposed(self) -> bool:
        """The single proceed-with-data outcome (inert ``SubQuestion`` drafts)."""
        return self.status == STATUS_DECOMPOSED

    @property
    def needs_clarification(self) -> bool:
        """A legitimate-but-paused outcome; nothing is auto-fabricated."""
        return self.status == STATUS_NEEDS_CLARIFICATION

    @property
    def rejected(self) -> bool:
        """A fail-closed outcome (compound, scope-exceeds, or malformed)."""
        return self.status in (STATUS_REJECTED_COMPOUND, STATUS_SCOPE_EXCEEDS_PARENT, STATUS_REJECTED_MALFORMED)

    @property
    def subquestion_count(self) -> int:
        return len(self.subquestions)

    @property
    def subquestion_ids(self) -> list[str]:
        return [str(sq.get("subquestion_id", "")) for sq in self.subquestions]

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the result (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "decomposed": self.decomposed,
            "needs_clarification": self.needs_clarification,
            "rejected": self.rejected,
            "subquestions": copy.deepcopy(self.subquestions),
            "assignments": copy.deepcopy(self.assignments),
            "subquestion_ids": list(self.subquestion_ids),
            "research_spec": copy.deepcopy(self.research_spec) if self.research_spec is not None else None,
            "parent_claim_ceiling": self.parent_claim_ceiling,
            "coverage": self.coverage,
            "capped": self.capped,
            "binding": copy.deepcopy(self.binding),
        }


def _spec_dict(spec: Any) -> dict[str, Any] | None:
    """Return a draft ``ResearchSpec`` projection for an accepted shape, else ``None``.

    Accepts a :class:`ResearchSpec` or a mapping projection of one; the value is
    only read, never mutated.
    """
    if isinstance(spec, ResearchSpec):
        return spec.to_dict()
    if isinstance(spec, Mapping):
        return dict(spec)
    return None


def _clean_str_list(value: Any) -> list[str]:
    """Order-preserving list of the non-blank string entries in ``value``."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _distinct(values: list[str]) -> list[str]:
    """Order-preserving de-duplication."""
    return list(dict.fromkeys(values))


def _between_phrase(groups: list[str]) -> str:
    """A single-relationship ``between ...`` comparison phrase over ``groups``.

    ``between A and B`` for two groups; ``between A, B and C`` for more.  The
    conjunction merely closes the range, so the phrase stays single-purpose (see
    :func:`auto_bioinfo.core.validation.subquestion_is_single_purpose`).
    """
    if len(groups) == 2:
        return f"between {groups[0]} and {groups[1]}"
    return "between " + ", ".join(groups[:-1]) + " and " + groups[-1]


def _endpoint_question(endpoint: str, groups: list[str]) -> str:
    """A single-relationship question for one explicit endpoint (+ comparison)."""
    if len(groups) >= 2:
        return f"What is the {endpoint} {_between_phrase(groups)}?"
    return f"What is the {endpoint}?"


def _cap_claim_level(level: str, ceiling: str) -> str:
    """The allowed claim level: the lower of ``level`` and the parent ``ceiling``.

    A candidate's implied claim can only ever be pulled *down* to the ceiling,
    never allowed above it (mirrors the gap-ceiling rule elsewhere in the core).
    """
    if level not in CLAIM_LEVELS:
        return ceiling
    if ceiling not in CLAIM_LEVELS:
        return level
    return level if CLAIM_LEVELS.index(level) <= CLAIM_LEVELS.index(ceiling) else ceiling


def _scope_comparison_groups(scope: Any) -> tuple[set[str] | None, str | None]:
    """Return ``(allowed_groups | None, error_code | None)`` for an optional scope.

    ``None`` allowed_groups means "the scope imposes no comparison-group
    restriction" (no scope supplied, or the resolved scope names no comparisons).
    A scope value that is neither ``None``, a :class:`ScopeBundle`, nor a mapping is
    malformed and fails closed.
    """
    if scope is None:
        return (None, None)
    if isinstance(scope, ScopeBundle):
        scope_dict: Mapping[str, Any] = scope.to_dict()
    elif isinstance(scope, Mapping):
        scope_dict = scope
    else:
        return (None, CODE_SCOPE_MALFORMED)
    comparisons = scope_dict.get("comparisons")
    cleaned = {c.strip() for c in comparisons if isinstance(c, str) and c.strip()} if isinstance(comparisons, list) else set()
    return (cleaned or None, None)


def _candidates_from_spec(spec_dict: Mapping[str, Any], research_question: str) -> list[_Candidate]:
    """Derive deterministic candidate sub-questions from the explicit draft facts.

    Rules (T-07-01), applied in a fixed order and using only explicitly stated
    facts:

    - When the draft lists explicit ``primary_endpoints``, each endpoint is one
      single-relationship sub-question (multiple explicitly stated endpoints are
      genuinely multiple relationships, so splitting is correct); it is scoped by
      the explicit ``comparison_groups`` when two or more distinct groups exist.
    - Otherwise, when the draft states an explicit two-group-or-more comparison,
      the single differential relationship is one sub-question carrying the draft's
      verbatim ``research_question`` text.
    - Otherwise the draft states no explicitly decomposable relationship and no
      candidate is produced (the caller returns ``needs_clarification``).
    """
    endpoints = _distinct(_clean_str_list(spec_dict.get("primary_endpoints")))
    groups = _distinct(_clean_str_list(spec_dict.get("comparison_groups")))
    has_comparison = len(groups) >= 2

    if endpoints:
        coverage = COVERAGE_COVERED if has_comparison else COVERAGE_PARTIAL
        implied = IMPLIED_COMPARISON_CLAIM if has_comparison else IMPLIED_DESCRIPTIVE_CLAIM
        return [
            _Candidate(
                question=_endpoint_question(endpoint, groups),
                purpose=endpoint,
                evidence_type=endpoint,
                groups=tuple(groups),
                implied_claim=implied,
                coverage=coverage,
            )
            for endpoint in endpoints
        ]

    if has_comparison:
        return [
            _Candidate(
                question=research_question,
                purpose="differential comparison",
                evidence_type="differential_comparison",
                groups=tuple(groups),
                implied_claim=IMPLIED_COMPARISON_CLAIM,
                coverage=COVERAGE_COVERED,
            )
        ]

    return []


def decompose_research_spec(spec: Any, scope: Any = None) -> DecompositionResult:
    """Run the local/offline sub-question decomposition command, fail-closed.

    A pure, deterministic function returning a bounded :class:`DecompositionResult`
    (it never raises for a domain condition, never mutates its inputs, and performs
    no I/O, clock read, LLM/provider call, persistence, event emission, approval
    grant, or content egress).

    ``spec`` is a frozen inert draft :class:`ResearchSpec` (or a mapping projection
    of one); ``scope`` is the optional resolved :class:`ScopeBundle` (or a mapping
    projection, or ``None``).  Precedence — structural validity first, then the
    per-candidate semantic check, so any uncertainty fails closed and no
    sub-question is produced unless every gate passes:

    1. **Spec** — a non-mapping / non-``ResearchSpec`` value, a missing
       ``research_question``, a locked/resolved (non-``draft``) spec, an invalid
       ``research_spec_id``, or an invalid claim-level field → ``rejected_malformed``.
    2. **Scope** — a scope value that is neither a ``ScopeBundle`` nor a mapping →
       ``rejected_malformed``.
    3. **Decomposition** (T-07-01) — derive candidates from the explicit facts; a
       draft stating no explicitly decomposable relationship → ``needs_clarification``.
    4. **Semantic check** (T-07-03) — a candidate that is not single-purpose →
       ``rejected_compound``; a candidate whose comparison scope exceeds the
       resolved scope → ``scope_exceeds_parent``.
    5. **Assignment** (T-07-05) — otherwise produce inert ``SubQuestion`` drafts,
       each with a deterministic priority, an ``allowed_claim_level`` capped at the
       parent ceiling, and a coverage status (``decomposed``).
    """
    binding: dict[str, Any] = {
        "spec_kind": type(spec).__name__,
        "scope_kind": type(scope).__name__,
    }

    def _result(
        code: str,
        message: str,
        *,
        subquestions: list[dict[str, Any]] | None = None,
        assignments: list[dict[str, Any]] | None = None,
        research_spec: dict[str, Any] | None = None,
        parent_claim_ceiling: str = "",
        coverage: str = "",
        capped: bool = False,
    ) -> DecompositionResult:
        return DecompositionResult(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            subquestions=subquestions or [],
            assignments=assignments or [],
            research_spec=research_spec,
            parent_claim_ceiling=parent_claim_ceiling,
            coverage=coverage,
            capped=capped,
            binding=dict(binding),
        )

    # 1. Resolve and structurally validate the draft spec, fail closed.
    spec_dict = _spec_dict(spec)
    if spec_dict is None:
        return _result(CODE_SPEC_MALFORMED, f"spec must be a ResearchSpec or a research-spec mapping, not {type(spec).__name__}")

    research_question = spec_dict.get("research_question")
    if not isinstance(research_question, str) or not research_question.strip():
        return _result(CODE_SPEC_MALFORMED, "draft spec is missing a non-empty research_question")
    research_question = research_question.strip()

    spec_status = spec_dict.get("status", DRAFT_STATUS)
    if spec_status not in ("", DRAFT_STATUS):
        return _result(
            CODE_SPEC_MALFORMED,
            f"sub-questions can only be decomposed from an inert draft spec (status={spec_status!r}); a locked/resolved spec is not accepted",
        )

    # A claim-level field, when present, must be a valid claim level.
    for level_field in ("claim_ceiling", "max_claim_level"):
        value = spec_dict.get(level_field)
        if value not in (None, "") and value not in CLAIM_LEVELS:
            return _result(CODE_CLAIM_LEVEL_MALFORMED, f"{level_field} {value!r} is not a valid claim level (must be one of {', '.join(CLAIM_LEVELS)})")

    # Anchor the sub-questions to a well-formed research_spec_id (minted exactly as
    # the schema does when the draft carries none).
    spec_id = str(spec_dict.get("research_spec_id") or "")
    if not spec_id:
        spec_id = make_stable_id("research_spec", {"project_id": spec_dict.get("project_id", ""), "research_question": research_question})
    if common.validate_identifier(spec_id, "research_spec_id"):
        return _result(CODE_SPEC_MALFORMED, "draft spec has an invalid research_spec_id; cannot anchor sub-questions", research_spec=copy.deepcopy(spec_dict))

    # 2. Resolve the optional scope, fail closed on a malformed value.
    allowed_scope_groups, scope_error = _scope_comparison_groups(scope)
    if scope_error is not None:
        return _result(scope_error, f"scope must be a ScopeBundle or a scope mapping, not {type(scope).__name__}", research_spec=copy.deepcopy(spec_dict))

    # The parent ceiling every allowed claim level is capped against.
    parent_ceiling = spec_dict.get("claim_ceiling") or spec_dict.get("max_claim_level") or DEFAULT_CLAIM_CEILING

    binding["research_spec_id"] = spec_id
    binding["project_id"] = spec_dict.get("project_id", "")
    binding["parent_claim_ceiling"] = parent_ceiling
    binding["endpoint_count"] = len(_distinct(_clean_str_list(spec_dict.get("primary_endpoints"))))
    binding["comparison_group_count"] = len(_distinct(_clean_str_list(spec_dict.get("comparison_groups"))))
    binding["scope_restricts_comparisons"] = allowed_scope_groups is not None

    # 3. Derive the deterministic candidate sub-questions from the explicit facts.
    candidates = _candidates_from_spec(spec_dict, research_question)
    if not candidates:
        return _result(
            CODE_NEEDS_CLARIFICATION,
            "draft states no explicitly decomposable relationship (no explicit endpoint and no two-group comparison); it needs human clarification before decomposition",
            research_spec=copy.deepcopy(spec_dict),
            parent_claim_ceiling=parent_ceiling,
        )

    # 4. Semantic check each candidate (T-07-03), fail closed — never silently record.
    for candidate in candidates:
        if not _is_single_purpose(candidate.question):
            return _result(
                CODE_COMPOUND_SUBQUESTION,
                f"candidate sub-question {candidate.question!r} expresses more than one relationship and cannot be split deterministically; it is rejected, not recorded",
                research_spec=copy.deepcopy(spec_dict),
                parent_claim_ceiling=parent_ceiling,
            )
        if allowed_scope_groups is not None and not set(candidate.groups) <= allowed_scope_groups:
            exceeding = sorted(set(candidate.groups) - allowed_scope_groups)
            return _result(
                CODE_SCOPE_EXCEEDS_PARENT,
                f"candidate sub-question names comparison group(s) {exceeding} outside the resolved parent scope; it is rejected rather than allowed to widen the scope",
                research_spec=copy.deepcopy(spec_dict),
                parent_claim_ceiling=parent_ceiling,
            )

    # 5. Assign priority / allowed_claim_level / coverage and build inert drafts.
    subquestions: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    capped_any = False
    for index, candidate in enumerate(candidates):
        allowed_claim_level = _cap_claim_level(candidate.implied_claim, parent_ceiling)
        capped = allowed_claim_level != candidate.implied_claim
        capped_any = capped_any or capped

        subquestion = SubQuestion(
            research_spec_id=spec_id,
            question=candidate.question,
            purpose=candidate.purpose,
            evidence_type=candidate.evidence_type,
            claim_ceiling=allowed_claim_level,
            status=DRAFT_STATUS,
            created_at="",  # inert, deterministic — no wall-clock timestamp
        ).to_dict()

        # Defensive self-check: a self-produced sub-question must be structurally
        # valid and single-purpose; an invalid projection fails closed rather than
        # being recorded (reuses the upstream WP-02 validator).
        errors = validate_subquestion(subquestion, research_spec_id=spec_id)
        if errors:
            return _result(
                CODE_SUBQUESTION_INVALID,
                "decomposer produced an invalid sub-question projection: " + "; ".join(errors),
                research_spec=copy.deepcopy(spec_dict),
                parent_claim_ceiling=parent_ceiling,
            )

        subquestions.append(subquestion)
        assignments.append(
            {
                "subquestion_id": subquestion["subquestion_id"],
                "question": candidate.question,
                "priority": index + 1,
                "implied_claim_level": candidate.implied_claim,
                "allowed_claim_level": allowed_claim_level,
                "capped": capped,
                "coverage": candidate.coverage,
            }
        )

    overall_coverage = COVERAGE_COVERED if all(a["coverage"] == COVERAGE_COVERED for a in assignments) else COVERAGE_PARTIAL
    binding["subquestion_count"] = len(subquestions)
    binding["capped"] = capped_any
    binding["coverage"] = overall_coverage

    return _result(
        CODE_DECOMPOSED,
        f"decomposed the draft into {len(subquestions)} inert single-relationship sub-question draft(s) from the explicit facts; each is scope-bounded and its claim level is capped at the parent ceiling",
        subquestions=subquestions,
        assignments=assignments,
        research_spec=copy.deepcopy(spec_dict),
        parent_claim_ceiling=parent_ceiling,
        coverage=overall_coverage,
        capped=capped_any,
    )


def _is_single_purpose(question: str) -> bool:
    """Reuse the upstream single-purpose rule (no local re-implementation)."""
    from ..core.validation import subquestion_is_single_purpose

    return subquestion_is_single_purpose(question)


__all__ = [
    "STATUS_DECOMPOSED",
    "STATUS_NEEDS_CLARIFICATION",
    "STATUS_REJECTED_COMPOUND",
    "STATUS_SCOPE_EXCEEDS_PARENT",
    "STATUS_REJECTED_MALFORMED",
    "STATUSES",
    "CODE_DECOMPOSED",
    "CODE_NEEDS_CLARIFICATION",
    "CODE_COMPOUND_SUBQUESTION",
    "CODE_SCOPE_EXCEEDS_PARENT",
    "CODE_SPEC_MALFORMED",
    "CODE_SCOPE_MALFORMED",
    "CODE_CLAIM_LEVEL_MALFORMED",
    "CODE_SUBQUESTION_INVALID",
    "REASON_CODES",
    "DRAFT_STATUS",
    "COVERAGE_COVERED",
    "COVERAGE_PARTIAL",
    "COVERAGE_STATUSES",
    "IMPLIED_COMPARISON_CLAIM",
    "IMPLIED_DESCRIPTIVE_CLAIM",
    "DEFAULT_CLAIM_CEILING",
    "DecompositionResult",
    "decompose_research_spec",
]
