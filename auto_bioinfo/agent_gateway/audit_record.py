"""Local provider/tool-call audit record contract (WP-05h / T-05-08).

The smallest *local* contract the future agent gateway (WP-05) needs so that —
before any real audit-log *store* exists — it can record bounded, inert metadata
about an *already-completed* synthetic provider or tool interaction and query that
metadata in memory by ``project_id`` / ``correlation_id``.

A single :class:`AuditRecord` captures only **bounded, non-content facts** about one
call: a trace binding (``project_id`` / ``correlation_id`` / ``call_id`` /
``parent_call_id``), the call kind (``provider`` / ``tool``) and a deterministic
outcome / reason, provider/model/prompt identifiers (for a provider call) **or**
tool name/version + request/result *references* (for a tool call), input
version/fingerprint metadata, usage counters, caller-supplied timing facts, and an
optional restricted raw-output artifact *reference* (id + fingerprint only, never the
payload).  It never stores prompt content, full raw output, raw input values, or tool
arguments — those are not even fields.

Everything here is local, deterministic, and offline.  There is **no** real
provider/tool call, network call, HTTP client, SDK, credential/environment access,
real clock read, subprocess, file/DB/queue write, event, ordinary log, report, or
global mutable registry.  :func:`build_audit_record` is a pure total function of its
explicit in-memory inputs that returns an inert :class:`AuditRecordDecision`, and
:func:`query_audit_records` is a pure in-memory filter over a supplied collection that
mutates nothing and creates no repository / index.

Design constraints (mirroring the WP-05a..g style):

- **Pure, deterministic, offline.**  No I/O whatsoever; a decision / query result is a
  total function of its explicit in-memory inputs, and neither helper mutates them.
- **Fail closed, no fallback.**  Every uncertainty resolves to a bounded, reason-coded
  ``rejected`` decision (:data:`REASON_CODES`): a malformed call kind / outcome, a
  missing / malformed project-or-correlation binding, a missing call identity, a
  malformed provider/tool/prompt identifier, a provider record carrying tool fields (or
  vice-versa), missing usage/timing for a completed call, an invalid (negative /
  non-finite / oversized) usage or timing fact, an inconsistent outcome/reason
  combination, oversized metadata, or any attempt to leak a sensitive raw value into the
  metadata all fail closed and yield **no record**.
- **No content, ever.**  Prompt content, full raw output, raw input values, and tool
  arguments are never fields; the optional free-form ``metadata`` mapping is rejected
  fail-closed if it carries an inline secret or a sensitive key, so even an audit record
  cannot become a side channel for content.
- **Data only.**  The builder returns *data* to the caller — an inert decision.  It
  writes no project state, business object, event, artifact file, queue/outbox record,
  domain table, report, audit-log store, query index, or full-content log.

Out of scope for T-05-08 (and deliberately *not* implemented here): any durable
audit-log / event / artifact *storage*, registry, file write, query index, or
persistence; budgets / rate limits / timeouts / cost accounting / circuit breakers /
retries / NEED_HUMAN_REVIEW (T-05-09); fake-model fixture expansion (T-05-10); the eval
framework (T-05-11); prompt approval / rollback (T-05-12); and any real LLM / provider /
tool / network call or content egress.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.observability.redaction import redact

from .llm_provider import LLMResponse, LLMUsage, validate_usage
from .raw_output_artifact import RestrictedRawOutputArtifact
from .structured_output import AdmissionDecision
from .tool_broker import ToolMediationDecision

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated.
MAX_ID_LENGTH = 200
MAX_LABEL_LENGTH = 64
MAX_FINGERPRINT_LENGTH = 128
MAX_USAGE_COUNTERS = 16
MAX_USAGE_VALUE = 1_000_000_000
MAX_DURATION_MS = 86_400_000  # one day, in ms — a generous upper bound, not a real clock
MAX_ATTEMPT = 1_000
MAX_METADATA_ENTRIES = 16
MAX_METADATA_DEPTH = 8
MAX_METADATA_BYTES = 4_096

# --- Bounded call-kind vocabulary --------------------------------------------
# A record describes either an LLM provider call or a Tool Broker tool call.  An
# unknown kind fails closed.
CALL_KIND_PROVIDER = "provider"
CALL_KIND_TOOL = "tool"

CALL_KINDS = (CALL_KIND_PROVIDER, CALL_KIND_TOOL)

# --- Bounded outcome vocabulary ----------------------------------------------
# ``completed`` — the call finished normally (requires usage/timing facts).
# ``failed`` — the call errored; requires a bounded outcome reason.
# ``denied`` — the call was blocked (e.g. a Tool Broker deny); requires a reason.
OUTCOME_COMPLETED = "completed"
OUTCOME_FAILED = "failed"
OUTCOME_DENIED = "denied"

OUTCOMES = (OUTCOME_COMPLETED, OUTCOME_FAILED, OUTCOME_DENIED)

# Outcomes that must carry a bounded ``outcome_reason``; ``completed`` must not.
OUTCOMES_REQUIRING_REASON = (OUTCOME_FAILED, OUTCOME_DENIED)

# --- Bounded build-status vocabulary -----------------------------------------
# ``built`` means every check passed and an audit record was produced.
# ``rejected`` is the fail-closed outcome for everything else; it carries no record.
STATUS_BUILT = "built"
STATUS_REJECTED = "rejected"

STATUSES = (STATUS_BUILT, STATUS_REJECTED)

# --- Stable reason codes -----------------------------------------------------
# Callers / a future gateway branch on these machine-readable codes, never the
# human message, so they must stay stable.
CODE_MALFORMED_CALL_KIND = "AUDIT_MALFORMED_CALL_KIND"
CODE_MISSING_CALL_IDENTITY = "AUDIT_MISSING_CALL_IDENTITY"
CODE_MALFORMED_CALL_IDENTITY = "AUDIT_MALFORMED_CALL_IDENTITY"
CODE_MISSING_BINDING = "AUDIT_MISSING_BINDING"
CODE_MALFORMED_BINDING = "AUDIT_MALFORMED_BINDING"
CODE_MALFORMED_OUTCOME = "AUDIT_MALFORMED_OUTCOME"
CODE_MALFORMED_SOURCE = "AUDIT_MALFORMED_SOURCE"
CODE_MALFORMED_PROVIDER_IDENTIFIER = "AUDIT_MALFORMED_PROVIDER_IDENTIFIER"
CODE_MALFORMED_PROMPT_IDENTIFIER = "AUDIT_MALFORMED_PROMPT_IDENTIFIER"
CODE_MALFORMED_TOOL_IDENTIFIER = "AUDIT_MALFORMED_TOOL_IDENTIFIER"
CODE_MALFORMED_INPUT_METADATA = "AUDIT_MALFORMED_INPUT_METADATA"
CODE_MALFORMED_ARTIFACT_REF = "AUDIT_MALFORMED_ARTIFACT_REF"
CODE_INCONSISTENT_KIND_FIELDS = "AUDIT_INCONSISTENT_KIND_FIELDS"
CODE_MISSING_USAGE = "AUDIT_MISSING_USAGE"
CODE_MISSING_TIMING = "AUDIT_MISSING_TIMING"
CODE_INVALID_USAGE = "AUDIT_INVALID_USAGE"
CODE_INVALID_TIMING = "AUDIT_INVALID_TIMING"
CODE_INCONSISTENT_STATUS = "AUDIT_INCONSISTENT_STATUS"
CODE_SENSITIVE_METADATA = "AUDIT_SENSITIVE_METADATA"
CODE_METADATA_TOO_LARGE = "AUDIT_METADATA_TOO_LARGE"
CODE_MALFORMED_METADATA = "AUDIT_MALFORMED_METADATA"

IDENTITY_CODES = (
    CODE_MALFORMED_CALL_KIND,
    CODE_MISSING_CALL_IDENTITY,
    CODE_MALFORMED_CALL_IDENTITY,
    CODE_MALFORMED_OUTCOME,
    CODE_MALFORMED_SOURCE,
)

BINDING_CODES = (
    CODE_MISSING_BINDING,
    CODE_MALFORMED_BINDING,
)

FIELD_CODES = (
    CODE_MALFORMED_PROVIDER_IDENTIFIER,
    CODE_MALFORMED_PROMPT_IDENTIFIER,
    CODE_MALFORMED_TOOL_IDENTIFIER,
    CODE_MALFORMED_INPUT_METADATA,
    CODE_MALFORMED_ARTIFACT_REF,
    CODE_INCONSISTENT_KIND_FIELDS,
)

USAGE_TIMING_CODES = (
    CODE_MISSING_USAGE,
    CODE_MISSING_TIMING,
    CODE_INVALID_USAGE,
    CODE_INVALID_TIMING,
    CODE_INCONSISTENT_STATUS,
)

METADATA_CODES = (
    CODE_SENSITIVE_METADATA,
    CODE_METADATA_TOO_LARGE,
    CODE_MALFORMED_METADATA,
)

REASON_CODES = IDENTITY_CODES + BINDING_CODES + FIELD_CODES + USAGE_TIMING_CODES + METADATA_CODES


# --- Small, pure predicates / helpers ----------------------------------------


def _is_bounded_token(value: Any, max_length: int) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII token."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length and all("\x20" <= ch <= "\x7e" for ch in value)


def _is_nonnegative_int(value: Any) -> bool:
    """True iff ``value`` is a real (non-bool) non-negative ``int``."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_nonnegative_number(value: Any) -> bool:
    """True iff ``value`` is a real (non-bool) non-negative finite ``int`` / ``float``."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, float):
        return math.isfinite(value) and value >= 0.0
    return False


def _normalize_usage(usage: Any) -> dict[str, int] | None:
    """Normalize ``usage`` to a bounded ``{counter: count}`` dict, or ``None`` if invalid.

    Accepts an inert :class:`LLMUsage` (validated via the WP-05a contract) or a bounded
    mapping of ``str`` counter names to real non-negative integers (e.g. ``{"tokens": 3}``).
    Any other shape, a non-string key, a bool / negative / non-int / oversized value, or
    too many counters yields ``None`` (the caller maps that to a fail-closed reason).  Pure;
    mutates nothing.
    """
    if isinstance(usage, LLMUsage):
        if validate_usage(usage):
            return None
        return dict(usage.to_dict())
    if isinstance(usage, Mapping):
        if not usage or len(usage) > MAX_USAGE_COUNTERS:
            return None
        normalized: dict[str, int] = {}
        for key, value in usage.items():
            if not _is_bounded_token(key, MAX_LABEL_LENGTH):
                return None
            if not _is_nonnegative_int(value) or value > MAX_USAGE_VALUE:
                return None
            normalized[key] = value
        return dict(sorted(normalized.items()))
    return None


def _metadata_byte_estimate(value: Any, depth: int = 0) -> int | None:
    """Return a bounded byte estimate of plain ``value``, or ``None`` if malformed.

    Walks mappings / lists / tuples up to :data:`MAX_METADATA_DEPTH` admitting only JSON
    scalar leaves; an over-deep structure, a non-string mapping key, a non-finite float, or
    a non-serializable leaf yields ``None``.  Pure; performs no I/O and mutates nothing.
    """
    if depth > MAX_METADATA_DEPTH:
        return None
    if value is None or isinstance(value, bool):
        return 4
    if isinstance(value, int):
        return len(str(value))
    if isinstance(value, float):
        return len(str(value)) if math.isfinite(value) else None
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, Mapping):
        total = 2
        for key, item in value.items():
            if not isinstance(key, str):
                return None
            child = _metadata_byte_estimate(item, depth + 1)
            if child is None:
                return None
            total += len(key.encode("utf-8")) + child + 2
        return total
    if isinstance(value, (list, tuple)):
        total = 2
        for item in value:
            child = _metadata_byte_estimate(item, depth + 1)
            if child is None:
                return None
            total += child + 1
        return total
    return None


def _freeze(value: Any) -> Any:
    """Recursively freeze plain JSON-like ``value`` into an immutable structure.

    A mapping becomes a read-only :class:`~types.MappingProxyType` of recursively-frozen
    values; a list / tuple becomes a ``tuple`` of recursively-frozen items; a scalar is
    returned as-is.  Storing this on the frozen :class:`AuditRecord` means a caller cannot
    mutate the record's facts in place through ``record.usage`` / ``record.metadata`` or
    through any nested container.  Pure; mutates nothing.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _to_plain(value: Any) -> Any:
    """Recursively convert a frozen structure back to plain, mutable JSON-like data.

    The inverse of :func:`_freeze` for projection: a mapping (including a read-only
    :class:`~types.MappingProxyType`) becomes a plain ``dict`` and a ``tuple`` becomes a
    plain ``list``, so :meth:`AuditRecord.to_dict` hands callers ordinary JSON-like data
    they can use freely without ever reaching the frozen record's facts.  Pure; mutates
    nothing.
    """
    if isinstance(value, Mapping):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    return value


# --- The audit record value --------------------------------------------------


@dataclass(frozen=True)
class AuditRecord:
    """An inert, bounded audit record for one already-completed provider / tool call.

    Carries only **non-content facts**.  Prompt content, full raw output, raw input
    values, and tool arguments are not fields; the optional ``metadata`` mapping is
    validated to be free of sensitive keys / inline secrets before a record exists.

    Fields:

    - ``record_id`` — a content-address-like id over the trace binding + facts;
    - ``call_id`` / ``project_id`` / ``correlation_id`` / ``parent_call_id`` — the trace
      binding (``parent_call_id`` optional);
    - ``call_kind`` — one of :data:`CALL_KINDS`;
    - ``outcome`` — one of :data:`OUTCOMES`; ``outcome_reason`` is a bounded code for a
      ``failed`` / ``denied`` call and ``None`` for a ``completed`` one;
    - ``provider`` / ``model`` / ``prompt_id`` / ``prompt_version`` / ``template_hash`` —
      provider-side identifiers (``None`` on a tool record);
    - ``tool_name`` / ``tool_version`` / ``tool_request_ref`` / ``tool_result_ref`` —
      tool-side identifiers and bounded *references* (``None`` on a provider record);
    - ``input_version`` / ``input_fingerprint`` — input version / fingerprint metadata;
    - ``usage`` — a bounded read-only ``{counter: count}`` mapping, or ``None``;
    - ``duration_ms`` / ``attempt`` — caller-supplied timing facts, or ``None``;
    - ``raw_output_artifact_id`` / ``raw_output_fingerprint`` — a bounded restricted
      raw-output artifact *reference* (id + fingerprint only, never the payload), or ``None``;
    - ``metadata`` — a bounded, sensitive-free, read-only mapping, or ``None``.

    The value is inert data; constructing it performs no I/O and writes nothing.  Beyond
    the ``frozen=True`` guard on the attribute *bindings*, the ``usage`` / ``metadata``
    facts are stored as deeply-frozen read-only structures (see :func:`_freeze`), so a
    caller cannot mutate the audit facts in place through ``record.usage`` /
    ``record.metadata`` or through any nested container after the deterministic
    ``record_id`` has been computed.
    """

    record_id: str
    call_id: str
    project_id: str
    correlation_id: str
    parent_call_id: str | None
    call_kind: str
    outcome: str
    outcome_reason: str | None
    provider: str | None
    model: str | None
    prompt_id: str | None
    prompt_version: str | None
    template_hash: str | None
    tool_name: str | None
    tool_version: str | None
    tool_request_ref: str | None
    tool_result_ref: str | None
    input_version: str | None
    input_fingerprint: str | None
    usage: Mapping[str, int] | None
    duration_ms: int | float | None
    attempt: int | None
    raw_output_artifact_id: str | None
    raw_output_fingerprint: str | None
    metadata: Mapping[str, Any] | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the record (stable key order; no content).

        Omits prompt content, full raw output, raw input values, and tool arguments —
        none of which are fields — and returns the bounded ``usage`` / ``metadata`` facts
        as fresh plain JSON-like data (a deep copy via :func:`_to_plain`), so a caller can
        use the projection freely without ever reaching the frozen record's facts.
        """
        return {
            "record_id": self.record_id,
            "call_id": self.call_id,
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "parent_call_id": self.parent_call_id,
            "call_kind": self.call_kind,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "provider": self.provider,
            "model": self.model,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "template_hash": self.template_hash,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "tool_request_ref": self.tool_request_ref,
            "tool_result_ref": self.tool_result_ref,
            "input_version": self.input_version,
            "input_fingerprint": self.input_fingerprint,
            "usage": _to_plain(self.usage) if self.usage is not None else None,
            "duration_ms": self.duration_ms,
            "attempt": self.attempt,
            "raw_output_artifact_id": self.raw_output_artifact_id,
            "raw_output_fingerprint": self.raw_output_fingerprint,
            "metadata": _to_plain(self.metadata) if self.metadata is not None else None,
        }

    def audit_projection(self) -> dict[str, Any]:
        """A bounded audit projection — traceable by ids/hashes, never any content.

        The full :meth:`to_dict` plus a ``traceable`` marker; it carries no prompt
        content, raw output, raw input value, or tool argument (none are fields).
        """
        projection = self.to_dict()
        projection["traceable"] = True
        return projection


# --- The build decision ------------------------------------------------------


@dataclass(frozen=True)
class AuditRecordDecision:
    """The inert result of a build: an audit record, or a fail-closed reason.

    Fields:

    - ``status`` — one of :data:`STATUSES`;
    - ``reason_code`` — ``None`` when built, else the bounded rejection code
      (:data:`REASON_CODES`);
    - ``record`` — the :class:`AuditRecord` on a ``built`` decision, else ``None``.  A
      ``rejected`` decision never carries a record.

    The value is inert data; its projections never expose any content.
    """

    status: str
    reason_code: str | None
    record: AuditRecord | None = None

    @property
    def built(self) -> bool:
        """True iff an audit record was produced."""
        return self.status == STATUS_BUILT

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order; no content)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "record": self.record.to_dict() if self.record is not None else None,
        }

    def audit_projection(self) -> dict[str, Any] | None:
        """The bounded audit projection, or ``None`` when not built."""
        return self.record.audit_projection() if self.record is not None else None


def _rejected(reason_code: str) -> AuditRecordDecision:
    """Build a fail-closed ``rejected`` decision that carries no record."""
    return AuditRecordDecision(status=STATUS_REJECTED, reason_code=reason_code, record=None)


def build_audit_record(
    *,
    call_id: Any,
    project_id: Any,
    correlation_id: Any,
    call_kind: Any,
    outcome: Any,
    parent_call_id: Any = None,
    outcome_reason: Any = None,
    provider: Any = None,
    model: Any = None,
    prompt_id: Any = None,
    prompt_version: Any = None,
    template_hash: Any = None,
    tool_name: Any = None,
    tool_version: Any = None,
    tool_request_ref: Any = None,
    tool_result_ref: Any = None,
    input_version: Any = None,
    input_fingerprint: Any = None,
    usage: Any = None,
    duration_ms: Any = None,
    attempt: Any = None,
    raw_output_artifact_id: Any = None,
    raw_output_fingerprint: Any = None,
    metadata: Any = None,
    response: Any = None,
    admission: Any = None,
    artifact: Any = None,
    tool_decision: Any = None,
) -> AuditRecordDecision:
    """Build an inert audit record from explicit synthetic in-memory call metadata.

    Accepts only synthetic / in-memory facts about an *already-completed* call and returns
    an inert :class:`AuditRecordDecision`.  Optional inert source objects fill provider /
    prompt / tool / artifact gaps **only when** the corresponding explicit argument is not
    supplied (an explicit argument always wins): an :class:`LLMResponse` supplies
    ``provider`` / ``model`` / ``usage``; an :class:`AdmissionDecision` supplies
    ``prompt_id`` / ``prompt_version`` / ``template_hash``; a :class:`ToolMediationDecision`
    supplies ``tool_name`` / ``tool_version``; a :class:`RestrictedRawOutputArtifact`
    supplies the ``raw_output_artifact_id`` / ``raw_output_fingerprint`` *reference* (never
    the payload).  No source object's content, prompt, raw output, or tool arguments are
    read into the record.

    Resolution is fail-closed, in order: call kind, call identity, project/correlation
    binding, outcome, source-object shapes, kind-specific identifiers, kind-field
    consistency, input/artifact references, usage/timing (required for a ``completed``
    call), outcome/reason consistency, and bounded sensitive-free metadata.  Pure: writes
    nothing, performs no I/O, and mutates none of its inputs.
    """
    # 1. call kind ------------------------------------------------------------
    if call_kind not in CALL_KINDS:
        return _rejected(CODE_MALFORMED_CALL_KIND)

    # 2. call identity --------------------------------------------------------
    if call_id is None:
        return _rejected(CODE_MISSING_CALL_IDENTITY)
    if not _is_bounded_token(call_id, MAX_ID_LENGTH):
        return _rejected(CODE_MALFORMED_CALL_IDENTITY)
    if parent_call_id is not None and not _is_bounded_token(parent_call_id, MAX_ID_LENGTH):
        return _rejected(CODE_MALFORMED_CALL_IDENTITY)

    # 3. project / correlation binding ---------------------------------------
    if project_id is None or correlation_id is None:
        return _rejected(CODE_MISSING_BINDING)
    if not _is_bounded_token(project_id, MAX_ID_LENGTH) or not _is_bounded_token(correlation_id, MAX_ID_LENGTH):
        return _rejected(CODE_MALFORMED_BINDING)

    # 4. outcome --------------------------------------------------------------
    if outcome not in OUTCOMES:
        return _rejected(CODE_MALFORMED_OUTCOME)

    # 5. optional inert source objects ----------------------------------------
    if response is not None and not isinstance(response, LLMResponse):
        return _rejected(CODE_MALFORMED_SOURCE)
    if admission is not None and not isinstance(admission, AdmissionDecision):
        return _rejected(CODE_MALFORMED_SOURCE)
    if artifact is not None and not isinstance(artifact, RestrictedRawOutputArtifact):
        return _rejected(CODE_MALFORMED_SOURCE)
    if tool_decision is not None and not isinstance(tool_decision, ToolMediationDecision):
        return _rejected(CODE_MALFORMED_SOURCE)

    # Explicit argument wins; a source object only fills a not-supplied gap.
    if provider is None and response is not None and isinstance(response.provider, str):
        provider = response.provider
    if model is None and response is not None and isinstance(response.model, str):
        model = response.model
    if usage is None and response is not None:
        usage = response.usage
    if prompt_id is None and admission is not None:
        prompt_id = admission.prompt_id
    if prompt_version is None and admission is not None:
        prompt_version = admission.version
    if template_hash is None and admission is not None:
        template_hash = admission.template_hash
    if tool_name is None and tool_decision is not None:
        tool_name = tool_decision.tool_id
    if tool_version is None and tool_decision is not None:
        tool_version = tool_decision.version
    if raw_output_artifact_id is None and artifact is not None:
        raw_output_artifact_id = artifact.artifact_id
    if raw_output_fingerprint is None and artifact is not None:
        raw_output_fingerprint = artifact.raw_fingerprint

    # 6. kind-field consistency: a provider record carries no tool field and a
    #    tool record carries no provider/prompt field (fail closed, no mixing).
    provider_specific = (provider, model, prompt_id, prompt_version, template_hash)
    tool_specific = (tool_name, tool_version, tool_request_ref, tool_result_ref)
    if call_kind == CALL_KIND_PROVIDER and any(value is not None for value in tool_specific):
        return _rejected(CODE_INCONSISTENT_KIND_FIELDS)
    if call_kind == CALL_KIND_TOOL and any(value is not None for value in provider_specific):
        return _rejected(CODE_INCONSISTENT_KIND_FIELDS)

    # 7. kind-specific identifiers -------------------------------------------
    if call_kind == CALL_KIND_PROVIDER:
        # provider + model are required identity for a provider call.
        if not _is_bounded_token(provider, MAX_LABEL_LENGTH) or not _is_bounded_token(model, MAX_LABEL_LENGTH):
            return _rejected(CODE_MALFORMED_PROVIDER_IDENTIFIER)
        for value in (prompt_id, prompt_version, template_hash):
            if value is not None and not _is_bounded_token(value, MAX_ID_LENGTH):
                return _rejected(CODE_MALFORMED_PROMPT_IDENTIFIER)
    else:
        # tool_name is required identity for a tool call.
        if not _is_bounded_token(tool_name, MAX_ID_LENGTH):
            return _rejected(CODE_MALFORMED_TOOL_IDENTIFIER)
        for value in (tool_version, tool_request_ref, tool_result_ref):
            if value is not None and not _is_bounded_token(value, MAX_ID_LENGTH):
                return _rejected(CODE_MALFORMED_TOOL_IDENTIFIER)

    # 8. input version / fingerprint metadata --------------------------------
    for value in (input_version, input_fingerprint):
        if value is not None and not _is_bounded_token(value, MAX_FINGERPRINT_LENGTH):
            return _rejected(CODE_MALFORMED_INPUT_METADATA)

    # 9. raw-output artifact *reference* (id + fingerprint only) --------------
    for value in (raw_output_artifact_id, raw_output_fingerprint):
        if value is not None and not _is_bounded_token(value, MAX_FINGERPRINT_LENGTH):
            return _rejected(CODE_MALFORMED_ARTIFACT_REF)

    # 10. usage / timing ------------------------------------------------------
    normalized_usage: dict[str, int] | None = None
    if usage is not None:
        normalized_usage = _normalize_usage(usage)
        if normalized_usage is None:
            return _rejected(CODE_INVALID_USAGE)
    if duration_ms is not None and (not _is_finite_nonnegative_number(duration_ms) or duration_ms > MAX_DURATION_MS):
        return _rejected(CODE_INVALID_TIMING)
    if attempt is not None and (not _is_nonnegative_int(attempt) or attempt < 1 or attempt > MAX_ATTEMPT):
        return _rejected(CODE_INVALID_TIMING)

    # A completed call must carry timing; a completed provider call must also carry
    # usage counters (a completed tool call may omit usage).
    if outcome == OUTCOME_COMPLETED:
        if duration_ms is None:
            return _rejected(CODE_MISSING_TIMING)
        if call_kind == CALL_KIND_PROVIDER and normalized_usage is None:
            return _rejected(CODE_MISSING_USAGE)

    # 11. outcome / reason consistency ---------------------------------------
    if outcome in OUTCOMES_REQUIRING_REASON:
        if not _is_bounded_token(outcome_reason, MAX_LABEL_LENGTH):
            return _rejected(CODE_INCONSISTENT_STATUS)
    elif outcome_reason is not None:
        # A completed call must not carry a failure/deny reason.
        return _rejected(CODE_INCONSISTENT_STATUS)

    # 12. optional bounded, sensitive-free metadata --------------------------
    normalized_metadata: dict[str, Any] | None = None
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            return _rejected(CODE_MALFORMED_METADATA)
        if len(metadata) > MAX_METADATA_ENTRIES:
            return _rejected(CODE_METADATA_TOO_LARGE)
        byte_estimate = _metadata_byte_estimate(dict(metadata))
        if byte_estimate is None:
            return _rejected(CODE_MALFORMED_METADATA)
        if byte_estimate > MAX_METADATA_BYTES:
            return _rejected(CODE_METADATA_TOO_LARGE)
        plain_metadata = {key: value for key, value in metadata.items()}
        # Reject (never silently redact) any sensitive key or inline secret so the
        # record cannot become a side channel for content.
        if redact(plain_metadata) != plain_metadata:
            return _rejected(CODE_SENSITIVE_METADATA)
        normalized_metadata = dict(sorted(plain_metadata.items()))

    record_id = make_stable_id(
        "audit",
        {
            "call_id": call_id,
            "project_id": project_id,
            "correlation_id": correlation_id,
            "call_kind": call_kind,
            "outcome": outcome,
            "input_fingerprint": input_fingerprint,
            "raw_output_fingerprint": raw_output_fingerprint,
        },
    )

    record = AuditRecord(
        record_id=record_id,
        call_id=call_id,
        project_id=project_id,
        correlation_id=correlation_id,
        parent_call_id=parent_call_id,
        call_kind=call_kind,
        outcome=outcome,
        outcome_reason=outcome_reason if outcome in OUTCOMES_REQUIRING_REASON else None,
        provider=provider,
        model=model,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        template_hash=template_hash,
        tool_name=tool_name,
        tool_version=tool_version,
        tool_request_ref=tool_request_ref,
        tool_result_ref=tool_result_ref,
        input_version=input_version,
        input_fingerprint=input_fingerprint,
        # Store the bounded usage / metadata facts as deeply-frozen read-only structures
        # so they cannot be mutated in place through the record after build.
        usage=_freeze(normalized_usage) if normalized_usage is not None else None,
        duration_ms=duration_ms,
        attempt=attempt,
        raw_output_artifact_id=raw_output_artifact_id,
        raw_output_fingerprint=raw_output_fingerprint,
        metadata=_freeze(normalized_metadata) if normalized_metadata is not None else None,
    )

    return AuditRecordDecision(status=STATUS_BUILT, reason_code=None, record=record)


def query_audit_records(
    records: Any,
    *,
    project_id: Any = None,
    correlation_id: Any = None,
) -> tuple[AuditRecord, ...]:
    """Return the records in ``records`` matching the supplied filter, order-preserving.

    A pure, deterministic, in-memory projection over an explicit ``list`` / ``tuple`` of
    :class:`AuditRecord` values.  It filters by ``project_id`` and/or ``correlation_id``
    (each, when supplied, must be a bounded token — a malformed filter matches nothing)
    and returns a **new** tuple; a non-``AuditRecord`` item never matches, and the input
    collection is never mutated.

    This helper creates **no** repository, event, DB row, file, ordinary log, report,
    queue/outbox entry, query index, or global registry — it only reads the supplied
    collection and returns a filtered copy.
    """
    if not isinstance(records, (list, tuple)):
        return ()

    # A supplied-but-malformed filter is fail-closed: it matches nothing rather than
    # silently degrading to "match all".
    if project_id is not None and not _is_bounded_token(project_id, MAX_ID_LENGTH):
        return ()
    if correlation_id is not None and not _is_bounded_token(correlation_id, MAX_ID_LENGTH):
        return ()

    matched: list[AuditRecord] = []
    for record in records:
        if not isinstance(record, AuditRecord):
            continue
        if project_id is not None and record.project_id != project_id:
            continue
        if correlation_id is not None and record.correlation_id != correlation_id:
            continue
        matched.append(record)
    return tuple(matched)


__all__ = [
    "MAX_ID_LENGTH",
    "MAX_LABEL_LENGTH",
    "MAX_FINGERPRINT_LENGTH",
    "MAX_USAGE_COUNTERS",
    "MAX_USAGE_VALUE",
    "MAX_DURATION_MS",
    "MAX_ATTEMPT",
    "MAX_METADATA_ENTRIES",
    "MAX_METADATA_DEPTH",
    "MAX_METADATA_BYTES",
    "CALL_KIND_PROVIDER",
    "CALL_KIND_TOOL",
    "CALL_KINDS",
    "OUTCOME_COMPLETED",
    "OUTCOME_FAILED",
    "OUTCOME_DENIED",
    "OUTCOMES",
    "OUTCOMES_REQUIRING_REASON",
    "STATUS_BUILT",
    "STATUS_REJECTED",
    "STATUSES",
    "CODE_MALFORMED_CALL_KIND",
    "CODE_MISSING_CALL_IDENTITY",
    "CODE_MALFORMED_CALL_IDENTITY",
    "CODE_MISSING_BINDING",
    "CODE_MALFORMED_BINDING",
    "CODE_MALFORMED_OUTCOME",
    "CODE_MALFORMED_SOURCE",
    "CODE_MALFORMED_PROVIDER_IDENTIFIER",
    "CODE_MALFORMED_PROMPT_IDENTIFIER",
    "CODE_MALFORMED_TOOL_IDENTIFIER",
    "CODE_MALFORMED_INPUT_METADATA",
    "CODE_MALFORMED_ARTIFACT_REF",
    "CODE_INCONSISTENT_KIND_FIELDS",
    "CODE_MISSING_USAGE",
    "CODE_MISSING_TIMING",
    "CODE_INVALID_USAGE",
    "CODE_INVALID_TIMING",
    "CODE_INCONSISTENT_STATUS",
    "CODE_SENSITIVE_METADATA",
    "CODE_METADATA_TOO_LARGE",
    "CODE_MALFORMED_METADATA",
    "IDENTITY_CODES",
    "BINDING_CODES",
    "FIELD_CODES",
    "USAGE_TIMING_CODES",
    "METADATA_CODES",
    "REASON_CODES",
    "AuditRecord",
    "AuditRecordDecision",
    "build_audit_record",
    "query_audit_records",
]
