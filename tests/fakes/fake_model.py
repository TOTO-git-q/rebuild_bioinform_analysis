"""Offline, deterministic fake-model fixtures (WP-05j / T-05-10).

The fixture surface tests use to answer the single question *given a fixture id,
what canned completion (or bounded error) does the offline fake model return?* —
**without ever opening a socket, importing a provider SDK, reading a credential or
environment variable, reaching the network, calling a paid service, touching the
filesystem/clock/randomness, or letting any content leave the process**.

It is a thin, test-only layer over the provider-agnostic local contract in
:mod:`auto_bioinfo.agent_gateway.llm_provider` (WP-05a / T-05-01):

- a :class:`FakeResponseFixture` wraps a pre-validated, inert :class:`LLMResponse`;
- a :class:`FakeErrorFixture` is a bounded, reason-coded synthetic failure
  (configured fake error/refusal, or — at call time — an unknown/malformed
  request);
- a :class:`FixtureFakeModel` is a deterministic, offline object compatible with
  the :class:`LLMProvider` protocol: ``complete(request)`` resolves a fixture by
  the synthetic ``fixture_id`` carried in request metadata and returns the canned
  response, failing closed with a stable reason code on an unknown id or a
  malformed request.

Design constraints (mirroring the WP-05a contract style and ``tests/README.md``):

- **Pure, deterministic, offline.**  No I/O of any kind: no network, socket, HTTP
  client, provider SDK, environment/credential access, real clock, randomness,
  thread, subprocess, or file/DB/queue/log side effect.  A fixture lookup is a
  total function of its explicit in-memory inputs; repeated calls return equal
  values.
- **Fail closed.**  An unknown fixture id, a malformed request, or a configured
  error fixture raises a bounded :class:`FakeModelError` carrying a stable
  :data:`FAKE_REASON_CODES` code — never a silent default and never an unhandled
  low-level exception.
- **Synthetic only.**  Every fixture id, model/provider id, text, and usage
  counter is a tiny synthetic placeholder.  No real prompt, raw user/project
  content, real model output, secret, credential, or human-derived data is ever
  present; canned responses are re-validated through the contract (which forbids
  credential-like metadata) at build time.
- **Data only.**  A fixture is inert value data; resolving one writes no project
  state, event, artifact, domain table, or content log.

This package is deliberately additive and test-only: it touches no production
module and changes no public provider/gateway semantics.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from auto_bioinfo.agent_gateway.llm_provider import (
    FINISH_CONTENT_FILTER,
    FINISH_STOP,
    MAX_PROVIDER_ID_LENGTH,
    ROLE_ASSISTANT,
    ROLE_USER,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    _is_bounded_token,
    ensure_valid_response,
    validate_request,
)

# --- Synthetic identifiers (placeholders; never a real provider/model) -------
DEFAULT_FAKE_PROVIDER = "fake-local"
DEFAULT_FAKE_MODEL = "offline-fake-model"

# The request-metadata key a :class:`FixtureFakeModel` reads to resolve which
# canned fixture to return.  It is an ordinary bounded scalar metadata key (never
# a credential marker), so a request carrying it still passes the contract.
FIXTURE_ID_METADATA_KEY = "fixture_id"

MAX_FIXTURE_ID_LENGTH = 100

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these machine-readable codes, never the human message, so they
# must stay stable.
CODE_UNKNOWN_FIXTURE = "FAKE_UNKNOWN_FIXTURE"
CODE_MALFORMED_FIXTURE_REQUEST = "FAKE_MALFORMED_REQUEST"
CODE_FIXTURE_ERROR = "FAKE_FIXTURE_ERROR"
CODE_DUPLICATE_FIXTURE = "FAKE_DUPLICATE_FIXTURE"

FAKE_REASON_CODES = (
    CODE_UNKNOWN_FIXTURE,
    CODE_MALFORMED_FIXTURE_REQUEST,
    CODE_FIXTURE_ERROR,
    CODE_DUPLICATE_FIXTURE,
)


class FakeModelError(Exception):
    """A bounded, reason-coded failure from the offline fake-model fixtures.

    ``code`` is one of :data:`FAKE_REASON_CODES`; ``message`` is a human-readable
    explanation a caller may surface but should never branch on (branch on
    ``code``).  This is the fail-closed signal an unknown fixture id, a malformed
    request, or a configured error fixture produces — it carries no I/O, transport,
    or provider state.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _ensure_bounded_fixture_id(fixture_id: object) -> str:
    """Return ``fixture_id`` if a bounded synthetic id, else fail closed."""
    if not _is_bounded_token(fixture_id, MAX_FIXTURE_ID_LENGTH):
        raise FakeModelError(
            CODE_MALFORMED_FIXTURE_REQUEST,
            "fixture_id must be a non-blank, bounded, single-line printable-ASCII identifier",
        )
    return fixture_id  # type: ignore[return-value]


# --- Fixture value shapes ----------------------------------------------------


@dataclass(frozen=True)
class FakeResponseFixture:
    """A canned successful (or refusal) completion keyed by a synthetic id.

    ``response`` is a pre-validated, inert :class:`LLMResponse`; returning it is a
    pure lookup with no side effect.  A refusal is modelled as an ordinary response
    whose ``finish_reason`` is :data:`FINISH_CONTENT_FILTER` (still valid contract
    data), distinct from a configured hard error (:class:`FakeErrorFixture`).
    """

    fixture_id: str
    response: LLMResponse


@dataclass(frozen=True)
class FakeErrorFixture:
    """A configured, bounded synthetic failure keyed by a fixture id.

    Resolving it raises :class:`FakeModelError` with this ``code``/``message`` so a
    test can exercise the fail-closed error path deterministically.
    """

    fixture_id: str
    code: str
    message: str


# --- Fixture builders --------------------------------------------------------


def fake_response(
    fixture_id: str,
    *,
    text: str = "fake fixed response",
    provider: str = DEFAULT_FAKE_PROVIDER,
    model: str = DEFAULT_FAKE_MODEL,
    finish_reason: str = FINISH_STOP,
    prompt_tokens: int = 3,
    completion_tokens: int | None = None,
    metadata: Mapping[str, object] | None = None,
) -> FakeResponseFixture:
    """Build a :class:`FakeResponseFixture` from tiny synthetic inputs.

    The canned :class:`LLMResponse` is re-validated through the contract
    (:func:`ensure_valid_response`) so a malformed/forbidden fixture (e.g.
    credential-like metadata, oversized text, bad finish reason) fails closed at
    *build* time rather than at call time.  When ``completion_tokens`` is ``None``
    it defaults to a deterministic synthetic word-count proxy of ``text`` — a
    placeholder, never a real tokenizer or billing measurement.
    """
    fixture_id = _ensure_bounded_fixture_id(fixture_id)
    if completion_tokens is None:
        completion_tokens = len(text.split())
    response = ensure_valid_response(
        LLMResponse(
            provider=provider,
            model=model,
            message=LLMMessage(role=ROLE_ASSISTANT, content=text),
            finish_reason=finish_reason,
            usage=LLMUsage.from_counts(prompt_tokens, completion_tokens),
            metadata=metadata,
        )
    )
    return FakeResponseFixture(fixture_id=fixture_id, response=response)


def fake_error(
    fixture_id: str,
    *,
    code: str = CODE_FIXTURE_ERROR,
    message: str = "configured fake model error",
) -> FakeErrorFixture:
    """Build a :class:`FakeErrorFixture` (a configured synthetic failure)."""
    fixture_id = _ensure_bounded_fixture_id(fixture_id)
    if not isinstance(code, str) or not code:
        raise FakeModelError(CODE_MALFORMED_FIXTURE_REQUEST, "error fixture code must be a non-blank string")
    if not isinstance(message, str):
        raise FakeModelError(CODE_MALFORMED_FIXTURE_REQUEST, "error fixture message must be a string")
    return FakeErrorFixture(fixture_id=fixture_id, code=code, message=message)


# --- The offline fake model --------------------------------------------------


class FixtureFakeModel:
    """A deterministic, offline fake model resolving canned fixtures by id.

    Structurally compatible with the
    :class:`auto_bioinfo.agent_gateway.llm_provider.LLMProvider` protocol (it
    exposes ``provider_id`` and ``complete``), so it can stand in wherever the
    gateway depends on that seam — but it answers *only* from explicit in-memory
    fixtures and performs no network/SDK/credential/clock/file access whatsoever.

    Resolution: :meth:`complete` reads the synthetic fixture id from
    ``request.metadata[FIXTURE_ID_METADATA_KEY]`` (a malformed request or a missing
    id fails closed); :meth:`respond` looks a fixture up directly by id.  A response
    fixture returns its inert :class:`LLMResponse`; an error fixture and an unknown
    id raise a bounded :class:`FakeModelError`.
    """

    def __init__(
        self,
        *,
        provider_id: str = DEFAULT_FAKE_PROVIDER,
        fixtures: Iterable[FakeResponseFixture | FakeErrorFixture] = (),
    ) -> None:
        if not _is_bounded_token(provider_id, MAX_PROVIDER_ID_LENGTH):
            raise FakeModelError(
                CODE_MALFORMED_FIXTURE_REQUEST,
                "provider_id must be a non-blank, bounded, single-line printable-ASCII identifier",
            )
        self.provider_id = provider_id
        # Build the fixture index, failing closed on a duplicate id so an ambiguous
        # registry is rejected at construction rather than silently shadowing.
        self._fixtures: dict[str, FakeResponseFixture | FakeErrorFixture] = {}
        for fixture in fixtures:
            if not isinstance(fixture, (FakeResponseFixture, FakeErrorFixture)):
                raise FakeModelError(CODE_MALFORMED_FIXTURE_REQUEST, "each fixture must be a FakeResponseFixture or FakeErrorFixture")
            fixture_id = _ensure_bounded_fixture_id(fixture.fixture_id)
            if fixture_id in self._fixtures:
                raise FakeModelError(CODE_DUPLICATE_FIXTURE, f"fixture id {fixture_id!r} is registered more than once")
            self._fixtures[fixture_id] = fixture

    @property
    def fixture_ids(self) -> tuple[str, ...]:
        """The registered fixture ids, in stable sorted order (a deterministic view)."""
        return tuple(sorted(self._fixtures))

    def respond(self, fixture_id: str) -> LLMResponse:
        """Return the canned :class:`LLMResponse` for ``fixture_id`` (fail-closed).

        An unknown id raises :class:`FakeModelError` (:data:`CODE_UNKNOWN_FIXTURE`);
        a configured error fixture raises with its own bounded code/message.  A
        response fixture's value is re-validated before return so a registry can
        never leak a malformed response.
        """
        fixture_id = _ensure_bounded_fixture_id(fixture_id)
        fixture = self._fixtures.get(fixture_id)
        if fixture is None:
            raise FakeModelError(CODE_UNKNOWN_FIXTURE, f"no fixture registered for id {fixture_id!r}")
        if isinstance(fixture, FakeErrorFixture):
            raise FakeModelError(fixture.code, fixture.message)
        return ensure_valid_response(fixture.response)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the canned response for ``request`` (provider-protocol entry point).

        The request must be a valid :class:`LLMRequest` carrying a bounded synthetic
        fixture id at ``metadata[FIXTURE_ID_METADATA_KEY]``; otherwise the call fails
        closed with :data:`CODE_MALFORMED_FIXTURE_REQUEST`.  Resolution then defers
        to :meth:`respond`.
        """
        errors = validate_request(request)
        if errors:
            code, message = errors[0]
            raise FakeModelError(CODE_MALFORMED_FIXTURE_REQUEST, f"malformed request ({code}): {message}")
        metadata = request.metadata
        if not isinstance(metadata, Mapping) or FIXTURE_ID_METADATA_KEY not in metadata:
            raise FakeModelError(
                CODE_MALFORMED_FIXTURE_REQUEST,
                f"request metadata must carry a {FIXTURE_ID_METADATA_KEY!r} fixture id",
            )
        return self.respond(metadata[FIXTURE_ID_METADATA_KEY])


# --- Ergonomic helpers -------------------------------------------------------


def request_for(
    fixture_id: str,
    *,
    content: str = "prompt-ref:test",
    role: str = ROLE_USER,
    model: str = DEFAULT_FAKE_MODEL,
) -> LLMRequest:
    """Build a tiny valid :class:`LLMRequest` that selects ``fixture_id``.

    The fixture id rides in bounded scalar metadata (the same place
    :meth:`FixtureFakeModel.complete` reads it), and the message content is a
    synthetic placeholder reference (``prompt-ref:test``) — never a real prompt.
    """
    return LLMRequest(
        model=model,
        messages=(LLMMessage(role=role, content=content),),
        metadata={FIXTURE_ID_METADATA_KEY: fixture_id},
    )


def default_fake_model(*, provider_id: str = DEFAULT_FAKE_PROVIDER) -> FixtureFakeModel:
    """A :class:`FixtureFakeModel` preloaded with a tiny canonical fixture set.

    The built-in fixtures are deliberately minimal, synthetic placeholders covering
    the three shapes a model-facing test usually needs: a fixed success, a refusal
    (a ``content_filter`` response), and a configured hard error.  Unknown ids and
    malformed requests fail closed via the model's normal paths.
    """
    return FixtureFakeModel(
        provider_id=provider_id,
        fixtures=(
            fake_response("fake-summary-ok", text="fake fixed response", prompt_tokens=3, completion_tokens=3),
            fake_response(
                "fake-refusal",
                text="fake refusal: request declined by offline fake model",
                finish_reason=FINISH_CONTENT_FILTER,
                prompt_tokens=3,
                completion_tokens=8,
            ),
            fake_error("fake-error", code=CODE_FIXTURE_ERROR, message="configured fake model error"),
        ),
    )


__all__ = [
    "DEFAULT_FAKE_PROVIDER",
    "DEFAULT_FAKE_MODEL",
    "FIXTURE_ID_METADATA_KEY",
    "MAX_FIXTURE_ID_LENGTH",
    "CODE_UNKNOWN_FIXTURE",
    "CODE_MALFORMED_FIXTURE_REQUEST",
    "CODE_FIXTURE_ERROR",
    "CODE_DUPLICATE_FIXTURE",
    "FAKE_REASON_CODES",
    "FakeModelError",
    "FakeResponseFixture",
    "FakeErrorFixture",
    "fake_response",
    "fake_error",
    "FixtureFakeModel",
    "request_for",
    "default_fake_model",
]
