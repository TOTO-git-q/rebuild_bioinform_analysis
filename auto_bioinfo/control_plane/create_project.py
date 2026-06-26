"""CreateProject command handler (WP-04a / T-04-01).

The smallest control-plane slice that can create a project *locally and
auditably* out of an explicit command, reusing the existing core contracts and
event store rather than introducing a parallel mechanism:

- the user's request is stored **verbatim** as an immutable, hash-bound
  :class:`~auto_bioinfo.core.schemas.OriginalRequest` — normalisation/defaulting
  happens on a separate field and may never overwrite the original;
- the initial governance :class:`~auto_bioinfo.core.schemas.ProjectPolicy` is a
  versioned, content-hashable object, and the initial project state is bound to
  that exact policy reference;
- a project-created/intake event is recorded in the append-only event log
  (``PROJECT_STATE_INITIALIZED``) so the project's creation can be reconstructed
  from the timeline alone, without reading any chat history;
- the command is **idempotent**: a true retry (same key, identical payload)
  re-returns the recorded result without writing a second event, while a
  same-key conflicting payload fails closed — the same retry/conflict contract
  WP-03b established for the event store, applied at command granularity.

This handler only *records* a project; it never runs analysis, advances the
state machine past ``INTAKE``, locks a dataset, or authorises scientific output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..core.common import validate_identifier
from ..core.ids import hash_payload, make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION, OriginalRequest, Project, ProjectPolicy
from ..core.store import init_project_state, load_events, load_state
from ..core.validation import validate_original_request, validate_project_policy
from ..execution.objects import read_object, write_object

# Stable on-disk object names for the project's control-plane records.  They live
# alongside the planning objects under ``state/objects/`` (see
# :mod:`auto_bioinfo.execution.objects`).
ORIGINAL_REQUEST_OBJECT = "original_request"
PROJECT_POLICY_OBJECT = "project_policy"
PROJECT_OBJECT = "project"
# The recorded command, kept so a later retry can be recognised as a true replay
# (identical payload) or rejected as a same-key conflict (fail closed).
COMMAND_RECORD_OBJECT = "create_project_command"


class CreateProjectError(RuntimeError):
    """A CreateProject command could not be honoured (bad input or a clashing
    project already exists)."""


class CreateProjectConflict(CreateProjectError):
    """The command's idempotency key was reused with a *different* payload.

    Mirrors the event store's same-key conflict (WP-03b): a key may dedupe a true
    retry only; a conflicting reuse must fail closed rather than silently
    overwrite or fork the existing project."""


@dataclass
class CreateProjectCommand:
    """An explicit request to create a project.

    ``project_dir`` is the project's directory; its name is the ``project_id``
    (matching the event store's convention).  ``original_text`` is stored
    verbatim.  ``command_id`` is the optional explicit idempotency key; when
    empty a deterministic key is derived from the command's identity so two
    byte-identical commands still dedupe.
    """

    project_dir: str
    title: str
    original_text: str
    execution_mode: str = "DEMO"
    automation_level: str = "A0"
    policy_version: int = 1
    submitter: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    user_constraints: list[str] = field(default_factory=list)
    network_policy: dict[str, Any] = field(default_factory=dict)
    data_sensitivity: str = "unspecified"
    export_policy: dict[str, Any] = field(default_factory=dict)
    command_id: str = ""


@dataclass
class CreateProjectResult:
    """The deterministic, testable outcome of a CreateProject command.

    Every field is a reference into the persisted, append-only record: the
    project, its verbatim request, its bound policy, the projected state, and the
    initial creation event.  ``created`` is ``True`` only when this call wrote the
    project; ``idempotent_replay`` is ``True`` when the call recognised a prior
    identical command and returned the existing record unchanged.
    """

    project_id: str
    request_id: str
    project_policy_id: str
    project_state_id: str
    current_stage: str
    event_id: str
    idempotency_key: str
    created: bool
    idempotent_replay: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _command_identity(project_id: str, title: str, original_text: str, policy: dict[str, Any]) -> dict[str, Any]:
    """The facts that define "the same logical CreateProject".

    Two commands sharing an idempotency key are a true retry only when these
    match exactly; the policy is pinned by both its id and its content hash so a
    silent governance change is treated as a conflict, never a retry."""
    return {
        "project_id": project_id,
        "title": title,
        "original_text": original_text,
        "project_policy_id": policy.get("project_policy_id", ""),
        "policy_content_hash": policy.get("content_hash", ""),
    }


def _result(
    project_dir: Path,
    project_id: str,
    request: dict[str, Any],
    policy: dict[str, Any],
    key: str,
    *,
    created: bool,
    idempotent_replay: bool,
) -> CreateProjectResult:
    # The authoritative state and creation event come from the append-only log,
    # not the snapshot, so the result is reconstructable from the timeline alone.
    state = load_state(project_dir)
    events = load_events(project_dir)
    creation_event = events[0] if events else {}
    return CreateProjectResult(
        project_id=project_id,
        request_id=request.get("request_id", ""),
        project_policy_id=policy.get("project_policy_id", ""),
        project_state_id=state.get("project_state_id", ""),
        current_stage=state.get("current_stage", ""),
        event_id=creation_event.get("event_id", ""),
        idempotency_key=key,
        created=created,
        idempotent_replay=idempotent_replay,
    )


def _handle_existing(
    project_dir: Path,
    project_id: str,
    key: str,
    identity: dict[str, Any],
) -> CreateProjectResult:
    """A project already exists in ``project_dir``: decide retry vs. conflict."""
    record = read_object(project_dir, COMMAND_RECORD_OBJECT, {}) or {}
    if record.get("idempotency_key") == key:
        # Same key dedupes a true retry only — the payload must be identical.
        if record.get("identity_hash") == hash_payload(identity):
            existing_request = read_object(project_dir, ORIGINAL_REQUEST_OBJECT, {}) or {}
            existing_policy = read_object(project_dir, PROJECT_POLICY_OBJECT, {}) or {}
            return _result(project_dir, project_id, existing_request, existing_policy, key, created=False, idempotent_replay=True)
        raise CreateProjectConflict(
            f"idempotency_key {key!r} was reused with a different CreateProject payload; refusing to overwrite or fork the existing project (fail closed)"
        )
    raise CreateProjectError(
        f"project {project_id!r} already exists; refusing to recreate it with a different command (existing idempotency_key={record.get('idempotency_key')!r})"
    )


def create_project(command: CreateProjectCommand) -> CreateProjectResult:
    """Create a project from ``command`` and return a deterministic result.

    Raises :class:`CreateProjectError` on invalid input or a clashing existing
    project, and :class:`CreateProjectConflict` on a same-key conflicting retry.
    """
    project_dir = Path(command.project_dir)
    project_id = project_dir.name

    id_errors = validate_identifier(project_id, "project_id")
    if id_errors:
        raise CreateProjectError(f"invalid project directory name {project_id!r}: {'; '.join(id_errors)}")

    # Build the immutable contract objects up front so identity (and therefore the
    # idempotency key) is computed from the exact persisted facts.
    request = OriginalRequest(
        project_id=project_id,
        original_text=command.original_text,
        submitter=dict(command.submitter),
        attachments=[dict(a) for a in command.attachments],
        user_constraints=list(command.user_constraints),
    ).to_dict()
    policy = ProjectPolicy(
        project_id=project_id,
        execution_mode=command.execution_mode,
        automation_level=command.automation_level,
        policy_version=command.policy_version,
        network_policy=dict(command.network_policy),
        data_sensitivity=command.data_sensitivity,
        export_policy=dict(command.export_policy),
    ).to_dict()

    request_errors = validate_original_request(request)
    policy_errors = validate_project_policy(policy)
    if request_errors or policy_errors:
        raise CreateProjectError(f"invalid CreateProject command: {'; '.join(request_errors + policy_errors)}")

    identity = _command_identity(project_id, command.title, command.original_text, policy)
    key = command.command_id.strip() or make_stable_id("create_project_command", identity)

    # Idempotency: a project already initialised here is either a true retry or a
    # conflict.  Decided before any write so a retry never produces a second event.
    if load_events(project_dir):
        return _handle_existing(project_dir, project_id, key, identity)

    # Fresh creation. Persist the verbatim request and the versioned policy first.
    write_object(project_dir, ORIGINAL_REQUEST_OBJECT, request)
    write_object(project_dir, PROJECT_POLICY_OBJECT, policy)
    project = Project(
        project_id=project_id,
        title=command.title,
        current_stage="INTAKE",
        request_ids=[request["request_id"]],
        active_policy_id=policy["project_policy_id"],
    ).to_dict()
    write_object(project_dir, PROJECT_OBJECT, project)

    # Bind the initial ProjectState to the exact policy reference and anchor the
    # append-only log with the canonical project-created/intake event.  The
    # original request text is carried in the event payload so the project's
    # creation reconstructs from the timeline alone.
    init_project_state(
        project_dir,
        command.original_text,
        execution_mode=command.execution_mode,
        project_policy_ref=policy["project_policy_id"],
    )

    # Record the command so a later retry can be recognised (true replay) or
    # rejected (same-key conflict), without trusting any in-memory state.
    write_object(
        project_dir,
        COMMAND_RECORD_OBJECT,
        {
            "schema_version": CANONICAL_SCHEMA_VERSION,
            "idempotency_key": key,
            "identity": identity,
            "identity_hash": hash_payload(identity),
            "request_id": request["request_id"],
            "project_policy_id": policy["project_policy_id"],
        },
    )

    return _result(project_dir, project_id, request, policy, key, created=True, idempotent_replay=False)
