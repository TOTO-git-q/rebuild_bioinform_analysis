"""Control-plane command handlers (application layer, WP-04).

The control plane turns an explicit, validated *command* into auditable domain
state — persisted contract objects plus an append-only event — using the
existing core contracts (``auto_bioinfo.core``) and the on-disk event store.
It never runs analysis, locks a dataset, or authorises scientific output; it
only records intent and the facts needed to reconstruct a project's timeline.

WP-04a delivers the first slice: :func:`create_project`.
"""

from __future__ import annotations

from .create_project import (
    CreateProjectCommand,
    CreateProjectConflict,
    CreateProjectError,
    CreateProjectResult,
    create_project,
)

__all__ = [
    "CreateProjectCommand",
    "CreateProjectConflict",
    "CreateProjectError",
    "CreateProjectResult",
    "create_project",
]
