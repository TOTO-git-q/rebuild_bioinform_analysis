"""Inert deterministic ready-node scheduler + transactional outbox (WP-13).

Turns an authorized WorkflowPlan into a delivery order without running anything:
only nodes whose dependencies are satisfied are enqueued (T-13-10), messages carry
*only* a TaskPacket id/version and a trace context — never the packet body
(T-13-11), delivery goes through a transactional outbox so a failed "commit" never
delivers (T-13-11), and priority / project fairness / concurrency caps keep one
project from starving another (T-13-12).  Cancel / pause / resume stop scheduling
successors (T-13-13), and the whole thing is idempotent under duplicate messages,
broker disconnects and crashes (T-13-14).

Everything is an in-memory, deterministic control object: no real broker, no
network, no thread, no clock read.  Re-running :meth:`Scheduler.dispatch` after a
simulated crash re-delivers nothing already delivered, so state is never lost and
no side effect is duplicated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.ids import make_stable_id

# --- Bounded task delivery states --------------------------------------------
TASK_BLOCKED = "blocked"  # dependencies not satisfied (or an ancestor cancelled)
TASK_READY = "ready"  # deps satisfied, awaiting dispatch
TASK_DELIVERED = "delivered"  # message enqueued
TASK_COMPLETED = "completed"  # reported done
TASK_CANCELLED = "cancelled"
TASK_STATES = (TASK_BLOCKED, TASK_READY, TASK_DELIVERED, TASK_COMPLETED, TASK_CANCELLED)


@dataclass(frozen=True)
class QueueMessage:
    """A delivery message — ids/version + trace only, never the packet body."""

    message_id: str
    task_id: str
    task_version: str
    project_id: str
    authorization_id: str
    trace_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TransactionalOutbox:
    """A deterministic transactional outbox (T-13-11/14).

    Messages are *staged* inside a transaction and only become deliverable on
    :meth:`commit`; a :meth:`rollback` (a simulated DB-commit failure) discards
    them so nothing is delivered.  Enqueue is idempotent on ``message_id`` — a
    duplicate (a redelivered / crash-replayed message) never produces a second
    queue row.
    """

    def __init__(self) -> None:
        self._committed: list[QueueMessage] = []
        self._staged: list[QueueMessage] = []
        self._seen_ids: set[str] = set()

    def stage(self, message: QueueMessage) -> None:
        self._staged.append(message)

    def commit(self) -> list[QueueMessage]:
        delivered: list[QueueMessage] = []
        for message in self._staged:
            if message.message_id in self._seen_ids:
                continue  # idempotent: already delivered
            self._seen_ids.add(message.message_id)
            self._committed.append(message)
            delivered.append(message)
        self._staged = []
        return delivered

    def rollback(self) -> None:
        self._staged = []

    def queue(self) -> list[QueueMessage]:
        return list(self._committed)

    def delivered_task_ids(self) -> set[str]:
        return {m.task_id for m in self._committed}


@dataclass
class SchedulableTask:
    """A task the scheduler tracks (deps by task id; body lives elsewhere)."""

    task_id: str
    project_id: str
    dependencies: list[str] = field(default_factory=list)
    version: str = "1"
    priority: int = 0
    authorization_id: str = ""


class Scheduler:
    """A deterministic ready-node scheduler over authorized tasks.

    A task is dispatched only when authorized, all its dependencies are completed,
    no dependency (transitively) is cancelled, and its project is not paused.
    Dispatch order is deterministic: higher priority first, then the project with
    the fewest in-flight deliveries (fairness), then the task id.
    """

    def __init__(self, *, max_concurrency: int = 4, per_project_concurrency: int = 2) -> None:
        self._tasks: dict[str, SchedulableTask] = {}
        self._state: dict[str, str] = {}
        self._authorized: set[str] = set()
        self._paused_projects: set[str] = set()
        self.outbox = TransactionalOutbox()
        self.max_concurrency = max_concurrency
        self.per_project_concurrency = per_project_concurrency

    # --- registration --------------------------------------------------------
    def add_task(self, task: SchedulableTask, *, authorized: bool = True) -> None:
        self._tasks[task.task_id] = task
        self._state[task.task_id] = TASK_BLOCKED
        if authorized:
            self._authorized.add(task.task_id)

    def load_authorization(self, tasks: list[SchedulableTask], authorization: Any) -> None:
        """Register tasks, authorizing only those an ExecutionAuthorization covers."""
        for task in tasks:
            authorized = bool(getattr(authorization, "authorizes", lambda _t: False)(task.task_id))
            task.authorization_id = getattr(authorization, "authorization_id", "")
            self.add_task(task, authorized=authorized)

    # --- lifecycle commands --------------------------------------------------
    def mark_completed(self, task_id: str) -> None:
        if task_id in self._state and self._state[task_id] != TASK_CANCELLED:
            self._state[task_id] = TASK_COMPLETED

    def cancel(self, task_id: str) -> None:
        if task_id in self._state:
            self._state[task_id] = TASK_CANCELLED

    def pause_project(self, project_id: str) -> None:
        self._paused_projects.add(project_id)

    def resume_project(self, project_id: str) -> None:
        self._paused_projects.discard(project_id)

    # --- scheduling ----------------------------------------------------------
    def _has_cancelled_ancestor(self, task_id: str, _seen: set[str] | None = None) -> bool:
        seen = _seen if _seen is not None else set()
        if task_id in seen:
            return False
        seen.add(task_id)
        task = self._tasks.get(task_id)
        if task is None:
            return False
        for dep in task.dependencies:
            if self._state.get(dep) == TASK_CANCELLED:
                return True
            if self._has_cancelled_ancestor(dep, seen):
                return True
        return False

    def ready_tasks(self) -> list[str]:
        """Deterministically ordered set of tasks eligible for dispatch now."""
        ready: list[str] = []
        for task_id, task in self._tasks.items():
            if self._state.get(task_id) != TASK_BLOCKED:
                continue
            if task_id not in self._authorized:
                continue
            if task.project_id in self._paused_projects:
                continue
            if self._has_cancelled_ancestor(task_id):
                continue
            if all(self._state.get(dep) == TASK_COMPLETED for dep in task.dependencies):
                ready.append(task_id)
        in_flight = self._in_flight_by_project()
        ready.sort(key=lambda t: (-self._tasks[t].priority, in_flight.get(self._tasks[t].project_id, 0), t))
        return ready

    def _in_flight_by_project(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task_id, state in self._state.items():
            if state == TASK_DELIVERED:
                project = self._tasks[task_id].project_id
                counts[project] = counts.get(project, 0) + 1
        return counts

    def dispatch(self, *, trace_id: str = "trace") -> list[QueueMessage]:
        """Stage + commit messages for as many ready tasks as caps allow.

        Idempotent: a task already delivered is never re-delivered, so calling
        ``dispatch`` again after a crash replays no side effect.
        """
        in_flight = self._in_flight_by_project()
        total_in_flight = sum(in_flight.values())
        staged: list[str] = []
        for task_id in self.ready_tasks():
            if total_in_flight >= self.max_concurrency:
                break
            task = self._tasks[task_id]
            if in_flight.get(task.project_id, 0) >= self.per_project_concurrency:
                continue
            message = QueueMessage(
                message_id=make_stable_id("queue_message", {"task_id": task_id, "version": task.version, "authorization_id": task.authorization_id}),
                task_id=task_id,
                task_version=task.version,
                project_id=task.project_id,
                authorization_id=task.authorization_id,
                trace_id=trace_id,
            )
            self.outbox.stage(message)
            staged.append(task_id)
            in_flight[task.project_id] = in_flight.get(task.project_id, 0) + 1
            total_in_flight += 1
        delivered = self.outbox.commit()
        delivered_ids = {m.task_id for m in delivered}
        for task_id in staged:
            if task_id in delivered_ids:
                self._state[task_id] = TASK_DELIVERED
        return delivered

    def dispatch_all(self, *, trace_id: str = "trace") -> list[QueueMessage]:
        """Drive the DAG to completion by auto-completing delivered tasks.

        Deterministic simulation helper: repeatedly dispatch ready tasks and mark
        them completed until nothing more can be scheduled.  Used to prove the DAG
        delivers dependency-first with no orphaned nodes.
        """
        all_delivered: list[QueueMessage] = []
        while True:
            delivered = self.dispatch(trace_id=trace_id)
            if not delivered:
                break
            for message in delivered:
                all_delivered.append(message)
                self.mark_completed(message.task_id)
        return all_delivered

    # --- introspection -------------------------------------------------------
    def state(self, task_id: str) -> str:
        return self._state.get(task_id, TASK_BLOCKED)

    def states(self) -> dict[str, str]:
        return dict(self._state)


def tasks_from_workflow_plan(workflow_plan: dict[str, Any], *, project_id: str, authorization_id: str = "", priority: int = 0) -> list[SchedulableTask]:
    """Project a compiled WorkflowPlan's tasks + dependency edges to SchedulableTasks."""
    deps: dict[str, list[str]] = {tid: [] for tid in workflow_plan.get("task_ids", [])}
    for edge in workflow_plan.get("dependencies", []):
        if isinstance(edge, (list, tuple)) and len(edge) == 2 and edge[0] in deps:
            deps[edge[0]].append(edge[1])
    return [
        SchedulableTask(task_id=tid, project_id=project_id, dependencies=sorted(deps[tid]), authorization_id=authorization_id, priority=priority)
        for tid in workflow_plan.get("task_ids", [])
    ]


__all__ = [
    "TASK_BLOCKED",
    "TASK_READY",
    "TASK_DELIVERED",
    "TASK_COMPLETED",
    "TASK_CANCELLED",
    "TASK_STATES",
    "QueueMessage",
    "TransactionalOutbox",
    "SchedulableTask",
    "Scheduler",
    "tasks_from_workflow_plan",
]
