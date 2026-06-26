import json
import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.core import state, store
from auto_bioinfo.core.events import build_event
from auto_bioinfo.core.store import (
    append_event,
    init_project_state,
    load_events,
    load_project_state,
    load_state,
    rebuild_state,
    transition_state,
    verify_projection,
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

    def test_rebuild_state_rejects_invalid_first_event(self):
        # A log whose first record is not the canonical initialization event
        # cannot seed a projection — replay must fail closed, not guess.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            events_path = p / "state" / "events.jsonl"
            lines = events_path.read_text(encoding="utf-8").splitlines()
            forged_first = json.loads(lines[0])
            forged_first["event_type"] = "SOMETHING_ELSE"
            lines[0] = json.dumps(forged_first)
            events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                rebuild_state(p)

    def test_rebuild_state_rejects_unknown_later_next_stage(self):
        # Structurally complete later event with an unknown next_stage must be
        # rejected rather than projected verbatim into current_stage/history.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            forged = build_event(
                project_id=p.name,
                event_type="QUESTION_RESOLVED",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="NOT_A_STAGE",
                message="forged",
            )
            append_event(p, forged)
            with self.assertRaises(ValueError):
                rebuild_state(p)

    def test_rebuild_state_rejects_illegal_transition(self):
        # A later event naming a known but illegal target stage (skipping the
        # linear sequence) must be rejected by the shared transition guard.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            forged = build_event(
                project_id=p.name,
                event_type="JUMP_AHEAD",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="REPORT_READY",
                message="forged",
            )
            append_event(p, forged)
            with self.assertRaises(ValueError):
                rebuild_state(p)

    def test_rebuild_state_rejects_foreign_project_event(self):
        # A later event from a different project_id is a tampered log.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            forged = build_event(
                project_id="other-project",
                event_type="QUESTION_RESOLVED",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="QUESTION_RESOLVED",
                message="forged",
            )
            append_event(p, forged)
            with self.assertRaises(ValueError):
                rebuild_state(p)

    def test_rebuild_state_rejects_previous_stage_mismatch(self):
        # A later event whose previous_stage does not match the projection's
        # current stage indicates a gap/reorder in the log and must fail closed.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            forged = build_event(
                project_id=p.name,
                event_type="SCOPE_RESOLVED",
                actor="actor",
                previous_stage="QUESTION_RESOLVED",
                next_stage="SCOPE_RESOLVED",
                message="forged",
            )
            append_event(p, forged)
            with self.assertRaises(ValueError):
                rebuild_state(p)

    def test_rebuild_state_rejects_forged_same_stage_noop(self):
        # A non-legacy later event whose previous_stage == next_stage is a
        # self-loop the legal write path (validate_transition) can never
        # produce; replay must run the transition guard even for no-ops rather
        # than silently accepting the forged event.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            forged = build_event(
                project_id=p.name,
                event_type="FORGED_NOOP",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="INTAKE",
                message="forged",
            )
            append_event(p, forged)
            with self.assertRaises(ValueError):
                rebuild_state(p)

    def test_store_module_satisfies_event_store_port(self):
        # The JSONL adapter must expose the EventStorePort surface, including the
        # load_state projection operation the port declares.
        for name in ("append_event", "load_events", "load_state"):
            self.assertTrue(callable(getattr(store, name)))
        self.assertIn("load_state", dir(EventStorePort))


class EventIdempotencyKeyTest(unittest.TestCase):
    """WP-03b: explicit idempotency keys make a duplicate append a no-op."""

    def test_build_event_without_key_omits_field(self):
        # Backward compatibility: an event built with no key has no extra field,
        # so existing logs and callers stay byte-for-byte identical.
        event = build_event(
            project_id="p",
            event_type="QUESTION_RESOLVED",
            actor="actor",
            previous_stage="INTAKE",
            next_stage="QUESTION_RESOLVED",
        )
        self.assertNotIn("idempotency_key", event)

    def test_build_event_key_decoupled_from_created_at(self):
        # The key is the caller's token, independent of created_at / event_id:
        # two events built with the same key keep that key even though their
        # wall-clock-derived created_at / event_id differ.
        first = build_event(
            project_id="p",
            event_type="QUESTION_RESOLVED",
            actor="actor",
            previous_stage="INTAKE",
            next_stage="QUESTION_RESOLVED",
            idempotency_key="retry-1",
        )
        second = build_event(
            project_id="p",
            event_type="QUESTION_RESOLVED",
            actor="actor",
            previous_stage="INTAKE",
            next_stage="QUESTION_RESOLVED",
            idempotency_key="retry-1",
        )
        self.assertEqual(first["idempotency_key"], "retry-1")
        self.assertEqual(second["idempotency_key"], "retry-1")
        self.assertNotEqual(first["idempotency_key"], first["created_at"])

    def test_append_event_keyed_duplicate_adds_no_second_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            before = len(load_events(p))
            event = build_event(
                project_id=p.name,
                event_type="QUESTION_RESOLVED",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="QUESTION_RESOLVED",
                idempotency_key="key-A",
            )
            append_event(p, event)
            append_event(p, event)
            self.assertEqual(len(load_events(p)), before + 1)

    def test_append_event_keyed_duplicate_returns_existing(self):
        # Re-appending a keyed event returns the already-recorded event
        # deterministically rather than the second instance.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            first = build_event(
                project_id=p.name,
                event_type="QUESTION_RESOLVED",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="QUESTION_RESOLVED",
                idempotency_key="key-B",
            )
            recorded = append_event(p, first)
            # A distinct second instance carrying the same key must not win.
            second = build_event(
                project_id=p.name,
                event_type="QUESTION_RESOLVED",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="QUESTION_RESOLVED",
                message="different message",
                idempotency_key="key-B",
            )
            returned = append_event(p, second)
            self.assertEqual(returned, recorded)
            self.assertEqual(returned["message"], first["message"])

    def test_append_event_keyless_appends_each_time(self):
        # Without a key the historical append-always behavior is preserved, so
        # the existing init/transition write paths are unaffected.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            before = len(load_events(p))
            event = build_event(
                project_id=p.name,
                event_type="QUESTION_RESOLVED",
                actor="actor",
                previous_stage="INTAKE",
                next_stage="QUESTION_RESOLVED",
            )
            append_event(p, event)
            append_event(p, event)
            self.assertEqual(len(load_events(p)), before + 2)

    def test_distinct_keys_both_append(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            init_project_state(p, "q")
            before = len(load_events(p))
            for key in ("key-1", "key-2"):
                append_event(
                    p,
                    build_event(
                        project_id=p.name,
                        event_type="QUESTION_RESOLVED",
                        actor="actor",
                        previous_stage="INTAKE",
                        next_stage="QUESTION_RESOLVED",
                        idempotency_key=key,
                    ),
                )
            self.assertEqual(len(load_events(p)), before + 2)


class ProjectionDriftTest(unittest.TestCase):
    """WP-03b: detect (never repair) snapshot drift from the event-log projection."""

    def _advance(self, p):
        init_project_state(p, "q")
        for nxt in ("QUESTION_RESOLVED", "SCOPE_RESOLVED", "EVIDENCE_PLANNED"):
            transition_state(p, nxt, nxt, "actor", [], "ok")

    def test_verify_projection_healthy_reports_no_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            self.assertEqual(verify_projection(p), [])

    def test_verify_projection_detects_tampered_stage(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            snapshot_path = p / "state" / "project_state.json"
            tampered = load_project_state(p)
            tampered["current_stage"] = "COMPLETED"
            tampered["stage_history"] = ["INTAKE", "COMPLETED"]
            snapshot_path.write_text(json.dumps(tampered), encoding="utf-8")
            mismatches = verify_projection(p)
            fields = {m["field"] for m in mismatches}
            self.assertIn("current_stage", fields)
            self.assertIn("stage_history", fields)
            stage_mismatch = next(m for m in mismatches if m["field"] == "current_stage")
            self.assertEqual(stage_mismatch["snapshot"], "COMPLETED")
            self.assertEqual(stage_mismatch["rebuilt"], "EVIDENCE_PLANNED")

    def test_verify_projection_does_not_mutate_snapshot_or_log(self):
        # Detection only: the tampered snapshot and the log are left untouched.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            self._advance(p)
            snapshot_path = p / "state" / "project_state.json"
            events_path = p / "state" / "events.jsonl"
            tampered = load_project_state(p)
            tampered["current_stage"] = "FAILED"
            snapshot_path.write_text(json.dumps(tampered), encoding="utf-8")
            snapshot_before = snapshot_path.read_text(encoding="utf-8")
            events_before = events_path.read_text(encoding="utf-8")
            verify_projection(p)
            self.assertEqual(snapshot_path.read_text(encoding="utf-8"), snapshot_before)
            self.assertEqual(events_path.read_text(encoding="utf-8"), events_before)
            # The snapshot is still tampered — verification repaired nothing.
            self.assertEqual(load_project_state(p)["current_stage"], "FAILED")


if __name__ == "__main__":
    unittest.main()
