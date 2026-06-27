"""Offline tests for the fake-model fixtures (WP-05j / T-05-10).

Covers, for the test-only :mod:`tests.fakes` foundation:

- deterministic fixed-response lookup across repeated calls (by id and via the
  provider-protocol ``complete`` entry point),
- deterministic, synthetic usage/counter metadata,
- fail-closed handling of an unknown fixture id, a malformed request, a missing
  fixture id, a duplicate registration, and a configured error fixture — each with
  a bounded reason code,
- structural conformance to the ``LLMProvider`` protocol,
- that no real external model/provider/network/socket/env/credential access is
  attempted (a fixture resolution still works with sockets disabled), and
- that only tiny synthetic content is exposed (no real prompt/user content, model
  output, secret, or credential-like metadata can be smuggled into a fixture).
"""

import socket
import unittest
from unittest import mock

from auto_bioinfo.agent_gateway.llm_provider import (
    FINISH_CONTENT_FILTER,
    FINISH_STOP,
    ROLE_ASSISTANT,
    LLMContractError,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMUsage,
)
from tests.fakes import (
    CODE_DUPLICATE_FIXTURE,
    CODE_FIXTURE_ERROR,
    CODE_MALFORMED_FIXTURE_REQUEST,
    CODE_UNKNOWN_FIXTURE,
    DEFAULT_FAKE_MODEL,
    FAKE_REASON_CODES,
    FIXTURE_ID_METADATA_KEY,
    FakeErrorFixture,
    FakeModelError,
    FixtureFakeModel,
    default_fake_model,
    fake_error,
    fake_response,
    request_for,
)


class FixtureBuildTest(unittest.TestCase):
    def test_response_fixture_carries_validated_synthetic_response(self):
        fixture = fake_response("fake-summary-ok", text="fake fixed response", prompt_tokens=3, completion_tokens=3)
        self.assertEqual(fixture.fixture_id, "fake-summary-ok")
        self.assertEqual(fixture.response.message.role, ROLE_ASSISTANT)
        self.assertEqual(fixture.response.message.content, "fake fixed response")
        self.assertEqual(fixture.response.model, DEFAULT_FAKE_MODEL)
        self.assertEqual(fixture.response.finish_reason, FINISH_STOP)

    def test_completion_tokens_default_is_deterministic_word_count_proxy(self):
        fixture = fake_response("fake-words", text="one two three four")
        self.assertEqual(fixture.response.usage, LLMUsage.from_counts(3, 4))

    def test_blank_fixture_id_fails_closed(self):
        with self.assertRaises(FakeModelError) as ctx:
            fake_response("   ", text="x")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_FIXTURE_REQUEST)

    def test_credential_like_metadata_fixture_fails_closed_at_build(self):
        # The contract forbids credential-like metadata, so a fixture can never be
        # built to smuggle a secret out of a fake response.
        with self.assertRaises(LLMContractError):
            fake_response("fake-leak", text="x", metadata={"api_key": "nope"})

    def test_oversized_or_bad_finish_reason_fixture_fails_closed_at_build(self):
        with self.assertRaises(LLMContractError):
            fake_response("fake-bad-finish", text="x", finish_reason="exploded")


class DeterministicLookupTest(unittest.TestCase):
    def setUp(self):
        self.model = default_fake_model()

    def test_fixture_lookup_is_deterministic_across_repeated_calls(self):
        first = self.model.respond("fake-summary-ok")
        second = self.model.respond("fake-summary-ok")
        self.assertEqual(first, second)
        self.assertEqual(first.message.content, "fake fixed response")

    def test_complete_resolves_fixture_from_request_metadata(self):
        request = request_for("fake-summary-ok")
        first = self.model.complete(request)
        second = self.model.complete(request)
        self.assertEqual(first, second)
        self.assertEqual(first.message.content, "fake fixed response")

    def test_usage_counters_are_deterministic_and_synthetic(self):
        usage = self.model.respond("fake-summary-ok").usage
        self.assertEqual(usage, LLMUsage.from_counts(3, 3))
        # Stable across calls (no clock/random/tokenizer involvement).
        self.assertEqual(self.model.respond("fake-summary-ok").usage, usage)

    def test_refusal_fixture_is_a_content_filter_response(self):
        response = self.model.respond("fake-refusal")
        self.assertEqual(response.finish_reason, FINISH_CONTENT_FILTER)
        self.assertEqual(response.message.role, ROLE_ASSISTANT)
        self.assertIn("refusal", response.message.content)

    def test_fixture_ids_view_is_sorted_and_stable(self):
        self.assertEqual(self.model.fixture_ids, ("fake-error", "fake-refusal", "fake-summary-ok"))


class FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.model = default_fake_model()

    def test_unknown_fixture_id_fails_closed(self):
        with self.assertRaises(FakeModelError) as ctx:
            self.model.respond("does-not-exist")
        self.assertEqual(ctx.exception.code, CODE_UNKNOWN_FIXTURE)

    def test_configured_error_fixture_raises_bounded_error(self):
        with self.assertRaises(FakeModelError) as ctx:
            self.model.respond("fake-error")
        self.assertEqual(ctx.exception.code, CODE_FIXTURE_ERROR)
        self.assertEqual(ctx.exception.message, "configured fake model error")

    def test_malformed_request_fails_closed(self):
        # Empty messages => contract-malformed request, surfaced as a bounded fake code.
        bad = LLMRequest(model="m", messages=(), metadata={FIXTURE_ID_METADATA_KEY: "fake-summary-ok"})
        with self.assertRaises(FakeModelError) as ctx:
            self.model.complete(bad)
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_FIXTURE_REQUEST)

    def test_missing_fixture_id_in_metadata_fails_closed(self):
        no_id = LLMRequest(model="m", messages=(LLMMessage(role="user", content="hi"),))
        with self.assertRaises(FakeModelError) as ctx:
            self.model.complete(no_id)
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_FIXTURE_REQUEST)

    def test_duplicate_fixture_id_fails_closed_at_construction(self):
        with self.assertRaises(FakeModelError) as ctx:
            FixtureFakeModel(fixtures=(fake_response("dup", text="a"), fake_response("dup", text="b")))
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_FIXTURE)

    def test_all_raised_codes_are_in_the_stable_reason_set(self):
        for fixture_id, expected in (("does-not-exist", CODE_UNKNOWN_FIXTURE), ("fake-error", CODE_FIXTURE_ERROR)):
            with self.assertRaises(FakeModelError) as ctx:
                self.model.respond(fixture_id)
            self.assertIn(ctx.exception.code, FAKE_REASON_CODES)
            self.assertEqual(ctx.exception.code, expected)


class IsolationAndContractTest(unittest.TestCase):
    def test_fixture_model_conforms_to_provider_protocol(self):
        model = default_fake_model()
        self.assertIsInstance(model, LLMProvider)
        self.assertEqual(model.provider_id, "fake-local")

    def test_resolution_opens_no_socket(self):
        # Disable socket creation entirely; a fixture resolution must still succeed,
        # proving the fake model touches no network/provider transport.
        model = default_fake_model()
        with mock.patch.object(socket, "socket", side_effect=AssertionError("no socket allowed")):
            response = model.complete(request_for("fake-summary-ok"))
        self.assertEqual(response.message.content, "fake fixed response")

    def test_request_helper_carries_only_synthetic_placeholder_content(self):
        request = request_for("fake-summary-ok")
        self.assertEqual(request.messages[0].content, "prompt-ref:test")
        self.assertEqual(request.metadata, {FIXTURE_ID_METADATA_KEY: "fake-summary-ok"})

    def test_error_fixture_builder_rejects_blank_code(self):
        with self.assertRaises(FakeModelError) as ctx:
            fake_error("fake-x", code="")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_FIXTURE_REQUEST)


class BoundedReasonCodeTest(unittest.TestCase):
    """A configured error fixture can never carry a code outside the stable set.

    The bounded reason-code contract (turn 0255) requires every raised
    ``FakeModelError.code`` to come from :data:`FAKE_REASON_CODES`.  These tests
    pin the two ways a non-stable code could otherwise be introduced — the
    :func:`fake_error` builder and a direct :class:`FakeErrorFixture` registration
    — to fail closed, and assert the resulting invariant on resolution.
    """

    def test_fake_error_builder_rejects_non_stable_code_fail_closed(self):
        with self.assertRaises(FakeModelError) as ctx:
            fake_error("fake-x", code="UNBOUNDED_ARBITRARY_CODE", message="x")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_FIXTURE_REQUEST)

    def test_direct_error_fixture_with_non_stable_code_cannot_be_registered(self):
        # A caller bypassing the builder still cannot register a non-stable code:
        # construction of the fixture object is allowed (it is inert data), but the
        # model rejects it fail-closed at registration so respond() can never reach
        # it and raise UNBOUNDED_ARBITRARY_CODE.
        bad = FakeErrorFixture(fixture_id="fake-x", code="UNBOUNDED_ARBITRARY_CODE", message="x")
        with self.assertRaises(FakeModelError) as ctx:
            FixtureFakeModel(fixtures=(bad,))
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_FIXTURE_REQUEST)

    def test_every_stable_code_is_accepted_by_the_error_builder(self):
        for code in FAKE_REASON_CODES:
            fixture = fake_error("fake-ok", code=code, message="x")
            self.assertEqual(fixture.code, code)

    def test_all_raised_codes_from_public_error_paths_are_stable(self):
        # Build a model whose only error fixtures are every stable code, plus the
        # unknown-id path, and assert each raised code stays inside the stable set.
        model = FixtureFakeModel(fixtures=tuple(fake_error(f"err-{i}", code=code, message="x") for i, code in enumerate(FAKE_REASON_CODES)))
        for fixture_id in model.fixture_ids:
            with self.assertRaises(FakeModelError) as ctx:
                model.respond(fixture_id)
            self.assertIn(ctx.exception.code, FAKE_REASON_CODES)
        with self.assertRaises(FakeModelError) as ctx:
            model.respond("no-such-id")
        self.assertIn(ctx.exception.code, FAKE_REASON_CODES)


if __name__ == "__main__":
    unittest.main()
