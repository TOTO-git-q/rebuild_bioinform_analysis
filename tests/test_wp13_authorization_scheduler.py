"""WP-13 tests: execution authorization, preflight, and scheduling."""

from __future__ import annotations

import dataclasses
import unittest
from types import MappingProxyType

from auto_bioinfo.execution.authorization import (
    AUTH_APPROVAL_REQUIRED,
    AUTH_AUTHORIZED,
    AUTH_BLOCKED,
    CAT_INPUT_INTEGRITY,
    CHECK_FAIL,
    AuthorizationRequest,
    authorize_execution,
    run_preflight,
)
from auto_bioinfo.execution.scheduler import (
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_DELIVERED,
    SchedulableTask,
    Scheduler,
    TransactionalOutbox,
    tasks_from_workflow_plan,
)
from auto_bioinfo.methods.compatibility import build_method_plan
from auto_bioinfo.methods.contract_registry import build_default_registry
from auto_bioinfo.workflow.dag_compiler import compile_workflow


def _compiled():
    reg = build_default_registry()
    profile = {
        "dataset_id": "ds_bulk",
        "modality": "bulk_expression_matrix",
        "statistical_unit": "sample",
        "group_sizes": {"a": 3, "b": 3},
        "present_metadata": ["sample_group_labels"],
    }
    sq = {"subquestion_id": "subquestion_a", "claim_ceiling": "association"}
    method_plan, _ = build_method_plan(reg, profile, sq, evidence_plan_id="ep", candidate_method_ids=["bulk_deg"])
    plans = [{"subquestion": sq, "method_plan": method_plan, "manifest_inputs": ["artifact_input_counts"]}]
    return reg, compile_workflow(reg, plans, project_id="proj1")


def _base_request(result, **overrides):
    facts = {
        "artifact_input_counts": {"state": "VALID", "checksum_sha256": "a" * 64, "expected_checksum_sha256": "a" * 64, "exists": True},
    }
    impl = {"bulk_deg": {"code_commit": "abc123", "container_digest": "sha256:deadbeef"}}
    kwargs = dict(
        project_id="proj1",
        workflow_plan=result.workflow_plan,
        task_packets=result.task_packets,
        artifact_facts=facts,
        implementation_facts=impl,
        resource_status={"cpu_available": 8, "memory_mb_available": 16000},
        policy={"execution_mode": "TEST", "data_sensitivity": "unspecified", "network_policy": {"egress": "deny"}},
    )
    kwargs.update(overrides)
    return AuthorizationRequest(**kwargs)


class PreflightTest(unittest.TestCase):
    def setUp(self):
        _, self.result = _compiled()

    def test_clean_request_authorized(self):
        auth = authorize_execution(_base_request(self.result), plan_hash=self.result.plan_hash)
        self.assertEqual(auth.decision, AUTH_AUTHORIZED)
        self.assertTrue(auth.authorized)
        self.assertTrue(all(auth.authorizes(t) for t in self.result.workflow_plan["task_ids"]))

    def test_checksum_mismatch_blocks(self):
        facts = {"artifact_input_counts": {"state": "VALID", "checksum_sha256": "a" * 64, "expected_checksum_sha256": "b" * 64}}
        auth = authorize_execution(_base_request(self.result, artifact_facts=facts))
        self.assertEqual(auth.decision, AUTH_BLOCKED)
        codes = {f["category"] for f in auth.preflight["findings"] if f["status"] == CHECK_FAIL}
        self.assertIn(CAT_INPUT_INTEGRITY, codes)

    def test_missing_input_artifact_blocks(self):
        auth = authorize_execution(_base_request(self.result, artifact_facts={}))
        self.assertEqual(auth.decision, AUTH_BLOCKED)

    def test_floating_digest_blocks(self):
        impl = {"bulk_deg": {"code_commit": "abc", "container_digest": "latest"}}
        auth = authorize_execution(_base_request(self.result, implementation_facts=impl))
        self.assertEqual(auth.decision, AUTH_BLOCKED)

    def test_egress_on_sensitive_blocks(self):
        # Force an analysis packet to request egress under a deny policy.
        packets = [dict(p) for p in self.result.task_packets]
        for p in packets:
            fields = dict(p.get("execution_fields", {}))
            fields["network_policy"] = {"egress": "allow"}
            p["execution_fields"] = fields
        auth = authorize_execution(_base_request(self.result, task_packets=packets))
        self.assertEqual(auth.decision, AUTH_BLOCKED)

    def test_write_scope_escape_blocks(self):
        packets = [dict(p) for p in self.result.task_packets]
        for p in packets:
            fields = dict(p.get("execution_fields", {}))
            fields["write_scope"] = "/etc/"
            p["execution_fields"] = fields
        auth = authorize_execution(_base_request(self.result, task_packets=packets))
        self.assertEqual(auth.decision, AUTH_BLOCKED)

    def test_missing_approval_gate(self):
        auth = authorize_execution(_base_request(self.result, required_gates=frozenset({"G-E"}), granted_gates=frozenset()))
        self.assertEqual(auth.decision, AUTH_APPROVAL_REQUIRED)
        self.assertEqual(auth.authorized_task_ids, ())

    def test_granted_approval_authorizes(self):
        auth = authorize_execution(_base_request(self.result, required_gates=frozenset({"G-E"}), granted_gates=frozenset({"G-E"})))
        self.assertEqual(auth.decision, AUTH_AUTHORIZED)

    def test_snapshot_deterministic_and_immutable(self):
        a1 = authorize_execution(_base_request(self.result), plan_hash=self.result.plan_hash)
        a2 = authorize_execution(_base_request(self.result), plan_hash=self.result.plan_hash)
        self.assertEqual(a1.to_dict(), a2.to_dict())
        self.assertTrue(a1.snapshot_hash)

    def test_preflight_report_shape(self):
        report = run_preflight(_base_request(self.result))
        self.assertIn("counts", report.to_dict())


class AuthorizationImmutabilityTest(unittest.TestCase):
    """A minted authorization snapshot cannot be tampered with after the fact."""

    def setUp(self):
        _, self.result = _compiled()
        self.auth = authorize_execution(_base_request(self.result), plan_hash=self.result.plan_hash)
        self.assertEqual(self.auth.decision, AUTH_AUTHORIZED)

    def test_decision_field_assignment_is_rejected(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.auth.decision = AUTH_BLOCKED  # type: ignore[misc]
        self.assertEqual(self.auth.decision, AUTH_AUTHORIZED)

    def test_authorized_task_ids_cannot_add_or_remove_authority(self):
        self.assertIsInstance(self.auth.authorized_task_ids, tuple)
        # No in-place mutation of the stored collection.
        with self.assertRaises(AttributeError):
            self.auth.authorized_task_ids.append("evil")  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            self.auth.authorized_task_ids.clear()  # type: ignore[attr-defined]
        # No reassignment of the field itself.
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.auth.authorized_task_ids = ("evil",)  # type: ignore[misc]
        self.assertFalse(self.auth.authorizes("evil"))
        # A previously-authorized task stays authorized (nothing was removed).
        for tid in self.result.workflow_plan["task_ids"]:
            self.assertTrue(self.auth.authorizes(tid))

    def test_object_versions_and_preflight_facts_are_read_only(self):
        self.assertIsInstance(self.auth.object_versions, MappingProxyType)
        with self.assertRaises(TypeError):
            self.auth.object_versions["plan_hash"] = "tampered"  # type: ignore[index]
        self.assertIsInstance(self.auth.preflight, MappingProxyType)
        with self.assertRaises(TypeError):
            self.auth.preflight["failed"] = True  # type: ignore[index]
        # Nested containers are frozen too — no append/insert through them.
        with self.assertRaises(AttributeError):
            self.auth.preflight["findings"].append({})  # type: ignore[attr-defined]

    def test_granted_gates_and_reasons_are_immutable(self):
        self.assertIsInstance(self.auth.granted_gates, tuple)
        self.assertIsInstance(self.auth.reasons, tuple)
        with self.assertRaises(AttributeError):
            self.auth.reasons.append("x")  # type: ignore[attr-defined]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.auth.granted_gates = ("forged",)  # type: ignore[misc]

    def test_to_dict_returns_defensive_copies(self):
        d = self.auth.to_dict()
        d["decision"] = AUTH_BLOCKED
        d["authorized_task_ids"].append("evil")
        d["object_versions"]["plan_hash"] = "tampered"
        d["preflight"]["findings"].append({"forged": True})
        # None of that reached back into the snapshot.
        self.assertEqual(self.auth.decision, AUTH_AUTHORIZED)
        self.assertNotIn("evil", self.auth.authorized_task_ids)
        self.assertNotEqual(self.auth.object_versions.get("plan_hash"), "tampered")
        self.assertFalse(self.auth.authorizes("evil"))

    def test_scheduler_cannot_be_tricked_by_post_hoc_snapshot_mutation(self):
        # A BLOCKED snapshot authorizes nothing; attacker tries to grant authority
        # by mutating it, then loads a scheduler from it.
        blocked = authorize_execution(_base_request(self.result, artifact_facts={}))
        self.assertEqual(blocked.decision, AUTH_BLOCKED)
        tasks = tasks_from_workflow_plan(self.result.workflow_plan, project_id="proj1", authorization_id=blocked.authorization_id)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            blocked.decision = AUTH_AUTHORIZED  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            blocked.authorized_task_ids.append(tasks[0].task_id)  # type: ignore[attr-defined]
        sched = Scheduler()
        sched.load_authorization(tasks, blocked)
        self.assertEqual(sched.dispatch_all(), [])


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        _, self.result = _compiled()
        self.auth = authorize_execution(_base_request(self.result), plan_hash=self.result.plan_hash)
        self.tasks = tasks_from_workflow_plan(self.result.workflow_plan, project_id="proj1", authorization_id=self.auth.authorization_id)

    def test_only_ready_nodes_delivered_first(self):
        sched = Scheduler()
        sched.load_authorization(self.tasks, self.auth)
        # Only the data-prep node (no deps) is ready first.
        first = sched.dispatch()
        self.assertEqual(len(first), 1)
        prep_task = first[0].task_id
        # An analysis node with an unmet dep must not be delivered yet.
        self.assertNotIn(TASK_DELIVERED, [sched.state(t.task_id) for t in self.tasks if t.task_id != prep_task])

    def test_message_carries_only_ids(self):
        sched = Scheduler()
        sched.load_authorization(self.tasks, self.auth)
        msg = sched.dispatch()[0]
        d = msg.to_dict()
        self.assertEqual(set(d), {"message_id", "task_id", "task_version", "project_id", "authorization_id", "trace_id"})

    def test_full_drive_delivers_all_dependency_first(self):
        sched = Scheduler()
        sched.load_authorization(self.tasks, self.auth)
        delivered = sched.dispatch_all()
        self.assertEqual(len(delivered), len(self.tasks))
        self.assertTrue(all(sched.state(t.task_id) == TASK_COMPLETED for t in self.tasks))

    def test_unauthorized_task_never_delivered(self):
        # An authorization that authorizes nothing (blocked) must deliver nothing.
        blocked = authorize_execution(_base_request(self.result, artifact_facts={}))
        sched = Scheduler()
        sched.load_authorization(self.tasks, blocked)
        self.assertEqual(sched.dispatch_all(), [])

    def test_cancel_stops_successors(self):
        sched = Scheduler()
        sched.load_authorization(self.tasks, self.auth)
        prep = sched.dispatch()[0].task_id
        sched.cancel(prep)
        # Successors of the cancelled prep never become ready.
        delivered = sched.dispatch_all()
        self.assertEqual(delivered, [])
        self.assertEqual(sched.state(prep), TASK_CANCELLED)

    def test_pause_resume_project(self):
        sched = Scheduler()
        sched.load_authorization(self.tasks, self.auth)
        sched.pause_project("proj1")
        self.assertEqual(sched.dispatch(), [])
        sched.resume_project("proj1")
        self.assertEqual(len(sched.dispatch()), 1)

    def test_duplicate_dispatch_idempotent(self):
        sched = Scheduler()
        sched.load_authorization(self.tasks, self.auth)
        first = sched.dispatch()
        # A second dispatch without completing the first delivers nothing new.
        again = sched.dispatch()
        self.assertEqual(len(first), 1)
        self.assertEqual(again, [])

    def test_outbox_rollback_delivers_nothing(self):
        outbox = TransactionalOutbox()
        from auto_bioinfo.execution.scheduler import QueueMessage

        outbox.stage(QueueMessage("m1", "t1", "1", "proj1", "auth1", "trace"))
        outbox.rollback()
        self.assertEqual(outbox.commit(), [])
        self.assertEqual(outbox.queue(), [])

    def test_project_fairness(self):
        # Two projects, per-project cap 1, concurrency 4: each project gets one.
        sched = Scheduler(max_concurrency=4, per_project_concurrency=1)
        sched.add_task(SchedulableTask("t_a", "projA"))
        sched.add_task(SchedulableTask("t_b", "projB"))
        sched.add_task(SchedulableTask("t_a2", "projA"))
        delivered = sched.dispatch()
        projects = {m.project_id for m in delivered}
        self.assertEqual(projects, {"projA", "projB"})
        self.assertEqual(len(delivered), 2)


if __name__ == "__main__":
    unittest.main()
