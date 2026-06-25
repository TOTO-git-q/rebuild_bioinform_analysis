import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.core import state
from auto_bioinfo.core.store import init_project_state, load_events, load_project_state, transition_state


class StateMachineTest(unittest.TestCase):
    def test_main_sequence_is_acyclic_and_complete(self):
        # every main stage (except COMPLETED) advances to its successor
        for i, s in enumerate(state.MAIN_SEQUENCE[:-1]):
            self.assertIn(state.MAIN_SEQUENCE[i + 1], state.allowed_next_stages(s))

    def test_terminals_have_no_exits(self):
        for t in state.TERMINAL_STAGES:
            self.assertEqual(state.allowed_next_stages(t), [])

    def test_every_working_stage_can_stop_safely(self):
        for s in state.MAIN_SEQUENCE[:-1]:
            self.assertIn("INSUFFICIENT_DATA", state.allowed_next_stages(s))

    def test_legal_transition_and_event_logged(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            transition_state(p, "QUESTION_RESOLVED", "QUESTION_RESOLVED", "actor", [], "ok")
            self.assertEqual(load_project_state(p)["current_stage"], "QUESTION_RESOLVED")
            self.assertTrue(any(e["next_stage"] == "QUESTION_RESOLVED" for e in load_events(p)))

    def test_illegal_transition_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            with self.assertRaises(ValueError):
                transition_state(p, "REPORT_READY", "x", "actor", [], "skip ahead")

    def test_state_rebuildable_from_events(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            transition_state(p, "QUESTION_RESOLVED", "QUESTION_RESOLVED", "a", [], "ok")
            events = load_events(p)
            last_stage = [e["next_stage"] for e in events if e["next_stage"]][-1]
            self.assertEqual(last_stage, load_project_state(p)["current_stage"])


if __name__ == "__main__":
    unittest.main()
