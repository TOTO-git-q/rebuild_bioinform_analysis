"""WP-04c / T-04-03: main state enum, transition registry, and guard interface.

These tests pin the new domain-layer state-machine foundation in
:mod:`auto_bioinfo.core.state_machine`:

- the bounded :class:`MainState` enum stays in lock-step with the canonical
  ``state.STAGES`` table and serialises deterministically;
- the :class:`TransitionRegistry` lookups/listings are deterministic and reject
  malformed/duplicate registrations with stable error *codes*;
- the guard interface returns structured allow/deny :class:`GuardResult` objects
  (never a bare boolean), and every illegal transition is classified by a stable
  code; and
- the whole slice is side-effect free (no project file is ever created).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.core import state
from auto_bioinfo.core.state_machine import (
    CODE_ALLOWED,
    CODE_DUPLICATE_TRANSITION,
    CODE_GUARD_DENIED,
    CODE_MALFORMED_GUARD_RESULT,
    CODE_MALFORMED_TRANSITION,
    CODE_UNKNOWN_SOURCE_STATE,
    CODE_UNKNOWN_TARGET_STATE,
    CODE_UNREGISTERED_TRANSITION,
    ERROR_CODES,
    GuardResult,
    IllegalTransitionError,
    MainState,
    Transition,
    TransitionRegistrationError,
    TransitionRegistry,
    UnknownStateError,
    allow,
    coerce_main_state,
    deny,
    is_main_state,
    serialize_main_state,
    validate_main_state,
)


class MainStateEnumTest(unittest.TestCase):
    def test_enum_mirrors_canonical_state_table_exactly(self):
        # The enum is derived from the single source of truth; no divergent
        # second vocabulary is introduced.
        self.assertEqual([m.value for m in MainState], list(state.STAGES))
        self.assertEqual({m.name for m in MainState}, set(state.STAGES))

    def test_member_compares_equal_to_canonical_string(self):
        self.assertEqual(MainState.INTAKE, "INTAKE")
        self.assertEqual(MainState.INTAKE.value, "INTAKE")

    def test_serialize_main_state_is_deterministic_canonical_string(self):
        self.assertEqual(serialize_main_state(MainState.QUESTION_RESOLVED), "QUESTION_RESOLVED")
        self.assertEqual(serialize_main_state("QUESTION_RESOLVED"), "QUESTION_RESOLVED")

    def test_is_main_state_accepts_member_and_string_rejects_unknown(self):
        self.assertTrue(is_main_state(MainState.COMPLETED))
        self.assertTrue(is_main_state("COMPLETED"))
        self.assertFalse(is_main_state("NOT_A_STAGE"))
        self.assertFalse(is_main_state(None))
        self.assertFalse(is_main_state(123))

    def test_coerce_main_state_rejects_unknown_with_code(self):
        self.assertIs(coerce_main_state("INTAKE"), MainState.INTAKE)
        with self.assertRaises(UnknownStateError) as ctx:
            coerce_main_state("NOPE")
        self.assertEqual(ctx.exception.code, CODE_UNKNOWN_SOURCE_STATE)

    def test_validate_main_state_returns_error_list(self):
        self.assertEqual(validate_main_state("INTAKE"), [])
        errors = validate_main_state("NOPE", "current_stage")
        self.assertEqual(len(errors), 1)
        self.assertIn("current_stage", errors[0])


class TransitionRegistryDeterminismTest(unittest.TestCase):
    def _registry(self) -> TransitionRegistry:
        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", label="resolve question")
        reg.register("INTAKE", "FAILED")
        reg.register("QUESTION_RESOLVED", "SCOPE_RESOLVED")
        return reg

    def test_register_returns_normalised_transition(self):
        reg = TransitionRegistry()
        t = reg.register(MainState.INTAKE, MainState.QUESTION_RESOLVED)
        self.assertIsInstance(t, Transition)
        self.assertEqual((t.source, t.target), ("INTAKE", "QUESTION_RESOLVED"))
        self.assertEqual(t.key, ("INTAKE", "QUESTION_RESOLVED"))

    def test_targets_are_sorted_and_deterministic(self):
        reg = self._registry()
        self.assertEqual(reg.targets("INTAKE"), ["FAILED", "QUESTION_RESOLVED"])
        self.assertEqual(reg.targets("INTAKE"), reg.targets("INTAKE"))
        self.assertEqual(reg.targets("COMPLETED"), [])

    def test_transitions_listing_is_sorted_by_edge(self):
        reg = self._registry()
        listed = [(t.source, t.target) for t in reg.transitions()]
        self.assertEqual(listed, sorted(listed))
        self.assertEqual(len(reg), 3)

    def test_membership_and_lookup(self):
        reg = self._registry()
        self.assertTrue(reg.is_registered("INTAKE", "QUESTION_RESOLVED"))
        self.assertIn(("INTAKE", "FAILED"), reg)
        self.assertNotIn(("INTAKE", "COMPLETED"), reg)
        self.assertNotIn("not-a-tuple", reg)
        self.assertIsNone(reg.get("INTAKE", "COMPLETED"))
        self.assertEqual(reg.get("INTAKE", "QUESTION_RESOLVED").label, "resolve question")

    def test_sources_listing_is_sorted(self):
        reg = self._registry()
        self.assertEqual(reg.sources(), ["INTAKE", "QUESTION_RESOLVED"])

    def test_from_table_mirrors_canonical_linear_table(self):
        # Reuse of the existing state table proves the abstraction handles the
        # real edges without inventing a divergent vocabulary. The canonical
        # table has no self-loops, so every edge is registered faithfully — none
        # is silently dropped.
        self.assertFalse(
            any(t == s for s, ts in state.LINEAR_NEXT.items() for t in ts),
            "canonical LINEAR_NEXT unexpectedly contains a self-loop",
        )
        reg = TransitionRegistry.from_table(state.LINEAR_NEXT)
        expected = sum(1 for _s, ts in state.LINEAR_NEXT.items() for _t in ts)
        self.assertEqual(len(reg), expected)
        for source, targets in state.LINEAR_NEXT.items():
            for target in targets:
                self.assertTrue(reg.is_registered(source, target))

    def test_from_table_rejects_self_loop_failing_closed(self):
        # A malformed input table is never normalised into success: a self-loop
        # fails closed with the same stable code direct register() raises.
        with self.assertRaises(TransitionRegistrationError) as ctx:
            TransitionRegistry.from_table({"INTAKE": ["INTAKE"]})
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_TRANSITION)

    def test_from_table_rejects_unknown_state_failing_closed(self):
        with self.assertRaises(TransitionRegistrationError) as ctx:
            TransitionRegistry.from_table({"INTAKE": ["NOT_A_STAGE"]})
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_TRANSITION)


class TransitionRegistrationRejectionTest(unittest.TestCase):
    def test_duplicate_registration_rejected_with_code(self):
        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED")
        with self.assertRaises(TransitionRegistrationError) as ctx:
            reg.register("INTAKE", "QUESTION_RESOLVED")
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_TRANSITION)
        self.assertEqual(len(reg), 1)  # the duplicate did not register

    def test_unknown_source_registration_rejected_as_malformed(self):
        reg = TransitionRegistry()
        with self.assertRaises(TransitionRegistrationError) as ctx:
            reg.register("NOT_A_STAGE", "INTAKE")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_TRANSITION)

    def test_unknown_target_registration_rejected_as_malformed(self):
        reg = TransitionRegistry()
        with self.assertRaises(TransitionRegistrationError) as ctx:
            reg.register("INTAKE", "NOT_A_STAGE")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_TRANSITION)

    def test_self_loop_registration_rejected_as_malformed(self):
        reg = TransitionRegistry()
        with self.assertRaises(TransitionRegistrationError) as ctx:
            reg.register("INTAKE", "INTAKE")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_TRANSITION)


class GuardEvaluationTest(unittest.TestCase):
    def test_allowed_transition_returns_structured_allow(self):
        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", label="ok")
        result = reg.evaluate("INTAKE", "QUESTION_RESOLVED")
        self.assertIsInstance(result, GuardResult)
        self.assertTrue(result.allowed)
        self.assertEqual(result.code, CODE_ALLOWED)
        self.assertEqual((result.source, result.target), ("INTAKE", "QUESTION_RESOLVED"))

    def test_unknown_source_state_denied_with_code(self):
        reg = TransitionRegistry()
        result = reg.evaluate("NOT_A_STAGE", "INTAKE")
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, CODE_UNKNOWN_SOURCE_STATE)

    def test_unknown_target_state_denied_with_code(self):
        reg = TransitionRegistry()
        result = reg.evaluate("INTAKE", "NOT_A_STAGE")
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, CODE_UNKNOWN_TARGET_STATE)

    def test_unregistered_transition_denied_with_code(self):
        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED")
        result = reg.evaluate("INTAKE", "REPORT_READY")
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, CODE_UNREGISTERED_TRANSITION)

    def test_guard_denial_uses_default_code_and_pins_edge(self):
        def reject(transition: Transition, context) -> GuardResult:
            return deny(CODE_GUARD_DENIED, "policy says no")

        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", guard=reject)
        result = reg.evaluate("INTAKE", "QUESTION_RESOLVED")
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, CODE_GUARD_DENIED)
        self.assertEqual((result.source, result.target), ("INTAKE", "QUESTION_RESOLVED"))

    def test_guard_can_allow_based_on_context(self):
        def gated(transition: Transition, context) -> GuardResult:
            if context.get("ready"):
                return allow(transition.source, transition.target)
            return deny(CODE_GUARD_DENIED, "not ready")

        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", guard=gated)
        self.assertFalse(reg.evaluate("INTAKE", "QUESTION_RESOLVED").allowed)
        self.assertTrue(reg.evaluate("INTAKE", "QUESTION_RESOLVED", {"ready": True}).allowed)

    def test_guard_denial_without_code_is_normalised(self):
        # A guard that forgets to set a code still yields a stable GUARD_DENIED.
        def lazy(transition: Transition, context) -> GuardResult:
            return GuardResult(allowed=False, code="", detail="nope")

        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", guard=lazy)
        result = reg.evaluate("INTAKE", "QUESTION_RESOLVED")
        self.assertEqual(result.code, CODE_GUARD_DENIED)

    def test_guard_returning_bool_fails_closed_with_stable_code(self):
        # A guard that returns a bare bool (instead of a GuardResult) must fail
        # closed with a stable code, never raise a bare AttributeError.
        def bad_bool(transition: Transition, context):
            return True

        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", guard=bad_bool)
        result = reg.evaluate("INTAKE", "QUESTION_RESOLVED")
        self.assertIsInstance(result, GuardResult)
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, CODE_MALFORMED_GUARD_RESULT)
        self.assertEqual((result.source, result.target), ("INTAKE", "QUESTION_RESOLVED"))

    def test_guard_returning_non_guardresult_fails_closed(self):
        # Any non-GuardResult return (here None) is rejected, not trusted.
        def bad_none(transition: Transition, context):
            return None

        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", guard=bad_none)
        result = reg.evaluate("INTAKE", "QUESTION_RESOLVED")
        self.assertFalse(result.allowed)
        self.assertEqual(result.code, CODE_MALFORMED_GUARD_RESULT)

    def test_assert_allowed_raises_stable_code_on_malformed_guard(self):
        # The raise-style API also fails closed (not AttributeError) on a
        # malformed guard return.
        def bad_bool(transition: Transition, context):
            return True

        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", guard=bad_bool)
        with self.assertRaises(IllegalTransitionError) as ctx:
            reg.assert_allowed("INTAKE", "QUESTION_RESOLVED")
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_GUARD_RESULT)

    def test_every_denial_code_is_a_declared_error_code(self):
        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED")
        for src, tgt in (("NOPE", "INTAKE"), ("INTAKE", "NOPE"), ("INTAKE", "REPORT_READY")):
            result = reg.evaluate(src, tgt)
            self.assertIn(result.code, ERROR_CODES)

    def test_guard_result_to_dict_round_trip(self):
        result = deny(CODE_UNREGISTERED_TRANSITION, "x", source="A", target="B")
        self.assertEqual(
            result.to_dict(),
            {"allowed": False, "code": CODE_UNREGISTERED_TRANSITION, "detail": "x", "source": "A", "target": "B"},
        )


class AssertAllowedTest(unittest.TestCase):
    def test_assert_allowed_returns_transition_on_success(self):
        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED", label="ok")
        transition = reg.assert_allowed("INTAKE", "QUESTION_RESOLVED")
        self.assertEqual((transition.source, transition.target), ("INTAKE", "QUESTION_RESOLVED"))

    def test_assert_allowed_raises_with_stable_code(self):
        reg = TransitionRegistry()
        reg.register("INTAKE", "QUESTION_RESOLVED")
        with self.assertRaises(IllegalTransitionError) as ctx:
            reg.assert_allowed("INTAKE", "REPORT_READY")
        self.assertEqual(ctx.exception.code, CODE_UNREGISTERED_TRANSITION)


class SideEffectFreeTest(unittest.TestCase):
    def test_registry_and_guard_checks_write_nothing(self):
        # The whole slice is pure: building a registry from the canonical table
        # and evaluating transitions must not create or modify any file under a
        # project directory.
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj"
            project_dir.mkdir()
            reg = TransitionRegistry.from_table(state.LINEAR_NEXT)
            reg.evaluate("INTAKE", "QUESTION_RESOLVED")
            reg.evaluate("INTAKE", "REPORT_READY")
            reg.evaluate("NOPE", "INTAKE")
            try:
                reg.assert_allowed("INTAKE", "REPORT_READY")
            except IllegalTransitionError:
                pass
            # No state/ directory, no object files — nothing was written.
            self.assertEqual(list(project_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
