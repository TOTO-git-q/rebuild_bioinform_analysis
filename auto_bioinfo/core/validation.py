import re
from typing import Any

from . import common
from .schemas import (
    AMBIGUITY_STATES,
    APPROVAL_DECISIONS,
    APPROVAL_STATES,
    ARTIFACT_QC_STATUSES,
    AUTOMATION_LEVELS,
    CLAIM_LEVELS,
    COMPATIBILITY_ACCEPTED_DECISIONS,
    COMPATIBILITY_DECISIONS,
    EVIDENCE_DIRECTIONS,
    EVIDENCE_GAP_STATES,
    EVIDENCE_GAP_TYPES,
    EVIDENCE_REPLICATED_STATUSES,
    EVIDENCE_REPLICATION_STATUSES,
    FEASIBILITY_ACCEPTED_DECISIONS,
    FEASIBILITY_DECISIONS,
    ONTOLOGY_CONFIDENCE_FLOOR,
    ONTOLOGY_MAPPING_STATES,
    QC_CHECK_LAYERS,
    QC_CHECK_STATUSES,
    QC_OVERALL_STATUSES,
    QC_PASSED_OVERALL_STATUSES,
    TASK_RUN_RESULT_STATUSES,
    DependencyGraph,
    WorkflowPlan,
)


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
    """Validate an ArtifactManifest as a structured artifact fact record (REQ-OBJ-13).

    Identity (``artifact_id`` / ``project_id``) must be present and well-formed and
    ``path`` must be a non-blank recorded fact.  ``qc_status`` must be a bounded
    :data:`ARTIFACT_QC_STATUSES` value and ``size_bytes`` (a recorded fact) must be
    a non-negative integer.  Reference lists (``source_refs`` /
    ``expected_by_task_ids`` / ``supports_subquestion_ids`` / ``evidence_item_refs``)
    must hold distinct, non-blank facts — a duplicate source ref is rejected.  An
    artifact that *claims to exist* must carry a real content checksum (a valid
    lowercase sha-256), and the evidence-readiness contract is kept: a
    non-existent, placeholder, or QC-failed artifact may not support evidence.  The
    manifest records facts only; any truthy authority-like flag (under any alias
    spelling) is rejected — a manifest never computes a checksum, registers a file,
    or grants authority.
    """
    errors = validate_required_fields(
        manifest,
        ["artifact_id", "project_id", "path", "exists", "checksum_sha256", "is_placeholder", "qc_status"],
    )
    errors += common.validate_identifier(manifest.get("artifact_id", ""), "artifact_id")
    errors += common.validate_identifier(manifest.get("project_id", ""), "project_id")
    path = manifest.get("path")
    if path is not None and not (isinstance(path, str) and path.strip()):
        errors.append("path: an artifact must record a non-blank path fact")

    qc_status = manifest.get("qc_status")
    if qc_status is not None and qc_status not in ARTIFACT_QC_STATUSES:
        errors.append(f"qc_status: must be one of {', '.join(ARTIFACT_QC_STATUSES)}")

    size = manifest.get("size_bytes")
    if size is not None:
        if isinstance(size, bool) or not isinstance(size, int):
            errors.append("size_bytes: expected a non-negative integer")
        elif size < 0:
            errors.append("size_bytes: must not be negative")

    # Reference list facts must be distinct, non-blank strings — the same source
    # ref (or expected-by / supports / evidence ref) may not be recorded twice.
    for list_field in ("source_refs", "expected_by_task_ids", "supports_subquestion_ids", "evidence_item_refs", "limitations"):
        if manifest.get(list_field) is not None:
            errors += _string_list_errors(manifest.get(list_field), list_field, require_unique=True)

    # An artifact that claims to exist must carry a real content checksum (recorded
    # fact only; never computed here).  Evidence-readiness: a non-existent,
    # placeholder, or QC-failed artifact may not support evidence.
    if manifest.get("exists") is True:
        errors += common.validate_hash(manifest.get("checksum_sha256"), "checksum_sha256")
    else:
        errors.append("artifact cannot support evidence when exists=false")
    if manifest.get("is_placeholder") is True:
        errors.append("artifact cannot support evidence when is_placeholder=true")
    if qc_status == "fail":
        errors.append("artifact cannot support evidence when qc_status=fail")

    errors += _reject_truthy_authority_flags(
        manifest,
        (
            "authorizes_real_execution",
            "real_execution_authorized",
            "creates_formal_evidence",
            "creates_evidence",
            "authorizes_formal_evidence",
            "locks_dataset",
            "dataset_locked",
            "bypasses_gates",
            "raises_claim_level",
            "claim_level_raised",
            "authorizes_export",
            "publishes",
        ),
        "artifact manifest",
    )
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


def _has_nonblank_entry(value: Any) -> bool:
    """True when ``value`` is a list with at least one non-blank string entry."""
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)


# --- WP-02b / T-02-03: ResearchSpec, AmbiguityReport, ScopeBundle, Ontology --


def validate_research_spec(spec: dict[str, Any]) -> list[str]:
    """Validate the key research object and its declared unknowns.

    The question, project binding and a valid claim ceiling are required.
    ``open_questions``/``assumptions`` must be lists of non-empty strings — an
    unknown has to be stated explicitly, never invented or left as a placeholder.
    """
    errors = validate_required_fields(spec, ["schema_version", "project_id", "research_question"])
    errors += common.validate_identifier(spec.get("project_id", ""), "project_id")
    for level_field in ("max_claim_level", "claim_ceiling"):
        if level_field in spec and spec.get(level_field) not in CLAIM_LEVELS:
            errors.append(f"{level_field}: must be one of {', '.join(CLAIM_LEVELS)}")
    for list_field in ("open_questions", "assumptions", "comparison_groups"):
        value = spec.get(list_field)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{list_field}: expected a list")
        elif any((not isinstance(item, str)) or not item.strip() for item in value):
            errors.append(f"{list_field}: entries must be non-empty strings (unknowns must be stated, not blank)")
    return errors


def validate_ambiguity_report(report: dict[str, Any]) -> list[str]:
    """Each ambiguity must record subject, impact and status; an ``assumed`` item
    must carry the explicit ``default_value`` it is proceeding on (no silent
    guessing).  Assumptions are kept distinct from confirmed facts."""
    errors = validate_required_fields(report, ["schema_version", "research_spec_id"])
    errors += common.validate_identifier(report.get("research_spec_id", ""), "research_spec_id")
    items = report.get("items")
    if items is None:
        items = []
    if not isinstance(items, list):
        return errors + ["items: expected a list of ambiguity records"]
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{idx}]: each ambiguity must be an object")
            continue
        for key in ("subject", "impact"):
            if not str(item.get(key, "") or "").strip():
                errors.append(f"items[{idx}].{key}: missing required ambiguity {key}")
        status = item.get("status")
        if status not in AMBIGUITY_STATES:
            errors.append(f"items[{idx}].status: must be one of {', '.join(AMBIGUITY_STATES)}")
        if status == "assumed" and not str(item.get("default_value", "") or "").strip():
            errors.append(f"items[{idx}]: an assumed ambiguity must record an explicit default_value (no silent guess)")
    return errors


def validate_scope_bundle(scope: dict[str, Any], *, require_comparison: bool = False) -> list[str]:
    """Validate the species/tissue/condition/comparison scope.

    Every axis must be a list; an axis that repeats a value, or a comparison of a
    group against itself, is contradictory and rejected.  A comparison must name
    at least two distinct groups.  A scope with no axis populated at all (or, when
    ``require_comparison``, no comparison) is an empty critical scope and fails.
    """
    errors = validate_required_fields(scope, ["schema_version", "research_spec_id"])
    errors += common.validate_identifier(scope.get("research_spec_id", ""), "research_spec_id")
    axes = ("species", "tissues", "conditions", "comparisons")
    populated = False
    for axis in axes:
        value = scope.get(axis)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{axis}: expected a list")
            continue
        if any((not isinstance(item, str)) or not item.strip() for item in value):
            errors.append(f"{axis}: scope entries must be non-empty strings (a blank value is not a scope)")
        if _has_nonblank_entry(value):
            populated = True
        if len(set(value)) != len(value):
            errors.append(f"{axis}: contradictory scope — the same value is listed more than once")
    comparisons = scope.get("comparisons")
    if isinstance(comparisons, list) and comparisons and len(set(comparisons)) < 2:
        errors.append("comparisons: a comparison needs at least two distinct groups (cannot compare a group with itself)")
    if not populated:
        errors.append("scope is empty: at least one of species/tissue/condition/comparison must be specified")
    elif require_comparison and not (isinstance(comparisons, list) and len(set(comparisons)) >= 2):
        errors.append("comparisons: a critical comparison scope is required but missing")
    return errors


def validate_ontology_mapping(mapping: dict[str, Any]) -> list[str]:
    """Validate one source-term -> standard-id mapping.

    A ``mapped`` status requires a non-empty ``mapped_id`` and a confidence at or
    above :data:`ONTOLOGY_CONFIDENCE_FLOOR` — a low-confidence score may not be
    recorded as a resolved fact.  An ``unresolved`` mapping must *not* carry a
    fabricated ``mapped_id``; the unmapped term stays explicit.
    """
    errors = validate_required_fields(mapping, ["schema_version", "research_spec_id", "source_term", "mapping_source", "status"])
    errors += common.validate_identifier(mapping.get("research_spec_id", ""), "research_spec_id")
    status = mapping.get("status")
    if status not in ONTOLOGY_MAPPING_STATES:
        errors.append(f"status: must be one of {', '.join(ONTOLOGY_MAPPING_STATES)}")
    confidence = mapping.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not (0.0 <= float(confidence) <= 1.0):
        errors.append("confidence: must be a number in [0.0, 1.0]")
        confidence = 0.0
    mapped_id = str(mapping.get("mapped_id", "") or "").strip()
    if status == "mapped":
        if not mapped_id:
            errors.append("mapped status requires a non-empty mapped_id")
        if float(confidence) < ONTOLOGY_CONFIDENCE_FLOOR:
            errors.append(f"confidence {confidence} below floor {ONTOLOGY_CONFIDENCE_FLOOR}: a low-confidence match cannot be recorded as 'mapped'")
    if status == "unresolved" and mapped_id:
        errors.append("unresolved mapping must not carry a mapped_id (do not invent an identifier)")
    return errors


# --- WP-02b / T-02-04: SubQuestion, DependencyGraph, EvidencePlan, Gap --------

# A sub-question is compound when it joins two predicates with an explicit
# clause conjunction or asks more than one thing.  ``between X and Y`` is a single
# relationship, so a bare "and" is not enough — only conjunctions that introduce a
# second interrogative/predicate count.
#
# Two cases are caught: a conjunction directly followed by a second
# interrogative/auxiliary ("...and how are..."), and a conjunction that introduces
# a fresh subject which then takes its own finite verb/auxiliary
# ("...change and pathways are enriched").  A range like "between A and B" carries
# no second predicate — the conjunction merely closes the range — so it stays
# single-purpose even when a finite verb follows the range
# ("...between A and B are differentially expressed").
_FINITE_AUX = (
    r"is|are|was|were|be|been|being|has|have|had|do|does|did"
    r"|can|could|shall|should|will|would|may|might|must"
)
_COMPOUND_MARKERS = re.compile(
    r"\b(?:and|or)\s+(?:also|then|how|what|which|whether|why|when|where|" + _FINITE_AUX + r")\b"
    r"|\b(?:and|or)\s+(?:\w+\s+){1,2}(?:" + _FINITE_AUX + r")\b"
    r"|\bas well as\b|\bin addition to\b",
    re.IGNORECASE,
)
# The conjunction inside a ``between X and/or Y`` range closes the range rather
# than introducing a second predicate, so it must not count as a compound marker.
# Match "between" up to the first following and/or and drop that conjunction
# before scanning for compound markers — the surrounding text is preserved so a
# genuine second predicate elsewhere ("...between A and B change and pathways are
# enriched") is still caught.
_BETWEEN_RANGE_CONJUNCTION = re.compile(
    r"\bbetween\b(?:(?!\b(?:and|or)\b)[^?;])*?\b(and|or)\b",
    re.IGNORECASE,
)


def _neutralize_between_range_conjunction(question: str) -> str:
    """Blank out the range conjunction in ``between X and/or Y`` constructions."""
    return _BETWEEN_RANGE_CONJUNCTION.sub(
        lambda m: m.group(0)[: m.start(1) - m.start(0)] + " " * (m.end(1) - m.start(1)),
        question,
    )


def subquestion_is_single_purpose(question: str) -> bool:
    """True when ``question`` expresses exactly one purpose/relationship.

    Rejects multiple terminal questions (more than one ``?``) and clauses joined
    by a second-predicate conjunction; a range like "between A and B" stays
    single-purpose even when followed by a finite verb.
    """
    if not isinstance(question, str) or not question.strip():
        return False
    if question.count("?") > 1:
        return False
    if ";" in question:
        return False
    return _COMPOUND_MARKERS.search(_neutralize_between_range_conjunction(question)) is None


def validate_subquestion(subquestion: dict[str, Any], research_spec_id: str | None = None) -> list[str]:
    """Each sub-question has one clear purpose and binds to its ResearchSpec."""
    errors = validate_required_fields(subquestion, ["schema_version", "research_spec_id", "question"])
    errors += common.validate_identifier(subquestion.get("research_spec_id", ""), "research_spec_id")
    if "claim_ceiling" in subquestion and subquestion.get("claim_ceiling") not in CLAIM_LEVELS:
        errors.append(f"claim_ceiling: must be one of {', '.join(CLAIM_LEVELS)}")
    question = subquestion.get("question", "")
    if isinstance(question, str) and question.strip() and not subquestion_is_single_purpose(question):
        errors.append("question: a sub-question must have a single purpose (split compound questions)")
    if research_spec_id is not None and subquestion.get("research_spec_id") != research_spec_id:
        errors.append("research_spec_id: sub-question is not bound to the expected ResearchSpec")
    return errors


def validate_dependency_graph(graph: dict[str, Any]) -> list[str]:
    """Reject dangling endpoints, self-loops and cycles in a dependency graph."""
    errors = validate_required_fields(graph, ["schema_version", "research_spec_id"])
    errors += common.validate_identifier(graph.get("research_spec_id", ""), "research_spec_id")
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not isinstance(nodes, list):
        return errors + ["nodes: expected a list"]
    if not isinstance(edges, list):
        return errors + ["edges: expected a list"]
    node_set = set(nodes)
    if len(node_set) != len(nodes):
        errors.append("nodes: duplicate node ids are not allowed")
    for idx, edge in enumerate(edges):
        if not (isinstance(edge, (list, tuple)) and len(edge) == 2):
            errors.append(f"edges[{idx}]: each edge must be a [from, to] pair")
            continue
        src, dst = edge[0], edge[1]
        if src == dst:
            errors.append(f"edges[{idx}]: self-loop {src!r} is not allowed")
        if src not in node_set:
            errors.append(f"edges[{idx}]: source {src!r} is not a declared node")
        if dst not in node_set:
            errors.append(f"edges[{idx}]: target {dst!r} is not a declared node")
    if not errors and DependencyGraph(research_spec_id=graph.get("research_spec_id", ""), nodes=list(nodes), edges=[list(e) for e in edges]).has_cycle():
        errors.append("dependency graph has a cycle; sub-question dependencies must be acyclic")
    return errors


def validate_evidence_plan(plan: dict[str, Any]) -> list[str]:
    """Evidence axes, the claim ceiling and any planned gaps must be explicit.

    A plan must declare at least one evidence axis *or* an explicit stop reason /
    planned gap — it may never advance with no evidence path and no stated reason.
    """
    errors = validate_required_fields(plan, ["schema_version", "research_spec_id", "max_claim_level"])
    errors += common.validate_identifier(plan.get("research_spec_id", ""), "research_spec_id")
    if plan.get("max_claim_level") not in CLAIM_LEVELS:
        errors.append(f"max_claim_level: must be one of {', '.join(CLAIM_LEVELS)}")
    # evidence_axes may legitimately be empty *iff* an explicit stop reason is
    # given, so it is checked below rather than as a generic required field.
    axes = plan.get("evidence_axes")
    if axes is not None and not isinstance(axes, list):
        errors.append("evidence_axes: expected a list")
        axes = []
    for list_field in ("planned_gaps", "stop_conditions", "subquestion_ids"):
        if list_field in plan and not isinstance(plan.get(list_field), list):
            errors.append(f"{list_field}: expected a list")
    has_axes = bool(axes)
    # A blank/whitespace-only entry is not a meaningful stop reason or planned gap.
    has_stop = _has_nonblank_entry(plan.get("stop_conditions")) or _has_nonblank_entry(plan.get("planned_gaps"))
    if not has_axes and not has_stop:
        errors.append("evidence plan must declare at least one evidence axis or an explicit stop_condition/planned_gap")
    return errors


def validate_evidence_gap(gap: dict[str, Any]) -> list[str]:
    """A gap records missing/insufficient evidence and only *caps* a claim.

    ``imposed_claim_ceiling`` is the ceiling that applies while the gap is open;
    it must be a valid claim level.  A gap is never allowed to *raise* a claim, so
    when ``prior_claim_level`` is supplied the imposed ceiling must not exceed it.
    """
    errors = validate_required_fields(gap, ["schema_version", "research_spec_id", "subquestion_id", "description", "gap_type", "status"])
    errors += common.validate_identifier(gap.get("research_spec_id", ""), "research_spec_id")
    errors += common.validate_identifier(gap.get("subquestion_id", ""), "subquestion_id")
    if gap.get("gap_type") not in EVIDENCE_GAP_TYPES:
        errors.append(f"gap_type: must be one of {', '.join(EVIDENCE_GAP_TYPES)}")
    if gap.get("status") not in EVIDENCE_GAP_STATES:
        errors.append(f"status: must be one of {', '.join(EVIDENCE_GAP_STATES)}")
    ceiling = gap.get("imposed_claim_ceiling", "descriptive")
    if ceiling not in CLAIM_LEVELS:
        errors.append(f"imposed_claim_ceiling: must be one of {', '.join(CLAIM_LEVELS)}")
    else:
        prior = gap.get("prior_claim_level")
        if prior in CLAIM_LEVELS and CLAIM_LEVELS.index(ceiling) > CLAIM_LEVELS.index(prior):
            errors.append(f"imposed_claim_ceiling {ceiling} would raise the claim above prior {prior}; a gap may only cap a claim")
    return errors


# --- WP-02c / T-02-05..06: resource & dataset feasibility validators ----------

# The minimum verification level at which a recorded "verified" assertion is
# more than a bare boolean; kept in sync with the R0-01 truthful-execution gate
# in :mod:`auto_bioinfo.core.provenance`.
_MIN_VERIFICATION_FOR_VERIFIED_FACT = "METADATA_VERIFIED"


def _validate_provenance_markers(obj: dict[str, Any]) -> list[str]:
    """Validate the four R0-01 provenance markers and reject a bare "verified".

    ``source_class`` / ``retrieval_mode`` / ``verification_level`` must use the
    canonical provenance vocabularies when present.  A ``verified=True`` or
    ``legacy_verified_assertion=True`` flag is *not* authorisation on its own: it
    is rejected unless ``verification_level`` is at least
    ``METADATA_VERIFIED`` — a boolean never substitutes for verified facts.
    """
    # Imported lazily to avoid the provenance <-> schema import cycle.
    from .provenance import (
        RETRIEVAL_MODES,
        SOURCE_CLASSES,
        VERIFICATION_LEVELS,
        verification_at_least,
    )

    errors: list[str] = []
    marker_checks = (
        ("source_class", SOURCE_CLASSES),
        ("retrieval_mode", RETRIEVAL_MODES),
        ("verification_level", VERIFICATION_LEVELS),
    )
    for field_name, allowed in marker_checks:
        if field_name in obj and obj.get(field_name) not in allowed:
            errors.append(f"{field_name}: must be one of {', '.join(allowed)}")
    asserted = obj.get("verified") is True or obj.get("legacy_verified_assertion") is True
    if asserted and not verification_at_least(str(obj.get("verification_level", "UNVERIFIED")), _MIN_VERIFICATION_FOR_VERIFIED_FACT):
        errors.append(
            f"a verified assertion requires verification_level >= {_MIN_VERIFICATION_FOR_VERIFIED_FACT} (a boolean is not authorisation without verified facts)"
        )
    return errors


def validate_resource_candidate(candidate: dict[str, Any]) -> list[str]:
    """A candidate resource must name itself, a type and a source status, keep its
    R0-01 provenance markers honest, and never present an unverifiable mock /
    placeholder / ``AUTO_``-accession resource as ``verified``."""
    errors = validate_required_fields(candidate, ["schema_version", "resource_name", "resource_type", "source_status"])
    errors += validate_no_unknown_verified_dataset(candidate)
    errors += _validate_provenance_markers(candidate)
    return errors


def validate_dataset_profile(profile: dict[str, Any]) -> list[str]:
    """Validate a dataset's factual profile (REQ-OBJ-05).

    ``dataset_id`` and ``modality`` are required; the R0-01 provenance markers are
    checked and a bare "verified" assertion is rejected.  Factual fields may be
    absent (an unverified profile stays valid but non-authoritative), but a field
    that is *present* must not be blank or internally contradictory: species facts
    must be distinct non-blank strings, samples and files must be objects carrying
    a non-blank id/name, sample ids must be unique, a positive ``sample_count``
    must be backed by recorded samples and must agree with their number, and a
    grouping may not reference a sample id that is not declared in ``samples`` (even
    when no samples are declared at all).
    """
    errors = validate_required_fields(profile, ["schema_version", "dataset_id", "modality"])
    errors += common.validate_identifier(profile.get("dataset_id", ""), "dataset_id")
    errors += _validate_provenance_markers(profile)

    species = profile.get("species")
    if species is not None:
        if not isinstance(species, list):
            errors.append("species: expected a list")
        else:
            if any((not isinstance(item, str)) or not item.strip() for item in species):
                errors.append("species: facts must be non-empty strings (a blank fact is not a fact)")
            if len(set(species)) != len(species):
                errors.append("species: contradictory — the same species is listed more than once")

    samples = profile.get("samples")
    sample_ids: set[str] = set()
    if samples is not None:
        if not isinstance(samples, list):
            errors.append("samples: expected a list")
            samples = None
        else:
            for idx, sample in enumerate(samples):
                if not isinstance(sample, dict):
                    errors.append(f"samples[{idx}]: each sample must be an object")
                    continue
                sample_id = str(sample.get("sample_id", "") or "").strip()
                if not sample_id:
                    errors.append(f"samples[{idx}]: missing required sample_id")
                elif sample_id in sample_ids:
                    errors.append(f"samples[{idx}]: duplicate sample_id {sample_id!r} — sample ids must be unique")
                else:
                    sample_ids.add(sample_id)

    count = profile.get("sample_count")
    if isinstance(count, bool) or not isinstance(count, int):
        if count is not None:
            errors.append("sample_count: expected an integer")
    elif count < 0:
        errors.append("sample_count: must not be negative")
    elif count > 0 and not (isinstance(samples, list) and samples):
        errors.append(f"sample_count {count} claims samples but the profile records none — a positive count is an unbound fact")
    elif isinstance(samples, list) and samples and count != len(samples):
        errors.append(f"sample_count {count} contradicts the {len(samples)} recorded samples")

    files = profile.get("files")
    if files is not None:
        if not isinstance(files, list):
            errors.append("files: expected a list")
        else:
            for idx, item in enumerate(files):
                if not isinstance(item, dict):
                    errors.append(f"files[{idx}]: each file must be an object")
                elif not str(item.get("name", "") or "").strip():
                    errors.append(f"files[{idx}]: missing required file name")

    grouping = profile.get("grouping")
    if grouping is not None and not isinstance(grouping, dict):
        errors.append("grouping: expected an object")
    elif isinstance(grouping, dict):
        # A grouping that names sample ids is a positive sample fact: every member
        # must resolve to a declared sample.  This runs even when no samples are
        # declared, so a grouping over an empty sample set is rejected too.
        for label, members in grouping.items():
            if isinstance(members, list):
                for member in members:
                    if str(member) not in sample_ids:
                        errors.append(f"grouping[{label!r}]: references unknown sample_id {member!r}")

    metadata_facts = profile.get("metadata_facts")
    if metadata_facts is not None and not isinstance(metadata_facts, dict):
        errors.append("metadata_facts: expected an object")
    return errors


def validate_dataset_feasibility_report(report: dict[str, Any]) -> list[str]:
    """Validate a dataset feasibility verdict for a sub-question (REQ-OBJ-06).

    The verdict must bind its dataset profile / research spec / sub-question and
    use a value from :data:`FEASIBILITY_DECISIONS`, and must always record at
    least one non-blank reason.  An *accepted* verdict (usable /
    conditionally_usable) additionally needs the evidence-plan binding it
    satisfies and the dataset facts it checked; a conditional verdict needs its
    conditions plus a conservative claim ceiling.  A *negative* verdict
    (not_usable / insufficient) must keep its missing facts / blocking gaps
    instead of pretending success, and an insufficient verdict records a
    conservative ceiling.  The report never carries locking / REAL / formal-
    evidence authority — those flags are rejected if set.
    """
    errors = validate_required_fields(report, ["schema_version", "dataset_profile_id", "research_spec_id", "subquestion_id", "decision"])
    errors += common.validate_identifier(report.get("dataset_profile_id", ""), "dataset_profile_id")
    errors += common.validate_identifier(report.get("research_spec_id", ""), "research_spec_id")
    errors += common.validate_identifier(report.get("subquestion_id", ""), "subquestion_id")

    decision = report.get("decision")
    if decision not in FEASIBILITY_DECISIONS:
        errors.append(f"decision: must be one of {', '.join(FEASIBILITY_DECISIONS)}")

    for list_field in ("reasons", "required_facts_checked", "missing_facts", "blocking_gaps", "conditional_use_notes"):
        if list_field in report and not isinstance(report.get(list_field), list):
            errors.append(f"{list_field}: expected a list")

    # The report observes feasibility; it confers no authority on its own.  Any
    # truthy value (not just the literal ``True``) is an attempt to assert
    # authority and is rejected; explicit false / absent flags stay valid.
    for flag in ("locks_dataset", "authorizes_real_execution", "authorizes_formal_evidence", "bypasses_gates"):
        if report.get(flag):
            errors.append(f"{flag}: a feasibility report confers no such authority and may not assert a truthy {flag}")

    ceiling = report.get("imposed_claim_ceiling")
    has_ceiling = ceiling in CLAIM_LEVELS
    if ceiling not in (None, "") and not has_ceiling:
        errors.append(f"imposed_claim_ceiling: must be one of {', '.join(CLAIM_LEVELS)}")

    # Every verdict must record an honest, non-blank reason.
    if not _has_nonblank_entry(report.get("reasons")):
        errors.append("reasons: a feasibility decision must record at least one explicit, non-blank reason")

    if decision in FEASIBILITY_ACCEPTED_DECISIONS:
        evidence_plan_id = str(report.get("evidence_plan_id", "") or "").strip()
        if not evidence_plan_id:
            errors.append("evidence_plan_id: an accepted feasibility decision must bind the evidence plan it satisfies")
        else:
            errors += common.validate_identifier(evidence_plan_id, "evidence_plan_id")
        if not _has_nonblank_entry(report.get("required_facts_checked")):
            errors.append("required_facts_checked: a usable/conditionally-usable decision must record the dataset facts it checked")
        if decision == "conditionally_usable":
            if not _has_nonblank_entry(report.get("conditional_use_notes")):
                errors.append("conditional_use_notes: a conditionally-usable decision must record its conditions")
            if not has_ceiling:
                errors.append("imposed_claim_ceiling: a conditional decision must record a conservative claim ceiling")
    elif decision in FEASIBILITY_DECISIONS:
        if not (_has_nonblank_entry(report.get("missing_facts")) or _has_nonblank_entry(report.get("blocking_gaps"))):
            errors.append("a not-usable/insufficient decision must record the missing facts or blocking gaps behind it")
        if decision == "insufficient" and not has_ceiling:
            errors.append("imposed_claim_ceiling: an insufficient decision must record a conservative claim ceiling")
    return errors


# --- WP-02d / T-02-07..08: method & compatibility contract validators ---------

# The list facts of a MethodContract: every entry must be a non-blank string and
# no entry may be duplicated (a repeated requirement is not two facts).
_METHOD_CONTRACT_LIST_FIELDS = (
    "supported_modalities",
    "required_inputs",
    "required_metadata",
    "minimum_design_facts",
    "outputs",
    "statistical_assumptions",
    "required_qc",
    "known_limitations",
    "applicable_conditions",
    "forbidden_conditions",
)
# Applicability facts an *active* contract must positively record.
_METHOD_CONTRACT_ACTIVE_REQUIRED = ("supported_modalities", "required_inputs", "outputs")


def _normalized_condition_set(values: Any) -> set[str]:
    """Case/space-insensitive set of the non-blank string entries in ``values``."""
    if not isinstance(values, list):
        return set()
    return {item.strip().lower() for item in values if isinstance(item, str) and item.strip()}


def validate_method_contract(contract: dict[str, Any]) -> list[str]:
    """Validate a standalone MethodContract's scientific boundary (REQ-OBJ-08).

    Stable identity (``method_id`` / ``method_name`` / ``version``) is mandatory
    and may not be blank; ``method_id`` must be a well-formed identifier.  The
    claim capability and ceiling must be valid claim levels and the capability may
    never exceed the ceiling.  Every list fact must hold distinct, non-blank
    strings — a duplicated requirement is rejected.  An *active* contract must
    positively record its applicability and output facts (supported modality,
    required inputs, outputs).  A condition listed as both applicable and
    forbidden is contradictory and rejected.  The contract only describes a
    boundary; it never selects, executes or authorises a method.
    """
    errors = validate_required_fields(contract, ["schema_version", "method_id", "method_name", "version"])
    errors += common.validate_identifier(contract.get("method_id", ""), "method_id")

    for level_field in ("claim_capability", "claim_ceiling"):
        value = contract.get(level_field)
        if value is not None and value not in CLAIM_LEVELS:
            errors.append(f"{level_field}: must be one of {', '.join(CLAIM_LEVELS)}")
    capability = contract.get("claim_capability")
    ceiling = contract.get("claim_ceiling")
    if capability in CLAIM_LEVELS and ceiling in CLAIM_LEVELS and CLAIM_LEVELS.index(capability) > CLAIM_LEVELS.index(ceiling):
        errors.append(f"claim_capability {capability} exceeds claim_ceiling {ceiling}; a method may not claim above its ceiling")

    for list_field in _METHOD_CONTRACT_LIST_FIELDS:
        value = contract.get(list_field)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{list_field}: expected a list")
            continue
        if any((not isinstance(item, str)) or not item.strip() for item in value):
            errors.append(f"{list_field}: entries must be non-empty strings (a blank fact is not a fact)")
        normalized = [item.strip() for item in value if isinstance(item, str)]
        if len(set(normalized)) != len(normalized):
            errors.append(f"{list_field}: duplicate requirement entries are not allowed")

    if contract.get("status", "active") == "active":
        for required_list in _METHOD_CONTRACT_ACTIVE_REQUIRED:
            if not _has_nonblank_entry(contract.get(required_list)):
                errors.append(f"{required_list}: an active method contract must record at least one explicit fact")

    overlap = _normalized_condition_set(contract.get("applicable_conditions")) & _normalized_condition_set(contract.get("forbidden_conditions"))
    if overlap:
        errors.append(f"contradictory conditions: {sorted(overlap)} listed as both applicable and forbidden")
    return errors


def validate_compatibility_decision(decision: dict[str, Any]) -> list[str]:
    """Validate a method<->dataset<->sub-question compatibility verdict (REQ-OBJ-09).

    The verdict must bind its method contract and dataset and use a value from
    :data:`COMPATIBILITY_DECISIONS`, and must always record at least one non-blank
    reason — a bare boolean never stands alone.  An *accepted* verdict
    (compatible / conditionally_compatible) additionally needs the sub-question and
    evidence-plan bindings it was decided against and the dataset facts it checked;
    a conditional verdict records a conservative claim ceiling.  A *negative*
    verdict (incompatible / insufficient_information) must keep its blocking facts
    or gaps instead of pretending compatibility, and an insufficient verdict
    records a conservative ceiling.  The decision never carries execution /
    locking / evidence / claim-raising authority — those flags are rejected if set.
    """
    errors = validate_required_fields(decision, ["schema_version", "dataset_id", "method_contract_id", "decision"])
    errors += common.validate_identifier(decision.get("method_contract_id", ""), "method_contract_id")
    errors += common.validate_identifier(decision.get("dataset_id", ""), "dataset_id")

    verdict = decision.get("decision")
    if verdict not in COMPATIBILITY_DECISIONS:
        errors.append(f"decision: must be one of {', '.join(COMPATIBILITY_DECISIONS)}")

    # The legacy ``compatible`` boolean and the hardened bounded ``decision`` may
    # not contradict each other.  When both are present, the boolean must agree
    # with the verdict — an accepted verdict (compatible / conditionally_compatible)
    # means compatible, a negative verdict (incompatible / insufficient_information)
    # means not compatible — so the same object can never express opposite results
    # to consumers that read one field versus the other.  When ``decision`` is
    # absent it is derived from ``compatible`` (see ``CompatibilityDecision.to_dict``)
    # and is consistent by construction, so nothing here rejects the legacy form.
    compatible = decision.get("compatible")
    if isinstance(compatible, bool) and verdict in COMPATIBILITY_DECISIONS:
        if compatible != (verdict in COMPATIBILITY_ACCEPTED_DECISIONS):
            errors.append(f"compatible: the legacy boolean contradicts the hardened decision (compatible={compatible} with decision={verdict!r})")

    for list_field in ("reasons", "checked_facts", "blocking_facts", "missing_facts"):
        if list_field in decision and not isinstance(decision.get(list_field), list):
            errors.append(f"{list_field}: expected a list")

    # The decision observes compatibility; it confers no authority on its own.  Any
    # truthy value (not just the literal ``True``) is an attempt to assert authority
    # and is rejected; explicit false / absent flags stay valid.
    for flag in ("authorizes_execution", "locks_dataset", "creates_evidence", "raises_claim_level"):
        if decision.get(flag):
            errors.append(f"{flag}: a compatibility decision confers no such authority and may not assert a truthy {flag}")

    ceiling = decision.get("imposed_claim_ceiling")
    has_ceiling = ceiling in CLAIM_LEVELS
    if ceiling not in (None, "") and not has_ceiling:
        errors.append(f"imposed_claim_ceiling: must be one of {', '.join(CLAIM_LEVELS)}")

    # Every verdict must record an honest, non-blank reason — no bare boolean.
    if not _has_nonblank_entry(decision.get("reasons")):
        errors.append("reasons: a compatibility decision must record at least one explicit, non-blank reason")

    if verdict in COMPATIBILITY_ACCEPTED_DECISIONS:
        for binding in ("subquestion_id", "evidence_plan_id"):
            bound = str(decision.get(binding, "") or "").strip()
            if not bound:
                errors.append(f"{binding}: an accepted compatibility decision must bind the {binding}")
            else:
                errors += common.validate_identifier(bound, binding)
        if not _has_nonblank_entry(decision.get("checked_facts")):
            errors.append("checked_facts: a compatible/conditionally-compatible decision must record the dataset facts it checked")
        if verdict == "conditionally_compatible" and not has_ceiling:
            errors.append("imposed_claim_ceiling: a conditional compatibility decision must record a conservative claim ceiling")
    elif verdict in COMPATIBILITY_DECISIONS:
        if not (_has_nonblank_entry(decision.get("blocking_facts")) or _has_nonblank_entry(decision.get("missing_facts"))):
            errors.append("an incompatible/insufficient decision must record the blocking facts or gaps behind it")
        if verdict == "insufficient_information" and not has_ceiling:
            errors.append("imposed_claim_ceiling: an insufficient decision must record a conservative claim ceiling")
    return errors


# --- WP-02e / T-02-09..10: workflow DAG & task-packet contract validators ------


def _string_list_errors(value: Any, field: str, *, require_unique: bool = False) -> list[str]:
    """Shared non-blank-string-list check used by the task-packet validators.

    A present value must be a list whose entries are all non-blank strings; with
    ``require_unique`` a repeated entry (a fact stated twice) is rejected too.
    """
    if not isinstance(value, list):
        return [f"{field}: expected a list"]
    errors: list[str] = []
    if any((not isinstance(item, str)) or not item.strip() for item in value):
        errors.append(f"{field}: entries must be non-empty strings (a blank fact is not a fact)")
    if require_unique:
        normalized = [item for item in value if isinstance(item, str)]
        if len(set(normalized)) != len(normalized):
            errors.append(f"{field}: duplicate entries are not allowed")
    return errors


def validate_workflow_plan(plan: dict[str, Any]) -> list[str]:
    """Validate a WorkflowPlan as an explicit acyclic task DAG (REQ-OBJ-10).

    ``workflow_name`` and a non-empty ``task_ids`` list are required.  Every task
    id must be a non-blank string and may not be declared twice.  Each
    ``dependencies`` edge must be a ``[from_task, to_task]`` pair whose endpoints
    are declared tasks and which is not a self-loop, and the resulting dependency
    graph must be acyclic — acyclicity is checked explicitly, never assumed from
    the linear ``task_ids`` order.  ``expected_inputs`` / ``expected_outputs``
    (keyed by task id) and ``gates`` (each bound to a task id) may only reference
    declared tasks and must carry distinct, non-blank facts.  The plan is contract
    data only; this validator never compiles, schedules, or runs a task.
    """
    errors = validate_required_fields(plan, ["schema_version", "workflow_name", "task_ids"])
    task_ids = plan.get("task_ids")
    if not isinstance(task_ids, list):
        return errors + ["task_ids: expected a list of task ids"]

    declared: set[str] = set()
    for idx, task_id in enumerate(task_ids):
        if not (isinstance(task_id, str) and task_id.strip()):
            errors.append(f"task_ids[{idx}]: a task id must be a non-blank string")
            continue
        if task_id in declared:
            errors.append(f"task_ids[{idx}]: duplicate task id {task_id!r} is not allowed")
        else:
            declared.add(task_id)

    dependencies = plan.get("dependencies")
    if dependencies is None:
        dependencies = []
    if not isinstance(dependencies, list):
        errors.append("dependencies: expected a list of [from_task, to_task] pairs")
        dependencies = []
    else:
        for idx, edge in enumerate(dependencies):
            if not (isinstance(edge, (list, tuple)) and len(edge) == 2):
                errors.append(f"dependencies[{idx}]: each dependency must be a [from_task, to_task] pair")
                continue
            src, dst = edge[0], edge[1]
            if src == dst:
                errors.append(f"dependencies[{idx}]: self-loop {src!r} is not allowed")
            if src not in declared:
                errors.append(f"dependencies[{idx}]: source {src!r} is not a declared task")
            if dst not in declared:
                errors.append(f"dependencies[{idx}]: target {dst!r} is not a declared task")

    for mapping_field in ("expected_inputs", "expected_outputs"):
        mapping = plan.get(mapping_field)
        if mapping is None:
            continue
        if not isinstance(mapping, dict):
            errors.append(f"{mapping_field}: expected an object keyed by task id")
            continue
        for task_id, items in mapping.items():
            if task_id not in declared:
                errors.append(f"{mapping_field}[{task_id!r}]: references undeclared task")
            errors += _string_list_errors(items, f"{mapping_field}[{task_id!r}]", require_unique=True)

    gates = plan.get("gates")
    if gates is not None:
        if not isinstance(gates, list):
            errors.append("gates: expected a list of gate objects")
        else:
            for idx, gate in enumerate(gates):
                if not isinstance(gate, dict):
                    errors.append(f"gates[{idx}]: each gate must be an object")
                    continue
                gate_task = gate.get("task_id")
                if gate_task is not None and gate_task not in declared:
                    errors.append(f"gates[{idx}]: references undeclared task {gate_task!r}")
                for member in gate.get("task_ids", []) if isinstance(gate.get("task_ids"), list) else []:
                    if member not in declared:
                        errors.append(f"gates[{idx}]: references undeclared task {member!r}")

    # Acyclicity is asserted explicitly over the declared dependency edges; a
    # linear task_ids list never implies a checked DAG on its own.
    if (
        not errors
        and WorkflowPlan(
            workflow_name=plan.get("workflow_name", ""),
            task_ids=list(task_ids),
            dependencies=[list(e) for e in dependencies],
        ).has_cycle()
    ):
        errors.append("workflow plan has a dependency cycle; task dependencies must form an acyclic DAG")
    return errors


def _reject_truthy_authority_flags(obj: dict[str, Any], flags: tuple[str, ...], subject: str) -> list[str]:
    """Reject any truthy authority-like flag on a contract-only record.

    A contract record never grants authority on its own, so any truthy value (not
    just the literal ``True``) is an attempt to assert authority and is rejected;
    explicit false / absent flags stay valid.
    """
    return [f"{flag}: a {subject} confers no such authority and may not assert a truthy {flag}" for flag in flags if obj.get(flag)]


def validate_analysis_task_packet(packet: dict[str, Any]) -> list[str]:
    """Validate an AnalysisTaskPacket contract record (REQ-OBJ-11).

    Identity (``task_id`` / ``subquestion_id``) must be present and well-formed.
    The expected inputs/outputs, QC requirements and failure conditions must all be
    distinct, non-blank facts, and an analysis packet may never carry code-change
    authority.  This only validates the contract record; it does not change the
    runtime packet behaviour in :mod:`auto_bioinfo.core.task_packets`.
    """
    errors = validate_required_fields(
        packet, ["schema_version", "task_id", "subquestion_id", "expected_inputs", "expected_outputs", "qc_requirements", "failure_conditions"]
    )
    errors += common.validate_identifier(packet.get("task_id", ""), "task_id")
    errors += common.validate_identifier(packet.get("subquestion_id", ""), "subquestion_id")
    for list_field in ("expected_inputs", "expected_outputs"):
        if packet.get(list_field) is not None:
            errors += _string_list_errors(packet.get(list_field), list_field, require_unique=True)
    for list_field in ("qc_requirements", "failure_conditions"):
        if packet.get(list_field) is not None:
            errors += _string_list_errors(packet.get(list_field), list_field)
    if packet.get("code_change_instructions"):
        errors.append("code_change_instructions: an analysis packet must not carry code-change authority")
    return errors


def _path_escapes_scope(path: str) -> bool:
    """True when ``path`` claims authority outside the packet's declared scope.

    Both ``/`` and ``\\`` are treated as separators so a platform-specific path
    syntax cannot smuggle an escape past the validator.  An escape is any of:
    a POSIX absolute path or UNC-style absolute path (leading separator), a
    Windows drive-letter path (``C:\\...`` / ``C:/...`` / ``C:...``), or a
    ``..`` parent-traversal segment in any slash style.  A relative path that
    stays inside the declared scope is not an escape.
    """
    normalized = path.replace("\\", "/")
    if normalized.startswith("/"):
        return True
    if re.match(r"^[A-Za-z]:", normalized):
        return True
    return ".." in normalized.split("/")


def validate_engineering_task_packet(packet: dict[str, Any]) -> list[str]:
    """Validate an EngineeringTaskPacket contract record (REQ-OBJ-11).

    Identity is required and the allowed/forbidden path lists must hold distinct,
    non-blank paths.  An allowed path may not escape the packet's declared scope —
    a POSIX or Windows absolute path (leading ``/``, UNC, or a ``C:`` drive
    letter) or a ``..`` parent traversal in either slash style is path authority
    outside scope — and a path may not be declared both allowed and forbidden.
    This validates the contract record only; it does not change runtime packet
    behaviour.
    """
    errors = validate_required_fields(packet, ["schema_version", "task_id", "allowed_paths", "forbidden_paths", "expected_patch_summary", "test_commands"])
    errors += common.validate_identifier(packet.get("task_id", ""), "task_id")
    allowed = packet.get("allowed_paths")
    forbidden = packet.get("forbidden_paths")
    for path_field, value in (("allowed_paths", allowed), ("forbidden_paths", forbidden)):
        if value is not None:
            errors += _string_list_errors(value, path_field, require_unique=True)
    if packet.get("test_commands") is not None:
        errors += _string_list_errors(packet.get("test_commands"), "test_commands")
    if isinstance(allowed, list):
        for path in allowed:
            if isinstance(path, str) and _path_escapes_scope(path):
                errors.append(f"allowed_paths: {path!r} escapes the packet's declared scope (absolute path or parent traversal)")
    if isinstance(allowed, list) and isinstance(forbidden, list):
        overlap = {p for p in allowed if isinstance(p, str)} & {p for p in forbidden if isinstance(p, str)}
        if overlap:
            errors.append(f"path authority: {sorted(overlap)} listed as both allowed and forbidden")
    return errors


def validate_review_task_packet(packet: dict[str, Any]) -> list[str]:
    """Validate a ReviewTaskPacket contract record (REQ-OBJ-11).

    Identity is required, the ``claim_ceiling`` must be a valid claim level, and a
    review packet must record a non-blank audit scope and at least one required
    review check — a review with no criteria is not a review.  This validates the
    contract record only; it does not change runtime packet behaviour.
    """
    errors = validate_required_fields(packet, ["schema_version", "task_id", "audit_scope", "claim_ceiling", "required_checks"])
    errors += common.validate_identifier(packet.get("task_id", ""), "task_id")
    if packet.get("claim_ceiling") not in CLAIM_LEVELS:
        errors.append(f"claim_ceiling: must be one of {', '.join(CLAIM_LEVELS)}")
    for list_field in ("audit_scope", "required_checks"):
        if packet.get(list_field) is not None:
            errors += _string_list_errors(packet.get(list_field), list_field)
    return errors


def validate_data_preparation_task_packet(packet: dict[str, Any]) -> list[str]:
    """Validate a DataPreparationTaskPacket contract record (REQ-OBJ-11).

    Identity (``task_id`` / ``subquestion_id``) is required and well-formed.  A
    prep packet must declare at least one planned input fact and one expected
    materialized output, and those facts (plus any planned resource / dataset
    profile ids and preparation steps) must be distinct and non-blank.  The packet
    is a contract record only: it may not download data, lock a dataset, authorise
    REAL execution, create formal evidence, or bypass gates, so any truthy
    authority-like flag — including alias field names for the same powers — is
    rejected.
    """
    errors = validate_required_fields(packet, ["schema_version", "task_id", "subquestion_id", "planned_inputs", "expected_outputs"])
    errors += common.validate_identifier(packet.get("task_id", ""), "task_id")
    errors += common.validate_identifier(packet.get("subquestion_id", ""), "subquestion_id")
    for list_field in ("planned_inputs", "expected_outputs", "planned_resource_ids", "planned_dataset_profile_ids", "preparation_steps", "failure_conditions"):
        if packet.get(list_field) is not None:
            errors += _string_list_errors(packet.get(list_field), list_field, require_unique=True)
    errors += _reject_truthy_authority_flags(
        packet,
        (
            "downloads_data",
            "locks_dataset",
            "authorizes_real_execution",
            "creates_formal_evidence",
            # Alias / alternative authority field names that express the same
            # forbidden powers; a prep packet is a contract record only and may
            # not lock datasets, authorise REAL execution, create formal
            # evidence, or bypass gates under any spelling.
            "authorizes_execution",
            "creates_evidence",
            "authorizes_formal_evidence",
            "bypasses_gates",
            "dataset_locked",
            "real_execution_authorized",
        ),
        "data-preparation packet",
    )
    return errors


# --- WP-02f / T-02-11: TaskRun run-record contract (REQ-OBJ-12) ---------------


def _validate_resource_usage(usage: Any) -> list[str]:
    """Resource-usage facts must be a map of named, non-negative numbers.

    Each value is a measured quantity (cpu seconds, peak memory, wall time, ...),
    so it must be a real non-negative number; booleans, negatives and non-numeric
    values are malformed resource facts.
    """
    if usage is None:
        return []
    if not isinstance(usage, dict):
        return ["resource_usage: expected an object of named numeric facts"]
    errors: list[str] = []
    for key, value in usage.items():
        if not (isinstance(key, str) and key.strip()):
            errors.append("resource_usage: every resource key must be a non-blank string")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"resource_usage[{key!r}]: must be a non-negative number")
        elif value < 0:
            errors.append(f"resource_usage[{key!r}]: must be non-negative")
    return errors


# Authority-like flags (and obvious alias spellings) a run record may never assert.
_TASK_RUN_AUTHORITY_FLAGS = (
    "authorizes_execution",
    "authorizes_real_execution",
    "real_execution_authorized",
    "locks_dataset",
    "dataset_locked",
    "creates_formal_evidence",
    "creates_evidence",
    "authorizes_formal_evidence",
    "bypasses_gates",
    "raises_claim_level",
    "raises_claim",
    "claim_level_raised",
    "mutates_workflow_state",
    "workflow_state_mutated",
)


def _validate_task_run_status_facts(run: dict[str, Any], status: str, exit_code: int | None) -> list[str]:
    """Status-dependent exit-code consistency and auditability of a TaskRun.

    A ``completed`` run must exit 0 and carry identity + output/artifact facts; a
    ``failed`` run must not record a success exit and must carry identity +
    error/log facts; an incomplete (``pending`` / ``running`` / ``skipped``) run
    has not exited, so it must not record an exit code and must state an explicit
    reason for the missing execution facts.
    """
    errors: list[str] = []
    has_identity = bool((run.get("tool_identity") or "").strip()) or bool(run.get("environment"))
    has_outputs = bool(run.get("artifact_refs")) or bool(run.get("output_refs"))
    has_error_or_log = bool((run.get("error_summary") or "").strip()) or bool(run.get("log_refs"))
    reason = (run.get("reason") or "").strip()

    if status == "completed":
        if exit_code is None:
            errors.append("exit_code: a completed run must record an explicit exit code 0")
        elif exit_code != 0:
            errors.append(f"exit_code: a completed run must exit 0, not {exit_code}")
        if not has_identity:
            errors.append("result_status 'completed' requires non-empty environment or tool_identity facts to be auditable")
        if not has_outputs:
            errors.append("result_status 'completed' requires at least one output or artifact ref")
    elif status == "failed":
        if exit_code is not None and exit_code == 0:
            errors.append("exit_code: a failed run must not record a success exit code 0")
        if not has_identity:
            errors.append("result_status 'failed' requires non-empty environment or tool_identity facts to be auditable")
        if not has_error_or_log:
            errors.append("result_status 'failed' requires an explicit error_summary or log ref")
    else:  # pending / running / skipped — incomplete records
        if exit_code is not None:
            errors.append(f"exit_code: an incomplete '{status}' run has not exited and must not record an exit code")
        if not reason:
            errors.append(f"result_status '{status}' is incomplete and requires an explicit reason")
    return errors


def validate_task_run(run: dict[str, Any]) -> list[str]:
    """Validate a TaskRun run-record contract (REQ-OBJ-12).

    Identity (``task_run_id`` / ``task_id``) is required and well-formed and the
    ``result_status`` must be one of the bounded :data:`TASK_RUN_RESULT_STATUSES`.
    Log / output / artifact references must be distinct, non-blank facts; the
    ``environment`` / ``parameters`` maps and ``resource_usage`` (named,
    non-negative numbers) must be well-typed; ``exit_code`` is an optional integer
    that must be consistent with ``result_status``; retry lineage (``attempt`` /
    ``retry_of``) must not self-reference and must use consistent attempt
    numbering.  Completed / failed records must be auditable on their own and
    incomplete records must state an explicit reason.  Any truthy authority-like
    flag (under any alias spelling) is rejected — a run record is never authority.
    This validates the contract record only; it never runs, compiles, schedules,
    or registers anything.
    """
    errors = validate_required_fields(run, ["schema_version", "task_run_id", "task_id", "result_status"])
    errors += common.validate_identifier(run.get("task_run_id", ""), "task_run_id")
    errors += common.validate_identifier(run.get("task_id", ""), "task_id")

    status = run.get("result_status")
    if status not in TASK_RUN_RESULT_STATUSES:
        errors.append(f"result_status: must be one of {', '.join(TASK_RUN_RESULT_STATUSES)}")

    # Reference lists must hold distinct, non-blank facts (empty is allowed at the
    # shape level; status-specific auditability decides when refs are required).
    errors += _string_list_errors(run.get("artifact_refs"), "artifact_refs", require_unique=True)
    for list_field in ("output_refs", "log_refs"):
        if run.get(list_field) is not None:
            errors += _string_list_errors(run.get(list_field), list_field, require_unique=True)

    # A reference identifies one fact and may appear in exactly one ref list: the
    # same id must not be claimed as both (e.g.) an artifact and a log. Enforce
    # non-blank uniqueness globally across all three ref lists, not just per-list.
    seen_refs: set[str] = set()
    for list_field in ("artifact_refs", "output_refs", "log_refs"):
        value = run.get(list_field)
        if not isinstance(value, list):
            continue
        for item in value:
            if not (isinstance(item, str) and item.strip()):
                continue
            if item in seen_refs:
                errors.append(f"{list_field}: ref {item!r} is already declared in another ref list (refs must be globally unique)")
            else:
                seen_refs.add(item)

    for map_field in ("environment", "parameters"):
        value = run.get(map_field)
        if value is not None and not isinstance(value, dict):
            errors.append(f"{map_field}: expected an object of recorded facts")

    errors += _validate_resource_usage(run.get("resource_usage"))

    # Exit code: optional integer, never a bool; a malformed value is dropped so it
    # does not spawn a spurious status/exit consistency error too.
    exit_code = run.get("exit_code")
    if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
        errors.append("exit_code: must be an integer or null")
        exit_code = None

    # Retry lineage: positive attempt numbering, no self-reference, consistency.
    attempt = run.get("attempt", 1)
    attempt_ok = isinstance(attempt, int) and not isinstance(attempt, bool)
    if not attempt_ok or attempt < 1:
        errors.append("attempt: must be a positive integer (attempts start at 1)")
    retry_of = run.get("retry_of", "")
    if retry_of:
        if not (isinstance(retry_of, str) and retry_of.strip()):
            errors.append("retry_of: must be the non-blank id of the prior run")
        elif retry_of == run.get("task_run_id"):
            errors.append("retry_of: a run may not be a retry of itself")
        if attempt_ok and attempt < 2:
            errors.append("retry_of: a retry must record attempt >= 2")
    elif attempt_ok and attempt > 1:
        errors.append("attempt: attempt > 1 must reference the prior run via retry_of")

    if status in TASK_RUN_RESULT_STATUSES:
        errors += _validate_task_run_status_facts(run, status, exit_code)

    errors += _reject_truthy_authority_flags(run, _TASK_RUN_AUTHORITY_FLAGS, "task run")
    return errors


# --- WP-02g / T-02-13..14: QCReport & EvidenceItem contract validators ---------


def _qc_check_reason(check: dict[str, Any]) -> str:
    """The recorded reason of a QC check (``reason`` or the engine's ``detail``)."""
    return str(check.get("reason", check.get("detail", "")) or "").strip()


def validate_qc_report(report: dict[str, Any]) -> list[str]:
    """Validate a QCReport four-layer fact record (REQ-OBJ-14).

    Identity (``qc_report_id``) is required and well-formed and ``overall_status``
    must be one of the bounded :data:`QC_OVERALL_STATUSES`.  ``checks`` must be a
    non-empty list of structured check facts — never a bare boolean: every check
    is an object carrying a ``layer`` (:data:`QC_CHECK_LAYERS`) and a ``status``
    (:data:`QC_CHECK_STATUSES`), a failing or warning check must record an explicit
    reason (``reason`` or the engine's ``detail``), and any present check id must be
    unique.  The overall status may not contradict the recorded checks (any fail ->
    ``fail``; a warn with no fail -> ``pass_with_warnings``; otherwise ``pass``).
    A QC report records facts only: any truthy authority-like flag — creating
    evidence, raising a claim level, or authorising export/publishing — is
    rejected.  This validates the contract record only; it never runs QC.
    """
    errors = validate_required_fields(report, ["schema_version", "qc_report_id", "overall_status", "checks"])
    errors += common.validate_identifier(report.get("qc_report_id", ""), "qc_report_id")

    overall = report.get("overall_status")
    if overall is not None and overall not in QC_OVERALL_STATUSES:
        errors.append(f"overall_status: must be one of {', '.join(QC_OVERALL_STATUSES)}")

    checks = report.get("checks")
    # A QC report is structured findings, never a bare boolean verdict.
    if isinstance(checks, bool) or not isinstance(checks, list):
        return errors + ["checks: a QC report must record a list of structured check facts, not a bare boolean"]

    seen_ids: set[str] = set()
    saw_fail = False
    saw_warn = False
    for idx, check in enumerate(checks):
        if isinstance(check, bool) or not isinstance(check, dict):
            errors.append(f"checks[{idx}]: each check must be a structured fact object, not a bare boolean")
            continue
        if check.get("layer") not in QC_CHECK_LAYERS:
            errors.append(f"checks[{idx}].layer: must be one of {', '.join(QC_CHECK_LAYERS)}")
        status = check.get("status")
        if status not in QC_CHECK_STATUSES:
            errors.append(f"checks[{idx}].status: must be one of {', '.join(QC_CHECK_STATUSES)}")
        else:
            saw_fail = saw_fail or status == "fail"
            saw_warn = saw_warn or status == "warn"
            if status in ("fail", "warn") and not _qc_check_reason(check):
                errors.append(f"checks[{idx}]: a {status} check must record an explicit reason (a QC finding is never a bare flag)")
        check_id = str(check.get("check_id", check.get("id", "")) or "").strip()
        if check_id:
            if check_id in seen_ids:
                errors.append(f"checks[{idx}]: duplicate check id {check_id!r} — check ids must be unique")
            else:
                seen_ids.add(check_id)

    # The overall status must agree with the recorded checks (no contradiction).
    if overall in QC_OVERALL_STATUSES:
        if saw_fail and overall != "fail":
            errors.append(f"overall_status {overall!r} contradicts a failing check; a report with any fail is 'fail'")
        elif not saw_fail and saw_warn and overall != "pass_with_warnings":
            errors.append(f"overall_status {overall!r} contradicts a warning check; a report with a warn (and no fail) is 'pass_with_warnings'")
        elif not saw_fail and not saw_warn and overall != "pass":
            errors.append(f"overall_status {overall!r} contradicts all-passing checks; a report with no warn/fail is 'pass'")

    errors += _reject_truthy_authority_flags(
        report,
        (
            "creates_evidence",
            "creates_formal_evidence",
            "raises_claim_level",
            "claim_level_raised",
            "authorizes_export",
            "authorizes_publishing",
            "publishes",
            "bypasses_gates",
        ),
        "QC report",
    )
    return errors


def validate_evidence_item(item: dict[str, Any]) -> list[str]:
    """Validate an EvidenceItem evidence-fact record (REQ-OBJ-15).

    Identity (``evidence_item_id`` / ``artifact_id``) must be present and
    well-formed.  Lineage is mandatory: an evidence record must bind non-empty
    ``subquestion_ids`` / ``source_dataset_ids`` / ``source_task_run_ids`` (each a
    list of distinct, non-blank ids).  ``observation`` and ``evidence_type`` must be
    non-blank, ``allowed_claim_level`` must be a valid :data:`CLAIM_LEVELS` value,
    and ``supports_or_opposes`` must record an explicit :data:`EVIDENCE_DIRECTIONS`
    direction.  Formal evidence must be QC-passed (``qc_status`` in
    :data:`QC_PASSED_OVERALL_STATUSES`); ``effect_summary`` / ``uncertainty`` /
    ``scope`` must be structured fact objects.  Single-dataset evidence may not
    claim independent replication and must keep its limitations visible.  External
    validation may only be asserted with recorded ``external_validation_refs``, and
    any truthy authority-like flag (raising a claim level, bypassing QC, creating a
    Claim, or authorising export/publishing) is rejected — an EvidenceItem never
    raises a claim, bypasses QC, creates a Claim, or publishes.  This validates the
    contract record only; it never changes evidence admission or claim synthesis.
    """
    errors = validate_required_fields(
        item,
        [
            "schema_version",
            "evidence_item_id",
            "artifact_id",
            "subquestion_ids",
            "source_dataset_ids",
            "source_task_run_ids",
            "observation",
            "evidence_type",
            "qc_status",
            "allowed_claim_level",
        ],
    )
    errors += common.validate_identifier(item.get("evidence_item_id", ""), "evidence_item_id")
    errors += common.validate_identifier(item.get("artifact_id", ""), "artifact_id")

    # Lineage: evidence must bind a sub-question, a dataset and a task run.
    for list_field in ("subquestion_ids", "source_dataset_ids", "source_task_run_ids"):
        if not _has_nonblank_entry(item.get(list_field)):
            errors.append(f"{list_field}: evidence must record non-empty lineage to its {list_field}")
        elif item.get(list_field) is not None:
            errors += _string_list_errors(item.get(list_field), list_field, require_unique=True)

    if not str(item.get("observation", "") or "").strip():
        errors.append("observation: evidence must record a non-blank observation")
    if not str(item.get("evidence_type", "") or "").strip():
        errors.append("evidence_type: evidence must record a non-blank evidence type")

    if item.get("allowed_claim_level") not in CLAIM_LEVELS:
        errors.append(f"allowed_claim_level: must be one of {', '.join(CLAIM_LEVELS)}")

    if item.get("supports_or_opposes") not in EVIDENCE_DIRECTIONS:
        errors.append(f"supports_or_opposes: must be one of {', '.join(EVIDENCE_DIRECTIONS)} (an explicit support direction is required)")

    # Formal evidence must be QC-passed: a non-passing QC status is not evidence.
    qc_status = item.get("qc_status")
    if qc_status not in QC_PASSED_OVERALL_STATUSES:
        errors.append(f"qc_status: formal evidence requires a QC-passed status ({', '.join(QC_PASSED_OVERALL_STATUSES)}), not {qc_status!r}")

    for map_field in ("effect_summary", "uncertainty", "scope"):
        value = item.get(map_field)
        if value is not None and not isinstance(value, dict):
            errors.append(f"{map_field}: expected an object of recorded facts")

    if item.get("limitations") is not None:
        errors += _string_list_errors(item.get("limitations"), "limitations")

    replication = item.get("replication_status")
    if replication is not None and replication not in EVIDENCE_REPLICATION_STATUSES:
        errors.append(f"replication_status: must be one of {', '.join(EVIDENCE_REPLICATION_STATUSES)}")
    datasets = item.get("source_dataset_ids")
    single_dataset = isinstance(datasets, list) and len({d for d in datasets if isinstance(d, str) and d.strip()}) == 1
    if single_dataset:
        if replication in EVIDENCE_REPLICATED_STATUSES:
            errors.append(f"replication_status {replication!r}: single-dataset evidence may not claim independent replication by default")
        if not _has_nonblank_entry(item.get("limitations")):
            errors.append("limitations: single-dataset evidence must keep its limitations visible (e.g. not independently replicated)")

    # External validation is a recorded fact, not a self-assertion.
    if item.get("externally_validated") and not _has_nonblank_entry(item.get("external_validation_refs")):
        errors.append("externally_validated: a true external-validation flag requires recorded external_validation_refs")

    errors += _reject_truthy_authority_flags(
        item,
        (
            "raises_claim_level",
            "claim_level_raised",
            "bypasses_qc",
            "bypasses_gates",
            "creates_claim",
            "creates_formal_evidence",
            "authorizes_export",
            "authorizes_publishing",
            "publishes",
        ),
        "evidence item",
    )
    return errors
