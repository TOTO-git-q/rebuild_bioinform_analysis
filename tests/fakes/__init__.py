"""Offline, deterministic fake-model fixtures for tests (WP-05j / T-05-10).

This test-only package provides the smallest reusable *fake model* foundation so
tests can exercise model-facing contracts **without an external model, provider
SDK, network, credential, or any side effect**.  It builds purely on the local,
provider-agnostic contract in :mod:`auto_bioinfo.agent_gateway.llm_provider`
(WP-05a / T-05-01): a fixture is just a pre-validated, inert :class:`LLMResponse`
(or a bounded, reason-coded error) keyed by a stable synthetic ``fixture_id``.

Nothing here reads the network, a socket, an SDK, an environment variable, a
credential, the real clock, randomness, the filesystem, or any persistent store;
every fixture is a total function of explicit in-memory inputs.  Token "usage"
counters are deterministic synthetic placeholders, never a real tokenizer or
billing measurement.

See :mod:`tests.fakes.fake_model` for the public surface.
"""

from tests.fakes.fake_model import (
    CODE_DUPLICATE_FIXTURE,
    CODE_FIXTURE_ERROR,
    CODE_MALFORMED_FIXTURE_REQUEST,
    CODE_UNKNOWN_FIXTURE,
    DEFAULT_FAKE_MODEL,
    DEFAULT_FAKE_PROVIDER,
    FAKE_REASON_CODES,
    FIXTURE_ID_METADATA_KEY,
    FakeErrorFixture,
    FakeModelError,
    FakeResponseFixture,
    FixtureFakeModel,
    default_fake_model,
    fake_error,
    fake_response,
    request_for,
)

__all__ = [
    "CODE_DUPLICATE_FIXTURE",
    "CODE_FIXTURE_ERROR",
    "CODE_MALFORMED_FIXTURE_REQUEST",
    "CODE_UNKNOWN_FIXTURE",
    "DEFAULT_FAKE_MODEL",
    "DEFAULT_FAKE_PROVIDER",
    "FAKE_REASON_CODES",
    "FIXTURE_ID_METADATA_KEY",
    "FakeErrorFixture",
    "FakeModelError",
    "FakeResponseFixture",
    "FixtureFakeModel",
    "default_fake_model",
    "fake_error",
    "fake_response",
    "request_for",
]
