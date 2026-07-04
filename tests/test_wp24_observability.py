"""Unit tests for the WP-24 observability layer (audit query + run panel).

Covers, over in-memory event lists (no filesystem, no clock, no network):

- audit query: filter by project / actor / event-type / stage / object-type /
  tool-call dimensions; redaction of sensitive payload; malformed events reported
  in ``skipped`` (never silently dropped); pagination; determinism;
- run panel: current-stage / waiting-reason / next-action projection for active,
  paused, completed, and stopped projects; per-task attempt reconstruction (each
  attempt distinguishable, retry reason surfaced); review queue derived from
  request/decision events; empty-log handling.
"""

import copy
import unittest

from auto_bioinfo.observability import audit_query as aq
from auto_bioinfo.observability import run_panel as rp


def _ev(**kw):
    base = {
        "event_id": kw.get("event_id", "e"),
        "project_id": kw.get("project_id", "proj1"),
        "event_type": kw.get("event_type", "GENERIC"),
        "actor": kw.get("actor", "system"),
        "created_at": kw.get("created_at", ""),
        "previous_stage": kw.get("previous_stage", ""),
        "next_stage": kw.get("next_stage", "INTAKE"),
        "message": kw.get("message", ""),
        "object_refs": kw.get("object_refs", []),
        "payload_hash": "h",
        "payload": kw.get("payload", {}),
    }
    return base


def _pipeline_events():
    stages = [
        ("PROJECT_STATE_INITIALIZED", "", "INTAKE"),
        ("QUESTION_RESOLVED", "INTAKE", "QUESTION_RESOLVED"),
        ("SCOPE_RESOLVED", "QUESTION_RESOLVED", "SCOPE_RESOLVED"),
    ]
    return [_ev(event_id=f"e{i}", event_type=t, previous_stage=p, next_stage=n) for i, (t, p, n) in enumerate(stages)]


class AuditQueryTests(unittest.TestCase):
    def test_empty_filter_matches_all(self):
        events = _pipeline_events()
        page = aq.query_audit(events)
        self.assertEqual(page.total, 3)
        self.assertEqual(page.returned, 3)

    def test_filter_by_actor_and_type(self):
        events = [_ev(event_id="a", actor="alice", event_type="X"), _ev(event_id="b", actor="bob", event_type="Y")]
        page = aq.query_audit(events, aq.AuditFilter(actor="alice"))
        self.assertEqual(page.total, 1)
        self.assertEqual(page.records[0].actor, "alice")
        self.assertEqual(aq.query_audit(events, aq.AuditFilter(event_type="Y")).total, 1)

    def test_filter_by_object_ref(self):
        events = [
            _ev(event_id="a", object_refs=[{"object_type": "QCReport", "object_id": "qc1"}]),
            _ev(event_id="b", object_refs=[{"object_type": "Claim", "object_id": "c1"}]),
        ]
        page = aq.query_audit(events, aq.AuditFilter(object_type="QCReport"))
        self.assertEqual(page.total, 1)
        self.assertEqual(aq.query_audit(events, aq.AuditFilter(object_id="c1")).total, 1)

    def test_tool_call_filter(self):
        events = [
            _ev(event_id="a", event_type="TOOL_CALL", payload={"tool": "blast", "provider": "ncbi", "prompt_version": "v3"}),
            _ev(event_id="b", event_type="TOOL_CALL", payload={"tool": "star", "provider": "internal", "prompt_version": "v3"}),
            _ev(event_id="c", event_type="GENERIC", payload={"note": "no tool"}),
        ]
        page = aq.query_tool_calls(events, provider="ncbi")
        self.assertEqual(page.total, 1)
        self.assertEqual(page.records[0].payload["tool"], "blast")
        vp = aq.query_tool_calls(events, prompt_version="v3")
        self.assertEqual(vp.total, 2)

    def test_payload_redacted(self):
        events = [_ev(event_id="a", payload={"api_key": "supersecretvalue123", "note": "ok"})]
        page = aq.query_audit(events)
        self.assertEqual(page.records[0].payload["api_key"], "***REDACTED***")
        self.assertEqual(page.records[0].payload["note"], "ok")

    def test_malformed_event_skipped_not_dropped(self):
        events = [_ev(event_id="a"), {"not": "an event"}, "garbage"]
        page = aq.query_audit(events)
        self.assertEqual(page.total, 1)
        self.assertEqual(len(page.skipped), 2)

    def test_pagination(self):
        events = [_ev(event_id=f"e{i}", event_type="X") for i in range(5)]
        page = aq.query_audit(events, limit=2, offset=1)
        self.assertEqual(page.total, 5)
        self.assertEqual([r.event_id for r in page.records], ["e1", "e2"])

    def test_bad_pagination_raises(self):
        with self.assertRaises(aq.AuditQueryError):
            aq.query_audit([_ev()], offset=-1)
        with self.assertRaises(aq.AuditQueryError):
            aq.query_audit("not a list")

    def test_deterministic(self):
        events = _pipeline_events()
        self.assertEqual(aq.query_audit(events).to_dict(), aq.query_audit(events).to_dict())

    def test_summary(self):
        events = [_ev(actor="a", event_type="X"), _ev(actor="a", event_type="Y"), _ev(actor="b", event_type="X"), {"bad": 1}]
        summary = aq.audit_summary(events)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["by_event_type"], {"X": 2, "Y": 1})
        self.assertEqual(summary["by_actor"], {"a": 2, "b": 1})

    def test_inputs_not_mutated(self):
        events = _pipeline_events()
        before = copy.deepcopy(events)
        aq.query_audit(events, aq.AuditFilter(actor="system"))
        self.assertEqual(events, before)


class RunPanelStatusTests(unittest.TestCase):
    def test_active_project(self):
        s = rp.project_status(_pipeline_events())
        self.assertEqual(s.run_status, rp.RUN_ACTIVE)
        self.assertEqual(s.current_stage, "SCOPE_RESOLVED")
        self.assertFalse(s.is_terminal)
        self.assertTrue(s.next_action)

    def test_completed_project(self):
        events = _pipeline_events() + [_ev(event_id="done", previous_stage="REPORT_READY", next_stage="COMPLETED")]
        s = rp.project_status(events)
        self.assertEqual(s.run_status, rp.RUN_COMPLETED)
        self.assertTrue(s.is_terminal)
        self.assertEqual(s.next_action, "")

    def test_paused_project(self):
        events = _pipeline_events() + [_ev(event_id="pause", next_stage="HUMAN_REVIEW_REQUIRED")]
        s = rp.project_status(events)
        self.assertEqual(s.run_status, rp.RUN_PAUSED)
        self.assertTrue(s.is_paused)
        self.assertIn("human", s.waiting_reason.lower())

    def test_stopped_project(self):
        events = _pipeline_events() + [_ev(event_id="stop", next_stage="INSUFFICIENT_DATA")]
        s = rp.project_status(events)
        self.assertEqual(s.run_status, rp.RUN_STOPPED)
        self.assertTrue(s.is_terminal)

    def test_empty_log(self):
        s = rp.project_status([])
        self.assertEqual(s.run_status, rp.RUN_EMPTY)

    def test_status_vocab_bounded(self):
        s = rp.project_status(_pipeline_events())
        self.assertIn(s.run_status, rp.RUN_STATUSES)

    def test_non_list_raises(self):
        with self.assertRaises(rp.RunPanelError):
            rp.project_status("nope")


class RunPanelTaskAttemptTests(unittest.TestCase):
    def test_attempts_distinguishable(self):
        events = [
            _ev(
                event_id="t1",
                event_type="TASK_FAILED",
                object_refs=[{"object_type": "TaskRun", "object_id": "task-a"}],
                payload={"attempt": 1, "retry_reason": "network timeout"},
            ),
            _ev(
                event_id="t2",
                event_type="TASK_FAILED",
                object_refs=[{"object_type": "TaskRun", "object_id": "task-a"}],
                payload={"attempt": 2, "retry_reason": "rate limited"},
            ),
            _ev(event_id="t3", event_type="TASK_SUCCEEDED", object_refs=[{"object_type": "TaskRun", "object_id": "task-a"}], payload={"attempt": 3}),
        ]
        attempts = rp.task_attempts(events, task_id="task-a")
        self.assertEqual([a.attempt for a in attempts], [1, 2, 3])
        self.assertEqual(attempts[0].retry_reason, "network timeout")
        self.assertEqual(attempts[2].outcome, "TASK_SUCCEEDED")

    def test_attempt_counter_when_no_payload(self):
        events = [
            _ev(event_id="t1", event_type="TASK_RAN", payload={"task_id": "b"}),
            _ev(event_id="t2", event_type="TASK_RAN", payload={"task_id": "b"}),
        ]
        attempts = rp.task_attempts(events)
        self.assertEqual([a.attempt for a in attempts], [1, 2])

    def test_ignores_non_task_events(self):
        self.assertEqual(rp.task_attempts(_pipeline_events()), ())


class RunPanelReviewQueueTests(unittest.TestCase):
    def test_pending_until_decided(self):
        events = [
            _ev(event_id="r1", event_type="APPROVAL_REQUESTED", object_refs=[{"object_type": "Claim", "object_id": "claim-1"}]),
            _ev(event_id="r2", event_type="APPROVAL_REQUESTED", object_refs=[{"object_type": "QCReport", "object_id": "qc-1"}]),
            _ev(event_id="r3", event_type="APPROVAL_GRANTED", object_refs=[{"object_type": "Claim", "object_id": "claim-1"}]),
        ]
        queue = rp.review_queue(events)
        self.assertEqual([r.object_id for r in queue], ["qc-1"])

    def test_full_panel_assembles(self):
        events = _pipeline_events() + [
            _ev(
                event_id="r1",
                event_type="APPROVAL_REQUESTED",
                previous_stage="SCOPE_RESOLVED",
                next_stage="SCOPE_RESOLVED",
                object_refs=[{"object_type": "Claim", "object_id": "claim-1"}],
            ),
        ]
        panel = rp.run_panel(events)
        self.assertEqual(panel["status"]["current_stage"], "SCOPE_RESOLVED")
        self.assertEqual(len(panel["review_queue"]), 1)
        self.assertIn("main_sequence", panel)


if __name__ == "__main__":
    unittest.main()
