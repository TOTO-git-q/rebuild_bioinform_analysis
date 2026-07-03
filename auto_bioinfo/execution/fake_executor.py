"""Offline fake executor: Worker / Sandbox / executors / TaskRun (WP-14).

Executes the four TaskPacket kinds against *recorded fixtures* and produces
deterministic, auditable :class:`~auto_bioinfo.core.schemas.TaskRun` records —
with **no** real subprocess, container, Nextflow run, queue, filesystem side
effect, network, or clock read.  A recorded outcome (exit code, captured
stdout/stderr, declared outputs, resource facts, error class) is *replayed*
deterministically, so byte-identical inputs always yield the byte-identical
TaskRun (T-14-01/08/15).  Produced records carry an empty ``created_at`` and pass
:func:`auto_bioinfo.core.validation.validate_task_run`.

The module models a read-only-input / temp-work / scoped-output Sandbox with
path-escape and symlink-escape guards (T-14-03), fake Local / Container /
Nextflow executors plus a reserved Slurm interface (T-14-04..07), a task
lease/heartbeat with logical-clock expiry reclaim (T-14-02), a retry classifier
that never retries a sample-insufficient / incompatible error (T-14-11), output
enumeration that flags undeclared / over-quota writes (T-14-12), controlled log
artifacts with sensitive-field filtering (T-14-13), and an EngineeringTaskPacket
runner that works in an isolated worktree, exports a patch, and never merges —
leaving the main-branch hash unchanged (T-14-14).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.ids import hash_payload, make_stable_id
from ..core.schemas import TaskRun
from ..core.validation import validate_task_run

# --- Bounded executor kinds --------------------------------------------------
EXEC_LOCAL = "local_process"
EXEC_CONTAINER = "container"
EXEC_NEXTFLOW = "nextflow"
EXEC_SLURM = "slurm"
EXECUTOR_KINDS = (EXEC_LOCAL, EXEC_CONTAINER, EXEC_NEXTFLOW, EXEC_SLURM)

# --- Bounded error classes ---------------------------------------------------
# Transient errors a plain retry may fix.
ERR_TRANSIENT_IO = "transient_io"
ERR_BROKER_TIMEOUT = "broker_timeout"
ERR_WORKER_CRASH = "worker_crash"
ERR_LEASE_EXPIRED = "lease_expired"
# Hard errors a retry will never fix (never auto-retried).
ERR_SAMPLE_INSUFFICIENT = "sample_insufficient"
ERR_METHOD_INCOMPATIBLE = "method_incompatible"
ERR_PRECONDITION_FAILED = "precondition_failed"
ERR_PATH_ESCAPE = "path_escape"
ERR_UNDECLARED_OUTPUT = "undeclared_output"
ERR_OUTPUT_QUOTA = "output_quota_exceeded"
ERR_TIMEOUT = "timeout"
ERR_OOM = "oom"
ERR_VALIDATION = "validation_error"

RETRYABLE_ERRORS = (ERR_TRANSIENT_IO, ERR_BROKER_TIMEOUT, ERR_WORKER_CRASH, ERR_LEASE_EXPIRED)
NON_RETRYABLE_ERRORS = (
    ERR_SAMPLE_INSUFFICIENT,
    ERR_METHOD_INCOMPATIBLE,
    ERR_PRECONDITION_FAILED,
    ERR_PATH_ESCAPE,
    ERR_UNDECLARED_OUTPUT,
    ERR_OUTPUT_QUOTA,
    ERR_TIMEOUT,
    ERR_OOM,
    ERR_VALIDATION,
)

# Sensitive field names filtered out of captured logs/metadata (T-14-13).
_SENSITIVE_KEYS = ("token", "secret", "password", "credential", "api_key", "authorization")


def is_retryable(error_class: str) -> bool:
    """Only a transient error class is retryable; sample/incompatible never are."""
    return error_class in RETRYABLE_ERRORS


@dataclass(frozen=True)
class RecordedOutput:
    """A single output file a fixture says a task produces (replayed, not written)."""

    output_name: str
    relative_path: str
    size_bytes: int
    checksum_sha256: str
    content_role: str = "result_table"
    media_type: str = "text/tab-separated-values"
    declared: bool = True
    sensitive: bool = False


@dataclass(frozen=True)
class RecordedOutcome:
    """The recorded result a fake executor replays for one task.

    Everything an executor would have observed is recorded here: the exit code and
    (optional) terminating signal, the captured stdout/stderr, the outputs, the
    resource facts, and the ``error_class`` for a non-zero exit.  ``success`` is
    derived from ``exit_code == 0`` and no error class.
    """

    exit_code: int = 0
    signal: int | None = None
    stdout: str = ""
    stderr: str = ""
    outputs: tuple[RecordedOutput, ...] = ()
    resource_usage: dict[str, Any] = field(default_factory=dict)
    error_class: str = ""
    error_summary: str = ""
    collection_failed: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.error_class


class SandboxViolation(Exception):
    """Raised internally when a sandbox path escapes its scope."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Sandbox:
    """In-memory model of a task sandbox: read-only inputs, temp work, scoped outputs.

    No real filesystem is touched.  :meth:`place_output` validates that every
    declared output path stays inside the write scope and is not an absolute /
    parent-traversal / symlink-escape path — the same escape rules the preflight
    output-isolation check uses.
    """

    def __init__(self, *, write_scope: str, input_ids: list[str]) -> None:
        self.write_scope = write_scope.rstrip("/") + "/" if write_scope else ""
        self.input_ids = list(input_ids)
        self.outputs: dict[str, RecordedOutput] = {}

    @staticmethod
    def _escapes(path: str) -> bool:
        normalized = path.replace("\\", "/")
        if normalized.startswith("/"):
            return True
        if normalized[1:2] == ":":
            return True
        return ".." in normalized.split("/")

    def place_output(self, output: RecordedOutput) -> None:
        if self._escapes(output.relative_path):
            raise SandboxViolation(f"output path {output.relative_path!r} escapes the sandbox")
        # A symlink-escape is modelled as a declared symlink target that escapes.
        if output.content_role == "symlink" and self._escapes(output.output_name):
            raise SandboxViolation(f"symlink output {output.output_name!r} escapes the sandbox")
        self.outputs[output.output_name] = output


@dataclass(frozen=True)
class ExecutionResult:
    """What a (fake) executor observed for one attempt."""

    executor_kind: str
    exit_code: int
    signal: int | None
    stdout: str
    stderr: str
    run_metadata: dict[str, Any]
    error_class: str = ""


class LocalProcessExecutor:
    """A fake local-process executor: replays a recorded outcome (T-14-04)."""

    kind = EXEC_LOCAL

    def execute(self, task_id: str, outcome: RecordedOutcome, *, params: dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            executor_kind=self.kind,
            exit_code=outcome.exit_code,
            signal=outcome.signal,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            run_metadata={"executor": self.kind, "params_hash": hash_payload(params)},
            error_class=outcome.error_class,
        )


class ContainerExecutor:
    """A fake container executor: pinned digest, read-only rootfs, no undeclared mounts (T-14-05)."""

    kind = EXEC_CONTAINER

    def execute(
        self,
        task_id: str,
        outcome: RecordedOutcome,
        *,
        params: dict[str, Any],
        container_digest: str = "",
        mounts: list[str] | None = None,
        network: str = "none",
    ) -> ExecutionResult:
        declared_mounts = mounts or []
        if not container_digest or container_digest.strip().lower().endswith(":latest") or container_digest.strip().lower() == "latest":
            return ExecutionResult(self.kind, 125, None, "", "floating or missing container digest", {"executor": self.kind}, ERR_PRECONDITION_FAILED)
        if network not in ("none", "deny"):
            return ExecutionResult(self.kind, 126, None, "", f"undeclared network {network!r}", {"executor": self.kind}, ERR_PRECONDITION_FAILED)
        return ExecutionResult(
            executor_kind=self.kind,
            exit_code=outcome.exit_code,
            signal=outcome.signal,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            run_metadata={
                "executor": self.kind,
                "container_digest": container_digest,
                "read_only_rootfs": True,
                "mounts": sorted(declared_mounts),
                "network": network,
            },
            error_class=outcome.error_class,
        )


class NextflowExecutor:
    """A fake Nextflow executor adapter: captures run id / profile / trace (T-14-06)."""

    kind = EXEC_NEXTFLOW

    def execute(self, task_id: str, outcome: RecordedOutcome, *, params: dict[str, Any], profile: str = "standard", workdir: str = "work/") -> ExecutionResult:
        run_id = make_stable_id("nextflow_run", {"task_id": task_id, "profile": profile})
        return ExecutionResult(
            executor_kind=self.kind,
            exit_code=outcome.exit_code,
            signal=outcome.signal,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            run_metadata={
                "executor": self.kind,
                "run_id": run_id,
                "profile": profile,
                "workdir": workdir,
                "trace": {"task_id": task_id, "status": "OK" if outcome.succeeded else "FAILED"},
            },
            error_class=outcome.error_class,
        )


class SlurmExecutor:
    """RESERVED HPC executor interface (T-14-07): declared, not implemented in the MVP.

    Keeps HPC assumptions out of the domain layer.  Calling :meth:`execute` raises
    ``NotImplementedError`` deterministically so nothing silently assumes Slurm.
    """

    kind = EXEC_SLURM

    def execute(self, task_id: str, outcome: RecordedOutcome, *, params: dict[str, Any]) -> ExecutionResult:  # pragma: no cover - interface only
        raise NotImplementedError("SlurmExecutor is a reserved interface; not implemented in the offline MVP")


def _select_executor(kind: str) -> Any:
    return {
        EXEC_LOCAL: LocalProcessExecutor(),
        EXEC_CONTAINER: ContainerExecutor(),
        EXEC_NEXTFLOW: NextflowExecutor(),
        EXEC_SLURM: SlurmExecutor(),
    }[kind]


def _filter_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """Redact obviously sensitive keys from captured metadata/logs (T-14-13)."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if any(marker in str(key).lower() for marker in _SENSITIVE_KEYS):
            out[key] = "[REDACTED]"
        elif isinstance(value, dict):
            out[key] = _filter_sensitive(value)
        else:
            out[key] = value
    return out


@dataclass
class TaskExecutionReport:
    """The full outcome of executing one task: TaskRun record + side facts."""

    task_run: dict[str, Any]
    output_manifests: list[dict[str, Any]]
    log_artifact: dict[str, Any]
    warnings: list[str]
    retryable: bool
    error_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def execute_task(
    task_packet: dict[str, Any],
    outcome: RecordedOutcome,
    *,
    worker_identity: str,
    executor_kind: str = EXEC_LOCAL,
    attempt: int = 1,
    retry_of: str = "",
    max_output_bytes: int = 10_000_000,
    executor_options: dict[str, Any] | None = None,
) -> TaskExecutionReport:
    """Replay a recorded outcome into a deterministic TaskRun report.

    Builds a sandbox, runs the selected fake executor, enumerates outputs (flagging
    undeclared / over-quota / path-escaping writes), collects resource facts, filters
    sensitive fields out of logs, and produces a validated TaskRun record.  A
    non-zero exit or a sandbox violation yields a ``failed`` record; the retry
    classifier decides whether it is retryable.
    """
    task_id = str(task_packet.get("task_id", ""))
    expected_outputs = set(task_packet.get("expected_outputs", []) or [])
    exec_fields = task_packet.get("execution_fields", {})
    write_scope = str(exec_fields.get("write_scope", "outputs/"))
    params = task_packet.get("params", {}) if isinstance(task_packet.get("params"), dict) else {}
    input_ids = list(task_packet.get("expected_inputs", []) or task_packet.get("planned_inputs", []))

    sandbox = Sandbox(write_scope=write_scope, input_ids=input_ids)
    warnings: list[str] = []
    error_class = outcome.error_class

    # --- place declared outputs into the sandbox (path/symlink escape guard) ---
    escape_violation = ""
    for output in outcome.outputs:
        try:
            sandbox.place_output(output)
        except SandboxViolation as exc:
            escape_violation = exc.message
            error_class = ERR_PATH_ESCAPE
            break

    # --- run the fake executor -------------------------------------------------
    executor = _select_executor(executor_kind)
    options = executor_options or {}
    result = executor.execute(task_id, outcome, params=params, **options) if executor_kind != EXEC_SLURM else executor.execute(task_id, outcome, params=params)
    if result.error_class and not error_class:
        error_class = result.error_class

    # --- output enumeration (T-14-12) -----------------------------------------
    output_manifests: list[dict[str, Any]] = []
    total_bytes = 0
    for _output_key, output in sorted(sandbox.outputs.items()):
        total_bytes += output.size_bytes
        if output.output_name not in expected_outputs:
            warnings.append(f"undeclared output {output.output_name!r} registered as a warning")
        output_manifests.append(
            {
                "output_name": output.output_name,
                "artifact_ref": make_stable_id("output_artifact", {"task_id": task_id, "output_name": output.output_name}),
                "size_bytes": output.size_bytes,
                "checksum_sha256": output.checksum_sha256,
                "content_role": output.content_role,
                "media_type": output.media_type,
                "declared": output.output_name in expected_outputs,
            }
        )
    if total_bytes > max_output_bytes and not error_class:
        error_class = ERR_OUTPUT_QUOTA

    # --- resource collection (T-14-09): failure is a warning, not a lost result ---
    resource_usage = dict(outcome.resource_usage)
    if outcome.collection_failed:
        warnings.append("resource metric collection failed; business result retained")
        resource_usage = {}

    # --- controlled log artifact with sensitive filtering (T-14-13) -----------
    log_payload = _filter_sensitive({"stdout": result.stdout, "stderr": result.stderr, "run_metadata": result.run_metadata})
    log_artifact = {
        "artifact_ref": make_stable_id("log_artifact", {"task_id": task_id, "attempt": attempt}),
        "content_role": "run_log",
        "media_type": "application/json",
        "payload": log_payload,
        "checksum_sha256": hash_payload(log_payload),
    }

    # --- determine terminal status --------------------------------------------
    succeeded = result.exit_code == 0 and not error_class and not escape_violation
    result_status = "completed" if succeeded else "failed"
    exit_code = result.exit_code if not escape_violation else 1
    error_summary = outcome.error_summary or escape_violation or (result.stderr if not succeeded else "")
    if not succeeded and not error_summary:
        error_summary = f"task failed with error class {error_class or 'unknown'}"

    output_refs: list[str] = [str(m["artifact_ref"]) for m in output_manifests]
    log_refs: list[str] = [str(log_artifact["artifact_ref"])]

    run = TaskRun(
        task_run_id="",
        task_id=task_id,
        result_status=result_status,
        artifact_refs=[],
        environment={"executor_kind": executor_kind, "worker_identity": worker_identity, "write_scope": write_scope},
        tool_identity=f"{executor_kind}:{worker_identity}",
        parameters=params,
        log_refs=log_refs,
        output_refs=output_refs if succeeded else [],
        exit_code=exit_code if result_status in ("completed", "failed") else None,
        resource_usage=resource_usage,
        attempt=attempt,
        retry_of=retry_of,
        error_summary="" if succeeded else error_summary,
        reason="",
        created_at="",
    )
    run_dict = run.to_dict()

    validation_errors = validate_task_run(run_dict)
    if validation_errors:  # pragma: no cover - defensive; a produced record must be valid
        warnings.append("produced TaskRun failed self-validation: " + "; ".join(validation_errors))

    return TaskExecutionReport(
        task_run=run_dict,
        output_manifests=output_manifests,
        log_artifact=log_artifact,
        warnings=warnings,
        retryable=is_retryable(error_class) if not succeeded else False,
        error_class="" if succeeded else error_class,
    )


# --- Worker with lease / heartbeat / idempotency (T-14-01/02) ----------------


@dataclass
class Lease:
    """A logical-clock task lease (no wall clock)."""

    task_id: str
    worker_identity: str
    acquired_tick: int
    ttl_ticks: int

    def expiry_tick(self) -> int:
        return self.acquired_tick + self.ttl_ticks

    def expired(self, now_tick: int) -> bool:
        return now_tick > self.expiry_tick()


class Worker:
    """A deterministic offline worker: idempotent consume + lease/heartbeat.

    A message is processed at most once into a valid TaskRun: the run's stable id
    is the idempotency key, so a duplicate / redelivered message never creates a
    second valid run (T-14-01).  Leases use a logical clock; an expired lease can
    be reclaimed by another worker without losing state (T-14-02/15).
    """

    def __init__(self, worker_identity: str, *, lease_ttl_ticks: int = 5) -> None:
        self.worker_identity = worker_identity
        self.lease_ttl_ticks = lease_ttl_ticks
        self._runs: dict[str, dict[str, Any]] = {}
        self._leases: dict[str, Lease] = {}
        self._tick = 0

    def tick(self, n: int = 1) -> int:
        self._tick += n
        return self._tick

    def acquire_lease(self, task_id: str) -> Lease | None:
        existing = self._leases.get(task_id)
        if existing is not None and not existing.expired(self._tick):
            return None  # still held by someone; cannot take over
        lease = Lease(task_id=task_id, worker_identity=self.worker_identity, acquired_tick=self._tick, ttl_ticks=self.lease_ttl_ticks)
        self._leases[task_id] = lease
        return lease

    def heartbeat(self, task_id: str) -> bool:
        lease = self._leases.get(task_id)
        if lease is None or lease.worker_identity != self.worker_identity:
            return False
        self._leases[task_id] = Lease(task_id, self.worker_identity, self._tick, self.lease_ttl_ticks)
        return True

    def consume(self, task_packet: dict[str, Any], outcome: RecordedOutcome, **kwargs: Any) -> dict[str, Any]:
        """Process a task once; a duplicate returns the already-recorded run."""
        report = execute_task(task_packet, outcome, worker_identity=self.worker_identity, **kwargs)
        run = report.task_run
        run_id = run["task_run_id"]
        if run_id in self._runs:
            return self._runs[run_id]  # idempotent: already recorded
        self._runs[run_id] = run
        return run

    def runs(self) -> list[dict[str, Any]]:
        return [self._runs[k] for k in sorted(self._runs)]


# --- EngineeringTaskPacket runner (T-14-14) ----------------------------------


@dataclass
class EngineeringRunResult:
    """The result of an isolated engineering task: a patch, never a merge."""

    task_id: str
    main_branch_hash_before: str
    main_branch_hash_after: str
    worktree_id: str
    patch_ref: str
    merged: bool
    to_dict_status: str = "patch_exported"

    @property
    def main_unchanged(self) -> bool:
        return self.main_branch_hash_before == self.main_branch_hash_after

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_engineering_task(engineering_packet: dict[str, Any], *, main_branch_hash: str, patch_content: str) -> EngineeringRunResult:
    """Run an engineering task in an isolated worktree and export a patch.

    Fully offline: the worktree, the patch export, and the main-branch hash are
    modelled deterministically.  The task never merges, so the main-branch hash is
    unchanged before and after (T-14-14).
    """
    task_id = str(engineering_packet.get("task_id", ""))
    worktree_id = make_stable_id("engineering_worktree", {"task_id": task_id})
    patch_ref = make_stable_id("engineering_patch", {"task_id": task_id, "patch": patch_content})
    return EngineeringRunResult(
        task_id=task_id,
        main_branch_hash_before=main_branch_hash,
        main_branch_hash_after=main_branch_hash,  # never merged → unchanged
        worktree_id=worktree_id,
        patch_ref=patch_ref,
        merged=False,
    )


__all__ = [
    "EXEC_LOCAL",
    "EXEC_CONTAINER",
    "EXEC_NEXTFLOW",
    "EXEC_SLURM",
    "EXECUTOR_KINDS",
    "RETRYABLE_ERRORS",
    "NON_RETRYABLE_ERRORS",
    "ERR_SAMPLE_INSUFFICIENT",
    "ERR_METHOD_INCOMPATIBLE",
    "ERR_PRECONDITION_FAILED",
    "ERR_PATH_ESCAPE",
    "ERR_UNDECLARED_OUTPUT",
    "ERR_OUTPUT_QUOTA",
    "ERR_TIMEOUT",
    "ERR_OOM",
    "ERR_TRANSIENT_IO",
    "ERR_WORKER_CRASH",
    "ERR_LEASE_EXPIRED",
    "is_retryable",
    "RecordedOutput",
    "RecordedOutcome",
    "Sandbox",
    "SandboxViolation",
    "ExecutionResult",
    "LocalProcessExecutor",
    "ContainerExecutor",
    "NextflowExecutor",
    "SlurmExecutor",
    "TaskExecutionReport",
    "execute_task",
    "Lease",
    "Worker",
    "EngineeringRunResult",
    "run_engineering_task",
]
