"""Unit tests for the local restricted raw-output artifact reference contract (WP-05g / T-05-07).

Covers, for the offline, deterministic, inert raw-output reference foundation:

- a restricted raw-output reference built from a tiny synthetic :class:`LLMResponse`,
- an ordinary business projection that contains only reference/metadata and **never** the
  full raw output,
- a bounded audit projection traceable by ids/hashes that **never** exposes the full raw
  output,
- malformed / missing response / binding / parsed-ref / restriction inputs failing closed
  with deterministic reason codes and **no artifact**,
- empty / oversized / non-serializable raw output failing closed,
- the full raw output being redacted/withheld from ``to_dict`` / business / audit / repr,
  reachable only through the explicit restricted accessor,
- binding derived from a synthetic :class:`AdmissionDecision`,
- the builder writing no project-state / event / artifact / log side effect, mutating none
  of its inputs, importing no I/O / network surface, and being a deterministic total
  function of its inputs.

All fixtures are tiny synthetic values (fake ids, ``{"answer": "synthetic"}``) — no real
human-derived data, secret, credential, real model output, or external-tool output.  The
whole module is offline and deterministic: no network, subprocess, provider SDK, credential
access, or content egress.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from auto_bioinfo.agent_gateway.llm_provider import (
    FINISH_STOP,
    ROLE_ASSISTANT,
    LLMMessage,
    LLMResponse,
    LLMUsage,
)
from auto_bioinfo.agent_gateway.raw_output_artifact import (
    ACCESS_TIER_AUDIT_ONLY,
    ACCESS_TIER_RESTRICTED_STORE,
    CODE_EMPTY_RAW_OUTPUT,
    CODE_MALFORMED_BINDING,
    CODE_MALFORMED_RAW_OUTPUT,
    CODE_MALFORMED_RESPONSE,
    CODE_MALFORMED_RESTRICTION,
    CODE_MISSING_BINDING,
    CODE_MISSING_PARSED_REF,
    CODE_NONSERIALIZABLE_RAW_OUTPUT,
    CODE_RAW_OUTPUT_TOO_LARGE,
    MAX_RAW_OUTPUT_BYTES,
    REASON_CODES,
    REDACTION_NOT_REDACTED,
    REDACTION_REDACTED,
    RESTRICTION_HIGHLY_RESTRICTED,
    RESTRICTION_RESTRICTED,
    RETENTION_EPHEMERAL,
    RETENTION_STANDARD,
    STATUS_BUILT,
    STATUS_REJECTED,
    RawOutputArtifactDecision,
    RestrictedRawOutputArtifact,
    build_raw_output_artifact,
)
from auto_bioinfo.agent_gateway.structured_output import (
    STATUS_ACCEPTED,
    AdmissionDecision,
)


def _response(content: str = "synthetic raw model output") -> LLMResponse:
    """A tiny synthetic, valid assistant response (never a real model)."""
    return LLMResponse(
        provider="fake-local",
        model="fake-echo-1",
        message=LLMMessage(role=ROLE_ASSISTANT, content=content),
        finish_reason=FINISH_STOP,
        usage=LLMUsage.from_counts(3, 4),
    )


def _build(**overrides):
    """Build with sensible synthetic defaults, overridable per test."""
    kwargs = {
        "response": _response(),
        "parsed_result_ref": "parsed-ref-001",
        "prompt_id": "prompt.summary",
        "prompt_version": "v1",
        "template_hash": "a" * 64,
    }
    kwargs.update(overrides)
    response = kwargs.pop("response")
    return build_raw_output_artifact(response, **kwargs)


class BuildRestrictedReferenceTest(unittest.TestCase):
    def test_restricted_reference_built_from_tiny_response(self):
        decision = _build()
        self.assertIsInstance(decision, RawOutputArtifactDecision)
        self.assertEqual(decision.status, STATUS_BUILT)
        self.assertIsNone(decision.reason_code)
        self.assertTrue(decision.built)
        artifact = decision.artifact
        self.assertIsInstance(artifact, RestrictedRawOutputArtifact)
        self.assertTrue(artifact.artifact_id.startswith("rawart_"))
        self.assertEqual(len(artifact.raw_fingerprint), 64)
        self.assertEqual(artifact.prompt_id, "prompt.summary")
        self.assertEqual(artifact.prompt_version, "v1")
        self.assertEqual(artifact.parsed_result_ref, "parsed-ref-001")
        self.assertEqual(artifact.restriction_label, RESTRICTION_RESTRICTED)
        self.assertEqual(artifact.access_tier, ACCESS_TIER_RESTRICTED_STORE)
        self.assertEqual(artifact.retention_hint, RETENTION_STANDARD)
        self.assertEqual(artifact.redaction_status, REDACTION_REDACTED)
        self.assertEqual(artifact.provider, "fake-local")
        self.assertEqual(artifact.model, "fake-echo-1")

    def test_build_is_deterministic(self):
        first = _build()
        second = _build()
        self.assertEqual(first.artifact.artifact_id, second.artifact.artifact_id)
        self.assertEqual(first.artifact.raw_fingerprint, second.artifact.raw_fingerprint)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_restricted_payload_reachable_only_through_explicit_accessor(self):
        artifact = _build().artifact
        revealed = artifact.reveal_restricted_payload()
        # The stored restricted payload is the full response projection.
        self.assertIsInstance(revealed, dict)
        self.assertEqual(revealed["message"]["content"], "synthetic raw model output")

    def test_alternate_labels_are_accepted(self):
        decision = _build(
            restriction_label=RESTRICTION_HIGHLY_RESTRICTED,
            access_tier=ACCESS_TIER_AUDIT_ONLY,
            retention_hint=RETENTION_EPHEMERAL,
            apply_redaction=False,
        )
        self.assertEqual(decision.status, STATUS_BUILT)
        self.assertEqual(decision.artifact.restriction_label, RESTRICTION_HIGHLY_RESTRICTED)
        self.assertEqual(decision.artifact.access_tier, ACCESS_TIER_AUDIT_ONLY)
        self.assertEqual(decision.artifact.redaction_status, REDACTION_NOT_REDACTED)


class ProjectionsWithholdRawOutputTest(unittest.TestCase):
    SECRET_CONTENT = "the model said the answer is 42 and it is unique synthetic text"

    def _artifact(self):
        return _build(response=_response(self.SECRET_CONTENT)).artifact

    def test_business_reference_has_only_reference_metadata(self):
        ref = self._artifact().business_reference()
        self.assertEqual(
            set(ref),
            {"artifact_id", "parsed_result_ref", "raw_fingerprint", "restriction_label", "access_tier"},
        )
        self.assertNotIn(self.SECRET_CONTENT, json.dumps(ref))

    def test_audit_projection_traceable_without_raw_output(self):
        audit = self._artifact().audit_projection()
        self.assertTrue(audit["traceable"])
        self.assertIn("raw_fingerprint", audit)
        self.assertIn("prompt_id", audit)
        self.assertIn("parsed_result_ref", audit)
        self.assertNotIn(self.SECRET_CONTENT, json.dumps(audit))

    def test_to_dict_and_repr_withhold_raw_output(self):
        artifact = self._artifact()
        self.assertNotIn(self.SECRET_CONTENT, json.dumps(artifact.to_dict()))
        self.assertNotIn(self.SECRET_CONTENT, repr(artifact))
        self.assertNotIn("_restricted_payload", repr(artifact))
        # But the explicit restricted accessor still has it.
        self.assertIn(self.SECRET_CONTENT, json.dumps(artifact.reveal_restricted_payload()))

    def test_decision_projections_withhold_raw_output(self):
        decision = _build(response=_response(self.SECRET_CONTENT))
        self.assertNotIn(self.SECRET_CONTENT, json.dumps(decision.to_dict()))
        self.assertNotIn(self.SECRET_CONTENT, json.dumps(decision.business_reference()))
        self.assertNotIn(self.SECRET_CONTENT, json.dumps(decision.audit_projection()))

    def test_inline_secret_is_redacted_from_stored_payload(self):
        decision = _build(response=_response("authorization: Bearer abc123secret"))
        stored = json.dumps(decision.artifact.reveal_restricted_payload())
        self.assertNotIn("abc123secret", stored)
        self.assertEqual(decision.artifact.redaction_status, REDACTION_REDACTED)


class FailClosedBindingTest(unittest.TestCase):
    def test_malformed_response_fails_closed(self):
        for bad in (None, "not-a-response", 123, object()):
            decision = build_raw_output_artifact(bad, parsed_result_ref="r", prompt_id="p", prompt_version="v")
            self.assertEqual(decision.status, STATUS_REJECTED)
            self.assertEqual(decision.reason_code, CODE_MALFORMED_RESPONSE)
            self.assertIsNone(decision.artifact)

    def test_invalid_response_fails_closed(self):
        # An LLMResponse whose message role is not assistant is invalid.
        bad = LLMResponse(
            provider="fake-local",
            model="fake-echo-1",
            message=LLMMessage(role="user", content="x"),
            finish_reason=FINISH_STOP,
        )
        decision = _build(response=bad)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_RESPONSE)

    def test_missing_prompt_binding_fails_closed(self):
        decision = _build(prompt_id=None, prompt_version=None, template_hash=None)
        self.assertEqual(decision.reason_code, CODE_MISSING_BINDING)
        self.assertIsNone(decision.artifact)

    def test_malformed_prompt_binding_fails_closed(self):
        for bad in ("", "  ", "x" * 5000, "line\nbreak", 12):
            decision = _build(prompt_id=bad)
            self.assertEqual(decision.reason_code, CODE_MALFORMED_BINDING)

    def test_malformed_template_hash_fails_closed(self):
        decision = _build(template_hash="bad\nhash")
        self.assertEqual(decision.reason_code, CODE_MALFORMED_BINDING)

    def test_missing_parsed_ref_fails_closed(self):
        for bad in (None, "", "   ", 5, "x" * 5000):
            decision = _build(parsed_result_ref=bad)
            self.assertEqual(decision.reason_code, CODE_MISSING_PARSED_REF)

    def test_malformed_restriction_label_fails_closed(self):
        self.assertEqual(_build(restriction_label="public").reason_code, CODE_MALFORMED_RESTRICTION)
        self.assertEqual(_build(access_tier="open").reason_code, CODE_MALFORMED_RESTRICTION)
        self.assertEqual(_build(retention_hint="forever").reason_code, CODE_MALFORMED_RESTRICTION)
        self.assertEqual(_build(apply_redaction="yes").reason_code, CODE_MALFORMED_RESTRICTION)

    def test_malformed_admission_fails_closed(self):
        decision = _build(prompt_id=None, prompt_version=None, admission="not-an-admission")
        self.assertEqual(decision.reason_code, CODE_MALFORMED_BINDING)


class FailClosedRawOutputTest(unittest.TestCase):
    def test_empty_raw_output_fails_closed(self):
        for empty in ("", {}, []):
            decision = _build(raw_output=empty)
            self.assertEqual(decision.reason_code, CODE_EMPTY_RAW_OUTPUT)

    def test_oversized_raw_output_fails_closed(self):
        big = {"answer": "x" * (MAX_RAW_OUTPUT_BYTES + 100)}
        decision = _build(raw_output=big)
        self.assertEqual(decision.reason_code, CODE_RAW_OUTPUT_TOO_LARGE)
        self.assertIsNone(decision.artifact)

    def test_nonserializable_raw_output_fails_closed(self):
        for bad in ({"answer", "set"}, {"k": {1, 2}}, b"bytes", {"k": b"v"}, {5: "non-string-key"}):
            decision = _build(raw_output=bad)
            self.assertEqual(decision.reason_code, CODE_NONSERIALIZABLE_RAW_OUTPUT)

    def test_nonfinite_raw_output_fails_closed(self):
        decision = _build(raw_output={"score": float("inf")})
        self.assertEqual(decision.reason_code, CODE_MALFORMED_RAW_OUTPUT)

    def test_over_deep_raw_output_fails_closed(self):
        payload: dict = {}
        node = payload
        for _ in range(40):
            node["n"] = {}
            node = node["n"]
        decision = _build(raw_output=payload)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_RAW_OUTPUT)

    def test_explicit_synthetic_raw_output_round_trips(self):
        decision = _build(raw_output={"answer": "synthetic"})
        self.assertEqual(decision.status, STATUS_BUILT)
        self.assertEqual(decision.artifact.reveal_restricted_payload(), {"answer": "synthetic"})


class AdmissionBindingTest(unittest.TestCase):
    def _admission(self) -> AdmissionDecision:
        return AdmissionDecision(
            status=STATUS_ACCEPTED,
            reason_code=None,
            prompt_id="prompt.from.admission",
            version="v7",
            template_hash="b" * 64,
            target_schema="schema.summary",
            schema_id="schema.summary",
            schema_hash="c" * 64,
            accepted_object={"answer": "synthetic"},
        )

    def test_binding_derived_from_admission(self):
        decision = build_raw_output_artifact(
            _response(),
            parsed_result_ref="parsed-ref-007",
            admission=self._admission(),
        )
        self.assertEqual(decision.status, STATUS_BUILT)
        self.assertEqual(decision.artifact.prompt_id, "prompt.from.admission")
        self.assertEqual(decision.artifact.prompt_version, "v7")
        self.assertEqual(decision.artifact.template_hash, "b" * 64)
        self.assertEqual(decision.artifact.admission_status, STATUS_ACCEPTED)

    def test_explicit_args_override_admission(self):
        decision = build_raw_output_artifact(
            _response(),
            parsed_result_ref="parsed-ref-007",
            prompt_id="explicit.prompt",
            prompt_version="v9",
            admission=self._admission(),
        )
        self.assertEqual(decision.artifact.prompt_id, "explicit.prompt")
        self.assertEqual(decision.artifact.prompt_version, "v9")


class InertContractTest(unittest.TestCase):
    def test_artifact_and_decision_are_frozen(self):
        decision = _build()
        with self.assertRaises(FrozenInstanceError):
            decision.status = STATUS_REJECTED  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            decision.artifact.artifact_id = "x"  # type: ignore[misc]

    def test_inputs_are_not_mutated(self):
        response = _response()
        raw = {"answer": "synthetic"}
        before = json.dumps(raw, sort_keys=True)
        build_raw_output_artifact(
            response,
            parsed_result_ref="parsed-ref-001",
            prompt_id="p",
            prompt_version="v",
            raw_output=raw,
        )
        self.assertEqual(json.dumps(raw, sort_keys=True), before)
        # Response value object is unchanged.
        self.assertEqual(response.message.content, "synthetic raw model output")

    def test_all_reason_codes_are_unique_and_prefixed(self):
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        self.assertTrue(all(code.startswith("RAWART_") for code in REASON_CODES))


if __name__ == "__main__":
    unittest.main()
