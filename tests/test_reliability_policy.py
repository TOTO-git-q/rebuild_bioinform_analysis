"""Unit tests for the local gateway reliability policy contract (WP-05i / T-05-09).

Covers, for the offline, deterministic, inert reliability-policy foundation:

- an under-limit synthetic provider/tool request is allowed with a bounded decision
  projection,
- a timeout-exceeded request is not allowed (denied),
- a rate-limit-exceeded request is not allowed (denied),
- a cost-budget-exceeded request escalates to ``need_human_review`` (never auto-allow),
- an open circuit / failure-threshold breach blocks the request (denied), while a
  permitted half-open recovery probe is allowed,
- malformed limits/facts, negative/non-finite numbers, missing bindings, unknown
  units/states, missing-limit pairings, inconsistent circuits, and bypass/authority
  flags fail closed with deterministic reason codes and **no allow**,
- decisions / projections are deterministic and expose no prompt content, raw input,
  raw output, tool arguments, credentials, or secrets,
- the evaluator introduces no filesystem / project-state / event / queue / DB / log /
  report / subprocess / network / provider-tool / clock / sleep / global-registry side
  effect and mutates neither input.

All fixtures are tiny synthetic values (fake ids, ``estimated_cost_units=3``,
``max_cost_units=10``, ``request_count=2``, ``max_requests=5``, ``elapsed_ms=12``) — no
real human-derived data, secret, credential, real model output, real billing data, or
real timing telemetry.  The whole module is offline and deterministic: no network,
subprocess, provider SDK, credential access, real clock, or content egress.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from auto_bioinfo.agent_gateway.reliability_policy import (
    CIRCUIT_CLOSED,
    CIRCUIT_HALF_OPEN,
    CIRCUIT_OPEN,
    CODE_AMBIGUOUS_RATE_WINDOW,
    CODE_BUDGET_EXCEEDED,
    CODE_CIRCUIT_OPEN,
    CODE_FORBIDDEN_AUTHORITY,
    CODE_INCONSISTENT_CIRCUIT,
    CODE_MALFORMED_BINDING,
    CODE_MALFORMED_CALL_IDENTITY,
    CODE_MALFORMED_FACT,
    CODE_MALFORMED_LIMIT,
    CODE_MALFORMED_POLICY,
    CODE_MALFORMED_REFERENCE,
    CODE_MALFORMED_REQUEST,
    CODE_MISSING_BINDING,
    CODE_MISSING_CALL_IDENTITY,
    CODE_MISSING_LIMIT,
    CODE_RATE_LIMIT_EXCEEDED,
    CODE_TIMEOUT_EXCEEDED,
    CODE_UNKNOWN_STATE,
    CODE_UNKNOWN_UNIT,
    DIMENSION_BUDGET,
    DIMENSION_CIRCUIT,
    DIMENSION_RATE,
    DIMENSION_TIMEOUT,
    MAX_COST_UNITS,
    MAX_DURATION_MS,
    REASON_CODES,
    STATUS_ALLOWED,
    STATUS_DENIED,
    STATUS_NEED_HUMAN_REVIEW,
    STATUS_REJECTED,
    ReliabilityDecision,
    ReliabilityPolicy,
    ReliabilityRequest,
    evaluate_reliability,
)


def _policy(**overrides) -> ReliabilityPolicy:
    """A small synthetic policy covering every dimension with sensible defaults."""
    kwargs = {
        "max_duration_ms": 1_000,
        "max_requests": 5,
        "rate_window": "w-1m",
        "max_cost_units": 10,
        "cost_unit": "credits",
        "failure_threshold": 3,
        "allow_recovery_probe": False,
    }
    kwargs.update(overrides)
    return ReliabilityPolicy(**kwargs)


def _request(**overrides) -> ReliabilityRequest:
    """A small synthetic, under-every-limit request with sensible defaults."""
    kwargs = {
        "project_id": "proj-001",
        "correlation_id": "corr-001",
        "call_id": "call-001",
        "provider": "fake-local",
        "elapsed_ms": 12,
        "request_count": 2,
        "window": "w-1m",
        "estimated_cost_units": 3,
        "consumed_cost_units": 1,
        "cost_unit": "credits",
        "circuit_state": CIRCUIT_CLOSED,
        "recent_failure_count": 0,
    }
    kwargs.update(overrides)
    return ReliabilityRequest(**kwargs)


class AllowedTest(unittest.TestCase):
    def test_under_limit_request_is_allowed(self):
        decision = evaluate_reliability(_policy(), _request())
        self.assertIsInstance(decision, ReliabilityDecision)
        self.assertEqual(decision.status, STATUS_ALLOWED)
        self.assertIsNone(decision.reason_code)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.project_id, "proj-001")
        self.assertEqual(decision.call_id, "call-001")
        self.assertEqual(
            set(decision.engaged_dimensions),
            {DIMENSION_TIMEOUT, DIMENSION_RATE, DIMENSION_BUDGET, DIMENSION_CIRCUIT},
        )
        self.assertTrue(decision.decision_id.startswith("reliability_"))

    def test_allow_is_deterministic(self):
        first = evaluate_reliability(_policy(), _request())
        second = evaluate_reliability(_policy(), _request())
        self.assertEqual(first.decision_id, second.decision_id)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_policy_shaped_mapping_is_accepted(self):
        decision = evaluate_reliability(
            {"max_requests": 5, "rate_window": "w-1m"},
            _request(request_count=2, window="w-1m", elapsed_ms=None, estimated_cost_units=None, consumed_cost_units=None, circuit_state=None, recent_failure_count=None),
        )
        self.assertEqual(decision.status, STATUS_ALLOWED)
        self.assertEqual(decision.engaged_dimensions, (DIMENSION_RATE,))

    def test_only_one_engaged_dimension_when_only_one_limit(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(max_cost_units=10, cost_unit="credits"),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k", estimated_cost_units=3),
        )
        self.assertEqual(decision.status, STATUS_ALLOWED)
        self.assertEqual(decision.engaged_dimensions, (DIMENSION_BUDGET,))

    def test_estimated_duration_used_when_no_elapsed(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(max_duration_ms=100),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k", estimated_duration_ms=50),
        )
        self.assertEqual(decision.status, STATUS_ALLOWED)


class TimeoutTest(unittest.TestCase):
    def test_timeout_exceeded_is_denied(self):
        decision = evaluate_reliability(_policy(max_duration_ms=10), _request(elapsed_ms=12))
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_TIMEOUT_EXCEEDED)
        self.assertFalse(decision.allowed)

    def test_estimated_duration_over_timeout_is_denied(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(max_duration_ms=10),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k", estimated_duration_ms=99),
        )
        self.assertEqual(decision.reason_code, CODE_TIMEOUT_EXCEEDED)


class RateLimitTest(unittest.TestCase):
    def test_rate_limit_exceeded_is_denied(self):
        decision = evaluate_reliability(_policy(max_requests=5), _request(request_count=6))
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_RATE_LIMIT_EXCEEDED)

    def test_request_count_equal_to_limit_is_allowed(self):
        decision = evaluate_reliability(_policy(max_requests=5), _request(request_count=5))
        self.assertEqual(decision.status, STATUS_ALLOWED)


class RateWindowPairingTest(unittest.TestCase):
    """An engaged rate-limit decision must be made against an unambiguous window.

    A request count is only meaningful relative to the bounded window it was counted
    in, so a ``w-1m`` policy must never be satisfied by a ``w-1h`` count, by a count
    with no declared window, or by a policy that declares no window at all.  Every
    such ambiguity fails closed; only a matching window pair under ``max_requests``
    is allowed.
    """

    def _rate_only_policy(self, **overrides):
        kwargs = {"max_requests": 5, "rate_window": "w-1m"}
        kwargs.update(overrides)
        return ReliabilityPolicy(**kwargs)

    def _rate_only_request(self, **overrides):
        kwargs = {"project_id": "p", "correlation_id": "c", "call_id": "k", "request_count": 2, "window": "w-1m"}
        kwargs.update(overrides)
        return ReliabilityRequest(**kwargs)

    def test_mismatched_windows_fail_closed(self):
        decision = evaluate_reliability(self._rate_only_policy(), self._rate_only_request(window="w-1h"))
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_AMBIGUOUS_RATE_WINDOW)
        self.assertFalse(decision.allowed)

    def test_policy_window_with_missing_request_window_fails_closed(self):
        decision = evaluate_reliability(self._rate_only_policy(), self._rate_only_request(window=None))
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_AMBIGUOUS_RATE_WINDOW)

    def test_request_window_with_missing_policy_window_fails_closed(self):
        decision = evaluate_reliability(self._rate_only_policy(rate_window=None), self._rate_only_request())
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_AMBIGUOUS_RATE_WINDOW)

    def test_rate_engaged_without_any_window_fails_closed(self):
        decision = evaluate_reliability(
            self._rate_only_policy(rate_window=None), self._rate_only_request(window=None)
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_AMBIGUOUS_RATE_WINDOW)

    def test_matching_windows_remain_allowed_under_limit(self):
        decision = evaluate_reliability(self._rate_only_policy(), self._rate_only_request())
        self.assertEqual(decision.status, STATUS_ALLOWED)
        self.assertEqual(decision.engaged_dimensions, (DIMENSION_RATE,))

    def test_matching_windows_still_deny_over_limit(self):
        decision = evaluate_reliability(self._rate_only_policy(), self._rate_only_request(request_count=6))
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_RATE_LIMIT_EXCEEDED)


class BudgetTest(unittest.TestCase):
    def test_cost_budget_exceeded_needs_human_review(self):
        decision = evaluate_reliability(_policy(max_cost_units=10), _request(estimated_cost_units=8, consumed_cost_units=5))
        self.assertEqual(decision.status, STATUS_NEED_HUMAN_REVIEW)
        self.assertEqual(decision.reason_code, CODE_BUDGET_EXCEEDED)
        self.assertTrue(decision.needs_human_review)
        self.assertFalse(decision.allowed)

    def test_estimate_alone_over_budget_needs_human_review(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(max_cost_units=10, cost_unit="credits"),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k", estimated_cost_units=11, cost_unit="credits"),
        )
        self.assertEqual(decision.status, STATUS_NEED_HUMAN_REVIEW)
        self.assertEqual(decision.reason_code, CODE_BUDGET_EXCEEDED)

    def test_projected_exactly_at_budget_is_allowed(self):
        decision = evaluate_reliability(_policy(max_cost_units=10), _request(estimated_cost_units=6, consumed_cost_units=4))
        self.assertEqual(decision.status, STATUS_ALLOWED)

    def test_budget_review_isolated_from_other_dimensions(self):
        # Only the budget dimension is engaged: an over-budget request must surface
        # as need_human_review, never as a silent allow or a deny.
        decision = evaluate_reliability(
            ReliabilityPolicy(max_cost_units=5),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k", consumed_cost_units=9),
        )
        self.assertEqual(decision.engaged_dimensions, (DIMENSION_BUDGET,))
        self.assertEqual(decision.status, STATUS_NEED_HUMAN_REVIEW)


class CircuitTest(unittest.TestCase):
    def test_open_circuit_is_denied(self):
        decision = evaluate_reliability(_policy(), _request(circuit_state=CIRCUIT_OPEN, recent_failure_count=1))
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_CIRCUIT_OPEN)

    def test_failure_threshold_reached_blocks(self):
        decision = evaluate_reliability(
            _policy(failure_threshold=3),
            _request(circuit_state=CIRCUIT_HALF_OPEN, recent_failure_count=3),
        )
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_CIRCUIT_OPEN)

    def test_half_open_without_probe_is_denied(self):
        decision = evaluate_reliability(
            _policy(failure_threshold=3, allow_recovery_probe=False),
            _request(circuit_state=CIRCUIT_HALF_OPEN, recent_failure_count=0),
        )
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_CIRCUIT_OPEN)

    def test_half_open_with_probe_is_allowed(self):
        decision = evaluate_reliability(
            _policy(failure_threshold=3, allow_recovery_probe=True),
            _request(circuit_state=CIRCUIT_HALF_OPEN, recent_failure_count=1),
        )
        self.assertEqual(decision.status, STATUS_ALLOWED)

    def test_closed_circuit_with_tripped_count_is_inconsistent(self):
        decision = evaluate_reliability(
            _policy(failure_threshold=3),
            _request(circuit_state=CIRCUIT_CLOSED, recent_failure_count=5),
        )
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertEqual(decision.reason_code, CODE_INCONSISTENT_CIRCUIT)


class DenyPrecedenceTest(unittest.TestCase):
    def test_timeout_deny_precedes_budget_review(self):
        # A request that is both over-timeout and over-budget is denied (never silently
        # allowed); the deterministic precedence puts the hard deny first.
        decision = evaluate_reliability(
            _policy(max_duration_ms=10, max_cost_units=10),
            _request(elapsed_ms=99, estimated_cost_units=99, consumed_cost_units=0),
        )
        self.assertEqual(decision.status, STATUS_DENIED)
        self.assertEqual(decision.reason_code, CODE_TIMEOUT_EXCEEDED)


class FailClosedTest(unittest.TestCase):
    def test_malformed_policy_fails_closed(self):
        self.assertEqual(evaluate_reliability("not-a-policy", _request()).reason_code, CODE_MALFORMED_POLICY)

    def test_unknown_policy_key_fails_closed(self):
        self.assertEqual(evaluate_reliability({"bogus": 1}, _request()).reason_code, CODE_MALFORMED_POLICY)

    def test_malformed_request_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), "not-a-request").reason_code, CODE_MALFORMED_REQUEST)

    def test_unknown_request_key_mapping_fails_closed(self):
        decision = evaluate_reliability(_policy(), {"project_id": "p", "correlation_id": "c", "call_id": "k", "bogus": 1})
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)

    def test_missing_required_mapping_key_fails_closed(self):
        decision = evaluate_reliability(_policy(), {"project_id": "p", "correlation_id": "c"})
        self.assertEqual(decision.reason_code, CODE_MALFORMED_REQUEST)

    def test_missing_binding_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(project_id=None)).reason_code, CODE_MISSING_BINDING)

    def test_malformed_binding_fails_closed(self):
        decision = evaluate_reliability(_policy(), _request(correlation_id="bad\nid"))
        self.assertEqual(decision.reason_code, CODE_MALFORMED_BINDING)

    def test_missing_call_identity_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(call_id=None)).reason_code, CODE_MISSING_CALL_IDENTITY)

    def test_malformed_call_identity_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(call_id="   ")).reason_code, CODE_MALFORMED_CALL_IDENTITY)

    def test_malformed_reference_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(provider="bad\nref")).reason_code, CODE_MALFORMED_REFERENCE)

    def test_negative_fact_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(elapsed_ms=-1)).reason_code, CODE_MALFORMED_FACT)

    def test_non_finite_fact_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(elapsed_ms=float("inf"))).reason_code, CODE_MALFORMED_FACT)

    def test_bool_fact_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(request_count=True)).reason_code, CODE_MALFORMED_FACT)

    def test_non_int_count_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(request_count=2.5)).reason_code, CODE_MALFORMED_FACT)

    def test_negative_limit_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(max_cost_units=-1), _request()).reason_code, CODE_MALFORMED_LIMIT)

    def test_non_int_rate_limit_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(max_requests=5.5), _request()).reason_code, CODE_MALFORMED_LIMIT)

    def test_oversized_limit_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(max_duration_ms=MAX_DURATION_MS + 1), _request()).reason_code, CODE_MALFORMED_LIMIT)

    def test_oversized_cost_fact_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(estimated_cost_units=MAX_COST_UNITS + 1)).reason_code, CODE_MALFORMED_FACT)

    def test_non_bool_recovery_probe_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(allow_recovery_probe="yes"), _request()).reason_code, CODE_MALFORMED_LIMIT)

    def test_unknown_cost_unit_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(cost_unit="bananas"), _request(cost_unit="bananas")).reason_code, CODE_UNKNOWN_UNIT)

    def test_cost_unit_mismatch_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(cost_unit="credits"), _request(cost_unit="tokens")).reason_code, CODE_UNKNOWN_UNIT)

    def test_unknown_circuit_state_fails_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(circuit_state="melting")).reason_code, CODE_UNKNOWN_STATE)

    def test_fact_without_limit_fails_closed(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(max_requests=5),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k", request_count=2, elapsed_ms=12),
        )
        self.assertEqual(decision.reason_code, CODE_MISSING_LIMIT)

    def test_limit_without_fact_fails_closed(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(max_requests=5),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k"),
        )
        self.assertEqual(decision.reason_code, CODE_MISSING_LIMIT)

    def test_empty_policy_fails_closed(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k"),
        )
        self.assertEqual(decision.reason_code, CODE_MISSING_LIMIT)

    def test_partial_circuit_facts_fail_closed(self):
        decision = evaluate_reliability(
            ReliabilityPolicy(failure_threshold=3),
            ReliabilityRequest(project_id="p", correlation_id="c", call_id="k", circuit_state=CIRCUIT_CLOSED),
        )
        self.assertEqual(decision.reason_code, CODE_MISSING_LIMIT)

    def test_truthy_authority_flag_fails_closed(self):
        decision = evaluate_reliability(_policy(), _request(authority_flags={"bypass_gates": True}))
        self.assertEqual(decision.reason_code, CODE_FORBIDDEN_AUTHORITY)

    def test_authority_flag_authorize_real_execution_fails_closed(self):
        decision = evaluate_reliability(_policy(), _request(authority_flags={"authorize_real_execution": 1}))
        self.assertEqual(decision.reason_code, CODE_FORBIDDEN_AUTHORITY)

    def test_all_false_authority_flags_are_allowed(self):
        decision = evaluate_reliability(_policy(), _request(authority_flags={"bypass_gates": False}))
        self.assertEqual(decision.status, STATUS_ALLOWED)

    def test_malformed_authority_flags_fail_closed(self):
        self.assertEqual(evaluate_reliability(_policy(), _request(authority_flags="nope")).reason_code, CODE_MALFORMED_REQUEST)


class ProjectionWithholdsContentTest(unittest.TestCase):
    def test_decision_projection_has_no_content_fields(self):
        decision = evaluate_reliability(_policy(), _request())
        for projection in (decision.to_dict(), decision.audit_projection()):
            for forbidden in ("prompt", "prompt_content", "raw_output", "raw_input", "arguments", "credential", "secret", "api_key"):
                self.assertNotIn(forbidden, projection)
        self.assertTrue(decision.audit_projection()["traceable"])

    def test_projection_is_plain_json_serializable(self):
        decision = evaluate_reliability(_policy(), _request())
        for projection in (decision.to_dict(), decision.audit_projection()):
            self.assertEqual(json.loads(json.dumps(projection))["status"], STATUS_ALLOWED)

    def test_authority_flags_projection_is_keys_only(self):
        # Even on a clean request, the request projection exposes only sorted flag keys,
        # never any value that could carry content.
        request = _request(authority_flags={"bypass_gates": False})
        self.assertEqual(request.to_dict()["authority_flags"], ["bypass_gates"])


class PurityTest(unittest.TestCase):
    def test_decision_is_frozen(self):
        decision = evaluate_reliability(_policy(), _request())
        with self.assertRaises(FrozenInstanceError):
            decision.status = STATUS_REJECTED  # type: ignore[misc]

    def test_inputs_are_not_mutated(self):
        policy = _policy()
        request = _request(authority_flags={"bypass_gates": False})
        before_policy = json.dumps(policy.to_dict(), sort_keys=True)
        before_request = json.dumps(request.to_dict(), sort_keys=True)
        evaluate_reliability(policy, request)
        self.assertEqual(json.dumps(policy.to_dict(), sort_keys=True), before_policy)
        self.assertEqual(json.dumps(request.to_dict(), sort_keys=True), before_request)

    def test_all_reason_codes_unique_and_prefixed(self):
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        self.assertTrue(all(code.startswith("RELIABILITY_") for code in REASON_CODES))

    def test_rejected_decision_has_no_decision_id(self):
        decision = evaluate_reliability("bad", _request())
        self.assertEqual(decision.status, STATUS_REJECTED)
        self.assertIsNone(decision.decision_id)

    def test_module_imports_no_io_surface(self):
        import auto_bioinfo.agent_gateway.reliability_policy as module

        for forbidden in ("socket", "subprocess", "requests", "urllib", "http", "os", "time", "datetime", "random"):
            self.assertNotIn(forbidden, vars(module))


if __name__ == "__main__":
    unittest.main()
