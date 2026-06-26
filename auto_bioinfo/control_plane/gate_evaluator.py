"""A0–A3 admission gate evaluator (WP-04f / T-04-06).

The smallest deterministic, *local* gate evaluator the control plane needs to
answer one question: *may a given subject pass a named A0–A3 admission gate
right now?*  It is the policy/approval counterpart to the WP-04e approval
lifecycle — where that module drives a single request from pending to a terminal
outcome, this module *reads* a project's governance policy and (optionally) an
approval record as **data** and returns a bounded, reason-coded decision.

Design constraints (WP-04f):

- **Pure and deterministic.** :func:`evaluate_gate` is a total function of its
  explicit in-memory :class:`GateEvaluationInput`.  It performs no I/O: it never
  reads files, opens the network, inspects environment variables, reads a real
  clock, or runs a command.  The same input always yields the same decision.
- **Fail closed.** Every uncertainty resolves to a *non-passing* decision.  An
  unknown gate name, a malformed/invalid input, an untrustworthy
  (tamper-evident-mismatched) policy, a policy bound to a different project, a
  subject evaluated against a superseded ``current_version``, or an approval
  record that binds a *different* subject/version never yields ``pass`` — they
  yield ``insufficient`` (or, for an explicit human rejection, ``block``).
- **Bounded vocabulary.** The outcome is one of exactly four values
  (:data:`OUTCOMES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never on
  the human-readable message.
- **Exact binding.** Every decision is bound to the exact
  project/subject/version, the exact policy identity/version/content-hash, and
  (when present) the exact approval request id it considered.  Missing or
  mismatched binding facts fail closed.
- **No mutation.** The evaluator only *reads* the supplied policy and approval
  objects; it copies what it records and never mutates an approval record or a
  policy in place.

The A0–A3 gate names reuse the authoritative
:data:`~auto_bioinfo.core.schemas.AUTOMATION_LEVELS` vocabulary so this module
cannot drift from it.  The *automation level* declared in a project's
:class:`~auto_bioinfo.core.schemas.ProjectPolicy` is the autonomy budget: a gate
whose tier is at or below the policy's automation level auto-clears, while a
higher-risk gate needs an explicit human approval (decision D-04 / ADR-010).  A
present approval record always takes precedence over the auto-clear path: an
explicit grant passes, an explicit rejection blocks, and a pending/expired/
cancelled record is treated conservatively as *not yet approved*.

This module evaluates a gate as a pure decision only; it does not drive an
approval lifecycle, persist anything, or expose any HTTP/CLI surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.schemas import (
    APPROVAL_STATES,
    AUTOMATION_LEVELS,
    ApprovalRequest,
    ProjectPolicy,
)
from ..core.validation import validate_project_policy
from .approval_lifecycle import PENDING_STATE, ApprovalLifecycleRecord

# The bounded A0–A3 gate names, taken verbatim from the authoritative automation
# vocabulary so the gate tiers and the policy automation levels share one scale.
GATE_NAMES = AUTOMATION_LEVELS
# Ordering used by the auto-clear rule: a gate auto-clears iff its tier index is
# at or below the project policy's automation-level index.
_LEVEL_ORDER = {name: index for index, name in enumerate(AUTOMATION_LEVELS)}

# --- Bounded outcome vocabulary --------------------------------------------
OUTCOME_PASS = "pass"
OUTCOME_BLOCK = "block"
OUTCOME_NEEDS_APPROVAL = "needs-approval"
OUTCOME_INSUFFICIENT = "insufficient"

OUTCOMES = (OUTCOME_PASS, OUTCOME_BLOCK, OUTCOME_NEEDS_APPROVAL, OUTCOME_INSUFFICIENT)

# --- Stable reason codes ----------------------------------------------------
# Callers branch on these, so they must stay stable.
# pass:
CODE_AUTO_CLEARED = "GATE_AUTO_CLEARED"
CODE_APPROVAL_GRANTED = "GATE_APPROVAL_GRANTED"
# block:
CODE_APPROVAL_REJECTED = "GATE_APPROVAL_REJECTED"
# needs-approval:
CODE_APPROVAL_REQUIRED = "GATE_APPROVAL_REQUIRED"
CODE_APPROVAL_PENDING = "GATE_APPROVAL_PENDING"
CODE_APPROVAL_EXPIRED = "GATE_APPROVAL_EXPIRED"
CODE_APPROVAL_CANCELLED = "GATE_APPROVAL_CANCELLED"
# insufficient (fail closed):
CODE_UNKNOWN_GATE = "GATE_UNKNOWN_GATE"
CODE_MALFORMED_INPUT = "GATE_MALFORMED_INPUT"
CODE_INVALID_POLICY = "GATE_INVALID_POLICY"
CODE_POLICY_PROJECT_MISMATCH = "GATE_POLICY_PROJECT_MISMATCH"
CODE_SUBJECT_BINDING_MISMATCH = "GATE_SUBJECT_BINDING_MISMATCH"
CODE_STALE_VERSION = "GATE_STALE_VERSION"
CODE_UNKNOWN_APPROVAL_STATE = "GATE_UNKNOWN_APPROVAL_STATE"

REASON_CODES = (
    CODE_AUTO_CLEARED,
    CODE_APPROVAL_GRANTED,
    CODE_APPROVAL_REJECTED,
    CODE_APPROVAL_REQUIRED,
    CODE_APPROVAL_PENDING,
    CODE_APPROVAL_EXPIRED,
    CODE_APPROVAL_CANCELLED,
    CODE_UNKNOWN_GATE,
    CODE_MALFORMED_INPUT,
    CODE_INVALID_POLICY,
    CODE_POLICY_PROJECT_MISMATCH,
    CODE_SUBJECT_BINDING_MISMATCH,
    CODE_STALE_VERSION,
    CODE_UNKNOWN_APPROVAL_STATE,
)

# Lifecycle/approval states that are *not yet a valid grant* map to a stable
# needs-approval reason code; a missing mapping is treated as unknown (fail
# closed) rather than silently passing.
_NON_GRANT_STATE_CODE = {
    PENDING_STATE: CODE_APPROVAL_PENDING,
    "expired": CODE_APPROVAL_EXPIRED,
    "cancelled": CODE_APPROVAL_CANCELLED,
}


@dataclass(frozen=True)
class GateEvaluationInput:
    """The explicit, in-memory facts a gate decision is computed from.

    ``gate`` is one of :data:`GATE_NAMES`.  ``project_id`` plus
    ``subject_type``/``subject_id``/``subject_version`` name the exact object and
    version under evaluation.  ``policy`` is the governing
    :class:`~auto_bioinfo.core.schemas.ProjectPolicy` (dataclass or its dict
    projection); its automation level is the autonomy budget.  ``approval`` is an
    optional already-recorded approval, supplied as an
    :class:`~auto_bioinfo.control_plane.approval_lifecycle.ApprovalLifecycleRecord`,
    an :class:`~auto_bioinfo.core.schemas.ApprovalRequest` (dataclass or dict),
    or a lifecycle-record dict projection — consumed as *data only*.
    ``current_version``, when given, is the subject's authoritative current
    version: evaluating or approving a superseded version fails closed.
    """

    gate: str
    project_id: str
    subject_type: str
    subject_id: str
    subject_version: int
    policy: ProjectPolicy | dict[str, Any]
    approval: ApprovalLifecycleRecord | ApprovalRequest | dict[str, Any] | None = None
    current_version: int | None = None


@dataclass(frozen=True)
class GateDecision:
    """An immutable, reason-coded gate decision.

    ``outcome`` is one of :data:`OUTCOMES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  ``binding`` records the exact identity/version facts
    the decision was bound to so it can be audited later.  ``passed`` is a
    convenience for the single safe-to-proceed outcome.
    """

    gate: str
    outcome: str
    reason_code: str
    message: str
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.outcome == OUTCOME_PASS

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order)."""
        return {
            "gate": self.gate,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "message": self.message,
            "passed": self.passed,
            "binding": dict(self.binding),
        }


@dataclass(frozen=True)
class _ApprovalView:
    """A normalised, read-only projection of whatever approval form was supplied."""

    approval_request_id: str
    project_id: str
    gate: str
    subject_type: str
    subject_id: str
    subject_version: Any
    state: str
    decision_subject_version: Any


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _policy_to_dict(policy: ProjectPolicy | dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(policy, ProjectPolicy):
        return policy.to_dict()
    if isinstance(policy, dict):
        return dict(policy)
    return None


def _project_approval(approval: Any) -> _ApprovalView | None:
    """Project any supported approval form to a read-only :class:`_ApprovalView`.

    Returns ``None`` for an unrecognised/malformed container so the caller can
    fail closed.  Never mutates the supplied object.
    """
    request: dict[str, Any]
    state: Any
    decision: dict[str, Any] | None

    if isinstance(approval, ApprovalLifecycleRecord):
        request = dict(approval.request)
        state = approval.state
        decision = dict(approval.decision) if approval.decision is not None else None
    elif isinstance(approval, ApprovalRequest):
        request = approval.to_dict()
        state = request.get("state")
        decision = None
    elif isinstance(approval, dict):
        inner = approval.get("request")
        if isinstance(inner, dict):
            # A lifecycle-record dict projection (to_dict()): state/decision live
            # at the top level, the bound request one level down.
            request = dict(inner)
            state = approval.get("state")
            raw_decision = approval.get("decision")
            decision = dict(raw_decision) if isinstance(raw_decision, dict) else None
        else:
            # A bare ApprovalRequest dict projection.
            request = dict(approval)
            state = request.get("state")
            decision = None
    else:
        return None

    return _ApprovalView(
        approval_request_id=str(request.get("approval_request_id", "") or ""),
        project_id=request.get("project_id"),
        gate=request.get("gate"),
        subject_type=request.get("subject_type"),
        subject_id=request.get("subject_id"),
        subject_version=request.get("subject_version"),
        state=state if isinstance(state, str) else "",
        decision_subject_version=(decision.get("subject_version") if decision is not None else None),
    )


def _binding(
    *,
    gate: str,
    project_id: str,
    subject_type: str,
    subject_id: str,
    subject_version: Any,
    current_version: int | None,
    policy: dict[str, Any] | None,
    approval_request_id: str,
) -> dict[str, Any]:
    """Assemble the deterministic identity/version binding for a decision."""
    policy = policy or {}
    return {
        "project_id": project_id,
        "gate": gate,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "subject_version": subject_version,
        "current_version": current_version,
        "policy_id": policy.get("project_policy_id", ""),
        "policy_version": policy.get("policy_version"),
        "policy_content_hash": policy.get("content_hash", ""),
        "automation_level": policy.get("automation_level", ""),
        "approval_request_id": approval_request_id,
    }


def evaluate_gate(gate_input: GateEvaluationInput) -> GateDecision:
    """Decide whether ``gate_input``'s subject may pass its A0–A3 gate.

    A pure, deterministic, fail-closed function returning a bounded
    :class:`GateDecision` (never raising for a domain condition).  Precedence:

    1. Validate the gate name, the subject binding facts, and the policy
       (identity/integrity + project binding).  Any failure → ``insufficient``.
    2. If a ``current_version`` is supplied and the subject under evaluation is
       not that version, fail closed (``insufficient`` / stale) — a superseded
       subject can never pass.
    3. If an approval record is supplied, it must bind the *exact* gate and
       subject/version; otherwise fail closed (``insufficient``).  A bound
       record then decides: ``granted`` → ``pass``, ``rejected`` → ``block``,
       and ``requested``/``expired``/``cancelled`` → ``needs-approval``.
    4. With no approval record, auto-clear by automation level: a gate at or
       below the policy's automation level → ``pass``; otherwise
       ``needs-approval``.
    """
    gate = gate_input.gate

    # 1a. Gate name must be one of the bounded A0–A3 names.
    if gate not in GATE_NAMES:
        return GateDecision(
            gate=str(gate),
            outcome=OUTCOME_INSUFFICIENT,
            reason_code=CODE_UNKNOWN_GATE,
            message=f"unknown gate {gate!r}; must be one of {', '.join(GATE_NAMES)}",
            binding=_binding(
                gate=str(gate),
                project_id=str(gate_input.project_id),
                subject_type=str(gate_input.subject_type),
                subject_id=str(gate_input.subject_id),
                subject_version=gate_input.subject_version,
                current_version=gate_input.current_version,
                policy=None,
                approval_request_id="",
            ),
        )

    # 1b. Subject binding facts must be present and well-formed.
    if not (_nonblank(gate_input.project_id) and _nonblank(gate_input.subject_type) and _nonblank(gate_input.subject_id)):
        return _insufficient(gate, gate_input, None, "", CODE_MALFORMED_INPUT, "project_id, subject_type and subject_id must be non-blank")
    if not _is_positive_int(gate_input.subject_version):
        return _insufficient(gate, gate_input, None, "", CODE_MALFORMED_INPUT, "subject_version must be a positive integer (the exact version under review)")
    if gate_input.current_version is not None and not _is_positive_int(gate_input.current_version):
        return _insufficient(gate, gate_input, None, "", CODE_MALFORMED_INPUT, "current_version, when supplied, must be a positive integer")

    # 1c. Policy must be a valid, tamper-evident ProjectPolicy bound to project.
    policy = _policy_to_dict(gate_input.policy)
    if policy is None:
        return _insufficient(gate, gate_input, None, "", CODE_MALFORMED_INPUT, "policy must be a ProjectPolicy or its dict projection")
    policy_errors = validate_project_policy(policy)
    if policy_errors:
        return _insufficient(gate, gate_input, policy, "", CODE_INVALID_POLICY, f"invalid project policy: {'; '.join(policy_errors)}")
    if policy.get("project_id") != gate_input.project_id:
        return _insufficient(
            gate,
            gate_input,
            policy,
            "",
            CODE_POLICY_PROJECT_MISMATCH,
            f"policy binds project {policy.get('project_id')!r}, not the gate's project {gate_input.project_id!r}",
        )

    # 2. A subject evaluated against a newer authoritative version is stale.
    if gate_input.current_version is not None and gate_input.subject_version != gate_input.current_version:
        return _insufficient(
            gate,
            gate_input,
            policy,
            "",
            CODE_STALE_VERSION,
            f"subject_version {gate_input.subject_version} is superseded (current is {gate_input.current_version}); a stale subject cannot pass",
        )

    # 3. A supplied approval record takes precedence over the auto-clear path.
    if gate_input.approval is not None:
        return _evaluate_with_approval(gate, gate_input, policy)

    # 4. No approval record: auto-clear by automation level.
    automation_level = policy.get("automation_level", "")
    if _LEVEL_ORDER.get(gate, len(AUTOMATION_LEVELS)) <= _LEVEL_ORDER.get(automation_level, -1):
        return _decision(gate, gate_input, policy, "", OUTCOME_PASS, CODE_AUTO_CLEARED, f"gate {gate} auto-clears at automation level {automation_level}")
    return _decision(
        gate,
        gate_input,
        policy,
        "",
        OUTCOME_NEEDS_APPROVAL,
        CODE_APPROVAL_REQUIRED,
        f"gate {gate} exceeds automation level {automation_level}; explicit human approval is required",
    )


def _evaluate_with_approval(gate: str, gate_input: GateEvaluationInput, policy: dict[str, Any]) -> GateDecision:
    view = _project_approval(gate_input.approval)
    if view is None:
        return _insufficient(
            gate, gate_input, policy, "", CODE_MALFORMED_INPUT, "approval must be an ApprovalLifecycleRecord, ApprovalRequest, or its dict projection"
        )

    # The approval must bind the *exact* gate and subject/version under review.
    # A mismatch (a stale or different-subject approval) fails closed and can
    # never pass a gate (WP-04f requirement: no cross-binding leakage).
    if (
        view.project_id != gate_input.project_id
        or view.gate != gate
        or view.subject_type != gate_input.subject_type
        or view.subject_id != gate_input.subject_id
        or view.subject_version != gate_input.subject_version
    ):
        return _insufficient(
            gate,
            gate_input,
            policy,
            view.approval_request_id,
            CODE_SUBJECT_BINDING_MISMATCH,
            "approval record binds a different project/gate/subject/version than the gate under evaluation",
        )

    state = view.state
    if state == "granted":
        # A grant must itself bind the exact version it ruled on; a grant whose
        # recorded decision targets a different (stale) version cannot pass.
        if view.decision_subject_version is not None and view.decision_subject_version != gate_input.subject_version:
            return _insufficient(
                gate,
                gate_input,
                policy,
                view.approval_request_id,
                CODE_STALE_VERSION,
                f"granted decision targets version {view.decision_subject_version}, not the subject version {gate_input.subject_version} under review",
            )
        return _decision(
            gate, gate_input, policy, view.approval_request_id, OUTCOME_PASS, CODE_APPROVAL_GRANTED, "an explicit, exactly-bound approval grants this gate"
        )
    if state == "rejected":
        return _decision(
            gate, gate_input, policy, view.approval_request_id, OUTCOME_BLOCK, CODE_APPROVAL_REJECTED, "an explicit human rejection blocks this gate"
        )
    if state in _NON_GRANT_STATE_CODE:
        return _decision(
            gate,
            gate_input,
            policy,
            view.approval_request_id,
            OUTCOME_NEEDS_APPROVAL,
            _NON_GRANT_STATE_CODE[state],
            f"approval is {state!r}; a valid grant is still required",
        )
    # Any state outside the authoritative vocabulary is untrusted: fail closed.
    return _insufficient(
        gate,
        gate_input,
        policy,
        view.approval_request_id,
        CODE_UNKNOWN_APPROVAL_STATE,
        f"approval state {state!r} is not one of {', '.join(APPROVAL_STATES)}",
    )


def _decision(
    gate: str,
    gate_input: GateEvaluationInput,
    policy: dict[str, Any] | None,
    approval_request_id: str,
    outcome: str,
    reason_code: str,
    message: str,
) -> GateDecision:
    return GateDecision(
        gate=gate,
        outcome=outcome,
        reason_code=reason_code,
        message=message,
        binding=_binding(
            gate=gate,
            project_id=str(gate_input.project_id),
            subject_type=str(gate_input.subject_type),
            subject_id=str(gate_input.subject_id),
            subject_version=gate_input.subject_version,
            current_version=gate_input.current_version,
            policy=policy,
            approval_request_id=approval_request_id,
        ),
    )


def _insufficient(
    gate: str,
    gate_input: GateEvaluationInput,
    policy: dict[str, Any] | None,
    approval_request_id: str,
    reason_code: str,
    message: str,
) -> GateDecision:
    return _decision(gate, gate_input, policy, approval_request_id, OUTCOME_INSUFFICIENT, reason_code, message)


__all__ = [
    "GATE_NAMES",
    "OUTCOMES",
    "OUTCOME_PASS",
    "OUTCOME_BLOCK",
    "OUTCOME_NEEDS_APPROVAL",
    "OUTCOME_INSUFFICIENT",
    "REASON_CODES",
    "CODE_AUTO_CLEARED",
    "CODE_APPROVAL_GRANTED",
    "CODE_APPROVAL_REJECTED",
    "CODE_APPROVAL_REQUIRED",
    "CODE_APPROVAL_PENDING",
    "CODE_APPROVAL_EXPIRED",
    "CODE_APPROVAL_CANCELLED",
    "CODE_UNKNOWN_GATE",
    "CODE_MALFORMED_INPUT",
    "CODE_INVALID_POLICY",
    "CODE_POLICY_PROJECT_MISMATCH",
    "CODE_SUBJECT_BINDING_MISMATCH",
    "CODE_STALE_VERSION",
    "CODE_UNKNOWN_APPROVAL_STATE",
    "GateDecision",
    "GateEvaluationInput",
    "evaluate_gate",
]
