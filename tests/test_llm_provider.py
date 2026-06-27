"""Unit tests for the local LLM provider interface + fake provider (WP-05a / T-05-01).

Covers, for the provider-agnostic, offline, deterministic contract foundation:

- request / message / usage / response value shapes, their deterministic
  ``to_dict`` projections, and request fingerprint stability,
- fail-closed request validation (malformed model, empty / oversized / malformed
  messages, malformed role/content, malformed sampling fields, malformed stop,
  malformed / forbidden credential-like metadata),
- fail-closed usage validation (negative tokens, oversized tokens, inconsistent
  total) and response validation (non-assistant role, bad finish reason, bad
  provider id),
- the ``ensure_valid_*`` constructor guards raising a bounded ``LLMContractError``,
- the offline ``FakeLLMProvider``: deterministic echo, scripted fixtures, repeated
  determinism, fail-closed on malformed request / malformed fixtures, structural
  conformance to the ``LLMProvider`` protocol, and no content egress / side effects.
"""

import unittest

from auto_bioinfo.agent_gateway.llm_provider import (
    CODE_CONTENT_TOO_LONG,
    CODE_EMPTY_MESSAGES,
    CODE_FORBIDDEN_METADATA,
    CODE_MALFORMED_FINISH_REASON,
    CODE_MALFORMED_MAX_TOKENS,
    CODE_MALFORMED_METADATA,
    CODE_MALFORMED_MODEL,
    CODE_MALFORMED_PROVIDER,
    CODE_MALFORMED_ROLE,
    CODE_MALFORMED_STOP,
    CODE_MALFORMED_TEMPERATURE,
    CODE_NEGATIVE_TOKENS,
    CODE_TOKENS_TOO_LARGE,
    CODE_TOO_MANY_MESSAGES,
    CODE_USAGE_INCONSISTENT,
    FINISH_REASONS,
    FINISH_STOP,
    MAX_CONTENT_LENGTH,
    MAX_MESSAGES,
    MAX_TOKEN_COUNT,
    REASON_CODES,
    ROLE_ASSISTANT,
    ROLE_USER,
    FakeLLMProvider,
    LLMContractError,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ensure_valid_request,
    ensure_valid_response,
    validate_request,
    validate_response,
    validate_usage,
)


def _request(content: str = "hello", *, model: str = "fake-echo-1", role: str = ROLE_USER, **kwargs) -> LLMRequest:
    return LLMRequest(model=model, messages=(LLMMessage(role=role, content=content),), **kwargs)


def _response(content: str = "hi", **kwargs) -> LLMResponse:
    base = {
        "provider": "fake-local",
        "model": "fake-echo-1",
        "message": LLMMessage(role=ROLE_ASSISTANT, content=content),
        "finish_reason": FINISH_STOP,
        "usage": LLMUsage.from_counts(1, 1),
    }
    base.update(kwargs)
    return LLMResponse(**base)


class ValueShapeTest(unittest.TestCase):
    def test_message_to_dict_is_deterministic(self):
        message = LLMMessage(role=ROLE_USER, content="ask")
        self.assertEqual(message.to_dict(), {"role": ROLE_USER, "content": "ask"})

    def test_usage_from_counts_derives_consistent_total(self):
        usage = LLMUsage.from_counts(3, 4)
        self.assertEqual(usage.total_tokens, 7)
        self.assertEqual(usage.to_dict(), {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7})
        self.assertEqual(validate_usage(usage), [])

    def test_request_coerces_lists_to_tuples_and_is_hashable(self):
        request = LLMRequest(model="m", messages=[LLMMessage(role=ROLE_USER, content="x")], stop=["END"])
        self.assertIsInstance(request.messages, tuple)
        self.assertIsInstance(request.stop, tuple)
        # frozen + tuple fields => hashable
        self.assertIsInstance(hash(request), int)

    def test_request_fingerprint_is_stable_and_order_independent_on_metadata(self):
        a = _request("hello", metadata={"k1": "v1", "k2": 2})
        b = _request("hello", metadata={"k2": 2, "k1": "v1"})
        self.assertEqual(a.fingerprint(), b.fingerprint())
        self.assertNotEqual(_request("hello").fingerprint(), _request("world").fingerprint())

    def test_response_to_dict_round_trips_nested_values(self):
        response = _response("done")
        projected = response.to_dict()
        self.assertEqual(projected["message"], {"role": ROLE_ASSISTANT, "content": "done"})
        self.assertEqual(projected["usage"], {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        self.assertEqual(projected["finish_reason"], FINISH_STOP)


class RequestValidationTest(unittest.TestCase):
    def test_valid_request_has_no_errors(self):
        self.assertEqual(validate_request(_request("hello", temperature=0.5, max_output_tokens=128, stop=("END",))), [])

    def test_non_request_is_malformed(self):
        self.assertTrue(validate_request({"model": "m"}))

    def test_blank_model_fails_closed(self):
        codes = [c for c, _ in validate_request(_request("hi", model="   "))]
        self.assertIn(CODE_MALFORMED_MODEL, codes)

    def test_empty_messages_fail_closed(self):
        codes = [c for c, _ in validate_request(LLMRequest(model="m", messages=()))]
        self.assertIn(CODE_EMPTY_MESSAGES, codes)

    def test_too_many_messages_fail_closed(self):
        many = tuple(LLMMessage(role=ROLE_USER, content="x") for _ in range(MAX_MESSAGES + 1))
        codes = [c for c, _ in validate_request(LLMRequest(model="m", messages=many))]
        self.assertIn(CODE_TOO_MANY_MESSAGES, codes)

    def test_bad_role_and_oversized_content_fail_closed(self):
        bad_role = [c for c, _ in validate_request(_request("hi", role="root"))]
        self.assertIn(CODE_MALFORMED_ROLE, bad_role)
        oversized = [c for c, _ in validate_request(_request("x" * (MAX_CONTENT_LENGTH + 1)))]
        self.assertIn(CODE_CONTENT_TOO_LONG, oversized)

    def test_bad_sampling_fields_fail_closed(self):
        self.assertIn(CODE_MALFORMED_TEMPERATURE, [c for c, _ in validate_request(_request("hi", temperature=5.0))])
        self.assertIn(CODE_MALFORMED_TEMPERATURE, [c for c, _ in validate_request(_request("hi", temperature=True))])
        self.assertIn(CODE_MALFORMED_MAX_TOKENS, [c for c, _ in validate_request(_request("hi", max_output_tokens=0))])
        self.assertIn(CODE_MALFORMED_MAX_TOKENS, [c for c, _ in validate_request(_request("hi", max_output_tokens=True))])

    def test_bad_stop_sequences_fail_closed(self):
        self.assertIn(CODE_MALFORMED_STOP, [c for c, _ in validate_request(_request("hi", stop=("",)))])
        self.assertIn(CODE_MALFORMED_STOP, [c for c, _ in validate_request(_request("hi", stop=tuple("s" for _ in range(9))))])

    def test_forbidden_credential_metadata_fails_closed(self):
        for key in ("api_key", "Authorization", "x_secret", "access_token"):
            codes = [c for c, _ in validate_request(_request("hi", metadata={key: "v"}))]
            self.assertIn(CODE_FORBIDDEN_METADATA, codes, key)

    def test_malformed_metadata_value_fails_closed(self):
        codes = [c for c, _ in validate_request(_request("hi", metadata={"nested": {"a": 1}}))]
        self.assertIn(CODE_MALFORMED_METADATA, codes)

    def test_scalar_metadata_is_accepted(self):
        self.assertEqual(validate_request(_request("hi", metadata={"trace": "abc", "n": 3, "f": 1.5, "ok": True})), [])


class UsageAndResponseValidationTest(unittest.TestCase):
    def test_negative_and_oversized_tokens_fail_closed(self):
        self.assertIn(CODE_NEGATIVE_TOKENS, [c for c, _ in validate_usage(LLMUsage(-1, 0, -1))])
        self.assertIn(CODE_TOKENS_TOO_LARGE, [c for c, _ in validate_usage(LLMUsage(MAX_TOKEN_COUNT + 1, 0, MAX_TOKEN_COUNT + 1))])

    def test_inconsistent_total_fails_closed(self):
        codes = [c for c, _ in validate_usage(LLMUsage(prompt_tokens=2, completion_tokens=2, total_tokens=99))]
        self.assertIn(CODE_USAGE_INCONSISTENT, codes)

    def test_valid_response_has_no_errors(self):
        self.assertEqual(validate_response(_response("ok")), [])

    def test_non_assistant_role_fails_closed(self):
        bad = _response("x", message=LLMMessage(role=ROLE_USER, content="x"))
        self.assertIn(CODE_MALFORMED_ROLE, [c for c, _ in validate_response(bad)])

    def test_bad_finish_reason_fails_closed(self):
        bad = _response("x", finish_reason="exploded")
        self.assertIn(CODE_MALFORMED_FINISH_REASON, [c for c, _ in validate_response(bad)])

    def test_blank_provider_fails_closed(self):
        bad = _response("x", provider="  ")
        self.assertIn(CODE_MALFORMED_PROVIDER, [c for c, _ in validate_response(bad)])

    def test_forged_total_in_response_usage_fails_closed(self):
        bad = _response("x", usage=LLMUsage(prompt_tokens=1, completion_tokens=1, total_tokens=50))
        self.assertIn(CODE_USAGE_INCONSISTENT, [c for c, _ in validate_response(bad)])


class EnsureGuardTest(unittest.TestCase):
    def test_ensure_valid_request_raises_bounded_error(self):
        with self.assertRaises(LLMContractError) as ctx:
            ensure_valid_request(_request("hi", role="root"))
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_ROLE)
        self.assertIn(ctx.exception.code, REASON_CODES)

    def test_ensure_valid_request_returns_value_on_success(self):
        request = _request("hello")
        self.assertIs(ensure_valid_request(request), request)

    def test_ensure_valid_response_raises_bounded_error(self):
        with self.assertRaises(LLMContractError) as ctx:
            ensure_valid_response(_response("x", finish_reason="nope"))
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_FINISH_REASON)


class FakeProviderTest(unittest.TestCase):
    def test_provider_conforms_to_protocol(self):
        self.assertIsInstance(FakeLLMProvider(), LLMProvider)

    def test_echo_is_deterministic_and_valid(self):
        provider = FakeLLMProvider()
        request = _request("what is up")
        first = provider.complete(request)
        second = provider.complete(request)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(validate_response(first), [])
        self.assertEqual(first.finish_reason, FINISH_STOP)
        self.assertEqual(first.message.role, ROLE_ASSISTANT)
        self.assertIn("what is up", first.message.content)
        self.assertEqual(first.model, request.model)
        self.assertIn(first.finish_reason, FINISH_REASONS)

    def test_echo_usage_counts_are_nonnegative_and_consistent(self):
        provider = FakeLLMProvider()
        response = provider.complete(_request("alpha beta gamma"))
        self.assertGreaterEqual(response.usage.prompt_tokens, 0)
        self.assertGreaterEqual(response.usage.completion_tokens, 0)
        self.assertEqual(response.usage.total_tokens, response.usage.prompt_tokens + response.usage.completion_tokens)

    def test_scripted_fixture_is_returned_verbatim(self):
        request = _request("scripted question")
        canned = _response("a fixed scripted answer")
        provider = FakeLLMProvider(scripted=[(request, canned)])
        self.assertIs(provider.complete(request), canned)
        # A different (unscripted) request falls back to the deterministic echo.
        other = provider.complete(_request("different"))
        self.assertIn("different", other.message.content)

    def test_complete_fails_closed_on_malformed_request(self):
        provider = FakeLLMProvider()
        with self.assertRaises(LLMContractError):
            provider.complete(_request("hi", role="root"))

    def test_constructor_rejects_malformed_provider_id(self):
        with self.assertRaises(LLMContractError) as ctx:
            FakeLLMProvider(provider_id="  ")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PROVIDER)

    def test_constructor_rejects_malformed_scripted_response(self):
        request = _request("q")
        bad = _response("x", finish_reason="boom")
        with self.assertRaises(LLMContractError):
            FakeLLMProvider(scripted=[(request, bad)])

    def test_complete_has_no_side_effects_on_inputs(self):
        provider = FakeLLMProvider()
        request = _request("immutable")
        before = request.to_dict()
        provider.complete(request)
        self.assertEqual(request.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
