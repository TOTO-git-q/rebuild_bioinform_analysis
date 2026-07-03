"""Tests for the inert capability-grant descriptor registry.

Proves no risky capability becomes executable and that deny-over-allow holds.
"""

import unittest

from auto_bioinfo.adapters.capability_registry import (
    DECISION_DENY,
    DECISION_ELIGIBLE_FOR_MANUAL_APPROVAL,
    assert_no_executable_grants,
    build_capability_registry,
    grant_by_id,
    grant_descriptors,
    resolve_decision,
)


class DescriptorTest(unittest.TestCase):
    def test_registry_non_empty(self):
        self.assertGreaterEqual(len(grant_descriptors()), 5)

    def test_no_grant_is_executable(self):
        self.assertTrue(assert_no_executable_grants())
        for grant in grant_descriptors():
            self.assertFalse(grant.is_executable(), grant.grant_id)
            self.assertFalse(grant.executable_by_default, grant.grant_id)

    def test_unknown_grant_raises(self):
        with self.assertRaises(KeyError):
            grant_by_id("no_such_grant")

    def test_build_registry_is_pure_data(self):
        registry = build_capability_registry()
        self.assertTrue(assert_no_executable_grants(registry))
        sample = registry["grant_remote_exec"]
        self.assertFalse(sample["executable_by_default"])
        self.assertIn("missing_cost_limit", sample["denial_defaults"])


class DecisionTest(unittest.TestCase):
    def test_missing_binding_denies(self):
        d = resolve_decision("grant_network_query_plan", provided_bindings=(), allow_intent=True)
        self.assertEqual(d["decision"], DECISION_DENY)
        self.assertFalse(d["executable"])

    def test_deny_reason_beats_allow_intent(self):
        # All bindings present, caller wants allow, but a deny reason is present.
        d = resolve_decision(
            "grant_network_query_plan",
            provided_bindings=("project_id", "tool_id", "query_hash", "caller_id"),
            deny_reasons=("sensitive_argument",),
            allow_intent=True,
        )
        self.assertEqual(d["decision"], DECISION_DENY)
        self.assertIn("sensitive_argument", d["reasons"])
        self.assertFalse(d["executable"])

    def test_default_deny_without_allow_intent(self):
        d = resolve_decision(
            "grant_network_query_plan",
            provided_bindings=("project_id", "tool_id", "query_hash", "caller_id"),
            allow_intent=False,
        )
        self.assertEqual(d["decision"], DECISION_DENY)

    def test_best_case_is_manual_approval_never_execute(self):
        d = resolve_decision(
            "grant_network_query_plan",
            provided_bindings=("project_id", "tool_id", "query_hash", "caller_id"),
            allow_intent=True,
        )
        self.assertEqual(d["decision"], DECISION_ELIGIBLE_FOR_MANUAL_APPROVAL)
        self.assertFalse(d["executable"])
        # There is no "execute"/"granted" decision anywhere.
        self.assertNotIn(d["decision"], {"execute", "granted", "run"})


if __name__ == "__main__":
    unittest.main()
