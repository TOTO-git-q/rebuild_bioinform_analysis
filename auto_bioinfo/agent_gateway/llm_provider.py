"""Local LLM provider interface + fake-provider contract foundation (WP-05a / T-05-01).

The smallest provider-agnostic, *local* contract layer the future agent gateway
(WP-05) needs so the rest of the system can describe a single question — *given an
explicit request, what completion, finish reason, and usage does a provider
return?* — **without ever opening a socket, importing a provider SDK, reading an
API key/credential/environment variable, reaching the network, calling a paid
service, or letting any content leave the process**.

This is the foundation slice only.  It defines:

- a small, provider-agnostic :class:`LLMProvider` ``Protocol`` (the seam a future
  network adapter will implement, mirroring the reserved ports under
  :mod:`auto_bioinfo.ports`);
- deterministic, serializable request / message / usage / response value shapes
  (frozen dataclasses with ``to_dict`` projections);
- bounded validators + a bounded :class:`LLMContractError` so a malformed
  request/response fails closed with a stable reason code rather than silently
  entering domain state; and
- a deterministic, offline :class:`FakeLLMProvider` for tests that answers purely
  from explicit in-memory fixtures (or a deterministic echo) — never a real model.

Design constraints (WP-05a), mirroring the WP-04 control-plane contract style:

- **Pure, deterministic, offline.**  No I/O whatsoever: no network, no socket, no
  HTTP client, no provider SDK, no environment/credential/secret access, **no real
  clock**, no threads, and no file/DB/queue side effect.  The fake provider is a
  total function of its explicit in-memory inputs and fixtures.
- **Provider-agnostic.**  The request/response shapes name a provider/model only as
  opaque bounded identifiers; nothing here is tied to a specific vendor, and the
  contract carries no transport, connection, or authentication state.
- **Fail closed.**  Every uncertainty resolves to a bounded, reason-coded error
  (:data:`REASON_CODES`).  A malformed model id, malformed/empty/oversized message
  list, malformed role/content, malformed sampling field, malformed/forbidden
  metadata (e.g. anything that looks like a credential), or inconsistent usage all
  raise :class:`LLMContractError` or surface via a ``validate_*`` helper — never a
  silent acceptance and never an unhandled low-level exception.
- **Data only.**  A provider call returns *data* to the caller.  It writes no
  project state, business object, event, artifact, ordinary domain table, or log of
  full content.  An :class:`LLMResponse` is an inert value, never a side effect.

Out of scope for T-05-01 (and deliberately *not* implemented here): any real
provider/HTTP/SDK integration or content egress, the PromptRegistry / prompt
versioning (T-05-02), structured-output parsing / schema-repair / gateway
admission (T-05-03), the domain semantic validator hook (T-05-04), the sensitive
content classifier / egress policy (T-05-05), the tool broker (T-05-06), and any
audit-record / budget / rate-limit / circuit-breaker machinery (T-05-07..12).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from auto_bioinfo.core.ids import hash_payload

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated.
MAX_MODEL_ID_LENGTH = 200
MAX_PROVIDER_ID_LENGTH = 200
MAX_MESSAGES = 256
MAX_CONTENT_LENGTH = 200_000
MAX_STOP_SEQUENCES = 8
MAX_STOP_SEQUENCE_LENGTH = 200
MAX_OUTPUT_TOKENS = 1_000_000
MAX_TOKEN_COUNT = 100_000_000
MAX_METADATA_ENTRIES = 32
MAX_METADATA_KEY_LENGTH = 100
MAX_METADATA_VALUE_LENGTH = 500

# --- Bounded role vocabulary -------------------------------------------------
# A provider-agnostic minimal chat role set; an unknown role fails closed.
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

ROLES = (ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT)

# --- Bounded finish-reason vocabulary ----------------------------------------
# Why a completion stopped, as a small stable set callers branch on.
FINISH_STOP = "stop"
FINISH_LENGTH = "length"
FINISH_CONTENT_FILTER = "content_filter"
FINISH_ERROR = "error"

FINISH_REASONS = (FINISH_STOP, FINISH_LENGTH, FINISH_CONTENT_FILTER, FINISH_ERROR)

# --- Forbidden metadata key markers ------------------------------------------
# This contract must never carry a token/key/secret.  A metadata key whose
# lowercased form contains any of these markers fails closed: the gateway records
# bounded, non-sensitive identifiers only, never credentials.
FORBIDDEN_METADATA_KEY_MARKERS = (
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "password",
    "passwd",
    "bearer",
    "credential",
    "private_key",
    "access_key",
    "authorization",
    "auth_token",
    "access_token",
    "refresh_token",
)

# --- Stable reason codes -----------------------------------------------------
# Callers / a future adapter branch on these machine-readable codes, never the
# human message, so they must stay stable.
# request:
CODE_MALFORMED_MODEL = "LLM_MALFORMED_MODEL"
CODE_MALFORMED_MESSAGES = "LLM_MALFORMED_MESSAGES"
CODE_EMPTY_MESSAGES = "LLM_EMPTY_MESSAGES"
CODE_TOO_MANY_MESSAGES = "LLM_TOO_MANY_MESSAGES"
CODE_MALFORMED_ROLE = "LLM_MALFORMED_ROLE"
CODE_MALFORMED_CONTENT = "LLM_MALFORMED_CONTENT"
CODE_CONTENT_TOO_LONG = "LLM_CONTENT_TOO_LONG"
CODE_MALFORMED_MAX_TOKENS = "LLM_MALFORMED_MAX_TOKENS"
CODE_MALFORMED_TEMPERATURE = "LLM_MALFORMED_TEMPERATURE"
CODE_MALFORMED_STOP = "LLM_MALFORMED_STOP"
CODE_MALFORMED_METADATA = "LLM_MALFORMED_METADATA"
CODE_FORBIDDEN_METADATA = "LLM_FORBIDDEN_METADATA"
# usage:
CODE_MALFORMED_USAGE = "LLM_MALFORMED_USAGE"
CODE_NEGATIVE_TOKENS = "LLM_NEGATIVE_TOKENS"
CODE_TOKENS_TOO_LARGE = "LLM_TOKENS_TOO_LARGE"
CODE_USAGE_INCONSISTENT = "LLM_USAGE_INCONSISTENT"
# response:
CODE_MALFORMED_RESPONSE = "LLM_MALFORMED_RESPONSE"
CODE_MALFORMED_PROVIDER = "LLM_MALFORMED_PROVIDER"
CODE_MALFORMED_FINISH_REASON = "LLM_MALFORMED_FINISH_REASON"

REQUEST_CODES = (
    CODE_MALFORMED_MODEL,
    CODE_MALFORMED_MESSAGES,
    CODE_EMPTY_MESSAGES,
    CODE_TOO_MANY_MESSAGES,
    CODE_MALFORMED_ROLE,
    CODE_MALFORMED_CONTENT,
    CODE_CONTENT_TOO_LONG,
    CODE_MALFORMED_MAX_TOKENS,
    CODE_MALFORMED_TEMPERATURE,
    CODE_MALFORMED_STOP,
    CODE_MALFORMED_METADATA,
    CODE_FORBIDDEN_METADATA,
)

USAGE_CODES = (
    CODE_MALFORMED_USAGE,
    CODE_NEGATIVE_TOKENS,
    CODE_TOKENS_TOO_LARGE,
    CODE_USAGE_INCONSISTENT,
)

RESPONSE_CODES = (
    CODE_MALFORMED_RESPONSE,
    CODE_MALFORMED_PROVIDER,
    CODE_MALFORMED_FINISH_REASON,
)

REASON_CODES = REQUEST_CODES + USAGE_CODES + RESPONSE_CODES


class LLMContractError(Exception):
    """A bounded, reason-coded contract failure raised by the local LLM contract.

    ``code`` is one of :data:`REASON_CODES`; ``message`` is a human-readable
    explanation a caller may surface but should never branch on (branch on
    ``code``).  This is the fail-closed signal a malformed request/response or a
    forbidden (credential-like) field produces — it carries no I/O, transport, or
    provider state.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# --- Small, pure predicates --------------------------------------------------


def _is_nonnegative_int(value: Any) -> bool:
    """A real non-negative integer — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_positive_int(value: Any) -> bool:
    """A real positive integer — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_real_number(value: Any) -> bool:
    """A real ``int``/``float`` — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_bounded_token(value: Any, max_length: int) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII id.

    Used for provider/model identifiers: visible ASCII plus spaces (0x20–0x7e), no
    control characters or newlines, and within ``max_length``.
    """
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length and all("\x20" <= ch <= "\x7e" for ch in value)


# --- Message / content shape -------------------------------------------------


@dataclass(frozen=True)
class LLMMessage:
    """One chat message: a bounded role and opaque text content.

    The content is plain text only — this foundation slice models no images,
    binary parts, or tool-call payloads (those belong to later T-05 slices).  The
    value is inert data; constructing it performs no I/O.
    """

    role: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the message (stable key order)."""
        return {"role": self.role, "content": self.content}


def validate_message(message: Any) -> list[tuple[str, str]]:
    """Return a list of ``(code, message)`` problems with ``message`` (empty == valid)."""
    if not isinstance(message, LLMMessage):
        return [(CODE_MALFORMED_MESSAGES, "each message must be an LLMMessage")]
    errors: list[tuple[str, str]] = []
    if message.role not in ROLES:
        errors.append((CODE_MALFORMED_ROLE, f"role {message.role!r} is not one of {ROLES}"))
    if not isinstance(message.content, str):
        errors.append((CODE_MALFORMED_CONTENT, "message content must be a string"))
    elif len(message.content) > MAX_CONTENT_LENGTH:
        errors.append((CODE_CONTENT_TOO_LONG, f"message content length {len(message.content)} exceeds the maximum of {MAX_CONTENT_LENGTH}"))
    return errors


# --- Usage shape -------------------------------------------------------------


@dataclass(frozen=True)
class LLMUsage:
    """Bounded, non-negative token-count metadata for a completion.

    This is *counts only* — provider/model token usage as plain integers.  It is
    deliberately **not** billing, money, latency/timing, rate-limit, budget, or
    circuit-breaker data (all out of scope for T-05-01).
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_counts(cls, prompt_tokens: int, completion_tokens: int) -> LLMUsage:
        """Build a usage value with ``total_tokens`` derived as the consistent sum."""
        return cls(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens)

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the usage (stable key order)."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


def validate_usage(usage: Any) -> list[tuple[str, str]]:
    """Return a list of ``(code, message)`` problems with ``usage`` (empty == valid).

    Token fields must be real non-negative integers within :data:`MAX_TOKEN_COUNT`,
    and ``total_tokens`` must equal ``prompt_tokens + completion_tokens`` (a forged
    total fails closed rather than silently entering domain state).
    """
    if not isinstance(usage, LLMUsage):
        return [(CODE_MALFORMED_USAGE, "usage must be an LLMUsage")]
    errors: list[tuple[str, str]] = []
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, name)
        if not _is_nonnegative_int(value):
            errors.append((CODE_NEGATIVE_TOKENS, f"usage.{name} must be a non-negative integer"))
        elif value > MAX_TOKEN_COUNT:
            errors.append((CODE_TOKENS_TOO_LARGE, f"usage.{name} ({value}) exceeds the maximum of {MAX_TOKEN_COUNT}"))
    if not errors and usage.total_tokens != usage.prompt_tokens + usage.completion_tokens:
        errors.append(
            (
                CODE_USAGE_INCONSISTENT,
                f"usage.total_tokens ({usage.total_tokens}) must equal prompt_tokens + completion_tokens ({usage.prompt_tokens + usage.completion_tokens})",
            )
        )
    return errors


# --- Metadata validation (shared by request and response) --------------------


def _validate_metadata(metadata: Any) -> list[tuple[str, str]]:
    """Return problems with optional bounded scalar metadata (empty == valid).

    ``None`` is permitted.  Otherwise it must be a mapping of bounded string keys to
    bounded JSON scalar values (str/int/float/bool), with no nested structures, no
    forbidden (credential-like) key, and within the entry/key/value bounds.  This
    keeps metadata serializable, bounded, and free of secrets.
    """
    if metadata is None:
        return []
    if not isinstance(metadata, Mapping):
        return [(CODE_MALFORMED_METADATA, "metadata, when supplied, must be a mapping")]
    if len(metadata) > MAX_METADATA_ENTRIES:
        return [(CODE_MALFORMED_METADATA, f"metadata has more than {MAX_METADATA_ENTRIES} entries")]
    errors: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not key or len(key) > MAX_METADATA_KEY_LENGTH:
            errors.append((CODE_MALFORMED_METADATA, "metadata keys must be non-blank strings within the length bound"))
            continue
        lowered = key.lower()
        if any(marker in lowered for marker in FORBIDDEN_METADATA_KEY_MARKERS):
            errors.append((CODE_FORBIDDEN_METADATA, f"metadata key {key!r} looks like a credential/secret and is forbidden"))
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            continue
        if isinstance(value, str):
            if len(value) > MAX_METADATA_VALUE_LENGTH:
                errors.append((CODE_MALFORMED_METADATA, f"metadata value for {key!r} exceeds the length bound of {MAX_METADATA_VALUE_LENGTH}"))
            continue
        errors.append((CODE_MALFORMED_METADATA, f"metadata value for {key!r} must be a string, number, or boolean"))
    return errors


# --- Request shape -----------------------------------------------------------


@dataclass(frozen=True)
class LLMRequest:
    """A provider-agnostic completion request, as a pure in-memory contract value.

    Fields:

    - ``model`` — an opaque, bounded provider model identifier;
    - ``messages`` — an ordered, non-empty, bounded tuple of :class:`LLMMessage`;
    - ``max_output_tokens`` — optional positive cap on the completion length;
    - ``temperature`` — optional sampling temperature in ``[0.0, 2.0]``;
    - ``stop`` — optional bounded tuple of stop sequences;
    - ``metadata`` — optional bounded scalar metadata (never credentials).

    ``messages`` and ``stop`` are coerced to tuples so the value is hashable and
    deterministic.  The object holds no transport, connection, credential, or
    execution state — it is the parsed *facts* a future adapter would hand to a
    provider.
    """

    model: str
    messages: tuple[LLMMessage, ...]
    max_output_tokens: int | None = None
    temperature: float | None = None
    stop: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        # Coerce common iterable inputs to tuples for hashability/determinism
        # without validating semantics (validation is explicit, via validate_request
        # / the provider).  Strings are never treated as iterables of characters.
        if isinstance(self.messages, list):
            object.__setattr__(self, "messages", tuple(self.messages))
        if isinstance(self.stop, list):
            object.__setattr__(self, "stop", tuple(self.stop))

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the request (stable key order)."""
        return {
            "model": self.model,
            "messages": [m.to_dict() for m in self.messages],
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "stop": list(self.stop),
            "metadata": dict(self.metadata) if self.metadata is not None else None,
        }

    def fingerprint(self) -> str:
        """A stable content fingerprint over the request, key-order independent.

        Reuses the core canonical-hash facility so two logically identical requests
        share a fingerprint (used by the fake provider to look up scripted answers).
        """
        return hash_payload(self.to_dict())


def validate_request(request: Any) -> list[tuple[str, str]]:
    """Return a list of ``(code, message)`` problems with ``request`` (empty == valid)."""
    if not isinstance(request, LLMRequest):
        return [(CODE_MALFORMED_MESSAGES, "request must be an LLMRequest")]
    errors: list[tuple[str, str]] = []

    if not _is_bounded_token(request.model, MAX_MODEL_ID_LENGTH):
        errors.append((CODE_MALFORMED_MODEL, "model must be a non-blank, bounded, single-line printable-ASCII identifier"))

    if not isinstance(request.messages, tuple):
        errors.append((CODE_MALFORMED_MESSAGES, "messages must be a sequence of LLMMessage"))
    elif not request.messages:
        errors.append((CODE_EMPTY_MESSAGES, "messages must contain at least one message"))
    elif len(request.messages) > MAX_MESSAGES:
        errors.append((CODE_TOO_MANY_MESSAGES, f"messages length {len(request.messages)} exceeds the maximum of {MAX_MESSAGES}"))
    else:
        for index, message in enumerate(request.messages):
            for code, message_text in validate_message(message):
                errors.append((code, f"messages[{index}]: {message_text}"))

    if request.max_output_tokens is not None:
        if not _is_positive_int(request.max_output_tokens) or request.max_output_tokens > MAX_OUTPUT_TOKENS:
            errors.append((CODE_MALFORMED_MAX_TOKENS, f"max_output_tokens, when supplied, must be a positive integer within {MAX_OUTPUT_TOKENS}"))

    if request.temperature is not None:
        if not _is_real_number(request.temperature) or not (0.0 <= float(request.temperature) <= 2.0):
            errors.append((CODE_MALFORMED_TEMPERATURE, "temperature, when supplied, must be a number in [0.0, 2.0]"))

    if not isinstance(request.stop, tuple):
        errors.append((CODE_MALFORMED_STOP, "stop must be a sequence of strings"))
    elif len(request.stop) > MAX_STOP_SEQUENCES:
        errors.append((CODE_MALFORMED_STOP, f"stop has more than {MAX_STOP_SEQUENCES} sequences"))
    else:
        for sequence in request.stop:
            if not isinstance(sequence, str) or not sequence or len(sequence) > MAX_STOP_SEQUENCE_LENGTH:
                errors.append((CODE_MALFORMED_STOP, "each stop sequence must be a non-blank string within the length bound"))
                break

    errors.extend(_validate_metadata(request.metadata))
    return errors


# --- Response shape ----------------------------------------------------------


@dataclass(frozen=True)
class LLMResponse:
    """A provider-agnostic completion response, as a pure in-memory contract value.

    Fields:

    - ``provider`` — an opaque, bounded provider identifier (e.g. the fake provider);
    - ``model`` — the opaque, bounded model identifier that produced the completion;
    - ``message`` — the assistant :class:`LLMMessage` (the completion text);
    - ``finish_reason`` — one of :data:`FINISH_REASONS`;
    - ``usage`` — bounded :class:`LLMUsage` token counts;
    - ``metadata`` — optional bounded scalar metadata (never credentials).

    The value is inert data returned to the caller; it is never written to project
    state, events, artifacts, domain tables, or full-content logs.
    """

    provider: str
    model: str
    message: LLMMessage
    finish_reason: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the response (stable key order)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "message": self.message.to_dict() if isinstance(self.message, LLMMessage) else self.message,
            "finish_reason": self.finish_reason,
            "usage": self.usage.to_dict() if isinstance(self.usage, LLMUsage) else self.usage,
            "metadata": dict(self.metadata) if self.metadata is not None else None,
        }


def validate_response(response: Any) -> list[tuple[str, str]]:
    """Return a list of ``(code, message)`` problems with ``response`` (empty == valid).

    A response's assistant message must itself be a valid assistant message; the
    provider/model identifiers must be bounded; the finish reason must be a known
    value; and the usage must validate (consistent, bounded, non-negative).
    """
    if not isinstance(response, LLMResponse):
        return [(CODE_MALFORMED_RESPONSE, "response must be an LLMResponse")]
    errors: list[tuple[str, str]] = []

    if not _is_bounded_token(response.provider, MAX_PROVIDER_ID_LENGTH):
        errors.append((CODE_MALFORMED_PROVIDER, "provider must be a non-blank, bounded, single-line printable-ASCII identifier"))
    if not _is_bounded_token(response.model, MAX_MODEL_ID_LENGTH):
        errors.append((CODE_MALFORMED_MODEL, "model must be a non-blank, bounded, single-line printable-ASCII identifier"))

    for code, message_text in validate_message(response.message):
        errors.append((code, f"message: {message_text}"))
    if isinstance(response.message, LLMMessage) and response.message.role != ROLE_ASSISTANT:
        errors.append((CODE_MALFORMED_ROLE, f"response message role must be {ROLE_ASSISTANT!r}"))

    if response.finish_reason not in FINISH_REASONS:
        errors.append((CODE_MALFORMED_FINISH_REASON, f"finish_reason {response.finish_reason!r} is not one of {FINISH_REASONS}"))

    errors.extend(validate_usage(response.usage))
    errors.extend(_validate_metadata(response.metadata))
    return errors


def ensure_valid_request(request: Any) -> LLMRequest:
    """Return ``request`` unchanged if valid, else raise :class:`LLMContractError`.

    A fail-closed constructor guard: the first reason code is raised so a malformed
    request never reaches a provider.
    """
    errors = validate_request(request)
    if errors:
        code, message = errors[0]
        raise LLMContractError(code, message)
    return request


def ensure_valid_response(response: Any) -> LLMResponse:
    """Return ``response`` unchanged if valid, else raise :class:`LLMContractError`.

    A fail-closed guard so a malformed/forged response never enters domain state.
    """
    errors = validate_response(response)
    if errors:
        code, message = errors[0]
        raise LLMContractError(code, message)
    return response


# --- The provider seam -------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """The provider-agnostic seam the future agent gateway depends on.

    The default (and only) adapter today is the offline, deterministic
    :class:`FakeLLMProvider`.  A RESERVED production adapter — a network LLM
    provider reached through an audited tool broker — would implement this same
    structural protocol without the gateway changing; its output must still pass
    :func:`validate_response`, and it never writes domain state directly (mirroring
    the reserved ports in :mod:`auto_bioinfo.ports`).
    """

    provider_id: str

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return a validated :class:`LLMResponse` for ``request`` (no side effects)."""
        ...


class FakeLLMProvider:
    """A deterministic, offline provider for tests — never a real model.

    It answers purely from explicit in-memory fixtures: an optional set of scripted
    ``(LLMRequest -> LLMResponse)`` pairs keyed by request fingerprint, falling back
    to a deterministic echo of the last user message.  It performs **no** network,
    socket, SDK, environment, credential, clock, or file access; token *counts* are
    a deterministic word-count proxy, not a real tokenizer, model, or billing
    measurement.  ``complete`` returns inert data and writes nothing.
    """

    def __init__(
        self,
        *,
        provider_id: str = "fake-local",
        model: str = "fake-echo-1",
        scripted: Iterable[tuple[LLMRequest, LLMResponse]] | None = None,
    ) -> None:
        if not _is_bounded_token(provider_id, MAX_PROVIDER_ID_LENGTH):
            raise LLMContractError(CODE_MALFORMED_PROVIDER, "provider_id must be a non-blank, bounded, single-line printable-ASCII identifier")
        if not _is_bounded_token(model, MAX_MODEL_ID_LENGTH):
            raise LLMContractError(CODE_MALFORMED_MODEL, "model must be a non-blank, bounded, single-line printable-ASCII identifier")
        self.provider_id = provider_id
        self.model = model
        # Build the scripted index, validating both ends so a malformed fixture
        # fails closed at registration rather than at call time.
        self._scripted: dict[str, LLMResponse] = {}
        for request, response in scripted or ():
            ensure_valid_request(request)
            ensure_valid_response(response)
            self._scripted[request.fingerprint()] = response

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return a validated response for ``request``, fail-closed on a malformed request.

        A scripted fixture (matched by request fingerprint) is returned verbatim;
        otherwise a deterministic echo response is synthesised.  The result is always
        re-validated before return.
        """
        ensure_valid_request(request)
        scripted = self._scripted.get(request.fingerprint())
        if scripted is not None:
            return scripted
        return ensure_valid_response(self._echo(request))

    def _echo(self, request: LLMRequest) -> LLMResponse:
        """Synthesise a deterministic echo completion for ``request`` (offline)."""
        last_user = ""
        for message in request.messages:
            if message.role == ROLE_USER:
                last_user = message.content
        reply_text = f"[{self.provider_id}] echo: {last_user}"
        if len(reply_text) > MAX_CONTENT_LENGTH:
            reply_text = reply_text[:MAX_CONTENT_LENGTH]
        prompt_tokens = min(sum(_estimate_tokens(m.content) for m in request.messages), MAX_TOKEN_COUNT)
        completion_tokens = min(_estimate_tokens(reply_text), MAX_TOKEN_COUNT)
        return LLMResponse(
            provider=self.provider_id,
            model=request.model,
            message=LLMMessage(role=ROLE_ASSISTANT, content=reply_text),
            finish_reason=FINISH_STOP,
            usage=LLMUsage.from_counts(prompt_tokens, completion_tokens),
        )


def _estimate_tokens(text: str) -> int:
    """A deterministic, offline word-count proxy for token usage (never a tokenizer).

    Returns a non-negative count; it is *not* a real model tokenizer and carries no
    billing, timing, or rate-limit meaning.
    """
    if not isinstance(text, str):
        return 0
    return len(text.split())


__all__ = [
    "MAX_MODEL_ID_LENGTH",
    "MAX_PROVIDER_ID_LENGTH",
    "MAX_MESSAGES",
    "MAX_CONTENT_LENGTH",
    "MAX_STOP_SEQUENCES",
    "MAX_STOP_SEQUENCE_LENGTH",
    "MAX_OUTPUT_TOKENS",
    "MAX_TOKEN_COUNT",
    "MAX_METADATA_ENTRIES",
    "MAX_METADATA_KEY_LENGTH",
    "MAX_METADATA_VALUE_LENGTH",
    "ROLE_SYSTEM",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLES",
    "FINISH_STOP",
    "FINISH_LENGTH",
    "FINISH_CONTENT_FILTER",
    "FINISH_ERROR",
    "FINISH_REASONS",
    "FORBIDDEN_METADATA_KEY_MARKERS",
    "CODE_MALFORMED_MODEL",
    "CODE_MALFORMED_MESSAGES",
    "CODE_EMPTY_MESSAGES",
    "CODE_TOO_MANY_MESSAGES",
    "CODE_MALFORMED_ROLE",
    "CODE_MALFORMED_CONTENT",
    "CODE_CONTENT_TOO_LONG",
    "CODE_MALFORMED_MAX_TOKENS",
    "CODE_MALFORMED_TEMPERATURE",
    "CODE_MALFORMED_STOP",
    "CODE_MALFORMED_METADATA",
    "CODE_FORBIDDEN_METADATA",
    "CODE_MALFORMED_USAGE",
    "CODE_NEGATIVE_TOKENS",
    "CODE_TOKENS_TOO_LARGE",
    "CODE_USAGE_INCONSISTENT",
    "CODE_MALFORMED_RESPONSE",
    "CODE_MALFORMED_PROVIDER",
    "CODE_MALFORMED_FINISH_REASON",
    "REQUEST_CODES",
    "USAGE_CODES",
    "RESPONSE_CODES",
    "REASON_CODES",
    "LLMContractError",
    "LLMMessage",
    "LLMUsage",
    "LLMRequest",
    "LLMResponse",
    "LLMProvider",
    "FakeLLMProvider",
    "validate_message",
    "validate_usage",
    "validate_request",
    "validate_response",
    "ensure_valid_request",
    "ensure_valid_response",
]
