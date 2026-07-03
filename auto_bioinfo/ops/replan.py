"""Replan / reconfirm / override / terminal decision engine (WP-25 / T-25-07..T-25-10).

When a failure is *not* fixable by a bounded retry (see
:mod:`auto_bioinfo.ops.retry_policy` / :mod:`auto_bioinfo.ops.failure_taxonomy`),
the requirement spec routes it to one of four *domain* actions, each with a hard
rule this module enforces purely and deterministically:

- **REPLAN (T-25-07).** Produce an inert replan record naming the triggering
  problem, the rollback stage, and the new object versions — while the *old* plan
  is preserved (never overwritten), so the change stays auditable.
- **RECONFIRM_REQUIRED (T-25-08).** If a scope / architecture / data / method /
  risk / acceptance assumption changed, a human must re-confirm **before** the new
  path may execute; an unconfirmed change fails closed.
- **Human override (T-25-09).** A human may only adjust items the policy explicitly
  permits; an override may **never** fabricate a ``PASS`` or delete the original
  finding — the finding is always preserved.
- **Terminal decision (T-25-10).** A legitimate non-success terminal
  (insufficient data / method not applicable / conflicting evidence / failed)
  requires a mandatory reason **and** supporting evidence; a bare terminal without
  them fails closed.

Everything is a bounded, reason-coded *value* over explicit in-memory facts — no
persistence, no event emission, no clock, no approval is actually granted here.

Reuses the canonical terminal-stage vocabulary from
:mod:`auto_bioinfo.core.state` so this engine cannot invent a terminal the state
machine does not recognise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..core.state import MAIN_SEQUENCE
from ..core.state import TERMINAL_STAGES as _CORE_TERMINALS

# The real *working* stages a replan may roll back to: the main sequence minus any
# terminal stage (a replan can never "roll back" to a terminal like COMPLETED).
WORKING_STAGES = tuple(s for s in MAIN_SEQUENCE if s not in _CORE_TERMINALS)

# --- Bounded status vocabulary -----------------------------------------------
STATUS_OK = "ok"  # a valid decision/record was produced
STATUS_RECONFIRM_REQUIRED = "reconfirm_required"  # a human must re-confirm first
STATUS_REJECTED = "rejected"  # a forbidden action (fabricated PASS, missing evidence)
STATUS_INVALID = "invalid"  # malformed input (fail closed)

STATUSES = (STATUS_OK, STATUS_RECONFIRM_REQUIRED, STATUS_REJECTED, STATUS_INVALID)

# --- Stable reason codes -----------------------------------------------------
CODE_REPLAN_RECORDED = "REPLAN_RECORDED"
CODE_RECONFIRM_REQUIRED = "RECONFIRM_REQUIRED"
CODE_NO_RECONFIRM_NEEDED = "RECONFIRM_NOT_NEEDED"
CODE_OVERRIDE_ALLOWED = "OVERRIDE_ALLOWED"
CODE_OVERRIDE_FORBIDDEN_PASS = "OVERRIDE_FORBIDDEN_PASS"
CODE_OVERRIDE_OUT_OF_POLICY = "OVERRIDE_OUT_OF_POLICY"
CODE_OVERRIDE_DROPS_FINDING = "OVERRIDE_DROPS_FINDING"
CODE_TERMINAL_RECORDED = "TERMINAL_RECORDED"
CODE_TERMINAL_MISSING_REASON = "TERMINAL_MISSING_REASON"
CODE_TERMINAL_MISSING_EVIDENCE = "TERMINAL_MISSING_EVIDENCE"
CODE_UNKNOWN_TERMINAL = "TERMINAL_UNKNOWN_KIND"
CODE_MALFORMED = "REPLAN_MALFORMED_REQUEST"

REASON_CODES = (
    CODE_REPLAN_RECORDED,
    CODE_RECONFIRM_REQUIRED,
    CODE_NO_RECONFIRM_NEEDED,
    CODE_OVERRIDE_ALLOWED,
    CODE_OVERRIDE_FORBIDDEN_PASS,
    CODE_OVERRIDE_OUT_OF_POLICY,
    CODE_OVERRIDE_DROPS_FINDING,
    CODE_TERMINAL_RECORDED,
    CODE_TERMINAL_MISSING_REASON,
    CODE_TERMINAL_MISSING_EVIDENCE,
    CODE_UNKNOWN_TERMINAL,
    CODE_MALFORMED,
)

# --- Change categories that require human re-confirmation (T-25-08) ----------
CHANGE_SCOPE = "scope"
CHANGE_ARCHITECTURE = "architecture"
CHANGE_DATA = "data"
CHANGE_METHOD = "method"
CHANGE_RISK = "risk"
CHANGE_ACCEPTANCE = "acceptance"

RECONFIRM_CHANGE_CATEGORIES = frozenset({CHANGE_SCOPE, CHANGE_ARCHITECTURE, CHANGE_DATA, CHANGE_METHOD, CHANGE_RISK, CHANGE_ACCEPTANCE})

# --- The legitimate non-success terminals this engine may record (T-25-10) ---
# Derived from the core terminal stages, excluding the clean success (COMPLETED is
# not a *failure* terminal) and CANCELLED (an explicit human cancel, not a decision
# this engine makes from project evidence).
TERMINAL_KINDS = tuple(sorted(_CORE_TERMINALS - {"COMPLETED", "CANCELLED"}))


@dataclass(frozen=True)
class Decision:
    """A generic bounded, reason-coded engine decision with an inert record payload."""

    status: str
    reason_code: str
    message: str
    record: dict[str, Any] = field(default_factory=dict)
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "record": dict(self.record),
            "binding": dict(self.binding),
        }


# --- REPLAN (T-25-07) --------------------------------------------------------


@dataclass(frozen=True)
class ReplanRequest:
    """The facts a replan needs: the trigger, the rollback stage, and new versions.

    ``triggering_problem`` is the failure/QC finding that forced the replan;
    ``rollback_stage`` is the working stage to roll back to (must be a real
    non-terminal stage); ``new_object_versions`` maps object ids to their new
    version; ``prior_plan_ref`` points at the old plan, which is preserved.
    """

    triggering_problem: str
    rollback_stage: str
    new_object_versions: Mapping[str, Any] = field(default_factory=dict)
    prior_plan_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggering_problem": self.triggering_problem,
            "rollback_stage": self.rollback_stage,
            "new_object_versions": dict(self.new_object_versions),
            "prior_plan_ref": self.prior_plan_ref,
        }


def plan_replan(request: Any) -> Decision:
    """Produce an inert REPLAN record, preserving the prior plan (T-25-07), fail-closed.

    Validates that the trigger is stated and the rollback stage is a real working
    (non-terminal) stage.  The record carries ``prior_plan_ref`` verbatim and never
    mutates it — the old plan stays auditable.  The record is inert data; nothing
    is executed, and ``created_at`` is empty for determinism.
    """
    if not isinstance(request, ReplanRequest):
        return Decision(STATUS_INVALID, CODE_MALFORMED, "request must be a ReplanRequest")
    if not isinstance(request.triggering_problem, str) or not request.triggering_problem.strip():
        return Decision(STATUS_INVALID, CODE_MALFORMED, "triggering_problem must be a non-empty string")
    if request.rollback_stage not in WORKING_STAGES:
        return Decision(
            STATUS_INVALID,
            CODE_MALFORMED,
            f"rollback_stage {request.rollback_stage!r} must be a real working (non-terminal) stage",
        )
    if not isinstance(request.new_object_versions, Mapping):
        return Decision(STATUS_INVALID, CODE_MALFORMED, "new_object_versions must be a mapping of object id -> new version")

    record = {
        "kind": "REPLAN",
        "triggering_problem": request.triggering_problem,
        "rollback_stage": request.rollback_stage,
        "new_object_versions": dict(sorted(request.new_object_versions.items())),
        "prior_plan_ref": request.prior_plan_ref,
        "prior_plan_preserved": True,
        "created_at": "",  # inert / deterministic
    }
    return Decision(
        status=STATUS_OK,
        reason_code=CODE_REPLAN_RECORDED,
        message=f"replan recorded rolling back to {request.rollback_stage!r}; the prior plan is preserved for audit",
        record=record,
        binding={"rollback_stage": request.rollback_stage, "changed_object_count": len(request.new_object_versions)},
    )


# --- RECONFIRM_REQUIRED (T-25-08) --------------------------------------------


def evaluate_reconfirm(changes: Any, *, confirmed: bool = False) -> Decision:
    """Decide whether a set of changes requires human re-confirmation (T-25-08).

    ``changes`` is a collection of change-category strings.  If any is in
    :data:`RECONFIRM_CHANGE_CATEGORIES` and ``confirmed`` is not ``True``, the
    decision is ``reconfirm_required`` (the new path may not execute yet).  When
    every triggering change has been confirmed, or no triggering change is present,
    the decision is ``ok``.  An unknown change category fails closed to ``invalid``.
    """
    if not isinstance(changes, (list, tuple, set, frozenset)):
        return Decision(STATUS_INVALID, CODE_MALFORMED, "changes must be a collection of change-category strings")
    normalized = [str(c).strip().lower() for c in changes]
    unknown = [c for c in normalized if c and c not in RECONFIRM_CHANGE_CATEGORIES]
    if unknown:
        return Decision(STATUS_INVALID, CODE_MALFORMED, f"unknown change categor(y/ies): {', '.join(sorted(set(unknown)))}")
    triggering = sorted({c for c in normalized if c in RECONFIRM_CHANGE_CATEGORIES})
    binding = {"triggering_changes": triggering, "confirmed": bool(confirmed)}
    if triggering and not confirmed:
        return Decision(
            STATUS_RECONFIRM_REQUIRED,
            CODE_RECONFIRM_REQUIRED,
            f"changes to {', '.join(triggering)} require human re-confirmation before the new path may execute (fail closed)",
            record={"kind": "RECONFIRM_REQUIRED", "triggering_changes": triggering, "created_at": ""},
            binding=binding,
        )
    return Decision(
        STATUS_OK,
        CODE_NO_RECONFIRM_NEEDED,
        "no unconfirmed reconfirm-triggering change; the path may proceed" if not triggering else "all reconfirm-triggering changes are confirmed",
        record={"kind": "RECONFIRM_CLEARED", "triggering_changes": triggering, "created_at": ""},
        binding=binding,
    )


# --- Human override boundary (T-25-09) ---------------------------------------


@dataclass(frozen=True)
class OverrideRequest:
    """A human override attempt over a prior finding.

    ``target_item`` is the item to adjust; ``policy_allows`` is the set of items the
    policy explicitly permits a human to adjust; ``sets_pass`` asserts the override
    would flip a finding to a ``PASS``; ``drops_finding`` asserts it would delete the
    original finding.  The last two are always forbidden.
    """

    target_item: str
    policy_allows: frozenset[str] = field(default_factory=frozenset)
    sets_pass: bool = False
    drops_finding: bool = False
    justification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_item": self.target_item,
            "policy_allows": sorted(self.policy_allows),
            "sets_pass": self.sets_pass,
            "drops_finding": self.drops_finding,
            "justification": self.justification,
        }


def evaluate_override(request: Any) -> Decision:
    """Enforce the human-override boundary (T-25-09), fail-closed.

    An override is ``rejected`` if it would fabricate a ``PASS`` or drop the
    original finding — those are never permitted, regardless of policy.  Otherwise
    it is allowed **only** when the target item is in the policy's explicitly
    permitted set; an out-of-policy target is rejected.  The original finding is
    always recorded as preserved.
    """
    if not isinstance(request, OverrideRequest) or not isinstance(request.target_item, str) or not request.target_item.strip():
        return Decision(STATUS_INVALID, CODE_MALFORMED, "request must be an OverrideRequest with a non-empty target_item")
    binding = {
        "target_item": request.target_item,
        "policy_allows": sorted(request.policy_allows),
        "sets_pass": request.sets_pass,
        "drops_finding": request.drops_finding,
    }
    if request.sets_pass:
        return Decision(
            STATUS_REJECTED, CODE_OVERRIDE_FORBIDDEN_PASS, "an override may never fabricate a PASS on a failed finding (fail closed)", binding=binding
        )
    if request.drops_finding:
        return Decision(
            STATUS_REJECTED,
            CODE_OVERRIDE_DROPS_FINDING,
            "an override may never delete the original finding; it must be preserved (fail closed)",
            binding=binding,
        )
    if request.target_item not in request.policy_allows:
        return Decision(
            STATUS_REJECTED,
            CODE_OVERRIDE_OUT_OF_POLICY,
            f"target item {request.target_item!r} is not in the policy-permitted override set; refused (fail closed)",
            binding=binding,
        )
    record = {
        "kind": "OVERRIDE",
        "target_item": request.target_item,
        "justification": request.justification,
        "original_finding_preserved": True,
        "created_at": "",
    }
    return Decision(
        STATUS_OK,
        CODE_OVERRIDE_ALLOWED,
        f"override of policy-permitted item {request.target_item!r} allowed; the original finding is preserved",
        record=record,
        binding=binding,
    )


# --- Terminal decision engine (T-25-10) --------------------------------------


@dataclass(frozen=True)
class TerminalRequest:
    """A request to record a legitimate non-success terminal.

    ``kind`` must be one of :data:`TERMINAL_KINDS`; ``reason`` is a mandatory
    human-readable rationale; ``evidence_refs`` is a non-empty list of references
    grounding the terminal.  A terminal without reason and evidence is refused.
    """

    kind: str
    reason: str
    evidence_refs: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "reason": self.reason, "evidence_refs": list(self.evidence_refs)}


def decide_terminal(request: Any) -> Decision:
    """Record a legitimate non-success terminal with mandatory reason + evidence (T-25-10).

    Fail-closed: an unknown terminal kind, a missing/blank reason, or an empty
    evidence list each refuses the terminal so the system can never "stop" without
    stating why and showing the evidence.
    """
    if not isinstance(request, TerminalRequest):
        return Decision(STATUS_INVALID, CODE_MALFORMED, "request must be a TerminalRequest")
    if request.kind not in TERMINAL_KINDS:
        return Decision(STATUS_INVALID, CODE_UNKNOWN_TERMINAL, f"terminal kind {request.kind!r} must be one of {TERMINAL_KINDS!r}")
    if not isinstance(request.reason, str) or not request.reason.strip():
        return Decision(STATUS_REJECTED, CODE_TERMINAL_MISSING_REASON, f"a {request.kind!r} terminal requires a non-empty reason (fail closed)")
    refs = [str(r) for r in request.evidence_refs if isinstance(r, str) and r.strip()] if isinstance(request.evidence_refs, (list, tuple)) else []
    if not refs:
        return Decision(STATUS_REJECTED, CODE_TERMINAL_MISSING_EVIDENCE, f"a {request.kind!r} terminal requires at least one evidence reference (fail closed)")
    record = {
        "kind": "TERMINAL",
        "terminal_kind": request.kind,
        "reason": request.reason.strip(),
        "evidence_refs": sorted(refs),
        "created_at": "",
    }
    return Decision(
        STATUS_OK,
        CODE_TERMINAL_RECORDED,
        f"recorded legitimate terminal {request.kind!r} with reason and {len(refs)} evidence reference(s)",
        record=record,
        binding={"terminal_kind": request.kind, "evidence_count": len(refs)},
    )


__all__ = [
    "STATUS_OK",
    "STATUS_RECONFIRM_REQUIRED",
    "STATUS_REJECTED",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_REPLAN_RECORDED",
    "CODE_RECONFIRM_REQUIRED",
    "CODE_NO_RECONFIRM_NEEDED",
    "CODE_OVERRIDE_ALLOWED",
    "CODE_OVERRIDE_FORBIDDEN_PASS",
    "CODE_OVERRIDE_OUT_OF_POLICY",
    "CODE_OVERRIDE_DROPS_FINDING",
    "CODE_TERMINAL_RECORDED",
    "CODE_TERMINAL_MISSING_REASON",
    "CODE_TERMINAL_MISSING_EVIDENCE",
    "CODE_UNKNOWN_TERMINAL",
    "CODE_MALFORMED",
    "REASON_CODES",
    "CHANGE_SCOPE",
    "CHANGE_ARCHITECTURE",
    "CHANGE_DATA",
    "CHANGE_METHOD",
    "CHANGE_RISK",
    "CHANGE_ACCEPTANCE",
    "RECONFIRM_CHANGE_CATEGORIES",
    "WORKING_STAGES",
    "TERMINAL_KINDS",
    "Decision",
    "ReplanRequest",
    "plan_replan",
    "evaluate_reconfirm",
    "OverrideRequest",
    "evaluate_override",
    "TerminalRequest",
    "decide_terminal",
]
