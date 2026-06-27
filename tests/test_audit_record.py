"""Unit tests for the local provider/tool-call audit record contract (WP-05h / T-05-08).

Covers, for the offline, deterministic, inert audit-record foundation:

- a provider-call audit record built from tiny synthetic provider/prompt/usage/timing
  metadata (and from an inert :class:`LLMResponse` / :class:`AdmissionDecision`),
- a tool-call audit record built from tiny synthetic Tool Broker metadata **without
  executing a tool**,
- the in-memory query helper returning records by ``project_id`` / ``correlation_id``
  without mutating the supplied collection and without creating any repository/index,
- public ``to_dict()`` / audit / query projections omitting prompt content, full raw
  output, raw input values, and tool arguments,
- the optional raw-output artifact reference being stored as a bounded id/fingerprint
  only, never the payload,
- malformed bindings, missing ids, negative / non-finite / oversized usage & timing,
  inconsistent outcome/reason, cross-kind field mixing, and sensitive-metadata leak
  attempts failing closed with deterministic reason codes and **no record**,
- the builder / query helper writing no project-state / event / artifact / log side
  effect, mutating none of their inputs, and being deterministic total functions.

All fixtures are tiny synthetic values (fake ids, ``{"tokens": 3}``, ``duration_ms=12``)
— no real human-derived data, secret, credential, real model output, real timing
telemetry, or external-tool output.  The whole module is offline and deterministic: no
network, subprocess, provider SDK, credential access, real clock, or content egress.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from auto_bioinfo.agent_gateway.audit_record import (
    CALL_KIND_PROVIDER,
    CALL_KIND_TOOL,
    CODE_INCONSISTENT_KIND_FIELDS,
    CODE_INCONSISTENT_STATUS,
    CODE_INVALID_TIMING,
    CODE_INVALID_USAGE,
    CODE_MALFORMED_ARTIFACT_REF,
    CODE_MALFORMED_BINDING,
    CODE_MALFORMED_CALL_IDENTITY,
    CODE_MALFORMED_CALL_KIND,
    CODE_MALFORMED_METADATA,
    CODE_MALFORMED_OUTCOME,
    CODE_MALFORMED_PROVIDER_IDENTIFIER,
    CODE_MALFORMED_SOURCE,
    CODE_MALFORMED_TOOL_IDENTIFIER,
    CODE_METADATA_TOO_LARGE,
    CODE_MISSING_BINDING,
    CODE_MISSING_CALL_IDENTITY,
    CODE_MISSING_TIMING,
    CODE_MISSING_USAGE,
    CODE_SENSITIVE_METADATA,
    MAX_ATTEMPT,
    MAX_DURATION_MS,
    MAX_METADATA_BYTES,
    OUTCOME_COMPLETED,
    OUTCOME_DENIED,
    OUTCOME_FAILED,
    REASON_CODES,
    STATUS_BUILT,
    STATUS_REJECTED,
    AuditRecord,
    AuditRecordDecision,
    build_audit_record,
    query_audit_records,
)
from auto_bioinfo.agent_gateway.llm_provider import (
    FINISH_STOP,
    ROLE_ASSISTANT,
    LLMMessage,
    LLMResponse,
    LLMUsage,
)
from auto_bioinfo.agent_gateway.raw_output_artifact import build_raw_output_artifact
from auto_bioinfo.agent_gateway.structured_output import (
    STATUS_ACCEPTED,
    AdmissionDecision,
)
from auto_bioinfo.agent_gateway.tool_broker import ToolMediationDecision


def _provider(**overrides):
    """Build a valid provider-call record with sensible synthetic defaults."""
    kwargs = {
        "call_id": "call-001",
        "project_id": "proj-001",
        "correlation_id": "corr-001",
        "call_kind": CALL_KIND_PROVIDER,
        "outcome": OUTCOME_COMPLETED,
        "provider": "fake-local",
        "model": "fake-echo-1",
        "prompt_id": "prompt.summary",
        "prompt_version": "v1",
        "usage": {"tokens": 3},
        "duration_ms": 12,
    }
    kwargs.update(overrides)
    return build_audit_record(**kwargs)


def _tool(**overrides):
    """Build a valid tool-call record with sensible synthetic defaults."""
    kwargs = {
        "call_id": "call-002",
        "project_id": "proj-001",
        "correlation_id": "corr-002",
        "call_kind": CALL_KIND_TOOL,
        "outcome": OUTCOME_COMPLETED,
        "tool_name": "lookup.dataset",
        "tool_version": "v2",
        "tool_request_ref": "treq-001",
        "tool_result_ref": "tres-001",
        "duration_ms": 7,
    }
    kwargs.update(overrides)
    return build_audit_record(**kwargs)


def _response() -> LLMResponse:
    """A tiny synthetic, valid assistant response (never a real model)."""
    return LLMResponse(
        provider="fake-local",
        model="fake-echo-1",
        message=LLMMessage(role=ROLE_ASSISTANT, content="synthetic raw model output"),
        finish_reason=FINISH_STOP,
        usage=LLMUsage.from_counts(3, 4),
    )


def _admission() -> AdmissionDecision:
    """A tiny synthetic accepted admission decision (never a real model)."""
    return AdmissionDecision(
        status=STATUS_ACCEPTED,
        reason_code=None,
        prompt_id="prompt.summary",
        version="v1",
        template_hash="a" * 64,
        target_schema="schema.summary",
        schema_id="schema.summary",
        schema_hash="b" * 64,
        accepted_object={"answer": "synthetic"},
    )


class BuildProviderRecordTest(unittest.TestCase):
    def test_provider_record_built_from_tiny_metadata(self):
        decision = _provider()
        self.assertIsInstance(decision, AuditRecordDecision)
        self.assertEqual(decision.status, STATUS_BUILT)
        self.assertIsNone(decision.reason_code)
        self.assertTrue(decision.built)
        record = decision.record
        self.assertIsInstance(record, AuditRecord)
        self.assertTrue(record.record_id.startswith("audit_"))
        self.assertEqual(record.call_kind, CALL_KIND_PROVIDER)
        self.assertEqual(record.project_id, "proj-001")
        self.assertEqual(record.correlation_id, "corr-001")
        self.assertEqual(record.provider, "fake-local")
        self.assertEqual(record.model, "fake-echo-1")
        self.assertEqual(record.prompt_id, "prompt.summary")
        self.assertEqual(record.usage, {"tokens": 3})
        self.assertEqual(record.duration_ms, 12)
        self.assertIsNone(record.tool_name)

    def test_build_is_deterministic(self):
        self.assertEqual(_provider().record.record_id, _provider().record.record_id)

    def test_provider_fields_derived_from_response_and_admission(self):
        decision = build_audit_record(
            call_id="call-003",
            project_id="proj-001",
            correlation_id="corr-003",
            call_kind=CALL_KIND_PROVIDER,
            outcome=OUTCOME_COMPLETED,
            duration_ms=9,
            response=_response(),
            admission=_admission(),
        )
        self.assertTrue(decision.built)
        record = decision.record
        # provider/model/usage come from the inert response; prompt binding from admission.
        self.assertEqual(record.provider, "fake-local")
        self.assertEqual(record.model, "fake-echo-1")
        self.assertEqual(record.usage, {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7})
        self.assertEqual(record.prompt_id, "prompt.summary")
        self.assertEqual(record.prompt_version, "v1")
        self.assertEqual(record.template_hash, "a" * 64)

    def test_explicit_args_override_source_objects(self):
        decision = build_audit_record(
            call_id="call-004",
            project_id="proj-001",
            correlation_id="corr-004",
            call_kind=CALL_KIND_PROVIDER,
            outcome=OUTCOME_COMPLETED,
            provider="explicit-provider",
            usage={"tokens": 1},
            duration_ms=5,
            response=_response(),
        )
        self.assertEqual(decision.record.provider, "explicit-provider")
        self.assertEqual(decision.record.usage, {"tokens": 1})

    def test_failed_provider_call_needs_no_usage_but_needs_reason(self):
        decision = _provider(outcome=OUTCOME_FAILED, outcome_reason="timeout", usage=None, duration_ms=None)
        self.assertTrue(decision.built)
        self.assertEqual(decision.record.outcome, OUTCOME_FAILED)
        self.assertEqual(decision.record.outcome_reason, "timeout")


class BuildToolRecordTest(unittest.TestCase):
    def test_tool_record_built_without_executing_tool(self):
        decision = _tool()
        self.assertTrue(decision.built)
        record = decision.record
        self.assertEqual(record.call_kind, CALL_KIND_TOOL)
        self.assertEqual(record.tool_name, "lookup.dataset")
        self.assertEqual(record.tool_version, "v2")
        self.assertEqual(record.tool_request_ref, "treq-001")
        self.assertEqual(record.tool_result_ref, "tres-001")
        # No provider-side identifiers leak onto a tool record.
        self.assertIsNone(record.provider)
        self.assertIsNone(record.prompt_id)

    def test_tool_fields_derived_from_mediation_decision(self):
        mediation = ToolMediationDecision(
            status="denied",
            reason_code="TOOL_UNKNOWN_TOOL",
            tool_id="lookup.dataset",
            version="v2",
        )
        decision = build_audit_record(
            call_id="call-005",
            project_id="proj-001",
            correlation_id="corr-005",
            call_kind=CALL_KIND_TOOL,
            outcome=OUTCOME_DENIED,
            outcome_reason="not_allowlisted",
            tool_decision=mediation,
        )
        self.assertTrue(decision.built)
        self.assertEqual(decision.record.tool_name, "lookup.dataset")
        self.assertEqual(decision.record.tool_version, "v2")
        self.assertEqual(decision.record.outcome, OUTCOME_DENIED)


class ArtifactReferenceTest(unittest.TestCase):
    def test_raw_output_artifact_reference_is_id_and_fingerprint_only(self):
        artifact = build_raw_output_artifact(
            _response(),
            parsed_result_ref="parsed-ref-001",
            prompt_id="prompt.summary",
            prompt_version="v1",
        ).artifact
        decision = _provider(artifact=artifact)
        self.assertTrue(decision.built)
        record = decision.record
        self.assertEqual(record.raw_output_artifact_id, artifact.artifact_id)
        self.assertEqual(record.raw_output_fingerprint, artifact.raw_fingerprint)
        # The full raw output payload never enters the record / projection.
        payload = json.dumps(artifact.reveal_restricted_payload(), sort_keys=True)
        self.assertNotIn(payload, json.dumps(record.to_dict(), sort_keys=True))

    def test_malformed_artifact_reference_fails_closed(self):
        decision = _provider(raw_output_artifact_id="bad id\nwith newline")
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_MALFORMED_ARTIFACT_REF)


class ProjectionWithholdsContentTest(unittest.TestCase):
    def test_to_dict_and_audit_projection_omit_content_fields(self):
        record = _provider(input_version="iv1", input_fingerprint="f" * 16).record
        for projection in (record.to_dict(), record.audit_projection()):
            self.assertNotIn("prompt_content", projection)
            self.assertNotIn("raw_output", projection)
            self.assertNotIn("arguments", projection)
            self.assertNotIn("input_value", projection)
        self.assertTrue(record.audit_projection()["traceable"])

    def test_to_dict_returns_defensive_copies(self):
        record = _provider(metadata={"attempt_note": "synthetic"}).record
        record.to_dict()["usage"]["tokens"] = 999
        record.to_dict()["metadata"]["attempt_note"] = "mutated"
        self.assertEqual(record.usage, {"tokens": 3})
        self.assertEqual(record.metadata, {"attempt_note": "synthetic"})


class QueryHelperTest(unittest.TestCase):
    def _records(self):
        return [
            _provider().record,
            _tool().record,  # proj-001 / corr-002
            _provider(call_id="call-x", project_id="proj-002", correlation_id="corr-001").record,
        ]

    def test_filter_by_project(self):
        records = self._records()
        result = query_audit_records(records, project_id="proj-001")
        self.assertEqual({r.project_id for r in result}, {"proj-001"})
        self.assertEqual(len(result), 2)

    def test_filter_by_correlation(self):
        result = query_audit_records(self._records(), correlation_id="corr-001")
        self.assertEqual({r.correlation_id for r in result}, {"corr-001"})
        self.assertEqual(len(result), 2)

    def test_filter_by_project_and_correlation(self):
        result = query_audit_records(self._records(), project_id="proj-001", correlation_id="corr-002")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].call_kind, CALL_KIND_TOOL)

    def test_no_filter_returns_all_audit_records(self):
        result = query_audit_records(self._records())
        self.assertEqual(len(result), 3)

    def test_query_does_not_mutate_input(self):
        records = self._records()
        snapshot = list(records)
        query_audit_records(records, project_id="proj-001")
        self.assertEqual(records, snapshot)
        self.assertIsInstance(query_audit_records(records), tuple)

    def test_non_audit_items_never_match(self):
        result = query_audit_records([_provider().record, "not-a-record", 42], project_id="proj-001")
        self.assertTrue(all(isinstance(r, AuditRecord) for r in result))
        self.assertEqual(len(result), 1)

    def test_malformed_filter_matches_nothing(self):
        self.assertEqual(query_audit_records(self._records(), project_id="bad\nid"), ())

    def test_non_collection_returns_empty(self):
        self.assertEqual(query_audit_records("not-a-list"), ())


class FailClosedTest(unittest.TestCase):
    def test_malformed_call_kind_fails_closed(self):
        self.assertEqual(_provider(call_kind="weird").reason_code, CODE_MALFORMED_CALL_KIND)

    def test_missing_call_id_fails_closed(self):
        self.assertEqual(_provider(call_id=None).reason_code, CODE_MISSING_CALL_IDENTITY)

    def test_malformed_call_id_fails_closed(self):
        self.assertEqual(_provider(call_id="bad\nid").reason_code, CODE_MALFORMED_CALL_IDENTITY)

    def test_missing_binding_fails_closed(self):
        self.assertEqual(_provider(project_id=None).reason_code, CODE_MISSING_BINDING)

    def test_malformed_binding_fails_closed(self):
        self.assertEqual(_provider(correlation_id="   ").reason_code, CODE_MALFORMED_BINDING)

    def test_malformed_outcome_fails_closed(self):
        self.assertEqual(_provider(outcome="ok").reason_code, CODE_MALFORMED_OUTCOME)

    def test_malformed_source_fails_closed(self):
        self.assertEqual(_provider(response="not-a-response").reason_code, CODE_MALFORMED_SOURCE)

    def test_missing_provider_identifier_fails_closed(self):
        self.assertEqual(_provider(provider=None).reason_code, CODE_MALFORMED_PROVIDER_IDENTIFIER)

    def test_missing_tool_identifier_fails_closed(self):
        self.assertEqual(_tool(tool_name=None).reason_code, CODE_MALFORMED_TOOL_IDENTIFIER)

    def test_provider_record_with_tool_field_fails_closed(self):
        self.assertEqual(_provider(tool_name="x").reason_code, CODE_INCONSISTENT_KIND_FIELDS)

    def test_tool_record_with_provider_field_fails_closed(self):
        self.assertEqual(_tool(provider="x").reason_code, CODE_INCONSISTENT_KIND_FIELDS)

    def test_completed_provider_call_requires_usage(self):
        self.assertEqual(_provider(usage=None).reason_code, CODE_MISSING_USAGE)

    def test_completed_call_requires_timing(self):
        self.assertEqual(_provider(duration_ms=None).reason_code, CODE_MISSING_TIMING)

    def test_negative_usage_fails_closed(self):
        self.assertEqual(_provider(usage={"tokens": -1}).reason_code, CODE_INVALID_USAGE)

    def test_non_int_usage_fails_closed(self):
        self.assertEqual(_provider(usage={"tokens": 1.5}).reason_code, CODE_INVALID_USAGE)

    def test_negative_duration_fails_closed(self):
        self.assertEqual(_provider(duration_ms=-1).reason_code, CODE_INVALID_TIMING)

    def test_non_finite_duration_fails_closed(self):
        self.assertEqual(_provider(duration_ms=float("inf")).reason_code, CODE_INVALID_TIMING)

    def test_oversized_duration_fails_closed(self):
        self.assertEqual(_provider(duration_ms=MAX_DURATION_MS + 1).reason_code, CODE_INVALID_TIMING)

    def test_bool_duration_fails_closed(self):
        self.assertEqual(_provider(duration_ms=True).reason_code, CODE_INVALID_TIMING)

    def test_invalid_attempt_fails_closed(self):
        self.assertEqual(_provider(attempt=0).reason_code, CODE_INVALID_TIMING)
        self.assertEqual(_provider(attempt=MAX_ATTEMPT + 1).reason_code, CODE_INVALID_TIMING)

    def test_completed_with_reason_fails_closed(self):
        self.assertEqual(_provider(outcome_reason="surprise").reason_code, CODE_INCONSISTENT_STATUS)

    def test_failed_without_reason_fails_closed(self):
        decision = _provider(outcome=OUTCOME_FAILED, usage=None, duration_ms=None)
        self.assertEqual(decision.reason_code, CODE_INCONSISTENT_STATUS)

    def test_sensitive_metadata_leak_fails_closed(self):
        self.assertEqual(_provider(metadata={"api_key": "sk-12345"}).reason_code, CODE_SENSITIVE_METADATA)

    def test_inline_secret_metadata_value_fails_closed(self):
        decision = _provider(metadata={"note": "token=sk-abcdef0123456789"})
        self.assertEqual(decision.reason_code, CODE_SENSITIVE_METADATA)

    def test_oversized_metadata_fails_closed(self):
        decision = _provider(metadata={"note": "x" * (MAX_METADATA_BYTES + 1)})
        self.assertEqual(decision.reason_code, CODE_METADATA_TOO_LARGE)

    def test_malformed_metadata_fails_closed(self):
        self.assertEqual(_provider(metadata="not-a-mapping").reason_code, CODE_MALFORMED_METADATA)
        self.assertEqual(_provider(metadata={"bad": {1, 2}}).reason_code, CODE_MALFORMED_METADATA)


class PurityTest(unittest.TestCase):
    def test_record_and_decision_are_frozen(self):
        decision = _provider()
        with self.assertRaises(FrozenInstanceError):
            decision.status = STATUS_REJECTED  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            decision.record.call_id = "x"  # type: ignore[misc]

    def test_inputs_are_not_mutated(self):
        usage = {"tokens": 3}
        metadata = {"attempt_note": "synthetic"}
        before_usage = json.dumps(usage, sort_keys=True)
        before_metadata = json.dumps(metadata, sort_keys=True)
        build_audit_record(
            call_id="call-001",
            project_id="proj-001",
            correlation_id="corr-001",
            call_kind=CALL_KIND_PROVIDER,
            outcome=OUTCOME_COMPLETED,
            provider="fake-local",
            model="fake-echo-1",
            usage=usage,
            duration_ms=12,
            metadata=metadata,
        )
        self.assertEqual(json.dumps(usage, sort_keys=True), before_usage)
        self.assertEqual(json.dumps(metadata, sort_keys=True), before_metadata)

    def test_all_reason_codes_are_unique_and_prefixed(self):
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        self.assertTrue(all(code.startswith("AUDIT_") for code in REASON_CODES))

    def test_module_imports_no_io_surface(self):
        import auto_bioinfo.agent_gateway.audit_record as module

        for forbidden in ("socket", "subprocess", "requests", "urllib", "http", "os", "time"):
            self.assertNotIn(forbidden, vars(module))


if __name__ == "__main__":
    unittest.main()
