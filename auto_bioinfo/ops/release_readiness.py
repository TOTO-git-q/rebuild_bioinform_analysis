"""Offline release-readiness checklist, hard-stop gates, and evolution boundary (WP-27).

WP-27 hands a *validated* version to its users and maintainers and freezes the MVP
boundary.  Most of that is documentation (see ``docs/rebuild/wp27_*.md``), but two
pieces are enforceable *objects* rather than prose, and live here:

- **A release-readiness checklist with hard-stop gates (T-27-01, T-27-10, T-27-12).**
  A deterministic evaluation of explicit gate results: the release is ``ready``
  only when **every hard-stop gate** has passed *with an evidence reference*; a
  single unmet hard-stop gate blocks the release (fail closed).  This also carries
  the extra pre-production gate set (privacy / ethics / compliance / storage /
  model-egress) that must pass before any real sensitive data is processed.
- **The MVP evolution boundary (T-27-09).** A bounded in-scope / out-of-scope
  classification so a non-core "full platform" feature cannot silently be treated
  as part of the core closed loop.

Everything is a pure, offline, deterministic value: no deployment, no network, no
clock, no persistence.  A ``ready`` decision is a *checklist value*, never a real
release action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- Bounded release-readiness gates -----------------------------------------
# Each gate is a hard-stop (a release cannot proceed until it passes) unless
# flagged otherwise.  The pre-production sensitive-data gates (T-27-10) are the
# extra gates that must additionally pass before real sensitive data is processed.
GATE_SECURITY_SCAN = "security_scan_clean"
GATE_ACCEPTANCE = "acceptance_suite_passed"
GATE_REPRODUCTION = "reproduction_verified"
GATE_NO_BLOCKING_FINDINGS = "no_unresolved_blocking_findings"
GATE_MIGRATION_RECOVERY = "migration_recovery_rehearsed"
GATE_TRACEABILITY = "requirement_traceability_complete"
GATE_OPERATOR_DOCS = "operator_docs_present"
# Pre-production sensitive-data gates (T-27-10):
GATE_PRIVACY = "privacy_review_passed"
GATE_ETHICS = "ethics_review_passed"
GATE_COMPLIANCE = "compliance_review_passed"
GATE_STORAGE = "storage_controls_verified"
GATE_MODEL_EGRESS = "model_egress_controls_verified"


@dataclass(frozen=True)
class ReadinessGate:
    """One release gate: an id, description, whether it is a hard stop, and its tier.

    ``tier`` is ``"core"`` (required for any release) or ``"sensitive_data"``
    (additionally required before real sensitive data is processed).  A hard-stop
    gate blocks the release when unmet; every gate here is a hard stop by design.
    """

    gate_id: str
    description: str
    hard_stop: bool = True
    tier: str = "core"

    def to_dict(self) -> dict[str, Any]:
        return {"gate_id": self.gate_id, "description": self.description, "hard_stop": self.hard_stop, "tier": self.tier}


CORE_GATES: tuple[ReadinessGate, ...] = (
    ReadinessGate(GATE_SECURITY_SCAN, "dependency/image/secret/static/license scans have no unresolved high-severity findings"),
    ReadinessGate(GATE_ACCEPTANCE, "the frozen end-to-end acceptance suite passed on the release candidate"),
    ReadinessGate(GATE_REPRODUCTION, "the reproduction bundle ran clean-room and matched the comparison spec"),
    ReadinessGate(GATE_NO_BLOCKING_FINDINGS, "there are no unresolved blocking findings in the gap report"),
    ReadinessGate(GATE_MIGRATION_RECOVERY, "database migration and a pre-production restore/recovery drill succeeded"),
    ReadinessGate(GATE_TRACEABILITY, "the requirement→task→evidence matrix is complete with no unjustified MUST skipped"),
    ReadinessGate(GATE_OPERATOR_DOCS, "install/config/start/stop/backup/restore/upgrade operator docs exist and were rehearsed"),
)

SENSITIVE_DATA_GATES: tuple[ReadinessGate, ...] = (
    ReadinessGate(GATE_PRIVACY, "a privacy review of real-data handling passed", tier="sensitive_data"),
    ReadinessGate(GATE_ETHICS, "an ethics review of the intended real-data use passed", tier="sensitive_data"),
    ReadinessGate(GATE_COMPLIANCE, "a compliance/regulatory review passed", tier="sensitive_data"),
    ReadinessGate(GATE_STORAGE, "sensitive-data storage controls (encryption/retention/access) are verified", tier="sensitive_data"),
    ReadinessGate(GATE_MODEL_EGRESS, "external-model data-egress controls are verified for real data", tier="sensitive_data"),
)

ALL_GATES: dict[str, ReadinessGate] = {gate.gate_id: gate for gate in (*CORE_GATES, *SENSITIVE_DATA_GATES)}

# --- Bounded status vocabulary -----------------------------------------------
STATUS_READY = "ready"
STATUS_BLOCKED = "blocked"
STATUS_INVALID = "invalid"

STATUSES = (STATUS_READY, STATUS_BLOCKED, STATUS_INVALID)

CODE_READY = "RELEASE_READY"
CODE_BLOCKED_UNMET_GATE = "RELEASE_BLOCKED_UNMET_GATE"
CODE_BLOCKED_MISSING_EVIDENCE = "RELEASE_BLOCKED_MISSING_EVIDENCE"
CODE_BLOCKED_MISSING_GATE = "RELEASE_BLOCKED_MISSING_GATE"
CODE_MALFORMED = "RELEASE_MALFORMED"

REASON_CODES = (CODE_READY, CODE_BLOCKED_UNMET_GATE, CODE_BLOCKED_MISSING_EVIDENCE, CODE_BLOCKED_MISSING_GATE, CODE_MALFORMED)


@dataclass(frozen=True)
class GateResult:
    """The reported outcome of one gate: passed/failed and an evidence reference.

    A gate is only *credited* as met when ``passed`` is true **and** a non-empty
    ``evidence_ref`` is supplied — a bare "it passed" without evidence never counts.
    """

    gate_id: str
    passed: bool
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"gate_id": self.gate_id, "passed": self.passed, "evidence_ref": self.evidence_ref}


@dataclass(frozen=True)
class ReleaseReadinessDecision:
    """The deterministic, reason-coded release-readiness outcome.

    ``unmet_gates`` names the hard-stop gates that were failed, unreported, or
    reported without evidence.  ``ready`` is true only when none are unmet.
    """

    status: str
    reason_code: str
    message: str
    required_gates: tuple[str, ...] = ()
    met_gates: tuple[str, ...] = ()
    unmet_gates: tuple[str, ...] = ()
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status == STATUS_READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "required_gates": list(self.required_gates),
            "met_gates": list(self.met_gates),
            "unmet_gates": list(self.unmet_gates),
            "ready": self.ready,
            "binding": dict(self.binding),
        }


def required_gate_ids(*, include_sensitive_data: bool = False) -> tuple[str, ...]:
    """The hard-stop gate ids required for a release.

    Always the core gates; additionally the sensitive-data gates when
    ``include_sensitive_data`` is set (i.e. the release will process real sensitive
    data and must clear the pre-production tier).
    """
    gates = list(CORE_GATES)
    if include_sensitive_data:
        gates += list(SENSITIVE_DATA_GATES)
    return tuple(gate.gate_id for gate in gates if gate.hard_stop)


def evaluate_release_readiness(results: Any, *, include_sensitive_data: bool = False) -> ReleaseReadinessDecision:
    """Evaluate release readiness against the hard-stop gates (T-27-01/10/12), fail-closed.

    ``results`` is a collection of :class:`GateResult`.  The release is ``ready``
    only when **every** required hard-stop gate is met — reported ``passed`` *with*
    a non-empty evidence reference.  A gate that is failed, unreported, or reported
    without evidence blocks the release (fail closed), and every blocking gate is
    listed in ``unmet_gates``.  ``include_sensitive_data`` additionally requires the
    pre-production sensitive-data gate tier.
    """
    if not isinstance(results, (list, tuple)):
        return ReleaseReadinessDecision(STATUS_INVALID, CODE_MALFORMED, "results must be a sequence of GateResult")
    by_id: dict[str, GateResult] = {}
    for result in results:
        if not isinstance(result, GateResult) or not isinstance(result.gate_id, str) or not result.gate_id:
            return ReleaseReadinessDecision(STATUS_INVALID, CODE_MALFORMED, "each result must be a GateResult with a non-empty gate_id")
        # Last report for a gate wins (a re-run supersedes an earlier attempt).
        by_id[result.gate_id] = result

    required = required_gate_ids(include_sensitive_data=include_sensitive_data)
    met: list[str] = []
    unmet: list[str] = []
    missing_evidence = False
    missing_gate = False
    for gate_id in required:
        result = by_id.get(gate_id)
        if result is None:
            unmet.append(gate_id)
            missing_gate = True
            continue
        if not result.passed:
            unmet.append(gate_id)
            continue
        if not str(result.evidence_ref).strip():
            unmet.append(gate_id)
            missing_evidence = True
            continue
        met.append(gate_id)

    binding = {"required_count": len(required), "met_count": len(met), "include_sensitive_data": include_sensitive_data}
    if not unmet:
        return ReleaseReadinessDecision(
            status=STATUS_READY,
            reason_code=CODE_READY,
            message=f"all {len(required)} hard-stop gate(s) passed with evidence; release readiness satisfied",
            required_gates=required,
            met_gates=tuple(met),
            unmet_gates=(),
            binding=binding,
        )
    if missing_gate:
        code = CODE_BLOCKED_MISSING_GATE
    elif missing_evidence:
        code = CODE_BLOCKED_MISSING_EVIDENCE
    else:
        code = CODE_BLOCKED_UNMET_GATE
    return ReleaseReadinessDecision(
        status=STATUS_BLOCKED,
        reason_code=code,
        message=f"{len(unmet)} hard-stop gate(s) are unmet; release is blocked (fail closed): {', '.join(sorted(unmet))}",
        required_gates=required,
        met_gates=tuple(met),
        unmet_gates=tuple(sorted(unmet)),
        binding=binding,
    )


# --- Release manifest (T-27-01) ----------------------------------------------
# The component kinds a release manifest must pin so every artifact is verifiable.
MANIFEST_COMPONENTS = ("code", "schema", "database", "prompt", "method", "image", "data_fixture")


@dataclass(frozen=True)
class ReleaseManifestResult:
    """The outcome of assembling a release manifest: complete or missing components."""

    complete: bool
    manifest: dict[str, str] = field(default_factory=dict)
    missing_components: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"complete": self.complete, "manifest": dict(self.manifest), "missing_components": list(self.missing_components)}


def build_release_manifest(versions: Any) -> ReleaseManifestResult:
    """Assemble a deterministic release manifest from component version/hash facts (T-27-01).

    ``versions`` maps each :data:`MANIFEST_COMPONENTS` kind to a non-empty
    version/hash string.  The manifest is ``complete`` only when every component is
    pinned; any missing/blank component is reported so an unpinned release cannot be
    declared verifiable.  Pure and deterministic (keys are sorted).
    """
    mapping = versions if isinstance(versions, dict) else {}
    manifest: dict[str, str] = {}
    missing: list[str] = []
    for component in MANIFEST_COMPONENTS:
        value = mapping.get(component)
        if isinstance(value, str) and value.strip():
            manifest[component] = value.strip()
        else:
            missing.append(component)
    return ReleaseManifestResult(complete=not missing, manifest=dict(sorted(manifest.items())), missing_components=tuple(missing))


# --- MVP evolution boundary (T-27-09) ----------------------------------------
SCOPE_IN = "in_scope"
SCOPE_OUT = "out_of_scope"
SCOPE_UNKNOWN = "unknown"

# The core closed-loop capabilities that are inside the MVP boundary.
IN_SCOPE_FEATURES = frozenset(
    {
        "intake_and_question_resolution",
        "scope_resolution",
        "evidence_planning",
        "resource_discovery_and_locking",
        "workflow_compilation",
        "task_execution_and_qc",
        "evidence_synthesis_and_alignment_audit",
        "reporting_and_reproduction_bundle",
        "approvals_and_gates",
        "failure_recovery_and_replanning",
        "security_and_observability_baseline",
    }
)

# Explicitly deferred "full platform" features that must NOT be treated as core.
OUT_OF_SCOPE_FEATURES = frozenset(
    {
        "multi_tenant_billing",
        "realtime_collaboration_ui",
        "arbitrary_third_party_plugin_marketplace",
        "auto_publication_submission",
        "self_service_model_finetuning",
        "production_sensitive_data_processing",
        "cross_organization_data_sharing",
        "clinical_decision_support",
    }
)


def classify_feature(feature: Any) -> str:
    """Classify a feature against the MVP evolution boundary (T-27-09).

    Returns :data:`SCOPE_IN`, :data:`SCOPE_OUT`, or :data:`SCOPE_UNKNOWN`.  An
    unknown feature is deliberately **not** assumed in-scope — it defaults to
    ``unknown`` so a new capability must be explicitly placed rather than silently
    absorbed into the core loop.
    """
    if not isinstance(feature, str):
        return SCOPE_UNKNOWN
    key = feature.strip().lower()
    if key in IN_SCOPE_FEATURES:
        return SCOPE_IN
    if key in OUT_OF_SCOPE_FEATURES:
        return SCOPE_OUT
    return SCOPE_UNKNOWN


__all__ = [
    "GATE_SECURITY_SCAN",
    "GATE_ACCEPTANCE",
    "GATE_REPRODUCTION",
    "GATE_NO_BLOCKING_FINDINGS",
    "GATE_MIGRATION_RECOVERY",
    "GATE_TRACEABILITY",
    "GATE_OPERATOR_DOCS",
    "GATE_PRIVACY",
    "GATE_ETHICS",
    "GATE_COMPLIANCE",
    "GATE_STORAGE",
    "GATE_MODEL_EGRESS",
    "ReadinessGate",
    "CORE_GATES",
    "SENSITIVE_DATA_GATES",
    "ALL_GATES",
    "STATUS_READY",
    "STATUS_BLOCKED",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_READY",
    "CODE_BLOCKED_UNMET_GATE",
    "CODE_BLOCKED_MISSING_EVIDENCE",
    "CODE_BLOCKED_MISSING_GATE",
    "CODE_MALFORMED",
    "REASON_CODES",
    "GateResult",
    "ReleaseReadinessDecision",
    "required_gate_ids",
    "evaluate_release_readiness",
    "MANIFEST_COMPONENTS",
    "ReleaseManifestResult",
    "build_release_manifest",
    "SCOPE_IN",
    "SCOPE_OUT",
    "SCOPE_UNKNOWN",
    "IN_SCOPE_FEATURES",
    "OUT_OF_SCOPE_FEATURES",
    "classify_feature",
]
