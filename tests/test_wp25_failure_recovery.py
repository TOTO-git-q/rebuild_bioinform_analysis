"""Unit tests for the WP-25 failure-recovery layer.

Covers, over synthetic in-memory facts (no clock, no network, no persistence):

- failure taxonomy: exactly 12 classes; scientific/design failures non-retryable;
  error-code mapping; unknown code fails closed to INTERNAL_ERROR;
- retry policy: retryable within budget schedules a deterministic backoff; a
  non-retryable class escalates; max-attempts / time-budget / scope-budget each
  exhaust; no infinite retry; backoff is deterministic;
- rerun planner: a partial failure blocks only descendants and keeps independent
  paths continuable; an invalidation re-runs only correct descendants; cycles /
  unknown deps fail closed;
- replan engine: REPLAN preserves the prior plan; RECONFIRM_REQUIRED on scope /
  method changes; override cannot fabricate PASS or drop a finding; terminal needs
  reason + evidence.
"""

import unittest

from auto_bioinfo.ops import failure_taxonomy as ft
from auto_bioinfo.ops import replan as rpl
from auto_bioinfo.ops import rerun_planner as rr
from auto_bioinfo.ops import retry_policy as rt


class FailureTaxonomyTests(unittest.TestCase):
    def test_exactly_twelve_classes(self):
        self.assertEqual(len(ft.FAILURE_CLASSES), 12)

    def test_scientific_failures_non_retryable(self):
        for code in (ft.CLASS_METHOD_NOT_APPLICABLE, ft.CLASS_SCIENTIFIC_INFEASIBLE, ft.CLASS_VALIDATION_FAILED):
            self.assertFalse(ft.is_retryable(code))

    def test_transient_failures_retryable(self):
        for code in (ft.CLASS_NETWORK_TRANSIENT, ft.CLASS_RATE_LIMITED, ft.CLASS_WORKER_INTERRUPTED, ft.CLASS_TIMEOUT):
            self.assertTrue(ft.is_retryable(code))

    def test_error_code_mapping(self):
        self.assertEqual(ft.classify_error_code("HTTP_429").code, ft.CLASS_RATE_LIMITED)
        self.assertEqual(ft.classify_error_code("oom_killed").code, ft.CLASS_RESOURCE_EXHAUSTED)
        self.assertEqual(ft.classify_error_code("QC_FAILED").code, ft.CLASS_VALIDATION_FAILED)

    def test_unknown_code_fails_closed(self):
        cls = ft.classify_error_code("SOMETHING_WEIRD")
        self.assertEqual(cls.code, ft.CLASS_INTERNAL_ERROR)
        self.assertFalse(cls.retryable)
        self.assertEqual(ft.classify_error_code(None).code, ft.CLASS_INTERNAL_ERROR)

    def test_resolution_paths_bounded(self):
        for cls in ft.FAILURE_CLASSES.values():
            self.assertIn(cls.resolution_path, ft.RESOLUTION_PATHS)


class RetryPolicyTests(unittest.TestCase):
    def test_retryable_within_budget_schedules(self):
        d = rt.decide_retry(
            rt.RetryRequest(failure_class=ft.CLASS_NETWORK_TRANSIENT, attempt=1, elapsed_seconds=0.0),
            policy=rt.RetryPolicy(),
        )
        self.assertTrue(d.should_retry)
        self.assertGreater(d.delay_seconds, 0.0)

    def test_non_retryable_escalates(self):
        d = rt.decide_retry(
            rt.RetryRequest(failure_class=ft.CLASS_METHOD_NOT_APPLICABLE, attempt=1),
            policy=rt.RetryPolicy(),
        )
        self.assertEqual(d.status, rt.STATUS_ESCALATE)
        self.assertEqual(d.reason_code, rt.CODE_NON_RETRYABLE)
        self.assertEqual(d.resolution_path, ft.PATH_TERMINAL)

    def test_max_attempts_exhausts(self):
        d = rt.decide_retry(
            rt.RetryRequest(failure_class=ft.CLASS_NETWORK_TRANSIENT, attempt=5),
            policy=rt.RetryPolicy(max_attempts=5),
        )
        self.assertEqual(d.status, rt.STATUS_EXHAUSTED)
        self.assertEqual(d.reason_code, rt.CODE_MAX_ATTEMPTS)

    def test_time_budget_exhausts(self):
        d = rt.decide_retry(
            rt.RetryRequest(failure_class=ft.CLASS_NETWORK_TRANSIENT, attempt=1, elapsed_seconds=4000.0),
            policy=rt.RetryPolicy(total_time_budget_seconds=3600.0),
        )
        self.assertEqual(d.reason_code, rt.CODE_TIME_BUDGET)

    def test_scope_budget_exhausts(self):
        budget = rt.RetryBudget(per_tool=2, spent={"tool:blast": 2})
        d = rt.decide_retry(
            rt.RetryRequest(failure_class=ft.CLASS_RATE_LIMITED, attempt=1, tool="blast"),
            policy=rt.RetryPolicy(),
            budget=budget,
        )
        self.assertEqual(d.reason_code, rt.CODE_SCOPE_BUDGET)

    def test_no_infinite_retry(self):
        # simulate a loop: every attempt must terminate within max_attempts
        policy = rt.RetryPolicy(max_attempts=4)
        attempt = 1
        retries = 0
        while retries < 100:
            d = rt.decide_retry(rt.RetryRequest(failure_class=ft.CLASS_TIMEOUT, attempt=attempt), policy=policy)
            if not d.should_retry:
                break
            attempt += 1
            retries += 1
        self.assertFalse(d.should_retry)
        self.assertLess(attempt, 100)

    def test_backoff_deterministic_and_capped(self):
        policy = rt.RetryPolicy(base_delay_seconds=1.0, multiplier=2.0, max_delay_seconds=10.0, jitter_fraction=0.0)
        self.assertEqual(rt.compute_backoff(policy, 1), 1.0)
        self.assertEqual(rt.compute_backoff(policy, 2), 2.0)
        self.assertEqual(rt.compute_backoff(policy, 5), 10.0)  # capped
        # jitter deterministic
        jp = rt.RetryPolicy(jitter_fraction=0.5)
        self.assertEqual(rt.compute_backoff(jp, 2, seed="x"), rt.compute_backoff(jp, 2, seed="x"))

    def test_malformed_fails_closed(self):
        self.assertEqual(rt.decide_retry(object(), policy=rt.RetryPolicy()).reason_code, rt.CODE_MALFORMED_REQUEST)
        self.assertEqual(rt.decide_retry(rt.RetryRequest(failure_class="NOPE", attempt=1), policy=rt.RetryPolicy()).reason_code, rt.CODE_MALFORMED_REQUEST)
        self.assertEqual(
            rt.decide_retry(rt.RetryRequest(failure_class=ft.CLASS_TIMEOUT, attempt=1), policy=rt.RetryPolicy(max_attempts=0)).reason_code,
            rt.CODE_MALFORMED_POLICY,
        )


def _diamond_graph():
    # a -> b, a -> c, b -> d, c -> d ; plus an independent node e
    return rr.build_graph(
        [
            rr.TaskNode("a"),
            rr.TaskNode("b", depends_on=("a",)),
            rr.TaskNode("c", depends_on=("a",)),
            rr.TaskNode("d", depends_on=("b", "c")),
            rr.TaskNode("e"),
        ]
    )


class RerunPlannerTests(unittest.TestCase):
    def test_partial_failure_isolates(self):
        plan = rr.plan_partial_failure(_diamond_graph(), ["b"])
        self.assertEqual(plan.blocked, ("b", "d"))
        self.assertIn("e", plan.continuable)
        self.assertIn("a", plan.continuable)
        self.assertIn("c", plan.continuable)

    def test_independent_path_not_cancelled(self):
        plan = rr.plan_partial_failure(_diamond_graph(), ["e"])
        self.assertEqual(plan.blocked, ("e",))
        self.assertNotIn("a", plan.blocked)

    def test_rerun_only_descendants(self):
        plan = rr.plan_rerun(_diamond_graph(), ["a"])
        self.assertEqual(set(plan.invalidated), {"a", "b", "c", "d"})
        self.assertEqual(plan.preserved, ("e",))

    def test_rerun_leaf_change_minimal(self):
        plan = rr.plan_rerun(_diamond_graph(), ["d"])
        self.assertEqual(plan.invalidated, ("d",))
        self.assertEqual(set(plan.preserved), {"a", "b", "c", "e"})

    def test_unknown_node_fails_closed(self):
        self.assertEqual(rr.plan_partial_failure(_diamond_graph(), ["zzz"]).reason_code, rr.CODE_UNKNOWN_NODE)
        self.assertEqual(rr.plan_rerun(_diamond_graph(), ["zzz"]).reason_code, rr.CODE_UNKNOWN_NODE)

    def test_cycle_rejected(self):
        with self.assertRaises(rr.TaskGraphError):
            rr.build_graph([rr.TaskNode("x", depends_on=("y",)), rr.TaskNode("y", depends_on=("x",))])

    def test_unknown_dependency_rejected(self):
        with self.assertRaises(rr.TaskGraphError):
            rr.build_graph([rr.TaskNode("x", depends_on=("missing",))])


class ReplanEngineTests(unittest.TestCase):
    def test_replan_preserves_prior_plan(self):
        d = rpl.plan_replan(rpl.ReplanRequest(triggering_problem="QC failed on batch effect", rollback_stage="EVIDENCE_PLANNED", prior_plan_ref="plan://v1"))
        self.assertTrue(d.ok)
        self.assertTrue(d.record["prior_plan_preserved"])
        self.assertEqual(d.record["prior_plan_ref"], "plan://v1")

    def test_replan_rejects_terminal_rollback(self):
        d = rpl.plan_replan(rpl.ReplanRequest(triggering_problem="x", rollback_stage="COMPLETED"))
        self.assertEqual(d.status, rpl.STATUS_INVALID)

    def test_reconfirm_required_on_scope_change(self):
        d = rpl.evaluate_reconfirm([rpl.CHANGE_SCOPE, rpl.CHANGE_METHOD])
        self.assertEqual(d.status, rpl.STATUS_RECONFIRM_REQUIRED)
        confirmed = rpl.evaluate_reconfirm([rpl.CHANGE_SCOPE], confirmed=True)
        self.assertTrue(confirmed.ok)

    def test_reconfirm_unknown_category_fails_closed(self):
        self.assertEqual(rpl.evaluate_reconfirm(["frobnicate"]).status, rpl.STATUS_INVALID)

    def test_override_cannot_fabricate_pass(self):
        d = rpl.evaluate_override(rpl.OverrideRequest(target_item="qc_threshold", policy_allows=frozenset({"qc_threshold"}), sets_pass=True))
        self.assertEqual(d.reason_code, rpl.CODE_OVERRIDE_FORBIDDEN_PASS)

    def test_override_cannot_drop_finding(self):
        d = rpl.evaluate_override(rpl.OverrideRequest(target_item="qc_threshold", policy_allows=frozenset({"qc_threshold"}), drops_finding=True))
        self.assertEqual(d.reason_code, rpl.CODE_OVERRIDE_DROPS_FINDING)

    def test_override_out_of_policy_rejected(self):
        d = rpl.evaluate_override(rpl.OverrideRequest(target_item="secret_flag", policy_allows=frozenset({"qc_threshold"})))
        self.assertEqual(d.reason_code, rpl.CODE_OVERRIDE_OUT_OF_POLICY)

    def test_override_allowed_preserves_finding(self):
        d = rpl.evaluate_override(rpl.OverrideRequest(target_item="qc_threshold", policy_allows=frozenset({"qc_threshold"}), justification="reviewer note"))
        self.assertTrue(d.ok)
        self.assertTrue(d.record["original_finding_preserved"])

    def test_terminal_needs_reason_and_evidence(self):
        self.assertEqual(
            rpl.decide_terminal(rpl.TerminalRequest(kind="INSUFFICIENT_DATA", reason="", evidence_refs=["e1"])).reason_code, rpl.CODE_TERMINAL_MISSING_REASON
        )
        self.assertEqual(
            rpl.decide_terminal(rpl.TerminalRequest(kind="INSUFFICIENT_DATA", reason="no donors", evidence_refs=[])).reason_code,
            rpl.CODE_TERMINAL_MISSING_EVIDENCE,
        )
        ok = rpl.decide_terminal(rpl.TerminalRequest(kind="INSUFFICIENT_DATA", reason="no donor-level data", evidence_refs=["evidence://1"]))
        self.assertTrue(ok.ok)

    def test_terminal_unknown_kind(self):
        self.assertEqual(rpl.decide_terminal(rpl.TerminalRequest(kind="COMPLETED", reason="x", evidence_refs=["e"])).reason_code, rpl.CODE_UNKNOWN_TERMINAL)


if __name__ == "__main__":
    unittest.main()
