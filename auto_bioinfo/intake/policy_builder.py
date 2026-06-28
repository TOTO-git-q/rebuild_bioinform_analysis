"""Local deterministic initial ``ProjectPolicy`` builder (WP-06c / T-06-03).

The third *local* intake slice.  Where :mod:`auto_bioinfo.intake.support_scope`
(WP-06a) answers *"is this request something this system may even attempt to
plan?"* and :mod:`auto_bioinfo.intake.multi_question` (WP-06b) answers *"does this
single request bundle more than one research question?"*, this module answers the
next bounded question — *"given explicit synthetic user-constraint facts, what is
the initial governance policy for this project, and when must a human decide
first?"* — **before any question normalisation, ontology scope resolution,
dataset/literature search, ``ResearchSpec`` creation, or execution path can
start**.

It is deliberately tiny and "deterministic rules first": an LLM, if ever used
later, would only *suggest* at most, and is **not** used or authorised here.

Design constraints (WP-06c), mirroring the WP-06a/WP-06b/WP-04 contract style:

- **Pure and deterministic.** :func:`build_initial_policy` and every helper is a
  total function of its explicit in-memory inputs.  There is no I/O whatsoever: no
  file access, no network, no environment inspection, **no real clock**, no LLM /
  provider / model call, no content egress, no threads, scheduler, queue, DB,
  outbox, audit log, or process side effect.  Inputs are never mutated in place.
  Because the built policy carries no timestamp, two byte-identical constraint sets
  always yield a byte-identical policy with a stable ``project_policy_id`` and
  ``content_hash`` (verified by :func:`validate_project_policy`).
- **Fail closed on the key sensitivity policy.** The data-sensitivity policy is the
  one *required* governance fact.  When it is missing, of the wrong type, or not a
  recognised level, the builder returns an inert *approval-needed* outcome with a
  stable reason code — it **never** silently falls back to a permissive policy and
  **never** creates a granted approval.  Every other malformed constraint (network,
  resources, automation level, execution mode, the constraints shape itself, the
  project id, the policy version) likewise fails closed into a bounded
  *rejected/malformed* outcome rather than a guessed permissive default.
- **Conservative defaults only.** An *absent* (not malformed) optional fact resolves
  to its most conservative value: network ``isolated`` (no egress), resources
  ``unspecified``, automation ``A0`` (least automation), execution mode ``DEMO``
  (never ``REAL`` — real execution is a hard stop this builder cannot reach).  A
  *malformed* fact never gets a default; it fails closed.
- **Inert result only.** The outcome is reviewable data: a :class:`ProjectPolicy`
  projection (``to_dict``) or a narrow inert :class:`ApprovalNeeded` object.  It is
  **never** persisted, versioned beyond the returned object, emitted as an event,
  sent to a human, sent to an external service, treated as authorization, or used
  to unblock any downstream research workflow.  An :class:`ApprovalNeeded` always
  stays ``state == "requested"``; the builder cannot and does not grant it.
- **Preserve original facts.** The user constraints and any request text passed in
  are recorded *verbatim* in the outcome binding (a deep copy snapshot) and never
  rewritten, normalised, redacted, or dropped; the inputs themselves are only read.
- **Bounded vocabulary.** The outcome status is one of exactly three values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code, never the
  human message.

This module builds an *initial* policy only.  It does not normalise the question,
resolve scope/ontology, search any dataset/literature/API, run an Agent /
PromptRegistry prompt, create a ``ResearchSpec`` / ``AmbiguityReport`` /
``ScopeBundle``, run the Approval lifecycle, persist a policy version, or call
``create_project`` — those are out of scope for T-06-03.  It reuses the existing
:class:`ProjectPolicy` schema, :func:`validate_project_policy`, and the same
``execution_mode`` / ``automation_level`` / ``network_policy`` / ``data_sensitivity``
/ ``export_policy`` policy fields as :class:`CreateProjectCommand`, so a built
policy is interoperable with the control plane without changing its semantics.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core import common
from ..core.schemas import AUTOMATION_LEVELS, ProjectPolicy
from ..core.validation import validate_project_policy

# --- Bounded outcome statuses ------------------------------------------------
# Exactly three.  ``built`` is the single proceed-with-data outcome (an inert
# policy projection).  ``approval_needed`` is the fail-closed outcome for the key
# sensitivity policy (a human must decide first).  ``rejected_malformed`` is the
# fail-closed outcome for any other malformed input.
STATUS_BUILT = "built"
STATUS_APPROVAL_NEEDED = "approval_needed"
STATUS_REJECTED_MALFORMED = "rejected_malformed"

STATUSES = (
    STATUS_BUILT,
    STATUS_APPROVAL_NEEDED,
    STATUS_REJECTED_MALFORMED,
)

# --- Stable reason codes -----------------------------------------------------
# Callers branch on these, so they must stay stable.
# built:
CODE_BUILT = "POLICY_BUILT"
# approval_needed (the key data-sensitivity policy is missing/malformed):
CODE_SENSITIVITY_MISSING = "POLICY_SENSITIVITY_MISSING"
CODE_SENSITIVITY_MALFORMED = "POLICY_SENSITIVITY_MALFORMED"
CODE_SENSITIVITY_UNRECOGNIZED = "POLICY_SENSITIVITY_UNRECOGNIZED"
# rejected_malformed (other fail-closed inputs):
CODE_PROJECT_ID_MALFORMED = "POLICY_PROJECT_ID_MALFORMED"
CODE_POLICY_VERSION_MALFORMED = "POLICY_POLICY_VERSION_MALFORMED"
CODE_CONSTRAINTS_MALFORMED = "POLICY_CONSTRAINTS_MALFORMED"
CODE_NETWORK_MALFORMED = "POLICY_NETWORK_MALFORMED"
CODE_RESOURCES_MALFORMED = "POLICY_RESOURCES_MALFORMED"
CODE_AUTOMATION_MALFORMED = "POLICY_AUTOMATION_MALFORMED"
CODE_EXECUTION_MODE_NOT_PERMITTED = "POLICY_EXECUTION_MODE_NOT_PERMITTED"
CODE_POLICY_INVALID = "POLICY_INVALID"

REASON_CODES = (
    CODE_BUILT,
    CODE_SENSITIVITY_MISSING,
    CODE_SENSITIVITY_MALFORMED,
    CODE_SENSITIVITY_UNRECOGNIZED,
    CODE_PROJECT_ID_MALFORMED,
    CODE_POLICY_VERSION_MALFORMED,
    CODE_CONSTRAINTS_MALFORMED,
    CODE_NETWORK_MALFORMED,
    CODE_RESOURCES_MALFORMED,
    CODE_AUTOMATION_MALFORMED,
    CODE_EXECUTION_MODE_NOT_PERMITTED,
    CODE_POLICY_INVALID,
)

# The status each reason code resolves to, so a future adapter can map a code to a
# status without re-deriving it.
_CODE_STATUS = {
    CODE_BUILT: STATUS_BUILT,
    CODE_SENSITIVITY_MISSING: STATUS_APPROVAL_NEEDED,
    CODE_SENSITIVITY_MALFORMED: STATUS_APPROVAL_NEEDED,
    CODE_SENSITIVITY_UNRECOGNIZED: STATUS_APPROVAL_NEEDED,
    CODE_PROJECT_ID_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_POLICY_VERSION_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_CONSTRAINTS_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_NETWORK_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_RESOURCES_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_AUTOMATION_MALFORMED: STATUS_REJECTED_MALFORMED,
    CODE_EXECUTION_MODE_NOT_PERMITTED: STATUS_REJECTED_MALFORMED,
    CODE_POLICY_INVALID: STATUS_REJECTED_MALFORMED,
}

# --- Recognised constraint keys ----------------------------------------------
KEY_SENSITIVITY = "data_sensitivity"
KEY_NETWORK = "network"
KEY_RESOURCES = "resources"
KEY_AUTOMATION = "automation_level"
KEY_EXECUTION_MODE = "execution_mode"

# --- Bounded fact vocabularies -----------------------------------------------
# Data sensitivity is the *required* key policy; there is no default.  The set is
# ordered from least to most sensitive for readability only.
SENSITIVITY_LEVELS = ("public", "internal", "restricted", "confidential")

# Whether export of a result at a given sensitivity requires a (later, separate)
# human approval.  External egress is *always* disallowed in this slice regardless
# of sensitivity — egress is a hard stop the builder cannot lift — so this only
# governs the inert ``requires_approval`` flag on the export policy.
_SENSITIVITY_EXPORT_REQUIRES_APPROVAL = {
    "public": False,
    "internal": True,
    "restricted": True,
    "confidential": True,
}

# Network policy facts.  Every recognised level keeps egress disabled (no real
# network call is reachable from this slice); the levels differ only in the inert
# ``access`` descriptor.  Absent → the most conservative ``isolated``.
DEFAULT_NETWORK = "isolated"
_NETWORK_PROFILES = {
    "isolated": {"access": "isolated", "egress_allowed": False},
    "local_only": {"access": "local_only", "egress_allowed": False},
    "allowlist": {"access": "allowlist", "egress_allowed": False},
}
NETWORK_LEVELS = tuple(_NETWORK_PROFILES)

# Inert resource-policy facts.  These are recorded in the outcome binding only;
# they are *not* folded into the authoritative :class:`ProjectPolicy` (which has no
# resource field), so they cannot change a policy's identity or content hash.
# Absent → the inert ``unspecified``.
DEFAULT_RESOURCES = "unspecified"
RESOURCE_LEVELS = ("minimal", "standard", "high")

# Execution mode.  The initial builder only ever produces a non-real policy:
# ``DEMO`` (default) or ``TEST``.  ``REAL`` is a hard stop that requires explicit
# CEO authorization elsewhere and is never reachable here, so a ``REAL`` (or
# unknown / non-string) request fails closed.
DEFAULT_EXECUTION_MODE = "DEMO"
PERMITTED_EXECUTION_MODES = ("DEMO", "TEST")

# Automation level.  Absent → the most conservative ``A0``.
DEFAULT_AUTOMATION_LEVEL = "A0"

# The gate an approval-needed sensitivity decision is bound to.
GATE_DATA_SENSITIVITY = "POLICY_DATA_SENSITIVITY"

# The only state an :class:`ApprovalNeeded` can ever carry.  The builder is
# incapable of granting an approval, so this is fixed and unrepresentable as
# anything else — see :class:`ApprovalNeeded`.
APPROVAL_NEEDED_STATE = "requested"


@dataclass(frozen=True)
class ApprovalNeeded:
    """A narrow, inert "a human must decide the data-sensitivity policy first"
    result.

    It is deliberately *not* a persisted :class:`ApprovalRequest`: it carries no
    real clock timestamp and no provenance, is never written to a store, never
    emitted as an event, never sent to a human or an external service, and never
    treated as authorization.  ``state`` is fixed at ``"requested"``: it is *not*
    a constructor field, so a caller cannot build a granted-looking instance, and
    the frozen dataclass forbids mutating it afterwards — the builder cannot and
    does not grant it.  It is ``ApprovalRequest``-shaped (same
    subject/gate/state vocabulary) so a later, separately authorised approval
    workflow could adopt it, but on its own it is inert reviewable data.
    """

    project_id: str
    subject_type: str
    subject_id: str
    subject_version: int
    gate: str
    reason_code: str
    message: str
    state: str = field(init=False, default=APPROVAL_NEEDED_STATE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "subject_version": self.subject_version,
            "gate": self.gate,
            "reason_code": self.reason_code,
            "message": self.message,
            "state": self.state,
        }


@dataclass(frozen=True)
class PolicyBuildOutcome:
    """The deterministic, reason-coded outcome of an initial-policy build.

    Exactly one of ``policy`` / ``approval_request`` is set:

    - ``built`` → ``policy`` is a :meth:`ProjectPolicy.to_dict` projection and
      ``approval_request`` is ``None``.
    - ``approval_needed`` → ``approval_request`` is an inert
      :class:`ApprovalNeeded` projection and ``policy`` is ``None``.
    - ``rejected_malformed`` → both are ``None``.

    ``binding`` records the exact facts considered (the project/request
    identifiers, the resolved sensitivity/network/resources/automation/execution
    values, the inert resolved ``resource_policy``, and a verbatim deep-copy
    snapshot of the original constraints and request text) so the decision can be
    audited later without re-reading the inputs.  The outcome is inert data: it is
    never persisted, emitted, sent out, or treated as authorization.
    """

    status: str
    reason_code: str
    message: str
    policy: dict[str, Any] | None = None
    approval_request: dict[str, Any] | None = None
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def built(self) -> bool:
        """The single proceed-with-data outcome (an inert policy projection)."""
        return self.status == STATUS_BUILT

    @property
    def approval_needed(self) -> bool:
        """The fail-closed outcome for the key data-sensitivity policy."""
        return self.status == STATUS_APPROVAL_NEEDED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the outcome (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "built": self.built,
            "approval_needed": self.approval_needed,
            "policy": copy.deepcopy(self.policy) if self.policy is not None else None,
            "approval_request": copy.deepcopy(self.approval_request) if self.approval_request is not None else None,
            "binding": copy.deepcopy(self.binding),
        }


def _resolve_sensitivity(constraints: Mapping[str, Any]) -> tuple[str | None, tuple[str, str] | None]:
    """Resolve the *required* data-sensitivity policy.

    Returns ``(level, None)`` on success or ``(None, (code, message))`` on a
    fail-closed condition.  Missing, non-string, or unrecognised values each get a
    distinct approval-needed reason code; there is never a permissive default.
    """
    if KEY_SENSITIVITY not in constraints:
        return (
            None,
            (CODE_SENSITIVITY_MISSING, "data-sensitivity policy is required but was not supplied; a human must decide it before a policy can be built"),
        )
    value = constraints[KEY_SENSITIVITY]
    # ``bool`` is a subclass of ``int`` but is not a string, so ``True`` / ``1``
    # are malformed (wrong type), while a string such as ``"true"`` is a
    # well-typed but unrecognised level.  Neither may default to permissive.
    if not isinstance(value, str):
        return (None, (CODE_SENSITIVITY_MALFORMED, f"data-sensitivity policy must be a string, not {type(value).__name__}; a human must decide it"))
    if value not in SENSITIVITY_LEVELS:
        return (None, (CODE_SENSITIVITY_UNRECOGNIZED, f"data-sensitivity {value!r} is not one of {SENSITIVITY_LEVELS}; a human must decide it"))
    return (value, None)


def _resolve_token(constraints: Mapping[str, Any], key: str, allowed: tuple[str, ...], default: str, code: str) -> tuple[str | None, tuple[str, str] | None]:
    """Resolve an optional bounded-token fact.

    An *absent* fact resolves to ``default`` (the conservative value).  A present
    fact that is non-string or not in ``allowed`` fails closed with ``code`` — a
    malformed fact never gets a default.
    """
    if key not in constraints:
        return (default, None)
    value = constraints[key]
    if not isinstance(value, str) or value not in allowed:
        return (None, (code, f"{key} must be one of {allowed} when supplied, got {value!r}"))
    return (value, None)


def build_initial_policy(
    constraints: Mapping[str, Any] | None,
    *,
    project_id: str,
    request_id: str = "",
    request_text: str = "",
    policy_version: int = 1,
) -> PolicyBuildOutcome:
    """Build an initial :class:`ProjectPolicy` from explicit synthetic constraints.

    A pure, deterministic function returning a bounded :class:`PolicyBuildOutcome`
    (it never raises for a domain condition, never mutates its inputs, and performs
    no I/O, clock read, LLM/provider call, persistence, event emission, or content
    egress).  ``constraints`` is a mapping of explicit user-constraint facts
    (recognised keys: ``data_sensitivity``, ``network``, ``resources``,
    ``automation_level``, ``execution_mode``); unrecognised keys are preserved
    verbatim in the binding but never interpreted.  Precedence — structural
    validity first, then the key sensitivity gate, then the remaining optional
    facts, so any uncertainty fails closed:

    1. **Identifiers** — an invalid ``project_id`` or non-positive-integer
       ``policy_version`` → ``rejected_malformed``.
    2. **Constraints shape** — a non-mapping or non-string-keyed ``constraints`` →
       ``rejected_malformed``.  ``None`` is treated as an empty mapping (which then
       fails the sensitivity gate, since sensitivity is required).
    3. **Data sensitivity (required)** — missing / non-string / unrecognised →
       ``approval_needed`` with a distinct reason code; never a permissive default,
       never a granted approval.
    4. **Optional facts** — a malformed ``network`` / ``resources`` /
       ``automation_level`` / ``execution_mode`` (including ``REAL``, which the
       initial builder may never produce) → ``rejected_malformed``; an absent one
       resolves to its conservative default.
    5. Otherwise build the policy, self-check it with
       :func:`validate_project_policy`, and return ``built``.
    """
    # A verbatim snapshot of the original facts, preserved (never rewritten,
    # normalised, redacted, or dropped) and decoupled from the caller's objects so
    # neither the inputs nor the snapshot can be mutated through the other.
    original_constraints = copy.deepcopy(constraints) if constraints is not None else None
    binding: dict[str, Any] = {
        "project_id": project_id,
        "request_id": request_id,
        "request_text": request_text,
        "policy_version": policy_version,
        "original_constraints": original_constraints,
    }

    def _reject(code: str, message: str) -> PolicyBuildOutcome:
        return PolicyBuildOutcome(status=_CODE_STATUS[code], reason_code=code, message=message, binding=dict(binding))

    # 1. Identifiers.
    if common.validate_identifier(project_id, "project_id"):
        return _reject(CODE_PROJECT_ID_MALFORMED, "project_id is missing or not a valid identifier (lowercase token, no whitespace)")
    if not isinstance(policy_version, int) or isinstance(policy_version, bool) or policy_version < 1:
        return _reject(CODE_POLICY_VERSION_MALFORMED, "policy_version must be a positive integer")

    # 2. Constraints shape (None → empty; sensitivity is then missing).
    if constraints is None:
        constraints = {}
    if not isinstance(constraints, Mapping):
        return _reject(CODE_CONSTRAINTS_MALFORMED, "constraints, when supplied, must be a mapping of explicit user-constraint facts")
    if any(not isinstance(k, str) for k in constraints):
        return _reject(CODE_CONSTRAINTS_MALFORMED, "constraints keys must be strings")

    # 3. Data sensitivity — the required key policy; fail closed to approval-needed.
    sensitivity, sens_error = _resolve_sensitivity(constraints)
    if sens_error is not None:
        code, message = sens_error
        approval = ApprovalNeeded(
            project_id=project_id,
            subject_type="ProjectPolicy",
            subject_id=project_id,
            subject_version=policy_version,
            gate=GATE_DATA_SENSITIVITY,
            reason_code=code,
            message=message,
        )
        binding["resolved"] = {"data_sensitivity": None}
        return PolicyBuildOutcome(
            status=STATUS_APPROVAL_NEEDED,
            reason_code=code,
            message=message,
            approval_request=approval.to_dict(),
            binding=dict(binding),
        )
    assert isinstance(sensitivity, str)

    # 4. Optional bounded facts (absent → conservative default; malformed → reject).
    network, net_error = _resolve_token(constraints, KEY_NETWORK, NETWORK_LEVELS, DEFAULT_NETWORK, CODE_NETWORK_MALFORMED)
    if net_error is not None:
        return _reject(*net_error)
    resources, res_error = _resolve_token(constraints, KEY_RESOURCES, RESOURCE_LEVELS, DEFAULT_RESOURCES, CODE_RESOURCES_MALFORMED)
    if res_error is not None:
        return _reject(*res_error)
    automation, auto_error = _resolve_token(constraints, KEY_AUTOMATION, AUTOMATION_LEVELS, DEFAULT_AUTOMATION_LEVEL, CODE_AUTOMATION_MALFORMED)
    if auto_error is not None:
        return _reject(*auto_error)
    execution_mode, mode_error = _resolve_token(
        constraints, KEY_EXECUTION_MODE, PERMITTED_EXECUTION_MODES, DEFAULT_EXECUTION_MODE, CODE_EXECUTION_MODE_NOT_PERMITTED
    )
    if mode_error is not None:
        # A REAL request is the common, important sub-case: spell it out.
        raw = constraints.get(KEY_EXECUTION_MODE)
        message = (
            "execution_mode REAL is a hard stop the initial policy builder may not produce; it requires explicit separate authorization"
            if raw == "REAL"
            else mode_error[1]
        )
        return _reject(CODE_EXECUTION_MODE_NOT_PERMITTED, message)

    assert isinstance(network, str) and isinstance(resources, str) and isinstance(automation, str) and isinstance(execution_mode, str)

    # Inert resource policy — recorded in the binding only, never in the
    # authoritative ProjectPolicy (so it cannot change the policy's identity).
    resource_policy = {"tier": resources}
    network_policy = dict(_NETWORK_PROFILES[network])
    export_policy = {"external_export_allowed": False, "requires_approval": _SENSITIVITY_EXPORT_REQUIRES_APPROVAL[sensitivity]}

    binding["resolved"] = {
        "data_sensitivity": sensitivity,
        "network": network,
        "resources": resources,
        "automation_level": automation,
        "execution_mode": execution_mode,
        "resource_policy": resource_policy,
    }

    policy = ProjectPolicy(
        project_id=project_id,
        execution_mode=execution_mode,
        automation_level=automation,
        policy_version=policy_version,
        network_policy=network_policy,
        data_sensitivity=sensitivity,
        export_policy=export_policy,
    )
    policy_dict = policy.to_dict()

    # Self-check: a built policy must pass the existing validator (tamper-evident
    # id/hash + bounded execution mode / automation level / version).  If it does
    # not, fail closed rather than emit an invalid policy.
    errors = validate_project_policy(policy_dict)
    if errors:
        return _reject(CODE_POLICY_INVALID, "; ".join(errors))

    return PolicyBuildOutcome(
        status=STATUS_BUILT,
        reason_code=CODE_BUILT,
        message="initial project policy built from explicit user constraints",
        policy=policy_dict,
        binding=dict(binding),
    )


__all__ = [
    "STATUS_BUILT",
    "STATUS_APPROVAL_NEEDED",
    "STATUS_REJECTED_MALFORMED",
    "STATUSES",
    "CODE_BUILT",
    "CODE_SENSITIVITY_MISSING",
    "CODE_SENSITIVITY_MALFORMED",
    "CODE_SENSITIVITY_UNRECOGNIZED",
    "CODE_PROJECT_ID_MALFORMED",
    "CODE_POLICY_VERSION_MALFORMED",
    "CODE_CONSTRAINTS_MALFORMED",
    "CODE_NETWORK_MALFORMED",
    "CODE_RESOURCES_MALFORMED",
    "CODE_AUTOMATION_MALFORMED",
    "CODE_EXECUTION_MODE_NOT_PERMITTED",
    "CODE_POLICY_INVALID",
    "REASON_CODES",
    "KEY_SENSITIVITY",
    "KEY_NETWORK",
    "KEY_RESOURCES",
    "KEY_AUTOMATION",
    "KEY_EXECUTION_MODE",
    "SENSITIVITY_LEVELS",
    "NETWORK_LEVELS",
    "RESOURCE_LEVELS",
    "PERMITTED_EXECUTION_MODES",
    "DEFAULT_NETWORK",
    "DEFAULT_RESOURCES",
    "DEFAULT_EXECUTION_MODE",
    "DEFAULT_AUTOMATION_LEVEL",
    "GATE_DATA_SENSITIVITY",
    "ApprovalNeeded",
    "PolicyBuildOutcome",
    "build_initial_policy",
]
