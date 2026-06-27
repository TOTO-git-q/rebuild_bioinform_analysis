"""Local deterministic intake support-scope classifier (WP-06a / T-06-01).

The smallest *local* gate the intake stage needs so an :class:`OriginalRequest`-
style request is classified — *is this request something this system may even
attempt to plan?* — **before any planning, question normalisation, ontology scope
resolution, dataset/literature search, or execution path can start**, and so an
unsupported or hard-stop-shaped request fails closed into a bounded legal stop
state.

This sits at the very front of the science chain described in the target
architecture: where the control plane (:mod:`auto_bioinfo.control_plane`) decides
whether a *command* may be applied, this module decides — purely, from explicit
request text and explicit caller facts — whether a *request* is in scope at all.
It is "deterministic rules first": an LLM, if ever used later, would only suggest
at most, and is **not** used or authorised here.

Design constraints (WP-06a), mirroring the WP-04 control-plane contract style:

- **Pure and deterministic.** :func:`classify_support_scope` and every helper is a
  total function of its explicit in-memory inputs.  There is no I/O whatsoever: no
  file access, no network, no environment inspection, **no real clock**, no LLM /
  provider / model call, no content egress, no threads, scheduler, queue, DB,
  outbox, or process side effect.  Inputs are never mutated in place; the request
  is never split into sub-requests; no project state, event, audit log, or
  persistent store is touched.
- **Fail closed.** Every uncertainty resolves to a *non-supported* decision.  A
  malformed/blank/oversized/non-string request, a malformed caller-facts mapping,
  a forbidden authority fact, a request that would require an external
  LLM/provider/network call or content egress, a request asking for public
  deployment/publishing / a paid service / a credential/secret/ruleset/branch-
  protection change / a destructive operation, a request needing real human-
  derived data before an approved dataset/data-lock workflow exists, and a clearly
  non-bioinformatics request all yield a bounded reason-coded decision — never a
  silent "supported" and never an unhandled exception.
- **Bounded vocabulary.** The classification is one of exactly six values
  (:data:`CLASSIFICATIONS`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.  Only ``supported`` is a proceed outcome; ``needs_clarification``
  is a legitimate-but-paused outcome (the request is **not** auto-split); the rest
  are bounded stop states.
- **Exact binding.** Every decision records the input kind, the request text
  length, the markers it matched per category, the caller-fact keys it inspected,
  the recognised ``data_lock_approved`` fact, and any detected analysis topics, so
  the decision can be audited later — without storing scientific content or making
  any claim.

This module defines a *classifier contract* only.  It does not normalise the
question, build a ``ResearchSpec`` / ``AmbiguityReport`` / ``ScopeBundle``, call a
Question Normalizer / Scope Resolver / Agent / PromptRegistry prompt, resolve an
ontology, search any dataset/literature/API, create an approval, emit an event, or
persist anything — those are out of scope for T-06-01 (see WP-06b+).  A
``supported`` decision is an inert classification value, never a grant to execute.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.schemas import OriginalRequest

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# A request text is capped; anything longer is rejected as malformed (oversized)
# rather than processed.  Generous enough for a real natural-language request,
# bounded enough to stay a safe classifier input.
MAX_REQUEST_LENGTH = 20_000
# Matched-marker lists recorded in the audit binding are capped so a pathological
# input cannot inflate the binding without bound.
_MAX_BINDING_MARKERS = 32

# --- Forbidden caller authority facts ----------------------------------------
# Intake has no power to authorise an external call, real execution, real human
# data, a public deploy, a paid service, or to bypass any gate, so a caller may
# not assert that it does.  Any of these caller-fact flags being truthy is a
# fail-closed condition: a support-scope decision is an inert value, never a real
# authorisation, and it refuses to pretend otherwise.
FORBIDDEN_AUTHORITY_FACTS = frozenset(
    {
        "authorizes_external_call",
        "authorizes_network_call",
        "authorizes_content_egress",
        "authorizes_real_execution",
        "authorizes_real_human_data",
        "authorizes_public_deploy",
        "authorizes_paid_service",
        "authorizes_credential_change",
        "authorizes_destructive_operation",
        "bypasses_gates",
        "bypasses_intake",
        "force",
    }
)
# The one recognised, *non-authority* context fact: whether an approved
# dataset/data-lock workflow already exists for this request.  It must be an exact
# boolean — only the literal ``True`` may let a real-human-derived-data request
# pass the intake hard stop (later stages still govern the actual lock); absent or
# the literal ``False`` fails that hard stop closed, and any non-boolean value
# (e.g. the string ``"false"``/``"yes"`` or the integer ``1``) is a malformed
# request, never an approval.
DATA_LOCK_APPROVED_FACT = "data_lock_approved"

# --- Bounded classification vocabulary ---------------------------------------
# A small, stable set.  ``supported`` is the single proceed outcome;
# ``needs_clarification`` is a legitimate-but-paused outcome (never auto-split);
# the remaining four are bounded stop states.
CLASS_SUPPORTED = "supported"
CLASS_NEEDS_CLARIFICATION = "needs_clarification"
CLASS_OUT_OF_SCOPE = "out_of_scope"
CLASS_UNSUPPORTED_NON_BIOINFORMATICS = "unsupported_non_bioinformatics"
CLASS_UNSUPPORTED_EXTERNAL_ACTION = "unsupported_external_action"
CLASS_MALFORMED_REQUEST = "malformed_request"

CLASSIFICATIONS = (
    CLASS_SUPPORTED,
    CLASS_NEEDS_CLARIFICATION,
    CLASS_OUT_OF_SCOPE,
    CLASS_UNSUPPORTED_NON_BIOINFORMATICS,
    CLASS_UNSUPPORTED_EXTERNAL_ACTION,
    CLASS_MALFORMED_REQUEST,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# supported:
CODE_SUPPORTED = "INTAKE_SUPPORTED"
# needs_clarification (legitimate, paused — never auto-split):
CODE_AMBIGUOUS = "INTAKE_AMBIGUOUS"
CODE_MULTI_TOPIC = "INTAKE_MULTI_TOPIC"
# unsupported_non_bioinformatics:
CODE_NON_BIOINFORMATICS = "INTAKE_NON_BIOINFORMATICS"
# unsupported_external_action:
CODE_EXTERNAL_LLM_OR_PROVIDER = "INTAKE_EXTERNAL_LLM_OR_PROVIDER"
CODE_NETWORK_OR_CONTENT_EGRESS = "INTAKE_NETWORK_OR_CONTENT_EGRESS"
# out_of_scope (hard-stop-shaped governance requests):
CODE_PUBLIC_DEPLOY_OR_PUBLISH = "INTAKE_PUBLIC_DEPLOY_OR_PUBLISH"
CODE_PAID_SERVICE = "INTAKE_PAID_SERVICE"
CODE_CREDENTIAL_OR_RULESET_CHANGE = "INTAKE_CREDENTIAL_OR_RULESET_CHANGE"
CODE_DESTRUCTIVE_OPERATION = "INTAKE_DESTRUCTIVE_OPERATION"
CODE_REAL_HUMAN_DATA_BEFORE_LOCK = "INTAKE_REAL_HUMAN_DATA_BEFORE_LOCK"
CODE_FORBIDDEN_AUTHORITY_FACT = "INTAKE_FORBIDDEN_AUTHORITY_FACT"
# malformed_request (fail closed):
CODE_NON_STRING_REQUEST = "INTAKE_NON_STRING_REQUEST"
CODE_BLANK_REQUEST = "INTAKE_BLANK_REQUEST"
CODE_OVERSIZED_REQUEST = "INTAKE_OVERSIZED_REQUEST"
CODE_MALFORMED_TEXT = "INTAKE_MALFORMED_TEXT"
CODE_MALFORMED_CALLER_FACTS = "INTAKE_MALFORMED_CALLER_FACTS"

REASON_CODES = (
    CODE_SUPPORTED,
    CODE_AMBIGUOUS,
    CODE_MULTI_TOPIC,
    CODE_NON_BIOINFORMATICS,
    CODE_EXTERNAL_LLM_OR_PROVIDER,
    CODE_NETWORK_OR_CONTENT_EGRESS,
    CODE_PUBLIC_DEPLOY_OR_PUBLISH,
    CODE_PAID_SERVICE,
    CODE_CREDENTIAL_OR_RULESET_CHANGE,
    CODE_DESTRUCTIVE_OPERATION,
    CODE_REAL_HUMAN_DATA_BEFORE_LOCK,
    CODE_FORBIDDEN_AUTHORITY_FACT,
    CODE_NON_STRING_REQUEST,
    CODE_BLANK_REQUEST,
    CODE_OVERSIZED_REQUEST,
    CODE_MALFORMED_TEXT,
    CODE_MALFORMED_CALLER_FACTS,
)

# The classification each reason code resolves to, so a future adapter can map a
# category to a transport status without re-deriving it from the code.
_CODE_CLASS = {
    CODE_SUPPORTED: CLASS_SUPPORTED,
    CODE_AMBIGUOUS: CLASS_NEEDS_CLARIFICATION,
    CODE_MULTI_TOPIC: CLASS_NEEDS_CLARIFICATION,
    CODE_NON_BIOINFORMATICS: CLASS_UNSUPPORTED_NON_BIOINFORMATICS,
    CODE_EXTERNAL_LLM_OR_PROVIDER: CLASS_UNSUPPORTED_EXTERNAL_ACTION,
    CODE_NETWORK_OR_CONTENT_EGRESS: CLASS_UNSUPPORTED_EXTERNAL_ACTION,
    CODE_PUBLIC_DEPLOY_OR_PUBLISH: CLASS_OUT_OF_SCOPE,
    CODE_PAID_SERVICE: CLASS_OUT_OF_SCOPE,
    CODE_CREDENTIAL_OR_RULESET_CHANGE: CLASS_OUT_OF_SCOPE,
    CODE_DESTRUCTIVE_OPERATION: CLASS_OUT_OF_SCOPE,
    CODE_REAL_HUMAN_DATA_BEFORE_LOCK: CLASS_OUT_OF_SCOPE,
    CODE_FORBIDDEN_AUTHORITY_FACT: CLASS_OUT_OF_SCOPE,
    CODE_NON_STRING_REQUEST: CLASS_MALFORMED_REQUEST,
    CODE_BLANK_REQUEST: CLASS_MALFORMED_REQUEST,
    CODE_OVERSIZED_REQUEST: CLASS_MALFORMED_REQUEST,
    CODE_MALFORMED_TEXT: CLASS_MALFORMED_REQUEST,
    CODE_MALFORMED_CALLER_FACTS: CLASS_MALFORMED_REQUEST,
}

# --- Deterministic lexical markers -------------------------------------------
# These are *not* a model: each category is a frozen tuple of lower-case
# substrings.  A request is classified by which categories its lower-cased text
# matches, in the fixed precedence encoded in :func:`classify_support_scope`.  The
# lists are intentionally conservative and curated to avoid common collisions; a
# future LLM suggestion layer is out of scope here.

# Bioinformatics-domain signal: at least one is required for a request to be even
# considered in scope (otherwise it is a clearly non-bioinformatics request).
_BIOINFORMATICS_MARKERS = (
    "bioinformatic",
    "rna-seq",
    "rnaseq",
    "rna seq",
    "scrna",
    "single-cell",
    "single cell",
    "differential expression",
    "gene expression",
    "expression analysis",
    "transcriptom",
    "genom",
    "exome",
    "proteom",
    "metabolom",
    "methylation",
    "variant calling",
    "fold change",
    "pathway",
    "enrichment",
    "go term",
    "kegg",
    "sequencing",
    "fastq",
    "count matrix",
    "read alignment",
    "deg table",
    "differentially expressed",
)

# External LLM / provider markers — requiring such a call is out of scope here.
_EXTERNAL_LLM_MARKERS = (
    "openai",
    "anthropic",
    "claude api",
    "gpt-",
    "chatgpt",
    "gemini",
    "large language model",
    "language model api",
    "llm api",
    "call an llm",
    "use an llm",
    "external model",
    "third-party model",
    "provider api key",
)

# Network call / content-egress markers — leaving the local boundary is out of
# scope here.
_NETWORK_EGRESS_MARKERS = (
    "http://",
    "https://",
    "upload to",
    "send to",
    "post to",
    "download from",
    "fetch from the internet",
    "scrape",
    "external service",
    "external api",
    "web service",
    "over the internet",
    "egress",
    "email the results",
    "share externally",
    "publish to slack",
)

# Public deployment / publishing markers.
_PUBLIC_DEPLOY_MARKERS = (
    "deploy",
    "publish",
    "public website",
    "go live",
    "production deployment",
    "release publicly",
    "make it public",
    "publicly available",
    "publish the paper",
)

# Paid-service markers.
_PAID_SERVICE_MARKERS = (
    "paid service",
    "paid api",
    "paid tier",
    "subscription",
    "credit card",
    "pay for",
    "purchase",
    "billing",
    "buy a license",
)

# Credential / secret / ruleset / branch-protection markers.
_CREDENTIAL_MARKERS = (
    "credential",
    "secret",
    "password",
    "api key",
    "ssh key",
    "private key",
    "access token",
    "branch protection",
    "branch-protection",
    "ruleset",
    "rotate the keys",
    ".env file",
)

# Destructive / irreversible operation markers.
_DESTRUCTIVE_MARKERS = (
    "delete",
    "drop database",
    "drop table",
    "truncate",
    "wipe",
    "destroy",
    "erase",
    "rm -rf",
    "format the disk",
    "overwrite everything",
    "purge",
)

# Real human-derived data markers — disallowed before an approved data-lock.
_REAL_HUMAN_DATA_MARKERS = (
    "patient",
    "clinical record",
    "medical record",
    "ehr",
    "hospital cohort",
    "real patient",
    "human subject",
    "identifiable",
    "biobank",
    "donor sample",
    "personal genome",
    "genomic records",
    "phi",
    "real-world clinical",
)

# Vague / "you decide" markers — a request that defers the goal needs human
# clarification (but is never auto-split).
_VAGUE_MARKERS = (
    "not sure",
    "whatever",
    "something interesting",
    "what is interesting",
    "whatever you find",
    "figure it out",
    "you decide",
    "do whatever",
    "i don't know",
    "anything you want",
    "surprise me",
)

# Distinct analysis topics — two or more present means a multi-topic request that
# must be clarified rather than auto-split into separate projects.
_TOPIC_MARKERS = {
    "differential_expression": ("differential expression", "differentially expressed", "deg", "fold change", "expression analysis"),
    "genome_assembly": ("genome assembly", "assemble the genome", "de novo assembly", "assembly"),
    "variant_calling": ("variant calling", "snp calling", "call variants"),
    "single_cell": ("single-cell", "single cell", "scrna"),
    "pathway_enrichment": ("pathway", "enrichment", "go term", "kegg"),
    "alignment": ("read alignment", "align reads", "map reads"),
    "methylation": ("methylation",),
    "proteomics": ("proteom",),
}


# --- Small, pure predicates --------------------------------------------------


def _is_printable_request_text(value: str) -> bool:
    """True iff every character is printable, allowing common line whitespace.

    Rejects NUL and other C0/C1 control characters (which a real natural-language
    request never contains) while permitting newlines, tabs, carriage returns,
    spaces, and any printable Unicode letter/symbol.
    """
    return all(ch.isprintable() or ch in "\n\r\t " for ch in value)


def _matches(lowered: str, markers: tuple[str, ...]) -> list[str]:
    """Return the sorted, de-duplicated, bounded markers present in ``lowered``."""
    found = sorted({m for m in markers if m in lowered})
    return found[:_MAX_BINDING_MARKERS]


def _detected_topics(lowered: str) -> list[str]:
    """Return the sorted distinct analysis-topic names present in ``lowered``."""
    return sorted(topic for topic, markers in _TOPIC_MARKERS.items() if any(m in lowered for m in markers))


# --- The deterministic intake decision ---------------------------------------


@dataclass(frozen=True)
class IntakeDecision:
    """The deterministic, reason-coded outcome of a support-scope classification.

    ``classification`` is one of :data:`CLASSIFICATIONS`; ``reason_code`` is one of
    :data:`REASON_CODES`.  ``binding`` records the exact facts considered (input
    kind, text length, matched markers per category, inspected caller-fact keys,
    the recognised ``data_lock_approved`` fact, and detected topics) so the
    decision can be audited.  The decision is an inert classification value: it
    stores no scientific content, makes no claim, never authorises execution, and
    never carries auto-split sub-requests.
    """

    classification: str
    reason_code: str
    message: str
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def supported(self) -> bool:
        """The single proceed outcome (the request may enter later intake stages)."""
        return self.classification == CLASS_SUPPORTED

    @property
    def needs_clarification(self) -> bool:
        """A legitimate-but-paused outcome; the request is never auto-split."""
        return self.classification == CLASS_NEEDS_CLARIFICATION

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order)."""
        return {
            "classification": self.classification,
            "reason_code": self.reason_code,
            "message": self.message,
            "supported": self.supported,
            "needs_clarification": self.needs_clarification,
            "binding": dict(self.binding),
        }


def _extract_text(request: Any) -> tuple[str | None, str, tuple[str, str] | None]:
    """Return ``(text, input_kind, error)`` for a request of an accepted shape.

    Accepts an :class:`OriginalRequest`, a bare ``str``, or a mapping carrying an
    ``original_text`` string (e.g. an ``OriginalRequest.to_dict()`` projection).
    Anything else, or a non-string ``original_text``, is a fail-closed
    ``(None, kind, error)``.  The request value itself is only read, never mutated.
    """
    if isinstance(request, OriginalRequest):
        text, kind = request.original_text, "original_request"
    elif isinstance(request, str):
        text, kind = request, "str"
    elif isinstance(request, Mapping):
        text, kind = request.get("original_text"), "mapping"
    else:
        return (None, type(request).__name__, (CODE_NON_STRING_REQUEST, "request must be an OriginalRequest, a string, or a mapping with 'original_text'"))
    if not isinstance(text, str):
        return (None, kind, (CODE_NON_STRING_REQUEST, "request text must be a string"))
    return (text, kind, None)


def _validate_caller_facts(caller_facts: Any) -> tuple[Mapping[str, Any], tuple[str, str] | None]:
    """Validate the optional caller facts; return ``(facts, error)``.

    ``None`` (absent) is treated as an empty mapping.  When supplied it must be a
    mapping with string keys, and no :data:`FORBIDDEN_AUTHORITY_FACTS` key may be
    truthy — intake cannot authorise an external/real/destructive action, so it
    refuses a fact claiming it can.
    """
    if caller_facts is None:
        return ({}, None)
    if not isinstance(caller_facts, Mapping):
        return ({}, (CODE_MALFORMED_CALLER_FACTS, "caller_facts, when supplied, must be a mapping"))
    for key in caller_facts:
        if not isinstance(key, str):
            return ({}, (CODE_MALFORMED_CALLER_FACTS, "caller_facts keys must be strings"))
    # The only recognised context fact, ``data_lock_approved``, gates the
    # real-human-data hard stop, so it must be an *exact* boolean.  Generic
    # truthiness would let a malformed caller value such as the string ``"false"``,
    # ``"no"``, or the integer ``1`` lift that hard stop — none of which is evidence
    # that an approved dataset/data-lock workflow exists.  When the fact is present
    # with any non-boolean value, fail closed as a malformed request.
    if DATA_LOCK_APPROVED_FACT in caller_facts and not isinstance(caller_facts[DATA_LOCK_APPROVED_FACT], bool):
        return (
            {},
            (CODE_MALFORMED_CALLER_FACTS, f"caller fact {DATA_LOCK_APPROVED_FACT!r} must be the exact boolean True or False"),
        )
    for flag in FORBIDDEN_AUTHORITY_FACTS:
        if caller_facts.get(flag):
            return (
                caller_facts,
                (CODE_FORBIDDEN_AUTHORITY_FACT, f"caller fact {flag!r} is forbidden: intake cannot authorise an external/real/destructive action"),
            )
    return (caller_facts, None)


def classify_support_scope(request: Any, *, caller_facts: Mapping[str, Any] | None = None) -> IntakeDecision:
    """Classify a request's support scope, fail-closed, from explicit facts only.

    A pure, deterministic function returning a bounded :class:`IntakeDecision` (it
    never raises for a domain condition, never mutates its inputs, never splits the
    request, and performs no I/O, clock read, LLM/provider call, or content
    egress).  Precedence — most severe / most certain first, so any uncertainty
    fails closed:

    1. **Request shape** — non-string, blank, oversized, or non-printable text →
       ``malformed_request``.
    2. **Caller facts** — a non-mapping / non-string-keyed ``caller_facts`` →
       ``malformed_request``; any forbidden authority fact being truthy →
       ``out_of_scope``.
    3. **External action** — text needing an external LLM/provider call →
       ``unsupported_external_action`` (LLM); a network call / content egress →
       ``unsupported_external_action`` (egress).
    4. **Governance hard stops** — a destructive operation, a credential/secret/
       ruleset/branch-protection change, a paid service, or public deployment/
       publishing → ``out_of_scope``.
    5. **Real human data** — text needing real human-derived data while no
       approved dataset/data-lock workflow exists (``data_lock_approved`` is not
       the exact boolean ``True``) → ``out_of_scope``.  ``data_lock_approved`` is
       validated as an exact boolean in step 2, so a non-boolean truthy value such
       as ``"false"`` or ``1`` is already ``malformed_request`` and can never lift
       this hard stop.
    6. **Non-bioinformatics** — no bioinformatics-domain signal at all →
       ``unsupported_non_bioinformatics``.
    7. **Clarification** — two or more distinct analysis topics (multi-topic) or a
       vague/"you decide" request → ``needs_clarification`` (never auto-split).
    8. Otherwise → ``supported``.
    """
    text, input_kind, shape_error = _extract_text(request)

    def _decide(code: str, message: str, *, lowered: str = "", topics: list[str] | None = None) -> IntakeDecision:
        binding: dict[str, Any] = {
            "input_kind": input_kind,
            "text_length": len(text) if isinstance(text, str) else None,
            "caller_fact_keys": sorted(str(k) for k in caller_facts) if isinstance(caller_facts, Mapping) else [],
            # Exact-boolean: the audit binding records an approved data-lock *only*
            # for the exact boolean ``True``, never for an arbitrary truthy value.
            "data_lock_approved": caller_facts.get(DATA_LOCK_APPROVED_FACT) is True if isinstance(caller_facts, Mapping) else False,
            "detected_topics": topics if topics is not None else [],
            "matched_markers": {
                "bioinformatics": _matches(lowered, _BIOINFORMATICS_MARKERS),
                "external_llm": _matches(lowered, _EXTERNAL_LLM_MARKERS),
                "network_egress": _matches(lowered, _NETWORK_EGRESS_MARKERS),
                "public_deploy": _matches(lowered, _PUBLIC_DEPLOY_MARKERS),
                "paid_service": _matches(lowered, _PAID_SERVICE_MARKERS),
                "credential_ruleset": _matches(lowered, _CREDENTIAL_MARKERS),
                "destructive": _matches(lowered, _DESTRUCTIVE_MARKERS),
                "real_human_data": _matches(lowered, _REAL_HUMAN_DATA_MARKERS),
                "vague": _matches(lowered, _VAGUE_MARKERS),
            }
            if lowered
            else {},
        }
        return IntakeDecision(classification=_CODE_CLASS[code], reason_code=code, message=message, binding=binding)

    # 1. Request shape.
    if shape_error is not None:
        code, message = shape_error
        return _decide(code, message)
    assert isinstance(text, str)  # narrowed by _extract_text returning no error
    if not text.strip():
        return _decide(CODE_BLANK_REQUEST, "request text is blank")
    if len(text) > MAX_REQUEST_LENGTH:
        return _decide(CODE_OVERSIZED_REQUEST, f"request text length {len(text)} exceeds the maximum of {MAX_REQUEST_LENGTH}")
    if not _is_printable_request_text(text):
        return _decide(CODE_MALFORMED_TEXT, "request text contains control characters and is not a printable natural-language request")

    # 2. Caller facts.
    facts, facts_error = _validate_caller_facts(caller_facts)
    caller_facts = facts
    lowered = text.lower()
    topics = _detected_topics(lowered)
    if facts_error is not None:
        code, message = facts_error
        return _decide(code, message, lowered=lowered, topics=topics)

    # 3. External action (LLM/provider, then network/content egress).
    if _matches(lowered, _EXTERNAL_LLM_MARKERS):
        return _decide(
            CODE_EXTERNAL_LLM_OR_PROVIDER, "request requires an external LLM/provider call, which intake does not authorise", lowered=lowered, topics=topics
        )
    if _matches(lowered, _NETWORK_EGRESS_MARKERS):
        return _decide(
            CODE_NETWORK_OR_CONTENT_EGRESS, "request requires a network call or content egress, which intake does not authorise", lowered=lowered, topics=topics
        )

    # 4. Governance hard stops (destructive, credential/ruleset, paid, deploy).
    if _matches(lowered, _DESTRUCTIVE_MARKERS):
        return _decide(CODE_DESTRUCTIVE_OPERATION, "request asks for a destructive/irreversible operation, which intake stops", lowered=lowered, topics=topics)
    if _matches(lowered, _CREDENTIAL_MARKERS):
        return _decide(
            CODE_CREDENTIAL_OR_RULESET_CHANGE,
            "request asks for a credential/secret/ruleset/branch-protection change, which intake stops",
            lowered=lowered,
            topics=topics,
        )
    if _matches(lowered, _PAID_SERVICE_MARKERS):
        return _decide(CODE_PAID_SERVICE, "request asks to use a paid service, which intake stops", lowered=lowered, topics=topics)
    if _matches(lowered, _PUBLIC_DEPLOY_MARKERS):
        return _decide(CODE_PUBLIC_DEPLOY_OR_PUBLISH, "request asks for public deployment/publishing, which intake stops", lowered=lowered, topics=topics)

    # 5. Real human-derived data before an approved data-lock workflow.
    if _matches(lowered, _REAL_HUMAN_DATA_MARKERS) and caller_facts.get(DATA_LOCK_APPROVED_FACT) is not True:
        return _decide(
            CODE_REAL_HUMAN_DATA_BEFORE_LOCK,
            "request requires real human-derived data before an approved dataset/data-lock workflow exists; intake stops",
            lowered=lowered,
            topics=topics,
        )

    # 6. Clearly non-bioinformatics (no domain signal at all).
    if not _matches(lowered, _BIOINFORMATICS_MARKERS):
        return _decide(
            CODE_NON_BIOINFORMATICS, "request shows no bioinformatics-domain signal and is out of this system's scope", lowered=lowered, topics=topics
        )

    # 7. Needs clarification (multi-topic or vague) — never auto-split.
    if len(topics) >= 2:
        return _decide(
            CODE_MULTI_TOPIC,
            f"request spans multiple distinct analysis topics {topics}; clarification is required (it is not auto-split)",
            lowered=lowered,
            topics=topics,
        )
    if _matches(lowered, _VAGUE_MARKERS):
        return _decide(CODE_AMBIGUOUS, "request defers the analysis goal and needs clarification", lowered=lowered, topics=topics)

    # 8. Supported.
    return _decide(
        CODE_SUPPORTED, "request is an in-scope, single-topic bioinformatics request and may enter later intake stages", lowered=lowered, topics=topics
    )


__all__ = [
    "MAX_REQUEST_LENGTH",
    "FORBIDDEN_AUTHORITY_FACTS",
    "DATA_LOCK_APPROVED_FACT",
    "CLASS_SUPPORTED",
    "CLASS_NEEDS_CLARIFICATION",
    "CLASS_OUT_OF_SCOPE",
    "CLASS_UNSUPPORTED_NON_BIOINFORMATICS",
    "CLASS_UNSUPPORTED_EXTERNAL_ACTION",
    "CLASS_MALFORMED_REQUEST",
    "CLASSIFICATIONS",
    "CODE_SUPPORTED",
    "CODE_AMBIGUOUS",
    "CODE_MULTI_TOPIC",
    "CODE_NON_BIOINFORMATICS",
    "CODE_EXTERNAL_LLM_OR_PROVIDER",
    "CODE_NETWORK_OR_CONTENT_EGRESS",
    "CODE_PUBLIC_DEPLOY_OR_PUBLISH",
    "CODE_PAID_SERVICE",
    "CODE_CREDENTIAL_OR_RULESET_CHANGE",
    "CODE_DESTRUCTIVE_OPERATION",
    "CODE_REAL_HUMAN_DATA_BEFORE_LOCK",
    "CODE_FORBIDDEN_AUTHORITY_FACT",
    "CODE_NON_STRING_REQUEST",
    "CODE_BLANK_REQUEST",
    "CODE_OVERSIZED_REQUEST",
    "CODE_MALFORMED_TEXT",
    "CODE_MALFORMED_CALLER_FACTS",
    "REASON_CODES",
    "IntakeDecision",
    "classify_support_scope",
]
