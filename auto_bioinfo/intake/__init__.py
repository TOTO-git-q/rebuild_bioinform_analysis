"""Intake stage (WP-06, phases 0-2): the project's entry boundary.

The intake stage is where a raw, untrusted user request first meets the system,
*before* any planning, question normalisation, ontology scope resolution, dataset
search, or execution path can start.  Its job is to fail closed: a request that is
malformed, clearly out of scope, hard-stop-shaped, or that needs human
clarification must be stopped here, with a bounded, auditable reason — never
silently forwarded into the science chain.

WP-06a delivers the first slice: :func:`classify_support_scope`, a pure, local,
deterministic *support-scope classifier* over an :class:`OriginalRequest`-style
request.  It reads only explicit request text and explicit caller-supplied facts,
emits a bounded, reason-coded :class:`IntakeDecision`, and never calls an LLM /
provider / network, never reads a real clock, secret, or environment, and never
mutates project state, events, queues, a DB, audit logs, or any persistent store.
An out-of-scope or unsupported request is projected to a bounded stop decision; it
is *never* split into sub-requests automatically.

WP-06b adds the second slice: :func:`assess_intake`, a pure, local, deterministic
*multi-research-question detector* that defers to :func:`classify_support_scope`,
preserves any support-scope stop, and — for a supported / needs-clarification
request — emits a bounded, reason-coded :class:`IntakeAssessment` indicating
whether the request appears to bundle multiple research questions.  When it does,
it offers inert :class:`SplitSuggestion` text snippets for *human review only*; it
**never** automatically splits the request, creates a sub-request or child
project, or produces any executable artifact.
"""

from __future__ import annotations

from .multi_question import (
    ASSESS_MULTI_QUESTION,
    ASSESS_NEEDS_CLARIFICATION,
    ASSESS_NOT_GENERATED,
    ASSESS_SINGLE_QUESTION,
    ASSESSMENT_REASON_CODES,
    ASSESSMENTS,
    CODE_MULTI_QUESTION,
    CODE_NEEDS_CLARIFICATION,
    CODE_SINGLE_QUESTION,
    CODE_STOPPED_BY_SUPPORT_SCOPE,
    MAX_SNIPPET_LENGTH,
    MAX_SPLIT_SUGGESTIONS,
    MIN_DISTINCT_TOPICS,
    MIN_QUESTION_MARKS,
    IntakeAssessment,
    SplitSuggestion,
    assess_intake,
)
from .support_scope import (
    CLASS_MALFORMED_REQUEST,
    CLASS_NEEDS_CLARIFICATION,
    CLASS_OUT_OF_SCOPE,
    CLASS_SUPPORTED,
    CLASS_UNSUPPORTED_EXTERNAL_ACTION,
    CLASS_UNSUPPORTED_NON_BIOINFORMATICS,
    CLASSIFICATIONS,
    CODE_AMBIGUOUS,
    CODE_BLANK_REQUEST,
    CODE_CREDENTIAL_OR_RULESET_CHANGE,
    CODE_DESTRUCTIVE_OPERATION,
    CODE_EXTERNAL_LLM_OR_PROVIDER,
    CODE_FORBIDDEN_AUTHORITY_FACT,
    CODE_MALFORMED_CALLER_FACTS,
    CODE_MALFORMED_TEXT,
    CODE_MULTI_TOPIC,
    CODE_NETWORK_OR_CONTENT_EGRESS,
    CODE_NON_BIOINFORMATICS,
    CODE_NON_STRING_REQUEST,
    CODE_OVERSIZED_REQUEST,
    CODE_PAID_SERVICE,
    CODE_PUBLIC_DEPLOY_OR_PUBLISH,
    CODE_REAL_HUMAN_DATA_BEFORE_LOCK,
    CODE_SUPPORTED,
    FORBIDDEN_AUTHORITY_FACTS,
    MAX_REQUEST_LENGTH,
    REASON_CODES,
    IntakeDecision,
    classify_support_scope,
)

__all__ = [
    "CLASSIFICATIONS",
    "CLASS_MALFORMED_REQUEST",
    "CLASS_NEEDS_CLARIFICATION",
    "CLASS_OUT_OF_SCOPE",
    "CLASS_SUPPORTED",
    "CLASS_UNSUPPORTED_EXTERNAL_ACTION",
    "CLASS_UNSUPPORTED_NON_BIOINFORMATICS",
    "CODE_AMBIGUOUS",
    "CODE_BLANK_REQUEST",
    "CODE_CREDENTIAL_OR_RULESET_CHANGE",
    "CODE_DESTRUCTIVE_OPERATION",
    "CODE_EXTERNAL_LLM_OR_PROVIDER",
    "CODE_FORBIDDEN_AUTHORITY_FACT",
    "CODE_MALFORMED_CALLER_FACTS",
    "CODE_MALFORMED_TEXT",
    "CODE_MULTI_TOPIC",
    "CODE_NETWORK_OR_CONTENT_EGRESS",
    "CODE_NON_BIOINFORMATICS",
    "CODE_NON_STRING_REQUEST",
    "CODE_OVERSIZED_REQUEST",
    "CODE_PAID_SERVICE",
    "CODE_PUBLIC_DEPLOY_OR_PUBLISH",
    "CODE_REAL_HUMAN_DATA_BEFORE_LOCK",
    "CODE_SUPPORTED",
    "FORBIDDEN_AUTHORITY_FACTS",
    "MAX_REQUEST_LENGTH",
    "REASON_CODES",
    "IntakeDecision",
    "classify_support_scope",
    "ASSESSMENTS",
    "ASSESSMENT_REASON_CODES",
    "ASSESS_MULTI_QUESTION",
    "ASSESS_NEEDS_CLARIFICATION",
    "ASSESS_NOT_GENERATED",
    "ASSESS_SINGLE_QUESTION",
    "CODE_MULTI_QUESTION",
    "CODE_NEEDS_CLARIFICATION",
    "CODE_SINGLE_QUESTION",
    "CODE_STOPPED_BY_SUPPORT_SCOPE",
    "MAX_SNIPPET_LENGTH",
    "MAX_SPLIT_SUGGESTIONS",
    "MIN_DISTINCT_TOPICS",
    "MIN_QUESTION_MARKS",
    "IntakeAssessment",
    "SplitSuggestion",
    "assess_intake",
]
