from typing import Any

from . import common
from .schemas import APPROVAL_DECISIONS, APPROVAL_STATES, AUTOMATION_LEVELS, CLAIM_LEVELS


def validate_required_fields(obj: dict[str, Any], required: list[str]) -> list[str]:
    errors = []
    for field in required:
        if field not in obj or obj[field] in (None, "", []):
            errors.append(f"{field}: missing required field")
    return errors


def validate_enum(value: str, allowed: list[str], field: str) -> list[str]:
    return [] if value in allowed else [f"{field}: must be one of {', '.join(allowed)}"]


def validate_no_unknown_verified_dataset(candidate: dict[str, Any]) -> list[str]:
    errors = []
    if candidate.get("verified") is True:
        source_status = str(candidate.get("source_status", "")).lower()
        accession = str(candidate.get("accession", "") or candidate.get("dataset_id", "")).upper()
        if source_status in {"mock", "mock_placeholder", "placeholder", "unknown"}:
            errors.append("verified dataset cannot come from mock/placeholder/unknown source_status")
        if accession.startswith("AUTO_") or accession.startswith("MOCK_") or not accession:
            errors.append("verified dataset requires a real accession, not AUTO_/MOCK_/empty")
    return errors


def validate_claim_ceiling(claim: dict[str, Any], max_allowed: str) -> list[str]:
    errors = []
    claim_level = claim.get("claim_level", "")
    if claim_level not in CLAIM_LEVELS:
        return [f"claim_level: must be one of {', '.join(CLAIM_LEVELS)}"]
    if max_allowed not in CLAIM_LEVELS:
        return [f"max_allowed: must be one of {', '.join(CLAIM_LEVELS)}"]
    if CLAIM_LEVELS.index(claim_level) > CLAIM_LEVELS.index(max_allowed):
        errors.append(f"claim_level {claim_level} exceeds ceiling {max_allowed}")
    return errors


def validate_artifact_manifest(manifest: dict[str, Any]) -> list[str]:
    errors = validate_required_fields(
        manifest,
        ["artifact_id", "project_id", "path", "exists", "checksum_sha256", "is_placeholder", "qc_status"],
    )
    if manifest.get("exists") is not True:
        errors.append("artifact cannot support evidence when exists=false")
    if manifest.get("is_placeholder") is True:
        errors.append("artifact cannot support evidence when is_placeholder=true")
    if manifest.get("qc_status") == "fail":
        errors.append("artifact cannot support evidence when qc_status=fail")
    return errors


def validate_project_state(state: dict[str, Any]) -> list[str]:
    errors = validate_required_fields(
        state,
        ["schema_version", "project_id", "current_stage", "allowed_next_stages", "status"],
    )
    if "allowed_next_stages" in state and not isinstance(state["allowed_next_stages"], list):
        errors.append("allowed_next_stages: expected list")
    return errors


# --- WP-02a / T-02-02: Project & Policy and Approval validators --------------


def _valid_execution_modes() -> tuple[str, ...]:
    """The authoritative execution_mode vocabulary (DEMO/TEST/REAL).

    Imported lazily from :mod:`auto_bioinfo.core.provenance` to avoid an import
    cycle (provenance imports schema constants at module load)."""
    from .provenance import EXECUTION_MODES

    return EXECUTION_MODES


def validate_original_request(request: dict[str, Any]) -> list[str]:
    """The original request text is immutable and hash-bound.

    Fails if the recorded ``original_text_sha256`` does not match the stored
    ``original_text`` (the original was tampered with), and surfaces — without
    failing — whether a normalised form is present.  Normalisation must never
    overwrite the original, so a normalised request must still carry the exact
    original text and matching hash.
    """
    errors = validate_required_fields(request, ["schema_version", "project_id", "original_text", "original_text_sha256"])
    errors += common.validate_identifier(request.get("project_id", ""), "project_id")
    text = request.get("original_text")
    if isinstance(text, str) and text:
        expected = common.content_hash(text)
        if request.get("original_text_sha256") != expected:
            errors.append("original_text_sha256 does not match original_text (the original request was altered)")
    submitter = request.get("submitter")
    if submitter:
        errors += common.validate_actor(submitter, "submitter")
    return errors


def validate_project_policy(policy: dict[str, Any]) -> list[str]:
    """Validate a ProjectPolicy's project binding, execution mode, automation
    level, version, and content-hash/id integrity (tamper-evident)."""
    errors = validate_required_fields(policy, ["schema_version", "project_id", "execution_mode", "automation_level", "policy_version", "status"])
    errors += common.validate_identifier(policy.get("project_id", ""), "project_id")
    if policy.get("execution_mode") not in _valid_execution_modes():
        errors.append(f"execution_mode: must be one of {', '.join(_valid_execution_modes())}")
    if policy.get("automation_level") not in AUTOMATION_LEVELS:
        errors.append(f"automation_level: must be one of {', '.join(AUTOMATION_LEVELS)}")
    version = policy.get("policy_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("policy_version: must be a positive integer")
    # Integrity: recompute content_hash / project_policy_id from the body so an
    # edited policy (even with both files changed) is detected.
    if "content_hash" in policy or "project_policy_id" in policy:
        from .schemas import ProjectPolicy

        rebuilt = ProjectPolicy(
            project_id=policy.get("project_id", ""),
            execution_mode=policy.get("execution_mode", ""),
            automation_level=policy.get("automation_level", "A0"),
            policy_version=version if isinstance(version, int) and not isinstance(version, bool) else 1,
            network_policy=policy.get("network_policy", {}),
            data_sensitivity=policy.get("data_sensitivity", "unspecified"),
            export_policy=policy.get("export_policy", {}),
            schema_version=policy.get("schema_version", ""),
            status=policy.get("status", ""),
        )
        if policy.get("content_hash") != rebuilt.content_hash():
            errors.append("content_hash does not match recomputed content (policy tampered)")
        if policy.get("project_policy_id") != rebuilt.policy_id():
            errors.append("project_policy_id does not match recomputed id (policy tampered)")
    return errors


def validate_approval_request(request: dict[str, Any]) -> list[str]:
    """An ApprovalRequest must bind the exact subject object and version."""
    errors = validate_required_fields(request, ["schema_version", "project_id", "subject_type", "subject_id", "subject_version", "gate", "state"])
    version = request.get("subject_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("subject_version: must be a positive integer (the version under review)")
    if request.get("state") not in APPROVAL_STATES:
        errors.append(f"state: must be one of {', '.join(APPROVAL_STATES)}")
    requested_by = request.get("requested_by")
    if requested_by:
        errors += common.validate_actor(requested_by, "requested_by")
    return errors


def validate_approval_decision(decision: dict[str, Any], request: dict[str, Any] | None = None, current_version: int | None = None) -> list[str]:
    """An ApprovalDecision must bind the exact target object/version it ruled on.

    When the originating ``request`` is supplied, the decision's
    subject_type/id/version must match it exactly.  When ``current_version`` is
    supplied, a decision approving a *superseded* version (one that is no longer
    current) is rejected — you cannot approve an old draft as if it were live
    (data-model constraint #9).
    """
    errors = validate_required_fields(
        decision, ["schema_version", "approval_request_id", "project_id", "subject_type", "subject_id", "subject_version", "decision"]
    )
    if decision.get("decision") not in APPROVAL_DECISIONS:
        errors.append(f"decision: must be one of {', '.join(APPROVAL_DECISIONS)}")
    version = decision.get("subject_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("subject_version: must be a positive integer (the exact version decided)")
    decided_by = decision.get("decided_by")
    if decided_by:
        errors += common.validate_actor(decided_by, "decided_by")
    if request is not None:
        for key in ("subject_type", "subject_id", "subject_version"):
            if decision.get(key) != request.get(key):
                errors.append(f"{key}: decision does not bind the same subject as its ApprovalRequest")
        if (
            decision.get("approval_request_id")
            and request.get("approval_request_id")
            and decision.get("approval_request_id") != request.get("approval_request_id")
        ):
            errors.append("approval_request_id: decision references a different ApprovalRequest")
    if (
        current_version is not None
        and decision.get("decision") == "approved"
        and isinstance(version, int)
        and not isinstance(version, bool)
        and version != current_version
    ):
        errors.append(f"cannot approve superseded subject_version {version} as current (current is {current_version})")
    return errors
