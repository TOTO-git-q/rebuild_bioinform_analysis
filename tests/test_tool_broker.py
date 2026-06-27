"""Unit tests for the local tool allowlist & Tool Broker contract (WP-05f / T-05-06).

Covers, for the offline, deterministic, inert tool-mediation foundation:

- allowlist registration that fails closed on a malformed / duplicate :class:`ToolSpec`,
- an allowed, registered fake tool producing a bounded, inert, redacted result,
- fail-closed denial of an unknown / disabled / version-mismatched / caller-disallowed
  tool, with deterministic reason codes and **no result**,
- fail-closed handling of a malformed request / identity / arguments (non-mapping, bad
  name, too many, oversized, non-serializable, over-deep, non-finite),
- raw sensitive argument data blocked *before any handler sees it*, and inline secrets
  redacted from admitted arguments and from the returned result,
- a handler exception or a malformed / oversized handler result failing closed,
- an unauthorized request never falling back to a default / no-op allowed handler,
- the broker writing no project-state / event / artifact / business side effect, mutating
  none of its inputs, importing no I/O / subprocess / network surface, and being a
  deterministic total function of its inputs.

All fixtures are tiny synthetic values (fake ids, sample args, SENSITIVE markers) — no
real human-derived data, secret, credential, or real external-tool output.  The whole
module is offline and deterministic: no network, subprocess, provider SDK, credential
access, or content egress.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from auto_bioinfo.agent_gateway.context_builder import (
    SENSITIVITY_INTERNAL,
    SENSITIVITY_PUBLIC,
)
from auto_bioinfo.agent_gateway.tool_broker import (
    ALLOWLIST_CODES,
    CODE_ARGUMENTS_TOO_LARGE,
    CODE_CALLER_NOT_ALLOWED,
    CODE_DUPLICATE_TOOL,
    CODE_HANDLER_ERROR,
    CODE_MALFORMED_ALLOWED_CALLERS,
    CODE_MALFORMED_ARGUMENTS,
    CODE_MALFORMED_HANDLER,
    CODE_MALFORMED_IDENTITY,
    CODE_MALFORMED_REQUEST,
    CODE_MALFORMED_RESULT,
    CODE_MALFORMED_TOOL_ID,
    CODE_MALFORMED_TOOL_VERSIONS,
    CODE_NON_PUBLIC_ARGUMENT,
    CODE_NONSERIALIZABLE_ARGUMENTS,
    CODE_RESULT_TOO_LARGE,
    CODE_SENSITIVE_ARGUMENT,
    CODE_TOO_MANY_ARGUMENTS,
    CODE_TOOL_DISABLED,
    CODE_UNKNOWN_TOOL,
    CODE_VERSION_MISMATCH,
    EXECUTION_CODES,
    MAX_PAYLOAD_DEPTH,
    MAX_TOOL_ARGUMENTS,
    REASON_CODES,
    REGISTRY_CODES,
    REQUEST_CODES,
    STATUS_ALLOWED,
    STATUS_DENIED,
    ToolBroker,
    ToolBrokerError,
    ToolCallRequest,
    ToolMediationDecision,
    ToolRegistry,
    ToolSpec,
)
from auto_bioinfo.observability.redaction import REDACTED


def _public(*names: str) -> dict[str, str]:
    """Declare each named argument explicitly ``public`` (the admission contract).

    The broker admits an argument to a handler *only* when the caller proves it public via
    :attr:`ToolCallRequest.argument_sensitivities`; an undeclared argument resolves to
    ``unknown`` and fails closed.  Tests use this helper to build the explicit declaration.
    """
    return {name: SENSITIVITY_PUBLIC for name in names}


class _RecordingHandler:
    """A deterministic, inert in-process fake handler that records what it received.

    It performs no I/O: it only echoes the (already sanitized) arguments it is handed,
    so a test can assert what — if anything — a handler ever saw.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, arguments: dict) -> dict:
        self.calls.append(arguments)
        return {"echoed": arguments, "ok": True}


def _broker(handler=None, **spec_kwargs) -> tuple[ToolBroker, _RecordingHandler]:
    """A broker with a single registered ``summarize`` fake tool (version ``1.0``)."""
    handler = handler if handler is not None else _RecordingHandler()
    spec = ToolSpec("summarize", ("1.0",), handler, **spec_kwargs)
    return ToolBroker(ToolRegistry([spec])), handler


# --- Registry / allowlist registration ---------------------------------------


class ToolRegistryTest(unittest.TestCase):
    """The allowlist registers only well-formed specs and rejects duplicates."""

    def test_registers_and_resolves_by_identity(self) -> None:
        spec = ToolSpec("t", ("1.0",), lambda a: None)
        registry = ToolRegistry([spec])
        self.assertIs(registry.resolve("t"), spec)
        self.assertTrue(registry.contains("t"))
        self.assertIn("t", registry)
        self.assertEqual(registry.tool_ids(), ("t",))
        self.assertEqual(len(registry), 1)

    def test_unknown_id_resolves_to_none_no_fallback(self) -> None:
        registry = ToolRegistry([ToolSpec("t", ("1.0",), lambda a: None)])
        self.assertIsNone(registry.resolve("other"))
        self.assertIsNone(registry.resolve(123))
        self.assertFalse(registry.contains("other"))

    def test_duplicate_registration_fails_closed(self) -> None:
        registry = ToolRegistry([ToolSpec("t", ("1.0",), lambda a: None)])
        with self.assertRaises(ToolBrokerError) as ctx:
            registry.register(ToolSpec("t", ("2.0",), lambda a: None))
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_TOOL)

    def test_malformed_tool_id_fails_closed(self) -> None:
        for bad_id in ("", "  ", "with\nnewline", 123, None):
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(ToolBrokerError) as ctx:
                    ToolRegistry([ToolSpec(bad_id, ("1.0",), lambda a: None)])
                self.assertEqual(ctx.exception.code, CODE_MALFORMED_TOOL_ID)

    def test_malformed_versions_fail_closed(self) -> None:
        for versions in ((), ["1.0"], ("",), ("1.0", "1.0"), ("ok", 9)):
            with self.subTest(versions=versions):
                with self.assertRaises(ToolBrokerError) as ctx:
                    ToolRegistry([ToolSpec("t", versions, lambda a: None)])
                self.assertEqual(ctx.exception.code, CODE_MALFORMED_TOOL_VERSIONS)

    def test_non_callable_handler_fails_closed(self) -> None:
        with self.assertRaises(ToolBrokerError) as ctx:
            ToolRegistry([ToolSpec("t", ("1.0",), "not-callable")])
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_HANDLER)

    def test_malformed_allowed_callers_fail_closed(self) -> None:
        for callers in (["planner"], ("",), ("ok", 1)):
            with self.subTest(callers=callers):
                with self.assertRaises(ToolBrokerError) as ctx:
                    ToolRegistry([ToolSpec("t", ("1.0",), lambda a: None, allowed_callers=callers)])
                self.assertEqual(ctx.exception.code, CODE_MALFORMED_ALLOWED_CALLERS)

    def test_registering_non_spec_fails_closed(self) -> None:
        with self.assertRaises(ToolBrokerError):
            ToolRegistry().register({"tool_id": "t"})


# --- Authorized execution ----------------------------------------------------


class AllowedExecutionTest(unittest.TestCase):
    """An allowed, registered fake tool produces a bounded, inert result."""

    def test_allowed_tool_returns_bounded_inert_result(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"q": "hi", "n": 3}, argument_sensitivities=_public("q", "n")))
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.status, STATUS_ALLOWED)
        self.assertIsNone(decision.reason_code)
        self.assertEqual(decision.tool_id, "summarize")
        self.assertEqual(decision.version, "1.0")
        self.assertEqual(decision.result, {"echoed": {"q": "hi", "n": 3}, "ok": True})
        self.assertEqual(len(handler.calls), 1)

    def test_caller_and_project_context_are_echoed(self) -> None:
        broker, _ = _broker(allowed_callers=("planner",))
        decision = broker.mediate(
            ToolCallRequest("summarize", "1.0", {"q": "x"}, caller_id="planner", project_ref="proj-1", argument_sensitivities=_public("q"))
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.caller_id, "planner")
        self.assertEqual(decision.project_ref, "proj-1")

    def test_empty_arguments_are_allowed(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0"))
        self.assertTrue(decision.allowed)
        self.assertEqual(handler.calls, [{}])

    def test_decision_to_dict_is_deterministic_projection(self) -> None:
        broker, _ = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"q": "x"}, argument_sensitivities=_public("q")))
        self.assertEqual(
            decision.to_dict(),
            {
                "status": STATUS_ALLOWED,
                "reason_code": None,
                "tool_id": "summarize",
                "version": "1.0",
                "caller_id": None,
                "project_ref": None,
                "allowed": True,
                "result": {"echoed": {"q": "x"}, "ok": True},
            },
        )


# --- Allowlist denials --------------------------------------------------------


class AllowlistDenialTest(unittest.TestCase):
    """Unknown / disabled / version- or caller-mismatched tools are denied, no result."""

    def test_unknown_tool_is_denied(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("does-not-exist", "1.0"))
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_TOOL)
        self.assertIsNone(decision.result)
        self.assertEqual(handler.calls, [])

    def test_disabled_tool_is_denied(self) -> None:
        broker, handler = _broker(enabled=False)
        decision = broker.mediate(ToolCallRequest("summarize", "1.0"))
        self.assertEqual(decision.reason_code, CODE_TOOL_DISABLED)
        self.assertEqual(handler.calls, [])

    def test_version_mismatch_is_denied(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "9.9"))
        self.assertEqual(decision.reason_code, CODE_VERSION_MISMATCH)
        self.assertEqual(handler.calls, [])

    def test_caller_not_in_allowlist_is_denied(self) -> None:
        broker, handler = _broker(allowed_callers=("planner",))
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", caller_id="intruder"))
        self.assertEqual(decision.reason_code, CODE_CALLER_NOT_ALLOWED)
        self.assertEqual(handler.calls, [])

    def test_caller_gated_tool_denies_missing_caller(self) -> None:
        broker, _ = _broker(allowed_callers=("planner",))
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0")).reason_code, CODE_CALLER_NOT_ALLOWED)


# --- Malformed request / identity / arguments --------------------------------


class MalformedRequestTest(unittest.TestCase):
    """A malformed request / identity / arguments fails closed before any handler."""

    def test_non_request_object_is_denied(self) -> None:
        broker, handler = _broker()
        for bad in ({"tool_id": "summarize"}, None, "summarize", 7):
            with self.subTest(bad=bad):
                decision = broker.mediate(bad)
                self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)
                self.assertIsNone(decision.tool_id)
        self.assertEqual(handler.calls, [])

    def test_malformed_identity_is_denied(self) -> None:
        broker, handler = _broker()
        # bad tool_id
        self.assertEqual(broker.mediate(ToolCallRequest("", "1.0")).reason_code, CODE_MALFORMED_IDENTITY)
        self.assertEqual(broker.mediate(ToolCallRequest(123, "1.0")).reason_code, CODE_MALFORMED_IDENTITY)
        # bad / missing version
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", None)).reason_code, CODE_MALFORMED_IDENTITY)
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "")).reason_code, CODE_MALFORMED_IDENTITY)
        self.assertEqual(handler.calls, [])

    def test_malformed_caller_or_project_ref_is_denied(self) -> None:
        broker, _ = _broker()
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0", caller_id="bad\nid")).reason_code, CODE_MALFORMED_REQUEST)
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0", project_ref=123)).reason_code, CODE_MALFORMED_REQUEST)

    def test_non_mapping_arguments_are_denied(self) -> None:
        broker, _ = _broker()
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0", ["a", "b"])).reason_code, CODE_MALFORMED_ARGUMENTS)

    def test_malformed_argument_name_is_denied(self) -> None:
        broker, handler = _broker()
        for args in ({"": "x"}, {"bad\nname": "x"}, {7: "x"}):
            with self.subTest(args=args):
                self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0", args)).reason_code, CODE_MALFORMED_ARGUMENTS)
        self.assertEqual(handler.calls, [])

    def test_too_many_arguments_are_denied(self) -> None:
        broker, _ = _broker()
        args = {f"a{i}": i for i in range(MAX_TOOL_ARGUMENTS + 1)}
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0", args)).reason_code, CODE_TOO_MANY_ARGUMENTS)

    def test_oversized_arguments_are_denied(self) -> None:
        broker, _ = _broker()
        args = {"blob": "x" * 70_000}
        self.assertEqual(
            broker.mediate(ToolCallRequest("summarize", "1.0", args, argument_sensitivities=_public("blob"))).reason_code, CODE_ARGUMENTS_TOO_LARGE
        )

    def test_non_serializable_arguments_are_denied(self) -> None:
        broker, handler = _broker()
        for value in ({1, 2, 3}, b"bytes", object()):
            with self.subTest(value=type(value)):
                self.assertEqual(
                    broker.mediate(ToolCallRequest("summarize", "1.0", {"v": value}, argument_sensitivities=_public("v"))).reason_code,
                    CODE_NONSERIALIZABLE_ARGUMENTS,
                )
        self.assertEqual(handler.calls, [])

    def test_non_finite_number_argument_is_denied(self) -> None:
        broker, _ = _broker()
        self.assertEqual(
            broker.mediate(ToolCallRequest("summarize", "1.0", {"v": float("inf")}, argument_sensitivities=_public("v"))).reason_code, CODE_MALFORMED_ARGUMENTS
        )

    def test_over_deep_argument_fails_closed(self) -> None:
        broker, handler = _broker()
        nested: dict = {}
        cursor = nested
        for _ in range(MAX_PAYLOAD_DEPTH + 2):
            cursor["next"] = {}
            cursor = cursor["next"]
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"v": nested}, argument_sensitivities=_public("v")))
        # An over-deep structure cannot be scanned within the bound; it fails closed.
        # The WP-05e sensitivity classifier shares the depth bound and treats an
        # unscannable structure as ``sensitive`` (blocked before normalization), so the
        # bounded reason is either the sensitive-block or the malformed-depth code.
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertIn(decision.reason_code, (CODE_SENSITIVE_ARGUMENT, CODE_MALFORMED_ARGUMENTS))
        self.assertEqual(handler.calls, [])


# --- Sensitive content gating ------------------------------------------------


class SensitiveArgumentTest(unittest.TestCase):
    """Raw sensitive arguments are blocked before any handler sees them; rest redacted."""

    def test_sensitive_key_argument_blocked_before_handler(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"api_token": "abc123"}))
        self.assertEqual(decision.reason_code, CODE_SENSITIVE_ARGUMENT)
        self.assertIsNone(decision.result)
        self.assertEqual(handler.calls, [], "handler must never see a sensitive argument")

    def test_sensitive_value_marker_blocked_before_handler(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"note": "patient PHI record"}))
        self.assertEqual(decision.reason_code, CODE_SENSITIVE_ARGUMENT)
        self.assertEqual(handler.calls, [])

    def test_nested_sensitive_value_blocked_before_handler(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"payload": {"inner": {"password": "hunter2"}}}))
        self.assertEqual(decision.reason_code, CODE_SENSITIVE_ARGUMENT)
        self.assertEqual(handler.calls, [])

    def test_inline_secret_in_admitted_argument_is_redacted_before_handler(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"note": "see Bearer abcdef for access"}, argument_sensitivities=_public("note")))
        self.assertTrue(decision.allowed)
        seen = handler.calls[0]["note"]
        self.assertIn(REDACTED, seen)
        self.assertNotIn("abcdef", seen)

    def test_redacted_result_carries_no_raw_secret(self) -> None:
        broker, _ = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"note": "Bearer abcdef"}, argument_sensitivities=_public("note")))
        self.assertTrue(decision.allowed)
        self.assertNotIn("abcdef", repr(decision.result))


# --- Explicit public admission (undeclared / non-public args fail closed) ----


class PublicArgumentAdmissionTest(unittest.TestCase):
    """An argument reaches a handler only when explicitly declared public; else denied."""

    def test_undeclared_ordinary_argument_classified_unknown_is_denied(self) -> None:
        # Regression (turn 0229): an ordinary, undeclared project note classifies as
        # ``unknown`` in the WP-05e contract and must NOT reach the handler.
        from auto_bioinfo.agent_gateway.context_builder import (
            SENSITIVITY_UNKNOWN,
            classify_field_sensitivity,
        )

        self.assertEqual(classify_field_sensitivity("note", "ordinary project note"), SENSITIVITY_UNKNOWN)
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"note": "ordinary project note"}))
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_NON_PUBLIC_ARGUMENT)
        self.assertIsNone(decision.result)
        self.assertEqual(handler.calls, [], "an undeclared (unknown) argument must never reach a handler")

    def test_explicitly_public_argument_is_admitted(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"note": "ordinary project note"}, argument_sensitivities=_public("note")))
        self.assertTrue(decision.allowed)
        self.assertEqual(handler.calls, [{"note": "ordinary project note"}])

    def test_partially_declared_arguments_fail_closed(self) -> None:
        # Declaring only some arguments public is not enough: the undeclared one is unknown.
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"q": "x", "note": "n"}, argument_sensitivities=_public("q")))
        self.assertEqual(decision.reason_code, CODE_NON_PUBLIC_ARGUMENT)
        self.assertEqual(handler.calls, [])

    def test_internal_declared_argument_is_denied(self) -> None:
        # ``internal`` is non-public; it must not reach a handler either.
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"q": "x"}, argument_sensitivities={"q": SENSITIVITY_INTERNAL}))
        self.assertEqual(decision.reason_code, CODE_NON_PUBLIC_ARGUMENT)
        self.assertEqual(handler.calls, [])

    def test_unrecognized_declaration_resolves_unknown_and_is_denied(self) -> None:
        broker, handler = _broker()
        for bad in ("PUBLIC", "open", "", 1, None):
            with self.subTest(bad=bad):
                decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"q": "x"}, argument_sensitivities={"q": bad}))
                self.assertEqual(decision.reason_code, CODE_NON_PUBLIC_ARGUMENT)
        self.assertEqual(handler.calls, [])

    def test_public_declaration_cannot_override_sensitive_escalation(self) -> None:
        # A credential-like name/value still escalates to ``sensitive`` despite a public
        # declaration; defense-in-depth: a misdeclared secret never reaches a handler.
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"api_token": "abc123"}, argument_sensitivities=_public("api_token")))
        self.assertEqual(decision.reason_code, CODE_SENSITIVE_ARGUMENT)
        self.assertEqual(handler.calls, [])

    def test_malformed_declarations_mapping_fails_closed(self) -> None:
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0", {"q": "x"}, argument_sensitivities=["q"]))
        self.assertEqual(decision.reason_code, CODE_MALFORMED_ARGUMENTS)
        self.assertEqual(handler.calls, [])

    def test_empty_arguments_need_no_declaration(self) -> None:
        # The admission gate only constrains supplied arguments; an empty call is allowed.
        broker, handler = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0"))
        self.assertTrue(decision.allowed)
        self.assertEqual(handler.calls, [{}])


# --- Handler / result faults -------------------------------------------------


class HandlerFaultTest(unittest.TestCase):
    """A handler exception or a malformed / oversized result fails closed."""

    def test_handler_exception_fails_closed(self) -> None:
        def boom(_args):
            raise ValueError("nope")

        broker, _ = _broker(handler=boom)
        decision = broker.mediate(ToolCallRequest("summarize", "1.0"))
        self.assertEqual(decision.reason_code, CODE_HANDLER_ERROR)
        self.assertIsNone(decision.result)

    def test_non_serializable_handler_result_fails_closed(self) -> None:
        broker, _ = _broker(handler=lambda a: {"bad": {1, 2}})
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0")).reason_code, CODE_MALFORMED_RESULT)

    def test_non_finite_handler_result_fails_closed(self) -> None:
        broker, _ = _broker(handler=lambda a: {"x": float("nan")})
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0")).reason_code, CODE_MALFORMED_RESULT)

    def test_over_deep_handler_result_fails_closed(self) -> None:
        def deep(_args):
            nested: dict = {}
            cursor = nested
            for _ in range(MAX_PAYLOAD_DEPTH + 2):
                cursor["next"] = {}
                cursor = cursor["next"]
            return nested

        broker, _ = _broker(handler=deep)
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0")).reason_code, CODE_MALFORMED_RESULT)

    def test_oversized_handler_result_fails_closed(self) -> None:
        broker, _ = _broker(handler=lambda a: {"blob": "x" * 70_000})
        self.assertEqual(broker.mediate(ToolCallRequest("summarize", "1.0")).reason_code, CODE_RESULT_TOO_LARGE)

    def test_none_handler_result_is_allowed(self) -> None:
        broker, _ = _broker(handler=lambda a: None)
        decision = broker.mediate(ToolCallRequest("summarize", "1.0"))
        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.result)


# --- No fallback / no side effects / determinism -----------------------------


class NoFallbackAndInertnessTest(unittest.TestCase):
    """An unauthorized request never reaches an allowed handler; the broker is inert."""

    def test_unauthorized_request_cannot_reach_any_handler(self) -> None:
        # Two distinct registered tools; an unknown id must not fall back to either.
        h1, h2 = _RecordingHandler(), _RecordingHandler()
        broker = ToolBroker(ToolRegistry([ToolSpec("a", ("1.0",), h1), ToolSpec("b", ("1.0",), h2)]))
        decision = broker.mediate(ToolCallRequest("c", "1.0", {"q": "x"}))
        self.assertEqual(decision.reason_code, CODE_UNKNOWN_TOOL)
        self.assertEqual(h1.calls, [])
        self.assertEqual(h2.calls, [])

    def test_empty_registry_denies_everything(self) -> None:
        broker = ToolBroker()
        self.assertEqual(broker.mediate(ToolCallRequest("anything", "1.0")).reason_code, CODE_UNKNOWN_TOOL)

    def test_mediation_does_not_mutate_request_arguments_or_registry(self) -> None:
        broker, _ = _broker()
        args = {"q": "x", "note": "Bearer abcdef"}
        request = ToolCallRequest("summarize", "1.0", args, argument_sensitivities=_public("q", "note"))
        before = dict(args)
        broker.mediate(request)
        self.assertEqual(args, before, "the caller's argument mapping must be untouched")
        self.assertIs(request.arguments, args)
        self.assertEqual(broker.registry.tool_ids(), ("summarize",))

    def test_mediation_is_deterministic(self) -> None:
        broker, _ = _broker()
        request = ToolCallRequest("summarize", "1.0", {"q": "x", "n": 1}, argument_sensitivities=_public("q", "n"))
        first = broker.mediate(request).to_dict()
        second = broker.mediate(request).to_dict()
        self.assertEqual(first, second)

    def test_module_imports_no_io_or_network_surface(self) -> None:
        import ast
        import inspect

        import auto_bioinfo.agent_gateway.tool_broker as module

        forbidden = {
            "os",
            "sys",
            "socket",
            "subprocess",
            "requests",
            "urllib",
            "http",
            "ssl",
            "asyncio",
            "threading",
            "multiprocessing",
            "shutil",
            "pathlib",
        }
        tree = ast.parse(inspect.getsource(module))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
                imported_roots.add(node.module.split(".")[0])
        self.assertFalse(imported_roots & forbidden, f"unexpected I/O/network imports: {imported_roots & forbidden}")


# --- Frozen value shapes & vocabulary integrity ------------------------------


class ValueShapeTest(unittest.TestCase):
    """Decisions / specs / requests are frozen, and the code vocabulary is consistent."""

    def test_decision_is_frozen(self) -> None:
        broker, _ = _broker()
        decision = broker.mediate(ToolCallRequest("summarize", "1.0"))
        with self.assertRaises(FrozenInstanceError):
            decision.status = STATUS_DENIED  # type: ignore[misc]

    def test_spec_is_frozen(self) -> None:
        spec = ToolSpec("t", ("1.0",), lambda a: None)
        with self.assertRaises(FrozenInstanceError):
            spec.enabled = False  # type: ignore[misc]

    def test_reason_codes_partition_cleanly(self) -> None:
        self.assertEqual(set(REASON_CODES), set(REQUEST_CODES) | set(ALLOWLIST_CODES) | set(EXECUTION_CODES))
        # request / allowlist / execution groups are disjoint
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        self.assertEqual(len(REQUEST_CODES) + len(ALLOWLIST_CODES) + len(EXECUTION_CODES), len(REASON_CODES))

    def test_registry_codes_are_disjoint_from_reason_codes(self) -> None:
        self.assertFalse(set(REGISTRY_CODES) & set(REASON_CODES))

    def test_every_denial_reason_is_a_known_code(self) -> None:
        broker, _ = _broker()
        decision = broker.mediate(ToolCallRequest("nope", "1.0"))
        self.assertIn(decision.reason_code, REASON_CODES)

    def test_statuses_vocabulary(self) -> None:
        decision = ToolMediationDecision(status=STATUS_DENIED, reason_code=CODE_UNKNOWN_TOOL, tool_id=None, version=None)
        self.assertFalse(decision.allowed)
        self.assertIn(decision.status, (STATUS_ALLOWED, STATUS_DENIED))


if __name__ == "__main__":
    unittest.main()
