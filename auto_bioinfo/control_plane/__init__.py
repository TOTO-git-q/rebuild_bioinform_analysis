"""Control-plane command handlers (application layer, WP-04).

The control plane turns an explicit, validated *command* into auditable domain
state — persisted contract objects plus an append-only event — using the
existing core contracts (``auto_bioinfo.core``) and the on-disk event store.
It never runs analysis, locks a dataset, or authorises scientific output; it
only records intent and the facts needed to reconstruct a project's timeline.

WP-04a delivers the first slice: :func:`create_project`. WP-04b adds the
read-only query slice over the projects it records: :func:`get_project`,
:func:`query_timeline`, :func:`list_projects`, and :func:`project_blockers`.
WP-04e adds the local ApprovalRequest lifecycle (:func:`create_approval_request`,
:func:`cancel`, :func:`expire`, :func:`decide`).  WP-04f adds the pure, local
A0–A3 admission gate evaluator (:func:`evaluate_gate`) that reads a project's
policy and an optional approval record as data and returns a bounded,
reason-coded :class:`GateDecision`.  WP-04g adds the pure, local command API
idempotency / optimistic-concurrency contract (:func:`evaluate_command_request`)
that decides — without any I/O or HTTP surface — whether a mutating command may
be applied, replayed, or fails closed on a key conflict or stale version.
WP-04h adds the pure, local operation-resource state/result contract
(:func:`new_operation`, :func:`apply_transition`, :func:`project_operation`,
:func:`operation_from_command_result`) that models a long-running command's
operation as a deterministic, bounded lifecycle value — with no actual
asynchronous execution.  WP-04i adds the pure, local CLI command contract
foundation (:func:`run_cli`) that parses an explicit ``argv`` list deterministically
and maps it onto the existing command-API decision — with no real console, process
exit, subprocess, or entry-point side effect.  WP-04j adds the pure, local
cancel-command contract (:func:`evaluate_cancel_request`) that decides — without
touching any real worker/process/job — whether a tracked operation may move into
the bounded ``cancelled`` terminal state, projecting a cancelled operation value
only when the supplied operation state makes that transition valid.
"""

from __future__ import annotations

from .approval_lifecycle import (
    ApprovalLifecycleError,
    ApprovalLifecycleRecord,
    approve,
    cancel,
    create_approval_request,
    decide,
    expire,
    is_due,
    reject,
)
from .cancel_command import (
    CANCEL_COMMAND_TYPE,
    CancelCommand,
    CancelDecision,
    evaluate_cancel_request,
)
from .cli_contract import (
    CLI_REASON_CODES,
    CLI_STATUSES,
    COMMANDS,
    CliResult,
    OptionSpec,
    ParsedInvocation,
    SubcommandSpec,
    run_cli,
)
from .command_api import (
    CommandApiResult,
    CommandRecord,
    CommandRequest,
    ParsedHeaders,
    command_fingerprint,
    evaluate_command_request,
    parse_command_headers,
    record_for,
)
from .create_project import (
    CreateProjectCommand,
    CreateProjectConflict,
    CreateProjectError,
    CreateProjectResult,
    create_project,
)
from .gate_evaluator import (
    GATE_NAMES,
    OUTCOMES,
    REASON_CODES,
    GateDecision,
    GateEvaluationInput,
    evaluate_gate,
)
from .operation_resource import (
    ALLOWED_TRANSITIONS,
    ERROR_CODES,
    OPERATION_STATUSES,
    PROJECTION_CATEGORIES,
    OperationError,
    OperationProjection,
    OperationRecord,
    apply_transition,
    can_transition,
    is_operation_status,
    is_terminal_status,
    new_operation,
    operation_from_command_result,
    project_operation,
    validate_operation_record,
)
from .queries import (
    BlockerItem,
    Page,
    ProjectListEntry,
    ProjectListPage,
    ProjectNotFoundError,
    ProjectQueryError,
    ProjectSummary,
    SkippedEntry,
    TimelineEntry,
    get_project,
    list_projects,
    project_blockers,
    query_timeline,
)

__all__ = [
    "ApprovalLifecycleError",
    "ApprovalLifecycleRecord",
    "approve",
    "cancel",
    "create_approval_request",
    "decide",
    "expire",
    "is_due",
    "reject",
    "CANCEL_COMMAND_TYPE",
    "CancelCommand",
    "CancelDecision",
    "evaluate_cancel_request",
    "GATE_NAMES",
    "OUTCOMES",
    "REASON_CODES",
    "GateDecision",
    "GateEvaluationInput",
    "evaluate_gate",
    "ALLOWED_TRANSITIONS",
    "ERROR_CODES",
    "OPERATION_STATUSES",
    "PROJECTION_CATEGORIES",
    "OperationError",
    "OperationProjection",
    "OperationRecord",
    "apply_transition",
    "can_transition",
    "is_operation_status",
    "is_terminal_status",
    "new_operation",
    "operation_from_command_result",
    "project_operation",
    "validate_operation_record",
    "CommandApiResult",
    "CommandRecord",
    "CommandRequest",
    "ParsedHeaders",
    "command_fingerprint",
    "evaluate_command_request",
    "parse_command_headers",
    "record_for",
    "CLI_REASON_CODES",
    "CLI_STATUSES",
    "COMMANDS",
    "CliResult",
    "OptionSpec",
    "ParsedInvocation",
    "SubcommandSpec",
    "run_cli",
    "CreateProjectCommand",
    "CreateProjectConflict",
    "CreateProjectError",
    "CreateProjectResult",
    "create_project",
    "BlockerItem",
    "Page",
    "ProjectListEntry",
    "ProjectListPage",
    "ProjectNotFoundError",
    "ProjectQueryError",
    "ProjectSummary",
    "SkippedEntry",
    "TimelineEntry",
    "get_project",
    "list_projects",
    "project_blockers",
    "query_timeline",
]
