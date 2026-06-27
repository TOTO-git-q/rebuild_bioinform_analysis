"""Unit tests for the local structured-output admission contract (WP-05c / T-05-03).

Covers, for the offline, deterministic admission-contract foundation:

- strict, fail-closed parsing of provider response text into a structured object
  (empty / oversized / malformed JSON / multiple payloads / non-finite / non-object),
- the bounded local JSON-schema-subset validator and the offline ``SchemaRegistry``
  (definition validation, fail-closed unknown / drifted / duplicate, no fallback),
- ``admit_structured_output`` end to end: a valid response accepted under the exact
  registered target schema; malformed JSON, schema violations, unknown / mismatched
  schema, unregistered prompt / version, and template-hash mismatch all rejected,
- bounded local repair retry succeeding only within the attempt bound and failing
  closed on exhaustion, with no fallback to another prompt / schema / version,
- deterministic serialization / reason-code behaviour, and
- the admission writing no project-state / event / artifact / business side effects.

All fixtures are tiny synthetic public data — no real human-derived data, secrets,
credentials, API keys, private prompts, or real model outputs.  The whole module is
offline and deterministic: no network, provider SDK, or content egress.
"""

import json
import os
import unittest

from auto_bioinfo.agent_gateway.llm_provider import (
    FINISH_STOP,
    ROLE_ASSISTANT,
    ROLE_USER,
    FakeLLMProvider,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from auto_bioinfo.agent_gateway.prompt_registry import (
    CODE_HASH_MISMATCH,
    CODE_UNKNOWN_PROMPT,
    CODE_UNKNOWN_VERSION,
    PromptRegistry,
    RegisteredPrompt,
)
from auto_bioinfo.agent_gateway.structured_output import (
    CODE_DUPLICATE_SCHEMA,
    CODE_EMPTY_PAYLOAD,
    CODE_MALFORMED_JSON,
    CODE_MALFORMED_MAX_ATTEMPTS,
    CODE_MALFORMED_RESPONSE,
    CODE_MALFORMED_SCHEMA,
    CODE_MALFORMED_SCHEMA_ID,
    CODE_MULTIPLE_PAYLOADS,
    CODE_NO_CANDIDATES,
    CODE_NON_FINITE_NUMBER,
    CODE_PAYLOAD_TOO_LARGE,
    CODE_REPAIR_EXHAUSTED,
    CODE_SCHEMA_DRIFT,
    CODE_SCHEMA_MISMATCH,
    CODE_SCHEMA_VIOLATION,
    CODE_UNKNOWN_SCHEMA,
    CODE_UNSUPPORTED_SHAPE,
    MAX_OUTPUT_TEXT_LENGTH,
    REASON_CODES,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    AdmissionDecision,
    SchemaRegistry,
    StructuredOutputError,
    admit_structured_output,
    is_repairable,
    parse_structured_output,
    validate_instance,
    validate_schema_definition,
)

# --- Tiny synthetic public fixtures ------------------------------------------

_TARGET_SCHEMA_ID = "report.summary/v1"

_REPORT_SCHEMA = {
    "title": "ReportSummary",
    "type": "object",
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "score"],
    "additionalProperties": False,
}

# A different schema bound to a different id; used to prove no silent fallback.
_OTHER_SCHEMA_ID = "report.other/v1"
_OTHER_SCHEMA = {
    "title": "Other",
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


def _prompt(
    *,
    prompt_id: str = "report.summary",
    version: str = "1.0.0",
    template: str = "Summarize {{run}} as JSON.",
    target_schema: str = _TARGET_SCHEMA_ID,
) -> RegisteredPrompt:
    return RegisteredPrompt(prompt_id=prompt_id, version=version, template=template, target_schema=target_schema)


def _prompt_registry() -> PromptRegistry:
    registry = PromptRegistry()
    registry.register(_prompt())
    registry.register(_prompt(prompt_id="report.other", target_schema=_OTHER_SCHEMA_ID))
    return registry


def _schema_registry() -> SchemaRegistry:
    return SchemaRegistry({_TARGET_SCHEMA_ID: _REPORT_SCHEMA, _OTHER_SCHEMA_ID: _OTHER_SCHEMA})


def _response(content: str, *, role: str = ROLE_ASSISTANT, provider: str = "fake-local", model: str = "fake-echo-1") -> LLMResponse:
    return LLMResponse(
        provider=provider,
        model=model,
        message=LLMMessage(role=role, content=content),
        finish_reason=FINISH_STOP,
        usage=LLMUsage.from_counts(3, 4),
    )


def _valid_payload(**overrides) -> str:
    payload = {"title": "Run 42", "score": 87, "tags": ["rna", "deg"]}
    payload.update(overrides)
    return json.dumps(payload)


def _admit(candidates, **kwargs):
    base = {
        "prompt_registry": _prompt_registry(),
        "prompt_id": "report.summary",
        "version": "1.0.0",
        "schema_registry": _schema_registry(),
        "candidates": candidates,
    }
    base.update(kwargs)
    return admit_structured_output(**base)


# --- Parsing -----------------------------------------------------------------


class ParseStructuredOutputTest(unittest.TestCase):
    def test_valid_object_parses(self):
        self.assertEqual(parse_structured_output('{"a": 1}'), {"a": 1})

    def test_surrounding_whitespace_is_tolerated(self):
        self.assertEqual(parse_structured_output('  \n {"a": 1}\n '), {"a": 1})

    def test_empty_or_whitespace_rejected(self):
        for text in ("", "   ", "\n\t"):
            with self.assertRaises(StructuredOutputError) as ctx:
                parse_structured_output(text)
            self.assertEqual(ctx.exception.code, CODE_EMPTY_PAYLOAD)

    def test_non_string_rejected(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            parse_structured_output({"a": 1})
        self.assertEqual(ctx.exception.code, CODE_EMPTY_PAYLOAD)

    def test_malformed_json_rejected(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            parse_structured_output('{"a": ')
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_JSON)

    def test_multiple_payloads_rejected(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            parse_structured_output('{"a": 1}{"b": 2}')
        self.assertEqual(ctx.exception.code, CODE_MULTIPLE_PAYLOADS)

    def test_non_finite_constant_rejected(self):
        for text in ('{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}'):
            with self.assertRaises(StructuredOutputError) as ctx:
                parse_structured_output(text)
            self.assertEqual(ctx.exception.code, CODE_NON_FINITE_NUMBER)

    def test_overflowing_number_literal_rejected(self):
        # 1e400 parses to float('inf') without going through parse_constant.
        with self.assertRaises(StructuredOutputError) as ctx:
            parse_structured_output('{"a": 1e400}')
        self.assertEqual(ctx.exception.code, CODE_NON_FINITE_NUMBER)

    def test_non_object_top_level_rejected(self):
        for text in ("[1, 2, 3]", '"hello"', "42", "true", "null"):
            with self.assertRaises(StructuredOutputError) as ctx:
                parse_structured_output(text)
            self.assertEqual(ctx.exception.code, CODE_UNSUPPORTED_SHAPE)

    def test_oversized_payload_rejected(self):
        oversized = "{" + " " * (MAX_OUTPUT_TEXT_LENGTH + 1) + "}"
        with self.assertRaises(StructuredOutputError) as ctx:
            parse_structured_output(oversized)
        self.assertEqual(ctx.exception.code, CODE_PAYLOAD_TOO_LARGE)


# --- Schema definition + registry --------------------------------------------


class SchemaDefinitionTest(unittest.TestCase):
    def test_valid_schema_definition_has_no_problems(self):
        self.assertEqual(validate_schema_definition(_REPORT_SCHEMA), [])

    def test_unknown_keyword_rejected(self):
        problems = validate_schema_definition({"type": "object", "patternProperties": {}})
        self.assertTrue(any("unsupported keyword" in p for p in problems))

    def test_unknown_type_rejected(self):
        problems = validate_schema_definition({"type": "tuple"})
        self.assertTrue(any("type" in p for p in problems))

    def test_missing_type_rejected(self):
        problems = validate_schema_definition({"properties": {}})
        self.assertTrue(any("must declare a 'type'" in p for p in problems))


class SchemaRegistryTest(unittest.TestCase):
    def test_register_and_resolve_roundtrips(self):
        registry = SchemaRegistry()
        registry.register(_TARGET_SCHEMA_ID, _REPORT_SCHEMA)
        self.assertIn(_TARGET_SCHEMA_ID, registry)
        self.assertEqual(registry.resolve(_TARGET_SCHEMA_ID)["title"], "ReportSummary")

    def test_unknown_schema_fails_closed(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            SchemaRegistry().resolve("nope/v1")
        self.assertEqual(ctx.exception.code, CODE_UNKNOWN_SCHEMA)

    def test_malformed_schema_id_rejected(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            SchemaRegistry().register("  ", _REPORT_SCHEMA)
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_SCHEMA_ID)

    def test_malformed_schema_definition_rejected(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            SchemaRegistry().register("bad/v1", {"type": "wat"})
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_SCHEMA)

    def test_duplicate_schema_rejected(self):
        registry = SchemaRegistry({_TARGET_SCHEMA_ID: _REPORT_SCHEMA})
        with self.assertRaises(StructuredOutputError) as ctx:
            registry.register(_TARGET_SCHEMA_ID, _REPORT_SCHEMA)
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_SCHEMA)

    def test_drifted_expected_hash_rejected(self):
        registry = SchemaRegistry({_TARGET_SCHEMA_ID: _REPORT_SCHEMA})
        with self.assertRaises(StructuredOutputError) as ctx:
            registry.resolve(_TARGET_SCHEMA_ID, expected_hash="deadbeef")
        self.assertEqual(ctx.exception.code, CODE_SCHEMA_DRIFT)

    def test_matching_expected_hash_resolves(self):
        registry = SchemaRegistry({_TARGET_SCHEMA_ID: _REPORT_SCHEMA})
        good = registry.schema_hash(_TARGET_SCHEMA_ID)
        self.assertEqual(registry.resolve(_TARGET_SCHEMA_ID, expected_hash=good)["title"], "ReportSummary")

    def test_registered_schema_is_isolated_from_caller_mutation(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        registry = SchemaRegistry()
        registry.register("iso/v1", schema)
        schema["properties"]["b"] = {"type": "string"}  # mutate caller copy after register
        self.assertNotIn("b", registry.resolve("iso/v1")["properties"])


# --- Instance validation -----------------------------------------------------


class ValidateInstanceTest(unittest.TestCase):
    def test_valid_instance_has_no_problems(self):
        self.assertEqual(validate_instance({"title": "x", "score": 5}, _REPORT_SCHEMA), [])

    def test_missing_required_property_rejected(self):
        problems = validate_instance({"title": "x"}, _REPORT_SCHEMA)
        self.assertTrue(any("missing required property" in p for p in problems))

    def test_wrong_type_rejected(self):
        problems = validate_instance({"title": "x", "score": "high"}, _REPORT_SCHEMA)
        self.assertTrue(any("expected type" in p for p in problems))

    def test_additional_property_rejected_when_forbidden(self):
        problems = validate_instance({"title": "x", "score": 5, "extra": 1}, _REPORT_SCHEMA)
        self.assertTrue(any("additional properties" in p for p in problems))

    def test_numeric_bounds_enforced(self):
        self.assertTrue(validate_instance({"title": "x", "score": 101}, _REPORT_SCHEMA))
        self.assertTrue(validate_instance({"title": "x", "score": -1}, _REPORT_SCHEMA))

    def test_bool_is_not_an_integer(self):
        problems = validate_instance({"title": "x", "score": True}, _REPORT_SCHEMA)
        self.assertTrue(any("expected type" in p for p in problems))

    def test_array_item_schema_enforced(self):
        problems = validate_instance({"title": "x", "score": 5, "tags": ["ok", 7]}, _REPORT_SCHEMA)
        self.assertTrue(any("expected type" in p for p in problems))


# --- Admission end to end ----------------------------------------------------


class AdmissionAcceptTest(unittest.TestCase):
    def test_valid_response_accepted_under_exact_target_schema(self):
        decision = _admit([_response(_valid_payload())])
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertTrue(decision.accepted)
        self.assertIsNone(decision.reason_code)
        self.assertEqual(decision.accepted_object, {"title": "Run 42", "score": 87, "tags": ["rna", "deg"]})
        self.assertEqual(decision.schema_id, _TARGET_SCHEMA_ID)
        self.assertEqual(decision.target_schema, _TARGET_SCHEMA_ID)
        self.assertEqual(decision.prompt_id, "report.summary")
        self.assertEqual(decision.version, "1.0.0")
        self.assertEqual(len(decision.attempts), 1)
        self.assertTrue(decision.attempts[0].accepted)

    def test_accept_works_with_fake_provider_synthetic_fixture(self):
        # The repair contract is exercised purely from an inert FakeLLMProvider
        # response — no real provider, network, or credential.
        provider = FakeLLMProvider(
            scripted=[
                (
                    LLMRequest(model="fake-echo-1", messages=(LLMMessage(role=ROLE_USER, content="give json"),)),
                    _response(_valid_payload()),
                )
            ]
        )
        request = LLMRequest(model="fake-echo-1", messages=(LLMMessage(role=ROLE_USER, content="give json"),))
        candidate = provider.complete(request)
        decision = _admit([candidate])
        self.assertEqual(decision.status, STATUS_ACCEPTED)


class AdmissionRejectTest(unittest.TestCase):
    def test_malformed_json_rejected(self):
        decision = _admit([_response('{"title": "x", ')])
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_REPAIR_EXHAUSTED)
        self.assertEqual(decision.attempts[0].reason_code, CODE_MALFORMED_JSON)
        self.assertIsNone(decision.accepted_object)

    def test_schema_violation_rejected(self):
        decision = _admit([_response(json.dumps({"title": "x", "score": 999}))])
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.attempts[0].reason_code, CODE_SCHEMA_VIOLATION)

    def test_missing_required_field_rejected(self):
        decision = _admit([_response(json.dumps({"title": "x"}))])
        self.assertEqual(decision.attempts[0].reason_code, CODE_SCHEMA_VIOLATION)
        self.assertEqual(decision.status, STATUS_REJECTED)

    def test_malformed_response_object_rejected_and_stops(self):
        decision = _admit([_response(_valid_payload(), role=ROLE_USER)])  # wrong role => invalid response
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_RESPONSE)
        self.assertEqual(decision.attempts[0].reason_code, CODE_MALFORMED_RESPONSE)

    def test_unknown_prompt_rejected(self):
        decision = _admit([_response(_valid_payload())], prompt_id="does.not.exist")
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_PROMPT)
        self.assertEqual(decision.status, STATUS_REJECTED)

    def test_unknown_version_rejected(self):
        decision = _admit([_response(_valid_payload())], version="9.9.9")
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_VERSION)

    def test_template_hash_mismatch_rejected(self):
        decision = _admit([_response(_valid_payload())], expected_template_hash="deadbeef")
        self.assertEqual(decision.reason_code, CODE_HASH_MISMATCH)

    def test_unknown_schema_rejected(self):
        # A prompt whose target schema is not registered fails closed (no fallback).
        registry = PromptRegistry()
        registry.register(_prompt(prompt_id="report.ghost", target_schema="report.ghost/v1"))
        decision = admit_structured_output(
            prompt_registry=registry,
            prompt_id="report.ghost",
            version="1.0.0",
            schema_registry=_schema_registry(),
            candidates=[_response(_valid_payload())],
        )
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_SCHEMA)
        self.assertEqual(decision.schema_id, "report.ghost/v1")

    def test_schema_id_mismatch_rejected_no_fallback(self):
        decision = _admit([_response(_valid_payload())], expected_schema_id=_OTHER_SCHEMA_ID)
        self.assertEqual(decision.reason_code, CODE_SCHEMA_MISMATCH)

    def test_schema_drift_rejected(self):
        decision = _admit([_response(_valid_payload())], expected_schema_hash="deadbeef")
        self.assertEqual(decision.reason_code, CODE_SCHEMA_DRIFT)

    def test_object_valid_under_other_schema_is_still_rejected(self):
        # {"name": ...} validates under _OTHER_SCHEMA but not the bound target schema;
        # admission must hold it to the prompt's target schema only (no fallback).
        decision = _admit([_response(json.dumps({"name": "only-name"}))])
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.attempts[0].reason_code, CODE_SCHEMA_VIOLATION)

    def test_no_candidates_rejected(self):
        decision = _admit([])
        self.assertEqual(decision.reason_code, CODE_NO_CANDIDATES)


class AdmissionRepairRetryTest(unittest.TestCase):
    def test_repair_succeeds_within_bound(self):
        candidates = [_response('{"title": "x"'), _response(json.dumps({"title": "x", "score": 200})), _response(_valid_payload())]
        decision = _admit(candidates, max_attempts=3)
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertEqual(len(decision.attempts), 3)
        self.assertEqual(decision.attempts[0].reason_code, CODE_MALFORMED_JSON)
        self.assertEqual(decision.attempts[1].reason_code, CODE_SCHEMA_VIOLATION)
        self.assertTrue(decision.attempts[2].accepted)

    def test_good_candidate_beyond_bound_is_never_reached(self):
        candidates = [_response('{"bad"'), _response('{"bad"'), _response(_valid_payload())]
        decision = _admit(candidates, max_attempts=2)
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_REPAIR_EXHAUSTED)
        self.assertEqual(len(decision.attempts), 2)

    def test_repair_exhaustion_fails_closed(self):
        candidates = [_response('{"bad"'), _response(json.dumps({"title": "x", "score": 999}))]
        decision = _admit(candidates, max_attempts=3)
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_REPAIR_EXHAUSTED)
        self.assertIsNone(decision.accepted_object)

    def test_first_valid_candidate_short_circuits(self):
        candidates = [_response(_valid_payload()), _response('{"bad"')]
        decision = _admit(candidates, max_attempts=3)
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertEqual(len(decision.attempts), 1)

    def test_malformed_max_attempts_rejected(self):
        for bad in (0, -1, 999, 1.5, True, "3"):
            decision = _admit([_response(_valid_payload())], max_attempts=bad)
            self.assertEqual(decision.reason_code, CODE_MALFORMED_MAX_ATTEMPTS)
            self.assertEqual(decision.status, STATUS_REJECTED)

    def test_accepted_candidate_never_consumes_beyond_bound_from_generator(self):
        # The first bounded candidate is accepted; the next generator element would
        # raise if it were ever produced.  A lazy, bounded consumer never reaches it.
        def _candidates():
            yield _response(_valid_payload())
            raise AssertionError("candidate beyond max_attempts was consumed")

        decision = _admit(_candidates(), max_attempts=1)
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertEqual(len(decision.attempts), 1)

    def test_exhausted_bound_never_consumes_beyond_bound_from_generator(self):
        # All bounded attempts fail (exhaustion), yet the element just past the bound
        # must still never be produced — even when no candidate short-circuits.
        def _candidates():
            yield _response('{"bad"')
            yield _response('{"bad"')
            raise AssertionError("candidate beyond max_attempts was consumed")

        decision = _admit(_candidates(), max_attempts=2)
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_REPAIR_EXHAUSTED)
        self.assertEqual(len(decision.attempts), 2)

    def test_empty_generator_still_fails_closed_with_no_candidates(self):
        def _candidates():
            return
            yield  # pragma: no cover - marks this a generator

        decision = _admit(_candidates(), max_attempts=3)
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_NO_CANDIDATES)


# --- Determinism, codes, purity ----------------------------------------------


class DeterminismAndPurityTest(unittest.TestCase):
    def test_decision_to_dict_is_deterministic(self):
        a = _admit([_response(_valid_payload())]).to_dict()
        b = _admit([_response(_valid_payload())]).to_dict()
        self.assertEqual(a, b)
        self.assertEqual(
            sorted(a),
            sorted(
                [
                    "status",
                    "reason_code",
                    "prompt_id",
                    "version",
                    "template_hash",
                    "target_schema",
                    "schema_id",
                    "schema_hash",
                    "accepted_object",
                    "attempts",
                    "max_attempts",
                ]
            ),
        )

    def test_every_reason_code_is_unique_and_stable(self):
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        for code in REASON_CODES:
            self.assertTrue(code.startswith("ADMIT_"))

    def test_is_repairable_predicate(self):
        self.assertTrue(is_repairable(CODE_MALFORMED_JSON))
        self.assertTrue(is_repairable(CODE_SCHEMA_VIOLATION))
        self.assertFalse(is_repairable(CODE_MALFORMED_RESPONSE))
        self.assertFalse(is_repairable(CODE_UNKNOWN_SCHEMA))

    def test_admission_is_a_pure_value_with_no_filesystem_side_effects(self):
        cwd = os.getcwd()
        before = set(os.listdir(cwd))
        decision = _admit([_response(_valid_payload())])
        after = set(os.listdir(cwd))
        self.assertEqual(before, after)
        self.assertIsInstance(decision, AdmissionDecision)
        # Re-running yields an equal projection (referential transparency).
        self.assertEqual(decision.to_dict(), _admit([_response(_valid_payload())]).to_dict())
        # No state/objects/, events, or artifacts directory was created.
        for sentinel in ("state", "events.jsonl", "artifacts"):
            self.assertNotIn(sentinel, after - before)


if __name__ == "__main__":
    unittest.main()
