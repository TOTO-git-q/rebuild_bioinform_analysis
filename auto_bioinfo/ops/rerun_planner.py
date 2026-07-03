"""Partial-failure isolation and affected-subgraph rerun planning (WP-25 / T-25-05, T-25-06).

Two requirement-spec behaviours over a task DAG:

- **Partial failure (T-25-05).** When a node fails, only the sub-graph that
  *depends on* it is blocked; independent sub-graphs continue.  An unrelated path
  must never be cancelled because a sibling failed.
- **Invalidation & affected-subgraph rerun (T-25-06).** When a node's inputs /
  version change, only its *correct descendants* are invalidated and re-run;
  everything not downstream of the change keeps its existing (still-valid) result.

This module computes both as **pure, deterministic** graph operations over an
explicit in-memory DAG.  It runs nothing, cancels nothing, and re-runs nothing for
real — it produces a *plan value* naming exactly which nodes are blocked /
continuable / invalidated.  A malformed graph (unknown dependency, or a cycle)
fails closed rather than producing a partial plan.

Design constraints mirror the house style: pure, deterministic, fail-closed,
bounded status vocabulary, stable (sorted) node ordering in every projection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# --- Bounded status vocabulary -----------------------------------------------
STATUS_OK = "ok"  # a valid plan was produced
STATUS_INVALID = "invalid"  # the graph or the node set is malformed (fail closed)

STATUSES = (STATUS_OK, STATUS_INVALID)

CODE_PLAN_OK = "RERUN_PLAN_OK"
CODE_UNKNOWN_NODE = "RERUN_UNKNOWN_NODE"
CODE_UNKNOWN_DEPENDENCY = "RERUN_UNKNOWN_DEPENDENCY"
CODE_CYCLE = "RERUN_GRAPH_HAS_CYCLE"
CODE_MALFORMED_GRAPH = "RERUN_MALFORMED_GRAPH"

REASON_CODES = (CODE_PLAN_OK, CODE_UNKNOWN_NODE, CODE_UNKNOWN_DEPENDENCY, CODE_CYCLE, CODE_MALFORMED_GRAPH)


class TaskGraphError(ValueError):
    """The task graph is structurally invalid (unknown dependency or a cycle)."""


@dataclass(frozen=True)
class TaskNode:
    """One DAG node: an id and the ids it directly depends on."""

    node_id: str
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "depends_on": list(self.depends_on)}


@dataclass(frozen=True)
class TaskGraph:
    """An immutable task DAG built from :class:`TaskNode` values.

    Validated on construction via :func:`build_graph` (which raises on an unknown
    dependency or a cycle); the frozen ``nodes`` mapping is the source of truth.
    """

    nodes: Mapping[str, TaskNode]

    def descendants(self, node_ids: Sequence[str]) -> set[str]:
        """The transitive set of nodes that depend (directly or indirectly) on any of ``node_ids``.

        The seed nodes themselves are **not** included unless one seed is a
        descendant of another; callers add the seeds explicitly when they want the
        closed set.
        """
        # Build the reverse adjacency (dependents) once.
        dependents: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                dependents[dep].add(nid)
        result: set[str] = set()
        stack = [nid for nid in node_ids if nid in self.nodes]
        while stack:
            current = stack.pop()
            for child in dependents.get(current, ()):
                if child not in result:
                    result.add(child)
                    stack.append(child)
        return result

    def ancestors(self, node_id: str) -> set[str]:
        """The transitive set of nodes ``node_id`` depends on (directly or indirectly)."""
        result: set[str] = set()
        stack = list(self.nodes[node_id].depends_on) if node_id in self.nodes else []
        while stack:
            current = stack.pop()
            if current in result or current not in self.nodes:
                continue
            result.add(current)
            stack.extend(self.nodes[current].depends_on)
        return result


def build_graph(nodes: Any) -> TaskGraph:
    """Build and validate a :class:`TaskGraph` from an iterable of :class:`TaskNode`.

    Raises :class:`TaskGraphError` on a duplicate node id, an unknown dependency,
    or a cycle — a malformed graph must never yield a partial plan.
    """
    if not isinstance(nodes, (list, tuple)):
        raise TaskGraphError("nodes must be a sequence of TaskNode")
    node_map: dict[str, TaskNode] = {}
    for node in nodes:
        if not isinstance(node, TaskNode) or not isinstance(node.node_id, str) or not node.node_id:
            raise TaskGraphError("each node must be a TaskNode with a non-empty node_id")
        if node.node_id in node_map:
            raise TaskGraphError(f"duplicate node id {node.node_id!r}")
        if not isinstance(node.depends_on, tuple):
            raise TaskGraphError(f"node {node.node_id!r} depends_on must be a tuple")
        node_map[node.node_id] = node
    for node in node_map.values():
        for dep in node.depends_on:
            if dep not in node_map:
                raise TaskGraphError(f"node {node.node_id!r} depends on unknown node {dep!r}")
            if dep == node.node_id:
                raise TaskGraphError(f"node {node.node_id!r} depends on itself")
    _assert_acyclic(node_map)
    return TaskGraph(nodes=node_map)


def _assert_acyclic(node_map: Mapping[str, TaskNode]) -> None:
    """Raise :class:`TaskGraphError` if the dependency graph contains a cycle."""
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in node_map}

    def visit(nid: str, path: tuple[str, ...]) -> None:
        color[nid] = GREY
        for dep in node_map[nid].depends_on:
            if color[dep] == GREY:
                raise TaskGraphError(f"dependency cycle detected involving {dep!r} (path {' -> '.join(path + (nid, dep))})")
            if color[dep] == WHITE:
                visit(dep, path + (nid,))
        color[nid] = BLACK

    for nid in node_map:
        if color[nid] == WHITE:
            visit(nid, ())


@dataclass(frozen=True)
class PartialFailurePlan:
    """The plan for a partial failure: which nodes are blocked vs. still runnable.

    - ``failed`` — the seed failed nodes;
    - ``blocked`` — the failed nodes plus their transitive dependents (must not run);
    - ``continuable`` — every node with no failed ancestor (an independent path that
      is never cancelled by an unrelated failure).
    """

    status: str
    reason_code: str
    message: str
    failed: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    continuable: tuple[str, ...] = ()
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "failed": list(self.failed),
            "blocked": list(self.blocked),
            "continuable": list(self.continuable),
            "binding": dict(self.binding),
        }


def plan_partial_failure(graph: Any, failed_nodes: Any) -> PartialFailurePlan:
    """Plan a partial failure: isolate the failed sub-graph, keep the rest runnable (T-25-05).

    Returns a :class:`PartialFailurePlan`.  ``blocked`` is the failed nodes plus
    everything transitively downstream of them; ``continuable`` is every node that
    is not blocked (its dependency chain is unaffected).  A failed node that is not
    in the graph fails closed to ``invalid`` so a typo cannot silently drop a
    blocker.
    """
    if not isinstance(graph, TaskGraph):
        return PartialFailurePlan(STATUS_INVALID, CODE_MALFORMED_GRAPH, "graph must be a TaskGraph built via build_graph")
    if not isinstance(failed_nodes, (list, tuple, set, frozenset)):
        return PartialFailurePlan(STATUS_INVALID, CODE_MALFORMED_GRAPH, "failed_nodes must be a collection of node ids")
    failed = sorted({str(n) for n in failed_nodes})
    unknown = [n for n in failed if n not in graph.nodes]
    if unknown:
        return PartialFailurePlan(STATUS_INVALID, CODE_UNKNOWN_NODE, f"failed node(s) not in the graph: {', '.join(unknown)}")

    blocked_set = set(failed) | graph.descendants(failed)
    blocked = sorted(blocked_set)
    continuable = sorted(nid for nid in graph.nodes if nid not in blocked_set)
    return PartialFailurePlan(
        status=STATUS_OK,
        reason_code=CODE_PLAN_OK,
        message=f"{len(blocked)} node(s) blocked by the failure; {len(continuable)} independent node(s) continue",
        failed=tuple(failed),
        blocked=tuple(blocked),
        continuable=tuple(continuable),
        binding={"node_count": len(graph.nodes)},
    )


@dataclass(frozen=True)
class RerunPlan:
    """The plan for an invalidation: which nodes to re-run vs. preserve (T-25-06).

    - ``changed`` — the seed changed/invalidated nodes;
    - ``invalidated`` — the changed nodes plus their transitive descendants (the
      *correct* affected subgraph to re-run);
    - ``preserved`` — every node not downstream of a change (its result stays valid
      and is **not** re-run).
    """

    status: str
    reason_code: str
    message: str
    changed: tuple[str, ...] = ()
    invalidated: tuple[str, ...] = ()
    preserved: tuple[str, ...] = ()
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "changed": list(self.changed),
            "invalidated": list(self.invalidated),
            "preserved": list(self.preserved),
            "binding": dict(self.binding),
        }


def plan_rerun(graph: Any, changed_nodes: Any) -> RerunPlan:
    """Plan a minimal rerun of only the correct descendants of a change (T-25-06).

    Returns a :class:`RerunPlan`.  ``invalidated`` is the changed nodes plus every
    node transitively downstream of them; ``preserved`` is everything else, whose
    existing result remains valid and must not be re-run.  An unknown changed node
    fails closed to ``invalid`` so an over-broad or under-broad rerun cannot be
    produced from a typo.
    """
    if not isinstance(graph, TaskGraph):
        return RerunPlan(STATUS_INVALID, CODE_MALFORMED_GRAPH, "graph must be a TaskGraph built via build_graph")
    if not isinstance(changed_nodes, (list, tuple, set, frozenset)):
        return RerunPlan(STATUS_INVALID, CODE_MALFORMED_GRAPH, "changed_nodes must be a collection of node ids")
    changed = sorted({str(n) for n in changed_nodes})
    unknown = [n for n in changed if n not in graph.nodes]
    if unknown:
        return RerunPlan(STATUS_INVALID, CODE_UNKNOWN_NODE, f"changed node(s) not in the graph: {', '.join(unknown)}")

    invalidated_set = set(changed) | graph.descendants(changed)
    invalidated = sorted(invalidated_set)
    preserved = sorted(nid for nid in graph.nodes if nid not in invalidated_set)
    return RerunPlan(
        status=STATUS_OK,
        reason_code=CODE_PLAN_OK,
        message=f"{len(invalidated)} node(s) invalidated and to be re-run; {len(preserved)} node(s) preserved",
        changed=tuple(changed),
        invalidated=tuple(invalidated),
        preserved=tuple(preserved),
        binding={"node_count": len(graph.nodes)},
    )


__all__ = [
    "STATUS_OK",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_PLAN_OK",
    "CODE_UNKNOWN_NODE",
    "CODE_UNKNOWN_DEPENDENCY",
    "CODE_CYCLE",
    "CODE_MALFORMED_GRAPH",
    "REASON_CODES",
    "TaskGraphError",
    "TaskNode",
    "TaskGraph",
    "build_graph",
    "PartialFailurePlan",
    "plan_partial_failure",
    "RerunPlan",
    "plan_rerun",
]
