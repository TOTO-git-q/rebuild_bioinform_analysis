"""Local deterministic sub-question dependency-graph + coverage command contracts (WP-07 / T-07-04, T-07-09).

Two *local, offline* planning slices over a set of inert draft
:class:`~auto_bioinfo.core.schemas.SubQuestion` projections, both run **before**
any real search, data acquisition, approval grant, event emission, persistence,
or pipeline transition can start:

- **T-07-04 — QuestionDependencyGraph.** :func:`build_dependency_graph` takes an
  in-memory list of draft sub-questions (and their *explicit* dependency
  relations only) and assembles an inert draft
  :class:`~auto_bioinfo.core.schemas.DependencyGraph` — reusing that core class's
  own cycle detection, deterministic serialisation, and topological ordering
  rather than reimplementing any graph logic.  A dependency edge is derived
  **only** from an explicit ``parent_subquestion_id`` link or an explicitly
  supplied relation pair; a dependency is never invented.  A graph with a cycle,
  or with a dangling edge endpoint (an edge naming a node that was not declared),
  is reported with a distinct machine-readable reason code — never silently
  accepted or repaired.  A valid DAG yields the single proceed outcome carrying
  the inert graph draft and its deterministic ``topological_order()``.

- **T-07-09 — coverage check.** :func:`assess_coverage` takes the same
  sub-questions plus the :class:`~auto_bioinfo.core.schemas.EvidencePlan`
  references (or explicit *not-answered* decisions) that name them, and produces
  an inert :class:`CoverageReport`-style projection asserting that **every**
  sub-question has at least one evidence plan *or* an explicitly recorded
  not-answered decision.  Any sub-question with neither is an uncovered node that
  MUST block state advancement; it is reported with a reason code, never waved
  through.

Design constraints (mirroring the :mod:`auto_bioinfo.intake` contract style):

- **Pure and deterministic.** Both public functions and every helper are total
  functions of their explicit in-memory inputs.  There is no I/O whatsoever: no
  file/network/socket access, no environment/credential read, **no wall-clock
  read**, no LLM / provider / model / SDK / tool call, no subprocess, threads,
  scheduler, queue, DB, event, audit log, persistence, or any process side
  effect.  Inputs are never mutated in place.  Produced ``DependencyGraph`` /
  ``CoverageReport`` projections carry an empty ``created_at`` (no timestamp), so
  byte-identical inputs always yield a byte-identical result.
- **No-guess derivation.** An edge is added only from an explicit parent link or
  an explicit relation pair; a sub-question is counted covered only by an
  explicit evidence-plan reference or an explicit not-answered decision.  Nothing
  is inferred, defaulted, or invented.
- **Inert, non-authoritative result only.** Each outcome is reviewable data: a
  bounded, frozen :class:`DependencyResult` / :class:`CoverageResult` carrying an
  in-memory *draft* projection (``status == "draft"``).  It is **never** persisted,
  versioned, emitted, sent out, marked authoritative, treated as an approval, or
  used to unblock any downstream workflow or pipeline stage.
- **Bounded vocabulary.** The status is one of exactly six values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.

This module defines command contracts only.  A proceed outcome is an inert
reviewable projection, never a grant to execute.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core import common
from ..core.schemas import DependencyGraph, EvidencePlan, SubQuestion
from ..core.validation import validate_dependency_graph

# --- Bounded result statuses -------------------------------------------------
# Exactly six.  ``graph_built`` and ``coverage_complete`` are the two
# proceed-with-data outcomes; the other four are fail-closed / blocking outcomes,
# none of which permits state advancement.
STATUS_GRAPH_BUILT = "graph_built"
STATUS_COVERAGE_COMPLETE = "coverage_complete"
STATUS_CYCLE_DETECTED = "cycle_detected"
STATUS_DANGLING_NODE = "dangling_node"
STATUS_COVERAGE_INCOMPLETE = "coverage_incomplete"
STATUS_REJECTED_MALFORMED = "rejected_malformed"

STATUSES = (
    STATUS_GRAPH_BUILT,
    STATUS_COVERAGE_COMPLETE,
    STATUS_CYCLE_DETECTED,
    STATUS_DANGLING_NODE,
    STATUS_COVERAGE_INCOMPLETE,
    STATUS_REJECTED_MALFORMED,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# proceed outcomes:
CODE_GRAPH_BUILT = "DEP_GRAPH_BUILT"
CODE_COVERAGE_COMPLETE = "DEP_COVERAGE_COMPLETE"
# dependency-graph fail-closed outcomes:
CODE_CYCLE_DETECTED = "DEP_CYCLE_DETECTED"
CODE_DANGLING_ENDPOINT = "DEP_DANGLING_ENDPOINT"
# coverage blocking outcome:
CODE_COVERAGE_INCOMPLETE = "DEP_COVERAGE_INCOMPLETE"
# malformed input / graph (fail closed):
CODE_INPUT_MALFORMED = "DEP_INPUT_MALFORMED"
CODE_GRAPH_MALFORMED = "DEP_GRAPH_MALFORMED"

REASON_CODES = (
    CODE_GRAPH_BUILT,
    CODE_COVERAGE_COMPLETE,
    CODE_CYCLE_DETECTED,
    CODE_DANGLING_ENDPOINT,
    CODE_COVERAGE_INCOMPLETE,
    CODE_INPUT_MALFORMED,
    CODE_GRAPH_MALFORMED,
)

# The status each reason code resolves to, so a future adapter can map a code to a
# status without re-deriving it.
_CODE_STATUS = {
    CODE_GRAPH_BUILT: STATUS_GRAPH_BUILT,
    CODE_COVERAGE_COMPLETE: STATUS_COVERAGE_COMPLETE,
    CODE_CYCLE_DETECTED: STATUS_CYCLE_DETECTED,
    CODE_DANGLING_ENDPOINT: STATUS_DANGLING_NODE,
    CODE_COVERAGE_INCOMPLETE: STATUS_COVERAGE_INCOMPLETE,
    CODE_INPUT_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_GRAPH_MALFORMED: STATUS_REJECTED_MALFORMED,
}

# The single status the produced graph / coverage projections carry; the command
# may never produce a locked/authoritative object.
DRAFT_STATUS = "draft"


# --- Tolerant input views ----------------------------------------------------
# Every helper only *reads* its argument; inputs are never mutated.


def _subquestion_fields(item: Any) -> tuple[str, str, str] | None:
    """Return ``(subquestion_id, parent_subquestion_id, research_spec_id)`` for an
    accepted sub-question shape, else ``None``.

    Accepts a :class:`SubQuestion` instance, a mapping projection of one, or a
    bare id string (a node with no parent link and no bound spec).  Only read.
    """
    if isinstance(item, SubQuestion):
        data = item.to_dict()
        return (
            str(data.get("subquestion_id", "")),
            str(data.get("parent_subquestion_id", "")),
            str(data.get("research_spec_id", "")),
        )
    if isinstance(item, Mapping):
        sqid = item.get("subquestion_id", "")
        parent = item.get("parent_subquestion_id", "")
        rsid = item.get("research_spec_id", "")
        if not isinstance(sqid, str):
            return None
        return (
            sqid,
            parent if isinstance(parent, str) else "",
            rsid if isinstance(rsid, str) else "",
        )
    if isinstance(item, str):
        return (item, "", "")
    return None


def _relation_pair(rel: Any) -> tuple[str, str] | None:
    """Return an explicit ``(from, to)`` dependency pair, else ``None``.

    ``[from, to]`` (or ``{"from": ..., "to": ...}``) means "from depends on to",
    matching the core :class:`DependencyGraph` edge convention.
    """
    if isinstance(rel, Mapping):
        frm = rel.get("from")
        to = rel.get("to", rel.get("depends_on"))
        if isinstance(frm, str) and isinstance(to, str):
            return (frm, to)
        return None
    if isinstance(rel, (list, tuple)) and len(rel) == 2 and all(isinstance(x, str) for x in rel):
        return (rel[0], rel[1])
    return None


def _plan_subquestion_ids(plan: Any) -> list[str] | None:
    """Return the sub-question ids an evidence-plan reference names, else ``None``.

    Accepts an :class:`EvidencePlan` instance, a mapping projection of one (its
    ``subquestion_ids``), a plain list/tuple of ids, or a single id string.  Only
    read; a malformed shape returns ``None`` so the caller can fail closed.
    """
    if isinstance(plan, EvidencePlan):
        return [x for x in plan.subquestion_ids if isinstance(x, str)]
    if isinstance(plan, Mapping):
        ids = plan.get("subquestion_ids", [])
        if not isinstance(ids, list):
            return None
        return [x for x in ids if isinstance(x, str)]
    if isinstance(plan, (list, tuple)):
        if all(isinstance(x, str) for x in plan):
            return [x for x in plan]
        return None
    if isinstance(plan, str):
        return [plan]
    return None


def _not_answered_id(item: Any) -> str | None:
    """Return the sub-question id of an explicit not-answered decision, else ``None``."""
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        sqid = item.get("subquestion_id")
        return sqid if isinstance(sqid, str) else None
    return None


def _resolve_nodes(subquestions: Any, research_spec_id: str | None) -> tuple[list[str], str, str | None]:
    """Resolve the ordered node ids + the bound research-spec id, fail-closed.

    Returns ``(node_ids, research_spec_id, error_message)``; ``error_message`` is
    ``None`` on success.  A non-sequence input, an unrecognised sub-question shape,
    an empty/blank node id, duplicate ids, sub-questions spanning more than one
    ResearchSpec, or a missing/invalid research-spec id each fails closed.
    """
    if not isinstance(subquestions, (list, tuple)):
        return ([], "", f"subquestions must be a list/tuple, not {type(subquestions).__name__}")
    if not subquestions:
        return ([], "", "no sub-questions provided; nothing to plan over")

    node_ids: list[str] = []
    rsids: set[str] = set()
    for idx, item in enumerate(subquestions):
        fields = _subquestion_fields(item)
        if fields is None:
            return ([], "", f"subquestions[{idx}] is not a SubQuestion, mapping, or id string")
        sqid, _parent, rsid = fields
        if not sqid.strip():
            return ([], "", f"subquestions[{idx}] has a missing/blank subquestion_id")
        node_ids.append(sqid)
        if rsid.strip():
            rsids.add(rsid)

    if len(set(node_ids)) != len(node_ids):
        return ([], "", "duplicate subquestion_id values are not allowed in a dependency graph")

    resolved_rsid = research_spec_id if research_spec_id is not None else (next(iter(rsids)) if len(rsids) == 1 else "")
    if research_spec_id is None and len(rsids) > 1:
        return ([], "", "sub-questions span more than one ResearchSpec; a dependency graph binds to exactly one")
    id_errors = common.validate_identifier(resolved_rsid, "research_spec_id")
    if id_errors:
        return ([], "", "; ".join(id_errors))

    return (node_ids, resolved_rsid, None)


# --- T-07-04: dependency graph ----------------------------------------------


@dataclass(frozen=True)
class DependencyResult:
    """The deterministic, reason-coded outcome of a QuestionDependencyGraph command.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  The single proceed outcome (``graph_built``) carries an
    inert :class:`DependencyGraph` draft projection (``dependency_graph``) and its
    deterministic ``topological_order``.  A cycle / dangling outcome still carries
    the built draft (for review) with an empty topological order;
    ``dangling_endpoints`` lists any edge endpoints that were not declared nodes.
    ``binding`` records the exact facts considered so the decision can be audited.
    The result is inert reviewable data — never persisted, emitted, marked
    authoritative, or treated as authorization.
    """

    status: str
    reason_code: str
    message: str
    dependency_graph: dict[str, Any] | None = None
    topological_order: list[str] = field(default_factory=list)
    dangling_endpoints: list[str] = field(default_factory=list)
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def graph_built(self) -> bool:
        """The single proceed-with-data outcome (an inert DependencyGraph draft)."""
        return self.status == STATUS_GRAPH_BUILT

    @property
    def has_cycle(self) -> bool:
        return self.status == STATUS_CYCLE_DETECTED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the result (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "graph_built": self.graph_built,
            "has_cycle": self.has_cycle,
            "dependency_graph": copy.deepcopy(self.dependency_graph) if self.dependency_graph is not None else None,
            "topological_order": list(self.topological_order),
            "dangling_endpoints": list(self.dangling_endpoints),
            "binding": copy.deepcopy(self.binding),
        }


def build_dependency_graph(subquestions: Any, relations: Any = None, *, research_spec_id: str | None = None) -> DependencyResult:
    """Build an inert draft sub-question dependency graph, fail-closed (T-07-04).

    A pure, deterministic function returning a bounded :class:`DependencyResult`
    (it never raises for a domain condition, never mutates its inputs, and performs
    no I/O, clock read, LLM/provider call, persistence, or event emission).

    ``subquestions`` is a list of draft :class:`SubQuestion` instances, mapping
    projections, or bare id strings.  Edges are derived **only** from explicit
    dependencies: each sub-question's ``parent_subquestion_id`` (the child depends
    on its parent) plus any explicit ``relations`` pairs (``[from, to]`` meaning
    "from depends on to").  ``research_spec_id`` may be supplied for bare-id nodes;
    otherwise it is taken from the sub-questions (which must agree).  Precedence:

    1. **Input** — a non-sequence, an unrecognised sub-question shape, a
       blank/duplicate node id, sub-questions spanning multiple specs, a malformed
       relation, or a missing/invalid research-spec id → ``rejected_malformed``.
    2. **Dangling endpoint** — an edge naming a node that was not declared →
       ``dangling_node`` (never silently dropped).
    3. **Cycle** — a cyclic dependency (including a self-dependency) →
       ``cycle_detected`` (reusing :meth:`DependencyGraph.has_cycle`).
    4. Otherwise a valid DAG → ``graph_built`` carrying the inert graph draft and
       its deterministic :meth:`DependencyGraph.topological_order`.
    """
    binding: dict[str, Any] = {
        "subquestions_kind": type(subquestions).__name__,
        "relations_kind": type(relations).__name__,
    }

    def _result(
        code: str,
        message: str,
        *,
        dependency_graph: dict[str, Any] | None = None,
        topological_order: list[str] | None = None,
        dangling_endpoints: list[str] | None = None,
    ) -> DependencyResult:
        return DependencyResult(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            dependency_graph=dependency_graph,
            topological_order=list(topological_order or []),
            dangling_endpoints=list(dangling_endpoints or []),
            binding=dict(binding),
        )

    # 1. Resolve the node set + bound spec, fail closed.
    node_ids, rsid, error = _resolve_nodes(subquestions, research_spec_id)
    if error is not None:
        return _result(CODE_INPUT_MALFORMED, error)
    binding["research_spec_id"] = rsid
    binding["node_count"] = len(node_ids)

    # 2. Derive edges from explicit parent links, then explicit relation pairs.
    edges: list[list[str]] = []
    for item in subquestions:
        fields = _subquestion_fields(item)
        assert fields is not None  # already validated in _resolve_nodes
        sqid, parent, _rsid = fields
        if parent.strip():
            edges.append([sqid, parent])

    if relations is not None:
        if not isinstance(relations, (list, tuple)):
            return _result(CODE_INPUT_MALFORMED, f"relations must be a list/tuple, not {type(relations).__name__}")
        for idx, rel in enumerate(relations):
            pair = _relation_pair(rel)
            if pair is None:
                return _result(CODE_INPUT_MALFORMED, f"relations[{idx}] is not an explicit [from, to] dependency pair")
            edges.append([pair[0], pair[1]])

    # Order-preserving de-dupe of identical edges.
    edges = [list(e) for e in dict.fromkeys(tuple(e) for e in edges)]
    binding["edge_count"] = len(edges)

    # 3. Assemble the inert core DependencyGraph draft (no wall-clock timestamp).
    graph = DependencyGraph(research_spec_id=rsid, nodes=list(node_ids), edges=[list(e) for e in edges], created_at="")
    graph_dict = graph.to_dict()
    binding["dependency_graph_id"] = graph_dict.get("dependency_graph_id")

    # 4. Dangling edge endpoints (an edge naming an undeclared node) — reported,
    #    never dropped — before cycle detection, which only sees declared nodes.
    node_set = set(node_ids)
    dangling = sorted({endpoint for edge in edges for endpoint in edge if endpoint not in node_set})
    if dangling:
        return _result(
            CODE_DANGLING_ENDPOINT,
            f"dependency graph has {len(dangling)} edge endpoint(s) that are not declared sub-questions: {dangling}",
            dependency_graph=graph_dict,
            dangling_endpoints=dangling,
        )

    # 5. Cycle detection (reuse the core class; a self-dependency is a cycle).
    if graph.has_cycle():
        return _result(
            CODE_CYCLE_DETECTED,
            "dependency graph has a cycle; sub-question dependencies must be acyclic and cannot be auto-broken",
            dependency_graph=graph_dict,
        )

    # 6. Defence in depth: a self-produced graph must be internally valid.
    errors = validate_dependency_graph(graph_dict)
    if errors:
        return _result(CODE_GRAPH_MALFORMED, "; ".join(errors), dependency_graph=graph_dict)

    return _result(
        CODE_GRAPH_BUILT,
        "assembled an inert acyclic sub-question dependency graph from the explicit dependencies",
        dependency_graph=graph_dict,
        topological_order=graph.topological_order(),
    )


# --- T-07-09: coverage report -----------------------------------------------


@dataclass(frozen=True)
class CoverageReport:
    """An inert, bounded projection of sub-question coverage (local to this module).

    Records, for one ResearchSpec, which sub-questions are ``covered`` by an
    evidence-plan reference, which carry an explicit ``not_answered`` decision, and
    which are ``uncovered`` (neither — these block state advancement).  ``complete``
    is true only when there are no uncovered sub-questions.  It is a *draft*
    projection (``status == "draft"``, ``created_at == ""``): inert reviewable data,
    never persisted, versioned, emitted, or treated as authoritative.
    """

    research_spec_id: str
    subquestion_ids: list[str] = field(default_factory=list)
    covered: list[str] = field(default_factory=list)
    not_answered: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    complete: bool = False
    status: str = DRAFT_STATUS
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_spec_id": self.research_spec_id,
            "subquestion_ids": list(self.subquestion_ids),
            "covered": list(self.covered),
            "not_answered": list(self.not_answered),
            "uncovered": list(self.uncovered),
            "complete": self.complete,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CoverageResult:
    """The deterministic, reason-coded outcome of a coverage-check command (T-07-09).

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  ``coverage_complete`` is the proceed outcome (every
    sub-question is covered or explicitly not-answered); ``coverage_incomplete``
    is the fail-closed outcome carrying the ``uncovered`` sub-questions that MUST
    block advancement.  ``coverage_report`` is the inert :class:`CoverageReport`
    projection.  The result is inert reviewable data — never persisted, emitted,
    marked authoritative, or treated as authorization.
    """

    status: str
    reason_code: str
    message: str
    coverage_report: dict[str, Any] | None = None
    uncovered: list[str] = field(default_factory=list)
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def coverage_complete(self) -> bool:
        """The single proceed outcome: no uncovered sub-questions remain."""
        return self.status == STATUS_COVERAGE_COMPLETE

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "coverage_complete": self.coverage_complete,
            "coverage_report": copy.deepcopy(self.coverage_report) if self.coverage_report is not None else None,
            "uncovered": list(self.uncovered),
            "binding": copy.deepcopy(self.binding),
        }


def assess_coverage(
    subquestions: Any,
    evidence_plans: Any = None,
    not_answered: Any = None,
    *,
    research_spec_id: str | None = None,
) -> CoverageResult:
    """Assert every sub-question is covered or explicitly not-answered, fail-closed (T-07-09).

    A pure, deterministic function returning a bounded :class:`CoverageResult` (it
    never raises for a domain condition, never mutates its inputs, and performs no
    I/O, clock read, LLM/provider call, persistence, or event emission).

    ``subquestions`` is a list of draft :class:`SubQuestion` instances, mapping
    projections, or bare id strings.  ``evidence_plans`` is a list of
    :class:`EvidencePlan` instances, mapping projections, plain id lists, or id
    strings — a sub-question is *covered* when any plan reference names it via its
    ``subquestion_ids``.  ``not_answered`` is a list of ids (or mappings carrying a
    ``subquestion_id``) explicitly recorded as not-answered.  Precedence:

    1. **Input** — a non-sequence / unrecognised sub-question, plan, or
       not-answered shape (or a missing/invalid research-spec id) →
       ``rejected_malformed``.
    2. **Uncovered** — a sub-question with neither an evidence-plan reference nor a
       not-answered decision → ``coverage_incomplete`` (these ids MUST block state
       advancement).
    3. Otherwise every sub-question is accounted for → ``coverage_complete``.
    """
    binding: dict[str, Any] = {
        "subquestions_kind": type(subquestions).__name__,
        "evidence_plans_kind": type(evidence_plans).__name__,
        "not_answered_kind": type(not_answered).__name__,
    }

    def _result(code: str, message: str, *, coverage_report: dict[str, Any] | None = None, uncovered: list[str] | None = None) -> CoverageResult:
        return CoverageResult(
            status=_CODE_STATUS[code],
            reason_code=code,
            message=message,
            coverage_report=coverage_report,
            uncovered=list(uncovered or []),
            binding=dict(binding),
        )

    node_ids, rsid, error = _resolve_nodes(subquestions, research_spec_id)
    if error is not None:
        return _result(CODE_INPUT_MALFORMED, error)
    binding["research_spec_id"] = rsid
    binding["node_count"] = len(node_ids)

    # Collect the ids referenced by every evidence-plan reference.
    covered_ids: set[str] = set()
    if evidence_plans is not None:
        if not isinstance(evidence_plans, (list, tuple)):
            return _result(CODE_INPUT_MALFORMED, f"evidence_plans must be a list/tuple, not {type(evidence_plans).__name__}")
        for idx, plan in enumerate(evidence_plans):
            ids = _plan_subquestion_ids(plan)
            if ids is None:
                return _result(CODE_INPUT_MALFORMED, f"evidence_plans[{idx}] is not an EvidencePlan, mapping, id list, or id string")
            covered_ids.update(ids)

    # Collect the ids explicitly recorded as not-answered.
    not_answered_ids: set[str] = set()
    if not_answered is not None:
        if not isinstance(not_answered, (list, tuple, set, frozenset)):
            return _result(CODE_INPUT_MALFORMED, f"not_answered must be a list/tuple/set, not {type(not_answered).__name__}")
        for idx, item in enumerate(not_answered):
            na_id = _not_answered_id(item)
            if na_id is None:
                return _result(CODE_INPUT_MALFORMED, f"not_answered[{idx}] is not an id string or a mapping carrying a subquestion_id")
            not_answered_ids.add(na_id)

    # A plan reference takes precedence over a not-answered decision for the same id.
    node_set = set(node_ids)
    covered = sorted(i for i in node_set if i in covered_ids)
    resolved_not_answered = sorted(i for i in node_set if i not in covered_ids and i in not_answered_ids)
    uncovered = sorted(i for i in node_set if i not in covered_ids and i not in not_answered_ids)

    report = CoverageReport(
        research_spec_id=rsid,
        subquestion_ids=sorted(node_ids),
        covered=covered,
        not_answered=resolved_not_answered,
        uncovered=uncovered,
        complete=not uncovered,
        status=DRAFT_STATUS,
        created_at="",
    ).to_dict()
    binding["covered_count"] = len(covered)
    binding["not_answered_count"] = len(resolved_not_answered)
    binding["uncovered_count"] = len(uncovered)

    if uncovered:
        return _result(
            CODE_COVERAGE_INCOMPLETE,
            f"{len(uncovered)} sub-question(s) have no evidence plan and no recorded not-answered decision; state advancement is blocked: {uncovered}",
            coverage_report=report,
            uncovered=uncovered,
        )
    return _result(
        CODE_COVERAGE_COMPLETE,
        "every sub-question has an evidence-plan reference or an explicit not-answered decision",
        coverage_report=report,
    )


__all__ = [
    "STATUS_GRAPH_BUILT",
    "STATUS_COVERAGE_COMPLETE",
    "STATUS_CYCLE_DETECTED",
    "STATUS_DANGLING_NODE",
    "STATUS_COVERAGE_INCOMPLETE",
    "STATUS_REJECTED_MALFORMED",
    "STATUSES",
    "CODE_GRAPH_BUILT",
    "CODE_COVERAGE_COMPLETE",
    "CODE_CYCLE_DETECTED",
    "CODE_DANGLING_ENDPOINT",
    "CODE_COVERAGE_INCOMPLETE",
    "CODE_INPUT_MALFORMED",
    "CODE_GRAPH_MALFORMED",
    "REASON_CODES",
    "DRAFT_STATUS",
    "DependencyResult",
    "CoverageReport",
    "CoverageResult",
    "build_dependency_graph",
    "assess_coverage",
]
