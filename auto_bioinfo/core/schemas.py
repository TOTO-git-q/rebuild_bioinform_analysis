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

# --- WP-02b / T-02-03..04: research & planning vocabularies ------------------

# Lifecycle of a recorded ambiguity: an unresolved unknown, an explicitly stated
# working assumption (with a recorded default), or a closed/answered item.
AMBIGUITY_STATES = ("open", "assumed", "resolved")

# Status of an ontology mapping.  ``unresolved`` keeps an unmapped term visible
# instead of inventing an identifier; ``ambiguous`` means competing candidates.
ONTOLOGY_MAPPING_STATES = ("mapped", "ambiguous", "unresolved")
# A mapping below this confidence may not be recorded as a resolved fact; it must
# be surfaced as ``ambiguous``/``unresolved`` instead of treated as certain.
ONTOLOGY_CONFIDENCE_FLOOR = 0.5

# Kinds of evidence shortfall and the append-only states a gap moves through.
EVIDENCE_GAP_TYPES = ("missing", "insufficient", "unverifiable")
EVIDENCE_GAP_STATES = ("open", "mitigated", "accepted")

# --- WP-02c / T-02-05..06: resource & dataset feasibility vocabularies --------

# Bounded per-(dataset, sub-question) feasibility verdict: can this dataset
# actually answer the question?  ``usable`` and ``conditionally_usable`` assert
# the dataset can (at least under stated conditions) be used; ``not_usable`` and
# ``insufficient`` must keep their reasons and missing facts instead of pretending
# success (validated by
# :func:`auto_bioinfo.core.validation.validate_dataset_feasibility_report`).
FEASIBILITY_DECISIONS = ("usable", "conditionally_usable", "not_usable", "insufficient")
# The two verdicts that claim a dataset is (at least conditionally) usable.
FEASIBILITY_ACCEPTED_DECISIONS = ("usable", "conditionally_usable")

# --- WP-02d / T-02-07..08: method & compatibility contract vocabularies -------

# Bounded compatibility verdict between a method and a dataset for a sub-question.
# ``compatible`` and ``conditionally_compatible`` assert the method can (at least
# under stated conditions) run on the dataset to answer the sub-question;
# ``incompatible`` and ``insufficient_information`` must keep their reasons and
# blocking facts/gaps instead of an ambiguous bare boolean (validated by
# :func:`auto_bioinfo.core.validation.validate_compatibility_decision`).
COMPATIBILITY_DECISIONS = ("compatible", "conditionally_compatible", "incompatible", "insufficient_information")
# The two verdicts that assert the method is (at least conditionally) usable.
COMPATIBILITY_ACCEPTED_DECISIONS = ("compatible", "conditionally_compatible")

# --- WP-02f / T-02-11: TaskRun run-record vocabularies (REQ-OBJ-12) -----------

# Bounded result status for a recorded run instance.  ``completed`` / ``failed``
# are terminal records that must be auditable on their own; ``pending`` /
# ``running`` / ``skipped`` are incomplete records that may be partial only when
# they carry an explicit reason (validated by
# :func:`auto_bioinfo.core.validation.validate_task_run`).
TASK_RUN_RESULT_STATUSES = ("pending", "running", "completed", "failed", "skipped")
# Terminal records: a run that has finished one way or the other.
TASK_RUN_TERMINAL_STATUSES = ("completed", "failed")
# Incomplete records: the run has not produced a terminal exit.
TASK_RUN_INCOMPLETE_STATUSES = ("pending", "running", "skipped")

# --- WP-02g / T-02-12..14: Artifact / QC / Evidence contract vocabularies -----

# Bounded artifact QC status (REQ-OBJ-13): an artifact's recorded QC verdict.
# ``pending`` is a pre-QC fact; ``pass`` / ``pass_with_warnings`` are QC-passed;
# ``fail`` blocks the artifact from supporting evidence (validated by
# :func:`auto_bioinfo.core.validation.validate_artifact_manifest`).
ARTIFACT_QC_STATUSES = ("pending", "pass", "pass_with_warnings", "fail")
# The two QC verdicts that let an artifact support evidence.
ARTIFACT_QC_PASSED_STATUSES = ("pass", "pass_with_warnings")

# Four-layer QC vocabulary (REQ-OBJ-14): the QC layers, the bounded per-check
# status, and the bounded overall-report status.  Kept in sync with the
# deterministic engine in :mod:`auto_bioinfo.quality.qc_engine` (which this WO
# does not change); the validator only checks the *shape* of a recorded report.
QC_CHECK_LAYERS = ("execution", "data", "statistical", "biological")
QC_CHECK_STATUSES = ("pass", "warn", "fail")
QC_OVERALL_STATUSES = ("pass", "pass_with_warnings", "fail")
# The overall verdicts that count as QC-passed for downstream evidence.
QC_PASSED_OVERALL_STATUSES = ("pass", "pass_with_warnings")

# Evidence direction and replication vocabularies (REQ-OBJ-15).  ``supports`` /
# ``opposes`` / ``neutral`` is the explicit support direction; the replication
# vocabulary keeps single- vs multi-dataset replication honest.
EVIDENCE_DIRECTIONS = ("supports", "opposes", "neutral")
EVIDENCE_REPLICATION_STATUSES = ("single_dataset", "multi_dataset", "replicated", "not_replicated")
# Replication statuses that *assert* independent replication; a single-dataset
# evidence record may not claim one of these by default.
EVIDENCE_REPLICATED_STATUSES = ("multi_dataset", "replicated")

# --- WP-02h / T-02-15..17: Claim / Alignment / Reproduction vocabularies -------

# Bounded final decision of a QuestionAlignmentReport (REQ-OBJ-17).  ``approve``
# is the only *passing* decision; ``needs_review`` and ``reject`` keep an
# unresolved or failed alignment honest (validated by
# :func:`auto_bioinfo.core.validation.validate_question_alignment_report`).  Kept
# in sync with the deterministic auditor in
# :mod:`auto_bioinfo.core.alignment_auditor` (which this WO does not change).
ALIGNMENT_DECISIONS = ("approve", "needs_review", "reject")
# The single decision that asserts the claims stay aligned to the question; it may
# never stand while a blocker, unsupported claim, overclaim, scope drift, or
# traceability gap is recorded.
ALIGNMENT_PASSING_DECISIONS = ("approve",)

# Reproducibility vocabularies (REQ-OBJ-18).  ``reproducibility_level`` is the
# *strength* of the reproduction (how closely outputs must match); the bounded
# ``reproduction_status`` is the recorded verdict.  ``reproduced`` /
# ``partially_reproduced`` assert (at least partial) reproduction; ``pending`` /
# ``not_reproduced`` / ``failed`` keep an unproven or failed reproduction honest.
# The manifest only *records* these facts; it never runs or materialises a bundle.
REPRODUCIBILITY_LEVELS = ("bitwise", "numerical", "statistical", "qualitative", "unspecified")
REPRODUCTION_STATUSES = ("pending", "reproduced", "partially_reproduced", "not_reproduced", "failed")
# The statuses that assert (at least partial) reproduction.
REPRODUCTION_REPRODUCED_STATUSES = ("reproduced", "partially_reproduced")


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
    # Link to the AmbiguityReport that records *why* fields were left empty; the
    # spec never guesses, it points at the recorded unknowns.
    ambiguity_report_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["research_spec_id"]:
            data["research_spec_id"] = make_stable_id("research_spec", {"project_id": self.project_id, "research_question": self.research_question})
        return data


@dataclass
class SubQuestion:
    """A single-purpose research sub-question bound to its parent ResearchSpec.

    Each sub-question must express exactly one relationship (the single-purpose
    rule, T-02-04); compound questions are split before they are recorded.  The
    optional ``purpose``/``evidence_type``/``claim_ceiling`` fields make the one
    purpose, its evidence axis, and its hard claim ceiling explicit, and
    ``parent_subquestion_id`` records a parent/child relationship without
    inventing one.
    """

    research_spec_id: str
    question: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    subquestion_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    purpose: str = ""
    evidence_type: str = ""
    parent_subquestion_id: str = ""
    claim_ceiling: str = "association"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["subquestion_id"]:
            data["subquestion_id"] = make_stable_id("subquestion", {"research_spec_id": self.research_spec_id, "question": self.question})
        return data


@dataclass
class ScopeBundle:
    """The resolved analysis scope: species/tissue/condition/comparison axes.

    ``comparisons`` carries the critical contrast(s) the question asks about; an
    empty or self-contradictory critical scope is rejected by
    :func:`auto_bioinfo.core.validation.validate_scope_bundle` rather than being
    silently completed.
    """

    research_spec_id: str
    species: list[str]
    tissues: list[str]
    conditions: list[str]
    comparisons: list[str] = field(default_factory=list)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    scope_bundle_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["scope_bundle_id"]:
            data["scope_bundle_id"] = make_stable_id("scope_bundle", {"research_spec_id": self.research_spec_id})
        return data


@dataclass
class EvidencePlan:
    """How a sub-question's evidence will be gathered, with the claim ceiling and
    any *planned* evidence gaps made explicit.

    ``evidence_axes`` and ``max_claim_level`` are mandatory; ``planned_gaps`` and
    ``stop_conditions`` keep known shortfalls and stop reasons visible instead of
    quietly proceeding (validated by
    :func:`auto_bioinfo.core.validation.validate_evidence_plan`).
    """

    research_spec_id: str
    evidence_axes: list[str]
    max_claim_level: str = "association"
    schema_version: str = CANONICAL_SCHEMA_VERSION
    evidence_plan_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    subquestion_ids: list[str] = field(default_factory=list)
    planned_gaps: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    minimum_replication: dict[str, Any] = field(default_factory=dict)
    negative_evidence_strategy: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["evidence_plan_id"]:
            data["evidence_plan_id"] = make_stable_id("evidence_plan", {"research_spec_id": self.research_spec_id})
        return data


# --- WP-02b / T-02-03: AmbiguityReport, OntologyMapping ----------------------


@dataclass
class AmbiguityReport:
    """The unresolved unknowns behind a ResearchSpec, kept explicit.

    Each entry in ``items`` records an ambiguity as a small dict with at least a
    ``subject`` (what is unclear), an ``impact`` (why it matters) and a
    ``status`` (:data:`AMBIGUITY_STATES`).  An ``assumed`` item must also carry a
    ``default_value`` — the system may proceed on a stated default but may never
    silently guess (validated by
    :func:`auto_bioinfo.core.validation.validate_ambiguity_report`).  Assumptions
    are kept separate from confirmed facts and never written back as known facts.
    """

    research_spec_id: str
    items: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    ambiguity_report_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"

    def open_items(self) -> list[dict[str, Any]]:
        return [it for it in self.items if str(it.get("status")) == "open"]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["ambiguity_report_id"]:
            data["ambiguity_report_id"] = make_stable_id("ambiguity_report", {"research_spec_id": self.research_spec_id})
        return data


@dataclass
class OntologyMapping:
    """An immutable record of mapping one source term to a standard identifier.

    Captures the original term, the resolved standard id (empty while
    unresolved), the mapping source/ontology, a confidence score, the status
    (:data:`ONTOLOGY_MAPPING_STATES`) and the ranked ``candidates`` considered.
    A low-confidence match may not be recorded as ``mapped`` — that would treat a
    single uncertain score as a fact (validated by
    :func:`auto_bioinfo.core.validation.validate_ontology_mapping`).
    """

    research_spec_id: str
    source_term: str
    mapping_source: str
    status: str = "unresolved"
    mapped_id: str = ""
    confidence: float = 0.0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    ontology_mapping_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["ontology_mapping_id"]:
            data["ontology_mapping_id"] = make_stable_id(
                "ontology_mapping",
                {"research_spec_id": self.research_spec_id, "source_term": self.source_term, "mapping_source": self.mapping_source},
            )
        return data


# --- WP-02b / T-02-04: DependencyGraph, EvidenceGap --------------------------


@dataclass
class DependencyGraph:
    """A directed dependency graph over sub-questions that must stay acyclic.

    ``edges`` are ``(from_id, to_id)`` pairs meaning "from depends on to".  The
    graph offers deterministic serialisation (nodes and edges sorted, so two
    graphs with the same content serialise identically) and cycle detection;
    :func:`auto_bioinfo.core.validation.validate_dependency_graph` rejects
    dangling endpoints, self-loops and cycles.
    """

    research_spec_id: str
    nodes: list[str] = field(default_factory=list)
    edges: list[list[str]] = field(default_factory=list)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    dependency_graph_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"

    def _adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {n: [] for n in self.nodes}
        for edge in self.edges:
            if len(edge) == 2 and edge[0] in adj:
                adj[edge[0]].append(edge[1])
        return adj

    def has_cycle(self) -> bool:
        adj = self._adjacency()
        # DFS three-colour cycle detection (WHITE=0, GREY=1, BLACK=2).
        colour: dict[str, int] = {n: 0 for n in self.nodes}

        def visit(node: str) -> bool:
            colour[node] = 1
            for nxt in adj.get(node, []):
                if nxt not in colour:
                    continue
                if colour[nxt] == 1:
                    return True
                if colour[nxt] == 0 and visit(nxt):
                    return True
            colour[node] = 2
            return False

        return any(colour[n] == 0 and visit(n) for n in sorted(self.nodes))

    def topological_order(self) -> list[str]:
        """Deterministic execution order: prerequisites first.

        An edge ``(u, v)`` means "u depends on v", so v is a prerequisite of u and
        must appear before it.  Raises if the graph has a cycle.
        """
        if self.has_cycle():
            raise ValueError("dependency graph has a cycle; no topological order exists")
        # Reverse the dependency edges: prerequisite -> dependent, and count each
        # node's unmet prerequisites so a node with none is ready first.
        dependents: dict[str, list[str]] = {n: [] for n in self.nodes}
        indeg: dict[str, int] = {n: 0 for n in self.nodes}
        for edge in self.edges:
            if len(edge) == 2 and edge[0] in indeg and edge[1] in dependents:
                dependents[edge[1]].append(edge[0])
                indeg[edge[0]] += 1
        ready = sorted(n for n in self.nodes if indeg[n] == 0)
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for nxt in sorted(dependents.get(node, [])):
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    ready.append(nxt)
            ready.sort()
        return order

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection (sorted nodes and edges)."""
        return {
            "research_spec_id": self.research_spec_id,
            "nodes": sorted(self.nodes),
            "edges": sorted([list(e) for e in self.edges]),
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["nodes"] = sorted(self.nodes)
        data["edges"] = sorted([list(e) for e in self.edges])
        if not data["dependency_graph_id"]:
            data["dependency_graph_id"] = make_stable_id("dependency_graph", self.canonical())
        return data


@dataclass
class EvidenceGap:
    """A recorded shortfall of evidence that *lowers* — never raises — a claim.

    A gap names the missing/insufficient/unverifiable evidence
    (:data:`EVIDENCE_GAP_TYPES`), the sub-question it affects and a follow-up
    action.  ``imposed_claim_ceiling`` is the hard ceiling that applies while the
    gap is open; :meth:`caps_claim_level` and
    :func:`auto_bioinfo.core.validation.validate_evidence_gap` guarantee a gap can
    only cap a claim, never license a higher one.
    """

    research_spec_id: str
    subquestion_id: str
    description: str
    gap_type: str
    follow_up: str = ""
    status: str = "open"
    imposed_claim_ceiling: str = "descriptive"
    schema_version: str = CANONICAL_SCHEMA_VERSION
    evidence_gap_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)

    def caps_claim_level(self, desired_level: str) -> str:
        """Return the allowed claim level: the lower of ``desired_level`` and the
        gap's imposed ceiling.  A gap can only pull a claim down, never up."""
        if desired_level not in CLAIM_LEVELS or self.imposed_claim_ceiling not in CLAIM_LEVELS:
            return self.imposed_claim_ceiling
        return min(desired_level, self.imposed_claim_ceiling, key=CLAIM_LEVELS.index)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["evidence_gap_id"]:
            data["evidence_gap_id"] = make_stable_id(
                "evidence_gap",
                {"research_spec_id": self.research_spec_id, "subquestion_id": self.subquestion_id, "description": self.description},
            )
        return data


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
    """Tool-verifiable factual profile of a candidate dataset (REQ-OBJ-05).

    The four R0-01 provenance markers (``source_class`` / ``retrieval_mode`` /
    ``verification_level`` / ``legacy_verified_assertion``) keep *how* the facts
    were obtained truthful; the WP-02c factual fields below
    (samples/platform/species/grouping/files/license/metadata) carry the actual
    dataset facts.  Every factual field is optional and defaults to an unknown
    value, so an explicitly unverified profile is valid but stays
    non-authoritative; :func:`auto_bioinfo.core.validation.validate_dataset_profile`
    only rejects *blank* or *internally contradictory* facts (e.g. a sample_count
    that disagrees with the recorded samples, or a group referencing an unknown
    sample), and never treats ``legacy_verified_assertion`` as authorisation on
    its own.
    """

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
    # --- WP-02c / T-02-05: tool-verifiable factual metadata (REQ-OBJ-05) ---
    accession: str = ""
    platform: str = ""
    species: list[str] = field(default_factory=list)
    sample_count: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)
    grouping: dict[str, Any] = field(default_factory=dict)
    files: list[dict[str, Any]] = field(default_factory=list)
    license: str = ""
    metadata_facts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["dataset_profile_id"]:
            data["dataset_profile_id"] = make_stable_id("dataset_profile", {"dataset_id": self.dataset_id})
        return data


@dataclass
class DatasetFeasibilityReport:
    """Whether a dataset can answer a sub-question / evidence plan (REQ-OBJ-06).

    Binds a feasibility verdict to the exact ``dataset_profile_id`` /
    ``research_spec_id`` / ``subquestion_id`` (and, for an accepted verdict, the
    ``evidence_plan_id`` it satisfies).  ``decision`` is one of
    :data:`FEASIBILITY_DECISIONS`; ``reasons`` and ``required_facts_checked`` keep
    the verdict's basis explicit, while ``missing_facts`` / ``blocking_gaps`` keep
    a negative verdict honest.  ``imposed_claim_ceiling`` records the conservative
    claim/evidence bound that applies when feasibility is conditional or
    insufficient.

    The report only *observes* feasibility: it never locks a dataset, authorises
    REAL execution, authorises formal scientific evidence, or bypasses later
    gates.  The ``locks_dataset`` / ``authorizes_real_execution`` /
    ``authorizes_formal_evidence`` flags are pinned ``False`` and the validator
    rejects any attempt to flip them — a boolean here is never authority.
    """

    research_spec_id: str
    subquestion_id: str
    dataset_profile_id: str
    decision: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    feasibility_report_id: str = ""
    evidence_plan_id: str = ""
    reasons: list[str] = field(default_factory=list)
    required_facts_checked: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    blocking_gaps: list[str] = field(default_factory=list)
    conditional_use_notes: list[str] = field(default_factory=list)
    imposed_claim_ceiling: str = "descriptive"
    # The report confers no authority of its own; these stay False.
    locks_dataset: bool = False
    authorizes_real_execution: bool = False
    authorizes_formal_evidence: bool = False
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["feasibility_report_id"]:
            data["feasibility_report_id"] = make_stable_id(
                "dataset_feasibility_report",
                {
                    "research_spec_id": self.research_spec_id,
                    "subquestion_id": self.subquestion_id,
                    "dataset_profile_id": self.dataset_profile_id,
                },
            )
        return data


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


# --- WP-02d / T-02-07: MethodContract standalone object (REQ-OBJ-08) ----------


@dataclass
class MethodContract:
    """The scientific boundary of an analysis method, made a standalone object.

    Promotes the ad hoc method-contract dict (today living inside
    ``auto_bioinfo.methods.bulk_deg``) to a structured, content-hashable contract
    *without* changing method execution, selection policy or the runtime registry.
    A lightweight :class:`MethodContractRef` can still point at this object by its
    ``method_contract_id``.

    The contract states stable method identity (``method_id`` / ``method_name`` /
    ``version``) and the applicability facts that bound what the method may do:
    the modalities it supports, the inputs / metadata / design facts it requires,
    the outputs it produces, its statistical assumptions, its hard claim
    capability and claim ceiling, the conditions under which it is applicable or
    forbidden, and its QC requirements.  The contract only *describes* a method's
    boundary; it never selects, executes, or authorises a method
    (validated by :func:`auto_bioinfo.core.validation.validate_method_contract`).
    """

    method_id: str
    method_name: str
    version: str
    scientific_purpose: str = ""
    schema_version: str = CANONICAL_SCHEMA_VERSION
    method_contract_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "active"
    # Applicability facts (REQ-OBJ-08): supported modality, required inputs /
    # metadata / design facts, outputs, statistical assumptions, QC requirements.
    supported_modalities: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    required_metadata: list[str] = field(default_factory=list)
    minimum_design_facts: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    statistical_assumptions: list[str] = field(default_factory=list)
    required_qc: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    # The scientific boundary: what the method can claim, the hard ceiling it may
    # never cross, and the conditions under which it is applicable vs forbidden.
    claim_capability: str = "descriptive"
    claim_ceiling: str = "association"
    applicable_conditions: list[str] = field(default_factory=list)
    forbidden_conditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["method_contract_id"]:
            data["method_contract_id"] = make_stable_id(
                "method_contract",
                {"method_id": self.method_id, "version": self.version},
            )
        return data


@dataclass
class CompatibilityDecision:
    """Records whether a method may run on a dataset to answer a sub-question.

    The legacy four-field form (``dataset_id`` / ``method_contract_id`` /
    ``compatible`` / ``reason``) still constructs and serialises; ``to_dict``
    derives the bounded :data:`COMPATIBILITY_DECISIONS` ``decision`` from the
    ``compatible`` boolean and mirrors a singular ``reason`` into ``reasons`` so an
    ambiguous bare boolean never stands alone.  The hardened fields bind the
    decision to its method / dataset profile / sub-question / evidence plan and
    keep the checked facts and any blocking facts/gaps explicit.

    A CompatibilityDecision only *observes* compatibility: it never authorises
    execution, locks a dataset, creates evidence, or raises a claim level.  The
    ``authorizes_execution`` / ``locks_dataset`` / ``creates_evidence`` /
    ``raises_claim_level`` flags are pinned ``False`` and the validator rejects any
    attempt to make them truthy — a boolean here is never authority.
    """

    dataset_id: str
    method_contract_id: str
    compatible: bool
    reason: str
    schema_version: str = CANONICAL_SCHEMA_VERSION
    compatibility_decision_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    # --- WP-02d / T-02-08: hardened bindings and bounded verdict (REQ-OBJ-09) ---
    decision: str = ""
    method_id: str = ""
    dataset_profile_id: str = ""
    subquestion_id: str = ""
    evidence_plan_id: str = ""
    reasons: list[str] = field(default_factory=list)
    checked_facts: list[str] = field(default_factory=list)
    blocking_facts: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    imposed_claim_ceiling: str = ""
    # The decision confers no authority of its own; these stay False.
    authorizes_execution: bool = False
    locks_dataset: bool = False
    creates_evidence: bool = False
    raises_claim_level: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["decision"]:
            data["decision"] = "compatible" if self.compatible else "incompatible"
        if not data["reasons"] and str(self.reason or "").strip():
            data["reasons"] = [self.reason]
        if not data["compatibility_decision_id"]:
            data["compatibility_decision_id"] = make_stable_id(
                "compatibility_decision",
                {
                    "method_contract_id": self.method_contract_id,
                    "dataset_id": self.dataset_id,
                    "subquestion_id": self.subquestion_id,
                },
            )
        return data


# --- WP-02e / T-02-09: WorkflowPlan explicit acyclic DAG (REQ-OBJ-10) ---------


@dataclass
class WorkflowPlan:
    """A planned analysis workflow as an explicit, acyclic task DAG (REQ-OBJ-10).

    The legacy ``WorkflowPlan(workflow_name, task_ids, ...)`` construction is
    preserved: ``task_ids`` is still the declared list of tasks.  The DAG is made
    explicit by ``dependencies`` — ``[from_task, to_task]`` edges meaning
    "from_task depends on to_task", so a bare linear ``task_ids`` list no longer
    silently implies a checked graph.  ``expected_inputs`` / ``expected_outputs``
    map a task id to its planned input/output facts and ``gates`` are quality
    gates bound to a task id; all are contract data, never execution behaviour.

    The plan only *describes* a workflow; it never compiles, schedules, or runs a
    task.  Cycle detection and a deterministic id are provided
    (:func:`auto_bioinfo.core.validation.validate_workflow_plan` rejects blank /
    duplicate task ids, dangling dependency endpoints, self-loops, cycles, and
    gates/inputs/outputs that reference undeclared tasks).
    """

    workflow_name: str
    task_ids: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    workflow_plan_id: str = ""
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    # --- WP-02e / T-02-09: explicit DAG contract data (REQ-OBJ-10) ---
    dependencies: list[list[str]] = field(default_factory=list)
    expected_inputs: dict[str, list[str]] = field(default_factory=dict)
    expected_outputs: dict[str, list[str]] = field(default_factory=dict)
    gates: list[dict[str, Any]] = field(default_factory=list)

    def _dependency_graph(self) -> "DependencyGraph":
        """Project the declared tasks/dependencies onto a DependencyGraph so the
        acyclicity machinery is shared with the sub-question graph."""
        return DependencyGraph(
            research_spec_id="workflow_plan",
            nodes=list(self.task_ids),
            edges=[list(edge) for edge in self.dependencies],
        )

    def has_cycle(self) -> bool:
        return self._dependency_graph().has_cycle()

    def topological_order(self) -> list[str]:
        """Deterministic task order (prerequisites first).  Raises on a cycle."""
        return self._dependency_graph().topological_order()

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection (sorted tasks and dependencies).

        ``task_ids`` is canonicalised to sorted order so two equivalent DAGs that
        declare the same tasks and dependencies in a different ``task_ids`` order
        produce the same stable id — the declaration order is harmless and must
        not affect content identity.  The explicit DAG semantics are unchanged:
        the set of tasks and the (sorted) dependency edges fully determine the
        graph, and cycle / dangling / self-loop checks run over the real edges in
        :func:`auto_bioinfo.core.validation.validate_workflow_plan`."""
        return {
            "workflow_name": self.workflow_name,
            "task_ids": sorted(self.task_ids),
            "dependencies": sorted([list(e) for e in self.dependencies]),
            "expected_inputs": {k: list(v) for k, v in self.expected_inputs.items()},
            "expected_outputs": {k: list(v) for k, v in self.expected_outputs.items()},
            "gates": [dict(g) for g in self.gates],
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["dependencies"] = sorted([list(e) for e in self.dependencies])
        if not data["workflow_plan_id"]:
            data["workflow_plan_id"] = make_stable_id("workflow_plan", self.canonical())
        return data


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


# --- WP-02e / T-02-10: DataPreparationTaskPacket subtype (REQ-OBJ-11) ---------


@dataclass
class DataPreparationTaskPacket:
    """A contract for *planned* data-preparation work (REQ-OBJ-11).

    Completes the TaskPacket subtype coverage alongside
    :class:`AnalysisTaskPacket`, :class:`EngineeringTaskPacket` and
    :class:`ReviewTaskPacket`.  A data-preparation packet declares the planned
    input facts it will consume (which may reference planned resource / dataset
    profile ids) and the expected *materialized* outputs it intends to produce,
    plus optional preparation steps and failure conditions.

    The packet is a contract record only: it does not download data, lock a
    dataset, authorise REAL execution, or create formal evidence.  The
    ``downloads_data`` / ``locks_dataset`` / ``authorizes_real_execution`` /
    ``creates_formal_evidence`` flags are pinned ``False`` and
    :func:`auto_bioinfo.core.validation.validate_data_preparation_task_packet`
    rejects any attempt to make them truthy — a boolean here is never authority.
    """

    task_id: str
    subquestion_id: str
    planned_inputs: list[str]
    expected_outputs: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    # Planned references — ids of resources / dataset profiles this prep will use.
    planned_resource_ids: list[str] = field(default_factory=list)
    planned_dataset_profile_ids: list[str] = field(default_factory=list)
    preparation_steps: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    # The packet confers no authority of its own; these stay False.
    downloads_data: bool = False
    locks_dataset: bool = False
    authorizes_real_execution: bool = False
    creates_formal_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["packet_type"] = "DataPreparationTaskPacket"
        if not data["task_id"]:
            data["task_id"] = make_stable_id(
                "data_preparation_task",
                {
                    "subquestion_id": self.subquestion_id,
                    "planned_inputs": list(self.planned_inputs),
                    "expected_outputs": list(self.expected_outputs),
                },
            )
        return data


@dataclass
class TaskRun:
    """An auditable record of a single run instance of a task (REQ-OBJ-12).

    The legacy ``TaskRun(task_run_id, task_id, result_status, artifact_refs, ...)``
    construction is preserved: those four fields stay first and keep their meaning.
    The record is hardened with structured *facts* about the run — its
    ``environment``, ``parameters``, command/``tool_identity``, ``log_refs`` /
    ``output_refs``, ``exit_code``, ``resource_usage``, retry lineage
    (``attempt`` / ``retry_of``) and an ``error_summary`` — so a completed or
    failed run can be audited from the record alone.

    Every field is a recorded fact or reference, never an action.  A TaskRun never
    runs a task, locks a dataset, authorises REAL execution, creates formal
    evidence, bypasses a gate, raises a claim level, or mutates workflow state: the
    authority-like flags are pinned ``False`` and
    :func:`auto_bioinfo.core.validation.validate_task_run` rejects any attempt to
    make them truthy.  Outputs and artifacts are references / checksummed facts
    only; this object never generates or registers an artifact.
    """

    task_run_id: str
    task_id: str
    result_status: str
    artifact_refs: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"
    # --- WP-02f / T-02-11: structured run-record facts (REQ-OBJ-12) ---
    environment: dict[str, Any] = field(default_factory=dict)
    tool_identity: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    log_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    exit_code: int | None = None
    resource_usage: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1
    retry_of: str = ""
    error_summary: str = ""
    reason: str = ""
    # The record confers no authority of its own; these stay False.
    authorizes_execution: bool = False
    locks_dataset: bool = False
    creates_formal_evidence: bool = False
    bypasses_gates: bool = False
    raises_claim_level: bool = False
    mutates_workflow_state: bool = False

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection used for the stable id.

        Only recorded run *facts* contribute to identity; the wall-clock
        ``created_at`` and the ``provenance`` envelope are excluded so the same
        run record always addresses to the same id."""
        return {
            "task_id": self.task_id,
            "result_status": self.result_status,
            "tool_identity": self.tool_identity,
            "environment": dict(self.environment),
            "parameters": dict(self.parameters),
            "exit_code": self.exit_code,
            "artifact_refs": list(self.artifact_refs),
            "output_refs": list(self.output_refs),
            "log_refs": list(self.log_refs),
            "resource_usage": dict(self.resource_usage),
            "attempt": self.attempt,
            "retry_of": self.retry_of,
            "error_summary": self.error_summary,
            "reason": self.reason,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["task_run_id"]:
            data["task_run_id"] = make_stable_id("task_run", self.canonical())
        return data


@dataclass
class ArtifactManifest:
    """A structured factual record of one file artifact (REQ-OBJ-13).

    The legacy seven-field construction
    (``artifact_id`` / ``project_id`` / ``path`` / ``exists`` /
    ``checksum_sha256`` / ``is_placeholder`` / ``qc_status``) is preserved and
    stays first.  The record is hardened with the artifact *facts* a registry
    needs — its content ``artifact_type`` / ``content_role``, the
    ``producer_agent_or_task`` / ``producer_run_id`` that produced it, the
    ``source_refs`` it derives from, its declared ``output_name`` /
    ``schema_name`` / ``media_type`` and ``size_bytes`` — so an artifact can be
    audited from the record alone.

    Every field is a recorded fact or reference, never an action.  Checksum and
    path are recorded facts only: this object never computes a checksum, creates,
    moves, or registers a file.  The authority-like flags are pinned ``False`` and
    :func:`auto_bioinfo.core.validation.validate_artifact_manifest` rejects any
    attempt to make them truthy — a manifest is never authorisation.
    """

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
    # --- WP-02g / T-02-12: structured artifact facts (REQ-OBJ-13) ---
    artifact_type: str = ""
    content_role: str = ""
    producer_agent_or_task: str = ""
    producer_run_id: str = ""
    source_refs: list[str] = field(default_factory=list)
    output_name: str = ""
    schema_name: str = ""
    media_type: str = ""
    size_bytes: int = 0
    expected_by_task_ids: list[str] = field(default_factory=list)
    supports_subquestion_ids: list[str] = field(default_factory=list)
    evidence_item_refs: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    # The manifest records facts only; it confers no authority. These stay False.
    authorizes_real_execution: bool = False
    creates_formal_evidence: bool = False
    locks_dataset: bool = False
    bypasses_gates: bool = False
    raises_claim_level: bool = False

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection used for the stable id."""
        return {
            "project_id": self.project_id,
            "path": self.path,
            "checksum_sha256": self.checksum_sha256,
            "is_placeholder": self.is_placeholder,
            "artifact_type": self.artifact_type,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["artifact_id"]:
            data["artifact_id"] = make_stable_id("artifact", self.canonical())
        return data


@dataclass
class QCReport:
    """A structured four-layer QC fact record (REQ-OBJ-14).

    The legacy ``QCReport(qc_report_id, overall_status, checks, ...)`` shape is
    preserved.  ``overall_status`` uses the bounded :data:`QC_OVERALL_STATUSES`
    vocabulary and ``checks`` is a list of structured check facts — each carrying
    a ``layer`` (:data:`QC_CHECK_LAYERS`), a ``status`` (:data:`QC_CHECK_STATUSES`),
    a ``reason`` (or ``detail``) and an optional metric / artifact ref — never a
    bare boolean.  ``artifact_id`` binds the report to the artifact it concerns.

    The report only *records* QC facts: it never creates evidence, raises a claim
    level, or authorises export/publishing
    (validated by :func:`auto_bioinfo.core.validation.validate_qc_report`).
    """

    qc_report_id: str
    overall_status: str
    checks: list[dict[str, Any]]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"
    # --- WP-02g / T-02-13: subject binding and authority pins (REQ-OBJ-14) ---
    artifact_id: str = ""
    # The report records facts only; it confers no authority. These stay False.
    creates_evidence: bool = False
    raises_claim_level: bool = False
    authorizes_export: bool = False
    bypasses_gates: bool = False

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection used for the stable id."""
        return {
            "artifact_id": self.artifact_id,
            "overall_status": self.overall_status,
            "checks": [c.get("check_id", c.get("id", "")) for c in self.checks if isinstance(c, dict)],
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["qc_report_id"]:
            data["qc_report_id"] = make_stable_id("qc_report", self.canonical())
        return data


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
    # --- WP-02g / T-02-14: evidence-record hardening (REQ-OBJ-15) ---
    # External validation is a recorded fact, not a self-assertion: the flag may
    # only be truthy when backed by recorded ``external_validation_refs``.
    externally_validated: bool = False
    external_validation_refs: list[str] = field(default_factory=list)
    # The record confers no authority of its own; these stay False.  (Note:
    # ``scientific_output_eligible`` above is a legitimate cached projection, not
    # an authority flag, and is recomputed by the admission gate.)
    raises_claim_level: bool = False
    bypasses_qc: bool = False
    creates_claim: bool = False
    authorizes_export: bool = False

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection used for the stable id.

        Mirrors the id derivation used by the evidence synthesiser so a recorded
        observation always addresses to the same evidence id."""
        return {"artifact_id": self.artifact_id, "observation": self.observation}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["evidence_item_id"]:
            data["evidence_item_id"] = make_stable_id("evidence_item", self.canonical())
        return data


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
    """A bounded scientific statement backed by evidence (REQ-OBJ-16).

    The legacy seven-field construction
    (``claim_id`` / ``text`` / ``claim_level`` / ``evidence_item_refs`` /
    ``supports_subquestion_ids`` / ``scope`` / ``limitations``) is preserved and
    stays first; ``evidence_item_refs`` is the claim's *supporting* evidence.  The
    statement is hardened with the facts that keep a claim from overreaching: its
    hard ``claim_ceiling`` (the level it may never cross), the ``opposing_evidence_refs``
    that argue against it, and the ``uncertainty`` it carries.

    Every field is a recorded fact or reference, never an action.  A claim never
    raises its own claim level, bypasses QC/gates, creates evidence, or authorises
    export/publishing: the authority-like flags are pinned ``False`` and
    :func:`auto_bioinfo.core.validation.validate_claim` rejects any attempt to make
    them truthy.  (Note: ``scientific_output_eligible`` is a legitimate cached
    projection of the eligibility decision, not an authority flag, and is recomputed
    by the admission gate.)
    """

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
    # --- WP-02h / T-02-15: bounded statement hardening (REQ-OBJ-16) ---
    # The hard ceiling this claim may never cross, the evidence that opposes it,
    # and the uncertainty it carries.  ``evidence_item_refs`` above stays the
    # supporting evidence; an opposing ref may not also be a supporting ref.
    claim_ceiling: str = "association"
    opposing_evidence_refs: list[str] = field(default_factory=list)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    # The statement confers no authority of its own; these stay False.
    raises_claim_level: bool = False
    bypasses_qc: bool = False
    bypasses_gates: bool = False
    creates_evidence: bool = False
    authorizes_export: bool = False
    publishes: bool = False

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection used for the stable id."""
        return {"text": self.text, "claim_level": self.claim_level, "evidence_item_refs": list(self.evidence_item_refs)}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["claim_id"]:
            data["claim_id"] = make_stable_id("claim", self.canonical())
        return data


@dataclass
class QuestionAlignmentReport:
    """Whether the final claims still answer the original question (REQ-OBJ-17).

    The legacy ``QuestionAlignmentReport(report_id, final_decision, unsupported_claims)``
    shape is preserved.  ``final_decision`` uses the bounded
    :data:`ALIGNMENT_DECISIONS` vocabulary — ``approve`` is the only passing
    verdict.  The report is hardened with the alignment facts a reviewer needs: the
    ``scope_drift_findings`` (claims that drifted outside the requested scope), the
    ``overclaim_findings`` (claims above their ceiling), the ``omitted_evidence``
    (negative/failed evidence that was dropped), the ``traceability_gaps`` (claims
    that cannot be traced back to evidence/sub-question), and any hard
    ``blocker_facts``.

    The report only *records* an alignment verdict; it never publishes, exports, or
    raises a claim level (validated by
    :func:`auto_bioinfo.core.validation.validate_question_alignment_report`, which
    rejects an ``approve`` decision while any blocker / unsupported claim / overclaim
    / scope drift / traceability gap is recorded).
    """

    report_id: str
    final_decision: str
    unsupported_claims: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    generated_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "recorded"
    # --- WP-02h / T-02-16: alignment-fact hardening (REQ-OBJ-17) ---
    research_spec_id: str = ""
    project_id: str = ""
    scope_drift_findings: list[dict[str, Any]] = field(default_factory=list)
    overclaim_findings: list[dict[str, Any]] = field(default_factory=list)
    omitted_evidence: list[dict[str, Any]] = field(default_factory=list)
    traceability_gaps: list[dict[str, Any]] = field(default_factory=list)
    blocker_facts: list[str] = field(default_factory=list)
    # The report records an alignment verdict only; these stay False.
    authorizes_export: bool = False
    publishes: bool = False
    raises_claim_level: bool = False
    bypasses_gates: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinalReportManifest:
    """Manifest of the produced final report and the claims it presents.

    Hardened only as far as report/claim traceability needs (REQ-OBJ-17 support):
    the ``claim_ids`` it presents stay the spine, and an optional
    ``alignment_report_id`` lets the manifest point at the
    :class:`QuestionAlignmentReport` that cleared it.  This object describes the
    report's contents only; it never generates, exports, or publishes a report —
    the authority-like flags are pinned ``False`` and
    :func:`auto_bioinfo.core.validation.validate_final_report_manifest` rejects any
    attempt to make them truthy.
    """

    final_report_id: str
    report_path: str
    claim_ids: list[str]
    schema_version: str = CANONICAL_SCHEMA_VERSION
    generated_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    # --- WP-02h / T-02-16: report/claim traceability (REQ-OBJ-17 support) ---
    alignment_report_id: str = ""
    # The manifest records contents only; it never generates or releases a report.
    authorizes_export: bool = False
    publishes: bool = False
    generates_report: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReproductionBundleManifest:
    """A manifest of what it takes to reproduce a result (REQ-OBJ-18).

    Records the ``files`` the bundle ships (each a ``{path, ...}`` fact, optionally
    checksummed), the ``run_order`` over those files, the ``environment_facts`` the
    run assumes, the ``expected_outputs`` it should produce, the ``comparison_rules``
    that decide whether a re-run matches, the ``reproducibility_level`` (how closely
    outputs must match) and the bounded ``reproduction_status`` verdict.

    The manifest is a contract record only: it never downloads, materialises,
    exports, or runs a bundle, never locks a dataset, and never creates formal
    evidence or authorises release.  The authority-like flags are pinned ``False``
    and :func:`auto_bioinfo.core.validation.validate_reproduction_bundle_manifest`
    rejects any attempt to make them truthy — a manifest is never authorisation.
    """

    bundle_id: str
    project_id: str
    files: list[dict[str, Any]] = field(default_factory=list)
    run_order: list[str] = field(default_factory=list)
    environment_facts: dict[str, Any] = field(default_factory=dict)
    expected_outputs: list[dict[str, Any]] = field(default_factory=list)
    comparison_rules: list[dict[str, Any]] = field(default_factory=list)
    reproducibility_level: str = "unspecified"
    reproduction_status: str = "pending"
    schema_version: str = CANONICAL_SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)
    provenance: list[dict[str, Any]] = field(default_factory=_default_provenance)
    status: str = "draft"
    # The manifest records facts only; it confers no authority. These stay False.
    materializes_bundle: bool = False
    exports_bundle: bool = False
    publishes: bool = False
    authorizes_real_execution: bool = False
    locks_dataset: bool = False
    creates_formal_evidence: bool = False

    def canonical(self) -> dict[str, Any]:
        """Content-only deterministic projection used for the stable id."""
        return {
            "project_id": self.project_id,
            "files": sorted(str(f.get("path", "")) for f in self.files if isinstance(f, dict)),
            "run_order": list(self.run_order),
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["bundle_id"]:
            data["bundle_id"] = make_stable_id("reproduction_bundle", self.canonical())
        return data


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
