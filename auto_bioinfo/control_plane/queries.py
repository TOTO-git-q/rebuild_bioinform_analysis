"""Read-only control-plane query layer (WP-04b / T-04-02).

The companion to the :mod:`~auto_bioinfo.control_plane.create_project` command
slice: where that *records* a project, this *reads* one back. Every function
here is a pure projection over the authoritative append-only event log and the
typed object records WP-04a persisted — it never creates, advances, or mutates a
project. Concretely it offers four local (in-process, non-HTTP) queries:

- :func:`get_project` — a deterministic single-project summary (identity,
  verbatim-request ref/hash, bound policy ref, rebuilt stage/state id,
  timestamps, projection drift, and the current blocker summary);
- :func:`query_timeline` — the project's events in canonical append order with
  simple ``limit``/``offset`` pagination;
- :func:`list_projects` — the projects under a root directory, deterministic and
  paginated, with non-project / malformed entries reported rather than silently
  treated as projects;
- :func:`project_blockers` — the current blocking items derived **only** from
  existing state/projection facts (projection drift, safe-stop terminals, or
  ``HUMAN_REVIEW_REQUIRED``); it invents no business facts.

All state is rebuilt through the existing core helpers (``load_state``,
``load_events``, ``verify_projection``) and object records (``read_object``), so
the answers stay consistent with the event store rather than introducing a
parallel read model. This slice deliberately does **not** implement approval
lifecycle, policy/gate decisions, an HTTP API, or a CLI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..core.state import TERMINAL_STAGES
from ..core.store import load_events, load_state, verify_projection
from ..execution.objects import read_object
from .create_project import ORIGINAL_REQUEST_OBJECT, PROJECT_OBJECT, PROJECT_POLICY_OBJECT

# A project's authoritative existence is its append-only log; the snapshot is
# only a cache (ADR-0003), so this — not ``project_state.json`` — is the file
# that decides whether a directory *is* a project for query purposes.
_EVENTS_RELPATH = ("state", "events.jsonl")

# A recoverable pause that still blocks forward progress until a human acts.
HUMAN_REVIEW_STAGE = "HUMAN_REVIEW_REQUIRED"
# Terminals that mean "stopped without a clean success" — every legal terminal
# except COMPLETED. Reaching one is a blocker to surface; COMPLETED is not.
SAFE_STOP_STAGES = frozenset(TERMINAL_STAGES) - {"COMPLETED"}

# Blocker kinds (stable strings so callers/tests can switch on them).
BLOCKER_PROJECTION_DRIFT = "PROJECTION_DRIFT"
BLOCKER_SNAPSHOT_MISSING = "SNAPSHOT_MISSING"
BLOCKER_HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
BLOCKER_SAFE_STOP_TERMINAL = "SAFE_STOP_TERMINAL"


class ProjectQueryError(RuntimeError):
    """A control-plane query could not be answered (bad input or bad path)."""


class ProjectNotFoundError(ProjectQueryError):
    """The given directory is not a queryable project (no event log present)."""


# --- Result projections ------------------------------------------------------


@dataclass
class BlockerItem:
    """One current blocking fact about a project.

    ``kind`` is one of the ``BLOCKER_*`` constants; ``stage`` is the project's
    current stage; ``detail`` is a human-readable summary; ``fields`` lists the
    specific drifting field names for a projection-drift blocker (empty
    otherwise). No business semantics are invented — every blocker is derived
    from an existing state/projection fact.
    """

    kind: str
    stage: str
    detail: str
    fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectSummary:
    """A deterministic single-project projection.

    Every field is reconstructed from the persisted record (object files plus
    the rebuilt event-log projection), so the same project always summarises to
    the same value. ``drift`` is the raw :func:`verify_projection` report;
    ``blockers`` is the derived current blocker summary; ``is_blocked`` is the
    convenience predicate ``bool(blockers)``.
    """

    project_id: str
    title: str
    request_id: str
    original_request_ref: str
    original_request_hash: str
    active_policy_id: str
    active_policy_ref: str
    current_stage: str
    project_state_id: str
    created_at: str
    updated_at: str
    drift: list[dict[str, Any]]
    blockers: list[BlockerItem]

    @property
    def is_blocked(self) -> bool:
        return bool(self.blockers)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_blocked"] = self.is_blocked
        return data


@dataclass
class TimelineEntry:
    """One event in a project's timeline, projected to its stable fields.

    ``seq`` is the event's absolute 0-based position in the append-only log, so
    entries stay identifiable across pages.
    """

    seq: int
    event_id: str
    event_type: str
    actor: str
    created_at: str
    previous_stage: str
    next_stage: str
    message: str
    object_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectListEntry:
    """A project's at-a-glance row in a list query."""

    project_id: str
    title: str
    current_stage: str
    project_state_id: str
    blocker_count: int
    path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkippedEntry:
    """A directory that was *not* counted as a project, with the reason why.

    Reporting these explicitly (rather than silently dropping or, worse,
    treating them as empty projects) is required by the WO so a malformed or
    non-project directory can never masquerade as a successful project.
    """

    name: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Page:
    """A deterministic slice of a larger ordered result set.

    ``items`` is the requested window; ``total`` is the full count before
    pagination; ``limit`` (``None`` means "all from ``offset``") and ``offset``
    echo the request so a caller can compute the next page.
    """

    items: list[Any]
    total: int
    limit: int | None
    offset: int

    @property
    def returned(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() if hasattr(item, "to_dict") else item for item in self.items],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "returned": self.returned,
        }


@dataclass
class ProjectListPage(Page):
    """A page of :class:`ProjectListEntry` plus the directories that were
    skipped (non-project or malformed), so the caller sees both what counted and
    what did not."""

    skipped: list[SkippedEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["skipped"] = [entry.to_dict() for entry in self.skipped]
        return data


# --- Internal helpers --------------------------------------------------------


def _events_file(project_dir: Path) -> Path:
    return project_dir.joinpath(*_EVENTS_RELPATH)


def _is_project_dir(project_dir: Path) -> bool:
    """A directory is queryable iff its append-only event log exists.

    Checked by direct filesystem probe — *not* by calling ``load_events`` —
    because the store helpers ``mkdir`` the ``state/`` directory as a side
    effect, which would mutate a non-project directory during a read.
    """
    return project_dir.is_dir() and _events_file(project_dir).is_file()


def _validate_pagination(limit: int | None, offset: int) -> None:
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ProjectQueryError(f"offset must be a non-negative int, got {offset!r}")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 0):
        raise ProjectQueryError(f"limit must be None or a non-negative int, got {limit!r}")


def _paginate(items: list[Any], limit: int | None, offset: int) -> tuple[list[Any], int]:
    _validate_pagination(limit, offset)
    total = len(items)
    window = items[offset:] if limit is None else items[offset : offset + limit]
    return window, total


def _drift_findings(project_dir: Path) -> tuple[list[dict[str, Any]], bool]:
    """Return ``(drift findings, snapshot_missing)``.

    ``verify_projection`` needs the snapshot to compare against; a missing
    snapshot is itself a form of drift (the cache is gone), so it is reported as
    a flag rather than raised — the project is still fully describable from its
    log.
    """
    try:
        return verify_projection(project_dir), False
    except FileNotFoundError:
        return [], True


def _blockers_from_facts(stage: str, drift: list[dict[str, Any]], snapshot_missing: bool) -> list[BlockerItem]:
    """Derive the current blockers from already-established facts only."""
    blockers: list[BlockerItem] = []
    if snapshot_missing:
        blockers.append(
            BlockerItem(
                kind=BLOCKER_SNAPSHOT_MISSING,
                stage=stage,
                detail="project_state.json snapshot is missing; the cached projection cannot be cross-checked against the event log",
            )
        )
    if drift:
        fields = sorted({str(item.get("field", "")) for item in drift if item.get("field")})
        blockers.append(
            BlockerItem(
                kind=BLOCKER_PROJECTION_DRIFT,
                stage=stage,
                detail=f"cached snapshot diverges from the event-log projection on {len(drift)} field(s): {', '.join(fields)}",
                fields=fields,
            )
        )
    if stage == HUMAN_REVIEW_STAGE:
        blockers.append(
            BlockerItem(
                kind=BLOCKER_HUMAN_REVIEW_REQUIRED,
                stage=stage,
                detail="project is paused awaiting human review",
            )
        )
    elif stage in SAFE_STOP_STAGES:
        blockers.append(
            BlockerItem(
                kind=BLOCKER_SAFE_STOP_TERMINAL,
                stage=stage,
                detail=f"project stopped at safe-stop terminal stage {stage!r} without a clean completion",
            )
        )
    return blockers


# --- Public queries ----------------------------------------------------------


def project_blockers(project_dir: str | Path) -> list[BlockerItem]:
    """Return the project's current blocking items (read-only).

    Blocker sources are limited, by design, to existing state/projection facts:
    projection drift (or a missing snapshot) from :func:`verify_projection`, the
    recoverable ``HUMAN_REVIEW_REQUIRED`` pause, and the safe-stop terminal
    stages. No approval lifecycle or gate-policy decision is implied.
    """
    path = Path(project_dir)
    if not _is_project_dir(path):
        raise ProjectNotFoundError(f"not a queryable project (no event log at {_events_file(path)})")
    stage = load_state(path).get("current_stage", "")
    drift, snapshot_missing = _drift_findings(path)
    return _blockers_from_facts(stage, drift, snapshot_missing)


def get_project(project_dir: str | Path) -> ProjectSummary:
    """Return a deterministic :class:`ProjectSummary` for one project (read-only).

    Raises :class:`ProjectNotFoundError` when ``project_dir`` has no event log.
    The stage and state id come from the rebuilt log projection (not the cached
    snapshot), so a stale or tampered ``project_state.json`` cannot change the
    answer — any divergence instead surfaces in ``drift``/``blockers``.
    """
    path = Path(project_dir)
    if not _is_project_dir(path):
        raise ProjectNotFoundError(f"not a queryable project (no event log at {_events_file(path)})")

    state = load_state(path)
    project = read_object(path, PROJECT_OBJECT, {}) or {}
    request = read_object(path, ORIGINAL_REQUEST_OBJECT, {}) or {}
    policy = read_object(path, PROJECT_POLICY_OBJECT, {}) or {}

    request_id = request.get("request_id", "")
    if not request_id:
        request_ids = project.get("request_ids") or []
        request_id = request_ids[0] if request_ids else ""

    stage = state.get("current_stage", "")
    drift, snapshot_missing = _drift_findings(path)
    blockers = _blockers_from_facts(stage, drift, snapshot_missing)

    return ProjectSummary(
        project_id=state.get("project_id", path.name),
        title=project.get("title", ""),
        request_id=request_id,
        original_request_ref=f"state/objects/{ORIGINAL_REQUEST_OBJECT}.json",
        original_request_hash=request.get("original_text_sha256", ""),
        active_policy_id=project.get("active_policy_id", "") or policy.get("project_policy_id", ""),
        active_policy_ref=f"state/objects/{PROJECT_POLICY_OBJECT}.json",
        current_stage=stage,
        project_state_id=state.get("project_state_id", ""),
        created_at=project.get("created_at", ""),
        updated_at=state.get("updated_at", ""),
        drift=drift,
        blockers=blockers,
    )


def query_timeline(project_dir: str | Path, *, limit: int | None = None, offset: int = 0) -> Page:
    """Return the project's events in canonical append order, paginated (read-only).

    Ordering is the append-only log order (the causal order events were
    recorded), which is fully deterministic for a given log; ``limit``/``offset``
    select a stable window over it. Raises :class:`ProjectNotFoundError` when the
    directory has no event log, and :class:`ProjectQueryError` on bad pagination.
    """
    path = Path(project_dir)
    if not _is_project_dir(path):
        raise ProjectNotFoundError(f"not a queryable project (no event log at {_events_file(path)})")

    entries = [
        TimelineEntry(
            seq=index,
            event_id=event.get("event_id", ""),
            event_type=event.get("event_type", ""),
            actor=event.get("actor", ""),
            created_at=event.get("created_at", ""),
            previous_stage=event.get("previous_stage", ""),
            next_stage=event.get("next_stage", ""),
            message=event.get("message", ""),
            object_refs=list(event.get("object_refs") or []),
        )
        for index, event in enumerate(load_events(path))
    ]
    window, total = _paginate(entries, limit, offset)
    return Page(items=window, total=total, limit=limit, offset=offset)


def list_projects(root_dir: str | Path, *, limit: int | None = None, offset: int = 0) -> ProjectListPage:
    """List the projects directly under ``root_dir``, deterministic and paginated.

    Immediate child directories are scanned in sorted-name order. A child counts
    as a project only when it carries an event log *and* that log rebuilds into a
    valid state; anything else (a plain directory, a file, or a directory whose
    log is corrupt/empty) is reported in ``skipped`` with a reason instead of
    being passed off as a project. The probe never writes to the scanned
    directories. Raises :class:`ProjectQueryError` for a missing/invalid root or
    bad pagination.
    """
    root = Path(root_dir)
    if not root.is_dir():
        raise ProjectQueryError(f"root_dir is not a directory: {root}")

    valid: list[ProjectListEntry] = []
    skipped: list[SkippedEntry] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            skipped.append(SkippedEntry(name=child.name, reason="not a directory"))
            continue
        if not _is_project_dir(child):
            skipped.append(SkippedEntry(name=child.name, reason="no event log (not a project)"))
            continue
        try:
            summary = get_project(child)
        except ProjectQueryError as exc:
            skipped.append(SkippedEntry(name=child.name, reason=f"malformed project: {exc}"))
            continue
        except (ValueError, KeyError) as exc:
            # rebuild_state / object reads fail closed on a corrupt log; surface
            # that as a skipped entry rather than crashing the whole listing.
            skipped.append(SkippedEntry(name=child.name, reason=f"corrupt project: {exc}"))
            continue
        valid.append(
            ProjectListEntry(
                project_id=summary.project_id,
                title=summary.title,
                current_stage=summary.current_stage,
                project_state_id=summary.project_state_id,
                blocker_count=len(summary.blockers),
                path=str(child),
            )
        )

    window, total = _paginate(valid, limit, offset)
    return ProjectListPage(items=window, total=total, limit=limit, offset=offset, skipped=skipped)
