"""RBAC hardening: separation-of-duties over the merged auth contract (WP-23 / T-23-01, T-23-02, T-23-08).

The base RBAC contract (:mod:`auto_bioinfo.control_plane.auth_rbac`) already
decides *"may this actor's roles perform this action on this resource?"*.  This
module layers the requirement spec's remaining hardening rules **on top of** that
decision, without reimplementing it:

- **Separation of duties (T-23-02).** An actor may never approve or review their
  own submission, and an executor may never review their own execution output —
  even when their role would otherwise permit the review/approval action.  Self-
  approval / self-review fail closed regardless of role.
- **Minimum-permission role matrix (T-23-02).** A small, explicit
  researcher / reviewer / operator / admin capability matrix that states, per role,
  which *capabilities* are the minimum each needs.  A capability an actor's roles
  do not include is denied.
- **Cross-project isolation (T-23-01).** A request whose actor is scoped to a
  different project than the resource is denied (defence in depth over the base
  contract's project-scoped grants).
- **Audit-log access control (T-23-08).** Reading sensitive audit payload or
  modifying the audit log is restricted; an ordinary (non-privileged) actor is
  denied, and *no* role may mutate the append-only audit log.

Everything here is a pure, deterministic decision over explicit in-memory facts —
no identity provider, token, session, or clock.  A decision is a bounded *value*.

It reuses the base contract's :func:`~auto_bioinfo.control_plane.auth_rbac.authorize`
and its :class:`AccessRequest` / :class:`Principal` shapes so the two layers agree
on identity and never drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..control_plane import auth_rbac
from ..control_plane.auth_rbac import (
    AccessRequest,
    AuthorizationPolicy,
    Principal,
)

# --- Bounded role catalogue --------------------------------------------------
ROLE_RESEARCHER = "researcher"
ROLE_REVIEWER = "reviewer"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"

ROLES = (ROLE_RESEARCHER, ROLE_REVIEWER, ROLE_OPERATOR, ROLE_ADMIN)

# --- Bounded capability catalogue (minimum-permission matrix) ----------------
# Capabilities are coarse product verbs (distinct from auth_rbac ACTIONS, which
# name control-plane entry points); this matrix states the *least* each role needs.
CAP_SUBMIT = "submit"  # create/submit a research request or artifact for review
CAP_REVIEW = "review"  # review another actor's submission / QC finding
CAP_APPROVE = "approve"  # grant a gate approval on another actor's submission
CAP_OPERATE = "operate"  # run/cancel operational commands (queues, workers)
CAP_READ_AUDIT = "read_audit"  # read audit records (non-sensitive projection)
CAP_READ_AUDIT_SENSITIVE = "read_audit_sensitive"  # read sensitive audit payload
CAP_ADMINISTER = "administer"  # manage roles/policy

CAPABILITIES = (
    CAP_SUBMIT,
    CAP_REVIEW,
    CAP_APPROVE,
    CAP_OPERATE,
    CAP_READ_AUDIT,
    CAP_READ_AUDIT_SENSITIVE,
    CAP_ADMINISTER,
)

# The minimum-permission matrix.  Each role maps to exactly the capabilities it
# needs — deliberately least-privilege (a researcher cannot review/approve their
# own or others' work; only admin holds sensitive-audit + administer).
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    ROLE_RESEARCHER: frozenset({CAP_SUBMIT, CAP_READ_AUDIT}),
    ROLE_REVIEWER: frozenset({CAP_REVIEW, CAP_APPROVE, CAP_READ_AUDIT}),
    ROLE_OPERATOR: frozenset({CAP_OPERATE, CAP_READ_AUDIT}),
    ROLE_ADMIN: frozenset({CAP_OPERATE, CAP_READ_AUDIT, CAP_READ_AUDIT_SENSITIVE, CAP_ADMINISTER}),
}

# Capabilities that are, by nature, a review/approval of someone else's work; a
# request for one of these on a resource the actor *authored* is self-review.
_SEPARATION_CAPABILITIES = frozenset({CAP_REVIEW, CAP_APPROVE})

# --- Bounded status + reason vocabulary --------------------------------------
STATUS_ALLOW = "allow"
STATUS_DENY = "deny"
STATUS_INVALID = "invalid"

STATUSES = (STATUS_ALLOW, STATUS_DENY, STATUS_INVALID)

CODE_ALLOW = "SOD_ALLOW"
CODE_SELF_APPROVAL = "SOD_SELF_APPROVAL_BLOCKED"
CODE_SELF_REVIEW = "SOD_SELF_REVIEW_BLOCKED"
CODE_MISSING_CAPABILITY = "SOD_MISSING_CAPABILITY"
CODE_CROSS_PROJECT = "SOD_CROSS_PROJECT_BLOCKED"
CODE_AUDIT_IMMUTABLE = "SOD_AUDIT_LOG_IMMUTABLE"
CODE_AUDIT_NOT_PRIVILEGED = "SOD_AUDIT_ACCESS_DENIED"
CODE_BASE_NOT_ALLOWED = "SOD_BASE_RBAC_NOT_ALLOWED"
CODE_MALFORMED = "SOD_MALFORMED"
CODE_UNKNOWN_ROLE = "SOD_UNKNOWN_ROLE"
CODE_UNKNOWN_CAPABILITY = "SOD_UNKNOWN_CAPABILITY"

REASON_CODES = (
    CODE_ALLOW,
    CODE_SELF_APPROVAL,
    CODE_SELF_REVIEW,
    CODE_MISSING_CAPABILITY,
    CODE_CROSS_PROJECT,
    CODE_AUDIT_IMMUTABLE,
    CODE_AUDIT_NOT_PRIVILEGED,
    CODE_BASE_NOT_ALLOWED,
    CODE_MALFORMED,
    CODE_UNKNOWN_ROLE,
    CODE_UNKNOWN_CAPABILITY,
)

_CODE_STATUS = {
    CODE_ALLOW: STATUS_ALLOW,
    CODE_SELF_APPROVAL: STATUS_DENY,
    CODE_SELF_REVIEW: STATUS_DENY,
    CODE_MISSING_CAPABILITY: STATUS_DENY,
    CODE_CROSS_PROJECT: STATUS_DENY,
    CODE_AUDIT_IMMUTABLE: STATUS_DENY,
    CODE_AUDIT_NOT_PRIVILEGED: STATUS_DENY,
    CODE_BASE_NOT_ALLOWED: STATUS_DENY,
    CODE_MALFORMED: STATUS_INVALID,
    CODE_UNKNOWN_ROLE: STATUS_INVALID,
    CODE_UNKNOWN_CAPABILITY: STATUS_INVALID,
}


def capabilities_for_roles(roles: Any) -> frozenset[str]:
    """The union of minimum capabilities granted by ``roles`` (unknown roles ignored)."""
    granted: set[str] = set()
    if isinstance(roles, (tuple, list)):
        for role in roles:
            granted |= ROLE_CAPABILITIES.get(role, frozenset())
    return frozenset(granted)


@dataclass(frozen=True)
class HardeningDecision:
    """A bounded, reason-coded separation-of-duties / capability decision."""

    status: str
    reason_code: str
    message: str
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.status == STATUS_ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "allowed": self.allowed,
            "binding": dict(self.binding),
        }


@dataclass(frozen=True)
class SubmissionRef:
    """The submission/artifact a review or approval targets.

    ``author_id`` is the actor who authored/produced it; ``project`` its project.
    Separation of duties compares this against the requesting actor.
    """

    submission_id: str
    author_id: str
    project: str

    def to_dict(self) -> dict[str, Any]:
        return {"submission_id": self.submission_id, "author_id": self.author_id, "project": self.project}


def evaluate_capability(roles: Any, capability: Any) -> HardeningDecision:
    """Decide whether ``roles`` include the minimum ``capability`` (T-23-02), fail-closed.

    A pure least-privilege check against :data:`ROLE_CAPABILITIES`.  An unknown
    role or an unknown capability fails closed to ``invalid``; a capability none of
    the actor's roles grant is ``deny``.
    """
    if not isinstance(roles, (tuple, list)) or not roles:
        return HardeningDecision(STATUS_INVALID, CODE_MALFORMED, "roles must be a non-empty sequence of role names", binding={"roles": roles})
    for role in roles:
        if role not in ROLE_CAPABILITIES:
            return HardeningDecision(STATUS_INVALID, CODE_UNKNOWN_ROLE, f"role {role!r} is not a known role", binding={"roles": sorted(str(r) for r in roles)})
    if capability not in CAPABILITIES:
        return HardeningDecision(
            STATUS_INVALID, CODE_UNKNOWN_CAPABILITY, f"capability {capability!r} is not a known capability", binding={"capability": capability}
        )
    granted = capabilities_for_roles(roles)
    binding = {"roles": sorted(str(r) for r in roles), "capability": capability, "granted_capabilities": sorted(granted)}
    if capability in granted:
        return HardeningDecision(STATUS_ALLOW, CODE_ALLOW, f"roles grant the minimum capability {capability!r}", binding=binding)
    return HardeningDecision(
        STATUS_DENY, CODE_MISSING_CAPABILITY, f"none of the actor's roles grant capability {capability!r} (least privilege, fail closed)", binding=binding
    )


def evaluate_separation_of_duties(
    principal: Any,
    capability: Any,
    submission: Any,
) -> HardeningDecision:
    """Enforce self-review / self-approval separation of duties (T-23-02), fail-closed.

    For a review/approval capability (:data:`_SEPARATION_CAPABILITIES`), the actor
    must (a) hold the capability via their roles, (b) belong to the submission's
    project, and (c) **not** be the submission's author.  An actor reviewing or
    approving their own work is denied even when their role would allow the action.
    For a non-separation capability this reduces to the capability check.
    """
    if not isinstance(principal, Principal):
        return HardeningDecision(STATUS_INVALID, CODE_MALFORMED, "principal must be an auth_rbac.Principal", binding={})
    if not isinstance(submission, SubmissionRef) or not submission.submission_id or not submission.author_id or not submission.project:
        return HardeningDecision(STATUS_INVALID, CODE_MALFORMED, "submission must be a fully-populated SubmissionRef", binding={"actor_id": principal.actor_id})

    cap_decision = evaluate_capability(principal.roles, capability)
    binding = {
        "actor_id": principal.actor_id,
        "roles": sorted(str(r) for r in principal.roles),
        "capability": capability,
        "submission_id": submission.submission_id,
        "author_id": submission.author_id,
        "project": submission.project,
    }
    if not cap_decision.allowed:
        # Carry the capability decision's code/status through (deny or invalid).
        return HardeningDecision(cap_decision.status, cap_decision.reason_code, cap_decision.message, binding=binding)

    if capability in _SEPARATION_CAPABILITIES:
        if principal.actor_id == submission.author_id:
            code = CODE_SELF_APPROVAL if capability == CAP_APPROVE else CODE_SELF_REVIEW
            verb = "approve" if capability == CAP_APPROVE else "review"
            return HardeningDecision(
                STATUS_DENY,
                code,
                f"actor {principal.actor_id!r} may not {verb} their own submission {submission.submission_id!r} (separation of duties, fail closed)",
                binding=binding,
            )

    return HardeningDecision(STATUS_ALLOW, CODE_ALLOW, f"separation of duties satisfied for capability {capability!r}", binding=binding)


def evaluate_cross_project(actor_project: Any, resource_project: Any) -> HardeningDecision:
    """Deny access when the actor's project scope differs from the resource's (T-23-01)."""
    if not isinstance(actor_project, str) or not actor_project or not isinstance(resource_project, str) or not resource_project:
        return HardeningDecision(STATUS_INVALID, CODE_MALFORMED, "actor_project and resource_project must be non-empty strings", binding={})
    binding = {"actor_project": actor_project, "resource_project": resource_project}
    if actor_project != resource_project:
        return HardeningDecision(
            STATUS_DENY,
            CODE_CROSS_PROJECT,
            f"actor scoped to project {actor_project!r} may not access a resource in project {resource_project!r} (cross-project, fail closed)",
            binding=binding,
        )
    return HardeningDecision(STATUS_ALLOW, CODE_ALLOW, "actor and resource share a project scope", binding=binding)


# Audit-log access modes.
AUDIT_READ = "read"
AUDIT_READ_SENSITIVE = "read_sensitive"
AUDIT_WRITE = "write"
AUDIT_ACCESS_MODES = (AUDIT_READ, AUDIT_READ_SENSITIVE, AUDIT_WRITE)


def evaluate_audit_access(roles: Any, mode: Any) -> HardeningDecision:
    """Gate audit-log access (T-23-08), fail-closed.

    The audit log is append-only, so **no** role may ``write`` (mutate) it — a
    write request is always denied as immutable.  Reading a non-sensitive audit
    projection requires ``read_audit``; reading sensitive payload requires the
    stricter ``read_audit_sensitive`` (admin only).  An ordinary actor lacking the
    capability is denied.
    """
    if mode not in AUDIT_ACCESS_MODES:
        return HardeningDecision(STATUS_INVALID, CODE_MALFORMED, f"mode must be one of {AUDIT_ACCESS_MODES!r}", binding={"mode": mode})
    if not isinstance(roles, (tuple, list)) or not roles:
        return HardeningDecision(STATUS_INVALID, CODE_MALFORMED, "roles must be a non-empty sequence", binding={"mode": mode})
    for role in roles:
        if role not in ROLE_CAPABILITIES:
            return HardeningDecision(STATUS_INVALID, CODE_UNKNOWN_ROLE, f"role {role!r} is not a known role", binding={"mode": mode})

    binding = {"roles": sorted(str(r) for r in roles), "mode": mode}
    if mode == AUDIT_WRITE:
        return HardeningDecision(STATUS_DENY, CODE_AUDIT_IMMUTABLE, "the audit log is append-only; no role may modify it (fail closed)", binding=binding)
    granted = capabilities_for_roles(roles)
    required = CAP_READ_AUDIT_SENSITIVE if mode == AUDIT_READ_SENSITIVE else CAP_READ_AUDIT
    if required not in granted:
        return HardeningDecision(
            STATUS_DENY,
            CODE_AUDIT_NOT_PRIVILEGED,
            f"audit {mode!r} requires capability {required!r}, which the actor's roles do not grant (fail closed)",
            binding=binding,
        )
    return HardeningDecision(STATUS_ALLOW, CODE_ALLOW, f"audit {mode!r} permitted", binding=binding)


def evaluate_hardened_access(
    request: Any,
    *,
    policy: AuthorizationPolicy,
    actor_project: str,
    current_version: int | None = None,
) -> HardeningDecision:
    """Compose the base RBAC decision with cross-project isolation (T-23-01).

    First runs the base :func:`auto_bioinfo.control_plane.auth_rbac.authorize`; a
    non-allow base decision is carried through as a hardened ``deny``/``invalid``.
    Only when the base contract allows does this add the cross-project check, so
    the hardened layer can only ever be *stricter* than the base contract, never
    looser.
    """
    if not isinstance(request, AccessRequest):
        return HardeningDecision(STATUS_INVALID, CODE_MALFORMED, "request must be an auth_rbac.AccessRequest", binding={})
    base = auth_rbac.authorize(request, policy=policy, current_version=current_version)
    binding = {"actor_project": actor_project, "base_status": base.status, "base_reason_code": base.reason_code, "base_binding": base.to_dict()["binding"]}
    if not base.allowed:
        status = STATUS_INVALID if base.status == auth_rbac.STATUS_INVALID else STATUS_DENY
        return HardeningDecision(status, CODE_BASE_NOT_ALLOWED, f"base RBAC did not allow the request ({base.reason_code})", binding=binding)
    resource_project = request.resource.project if request.resource is not None else ""
    cross = evaluate_cross_project(actor_project, resource_project)
    if not cross.allowed:
        return HardeningDecision(cross.status, cross.reason_code, cross.message, binding={**binding, **cross.binding})
    return HardeningDecision(
        STATUS_ALLOW, CODE_ALLOW, "base RBAC allowed and the actor shares the resource's project scope", binding={**binding, **cross.binding}
    )


def build_min_privilege_authority(_flags: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A helper returning an *empty* authority mapping (least privilege).

    Deliberately returns no privileged authority flag so a caller building a
    :class:`Principal` cannot accidentally assert a forbidden bypass authority.
    """
    return {}


__all__ = [
    "ROLE_RESEARCHER",
    "ROLE_REVIEWER",
    "ROLE_OPERATOR",
    "ROLE_ADMIN",
    "ROLES",
    "CAP_SUBMIT",
    "CAP_REVIEW",
    "CAP_APPROVE",
    "CAP_OPERATE",
    "CAP_READ_AUDIT",
    "CAP_READ_AUDIT_SENSITIVE",
    "CAP_ADMINISTER",
    "CAPABILITIES",
    "ROLE_CAPABILITIES",
    "STATUS_ALLOW",
    "STATUS_DENY",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_ALLOW",
    "CODE_SELF_APPROVAL",
    "CODE_SELF_REVIEW",
    "CODE_MISSING_CAPABILITY",
    "CODE_CROSS_PROJECT",
    "CODE_AUDIT_IMMUTABLE",
    "CODE_AUDIT_NOT_PRIVILEGED",
    "CODE_BASE_NOT_ALLOWED",
    "CODE_MALFORMED",
    "CODE_UNKNOWN_ROLE",
    "CODE_UNKNOWN_CAPABILITY",
    "REASON_CODES",
    "AUDIT_READ",
    "AUDIT_READ_SENSITIVE",
    "AUDIT_WRITE",
    "AUDIT_ACCESS_MODES",
    "capabilities_for_roles",
    "HardeningDecision",
    "SubmissionRef",
    "evaluate_capability",
    "evaluate_separation_of_duties",
    "evaluate_cross_project",
    "evaluate_audit_access",
    "evaluate_hardened_access",
    "build_min_privilege_authority",
]
