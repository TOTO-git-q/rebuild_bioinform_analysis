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


def _recompute_policy_content_hash(policy: dict[str, Any]) -> str:
    """Recompute the content_hash exactly as ``build_project_policy`` does."""
    body = {
        "schema_version": policy.get("schema_version"),
        "project_id": policy.get("project_id"),
        "execution_mode": policy.get("execution_mode"),
        "policy_version": policy.get("policy_version"),
        "status": policy.get("status"),
    }
    return hash_payload(body)


def _recompute_policy_id(policy: dict[str, Any]) -> str:
    return make_stable_id(
        "project_policy",
        {
            "project_id": policy.get("project_id"),
            "execution_mode": policy.get("execution_mode"),
            "policy_version": policy.get("policy_version"),
        },
    )


def verify_project_policy_integrity(policy: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Gate 3 (R0-01 review-fix): the ProjectPolicy is an *immutable* object.

    Unlike :func:`validate_policy_state_consistency` (which only checks that the
    two projections *agree*), this recomputes the policy's own integrity from its
    payload, so editing the policy JSON — even if ``ProjectState`` is edited to
    match — is detected:

    - ``content_hash`` is recomputed from the canonical body and compared;
    - ``project_policy_id`` is recomputed from (project_id, execution_mode,
      policy_version) and compared;
    - ``execution_mode`` must be a valid enum member;
    - ``project_id`` must agree with ``ProjectState.project_id``;
    - ``ProjectState.project_policy_ref`` must be present and point at the policy.

    An attacker who flips ``execution_mode`` DEMO→REAL in *both* files without
    re-deriving the hash/id (which they cannot, without the project's own
    hashing) is rejected here.
    """
    errors: list[str] = []
    if not policy:
        errors.append("project policy is missing; execution_mode has no authoritative source")
        return errors

    mode = policy.get("execution_mode")
    if mode not in EXECUTION_MODES:
        errors.append(f"ProjectPolicy.execution_mode={mode!r} is not a valid execution mode")

    if policy.get("content_hash") != _recompute_policy_content_hash(policy):
        errors.append("ProjectPolicy.content_hash does not match recomputed content (policy tampered)")

    if policy.get("project_policy_id") != _recompute_policy_id(policy):
        errors.append("ProjectPolicy.project_policy_id does not match recomputed id (policy tampered)")

    state_project_id = state.get("project_id")
    if state_project_id and policy.get("project_id") != state_project_id:
        errors.append("ProjectPolicy.project_id disagrees with ProjectState.project_id")

    if not state.get("project_policy_ref"):
        errors.append("ProjectState.project_policy_ref is missing; policy binding is unverifiable")

    # Subsume the agreement check (execution_mode + ref pointing) so the
    # integrity gate is a strict superset; de-dup while preserving order.
    for e in validate_policy_state_consistency(policy, state):
        if e not in errors:
            errors.append(e)
    return errors


# --- Provenance shape validation + pseudo-REAL detection --------------------

# --- Gate 7: structured provenance consistency ------------------------------
# Each source_class implies which *retrieval paths* are physically coherent.
# This is a real cross-field audit of the structured provenance triple, NOT a
# substitute based on how the accession string happens to be spelled.
_RETRIEVAL_CONSISTENT_WITH_SOURCE: dict[str, frozenset[str]] = {
    # A committed fixture is never *fetched live* over the network; it is read
    # from the local tree (or replayed). Claiming LIVE would misstate its origin.
    "SYNTHETIC_FIXTURE": frozenset({"LOCAL_CACHE", "RECORDED_REPLAY"}),
    # A public database may be hit live, replayed, or served from a local cache.
    "PUBLIC_DATABASE": frozenset({"LIVE", "RECORDED_REPLAY", "LOCAL_CACHE"}),
    # User-uploaded files and on-disk local data are, by definition, already
    # local; they are never *obtained* by a live network retrieval.
    "USER_UPLOAD": frozenset({"LOCAL_CACHE"}),
    "LOCAL_DATA": frozenset({"LOCAL_CACHE"}),
    # Unknown-provenance legacy data must not claim to have been fetched live.
    "LEGACY_UNKNOWN": frozenset({"LOCAL_CACHE", "RECORDED_REPLAY"}),
}

# The strongest verification a given source_class may *honestly* assert. Data
# whose provenance is unknown cannot have been verified beyond "bytes exist".
_MAX_VERIFICATION_BY_SOURCE: dict[str, str] = {
    "LEGACY_UNKNOWN": "UNVERIFIED",
}

# --- Gate 8: honest, source_class-driven bundle prose -----------------------
# An exported reproduction bundle must describe its inputs by what they *are*.
# Only a SYNTHETIC_FIXTURE may be called a committed fixture; real data sources
# must never be labelled as a fixture, and unknown-provenance data must say so.
_ORIGIN_DESCRIPTION_BY_SOURCE: dict[str, str] = {
    "SYNTHETIC_FIXTURE": "Inputs are a committed synthetic fixture, not a real biological dataset.",
    "PUBLIC_DATABASE": "Inputs are real data retrieved from a public database.",
    "USER_UPLOAD": "Inputs are user-uploaded files.",
    "LOCAL_DATA": "Inputs are local on-disk research data.",
    "LEGACY_UNKNOWN": "Inputs are of unknown (legacy, unverified) provenance.",
}


def describe_dataset_origin(source_class: str, *, accession: str = "") -> str:
    """Return one honest sentence describing where a bundle's inputs come from,
    driven by the *actual* ``source_class`` (Gate 8).

    A real data source (PUBLIC_DATABASE / USER_UPLOAD / LOCAL_DATA) is never
    described as a "committed fixture"; an unrecognised/missing source_class is
    treated conservatively as unknown provenance rather than as a fixture.
    """
    base = _ORIGIN_DESCRIPTION_BY_SOURCE.get(source_class)
    if base is None:
        base = _ORIGIN_DESCRIPTION_BY_SOURCE["LEGACY_UNKNOWN"]
    if source_class == "PUBLIC_DATABASE" and accession:
        base = base[:-1] + f" (accession `{accession}`)."
    return base


def validate_provenance(candidate: dict[str, Any]) -> list[str]:
    """Audit the *structured* provenance triple for internal consistency.

    Gate 7 (R0-01 review-fix): consistency is decided by the source_class /
    retrieval_mode / verification_level fields themselves — not by pattern-
    matching the accession string. The accession checks below remain only as a
    secondary honesty sanity-check; they never stand in for the structural audit.
    """
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

    # Only run the structural audit once the three fields are individually valid.
    if sc in SOURCE_CLASSES and rm in RETRIEVAL_MODES and vl in VERIFICATION_LEVELS:
        allowed = _RETRIEVAL_CONSISTENT_WITH_SOURCE[sc]
        if rm not in allowed:
            errors.append(f"retrieval_mode {rm!r} is inconsistent with source_class {sc!r} (allowed: {sorted(allowed)})")
        ceiling = _MAX_VERIFICATION_BY_SOURCE.get(sc)
        if ceiling is not None and verification_at_least(vl, ceiling) and vl != ceiling:
            errors.append(f"source_class {sc!r} cannot honestly claim verification_level {vl!r} (max {ceiling})")
        # A self-recorded replay can never, on its own, ground a checksum
        # verification of real materialized files — regardless of source_class.
        if rm == "RECORDED_REPLAY" and vl == "FILES_CHECKSUM_VERIFIED":
            errors.append("RECORDED_REPLAY retrieval cannot ground FILES_CHECKSUM_VERIFIED (a replay verifies its own recording, not real files)")

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


def validate_real_mode_lock(
    profile: dict[str, Any],
    execution_mode: str,
    *,
    file_checksums: dict[str, str],
    recomputed_checksums: dict[str, str] | None = None,
) -> list[str]:
    """Gate 5: a REAL run may only *lock* a dataset that is genuinely verified.

    ``validate_real_mode_dataset`` blocks a synthetic fixture before discovery;
    this is the lock-time defence in depth.  For REAL execution it enforces:

      * ``verification_level`` >= ``FILES_CHECKSUM_VERIFIED`` (identifier- or
        metadata-only verification can never ground a REAL scientific lock);
      * ``retrieval_mode`` is not ``RECORDED_REPLAY`` — a replay recording can
        never, on its own, authorize a REAL lock;
      * ``file_checksums`` is non-empty and every entry is a non-empty digest;
      * when ``recomputed_checksums`` is supplied (the digests of the actually
        materialized files), every recorded checksum matches the file and there
        is no missing or extra file.

    Non-REAL modes lock unchanged (returns ``[]``).
    """
    if execution_mode != "REAL":
        return []
    errors: list[str] = []
    vl = profile.get("verification_level", "UNVERIFIED")
    if not verification_at_least(vl, _MIN_VERIFICATION_FOR_LOCK):
        errors.append(f"REAL lock requires verification_level >= {_MIN_VERIFICATION_FOR_LOCK}, got {vl!r}")
    if profile.get("retrieval_mode") == "RECORDED_REPLAY":
        errors.append("REAL lock cannot be authorized by RECORDED_REPLAY retrieval alone")
    if not file_checksums:
        errors.append("REAL lock requires non-empty file_checksums")
    else:
        for name, digest in file_checksums.items():
            if not digest:
                errors.append(f"REAL lock requires a non-empty checksum for {name!r}")
        if recomputed_checksums is not None:
            for name, digest in file_checksums.items():
                actual = recomputed_checksums.get(name)
                if actual is None:
                    errors.append(f"REAL lock checksum for {name!r} has no materialized file to verify")
                elif actual != digest:
                    errors.append(f"REAL lock checksum mismatch for {name!r}")
            for name in recomputed_checksums:
                if name not in file_checksums:
                    errors.append(f"REAL lock has a materialized file {name!r} with no recorded checksum")
    return errors


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


# --- Gate 6 (R0-01 review-fix): explicit behavior for legacy projects -------

# Marker recorded on a ProjectState after a one-time legacy migration, so the
# migration is auditable and never silently re-applied.
LEGACY_MIGRATION_MARKER = "migrated_from_legacy"


def classify_project_policy_state(policy: dict[str, Any], state: dict[str, Any]) -> str:
    """Decide how to treat a project whose ProjectPolicy is *absent*, instead of
    bare-raising a generic integrity failure on every policy-less project.

    Returns one of:

    - ``"CURRENT"`` — a ProjectPolicy exists; the normal integrity gate runs.
      A *present but tampered* policy still fails :func:`verify_project_policy_integrity`
      and is rejected; this classification never weakens that path.
    - ``"LEGACY_MIGRATABLE"`` — no policy **and** ``ProjectState`` carries no
      policy binding: a genuinely pre-R0-01 project.  Safe to migrate
      *conservatively* to a DEMO policy (its data inherits LEGACY_UNKNOWN /
      UNVERIFIED via :func:`normalize_legacy_provenance`).
    - ``"MIGRATION_REQUIRED"`` — no policy but ``ProjectState`` *references* one
      (``project_policy_ref`` set, policy file gone): the binding was lost.
      Auto-migrating could silently relabel a once-REAL project to DEMO, so this
      is surfaced explicitly and **never** auto-migrated.
    """
    if policy:
        return "CURRENT"
    if state.get("project_policy_ref"):
        return "MIGRATION_REQUIRED"
    return "LEGACY_MIGRATABLE"


def migrate_legacy_project_policy(project_id: str) -> dict[str, Any]:
    """Build the conservative DEMO ProjectPolicy for a one-time legacy migration.

    A project whose provenance predates R0-01 cannot be trusted to back
    scientific output, so it is *always* migrated to DEMO — never REAL.  The
    returned policy is a normal immutable ProjectPolicy and therefore passes
    :func:`verify_project_policy_integrity` once bound to the state.
    """
    return build_project_policy(project_id, "DEMO")


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
        errors.append(f"decision id {stored_id!r} does not match recomputed id {recomputed_id!r} (decision content was tampered with)")

    reasons = _eligibility_reason_codes(
        execution_mode=decision.get("execution_mode", ""),
        source_class=decision.get("source_class", ""),
        verification_level=decision.get("verification_level", ""),
        qc_status=decision.get("qc_status", ""),
    )
    expected_verdict = "ELIGIBLE" if not reasons else "INELIGIBLE"
    if decision.get("decision") != expected_verdict:
        errors.append(f"decision verdict {decision.get('decision')!r} disagrees with the facts (recomputed {expected_verdict!r}); verdict was tampered with")
    if sorted(decision.get("reason_codes", [])) != sorted(reasons):
        errors.append("decision reason_codes disagree with the facts")
    expected_release = RESEARCH_PRELIMINARY if expected_verdict == "ELIGIBLE" else DEMONSTRATION_ONLY
    if decision.get("release_status") != expected_release:
        errors.append(f"release_status {decision.get('release_status')!r} disagrees with the recomputed verdict")

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
        errors.append(f"object references decision {referencing_decision_id!r} but the verified decision is {stored_id!r}")
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


def expected_decision_inputs(
    artifact: dict[str, Any] | None,
    dataset_profile: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """The ``evaluated_input_refs`` / ``evaluated_input_hashes`` a genuine decision
    *must* carry, derived from the real persisted ``registered_artifact`` and
    ``dataset_profile`` — the exact facts :meth:`Pipeline._synthesize_evidence`
    bound the decision to when it created it.

    The authoritative gate passes these as the *expected* values so a forged but
    internally self-consistent decision (refs/hashes rewritten and the decision id
    recomputed to match) is still rejected: the decision's stored refs/hashes are
    compared against the live downstream objects, not merely against themselves.
    Keep this in lock-step with the ``evaluated_input_*`` arguments in
    :meth:`Pipeline._synthesize_evidence`.
    """
    artifact = artifact or {}
    dataset_profile = dataset_profile or {}
    refs = [artifact.get("artifact_id", ""), dataset_profile.get("dataset_profile_id", "")]
    hashes = [artifact.get("checksum_sha256", "")]
    return refs, hashes


# --- Authoritative eligibility gate (Gate 1 of R0-01 review-fix) -------------


def authoritative_release(
    decision: dict[str, Any] | None,
    *,
    policy: dict[str, Any] | None = None,
    claims: list[dict[str, Any]] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    artifact: dict[str, Any] | None = None,
    dataset_profile: dict[str, Any] | None = None,
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
    4. When the live ``artifact`` (registered_artifact) and ``dataset_profile``
       are supplied, the decision's ``evaluated_input_refs`` / ``hashes`` must
       match the values *derived from those real persisted objects*
       (:func:`expected_decision_inputs`).  This closes the forged-but-self-
       consistent decision bypass (Blocker 2): rewriting the evaluated inputs and
       recomputing the decision id no longer suffices, because the gate checks the
       decision against the live downstream objects, not just against itself.

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

    expected_refs: list[str] | None = None
    expected_hashes: list[str] | None = None
    if artifact is not None or dataset_profile is not None:
        expected_refs, expected_hashes = expected_decision_inputs(artifact, dataset_profile)

    reasons: list[str] = list(
        verify_decision_integrity(
            decision,
            policy=policy,
            expected_input_refs=expected_refs,
            expected_input_hashes=expected_hashes,
        )
    )
    eligible = decision_is_authoritatively_eligible(
        decision,
        policy=policy,
        expected_input_refs=expected_refs,
        expected_input_hashes=expected_hashes,
    )

    # When (and only when) the decision is authoritatively ELIGIBLE, a formal
    # release is on the table — so *every* Claim/EvidenceItem must reference this
    # exact authoritative decision id.  This binding is enforced independently of
    # the cached ``scientific_output_eligible`` flag on the objects: that flag is
    # a display cache and is never trusted for authorisation.  An object that is
    # missing the decision id, or references a foreign one, forces
    # DEMONSTRATION_ONLY even when its cached flag is false or absent (Blocker 1).
    if eligible:
        authoritative_id = decision.get("scientific_eligibility_decision_id")
        for obj in list(claims or []) + list(evidence_items or []):
            ref = obj.get("scientific_eligibility_decision_id")
            if ref != authoritative_id:
                eligible = False
                reasons.append("OBJECT_MISSING_DECISION_ID" if not ref else "OBJECT_REFERENCES_FOREIGN_DECISION")

    if not eligible and not reasons:
        reasons = list(decision.get("reason_codes", [])) or ["INELIGIBLE"]

    return {
        "scientific_output_eligible": bool(eligible),
        "release_status": RESEARCH_PRELIMINARY if eligible else DEMONSTRATION_ONLY,
        "reasons": [] if eligible else reasons,
    }
