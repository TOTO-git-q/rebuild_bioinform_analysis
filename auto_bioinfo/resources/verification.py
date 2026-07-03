"""Local deterministic resource verification + metadata factualisation (WP-09 / T-09-01..12).

Turns a discovered :class:`~auto_bioinfo.core.schemas.ResourceCandidate` into a
*verified* profile — a :class:`~auto_bioinfo.core.schemas.DatasetProfile` for a
dataset, or a lane-local :class:`PaperProfile` / :class:`AnnotationSourceProfile`
— by checking existence and parsing metadata against an **offline verification
registry** (:class:`VerificationRegistry`).  The registry is the deterministic,
recorded stand-in for the real verification tool: nothing here reaches the
network, reads a credential, or a clock; a candidate is verified only against a
recorded fact, never against an LLM's memory.

What the plan requires, realised offline:

- **Existence with explicit status** (T-09-01): accession / DOI / PMID / version
  existence resolves to ``exists`` / ``not_found`` / ``redirected`` /
  ``access_restricted``; a redirect follows to the canonical id and re-checks.
- **Raw metadata artifact** (T-09-02): the recorded raw metadata plus its content
  checksum and source URI are kept on the verification record.
- **Field-level factualisation** (T-09-03/04): species / tissue / disease /
  platform / samples / grouping / age / sex / batch / intervention are parsed with
  a source location and a confidence; a missing donor is an explicit ``unknown``,
  never a guess.
- **File inventory** (T-09-05): file *visibility* and *downloadability* are kept
  separate — a listed file is not assumed retrievable.
- **Relations, licence, evidence tier** (T-09-06/07/08/09): a paper↔dataset
  relation needs an explicit recorded cross-reference (title similarity alone is
  not enough); an unclear licence is ``NEED_MORE_INFORMATION``; a paper's evidence
  type is bounded and never over-stated; an annotation records its version /
  update / entity scope / evidence tier and a missing version limits reproduction.
- **Completeness + human correction** (T-09-10/11): a completeness score plus a
  missing-field list (the score never substitutes for a hard-required fact); a
  human correction is a *new version* that preserves the original tool value,
  evidence and actor and never overwrites the tool fact.
- **Golden-sample parse** (T-09-12): :func:`parse_dataset_metadata` is a pure
  deterministic function a contract test can pin, so an external-format change
  makes the test fail explicitly.

All pure, offline, deterministic; produced profiles carry an empty ``created_at``
and bounded status/verdict vocabularies.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.ids import hash_payload, make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION, DatasetProfile
from ..core.validation import validate_dataset_profile

# --- Bounded verification-verdict vocabulary (WP-09 exit criterion) -----------
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"
INCOMPLETE = "INCOMPLETE"
ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
VERIFICATION_VERDICTS = (VERIFIED, REJECTED, INCOMPLETE, ACCESS_RESTRICTED)

# --- Bounded existence-status vocabulary (T-09-01) ---------------------------
EXISTS = "exists"
NOT_FOUND = "not_found"
REDIRECTED = "redirected"
EXISTENCE_ACCESS_RESTRICTED = "access_restricted"
EXISTENCE_STATUSES = (EXISTS, NOT_FOUND, REDIRECTED, EXISTENCE_ACCESS_RESTRICTED)

# --- Bounded licence-clarity vocabulary (T-09-07) ----------------------------
LICENSE_CLEAR = "clear"
LICENSE_CONTROLLED = "controlled_access"
LICENSE_NEED_MORE_INFORMATION = "NEED_MORE_INFORMATION"
LICENSE_CLARITIES = (LICENSE_CLEAR, LICENSE_CONTROLLED, LICENSE_NEED_MORE_INFORMATION)

# --- Bounded paper evidence-type vocabulary (T-09-08) ------------------------
# Ordered weakest -> strongest; a paper is annotated only with what its recorded
# metadata supports.  The strongest tiers may never be inferred from an abstract.
EVIDENCE_TYPES = (
    "expression_association",
    "protein_detection",
    "functional_assay",
    "mechanistic",
    "causal",
)
# Tiers that require an explicit experimental flag; never inferred from prose.
_EXPERIMENTAL_EVIDENCE_TYPES = ("functional_assay", "mechanistic", "causal")

# --- Bounded annotation evidence-tier vocabulary (T-09-09) -------------------
ANNOTATION_EVIDENCE_TIERS = ("database_annotation", "computational_prediction", "curated", "experimentally_validated")

# The dataset facts a *usable* dataset profile must carry to be VERIFIED (not just
# INCOMPLETE).  The completeness score never substitutes for these (T-09-10).
_REQUIRED_DATASET_FACTS = ("organism", "modality", "platform", "samples")


# =============================================================================
# Offline verification registry (recorded fixtures)
# =============================================================================
@dataclass(frozen=True)
class RegistryRecord:
    """One recorded, synthetic verification fact for a (namespace, identifier).

    ``existence`` is a :data:`EXISTENCE_STATUSES` value; ``redirect_to`` is the
    canonical ``{"namespace","identifier"}`` for a redirect; ``raw_metadata`` is
    the recorded raw response the profile is parsed from; ``source_uri`` and
    ``access`` (``open`` / ``controlled`` / ``unknown``) and ``license`` complete
    the recorded fact.  Everything is clearly-synthetic and honestly labelled.
    """

    existence: str
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    redirect_to: dict[str, str] = field(default_factory=dict)
    source_uri: str = ""
    access: str = "unknown"
    license: str = ""
    source_class: str = "PUBLIC_DATABASE"
    # Explicit recorded cross-references (T-09-06): the ids this resource *itself*
    # declares it is related to, e.g. a dataset accession cited by a paper.
    declared_relations: list[dict[str, str]] = field(default_factory=list)
    # For literature: the recorded, bounded evidence type + whether an experimental
    # assay was actually recorded (never inferred from an abstract).
    evidence_type: str = ""
    experimental_assay_recorded: bool = False
    # For annotation: version / update / entity scope / evidence tier.
    version: str = ""
    updated: str = ""
    entity_scope: list[str] = field(default_factory=list)
    evidence_tier: str = ""


class VerificationRegistry:
    """A deterministic offline registry of recorded verification facts.

    Keyed by ``NAMESPACE::IDENTIFIER`` (upper-cased).  :meth:`lookup` returns the
    recorded :class:`RegistryRecord` or ``None`` (treated as ``not_found``).  It
    performs no I/O and is a pure function of its recordings.
    """

    def __init__(self, records: Mapping[tuple[str, str], RegistryRecord] | None = None) -> None:
        self._records: dict[str, RegistryRecord] = {}
        for (ns, ident), rec in (records or {}).items():
            self._records[self._key(ns, ident)] = rec

    @staticmethod
    def _key(namespace: str, identifier: str) -> str:
        return f"{str(namespace).strip().upper()}::{str(identifier).strip().upper()}"

    def lookup(self, namespace: str, identifier: str) -> RegistryRecord | None:
        return self._records.get(self._key(namespace, identifier))


# =============================================================================
# T-09-03/04/05: deterministic metadata parse (golden-sample pinnable)
# =============================================================================
_PARSED_FIELDS = ("organism", "tissue", "disease", "platform", "age", "sex", "batch", "intervention")


def parse_dataset_metadata(raw_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Parse raw dataset metadata into factual fields with source + confidence.

    Pure and deterministic (T-09-12 golden sample).  Each recognised field is
    emitted as ``{"value","source_location","confidence"}``; a field absent from
    the raw metadata is listed in ``missing_fields`` and never invented.  Samples
    and files are normalised; a file keeps *visibility* and *downloadability* as
    separate facts (T-09-05).  A donor/subject that the metadata does not state is
    recorded as an explicit ``unknown`` per sample (T-09-04), never guessed.
    """
    fields: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for name in _PARSED_FIELDS:
        if name in raw_metadata and str(raw_metadata.get(name, "") or "").strip():
            fields[name] = {"value": str(raw_metadata[name]).strip(), "source_location": f"metadata.{name}", "confidence": 1.0}
        else:
            missing.append(name)

    species = raw_metadata.get("species")
    species_list = [str(s).strip() for s in species if str(s).strip()] if isinstance(species, list) else ([str(species).strip()] if species else [])

    raw_samples = raw_metadata.get("samples", [])
    samples: list[dict[str, Any]] = []
    donor_mapping: dict[str, str] = {}
    if isinstance(raw_samples, list):
        for s in raw_samples:
            if not isinstance(s, Mapping):
                continue
            sid = str(s.get("sample_id", "") or "").strip()
            if not sid:
                continue
            donor = str(s.get("donor_id", "") or s.get("subject_id", "") or "").strip() or "unknown"
            donor_mapping[sid] = donor
            samples.append(
                {
                    "sample_id": sid,
                    "group": str(s.get("group", "") or "").strip(),
                    "donor_id": donor,  # explicit "unknown" when unstated (never guessed)
                    "donor_known": donor != "unknown",
                }
            )

    raw_files = raw_metadata.get("files", [])
    files: list[dict[str, Any]] = []
    if isinstance(raw_files, list):
        for f in raw_files:
            if not isinstance(f, Mapping):
                continue
            name = str(f.get("name", "") or "").strip()
            if not name:
                continue
            files.append(
                {
                    "name": name,
                    "file_type": str(f.get("file_type", "") or "unknown"),
                    "size_bytes": int(f["size_bytes"]) if isinstance(f.get("size_bytes"), int) and not isinstance(f.get("size_bytes"), bool) else None,
                    # Visibility (listed in metadata) is separate from downloadability
                    # (actually retrievable) — never conflated (T-09-05).
                    "visible": True,
                    "downloadable": bool(f.get("downloadable", False)),
                    "access_status": str(f.get("access_status", "") or "unknown"),
                }
            )

    return {
        "fields": fields,
        "missing_fields": missing,
        "species": species_list,
        "samples": samples,
        "donor_mapping": donor_mapping,
        "files": files,
        "modality": str(raw_metadata.get("modality", "") or "").strip(),
    }


# =============================================================================
# Lane-local profile objects (not yet in core.schemas — see report)
# =============================================================================
@dataclass(frozen=True)
class PaperProfile:
    """A verified literature profile (lane-local; consolidate into core later).

    A paper may only be VERIFIED with a unique identifier (PMID/DOI) — T-08-03 /
    T-09-01.  ``evidence_type`` is a bounded :data:`EVIDENCE_TYPES` tier that is
    never over-stated: an experimental tier requires a recorded assay flag.
    """

    paper_id: str
    namespace: str
    identifier: str
    title: str = ""
    verdict: str = INCOMPLETE
    verification_level: str = "UNVERIFIED"
    evidence_type: str = ""
    source_uri: str = ""
    raw_metadata_checksum: str = ""
    schema_version: str = CANONICAL_SCHEMA_VERSION
    status: str = "profiled"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {k: (list(v) if isinstance(v, list) else v) for k, v in self.__dict__.items()}
        data["paper_id"] = self.paper_id or make_stable_id("paper_profile", {"namespace": self.namespace, "identifier": self.identifier})
        return data


@dataclass(frozen=True)
class AnnotationSourceProfile:
    """A verified annotation-source profile (lane-local; consolidate later).

    Records version / update / entity scope / evidence tier (T-09-09).  A missing
    version limits the reproduction level (``reproduction_limited``) and a database
    annotation is never labelled experimentally validated.
    """

    annotation_source_id: str
    namespace: str
    identifier: str
    name: str = ""
    verdict: str = INCOMPLETE
    verification_level: str = "UNVERIFIED"
    version: str = ""
    updated: str = ""
    entity_scope: list[str] = field(default_factory=list)
    evidence_tier: str = ""
    reproduction_limited: bool = False
    source_uri: str = ""
    schema_version: str = CANONICAL_SCHEMA_VERSION
    status: str = "profiled"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {k: (list(v) if isinstance(v, list) else v) for k, v in self.__dict__.items()}
        data["annotation_source_id"] = self.annotation_source_id or make_stable_id(
            "annotation_source_profile", {"namespace": self.namespace, "identifier": self.identifier}
        )
        return data


# =============================================================================
# Verification result
# =============================================================================
@dataclass(frozen=True)
class VerificationResult:
    """The bounded outcome of verifying one candidate.

    ``verdict`` is one of :data:`VERIFICATION_VERDICTS`.  ``profile`` is the
    verified profile draft (DatasetProfile / PaperProfile / AnnotationSourceProfile
    dict) for a VERIFIED / INCOMPLETE resource, else ``None``.  ``record`` is the
    verification record (existence status, verification level, source uri, raw
    metadata checksum, reasons).
    """

    verdict: str
    reason_code: str
    message: str
    profile: dict[str, Any] | None = None
    record: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.verdict == VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "message": self.message,
            "verified": self.verified,
            "profile": copy.deepcopy(self.profile) if self.profile is not None else None,
            "record": copy.deepcopy(self.record),
        }


CODE_VERIFIED = "VERIFY_OK"
CODE_NOT_FOUND = "VERIFY_NOT_FOUND"
CODE_NO_IDENTIFIER = "VERIFY_NO_IDENTIFIER"
CODE_INCOMPLETE = "VERIFY_INCOMPLETE"
CODE_ACCESS_RESTRICTED = "VERIFY_ACCESS_RESTRICTED"
CODE_MALFORMED = "VERIFY_MALFORMED"
VERIFY_REASON_CODES = (CODE_VERIFIED, CODE_NOT_FOUND, CODE_NO_IDENTIFIER, CODE_INCOMPLETE, CODE_ACCESS_RESTRICTED, CODE_MALFORMED)


def _candidate_ns_id(candidate: Mapping[str, Any]) -> tuple[str, str]:
    namespace = str(candidate.get("namespace", "") or "").strip()
    identifier = str(candidate.get("identifier", "") or candidate.get("accession", "") or "").strip()
    return namespace, identifier


def _resolve_existence(registry: VerificationRegistry, namespace: str, identifier: str) -> tuple[RegistryRecord | None, str, str, dict[str, str]]:
    """Resolve existence, following a single redirect.  Returns (record, ns, id, redirect_chain)."""
    redirect_chain: dict[str, str] = {}
    rec = registry.lookup(namespace, identifier)
    if rec is not None and rec.existence == REDIRECTED and rec.redirect_to:
        redirect_chain = {"from": f"{namespace}:{identifier}", "to": f"{rec.redirect_to.get('namespace', '')}:{rec.redirect_to.get('identifier', '')}"}
        namespace = str(rec.redirect_to.get("namespace", namespace))
        identifier = str(rec.redirect_to.get("identifier", identifier))
        rec = registry.lookup(namespace, identifier)
    return rec, namespace, identifier, redirect_chain


def verify_candidate(candidate: Mapping[str, Any], registry: VerificationRegistry) -> VerificationResult:
    """Verify one discovered candidate against the offline registry, fail-closed.

    Routes by ``discovery_domain`` / ``resource_type`` to the dataset / paper /
    annotation verifier.  A candidate lacking a namespace+identifier can never be
    VERIFIED (T-08-03).  A registry miss is ``not_found`` -> REJECTED; a recorded
    ``access_restricted`` -> ACCESS_RESTRICTED; a resource that exists but lacks a
    required fact -> INCOMPLETE.
    """
    if not isinstance(candidate, Mapping):
        return VerificationResult(REJECTED, CODE_MALFORMED, "candidate must be a mapping")
    namespace, identifier = _candidate_ns_id(candidate)
    if not namespace or not identifier:
        return VerificationResult(REJECTED, CODE_NO_IDENTIFIER, "candidate has no namespace/identifier; a resource without a unique id can never be VERIFIED")

    rec, namespace, identifier, redirect_chain = _resolve_existence(registry, namespace, identifier)
    base_record: dict[str, Any] = {
        "verification_record_id": make_stable_id("verification_record", {"namespace": namespace, "identifier": identifier}),
        "namespace": namespace,
        "identifier": identifier,
        "redirect": redirect_chain or None,
    }

    if rec is None or rec.existence == NOT_FOUND:
        base_record["existence_status"] = NOT_FOUND
        return VerificationResult(REJECTED, CODE_NOT_FOUND, f"{namespace}:{identifier} does not exist in the verification registry", record=base_record)
    if rec.existence == EXISTENCE_ACCESS_RESTRICTED:
        base_record["existence_status"] = EXISTENCE_ACCESS_RESTRICTED
        base_record["access"] = rec.access or "controlled"
        return VerificationResult(ACCESS_RESTRICTED, CODE_ACCESS_RESTRICTED, f"{namespace}:{identifier} exists but is access-restricted", record=base_record)

    base_record["existence_status"] = EXISTS
    base_record["source_uri"] = rec.source_uri
    base_record["raw_metadata_checksum"] = hash_payload(dict(rec.raw_metadata)) if rec.raw_metadata else ""
    base_record["source_class"] = rec.source_class

    domain = str(candidate.get("discovery_domain", "") or "")
    if domain == "literature" or str(candidate.get("resource_type", "")).startswith("paper"):
        return _verify_paper(candidate, rec, base_record)
    if domain == "annotation" or str(candidate.get("resource_type", "")).startswith("annotation"):
        return _verify_annotation(candidate, rec, base_record)
    return _verify_dataset(candidate, rec, base_record)


def classify_license(record: RegistryRecord) -> str:
    """Classify licence clarity (T-09-07): unclear -> NEED_MORE_INFORMATION."""
    if record.access == "controlled":
        return LICENSE_CONTROLLED
    if record.license.strip():
        return LICENSE_CLEAR
    return LICENSE_NEED_MORE_INFORMATION


def _verify_dataset(candidate: Mapping[str, Any], rec: RegistryRecord, base_record: dict[str, Any]) -> VerificationResult:
    parsed = parse_dataset_metadata(rec.raw_metadata)
    organism = parsed["fields"].get("organism", {}).get("value", "") or (parsed["species"][0] if parsed["species"] else "")
    tissue = parsed["fields"].get("tissue", {}).get("value", "")
    modality = parsed["modality"] or "unknown"
    license_clarity = classify_license(rec)

    # Verification level: identifier verified always; metadata verified when the
    # raw metadata parsed into facts.  A recorded replay can never reach FILES_CHECKSUM.
    has_metadata = bool(parsed["fields"]) or bool(parsed["samples"])
    verification_level = "METADATA_VERIFIED" if has_metadata else "IDENTIFIER_VERIFIED"

    profile = DatasetProfile(
        dataset_id=make_stable_id("dataset", {"namespace": base_record["namespace"], "identifier": base_record["identifier"]}),
        modality=modality,
        organism=organism or "unknown",
        tissue=tissue or "unknown",
        status="profiled",
        source_class=rec.source_class,
        retrieval_mode="RECORDED_REPLAY",
        verification_level=verification_level,
        accession=base_record["identifier"],
        platform=parsed["fields"].get("platform", {}).get("value", ""),
        species=parsed["species"],
        sample_count=len(parsed["samples"]),
        samples=parsed["samples"],
        files=parsed["files"],
        license=rec.license,
    ).to_dict()
    # Field-level facts with source + confidence, plus the missing-field list.
    profile["metadata_facts"] = {
        "parsed_fields": parsed["fields"],
        "donor_mapping": parsed["donor_mapping"],
        "license_clarity": license_clarity,
        "source_uri": rec.source_uri,
    }
    profile["missing_facts"] = parsed["missing_fields"]

    # Defensive self-check: a self-produced profile must pass the core validator.
    if validate_dataset_profile(profile):
        base_record["existence_status"] = EXISTS
        base_record["verdict_detail"] = "profile failed core validation"
        return VerificationResult(INCOMPLETE, CODE_INCOMPLETE, "verified dataset profile failed internal validation", profile=None, record=base_record)

    completeness = dataset_completeness(profile)
    base_record["verification_level"] = verification_level
    base_record["license_clarity"] = license_clarity
    base_record["completeness"] = completeness

    missing_required = [f for f in _REQUIRED_DATASET_FACTS if _dataset_fact_missing(profile, f)]
    if missing_required:
        base_record["missing_required_facts"] = missing_required
        return VerificationResult(
            INCOMPLETE,
            CODE_INCOMPLETE,
            f"dataset exists but is missing required facts: {', '.join(missing_required)} (score does not substitute)",
            profile=profile,
            record=base_record,
        )
    if license_clarity == LICENSE_CONTROLLED:
        return VerificationResult(ACCESS_RESTRICTED, CODE_ACCESS_RESTRICTED, "dataset exists but is controlled-access", profile=profile, record=base_record)

    return VerificationResult(VERIFIED, CODE_VERIFIED, "dataset verified from recorded metadata", profile=profile, record=base_record)


def _dataset_fact_missing(profile: Mapping[str, Any], fact: str) -> bool:
    if fact == "samples":
        return not profile.get("samples")
    value = profile.get(fact, "")
    return not str(value or "").strip() or str(value).strip().lower() == "unknown"


def dataset_completeness(profile: Mapping[str, Any]) -> dict[str, Any]:
    """A completeness score + missing-field list (T-09-10).

    The score is a soft signal only and never authorises use — the hard required
    facts are checked independently by the verifier.
    """
    checked = ("organism", "modality", "platform", "tissue", "species", "samples", "files", "license")
    present = 0
    missing: list[str] = []
    for fact in checked:
        val = profile.get(fact)
        ok = bool(val) and not (isinstance(val, str) and val.strip().lower() in {"", "unknown"})
        if ok:
            present += 1
        else:
            missing.append(fact)
    return {"score": round(present / len(checked), 4), "present": present, "total": len(checked), "missing_fields": missing, "authoritative": False}


def _verify_paper(candidate: Mapping[str, Any], rec: RegistryRecord, base_record: dict[str, Any]) -> VerificationResult:
    namespace, identifier = base_record["namespace"], base_record["identifier"]
    # Evidence type is bounded and never over-stated: an experimental tier requires
    # a recorded assay flag (T-09-08).
    evidence_type = rec.evidence_type if rec.evidence_type in EVIDENCE_TYPES else ""
    if evidence_type in _EXPERIMENTAL_EVIDENCE_TYPES and not rec.experimental_assay_recorded:
        base_record["evidence_downgrade"] = f"{evidence_type} -> expression_association (no recorded experimental assay; refusing to over-state)"
        evidence_type = "expression_association"
    profile = PaperProfile(
        paper_id="",
        namespace=namespace,
        identifier=identifier,
        title=str(rec.raw_metadata.get("title", "") or candidate.get("resource_name", "")),
        verdict=VERIFIED,
        verification_level="METADATA_VERIFIED",
        evidence_type=evidence_type,
        source_uri=rec.source_uri,
        raw_metadata_checksum=base_record.get("raw_metadata_checksum", ""),
    ).to_dict()
    base_record["evidence_type"] = evidence_type
    return VerificationResult(VERIFIED, CODE_VERIFIED, "paper verified with a unique identifier", profile=profile, record=base_record)


def _verify_annotation(candidate: Mapping[str, Any], rec: RegistryRecord, base_record: dict[str, Any]) -> VerificationResult:
    namespace, identifier = base_record["namespace"], base_record["identifier"]
    evidence_tier = rec.evidence_tier if rec.evidence_tier in ANNOTATION_EVIDENCE_TIERS else "database_annotation"
    reproduction_limited = not rec.version.strip()  # missing version limits reproduction (T-09-09)
    verdict = VERIFIED if rec.version.strip() and rec.entity_scope else INCOMPLETE
    profile = AnnotationSourceProfile(
        annotation_source_id="",
        namespace=namespace,
        identifier=identifier,
        name=str(rec.raw_metadata.get("name", "") or candidate.get("resource_name", "")),
        verdict=verdict,
        verification_level="METADATA_VERIFIED",
        version=rec.version,
        updated=rec.updated,
        entity_scope=list(rec.entity_scope),
        evidence_tier=evidence_tier,
        reproduction_limited=reproduction_limited,
        source_uri=rec.source_uri,
    ).to_dict()
    base_record["evidence_tier"] = evidence_tier
    base_record["reproduction_limited"] = reproduction_limited
    if verdict == INCOMPLETE:
        return VerificationResult(INCOMPLETE, CODE_INCOMPLETE, "annotation source is missing version and/or entity scope", profile=profile, record=base_record)
    return VerificationResult(VERIFIED, CODE_VERIFIED, "annotation source verified", profile=profile, record=base_record)


# =============================================================================
# T-09-06: paper <-> dataset relation verification
# =============================================================================
RELATION_VERIFIED = "verified"
RELATION_UNSUPPORTED = "unsupported"
RELATION_STATUSES = (RELATION_VERIFIED, RELATION_UNSUPPORTED)


def verify_paper_dataset_relation(paper_record: RegistryRecord, dataset_ns_id: tuple[str, str], *, title_similarity: float = 0.0) -> dict[str, Any]:
    """Verify a paper↔dataset relation; title similarity alone is never enough.

    A relation is ``verified`` only when the paper's recorded metadata *explicitly*
    declares the dataset accession (a real cross-reference).  A high title
    similarity with no declared reference stays ``unsupported`` (T-09-06).
    """
    ns, ident = str(dataset_ns_id[0]).strip().upper(), str(dataset_ns_id[1]).strip().upper()
    declared = any(
        str(r.get("namespace", "")).strip().upper() == ns and str(r.get("identifier", "")).strip().upper() == ident for r in paper_record.declared_relations
    )
    if declared:
        return {
            "status": RELATION_VERIFIED,
            "reason": "paper explicitly declares the dataset accession",
            "declared": True,
            "title_similarity": round(float(title_similarity), 4),
        }
    return {
        "status": RELATION_UNSUPPORTED,
        "reason": "no explicit declared cross-reference; title similarity alone cannot establish a relation",
        "declared": False,
        "title_similarity": round(float(title_similarity), 4),
    }


# =============================================================================
# T-09-11: human correction as a new version (never overwrites a tool fact)
# =============================================================================
def apply_human_correction(
    profile: Mapping[str, Any],
    *,
    field_name: str,
    corrected_value: Any,
    evidence: str,
    actor: str,
) -> dict[str, Any]:
    """Return a *new-version* profile applying a human correction, fail-closed.

    The original tool value, the evidence, the actor and the new version are all
    recorded in a ``corrections`` log; the original tool fact is preserved and
    never overwritten in place (T-09-11).  Raises ``ValueError`` for a missing
    evidence / actor — a correction must be accountable.
    """
    if not str(evidence or "").strip():
        raise ValueError("a human correction requires recorded evidence")
    if not str(actor or "").strip():
        raise ValueError("a human correction requires a recorded actor")
    updated = copy.deepcopy(dict(profile))
    original_value = profile.get(field_name)
    corrections = list(updated.get("corrections", []))
    corrections.append(
        {
            "field": field_name,
            "original_tool_value": copy.deepcopy(original_value),
            "corrected_value": copy.deepcopy(corrected_value),
            "evidence": str(evidence),
            "actor": str(actor),
            "version": int(updated.get("profile_version", 1)) + 1,
        }
    )
    updated[field_name] = copy.deepcopy(corrected_value)
    updated["corrections"] = corrections
    updated["profile_version"] = int(updated.get("profile_version", 1)) + 1
    return updated


__all__ = [
    "ACCESS_RESTRICTED",
    "ANNOTATION_EVIDENCE_TIERS",
    "AnnotationSourceProfile",
    "EVIDENCE_TYPES",
    "EXISTENCE_STATUSES",
    "INCOMPLETE",
    "LICENSE_CLARITIES",
    "PaperProfile",
    "REJECTED",
    "RegistryRecord",
    "VERIFICATION_VERDICTS",
    "VERIFIED",
    "VerificationRegistry",
    "VerificationResult",
    "apply_human_correction",
    "classify_license",
    "dataset_completeness",
    "parse_dataset_metadata",
    "verify_candidate",
    "verify_paper_dataset_relation",
]
