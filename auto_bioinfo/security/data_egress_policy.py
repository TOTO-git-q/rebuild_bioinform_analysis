"""Data-sensitivity classification and external-send policy (WP-23 / T-23-06, T-23-07, T-23-10).

Three requirement-spec controls, modelled as pure deterministic decisions over
in-memory facts:

- **Artifact sensitivity inheritance (T-23-06).** A produced artifact inherits at
  least the highest sensitivity of its inputs; a highly-sensitive input can never
  *automatically* yield a ``PUBLIC`` output.  Lowering sensitivity is a
  *downgrade* that requires an explicit approval.
- **External data-egress decision + field-level redaction (T-23-07).** When data
  would be sent to an external LLM / tool, each field is checked against the
  destination's maximum allowed sensitivity; a field above that ceiling is
  *blocked* (restricted data does not cross the boundary) or, when the field is
  marked maskable, replaced with a redaction marker.
- **Data lifecycle / lawful deletion guard (T-23-10).** An object that is bound to
  retained evidence / an audit link cannot be silently deleted; a deletion request
  fails closed unless a lawful tombstone with the required references is supplied.

All of this is inert policy: no network, no real send, no persistence, no clock.
"deciding to send" is a *value*; nothing is actually transmitted, and a
``PUBLIC``/``INTERNAL``/``RESTRICTED``/``SECRET`` label is a caller-supplied fact,
never real classified content.

Design constraints mirror the WP-04/WP-23 house style: pure, deterministic,
fail-closed, bounded status + reason-code vocabularies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..observability.redaction import REDACTED

# --- Ordered sensitivity lattice ---------------------------------------------
# A total order from least to most sensitive.  Comparisons use the rank, so a new
# level would slot in by rank rather than by ad-hoc string compare.
SENSITIVITY_PUBLIC = "PUBLIC"
SENSITIVITY_INTERNAL = "INTERNAL"
SENSITIVITY_RESTRICTED = "RESTRICTED"
SENSITIVITY_SECRET = "SECRET"

SENSITIVITY_LEVELS = (SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_RESTRICTED, SENSITIVITY_SECRET)
_RANK = {level: index for index, level in enumerate(SENSITIVITY_LEVELS)}


def is_sensitivity(value: Any) -> bool:
    return isinstance(value, str) and value in _RANK


def sensitivity_rank(level: str) -> int:
    """The ordinal rank of ``level`` (higher = more sensitive)."""
    return _RANK[level]


def max_sensitivity(levels: Any) -> str | None:
    """Return the most-sensitive level among ``levels``, or ``None`` if any is invalid.

    Fail closed: a single unrecognised level makes the whole set unusable.  An
    empty set has no floor, so it returns :data:`SENSITIVITY_PUBLIC` (the identity
    for a max over the lattice).
    """
    if not isinstance(levels, (list, tuple, set, frozenset)):
        return None
    result = SENSITIVITY_PUBLIC
    for level in levels:
        if not is_sensitivity(level):
            return None
        if _RANK[level] > _RANK[result]:
            result = level
    return result


# --- Bounded status + reason vocabulary --------------------------------------
STATUS_ALLOW = "allow"
STATUS_DENY = "deny"
STATUS_NEEDS_APPROVAL = "needs_approval"
STATUS_INVALID = "invalid"

STATUSES = (STATUS_ALLOW, STATUS_DENY, STATUS_NEEDS_APPROVAL, STATUS_INVALID)

# Inheritance:
CODE_INHERITED = "SENS_INHERITED"
# Downgrade:
CODE_DOWNGRADE_OK = "SENS_DOWNGRADE_APPROVED"
CODE_DOWNGRADE_NEEDS_APPROVAL = "SENS_DOWNGRADE_NEEDS_APPROVAL"
CODE_NOT_A_DOWNGRADE = "SENS_NOT_A_DOWNGRADE"
# External send:
CODE_SEND_ALLOWED = "EGRESS_DATA_ALLOWED"
CODE_SEND_BLOCKED = "EGRESS_DATA_BLOCKED"
# Deletion:
CODE_DELETE_ALLOWED = "DELETE_ALLOWED"
CODE_DELETE_BLOCKED_RETAINED = "DELETE_BLOCKED_RETAINED"
# Invalid (fail closed):
CODE_MALFORMED = "SENS_MALFORMED"

REASON_CODES = (
    CODE_INHERITED,
    CODE_DOWNGRADE_OK,
    CODE_DOWNGRADE_NEEDS_APPROVAL,
    CODE_NOT_A_DOWNGRADE,
    CODE_SEND_ALLOWED,
    CODE_SEND_BLOCKED,
    CODE_DELETE_ALLOWED,
    CODE_DELETE_BLOCKED_RETAINED,
    CODE_MALFORMED,
)


@dataclass(frozen=True)
class SensitivityDecision:
    """A bounded, reason-coded sensitivity/egress decision.

    ``level`` carries the resulting/derived sensitivity when relevant (the
    inherited artifact level, or the requested target level).  ``binding`` records
    the facts considered so the decision can be audited.
    """

    status: str
    reason_code: str
    message: str
    level: str = ""
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.status == STATUS_ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "level": self.level,
            "allowed": self.allowed,
            "binding": dict(self.binding),
        }


def inherit_artifact_sensitivity(input_levels: Any) -> SensitivityDecision:
    """Derive a produced artifact's sensitivity from its inputs (T-23-06).

    The output inherits the **maximum** sensitivity of its inputs, so a highly
    sensitive input can never automatically produce a lower-sensitivity artifact.
    A malformed level fails closed.  An artifact with no declared inputs inherits
    :data:`SENSITIVITY_PUBLIC` (the lattice floor) — a caller that wants a stricter
    default states it as an explicit input level.
    """
    inherited = max_sensitivity(input_levels)
    if inherited is None:
        return SensitivityDecision(
            status=STATUS_INVALID,
            reason_code=CODE_MALFORMED,
            message=f"input_levels must be a collection of {SENSITIVITY_LEVELS!r}",
            binding={"input_levels": list(input_levels) if isinstance(input_levels, (list, tuple, set, frozenset)) else input_levels},
        )
    return SensitivityDecision(
        status=STATUS_ALLOW,
        reason_code=CODE_INHERITED,
        message=f"artifact inherits the maximum input sensitivity {inherited!r}; it cannot be auto-labelled below this",
        level=inherited,
        binding={"input_levels": sorted(input_levels), "inherited": inherited},
    )


def evaluate_downgrade(current_level: Any, target_level: Any, *, approval_granted: bool = False) -> SensitivityDecision:
    """Decide whether relabelling ``current_level`` down to ``target_level`` is allowed (T-23-06).

    A move to a *lower* rank is a downgrade and requires ``approval_granted=True``;
    without it the decision is ``needs_approval`` (fail closed — never an automatic
    downgrade).  A move to the same or higher rank is not a downgrade and is
    allowed.  Malformed levels fail closed to ``invalid``.
    """
    if not is_sensitivity(current_level) or not is_sensitivity(target_level):
        return SensitivityDecision(
            status=STATUS_INVALID,
            reason_code=CODE_MALFORMED,
            message=f"current_level and target_level must each be one of {SENSITIVITY_LEVELS!r}",
            binding={"current_level": current_level, "target_level": target_level},
        )
    binding = {"current_level": current_level, "target_level": target_level, "approval_granted": bool(approval_granted)}
    if _RANK[target_level] >= _RANK[current_level]:
        return SensitivityDecision(
            status=STATUS_ALLOW,
            reason_code=CODE_NOT_A_DOWNGRADE,
            message="target is not lower than current sensitivity; not a downgrade",
            level=target_level,
            binding=binding,
        )
    if not approval_granted:
        return SensitivityDecision(
            status=STATUS_NEEDS_APPROVAL,
            reason_code=CODE_DOWNGRADE_NEEDS_APPROVAL,
            message=f"downgrading {current_level!r} to {target_level!r} requires an explicit approval (fail closed)",
            level=current_level,
            binding=binding,
        )
    return SensitivityDecision(
        status=STATUS_ALLOW,
        reason_code=CODE_DOWNGRADE_OK,
        message=f"downgrade {current_level!r} -> {target_level!r} permitted by explicit approval",
        level=target_level,
        binding=binding,
    )


@dataclass(frozen=True)
class DataField:
    """One field a caller wants to send outward: a name, sensitivity, and maskability."""

    name: str
    sensitivity: str = SENSITIVITY_PUBLIC
    maskable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "sensitivity": self.sensitivity, "maskable": self.maskable}


@dataclass(frozen=True)
class ExternalSendDecision:
    """The outcome of evaluating an external send: allow/deny + a masked projection.

    ``blocked_fields`` are field names above the destination ceiling that are not
    maskable; ``masked_fields`` are field names redacted down to a marker;
    ``sent_fields`` are field names permitted verbatim.  ``payload`` is the
    redacted projection a caller *would* send (with over-ceiling non-maskable
    fields removed and maskable ones replaced by :data:`REDACTED`).  ``allowed`` is
    true iff nothing was blocked.
    """

    status: str
    reason_code: str
    message: str
    sent_fields: tuple[str, ...] = ()
    masked_fields: tuple[str, ...] = ()
    blocked_fields: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
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
            "sent_fields": list(self.sent_fields),
            "masked_fields": list(self.masked_fields),
            "blocked_fields": list(self.blocked_fields),
            "payload": dict(self.payload),
            "binding": dict(self.binding),
        }


def evaluate_external_send(fields: Any, *, destination_max_sensitivity: Any) -> ExternalSendDecision:
    """Decide which fields may cross a boundary to an external destination (T-23-07).

    Pure and deterministic.  For each :class:`DataField`:

    - sensitivity at or below ``destination_max_sensitivity`` → sent verbatim;
    - above the ceiling and ``maskable`` → replaced with :data:`REDACTED` (the
      field name is exposed, the value is not);
    - above the ceiling and **not** maskable → *blocked* (restricted data does not
      cross the boundary), and the whole send is refused (``deny``).

    The returned ``payload`` is the masked projection a caller *would* send; the
    decision itself never performs a real send.  Malformed inputs fail closed.
    """
    if not is_sensitivity(destination_max_sensitivity):
        return ExternalSendDecision(
            status=STATUS_INVALID,
            reason_code=CODE_MALFORMED,
            message=f"destination_max_sensitivity must be one of {SENSITIVITY_LEVELS!r}",
            binding={"destination_max_sensitivity": destination_max_sensitivity},
        )
    if not isinstance(fields, (list, tuple)):
        return ExternalSendDecision(
            status=STATUS_INVALID,
            reason_code=CODE_MALFORMED,
            message="fields must be a sequence of DataField",
            binding={"destination_max_sensitivity": destination_max_sensitivity},
        )

    ceiling = _RANK[destination_max_sensitivity]
    sent: list[str] = []
    masked: list[str] = []
    blocked: list[str] = []
    payload: dict[str, Any] = {}
    for item in fields:
        if not isinstance(item, DataField) or not is_sensitivity(item.sensitivity) or not isinstance(item.name, str) or not item.name:
            return ExternalSendDecision(
                status=STATUS_INVALID,
                reason_code=CODE_MALFORMED,
                message="each field must be a DataField with a non-empty name and a valid sensitivity",
                binding={"destination_max_sensitivity": destination_max_sensitivity},
            )
        if _RANK[item.sensitivity] <= ceiling:
            sent.append(item.name)
            payload[item.name] = f"<{item.sensitivity}:sent>"
        elif item.maskable:
            masked.append(item.name)
            payload[item.name] = REDACTED
        else:
            blocked.append(item.name)

    binding = {
        "destination_max_sensitivity": destination_max_sensitivity,
        "field_count": len(fields),
    }
    if blocked:
        return ExternalSendDecision(
            status=STATUS_DENY,
            reason_code=CODE_SEND_BLOCKED,
            message=f"{len(blocked)} field(s) exceed the destination ceiling {destination_max_sensitivity!r} and are not maskable; send refused (fail closed)",
            sent_fields=tuple(sorted(sent)),
            masked_fields=tuple(sorted(masked)),
            blocked_fields=tuple(sorted(blocked)),
            payload={},  # nothing is sent when the send is refused
            binding=binding,
        )
    return ExternalSendDecision(
        status=STATUS_ALLOW,
        reason_code=CODE_SEND_ALLOWED,
        message="all fields are within the destination ceiling (over-ceiling maskable fields redacted); send permitted",
        sent_fields=tuple(sorted(sent)),
        masked_fields=tuple(sorted(masked)),
        blocked_fields=(),
        payload=payload,
        binding=binding,
    )


@dataclass(frozen=True)
class DeletionRequest:
    """A request to delete an object, with the retention facts that gate it.

    ``has_retained_evidence`` / ``has_audit_link`` are caller-asserted facts; when
    either is true the object is legally retained and cannot be deleted without a
    lawful ``tombstone`` carrying the required references.
    """

    object_id: str
    has_retained_evidence: bool = False
    has_audit_link: bool = False
    tombstone: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "has_retained_evidence": self.has_retained_evidence,
            "has_audit_link": self.has_audit_link,
            "tombstone": dict(self.tombstone) if isinstance(self.tombstone, Mapping) else None,
        }


# The reference keys a lawful tombstone must carry to delete a retained object.
_REQUIRED_TOMBSTONE_KEYS = ("reason", "approved_by", "retained_reference")


def evaluate_deletion(request: Any) -> SensitivityDecision:
    """Decide whether an object may be lawfully deleted (T-23-10), fail-closed.

    An object with no retention binding may be deleted.  An object bound to
    retained evidence / an audit link may be deleted **only** with a lawful
    tombstone carrying every key in :data:`_REQUIRED_TOMBSTONE_KEYS`; otherwise the
    deletion is blocked so an evidence- or audit-linked object can never be
    silently removed.
    """
    if not isinstance(request, DeletionRequest) or not isinstance(request.object_id, str) or not request.object_id:
        return SensitivityDecision(
            status=STATUS_INVALID,
            reason_code=CODE_MALFORMED,
            message="request must be a DeletionRequest with a non-empty object_id",
            binding={},
        )
    retained = bool(request.has_retained_evidence) or bool(request.has_audit_link)
    binding = {
        "object_id": request.object_id,
        "has_retained_evidence": bool(request.has_retained_evidence),
        "has_audit_link": bool(request.has_audit_link),
        "tombstone_keys": sorted(request.tombstone) if isinstance(request.tombstone, Mapping) else [],
    }
    if not retained:
        return SensitivityDecision(
            status=STATUS_ALLOW,
            reason_code=CODE_DELETE_ALLOWED,
            message="object has no retained evidence or audit link; deletion permitted",
            binding=binding,
        )
    tombstone = request.tombstone if isinstance(request.tombstone, Mapping) else {}
    missing = [key for key in _REQUIRED_TOMBSTONE_KEYS if not str(tombstone.get(key, "")).strip()]
    if missing:
        return SensitivityDecision(
            status=STATUS_DENY,
            reason_code=CODE_DELETE_BLOCKED_RETAINED,
            message=f"object is legally retained; a lawful tombstone is required (missing: {', '.join(missing)}) — deletion refused (fail closed)",
            binding=binding,
        )
    return SensitivityDecision(
        status=STATUS_ALLOW,
        reason_code=CODE_DELETE_ALLOWED,
        message="object is retained but a lawful tombstone with the required references was supplied; deletion permitted",
        binding=binding,
    )


__all__ = [
    "SENSITIVITY_PUBLIC",
    "SENSITIVITY_INTERNAL",
    "SENSITIVITY_RESTRICTED",
    "SENSITIVITY_SECRET",
    "SENSITIVITY_LEVELS",
    "is_sensitivity",
    "sensitivity_rank",
    "max_sensitivity",
    "STATUS_ALLOW",
    "STATUS_DENY",
    "STATUS_NEEDS_APPROVAL",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_INHERITED",
    "CODE_DOWNGRADE_OK",
    "CODE_DOWNGRADE_NEEDS_APPROVAL",
    "CODE_NOT_A_DOWNGRADE",
    "CODE_SEND_ALLOWED",
    "CODE_SEND_BLOCKED",
    "CODE_DELETE_ALLOWED",
    "CODE_DELETE_BLOCKED_RETAINED",
    "CODE_MALFORMED",
    "REASON_CODES",
    "SensitivityDecision",
    "inherit_artifact_sensitivity",
    "evaluate_downgrade",
    "DataField",
    "ExternalSendDecision",
    "evaluate_external_send",
    "DeletionRequest",
    "evaluate_deletion",
]
