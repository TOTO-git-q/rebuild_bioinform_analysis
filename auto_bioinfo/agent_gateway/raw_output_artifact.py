"""Local restricted raw-output artifact reference contract (WP-05g / T-05-07).

The smallest *local* contract the future agent gateway (WP-05) needs so that —
before any real raw-output artifact *store* exists — it can take an explicit,
inert, already-returned model response (a synthetic :class:`LLMResponse`, with an
optional structured-output :class:`AdmissionDecision` binding) and produce **three
clearly separated, inert projections as data only**:

1. a **restricted raw-output artifact reference** that carries the full raw output
   internally (for a future *restricted* storage layer) but withholds it from every
   ordinary projection / ``to_dict`` / ``repr``;
2. an **ordinary business-object-safe reference** that a domain/business object may
   hold — a bounded id + fingerprint + restriction metadata, **never** the full raw
   output;
3. a **bounded audit projection** that can *trace* the relationship by ids / hashes /
   binding but likewise **never** exposes the full raw output.

— all *without ever* writing a file, artifact registry, project state, event,
queue/outbox, DB record, report, or ordinary log; without a real provider/tool/network
call; and without letting any full raw content leave the process through an ordinary
projection.

This is the local *reference-contract* foundation slice only.  It defines:

- a bounded restriction / access-tier / retention / redaction vocabulary;
- :class:`RestrictedRawOutputArtifact`, a frozen value that holds the full raw output
  privately and exposes it **only** through the explicit
  :meth:`~RestrictedRawOutputArtifact.reveal_restricted_payload` accessor (the seam a
  future restricted store would call), while its :meth:`to_dict`, business reference,
  audit projection, and ``repr`` all withhold the raw output;
- :func:`build_raw_output_artifact`, a pure builder that validates the inert inputs
  fail-closed and returns an inert :class:`RawOutputArtifactDecision` carrying either the
  restricted artifact (status ``built``) or a bounded rejection reason code (status
  ``rejected``) and **no artifact**.

Design constraints (mirroring the WP-05a..f style):

- **Pure, deterministic, offline.**  No I/O whatsoever: no network, socket, HTTP client,
  provider SDK, environment/credential access, real clock, threads, or file/DB/queue
  side effect.  A decision is a total function of its explicit in-memory inputs, and the
  builder mutates none of them.
- **Fail closed, no fallback.**  Every uncertainty resolves to a bounded, reason-coded
  ``rejected`` decision (:data:`REASON_CODES`): a malformed/invalid response, a missing /
  malformed prompt-or-admission binding, a missing parsed-result reference, a malformed
  restriction/access/retention/redaction label, an empty / oversized / non-serializable
  raw output, or any (defensive) attempt to leak the full raw output into an unrestricted
  projection all fail closed and yield **no artifact**.
- **Raw output is restricted, never leaked.**  The full raw output lives only inside the
  artifact behind :meth:`~RestrictedRawOutputArtifact.reveal_restricted_payload`; it is
  withheld from ``to_dict`` / business reference / audit projection / ``repr``.  The
  stored restricted payload is additionally **redacted** of inline secrets by default,
  and the relationship stays *traceable* through the content fingerprint and binding ids
  without exposing the content.
- **Data only.**  The builder returns *data* to the caller — an inert decision.  It
  writes no project state, business object, event, artifact file, queue/outbox record,
  domain table, report, or full-content log.

Out of scope for T-05-07 (and deliberately *not* implemented here): any real raw-output
artifact *storage*, registry, file write, or persistence; provider/model/prompt/tool-
usage/timing audit *records* beyond this minimal local reference/audit projection
(T-05-08); budgets / rate limits / circuit breakers / NEED_HUMAN_REVIEW (T-05-09);
fake-model fixture expansion (T-05-10); the eval framework (T-05-11); prompt approval /
rollback (T-05-12); and any real LLM / provider / tool / network call or content egress.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.observability.redaction import redact

from .llm_provider import LLMResponse, validate_response
from .structured_output import AdmissionDecision

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated.
MAX_REFERENCE_LENGTH = 200
MAX_LABEL_LENGTH = 64
MAX_PAYLOAD_DEPTH = 32
MAX_RAW_OUTPUT_BYTES = 131_072

# --- Bounded build-status vocabulary -----------------------------------------
# ``built`` means every check passed and a restricted artifact was produced.
# ``rejected`` is the fail-closed outcome for everything else; it carries no
# artifact.
STATUS_BUILT = "built"
STATUS_REJECTED = "rejected"

STATUSES = (STATUS_BUILT, STATUS_REJECTED)

# --- Bounded restriction / access / retention / redaction vocabulary ---------
# A raw-output artifact is *restricted* by construction; the label records how
# strongly, the access tier records who a future store would gate it to, the
# retention hint records how long a future store should keep it, and the redaction
# status records whether the stored restricted payload was scrubbed of inline
# secrets.  An unknown value in any of these fails closed.
RESTRICTION_RESTRICTED = "restricted"
RESTRICTION_HIGHLY_RESTRICTED = "highly_restricted"

RESTRICTION_LABELS = (RESTRICTION_RESTRICTED, RESTRICTION_HIGHLY_RESTRICTED)

ACCESS_TIER_RESTRICTED_STORE = "restricted_store"
ACCESS_TIER_AUDIT_ONLY = "audit_only"

ACCESS_TIERS = (ACCESS_TIER_RESTRICTED_STORE, ACCESS_TIER_AUDIT_ONLY)

RETENTION_EPHEMERAL = "ephemeral"
RETENTION_SHORT = "short"
RETENTION_STANDARD = "standard"
RETENTION_EXTENDED = "extended"

RETENTION_HINTS = (RETENTION_EPHEMERAL, RETENTION_SHORT, RETENTION_STANDARD, RETENTION_EXTENDED)

REDACTION_REDACTED = "redacted"
REDACTION_NOT_REDACTED = "not_redacted"

REDACTION_STATUSES = (REDACTION_REDACTED, REDACTION_NOT_REDACTED)

# --- Stable reason codes -----------------------------------------------------
# Callers / a future gateway branch on these machine-readable codes, never the
# human message, so they must stay stable.
CODE_MALFORMED_RESPONSE = "RAWART_MALFORMED_RESPONSE"
CODE_MISSING_BINDING = "RAWART_MISSING_BINDING"
CODE_MALFORMED_BINDING = "RAWART_MALFORMED_BINDING"
CODE_MISSING_PARSED_REF = "RAWART_MISSING_PARSED_REF"
CODE_MALFORMED_RESTRICTION = "RAWART_MALFORMED_RESTRICTION"
CODE_EMPTY_RAW_OUTPUT = "RAWART_EMPTY_RAW_OUTPUT"
CODE_RAW_OUTPUT_TOO_LARGE = "RAWART_RAW_OUTPUT_TOO_LARGE"
CODE_NONSERIALIZABLE_RAW_OUTPUT = "RAWART_NONSERIALIZABLE_RAW_OUTPUT"
CODE_MALFORMED_RAW_OUTPUT = "RAWART_MALFORMED_RAW_OUTPUT"
CODE_RAW_OUTPUT_LEAK = "RAWART_RAW_OUTPUT_LEAK"

BINDING_CODES = (
    CODE_MALFORMED_RESPONSE,
    CODE_MISSING_BINDING,
    CODE_MALFORMED_BINDING,
    CODE_MISSING_PARSED_REF,
    CODE_MALFORMED_RESTRICTION,
)

RAW_OUTPUT_CODES = (
    CODE_EMPTY_RAW_OUTPUT,
    CODE_RAW_OUTPUT_TOO_LARGE,
    CODE_NONSERIALIZABLE_RAW_OUTPUT,
    CODE_MALFORMED_RAW_OUTPUT,
    CODE_RAW_OUTPUT_LEAK,
)

REASON_CODES = BINDING_CODES + RAW_OUTPUT_CODES


# --- Small, pure predicates / helpers ----------------------------------------


def _is_bounded_token(value: Any, max_length: int) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII token."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length and all("\x20" <= ch <= "\x7e" for ch in value)


_PAYLOAD_NONSERIALIZABLE = "nonserializable"
_PAYLOAD_MALFORMED = "malformed"


class _InertPayloadError(Exception):
    """Internal: a raw-output value could not be normalized to a bounded JSON-able payload.

    ``kind`` is :data:`_PAYLOAD_NONSERIALIZABLE` for a non-serializable leaf / key
    (e.g. a set, ``bytes``, a non-string mapping key) and :data:`_PAYLOAD_MALFORMED`
    for an otherwise-malformed payload (over-deep nesting, a non-finite float).
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(f"raw output is not a bounded JSON-able value ({kind})")


def _to_plain(value: Any, depth: int = 0) -> Any:
    """Normalize ``value`` to a bounded, plain, JSON-able structure or fail closed.

    Walks mappings / lists / tuples up to :data:`MAX_PAYLOAD_DEPTH` (an over-deep
    structure fails closed), normalizes every mapping to a plain ``dict`` (rejecting a
    non-string key) and every list/tuple to a plain ``list``, and admits only JSON
    scalar leaves (``str`` / ``bool`` / ``int`` / finite ``float`` / ``None``).  Any
    other leaf, a non-string mapping key, or a non-finite float raises
    :class:`_InertPayloadError`.  Pure; performs no I/O and mutates nothing.
    """
    if depth > MAX_PAYLOAD_DEPTH:
        raise _InertPayloadError(_PAYLOAD_MALFORMED)
    # ``bool`` is a subclass of ``int``; both are admissible JSON scalars.
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _InertPayloadError(_PAYLOAD_MALFORMED)
        return value
    if isinstance(value, Mapping):
        plain: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _InertPayloadError(_PAYLOAD_NONSERIALIZABLE)
            plain[key] = _to_plain(item, depth + 1)
        return plain
    if isinstance(value, (list, tuple)):
        return [_to_plain(item, depth + 1) for item in value]
    raise _InertPayloadError(_PAYLOAD_NONSERIALIZABLE)


def _canonical_json(plain: Any) -> str:
    """Return the canonical, key-sorted JSON encoding of a plain payload."""
    return json.dumps(plain, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _fingerprint(plain: Any) -> str:
    """Return a stable sha256 content fingerprint over a plain payload (hex)."""
    return hashlib.sha256(_canonical_json(plain).encode("utf-8")).hexdigest()


# --- The restricted artifact value -------------------------------------------


@dataclass(frozen=True)
class RestrictedRawOutputArtifact:
    """An inert, restricted raw-output artifact reference — the raw output stays private.

    The full raw output is held in the private ``_restricted_payload`` field, which is
    **withheld from every ordinary projection**: :meth:`to_dict`, :meth:`business_reference`,
    :meth:`audit_projection`, and ``repr`` all expose only bounded ids / fingerprint /
    binding / restriction metadata.  The raw output is reachable **only** through the
    explicit :meth:`reveal_restricted_payload` accessor — the seam a future *restricted*
    storage layer would call.

    Fields:

    - ``artifact_id`` — a content-address-like id over the fingerprint + binding;
    - ``raw_fingerprint`` — the sha256 of the (stored, redacted) raw-output payload;
    - ``raw_byte_length`` — the byte length of that canonical payload;
    - ``provider`` / ``model`` — opaque ids carried from the inert response;
    - ``prompt_id`` / ``prompt_version`` / ``template_hash`` — the prompt binding;
    - ``admission_status`` — the structured-output admission status, when bound;
    - ``parsed_result_ref`` — the reference id of the parsed/admitted result a business
      object holds instead of the raw output;
    - ``restriction_label`` / ``access_tier`` / ``retention_hint`` / ``redaction_status``
      — the bounded restriction metadata.

    The value is inert data; constructing it performs no I/O and writes nothing.
    """

    artifact_id: str
    raw_fingerprint: str
    raw_byte_length: int
    provider: str | None
    model: str | None
    prompt_id: str
    prompt_version: str
    template_hash: str | None
    admission_status: str | None
    parsed_result_ref: str
    restriction_label: str
    access_tier: str
    retention_hint: str
    redaction_status: str
    # The full raw output, held privately.  ``repr=False`` keeps it out of the
    # dataclass repr; every projection method omits it; only
    # :meth:`reveal_restricted_payload` returns it.
    _restricted_payload: Any = field(default=None, repr=False)

    def reference_projection(self) -> dict[str, Any]:
        """The full reference metadata projection (stable key order; no raw output)."""
        return {
            "artifact_id": self.artifact_id,
            "raw_fingerprint": self.raw_fingerprint,
            "raw_byte_length": self.raw_byte_length,
            "provider": self.provider,
            "model": self.model,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "template_hash": self.template_hash,
            "admission_status": self.admission_status,
            "parsed_result_ref": self.parsed_result_ref,
            "restriction_label": self.restriction_label,
            "access_tier": self.access_tier,
            "retention_hint": self.retention_hint,
            "redaction_status": self.redaction_status,
        }

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the artifact reference — **never** the raw output."""
        return self.reference_projection()

    def business_reference(self) -> dict[str, Any]:
        """The minimal, business-object-safe reference (no raw output).

        What an ordinary domain/business object may hold in place of the raw model
        output: the artifact id, the parsed-result reference it can resolve, the content
        fingerprint for traceability, and the restriction labels — nothing else, and
        never the full raw output.
        """
        return {
            "artifact_id": self.artifact_id,
            "parsed_result_ref": self.parsed_result_ref,
            "raw_fingerprint": self.raw_fingerprint,
            "restriction_label": self.restriction_label,
            "access_tier": self.access_tier,
        }

    def audit_projection(self) -> dict[str, Any]:
        """A bounded audit projection — traceable by ids/hashes, never the raw output.

        Carries the full binding so an audit trail can *trace* the relationship between
        a parsed result and its restricted raw-output artifact, plus a ``traceable``
        marker, but withholds the full raw content entirely.
        """
        projection = self.reference_projection()
        projection["traceable"] = True
        return projection

    def reveal_restricted_payload(self) -> Any:
        """Return the stored (redacted) raw-output payload — the **restricted** accessor.

        This is the single seam through which the full raw output is reachable, intended
        only for a future *restricted* storage layer.  It is deliberately **not** the
        artifact's ``to_dict`` / business reference / audit projection / ``repr``, none of
        which ever expose the raw output.
        """
        return self._restricted_payload

    def __repr__(self) -> str:
        """A repr that withholds the raw output (only bounded reference metadata)."""
        return (
            "RestrictedRawOutputArtifact("
            f"artifact_id={self.artifact_id!r}, "
            f"raw_fingerprint={self.raw_fingerprint!r}, "
            f"raw_byte_length={self.raw_byte_length!r}, "
            f"parsed_result_ref={self.parsed_result_ref!r}, "
            f"restriction_label={self.restriction_label!r}, "
            f"access_tier={self.access_tier!r}, "
            f"redaction_status={self.redaction_status!r})"
        )


# --- The build decision ------------------------------------------------------


@dataclass(frozen=True)
class RawOutputArtifactDecision:
    """The inert result of a build: a restricted artifact, or a fail-closed reason.

    Fields:

    - ``status`` — one of :data:`STATUSES`;
    - ``reason_code`` — ``None`` when built, else the bounded rejection code
      (:data:`REASON_CODES`);
    - ``artifact`` — the :class:`RestrictedRawOutputArtifact` on a ``built`` decision,
      else ``None``.  A ``rejected`` decision never carries an artifact.

    The value is inert data; its :meth:`to_dict` / :meth:`business_reference` /
    :meth:`audit_projection` projections never expose the full raw output.
    """

    status: str
    reason_code: str | None
    artifact: RestrictedRawOutputArtifact | None = None

    @property
    def built(self) -> bool:
        """True iff a restricted artifact was produced."""
        return self.status == STATUS_BUILT

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision — **never** the raw output."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "artifact": self.artifact.to_dict() if self.artifact is not None else None,
        }

    def business_reference(self) -> dict[str, Any] | None:
        """The business-object-safe reference, or ``None`` when not built."""
        return self.artifact.business_reference() if self.artifact is not None else None

    def audit_projection(self) -> dict[str, Any] | None:
        """The bounded audit projection, or ``None`` when not built."""
        return self.artifact.audit_projection() if self.artifact is not None else None


def _rejected(reason_code: str) -> RawOutputArtifactDecision:
    """Build a fail-closed ``rejected`` decision that carries no artifact."""
    return RawOutputArtifactDecision(status=STATUS_REJECTED, reason_code=reason_code, artifact=None)


def build_raw_output_artifact(
    response: Any,
    *,
    parsed_result_ref: Any,
    prompt_id: Any = None,
    prompt_version: Any = None,
    template_hash: Any = None,
    admission: Any = None,
    raw_output: Any = None,
    restriction_label: str = RESTRICTION_RESTRICTED,
    access_tier: str = ACCESS_TIER_RESTRICTED_STORE,
    retention_hint: str = RETENTION_STANDARD,
    apply_redaction: bool = True,
) -> RawOutputArtifactDecision:
    """Build a restricted raw-output artifact reference from inert response data.

    Accepts only synthetic / in-memory already-returned response data and returns an
    inert :class:`RawOutputArtifactDecision`.  Resolution is fail-closed, in order:

    1. ``response`` must be a valid :class:`LLMResponse` (else
       :data:`CODE_MALFORMED_RESPONSE`).
    2. The prompt binding (``prompt_id`` + ``prompt_version`` + optional
       ``template_hash``) is taken from the explicit arguments, falling back to an
       optional :class:`AdmissionDecision` ``admission``; a missing id/version fails
       closed (:data:`CODE_MISSING_BINDING`), a malformed one
       (:data:`CODE_MALFORMED_BINDING`).
    3. ``parsed_result_ref`` (what a business object holds instead of the raw output)
       must be a bounded reference (else :data:`CODE_MISSING_PARSED_REF`).
    4. The restriction / access / retention labels must each be in their bounded
       vocabulary (else :data:`CODE_MALFORMED_RESTRICTION`).
    5. The raw output (``raw_output`` when supplied, else the full ``response.to_dict()``
       payload) must be non-empty, JSON-serializable, bounded, and within
       :data:`MAX_RAW_OUTPUT_BYTES` (else :data:`CODE_EMPTY_RAW_OUTPUT` /
       :data:`CODE_NONSERIALIZABLE_RAW_OUTPUT` / :data:`CODE_MALFORMED_RAW_OUTPUT` /
       :data:`CODE_RAW_OUTPUT_TOO_LARGE`).

    On success the stored restricted payload is redacted of inline secrets by default,
    the artifact is fingerprinted over that stored payload, and a defensive guard
    confirms the full raw output does not appear in any unrestricted projection (else
    :data:`CODE_RAW_OUTPUT_LEAK`).  Pure: writes nothing and mutates no input.
    """
    # 1. response shape / validity (fail closed, no fallback) ------------------
    if not isinstance(response, LLMResponse) or validate_response(response):
        return _rejected(CODE_MALFORMED_RESPONSE)

    # 2. prompt binding: explicit args first, then the optional admission ------
    if admission is not None and not isinstance(admission, AdmissionDecision):
        return _rejected(CODE_MALFORMED_BINDING)
    resolved_prompt_id = prompt_id if prompt_id is not None else (admission.prompt_id if admission is not None else None)
    resolved_version = prompt_version if prompt_version is not None else (admission.version if admission is not None else None)
    resolved_template_hash = template_hash if template_hash is not None else (admission.template_hash if admission is not None else None)
    admission_status = admission.status if admission is not None else None

    if resolved_prompt_id is None or resolved_version is None:
        return _rejected(CODE_MISSING_BINDING)
    if not _is_bounded_token(resolved_prompt_id, MAX_REFERENCE_LENGTH) or not _is_bounded_token(resolved_version, MAX_REFERENCE_LENGTH):
        return _rejected(CODE_MALFORMED_BINDING)
    if resolved_template_hash is not None and not _is_bounded_token(resolved_template_hash, MAX_REFERENCE_LENGTH):
        return _rejected(CODE_MALFORMED_BINDING)
    if admission_status is not None and not _is_bounded_token(admission_status, MAX_LABEL_LENGTH):
        return _rejected(CODE_MALFORMED_BINDING)

    # 3. parsed-result reference (held by business objects, not the raw output) -
    if not _is_bounded_token(parsed_result_ref, MAX_REFERENCE_LENGTH):
        return _rejected(CODE_MISSING_PARSED_REF)

    # 4. bounded restriction / access / retention / redaction labels -----------
    redaction_status = REDACTION_REDACTED if apply_redaction else REDACTION_NOT_REDACTED
    if (
        restriction_label not in RESTRICTION_LABELS
        or access_tier not in ACCESS_TIERS
        or retention_hint not in RETENTION_HINTS
        or not isinstance(apply_redaction, bool)
    ):
        return _rejected(CODE_MALFORMED_RESTRICTION)

    # 5. raw output: present, serializable, bounded ----------------------------
    source = raw_output if raw_output is not None else response.to_dict()
    try:
        plain = _to_plain(source)
    except _InertPayloadError as exc:
        return _rejected(CODE_NONSERIALIZABLE_RAW_OUTPUT if exc.kind == _PAYLOAD_NONSERIALIZABLE else CODE_MALFORMED_RAW_OUTPUT)
    if plain is None or plain == "" or plain == {} or plain == []:
        return _rejected(CODE_EMPTY_RAW_OUTPUT)
    # Redact inline secrets from the *stored* restricted payload by default so even
    # the restricted store never holds a raw credential-like value.
    stored_payload = redact(plain) if apply_redaction else plain
    stored_json = _canonical_json(stored_payload)
    raw_byte_length = len(stored_json.encode("utf-8"))
    if raw_byte_length > MAX_RAW_OUTPUT_BYTES:
        return _rejected(CODE_RAW_OUTPUT_TOO_LARGE)

    raw_fingerprint = _fingerprint(stored_payload)
    artifact_id = make_stable_id(
        "rawart",
        {
            "fingerprint": raw_fingerprint,
            "prompt_id": resolved_prompt_id,
            "version": resolved_version,
            "parsed_result_ref": parsed_result_ref,
        },
    )

    artifact = RestrictedRawOutputArtifact(
        artifact_id=artifact_id,
        raw_fingerprint=raw_fingerprint,
        raw_byte_length=raw_byte_length,
        provider=response.provider if isinstance(response.provider, str) else None,
        model=response.model if isinstance(response.model, str) else None,
        prompt_id=resolved_prompt_id,
        prompt_version=resolved_version,
        template_hash=resolved_template_hash,
        admission_status=admission_status,
        parsed_result_ref=parsed_result_ref,
        restriction_label=restriction_label,
        access_tier=access_tier,
        retention_hint=retention_hint,
        redaction_status=redaction_status,
        _restricted_payload=stored_payload,
    )

    # Defensive, belt-and-suspenders fail-closed: the full raw output must never appear
    # in any unrestricted projection.  This can only fire on an internal invariant
    # violation, in which case we emit no artifact at all.
    if _projection_leaks_raw(artifact, stored_json):
        return _rejected(CODE_RAW_OUTPUT_LEAK)

    return RawOutputArtifactDecision(status=STATUS_BUILT, reason_code=None, artifact=artifact)


def _projection_leaks_raw(artifact: RestrictedRawOutputArtifact, stored_json: str) -> bool:
    """True iff the full stored raw output appears in any unrestricted projection.

    A defensive invariant check: a non-trivial raw payload must not be a substring of
    the serialized business / audit / to_dict projections.  A trivially short payload
    (which the fingerprint/ids legitimately could echo) is exempt to avoid false
    positives; the projections never include the raw output by construction regardless.
    """
    if len(stored_json) < 8:
        return False
    for projection in (artifact.to_dict(), artifact.business_reference(), artifact.audit_projection()):
        if stored_json in _canonical_json(projection):
            return True
    return False


__all__ = [
    "MAX_REFERENCE_LENGTH",
    "MAX_LABEL_LENGTH",
    "MAX_PAYLOAD_DEPTH",
    "MAX_RAW_OUTPUT_BYTES",
    "STATUS_BUILT",
    "STATUS_REJECTED",
    "STATUSES",
    "RESTRICTION_RESTRICTED",
    "RESTRICTION_HIGHLY_RESTRICTED",
    "RESTRICTION_LABELS",
    "ACCESS_TIER_RESTRICTED_STORE",
    "ACCESS_TIER_AUDIT_ONLY",
    "ACCESS_TIERS",
    "RETENTION_EPHEMERAL",
    "RETENTION_SHORT",
    "RETENTION_STANDARD",
    "RETENTION_EXTENDED",
    "RETENTION_HINTS",
    "REDACTION_REDACTED",
    "REDACTION_NOT_REDACTED",
    "REDACTION_STATUSES",
    "CODE_MALFORMED_RESPONSE",
    "CODE_MISSING_BINDING",
    "CODE_MALFORMED_BINDING",
    "CODE_MISSING_PARSED_REF",
    "CODE_MALFORMED_RESTRICTION",
    "CODE_EMPTY_RAW_OUTPUT",
    "CODE_RAW_OUTPUT_TOO_LARGE",
    "CODE_NONSERIALIZABLE_RAW_OUTPUT",
    "CODE_MALFORMED_RAW_OUTPUT",
    "CODE_RAW_OUTPUT_LEAK",
    "BINDING_CODES",
    "RAW_OUTPUT_CODES",
    "REASON_CODES",
    "RestrictedRawOutputArtifact",
    "RawOutputArtifactDecision",
    "build_raw_output_artifact",
]
