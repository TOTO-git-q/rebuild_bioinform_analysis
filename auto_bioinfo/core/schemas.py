from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .ids import hash_payload, make_stable_id

CANONICAL_SCHEMA_VERSION = "v5.canonical/0.1"

# Automation/approval levels (requirement spec stage 8): how much the system may
# do without a human in the loop.  Distinct from the per-run execution_mode
# vocabulary (DEMO/TEST/REAL) owned by :mod:`auto_bioinfo.core.provenance`.
AUTOMATION_LEVELS = ("A0", "A1", "A2", "A3")

# Append-only lifecycle of an ApprovalRequest, and the two terminal decisions.
APPROVAL_STATES = ("requested", "granted", "rejected", "expired", "cancelled")
APPROVAL_DECISIONS = ("approved", "rejected")

CLAIM_LEVELS = [
    "descriptive",
    "association",
    "co_expression",
    "candidate_biomarker",
    "mechanistic_hypothesis",
    "causal_support",
    "experimentally_validated_target",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_provenance() -> list[dict[str, str]]:
    return [{"source_type": "system", "source_id": "targetcompass_v5", "note": "canonical control-plane object"}]


@dataclass
class ResearchSpec:
    """Formal understanding of the user question.

    Unknown fields are intentionally left empty and surfaced through
    ``open_questions``; the planner is forbidden from inventing business
    defaults (disease/tissue/organism) the user never stated.
    """

    research_question: str
    project_id: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    research_spec_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    max_claim_level: str = "association"
    # Enriched, requirement-spec aligned fields (all optional, never guessed).
    organism: str = ""
    condition_or_phenotype: str = ""
    tissue: str = ""
    comparison_groups: list[str] = field(default_factory=list)
    primary_endpoints: list[str] = field(default_factory=list)
    target_outputs: list[str] = field(default_factory=list)
    inclusion_criteria: list[str] = field(default_factory=list)
    exclusion_criteria: list[str] = field(default_factory=list)
    claim_ceiling: str = "association"
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    user_constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["research_spec_id"]:
            data["research_spec_id"] = make_stable_id("research_spec", {"project_id": self.project_id, "research_question": self.research_question})
        return data


@dataclass
class SubQuestion:
    research_spec_id: str
    question: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    subquestion_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["subquestion_id"]:
            data["subquestion_id"] = make_stable_id("subquestion", {"research_spec_id": self.research_spec_id, "question": self.question})
        return data


@dataclass
class ScopeBundle:
    research_spec_id: str
    species: list[str]
    tissues: list[str]
    conditions: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    scope_bundle_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class EvidencePlan:
    research_spec_id: str
    evidence_axes: list[str]
    max_claim_level: str = "association"
    schema_version: str = CANONICAL_SCHEMA_VERSION
    evidence_plan_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class ResourceCandidate:
    resource_name: str
    resource_type: str
    verified: bool
    source_status: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    resource_candidate_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "candidate"
    accession: str = ""
    # R0-01 truthful-execution provenance (four orthogonal facts). ``verified``
    # is retained only as a derived convenience and must not be trusted alone.
    source_class: str = "LEGACY_UNKNOWN"
    retrieval_mode: str = "LOCAL_CACHE"
    verification_level: str = "UNVERIFIED"
    legacy_verified_assertion: bool = False


@dataclass
class DatasetProfile:
    dataset_id: str
    modality: str
    organism: str
    tissue: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    dataset_profile_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "profiled"
    source_class: str = "LEGACY_UNKNOWN"
    retrieval_mode: str = "LOCAL_CACHE"
    verification_level: str = "UNVERIFIED"
    legacy_verified_assertion: bool = False


@dataclass
class DatasetSelectionDecision:
    dataset_id: str
    decision: str
    reason: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    decision_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class MethodContractRef:
    method_contract_id: str
    method_name: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    method_ref_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "active"


@dataclass
class CompatibilityDecision:
    dataset_id: str
    method_contract_id: str
    compatible: bool
    reason: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    compatibility_decision_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class WorkflowPlan:
    workflow_name: str
    task_ids: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    workflow_plan_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class AnalysisTaskPacket:
    task_id: str
    subquestion_id: str
    expected_inputs: list[str]
    expected_outputs: list[str]
    qc_requirements: list[str]
    failure_conditions: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class EngineeringTaskPacket:
    task_id: str
    allowed_paths: list[str]
    forbidden_paths: list[str]
    expected_patch_summary: str
    test_commands: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class ReviewTaskPacket:
    task_id: str
    audit_scope: list[str]
    claim_ceiling: str
    required_checks: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class TaskRun:
    task_run_id: str
    task_id: str
    result_status: str
    artifact_refs: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"


@dataclass
class ArtifactManifest:
    artifact_id: str
    project_id: str
    path: str
    exists: bool
    checksum_sha256: str
    is_placeholder: bool
    qc_status: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "registered"


@dataclass
class QCReport:
    qc_report_id: str
    overall_status: str
    checks: list[dict[str, Any]]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"


@dataclass
class EvidenceItemRef:
    evidence_item_id: str
    artifact_id: str
    review_status: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "referenced"


@dataclass
class EvidenceItem:
    """A QC-passed observation turned into structured scientific evidence.

    Carries the fields the alignment auditor consumes (``evidence_item_id``,
    ``artifact_id``, ``review_status``) plus the requirement-spec payload that
    binds the observation to its lineage and a hard ``allowed_claim_level``.
    """

    evidence_item_id: str
    artifact_id: str
    review_status: str
    subquestion_ids: list[str]
    source_dataset_ids: list[str]
    source_task_run_ids: list[str]
    observation: str
    effect_summary: dict[str, Any]
    uncertainty: dict[str, Any]
    evidence_type: str
    scope: dict[str, Any]
    qc_status: str
    allowed_claim_level: str
    supports_or_opposes: str = "supports"
    replication_status: str = "single_dataset"
    limitations: list[str] = field(default_factory=list)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "audited"
    # R0-01: truthful-execution markers. ``scientific_output_eligible`` is a
    # cached copy of the referenced decision; the admission gate recomputes it.
    mode: str = "DEMO"
    release_status: str = "DEMONSTRATION_ONLY"
    source_class: str = "LEGACY_UNKNOWN"
    scientific_eligibility_decision_id: str = ""
    scientific_output_eligible: bool = False


@dataclass
class DatasetManifest:
    """Locked, version-stamped record of the datasets/samples used for analysis.

    Once locked, any change must produce a *new* manifest version with a reason;
    the manifest is never edited in place (see ADR-0003).
    """

    dataset_manifest_id: str
    dataset_id: str
    accession: str
    source_status: str
    samples: list[dict[str, Any]]
    excluded_samples: list[dict[str, Any]]
    file_checksums: dict[str, str]
    supports_subquestion_ids: list[str]
    known_limitations: list[str]
    manifest_version: int = 1
    locked: bool = True
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "locked"


@dataclass
class Claim:
    claim_id: str
    text: str
    claim_level: str
    evidence_item_refs: list[str]
    supports_subquestion_ids: list[str]
    scope: dict[str, Any]
    limitations: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    # R0-01: a Demo claim is allowed (keeps E2E value) but is never eligible and
    # never enters the formal scientific pool / export channel.
    mode: str = "DEMO"
    release_status: str = "DEMONSTRATION_ONLY"
    scientific_eligibility_decision_id: str = ""
    scientific_output_eligible: bool = False


@dataclass
class QuestionAlignmentReport:
    report_id: str
    final_decision: str
    unsupported_claims: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    generated_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"


@dataclass
class FinalReportManifest:
    final_report_id: str
    report_path: str
    claim_ids: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    generated_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"


@dataclass
class ProjectEvent:
    event_id: str
    project_id: str
    event_type: str
    actor: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"


@dataclass
class ProjectState:
    project_id: str
    current_stage: str
    allowed_next_stages: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    project_state_id: str = ""
    updated_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "active"
    # Projection of the immutable ProjectPolicy; the policy remains authoritative.
    execution_mode: str = "DEMO"
    project_policy_ref: str = ""


# --- WP-02a / T-02-02: Project & Policy and Approval contracts ---------------


@dataclass
class Project:
    """The mutable project projection (history is rebuilt from ProjectEvent).

    One project fans out to many OriginalRequests, ProjectEvents and Approvals;
    it references its active ProjectPolicy rather than embedding it, so the
    policy stays independently versioned and content-hashable.
    """

    project_id: str
    title: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    current_stage: str = "INTAKE"
    request_ids: list[str] = field(default_factory=list)
    approval_ids: list[str] = field(default_factory=list)
    active_policy_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OriginalRequest:
    """The user's request, stored *verbatim* and never overwritten.

    ``original_text`` is immutable once recorded; ``original_text_sha256`` binds
    it so any later edit is detectable.  Normalisation (Question Normalizer)
    writes only ``normalized_text`` — a separate field — and must never touch the
    original.  Use :meth:`with_normalized_text` to attach a normalised form while
    provably preserving the original byte content and hash.
    """

    project_id: str
    original_text: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    request_id: str = ""
    submitter: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    user_constraints: list[str] = field(default_factory=list)
    normalized_text: str = ""
    original_text_sha256: str = ""
    submitted_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"

    def text_hash(self) -> str:
        return hash_payload(self.original_text)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # The hash always tracks the *original* text, never the normalised form.
        data["original_text_sha256"] = self.text_hash()
        if not data["request_id"]:
            data["request_id"] = make_stable_id("original_request", {"project_id": self.project_id, "original_text": self.original_text})
        return data

    def with_normalized_text(self, normalized: str) -> dict[str, Any]:
        """Return the dict projection with ``normalized_text`` set, leaving the
        original text and its hash untouched."""
        data = self.to_dict()
        data["normalized_text"] = normalized
        return data


@dataclass
class ProjectPolicy:
    """Versioned, content-hashable governance policy for a project.

    Completes the minimal runtime ProjectPolicy projection in
    :mod:`auto_bioinfo.core.provenance` (which carries only execution_mode for
    the R0-01 truthful-execution gate) by adding the requirement-spec governance
    fields: automation level (A0–A3), network, data-sensitivity and export
    policy.  ``execution_mode`` keeps the same DEMO/TEST/REAL vocabulary so the
    two stay interoperable.  ``content_hash`` and ``project_policy_id`` are
    derived deterministically so a policy is stable-ID friendly and tamper-
    evident.
    """

    project_id: str
    execution_mode: str
    automation_level: str = "A0"
    policy_version: int = 1
    network_policy: dict[str, Any] = field(default_factory=dict)
    data_sensitivity: str = "unspecified"
    export_policy: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    status: str = "active"

    def _content_body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "execution_mode": self.execution_mode,
            "automation_level": self.automation_level,
            "policy_version": self.policy_version,
            "network_policy": self.network_policy,
            "data_sensitivity": self.data_sensitivity,
            "export_policy": self.export_policy,
            "status": self.status,
        }

    def content_hash(self) -> str:
        return hash_payload(self._content_body())

    def policy_id(self) -> str:
        return make_stable_id(
            "project_policy",
            {
                "project_id": self.project_id,
                "execution_mode": self.execution_mode,
                "automation_level": self.automation_level,
                "policy_version": self.policy_version,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        body = self._content_body()
        return {
            **body,
            "project_policy_id": self.policy_id(),
            "content_hash": self.content_hash(),
        }


@dataclass
class ApprovalRequest:
    """An append-only request for a human decision, bound to the exact version
    of the object it concerns.  ``subject_version`` is mandatory: an approval
    that does not name the version it asks about cannot be honoured later.
    """

    project_id: str
    subject_type: str
    subject_id: str
    subject_version: int
    gate: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    approval_request_id: str = ""
    requested_by: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    state: str = "requested"
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["approval_request_id"]:
            data["approval_request_id"] = make_stable_id(
                "approval_request",
                {
                    "project_id": self.project_id,
                    "subject_type": self.subject_type,
                    "subject_id": self.subject_id,
                    "subject_version": self.subject_version,
                    "gate": self.gate,
                },
            )
        return data


@dataclass
class ApprovalDecision:
    """An immutable approve/reject decision bound to the *exact* target object
    and version it ruled on.  A decision is never edited in place; a changed
    mind is a new decision.  It also records the ApprovalRequest it answers.
    """

    approval_request_id: str
    project_id: str
    subject_type: str
    subject_id: str
    subject_version: int
    decision: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    approval_decision_id: str = ""
    decided_by: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    decided_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["approval_decision_id"]:
            data["approval_decision_id"] = make_stable_id(
                "approval_decision",
                {
                    "approval_request_id": self.approval_request_id,
                    "subject_type": self.subject_type,
                    "subject_id": self.subject_id,
                    "subject_version": self.subject_version,
                    "decision": self.decision,
                },
            )
        return data
