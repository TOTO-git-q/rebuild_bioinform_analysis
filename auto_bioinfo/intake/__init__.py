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

WP-06c adds the third slice: :func:`build_initial_policy`, a pure, local,
deterministic *initial-policy builder* that turns explicit synthetic
user-constraint facts (data sensitivity, network, resources, automation level,
execution mode) into an inert initial :class:`ProjectPolicy` projection — or, when
the *required* data-sensitivity policy is missing/malformed, into a fail-closed
:class:`ApprovalNeeded` outcome.  It reuses the existing ``ProjectPolicy`` schema
and :func:`validate_project_policy`, never silently defaults to a permissive
policy, never grants an approval, and never persists, emits, sends out, or
authorises anything.

WP-06d adds the fourth slice: :func:`normalize_question`, a pure, local,
deterministic *Question Normalizer command* that turns an in-scope single request
plus a usable initial :class:`ProjectPolicy` into an inert :class:`ResearchSpec`
*draft* (``status == "draft"``).  It reuses the WP-06a/WP-06b gate via
:func:`assess_intake` (any support-scope stop stays a stop and produces no draft;
a multi-question request stays human-review oriented and is never auto-split into
child projects) and the WP-06c policy gate via :func:`validate_project_policy` (a
missing / approval-needed / malformed / non-permitted policy stays inert and never
becomes an approval).  The architecture's "Agent call" is realised as a
deterministic in-process fake/offline adapter
(:class:`OfflineQuestionNormalizerAdapter`) only — no external LLM/provider/SDK/
network/clock.  A created draft preserves *both* the exact original request text
(verbatim, with its content hash) and a deterministic normalized-text view, never
guesses unknown organism/tissue/condition/comparison facts, and is never
persisted, versioned, emitted, or treated as authorization.

WP-06e adds the fifth slice: :func:`resolve_scope`, a pure, local, deterministic
*Scope Resolver preflight command* that turns an inert ``ResearchSpec`` draft (or
a :class:`QuestionNormalizationResult`) plus a usable policy into an inert
:class:`ScopeBundle` *draft* projection over the species/tissue/condition/
comparison axes, alongside an :class:`AmbiguityReport` *draft* projection of the
open unknowns.  It preserves every upstream gate (a support-scope stop stays a
stop; a multi-question / needs-clarification request stays human-review oriented
and is never auto-resolved; a missing / approval-needed / malformed policy stays
inert), and resolves a scope axis **only** from facts the draft explicitly states
or that a tiny, public, clearly-synthetic fixture vocabulary recognises.  The
architecture's ontology/resolver call is realised as a deterministic in-process
fake/offline component (:class:`OfflineScopeResolverAdapter`) only — no real
ontology service, search API, provider, SDK, network, or clock.  Every unknown
organism/tissue/condition/comparison fact stays an empty field and an ``open``
ambiguity item; a draft with no explicit usable scope fact yields
``needs_clarification`` rather than a fabricated bundle.  The result carries no
real ontology id, is never marked authoritative, and is never persisted,
versioned, emitted, or treated as authorization.

WP-06f adds the sixth slice: :func:`assess_scope_readiness`, a pure, local,
deterministic *scope-readiness preflight* that judges whether an already-inert
WP-06e :class:`ScopeResolutionResult` is internally consistent enough for a human
to review, or must stay paused / be rejected.  It re-runs no resolver and invents
no scope: it preserves every upstream gate (a support-scope stop stays a stop; a
multi-question / needs-clarification or unsupported scope stays human-review
oriented and never becomes ready; a missing / approval-needed policy stays inert),
and only calls a ``scope_draft_created`` resolution ``ready_for_review`` when its
:class:`ScopeBundle` / :class:`AmbiguityReport` remain valid ``draft`` /
non-authoritative projections, the research-spec / bundle / report identifiers
match (and match an optional ``source`` draft), every populated scope axis value is
traceable to an explicit draft fact via the exact WP-06e path, every explicit fact
that did not reach an axis survives as an ``open`` ambiguity, and the scope is
non-empty.  A ``ready_for_review`` verdict is inert reviewable data — never a grant
to execute — and the preflight persists nothing, emits nothing, grants no approval,
and contacts no external service.
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
from .policy_builder import (
    CODE_AUTOMATION_MALFORMED,
    CODE_BUILT,
    CODE_CONSTRAINTS_MALFORMED,
    CODE_EXECUTION_MODE_NOT_PERMITTED,
    CODE_NETWORK_MALFORMED,
    CODE_POLICY_INVALID,
    CODE_POLICY_VERSION_MALFORMED,
    CODE_PROJECT_ID_MALFORMED,
    CODE_RESOURCES_MALFORMED,
    CODE_SENSITIVITY_MALFORMED,
    CODE_SENSITIVITY_MISSING,
    CODE_SENSITIVITY_UNRECOGNIZED,
    DEFAULT_AUTOMATION_LEVEL,
    DEFAULT_EXECUTION_MODE,
    DEFAULT_NETWORK,
    DEFAULT_RESOURCES,
    GATE_DATA_SENSITIVITY,
    KEY_AUTOMATION,
    KEY_EXECUTION_MODE,
    KEY_NETWORK,
    KEY_RESOURCES,
    KEY_SENSITIVITY,
    NETWORK_LEVELS,
    PERMITTED_EXECUTION_MODES,
    RESOURCE_LEVELS,
    SENSITIVITY_LEVELS,
    STATUS_APPROVAL_NEEDED,
    STATUS_BUILT,
    STATUS_REJECTED_MALFORMED,
    STATUSES,
    ApprovalNeeded,
    PolicyBuildOutcome,
    build_initial_policy,
)
from .question_normalizer import (
    CODE_DRAFT_CREATED,
    CODE_MULTI_QUESTION_REQUIRES_REVIEW,
    CODE_POLICY_APPROVAL_NEEDED,
    CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED,
    CODE_POLICY_MALFORMED,
    CODE_POLICY_MISSING,
    DRAFT_STATUS,
    STATUS_DRAFT_CREATED,
    STATUS_STOPPED_BY_SUPPORT_SCOPE,
    OfflineQuestionNormalizerAdapter,
    QuestionNormalizationResult,
    normalize_question,
)
from .scope_readiness import (
    CODE_APPROVAL_NEEDED as READINESS_CODE_APPROVAL_NEEDED,
)
from .scope_readiness import (
    CODE_AUTHORITATIVE_PROJECTION,
    CODE_DROPPED_UNKNOWN_AXIS,
    CODE_EMPTY_SCOPE,
    CODE_IDENTIFIER_MISMATCH,
    CODE_OPEN_AMBIGUITY,
    CODE_READY_FOR_REVIEW,
    CODE_RESOLUTION_MALFORMED,
    CODE_SCOPE_BUNDLE_INVALID,
    CODE_SOURCE_MISMATCH,
    CODE_STOPPED_BY_UPSTREAM_GATE,
    CODE_UNTRACEABLE_SCOPE,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_READY_FOR_REVIEW,
    STATUS_REJECTED_INCONSISTENT,
    STATUS_STOPPED_BY_UPSTREAM_GATE,
    ScopeReadinessResult,
    assess_scope_readiness,
)
from .scope_resolver import (
    CODE_SCOPE_DRAFT_CREATED,
    CODE_UNSUPPORTED_SCOPE,
    CODE_UPSTREAM_REJECTED,
    DEFAULT_VOCABULARY,
    STATUS_SCOPE_DRAFT_CREATED,
    STATUS_UNSUPPORTED_SCOPE,
    SYNTHETIC_CONDITIONS,
    SYNTHETIC_SPECIES,
    SYNTHETIC_TISSUES,
    OfflineScopeResolverAdapter,
    ScopeResolutionResult,
    ScopeVocabulary,
    resolve_scope,
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
    "STATUS_BUILT",
    "STATUS_APPROVAL_NEEDED",
    "STATUS_REJECTED_MALFORMED",
    "STATUSES",
    "CODE_BUILT",
    "CODE_SENSITIVITY_MISSING",
    "CODE_SENSITIVITY_MALFORMED",
    "CODE_SENSITIVITY_UNRECOGNIZED",
    "CODE_PROJECT_ID_MALFORMED",
    "CODE_POLICY_VERSION_MALFORMED",
    "CODE_CONSTRAINTS_MALFORMED",
    "CODE_NETWORK_MALFORMED",
    "CODE_RESOURCES_MALFORMED",
    "CODE_AUTOMATION_MALFORMED",
    "CODE_EXECUTION_MODE_NOT_PERMITTED",
    "CODE_POLICY_INVALID",
    "KEY_SENSITIVITY",
    "KEY_NETWORK",
    "KEY_RESOURCES",
    "KEY_AUTOMATION",
    "KEY_EXECUTION_MODE",
    "SENSITIVITY_LEVELS",
    "NETWORK_LEVELS",
    "RESOURCE_LEVELS",
    "PERMITTED_EXECUTION_MODES",
    "DEFAULT_NETWORK",
    "DEFAULT_RESOURCES",
    "DEFAULT_EXECUTION_MODE",
    "DEFAULT_AUTOMATION_LEVEL",
    "GATE_DATA_SENSITIVITY",
    "ApprovalNeeded",
    "PolicyBuildOutcome",
    "build_initial_policy",
    "STATUS_DRAFT_CREATED",
    "STATUS_STOPPED_BY_SUPPORT_SCOPE",
    "DRAFT_STATUS",
    "CODE_DRAFT_CREATED",
    "CODE_MULTI_QUESTION_REQUIRES_REVIEW",
    "CODE_POLICY_MISSING",
    "CODE_POLICY_APPROVAL_NEEDED",
    "CODE_POLICY_MALFORMED",
    "CODE_POLICY_EXECUTION_MODE_NOT_PERMITTED",
    "OfflineQuestionNormalizerAdapter",
    "QuestionNormalizationResult",
    "normalize_question",
    "STATUS_SCOPE_DRAFT_CREATED",
    "STATUS_UNSUPPORTED_SCOPE",
    "CODE_SCOPE_DRAFT_CREATED",
    "CODE_UNSUPPORTED_SCOPE",
    "CODE_UPSTREAM_REJECTED",
    "SYNTHETIC_SPECIES",
    "SYNTHETIC_TISSUES",
    "SYNTHETIC_CONDITIONS",
    "DEFAULT_VOCABULARY",
    "ScopeVocabulary",
    "OfflineScopeResolverAdapter",
    "ScopeResolutionResult",
    "resolve_scope",
    "STATUS_READY_FOR_REVIEW",
    "STATUS_CLARIFICATION_REQUIRED",
    "STATUS_STOPPED_BY_UPSTREAM_GATE",
    "STATUS_REJECTED_INCONSISTENT",
    "CODE_READY_FOR_REVIEW",
    "CODE_OPEN_AMBIGUITY",
    "CODE_STOPPED_BY_UPSTREAM_GATE",
    "READINESS_CODE_APPROVAL_NEEDED",
    "CODE_RESOLUTION_MALFORMED",
    "CODE_SCOPE_BUNDLE_INVALID",
    "CODE_AUTHORITATIVE_PROJECTION",
    "CODE_IDENTIFIER_MISMATCH",
    "CODE_SOURCE_MISMATCH",
    "CODE_UNTRACEABLE_SCOPE",
    "CODE_DROPPED_UNKNOWN_AXIS",
    "CODE_EMPTY_SCOPE",
    "ScopeReadinessResult",
    "assess_scope_readiness",
]
