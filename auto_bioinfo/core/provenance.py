"""Truthful-execution provenance model (Work Order R0-01).

This module keeps four *orthogonal* facts about a run separate, so a test
fixture can never be silently dressed up as a real scientific result:

- ``execution_mode``    — what the project is *run for*    (DEMO / TEST / REAL)
- ``source_class``      — where the data *actually comes from*
- ``retrieval_mode``    — how the data was *obtained this time*
- ``verification_level``— how far the source was *actually verified*

Scientific eligibility is never a free boolean an adapter can set.  It is a
re-computed, immutable ``ScientificEligibilityDecision`` derived from the four
facts above plus QC status; Evidence / Claim / Report may only *reference* a
decision, and the admission gate always recomputes it from the source objects
rather than trusting any ``eligible=true`` already on an object.
"""

from __future__ import annotations

from typing import Any

from .ids import hash_payload, make_stable_id
from .schemas import CANONICAL_SCHEMA_VERSION, now_iso

# --- The four orthogonal vocabularies ---------------------------------------
EXECUTION_MODES = ("DEMO", "TEST", "REAL")
SOURCE_CLASSES = ("SYNTHETIC_FIXTURE", "PUBLIC_DATABASE", "USER_UPLOAD", "LOCAL_DATA", "LEGACY_UNKNOWN")
RETRIEVAL_MODES = ("LIVE", "RECORDED_REPLAY", "LOCAL_CACHE")
VERIFICATION_LEVELS = ("UNVERIFIED", "IDENTIFIER_VERIFIED", "METADATA_VERIFIED", "FILES_CHECKSUM_VERIFIED")

# Source classes that describe *real* data and may, in principle, back a
# scientific claim.  SYNTHETIC_FIXTURE and LEGACY_UNKNOWN never can.
REAL_DATA_SOURCE_CLASSES = ("PUBLIC_DATABASE", "USER_UPLOAD", "LOCAL_DATA")

# Release status carried by demo vs. eligible scientific outputs.
DEMONSTRATION_ONLY = "DEMONSTRATION_ONLY"
RESEARCH_PRELIMINARY = "RESEARCH_PRELIMINARY"

_MIN_VERIFICATION_FOR_ELIGIBLE = "METADATA_VERIFIED"
_MIN_VERIFICATION_FOR_LOCK = "FILES_CHECKSUM_VERIFIED"


def verification_at_least(level: str, threshold: str) -> bool:
    if level not in VERIFICATION_LEVELS or threshold not in VERIFICATION_LEVELS:
        return False
    return VERIFICATION_LEVELS.index(level) >= VERIFICATION_LEVELS.index(threshold)


# --- ProjectPolicy: the authoritative source of execution_mode --------------

def build_project_policy(project_id: str, execution_mode: str, *, policy_version: int = 1) -> dict[str, Any]:
    if execution_mode not in EXECUTION_MODES:
        raise ValueError(f"execution_mode must be one of {EXECUTION_MODES}, got {execution_mode!r}")
    body = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "project_id": project_id,
        "execution_mode": execution_mode,
        "policy_version": policy_version,
        "status": "active",
    }
    content_hash = hash_payload(body)
    return {
        **body,
        "project_policy_id": make_stable_id("project_policy", {"project_id": project_id, "execution_mode": execution_mode, "policy_version": policy_version}),
        "content_hash": content_hash,
        "created_at": now_iso(),
    }


def validate_policy_state_consistency(policy: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """ProjectState must agree with the immutable ProjectPolicy projection."""
    errors: list[str] = []
    if not policy:
        errors.append("project policy is missing; execution_mode has no authoritative source")
        return errors
    if state.get("execution_mode") != policy.get("execution_mode"):
        errors.append(f"ProjectState.execution_mode={state.get('execution_mode')!r} disagrees with ProjectPolicy={policy.get('execution_mode')!r}")
    ref = state.get("project_policy_ref")
    if ref and ref != policy.get("project_policy_id"):
        errors.append("ProjectState.project_policy_ref does not point to the active ProjectPolicy")
    return errors


# --- Provenance shape validation + pseudo-REAL detection --------------------

def validate_provenance(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sc = candidate.get("source_class")
    rm = candidate.get("retrieval_mode")
    vl = candidate.get("verification_level")
    if sc not in SOURCE_CLASSES:
        errors.append(f"source_class must be one of {SOURCE_CLASSES}, got {sc!r}")
    if rm not in RETRIEVAL_MODES:
        errors.append(f"retrieval_mode must be one of {RETRIEVAL_MODES}, got {rm!r}")
    if vl not in VERIFICATION_LEVELS:
        errors.append(f"verification_level must be one of {VERIFICATION_LEVELS}, got {vl!r}")
    accession = str(candidate.get("accession", "") or candidate.get("dataset_id", "")).upper()
    if sc == "PUBLIC_DATABASE" and (not accession or accession.startswith("AUTO_") or accession.startswith("MOCK_") or accession.startswith("FIXTURE")):
        errors.append("PUBLIC_DATABASE source requires a real accession (not empty/AUTO_/MOCK_/FIXTURE)")
    if sc == "SYNTHETIC_FIXTURE" and verification_at_least(vl, "METADATA_VERIFIED") and not str(accession).startswith("FIXTURE"):
        # a synthetic fixture may have checksum-verified files, but must stay
        # honestly labelled as a fixture accession.
        errors.append("SYNTHETIC_FIXTURE must use a clearly-labelled FIXTURE accession")
    return errors


def validate_real_mode_dataset(candidate: dict[str, Any], execution_mode: str) -> list[str]:
    """REAL runs may not be backed by synthetic fixtures (checked before lock)."""
    if execution_mode == "REAL" and candidate.get("source_class") == "SYNTHETIC_FIXTURE":
        return ["REAL execution_mode cannot be backed by a SYNTHETIC_FIXTURE dataset (POLICY_FAILURE)"]
    return []


# --- Legacy normalisation (conservative; never invents provenance) ----------

def normalize_legacy_provenance(obj: dict[str, Any]) -> dict[str, Any]:
    """Fill missing provenance on an object loaded without R0-01 fields.

    Missing source is ``LEGACY_UNKNOWN`` (never SYNTHETIC_FIXTURE), verification
    is ``UNVERIFIED``, and a legacy ``verified=true`` is recorded only as a
    *claim the old system made* — never promoted to a real verification level.
    """
    out = dict(obj)
    if "source_class" not in out:
        out["source_class"] = "LEGACY_UNKNOWN"
    if "retrieval_mode" not in out:
        out["retrieval_mode"] = "LOCAL_CACHE"
    if "verification_level" not in out:
        out["verification_level"] = "UNVERIFIED"
    if "verified" in out and "legacy_verified_assertion" not in out:
        out["legacy_verified_assertion"] = bool(out.get("verified"))
    out.setdefault("scientific_output_eligible", False)
    return out


# --- ScientificEligibilityDecision (immutable, always recomputed) -----------

def _eligibility_reason_codes(
    *,
    execution_mode: str,
    source_class: str,
    verification_level: str,
    qc_status: str,
) -> list[str]:
    """The single source of truth for *why* an output is (in)eligible.

    Both fresh evaluation and integrity re-verification call this, so a tampered
    ``decision`` verdict can never disagree with the facts that produced it.
    """
    reasons: list[str] = []
    if execution_mode != "REAL":
        reasons.append("EXECUTION_MODE_NOT_REAL")
    if source_class not in REAL_DATA_SOURCE_CLASSES:
        reasons.append("SOURCE_CLASS_NOT_REAL_DATA")
    if not verification_at_least(verification_level, _MIN_VERIFICATION_FOR_ELIGIBLE):
        reasons.append("VERIFICATION_BELOW_METADATA")
    if str(qc_status).lower() not in {"pass", "pass_with_warnings"}:
        reasons.append("QC_NOT_PASSED")
    return reasons


def _decision_id_for(inputs: dict[str, Any]) -> str:
    """Canonical decision id derived purely from the evaluated input facts."""
    return make_stable_id("scientific_eligibility_decision", inputs)


def _decision_inputs(
    *,
    execution_mode: str,
    source_class: str,
    retrieval_mode: str,
    verification_level: str,
    qc_status: str,
    evaluated_input_refs: list[str],
    evaluated_input_hashes: list[str],
    policy_id: str,
    policy_version: int,
) -> dict[str, Any]:
    return {
        "execution_mode": execution_mode,
        "source_class": source_class,
        "retrieval_mode": retrieval_mode,
        "verification_level": verification_level,
        "qc_status": qc_status,
        "evaluated_input_refs": sorted(evaluated_input_refs),
        "evaluated_input_hashes": sorted(evaluated_input_hashes),
        "policy_id": policy_id,
        "policy_version": policy_version,
    }


def evaluate_scientific_eligibility(
    *,
    execution_mode: str,
    source_class: str,
    retrieval_mode: str,
    verification_level: str,
    qc_status: str,
    evaluated_input_refs: list[str],
    evaluated_input_hashes: list[str],
    policy_id: str,
    policy_version: int,
) -> dict[str, Any]:
    """Deterministically decide whether an output may back a scientific Claim.

    The decision id is a stable hash of the *inputs* (not the timestamp), so the
    same facts always yield the same decision id and re-computation is verifiable.
    """
    reasons = _eligibility_reason_codes(
        execution_mode=execution_mode,
        source_class=source_class,
        verification_level=verification_level,
        qc_status=qc_status,
    )

    decision = "ELIGIBLE" if not reasons else "INELIGIBLE"
    inputs = _decision_inputs(
        execution_mode=execution_mode,
        source_class=source_class,
        retrieval_mode=retrieval_mode,
        verification_level=verification_level,
        qc_status=qc_status,
        evaluated_input_refs=evaluated_input_refs,
        evaluated_input_hashes=evaluated_input_hashes,
        policy_id=policy_id,
        policy_version=policy_version,
    )
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "scientific_eligibility_decision_id": _decision_id_for(inputs),
        "decision": decision,
        "reason_codes": reasons,
        "execution_mode": execution_mode,
        "source_class": source_class,
        "retrieval_mode": retrieval_mode,
        "verification_level": verification_level,
        "qc_status": qc_status,
        "evaluated_input_refs": list(evaluated_input_refs),
        "evaluated_input_hashes": list(evaluated_input_hashes),
        "policy_id": policy_id,
        "policy_version": policy_version,
        "evaluated_at": now_iso(),
        "release_status": RESEARCH_PRELIMINARY if decision == "ELIGIBLE" else DEMONSTRATION_ONLY,
    }


def is_eligible(decision: dict[str, Any]) -> bool:
    return bool(decision) and decision.get("decision") == "ELIGIBLE"


# --- Decision integrity validation (Gate 2 of R0-01 review-fix) -------------

def verify_decision_integrity(
    decision: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    expected_input_refs: list[str] | None = None,
    expected_input_hashes: list[str] | None = None,
    referencing_decision_id: str | None = None,
) -> list[str]:
    """Re-verify a persisted ``ScientificEligibilityDecision`` against its own
    facts and the active policy, returning a list of integrity violations.

    This is the anti-tamper core of the authoritative eligibility gate: a formal
    output must never be authorised from a decision that fails any check here.

    Checks performed:

    1. **Decision id** is recomputed from the decision's own stored input facts
       and must match the stored ``scientific_eligibility_decision_id`` (detects
       any edit to execution_mode / source_class / verification / qc / refs /
       hashes / policy binding).
    2. **Verdict** (``decision`` + ``reason_codes``) is recomputed from the same
       facts and must match — the verdict is *not* part of the id hash, so a
       flipped ``INELIGIBLE -> ELIGIBLE`` is caught here rather than by (1).
    3. **release_status** must agree with the recomputed verdict.
    4. **Policy binding** — when ``policy`` is given, ``policy_id`` /
       ``policy_version`` must match the active ProjectPolicy.
    5. **evaluated_input_refs / hashes** — when expected values are supplied,
       they must match exactly.
    6. **Back-reference** — when a Claim/EvidenceItem ``referencing_decision_id``
       is supplied, it must point at this decision.
    """
    errors: list[str] = []
    if not decision:
        return ["scientific eligibility decision is missing"]

    stored_id = decision.get("scientific_eligibility_decision_id")
    inputs = _decision_inputs(
        execution_mode=decision.get("execution_mode", ""),
        source_class=decision.get("source_class", ""),
        retrieval_mode=decision.get("retrieval_mode", ""),
        verification_level=decision.get("verification_level", ""),
        qc_status=decision.get("qc_status", ""),
        evaluated_input_refs=list(decision.get("evaluated_input_refs", [])),
        evaluated_input_hashes=list(decision.get("evaluated_input_hashes", [])),
        policy_id=decision.get("policy_id", ""),
        policy_version=decision.get("policy_version", 1),
    )
    recomputed_id = _decision_id_for(inputs)
    if stored_id != recomputed_id:
        errors.append(
            f"decision id {stored_id!r} does not match recomputed id {recomputed_id!r} "
            "(decision content was tampered with)"
        )

    reasons = _eligibility_reason_codes(
        execution_mode=decision.get("execution_mode", ""),
        source_class=decision.get("source_class", ""),
        verification_level=decision.get("verification_level", ""),
        qc_status=decision.get("qc_status", ""),
    )
    expected_verdict = "ELIGIBLE" if not reasons else "INELIGIBLE"
    if decision.get("decision") != expected_verdict:
        errors.append(
            f"decision verdict {decision.get('decision')!r} disagrees with the facts "
            f"(recomputed {expected_verdict!r}); verdict was tampered with"
        )
    if sorted(decision.get("reason_codes", [])) != sorted(reasons):
        errors.append("decision reason_codes disagree with the facts")
    expected_release = RESEARCH_PRELIMINARY if expected_verdict == "ELIGIBLE" else DEMONSTRATION_ONLY
    if decision.get("release_status") != expected_release:
        errors.append(
            f"release_status {decision.get('release_status')!r} disagrees with the recomputed verdict"
        )

    if policy is not None:
        if decision.get("policy_id") != policy.get("project_policy_id"):
            errors.append("decision policy_id does not match the active ProjectPolicy")
        if decision.get("policy_version") != policy.get("policy_version"):
            errors.append("decision policy_version does not match the active ProjectPolicy")

    if expected_input_refs is not None and sorted(decision.get("evaluated_input_refs", [])) != sorted(expected_input_refs):
        errors.append("decision evaluated_input_refs do not match the evaluated objects")
    if expected_input_hashes is not None and sorted(decision.get("evaluated_input_hashes", [])) != sorted(expected_input_hashes):
        errors.append("decision evaluated_input_hashes do not match the evaluated objects")

    if referencing_decision_id is not None and referencing_decision_id != stored_id:
        errors.append(
            f"object references decision {referencing_decision_id!r} but the verified decision is {stored_id!r}"
        )
    return errors


def decision_is_authoritatively_eligible(
    decision: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    expected_input_refs: list[str] | None = None,
    expected_input_hashes: list[str] | None = None,
    referencing_decision_id: str | None = None,
) -> bool:
    """True only when the decision passes integrity *and* its recomputed verdict
    is ELIGIBLE.  Never trusts a cached ``scientific_output_eligible`` flag."""
    if verify_decision_integrity(
        decision,
        policy=policy,
        expected_input_refs=expected_input_refs,
        expected_input_hashes=expected_input_hashes,
        referencing_decision_id=referencing_decision_id,
    ):
        return False
    reasons = _eligibility_reason_codes(
        execution_mode=decision.get("execution_mode", ""),
        source_class=decision.get("source_class", ""),
        verification_level=decision.get("verification_level", ""),
        qc_status=decision.get("qc_status", ""),
    )
    return not reasons


def recompute_eligibility_for(obj: dict[str, Any], *, qc_status: str, policy: dict[str, Any]) -> dict[str, Any]:
    """Re-derive a fresh eligibility decision for an object, ignoring any
    ``scientific_output_eligible`` flag already present on it (anti-tamper)."""
    return evaluate_scientific_eligibility(
        execution_mode=policy.get("execution_mode", "DEMO"),
        source_class=obj.get("source_class", "LEGACY_UNKNOWN"),
        retrieval_mode=obj.get("retrieval_mode", "LOCAL_CACHE"),
        verification_level=obj.get("verification_level", "UNVERIFIED"),
        qc_status=qc_status,
        evaluated_input_refs=[str(obj.get("evidence_item_id") or obj.get("dataset_id") or "")],
        evaluated_input_hashes=[],
        policy_id=policy.get("project_policy_id", ""),
        policy_version=policy.get("policy_version", 1),
    )


def is_formally_exportable(obj: dict[str, Any]) -> bool:
    """A Demo/ineligible Claim or EvidenceItem may never enter a formal export."""
    return bool(obj.get("scientific_output_eligible")) and obj.get("release_status") == RESEARCH_PRELIMINARY


# --- Authoritative eligibility gate (Gate 1 of R0-01 review-fix) -------------

def authoritative_release(
    decision: dict[str, Any] | None,
    *,
    policy: dict[str, Any] | None = None,
    claims: list[dict[str, Any]] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The single authoritative eligibility gate shared by every output surface
    (``inspect`` / ``report`` / ``bundle`` / CLI formal export).

    The released eligibility is recomputed *only* from the persisted
    ``ScientificEligibilityDecision`` and the active ``ProjectPolicy``:

    1. With no persisted decision, the release is ``DEMONSTRATION_ONLY``.
    2. The decision must pass :func:`verify_decision_integrity` against the
       active policy (anti-tamper) and its recomputed verdict must be ELIGIBLE
       (:func:`decision_is_authoritatively_eligible`).
    3. Any ``Claim`` / ``EvidenceItem`` that *claims* eligibility must reference
       this exact authoritative decision id; one pointing at a foreign decision
       forces ``DEMONSTRATION_ONLY``.

    Crucially, the cached ``scientific_output_eligible`` flag on a Claim or
    EvidenceItem is **never** trusted as authorisation — it is a display cache
    only.  Flipping it to ``true`` therefore cannot move the release to
    ``RESEARCH_PRELIMINARY``; the verdict still comes from the recomputed
    decision.
    """
    if not decision:
        return {
            "scientific_output_eligible": False,
            "release_status": DEMONSTRATION_ONLY,
            "reasons": ["NO_ELIGIBILITY_DECISION"],
        }

    reasons: list[str] = list(verify_decision_integrity(decision, policy=policy))
    eligible = decision_is_authoritatively_eligible(decision, policy=policy)

    authoritative_id = decision.get("scientific_eligibility_decision_id")
    for obj in list(claims or []) + list(evidence_items or []):
        if obj.get("scientific_output_eligible") and obj.get("scientific_eligibility_decision_id") != authoritative_id:
            eligible = False
            reasons.append("OBJECT_REFERENCES_FOREIGN_DECISION")

    if not eligible and not reasons:
        reasons = list(decision.get("reason_codes", [])) or ["INELIGIBLE"]

    return {
        "scientific_output_eligible": bool(eligible),
        "release_status": RESEARCH_PRELIMINARY if eligible else DEMONSTRATION_ONLY,
        "reasons": [] if eligible else reasons,
    }
