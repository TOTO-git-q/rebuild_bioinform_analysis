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
    CODE_DUPLICATE_VALIDATOR,
    CODE_EMPTY_PAYLOAD,
    CODE_MALFORMED_JSON,
    CODE_MALFORMED_MAX_ATTEMPTS,
    CODE_MALFORMED_RESPONSE,
    CODE_MALFORMED_SCHEMA,
    CODE_MALFORMED_SCHEMA_ID,
    CODE_MALFORMED_VALIDATOR,
    CODE_MALFORMED_VALIDATOR_ID,
    CODE_MALFORMED_VALIDATOR_REQUEST,
    CODE_MALFORMED_VALIDATOR_RESULT,
    CODE_MULTIPLE_PAYLOADS,
    CODE_NO_CANDIDATES,
    CODE_NON_FINITE_NUMBER,
    CODE_PAYLOAD_TOO_LARGE,
    CODE_REPAIR_EXHAUSTED,
    CODE_SCHEMA_DRIFT,
    CODE_SCHEMA_MISMATCH,
    CODE_SCHEMA_VIOLATION,
    CODE_SEMANTIC_REJECTED,
    CODE_SEMANTIC_VALIDATOR_ERROR,
    CODE_UNKNOWN_SCHEMA,
    CODE_UNKNOWN_VALIDATOR,
    CODE_UNSUPPORTED_SHAPE,
    MAX_OUTPUT_TEXT_LENGTH,
    MAX_SEMANTIC_VALIDATORS,
    REASON_CODES,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    AdmissionDecision,
    SchemaRegistry,
    SemanticValidationResult,
    SemanticValidatorRegistry,
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
                    "applied_semantic_validators",
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


# --- Domain semantic validator hook (WP-05d / T-05-04) -----------------------
#
# Tiny, deterministic, offline semantic validators over the already-admitted
# structured object.  No real human-derived data, no network, no provider, no
# content egress — pure local rules.


def _accept_validator(obj, context):
    return SemanticValidationResult.accept()


def _reject_validator(obj, context):
    return SemanticValidationResult.reject("always rejects")


def _score_must_be_positive(obj, context):
    """A real domain-style rule the schema alone (minimum 0) cannot express."""
    if isinstance(obj.get("score"), int) and obj["score"] > 0:
        return SemanticValidationResult.accept()
    return SemanticValidationResult.reject("score must be strictly positive")


def _raises_validator(obj, context):
    raise ValueError("validator blew up")


def _malformed_result_validator(obj, context):
    return "not a SemanticValidationResult"


def _mutating_validator(obj, context):
    # Mutating the supplied object must never leak into the accepted object.
    obj["injected"] = True
    obj.setdefault("tags", []).append("tampered")
    return SemanticValidationResult.accept()


def _context_aware_validator(obj, context):
    if context.get("allow") is True:
        return SemanticValidationResult.accept()
    return SemanticValidationResult.reject("context did not allow")


def _validator_registry():
    return SemanticValidatorRegistry(
        {
            "score.positive": _score_must_be_positive,
            "always.accept": _accept_validator,
            "always.reject": _reject_validator,
        }
    )


def _candidates_then_raise(*payloads):
    for payload in payloads:
        yield _response(payload)
    raise AssertionError("a candidate beyond max_attempts was consumed")


class SemanticValidationResultTest(unittest.TestCase):
    def test_accept_and_reject_constructors(self):
        self.assertTrue(SemanticValidationResult.accept().valid)
        rejected = SemanticValidationResult.reject("nope")
        self.assertFalse(rejected.valid)
        self.assertEqual(rejected.message, "nope")

    def test_to_dict_is_deterministic(self):
        self.assertEqual(SemanticValidationResult.reject("x").to_dict(), {"valid": False, "message": "x"})
        self.assertEqual(SemanticValidationResult.accept().to_dict(), {"valid": True, "message": None})


class SemanticValidatorRegistryTest(unittest.TestCase):
    def test_register_and_resolve(self):
        registry = _validator_registry()
        self.assertEqual(len(registry), 3)
        self.assertIn("score.positive", registry)
        self.assertTrue(registry.contains("always.accept"))
        self.assertEqual(registry.resolve("always.accept"), _accept_validator)
        self.assertEqual(set(registry.validator_ids()), {"score.positive", "always.accept", "always.reject"})

    def test_malformed_validator_id_rejected(self):
        for bad in ("", "   ", "with\nnewline", 5, None):
            with self.assertRaises(StructuredOutputError) as ctx:
                SemanticValidatorRegistry().register(bad, _accept_validator)
            self.assertEqual(ctx.exception.code, CODE_MALFORMED_VALIDATOR_ID)

    def test_non_callable_validator_rejected(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            SemanticValidatorRegistry().register("v", 123)
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_VALIDATOR)

    def test_duplicate_validator_rejected(self):
        registry = SemanticValidatorRegistry({"v": _accept_validator})
        with self.assertRaises(StructuredOutputError) as ctx:
            registry.register("v", _reject_validator)
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_VALIDATOR)

    def test_resolve_unknown_fails_closed(self):
        with self.assertRaises(StructuredOutputError) as ctx:
            SemanticValidatorRegistry().resolve("ghost")
        self.assertEqual(ctx.exception.code, CODE_UNKNOWN_VALIDATOR)


class SemanticValidationAdmissionTest(unittest.TestCase):
    def test_semantic_pass_after_schema_pass_accepts(self):
        decision = _admit(
            [_response(_valid_payload(score=87))],
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["score.positive"],
        )
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertEqual(decision.accepted_object["score"], 87)
        self.assertEqual(decision.applied_semantic_validators, ("score.positive",))
        self.assertTrue(decision.attempts[0].accepted)

    def test_no_validators_requested_is_legacy_schema_only_admission(self):
        decision = _admit([_response(_valid_payload(score=0))])
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertEqual(decision.applied_semantic_validators, ())
        # An explicitly empty request is also a no-op gate.
        empty = _admit(
            [_response(_valid_payload(score=0))],
            semantic_validators=_validator_registry(),
            semantic_validator_ids=[],
        )
        self.assertEqual(empty.status, STATUS_ACCEPTED)
        self.assertEqual(empty.applied_semantic_validators, ())

    def test_schema_valid_but_semantic_invalid_then_later_valid_accepted(self):
        # score=0 is schema-valid (minimum 0) but fails the positivity rule; a later
        # candidate with score>0 is accepted within the attempt bound.
        candidates = [
            _response(_valid_payload(score=0)),
            _response(_valid_payload(score=42)),
        ]
        decision = _admit(
            candidates,
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["score.positive"],
            max_attempts=3,
        )
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertEqual(decision.accepted_object["score"], 42)
        self.assertEqual(len(decision.attempts), 2)
        self.assertFalse(decision.attempts[0].accepted)
        self.assertEqual(decision.attempts[0].reason_code, CODE_SEMANTIC_REJECTED)
        self.assertTrue(decision.attempts[1].accepted)

    def test_all_semantically_invalid_exhausts_closed(self):
        # Both are schema-valid (minimum 0) but fail the positivity rule.
        candidates = [_response(_valid_payload(score=0)), _response(_valid_payload(score=0))]
        decision = _admit(
            candidates,
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["score.positive"],
            max_attempts=2,
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_REPAIR_EXHAUSTED)
        self.assertEqual([a.reason_code for a in decision.attempts], [CODE_SEMANTIC_REJECTED, CODE_SEMANTIC_REJECTED])
        self.assertEqual(decision.applied_semantic_validators, ("score.positive",))

    def test_unknown_requested_validator_fails_closed_without_consuming_candidates(self):
        # No silent fallback to no-op validation; the candidate stream is never touched.
        decision = _admit(
            _candidates_then_raise(),  # raises if any candidate is consumed
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["does.not.exist"],
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_VALIDATOR)
        self.assertEqual(decision.attempts, ())

    def test_requested_validator_with_no_registry_fails_closed(self):
        decision = _admit(
            [_response(_valid_payload())],
            semantic_validator_ids=["score.positive"],
        )
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_VALIDATOR)

    def test_validator_exception_fails_closed_and_stops_early(self):
        # A raising validator is a fault in the validator, not repairable content: the
        # retry stops at the first such candidate and never consumes the next one.
        decision = _admit(
            _candidates_then_raise(_valid_payload(score=10)),
            semantic_validators={"boom": _raises_validator},
            semantic_validator_ids=["boom"],
            max_attempts=3,
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_SEMANTIC_VALIDATOR_ERROR)
        self.assertEqual(len(decision.attempts), 1)
        self.assertEqual(decision.attempts[0].reason_code, CODE_SEMANTIC_VALIDATOR_ERROR)

    def test_malformed_validator_result_fails_closed(self):
        decision = _admit(
            [_response(_valid_payload())],
            semantic_validators={"bad": _malformed_result_validator},
            semantic_validator_ids=["bad"],
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_VALIDATOR_RESULT)

    def test_malformed_validator_in_mapping_fails_closed(self):
        decision = _admit(
            [_response(_valid_payload())],
            semantic_validators={"bad": 5},
            semantic_validator_ids=["bad"],
        )
        self.assertEqual(decision.reason_code, CODE_MALFORMED_VALIDATOR)

    def test_semantic_validation_does_not_consume_candidates_beyond_bound(self):
        # Two within-bound candidates are semantically rejected; the source must never
        # be advanced to the third (which would raise).
        decision = _admit(
            _candidates_then_raise(_valid_payload(score=0), _valid_payload(score=0)),
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["always.reject"],
            max_attempts=2,
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_REPAIR_EXHAUSTED)
        self.assertEqual(len(decision.attempts), 2)

    def test_validators_run_in_order_and_short_circuit(self):
        # First validator accepts, second rejects -> a repairable semantic rejection.
        decision = _admit(
            [_response(_valid_payload(score=5))],
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["always.accept", "always.reject"],
            max_attempts=1,
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_REPAIR_EXHAUSTED)
        self.assertEqual(decision.attempts[0].reason_code, CODE_SEMANTIC_REJECTED)
        self.assertEqual(decision.applied_semantic_validators, ("always.accept", "always.reject"))

    def test_validator_cannot_mutate_the_accepted_object(self):
        decision = _admit(
            [_response(_valid_payload(score=7))],
            semantic_validators={"mutate": _mutating_validator},
            semantic_validator_ids=["mutate"],
        )
        self.assertEqual(decision.status, STATUS_ACCEPTED)
        self.assertNotIn("injected", decision.accepted_object)
        self.assertNotIn("tampered", decision.accepted_object.get("tags", []))

    def test_inert_context_is_passed_to_validators(self):
        allowed = _admit(
            [_response(_valid_payload())],
            semantic_validators={"ctx": _context_aware_validator},
            semantic_validator_ids=["ctx"],
            semantic_context={"allow": True},
        )
        self.assertEqual(allowed.status, STATUS_ACCEPTED)
        denied = _admit(
            [_response(_valid_payload())],
            semantic_validators={"ctx": _context_aware_validator},
            semantic_validator_ids=["ctx"],
            semantic_context={"allow": False},
            max_attempts=1,
        )
        self.assertEqual(denied.status, STATUS_REJECTED)
        self.assertEqual(denied.attempts[0].reason_code, CODE_SEMANTIC_REJECTED)

    def test_malformed_context_fails_closed(self):
        decision = _admit(
            [_response(_valid_payload())],
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["always.accept"],
            semantic_context=123,
        )
        self.assertEqual(decision.reason_code, CODE_MALFORMED_VALIDATOR_REQUEST)

    def test_malformed_request_list_fails_closed(self):
        registry = _validator_registry()
        bad_requests = [
            "always.accept",  # a bare string is not a list of ids
            123,  # not iterable
            ["always.accept", "always.accept"],  # duplicate id
            [123],  # non-string entry
            ["  "],  # blank id
            [f"v{i}" for i in range(MAX_SEMANTIC_VALIDATORS + 1)],  # too many
        ]
        for request in bad_requests:
            decision = _admit(
                [_response(_valid_payload())],
                semantic_validators=registry,
                semantic_validator_ids=request,
            )
            self.assertEqual(decision.reason_code, CODE_MALFORMED_VALIDATOR_REQUEST, request)

    def test_oversized_request_generator_is_bounded_and_consumes_no_candidates(self):
        # A request-id generator that yields far more than the bound and *raises* if it
        # is advanced past MAX_SEMANTIC_VALIDATORS + 1.  Admission must detect the
        # over-bound request from a bounded prefix, fail closed deterministically, and
        # never touch a response candidate.
        def _ids():
            for i in range(MAX_SEMANTIC_VALIDATORS + 1):
                yield f"v{i}"
            raise AssertionError("request id beyond MAX_SEMANTIC_VALIDATORS + 1 was consumed")

        def _candidates():
            raise AssertionError("a response candidate was consumed for a malformed validator request")
            yield  # pragma: no cover - marks this a generator

        decision = _admit(
            _candidates(),
            semantic_validators=_validator_registry(),
            semantic_validator_ids=_ids(),
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_VALIDATOR_REQUEST)
        self.assertEqual(decision.attempts, ())
        self.assertIsNone(decision.accepted_object)

    def test_misbehaving_request_generator_fails_closed_without_leaking(self):
        # A request iterable that raises *within* the bound must fail closed with the
        # deterministic reason code rather than leaking its own exception out of
        # admission, and must not consume any response candidate.
        def _ids():
            yield "score.positive"
            raise RuntimeError("request id source exploded")

        def _candidates():
            raise AssertionError("a response candidate was consumed for a malformed validator request")
            yield  # pragma: no cover - marks this a generator

        decision = _admit(
            _candidates(),
            semantic_validators=_validator_registry(),
            semantic_validator_ids=_ids(),
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_VALIDATOR_REQUEST)
        self.assertEqual(decision.attempts, ())

    def test_mapping_form_of_validators_is_supported(self):
        decision = _admit(
            [_response(_valid_payload(score=3))],
            semantic_validators={"score.positive": _score_must_be_positive},
            semantic_validator_ids=["score.positive"],
        )
        self.assertEqual(decision.status, STATUS_ACCEPTED)

    def test_semantic_reason_codes_repairability(self):
        self.assertTrue(is_repairable(CODE_SEMANTIC_REJECTED))
        self.assertFalse(is_repairable(CODE_SEMANTIC_VALIDATOR_ERROR))
        self.assertFalse(is_repairable(CODE_MALFORMED_VALIDATOR_RESULT))
        self.assertFalse(is_repairable(CODE_UNKNOWN_VALIDATOR))

    def test_semantic_admission_has_no_filesystem_side_effects(self):
        cwd = os.getcwd()
        before = set(os.listdir(cwd))
        _admit(
            [_response(_valid_payload(score=0)), _response(_valid_payload(score=9))],
            semantic_validators=_validator_registry(),
            semantic_validator_ids=["score.positive"],
            max_attempts=3,
        )
        self.assertEqual(set(os.listdir(cwd)) - before, set())


if __name__ == "__main__":
    unittest.main()
