import json
import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.core import state, store
from auto_bioinfo.core.store import (
    init_project_state,
    load_events,
    load_project_state,
    load_state,
    rebuild_state,
    transition_state,
)
from auto_bioinfo.ports import EventStorePort


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


class ProjectionRebuildTest(unittest.TestCase):
    """WP-03a: the projection must be reconstructable from the event log alone."""

    @staticmethod
    def _without_updated_at(state_dict):
        # updated_at is a live wall-clock stamp on the snapshot; the rebuilt
        # projection pins it to the last event, so it is excluded from equality.
        return {k: v for k, v in state_dict.items() if k != "updated_at"}

    def _advance(self, p):
        init_project_state(p, "q")
        for nxt in ("QUESTION_RESOLVED", "SCOPE_RESOLVED", "EVIDENCE_PLANNED"):
            transition_state(p, nxt, nxt, "actor", [], "ok")

    def test_rebuild_state_matches_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            self.assertEqual(
                self._without_updated_at(rebuild_state(p)),
                self._without_updated_at(load_project_state(p)),
            )

    def test_rebuild_state_recovers_full_stage_history(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            self.assertEqual(
                rebuild_state(p)["stage_history"],
                ["INTAKE", "QUESTION_RESOLVED", "SCOPE_RESOLVED", "EVIDENCE_PLANNED"],
            )

    def test_rebuild_state_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            self.assertEqual(rebuild_state(p), rebuild_state(p))

    def test_event_log_is_authoritative_over_tampered_snapshot(self):
        # The append-only log — not the JSON snapshot — is the source of truth.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            snapshot_path = p / "state" / "project_state.json"
            tampered = load_project_state(p)
            tampered["current_stage"] = "COMPLETED"
            tampered["stage_history"] = ["INTAKE", "COMPLETED"]
            snapshot_path.write_text(json.dumps(tampered), encoding="utf-8")
            # load_project_state trusts the tampered file; load_state replays the log.
            self.assertEqual(load_project_state(p)["current_stage"], "COMPLETED")
            self.assertEqual(load_state(p)["current_stage"], "EVIDENCE_PLANNED")
            self.assertEqual(
                load_state(p)["stage_history"],
                ["INTAKE", "QUESTION_RESOLVED", "SCOPE_RESOLVED", "EVIDENCE_PLANNED"],
            )

    def test_rebuild_state_rejects_empty_log(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            (p / "state").mkdir(parents=True)
            with self.assertRaises(ValueError):
                rebuild_state(p)

    def test_store_module_satisfies_event_store_port(self):
        # The JSONL adapter must expose the EventStorePort surface, including the
        # load_state projection operation the port declares.
        for name in ("append_event", "load_events", "load_state"):
            self.assertTrue(callable(getattr(store, name)))
        self.assertIn("load_state", dir(EventStorePort))


if __name__ == "__main__":
    unittest.main()
