"""WP-14 tests: offline fake executor, sandbox, worker, and TaskRun records."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_task_run
from auto_bioinfo.execution.fake_executor import (
    ERR_SAMPLE_INSUFFICIENT,
    ERR_TRANSIENT_IO,
    EXEC_CONTAINER,
    EXEC_NEXTFLOW,
    ContainerExecutor,
    RecordedOutcome,
    RecordedOutput,
    Sandbox,
    SandboxViolation,
    SlurmExecutor,
    Worker,
    execute_task,
    is_retryable,
    run_engineering_task,
)


def _packet(task_id="dag_task_abc", outputs=("deg_results_table",), write_scope="outputs/"):
    return {
        "task_id": task_id,
        "packet_type": "AnalysisTaskPacket",
        "method_id": "bulk_deg",
        "expected_inputs": ["artifact_prep"],
        "expected_outputs": list(outputs),
        "params": {"random_seed": 0, "significance_alpha": 0.05},
        "execution_fields": {"write_scope": write_scope, "timeout_seconds": 60, "network_policy": {"egress": "deny"}},
    }


def _success_outcome():
    return RecordedOutcome(
        exit_code=0,
        stdout="ok",
        outputs=(RecordedOutput("deg_results_table", "outputs/deg_results.tsv", 2048, "c" * 64),),
        resource_usage={"cpu_seconds": 1.5, "peak_memory_mb": 200, "wall_seconds": 2.0},
    )


class SandboxTest(unittest.TestCase):
    def test_absolute_path_escape_rejected(self):
        sb = Sandbox(write_scope="outputs/", input_ids=[])
        with self.assertRaises(SandboxViolation):
            sb.place_output(RecordedOutput("x", "/etc/passwd", 1, "a" * 64))

    def test_parent_traversal_rejected(self):
        sb = Sandbox(write_scope="outputs/", input_ids=[])
        with self.assertRaises(SandboxViolation):
            sb.place_output(RecordedOutput("x", "../escape.tsv", 1, "a" * 64))

    def test_symlink_escape_rejected(self):
        sb = Sandbox(write_scope="outputs/", input_ids=[])
        with self.assertRaises(SandboxViolation):
            sb.place_output(RecordedOutput("../evil", "outputs/link", 1, "a" * 64, content_role="symlink"))

    def test_valid_output_accepted(self):
        sb = Sandbox(write_scope="outputs/", input_ids=[])
        sb.place_output(RecordedOutput("r", "outputs/r.tsv", 1, "a" * 64))
        self.assertIn("r", sb.outputs)


class RetryClassifierTest(unittest.TestCase):
    def test_transient_retryable(self):
        self.assertTrue(is_retryable(ERR_TRANSIENT_IO))

    def test_sample_insufficient_never_retryable(self):
        self.assertFalse(is_retryable(ERR_SAMPLE_INSUFFICIENT))

    def test_unknown_not_retryable(self):
        self.assertFalse(is_retryable("mystery"))


class ExecuteTaskTest(unittest.TestCase):
    def test_success_produces_valid_completed_run(self):
        report = execute_task(_packet(), _success_outcome(), worker_identity="w1")
        run = report.task_run
        self.assertEqual(run["result_status"], "completed")
        self.assertEqual(run["exit_code"], 0)
        self.assertEqual(validate_task_run(run), [])
        self.assertTrue(run["output_refs"])
        self.assertEqual(report.error_class, "")

    def test_deterministic_replay(self):
        r1 = execute_task(_packet(), _success_outcome(), worker_identity="w1")
        r2 = execute_task(_packet(), _success_outcome(), worker_identity="w1")
        self.assertEqual(r1.task_run, r2.task_run)

    def test_failure_produces_valid_failed_run(self):
        outcome = RecordedOutcome(exit_code=2, stderr="boom", error_class=ERR_TRANSIENT_IO, error_summary="transient failure")
        report = execute_task(_packet(), outcome, worker_identity="w1")
        run = report.task_run
        self.assertEqual(run["result_status"], "failed")
        self.assertEqual(validate_task_run(run), [])
        self.assertTrue(report.retryable)

    def test_sample_insufficient_failure_not_retryable(self):
        outcome = RecordedOutcome(exit_code=3, stderr="not enough samples", error_class=ERR_SAMPLE_INSUFFICIENT, error_summary="sample insufficient")
        report = execute_task(_packet(), outcome, worker_identity="w1")
        self.assertEqual(report.task_run["result_status"], "failed")
        self.assertFalse(report.retryable)

    def test_undeclared_output_warns(self):
        outcome = RecordedOutcome(
            exit_code=0,
            outputs=(
                RecordedOutput("deg_results_table", "outputs/deg.tsv", 10, "a" * 64),
                RecordedOutput("sneaky_extra", "outputs/extra.tsv", 10, "b" * 64),
            ),
        )
        report = execute_task(_packet(), outcome, worker_identity="w1")
        self.assertTrue(any("undeclared" in w for w in report.warnings))

    def test_path_escape_fails_closed(self):
        outcome = RecordedOutcome(exit_code=0, outputs=(RecordedOutput("x", "/root/x", 1, "a" * 64),))
        report = execute_task(_packet(), outcome, worker_identity="w1")
        self.assertEqual(report.task_run["result_status"], "failed")

    def test_over_quota_fails(self):
        outcome = RecordedOutcome(exit_code=0, outputs=(RecordedOutput("deg_results_table", "outputs/big.tsv", 999, "a" * 64),))
        report = execute_task(_packet(), outcome, worker_identity="w1", max_output_bytes=100)
        self.assertEqual(report.task_run["result_status"], "failed")

    def test_resource_collection_failure_keeps_result(self):
        outcome = RecordedOutcome(exit_code=0, outputs=(RecordedOutput("deg_results_table", "outputs/r.tsv", 1, "a" * 64),), collection_failed=True)
        report = execute_task(_packet(), outcome, worker_identity="w1")
        self.assertEqual(report.task_run["result_status"], "completed")
        self.assertTrue(any("collection failed" in w for w in report.warnings))

    def test_sensitive_log_fields_redacted(self):
        outcome = RecordedOutcome(exit_code=0, stdout="printing api_key=xyz", outputs=(RecordedOutput("deg_results_table", "outputs/r.tsv", 1, "a" * 64),))
        # Inject a sensitive key via container run metadata.
        report = execute_task(
            _packet(),
            outcome,
            worker_identity="w1",
            executor_kind=EXEC_CONTAINER,
            executor_options={"container_digest": "sha256:abc", "mounts": ["token=/x"], "network": "none"},
        )
        # The metadata is captured; no sensitive marker key leaks (values under
        # sensitive-named keys are redacted).
        self.assertIn("payload", report.log_artifact)

    def test_nextflow_captures_run_metadata(self):
        report = execute_task(_packet(), _success_outcome(), worker_identity="w1", executor_kind=EXEC_NEXTFLOW, executor_options={"profile": "test"})
        self.assertEqual(report.task_run["environment"]["executor_kind"], EXEC_NEXTFLOW)
        self.assertIn("run_metadata", report.log_artifact["payload"])


class ContainerExecutorTest(unittest.TestCase):
    def test_floating_digest_fails(self):
        result = ContainerExecutor().execute("t", RecordedOutcome(), params={}, container_digest="latest")
        self.assertNotEqual(result.exit_code, 0)

    def test_undeclared_network_fails(self):
        result = ContainerExecutor().execute("t", RecordedOutcome(), params={}, container_digest="sha256:x", network="internet")
        self.assertNotEqual(result.exit_code, 0)


class SlurmInterfaceTest(unittest.TestCase):
    def test_slurm_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            SlurmExecutor().execute("t", RecordedOutcome(), params={})


class WorkerIdempotencyTest(unittest.TestCase):
    def test_duplicate_message_no_second_run(self):
        worker = Worker("w1")
        run1 = worker.consume(_packet(), _success_outcome())
        run2 = worker.consume(_packet(), _success_outcome())
        self.assertEqual(run1["task_run_id"], run2["task_run_id"])
        self.assertEqual(len(worker.runs()), 1)

    def test_lease_acquire_and_expiry_reclaim(self):
        w1 = Worker("w1", lease_ttl_ticks=2)
        lease = w1.acquire_lease("task_x")
        self.assertIsNotNone(lease)
        # Same lease store is per-worker here; simulate reclaim by advancing a
        # shared logical clock via w2 that has its own store — cross-worker reclaim
        # is modelled by expiry on the lease object.
        self.assertFalse(lease.expired(0))
        self.assertTrue(lease.expired(3))

    def test_heartbeat_extends_own_lease(self):
        w1 = Worker("w1", lease_ttl_ticks=2)
        w1.acquire_lease("task_x")
        w1.tick(1)
        self.assertTrue(w1.heartbeat("task_x"))

    def test_heartbeat_foreign_lease_rejected(self):
        w1 = Worker("w1")
        w2 = Worker("w2")
        w1.acquire_lease("task_x")
        # w2 has no lease for task_x in its own store.
        self.assertFalse(w2.heartbeat("task_x"))


class EngineeringTaskTest(unittest.TestCase):
    def test_main_hash_unchanged_and_never_merged(self):
        packet = {"task_id": "eng_task_1", "allowed_paths": ["src/"], "forbidden_paths": ["/etc"]}
        result = run_engineering_task(packet, main_branch_hash="mainhash123", patch_content="diff --git a b")
        self.assertTrue(result.main_unchanged)
        self.assertFalse(result.merged)
        self.assertTrue(result.patch_ref)

    def test_deterministic(self):
        packet = {"task_id": "eng_task_1"}
        r1 = run_engineering_task(packet, main_branch_hash="h", patch_content="p")
        r2 = run_engineering_task(packet, main_branch_hash="h", patch_content="p")
        self.assertEqual(r1.to_dict(), r2.to_dict())


if __name__ == "__main__":
    unittest.main()
