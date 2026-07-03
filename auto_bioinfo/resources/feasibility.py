"""Local deterministic data-feasibility assessment + DatasetManifest lock (WP-10 / T-10-01..15).

Separates *"the resource exists"* (WP-09) from *"the data can answer the
sub-question"* (this stage), and freezes the formal analysis input as a locked
:class:`~auto_bioinfo.core.schemas.DatasetManifest`.  All offline, deterministic,
inert — no network, no clock, no persistence, no event.

What the plan requires, realised offline:

- **Rule registry** (T-10-01): every feasibility rule carries an id, a version, a
  severity and a rationale, and is scoped to *general* / *design* / *bulk* /
  *sc-snRNA* data (:data:`FEASIBILITY_RULES`).
- **Design / bulk / sc checks** (T-10-02/03/04): comparison groups, independent
  individuals, tissue match, confounders; bulk matrix / grouping / covariates /
  platform / id-mapping; sc/sn donor / pseudobulk / per-group donor / cell
  annotation / quality — a missing donor never masquerades as a biological
  replicate.
- **File pre-check** (T-10-05): file accessibility / size / format — metadata
  existence is *not* data availability.
- **Suitability score** (T-10-06): a soft evidence-requirement match score that
  never overrides a hard-failed rule.
- **Report** (T-10-07): a :class:`~auto_bioinfo.core.schemas.DatasetFeasibilityReport`
  with an ACCEPT / CONDITIONAL / REJECT / NEED_MORE_INFORMATION verdict (mapped to
  the frozen :data:`~auto_bioinfo.core.schemas.FEASIBILITY_DECISIONS`), a mandatory
  reason and the affected sub-question.
- **Preconditions + coverage** (T-10-08/09): a conditional verdict's preconditions;
  a cross-dataset coverage matrix so every sub-question has a data path or a gap.
- **Checksums + manifests** (T-10-10/11/12): file checksum registration with a
  hard mismatch stop; a :class:`SampleManifest` with per-exclusion reasons; a
  locked :class:`~auto_bioinfo.core.schemas.DatasetManifest`.
- **Lock + supersede + terminal** (T-10-13/14/15): an approval package projection;
  a locked manifest that refuses in-place update and supersedes to a new version;
  and explicit ``INSUFFICIENT_DATA`` / ``NEED_MORE_INFORMATION`` terminal paths.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core import common
from ..core.ids import hash_payload, make_stable_id
from ..core.schemas import (
    CANONICAL_SCHEMA_VERSION,
    DatasetFeasibilityReport,
    DatasetManifest,
)
from ..core.validation import validate_dataset_feasibility_report

# --- Verdict aliases: the plan's names <-> the frozen FEASIBILITY_DECISIONS ---
ACCEPT = "usable"
CONDITIONAL = "conditionally_usable"
REJECT = "not_usable"
NEED_MORE_INFORMATION = "insufficient"
# The plan-facing spelling, kept as a stable alias vocabulary for callers.
VERDICT_ALIASES = {
    "ACCEPT": ACCEPT,
    "CONDITIONAL": CONDITIONAL,
    "REJECT": REJECT,
    "NEED_MORE_INFORMATION": NEED_MORE_INFORMATION,
}

# --- Bounded finding + severity vocabularies ---------------------------------
FINDING_PASS = "pass"
FINDING_FAIL = "fail"
FINDING_WARN = "warn"
FINDING_NEED_INFO = "need_info"
FINDING_NOT_APPLICABLE = "not_applicable"
FINDING_STATUSES = (FINDING_PASS, FINDING_FAIL, FINDING_WARN, FINDING_NEED_INFO, FINDING_NOT_APPLICABLE)

SEVERITY_HARD = "hard"  # a hard fail blocks ACCEPT and forces REJECT
SEVERITY_SOFT = "soft"  # a soft fail downgrades to CONDITIONAL / lowers the ceiling
SEVERITIES = (SEVERITY_HARD, SEVERITY_SOFT)

# --- Data design classes (T-10-01) -------------------------------------------
DESIGN_BULK = "bulk"
DESIGN_SINGLE_CELL = "single_cell"
DESIGN_OTHER = "other"

_SINGLE_CELL_TOKENS = ("sc", "scrna", "sc-rna", "single-cell", "single_cell", "snrna", "sn-rna", "single-nucleus", "single_nucleus")
_BULK_TOKENS = ("bulk", "bulk-rna", "bulk_rna", "rna-seq", "rnaseq", "microarray", "array")

# The conservative claim ceiling a conditional / insufficient verdict imposes.
_CONDITIONAL_CEILING = "association"
_INSUFFICIENT_CEILING = "descriptive"


def classify_design(profile: Mapping[str, Any]) -> str:
    """Classify the dataset design from its modality string (bulk / sc / other)."""
    modality = str(profile.get("modality", "") or "").strip().lower()
    if any(tok in modality for tok in _SINGLE_CELL_TOKENS):
        return DESIGN_SINGLE_CELL
    if any(tok in modality for tok in _BULK_TOKENS):
        return DESIGN_BULK
    return DESIGN_OTHER


@dataclass(frozen=True)
class FeasibilityRule:
    """A registry entry: a scoped, versioned, severity-tagged rule with rationale."""

    rule_id: str
    version: str
    severity: str
    applies_to: str  # "general" | "design" | DESIGN_BULK | DESIGN_SINGLE_CELL
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "version": self.version, "severity": self.severity, "applies_to": self.applies_to, "rationale": self.rationale}


# --- The rule registry (T-10-01): ids, versions, severities, rationale --------
FEASIBILITY_RULES: tuple[FeasibilityRule, ...] = (
    FeasibilityRule("FEAS-GEN-001", "1", SEVERITY_HARD, "design", "a comparison needs at least two defined groups"),
    FeasibilityRule("FEAS-GEN-002", "1", SEVERITY_HARD, "design", "each compared group needs independent individuals/donors"),
    FeasibilityRule("FEAS-GEN-003", "1", SEVERITY_SOFT, "design", "the dataset tissue should match the requested tissue"),
    FeasibilityRule("FEAS-GEN-004", "1", SEVERITY_SOFT, "design", "known confounders (disease/drug/age) should be balanced or recorded"),
    FeasibilityRule("FEAS-FILE-001", "1", SEVERITY_HARD, "general", "at least one analysis file must be actually downloadable, not merely listed"),
    FeasibilityRule("FEAS-BULK-001", "1", SEVERITY_HARD, DESIGN_BULK, "a bulk analysis needs a compatible expression matrix and grouping"),
    FeasibilityRule("FEAS-BULK-002", "1", SEVERITY_SOFT, DESIGN_BULK, "a bulk analysis should record platform and id-mapping for covariate control"),
    FeasibilityRule(
        "FEAS-SC-001", "1", SEVERITY_HARD, DESIGN_SINGLE_CELL, "a sc/snRNA design must have donor ids; without them there is no biological replicate"
    ),
    FeasibilityRule("FEAS-SC-002", "1", SEVERITY_SOFT, DESIGN_SINGLE_CELL, "a sc/snRNA design should record per-group donors, cell annotation and QC fields"),
)
_RULE_BY_ID = {r.rule_id: r for r in FEASIBILITY_RULES}


@dataclass(frozen=True)
class Finding:
    """One rule evaluation result."""

    rule_id: str
    status: str
    severity: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "status": self.status, "severity": self.severity, "message": self.message, "evidence": dict(self.evidence)}


# =============================================================================
# Rule evaluations (each pure over the profile + research spec)
# =============================================================================
def _groups_from_profile(profile: Mapping[str, Any]) -> dict[str, list[str]]:
    grouping = profile.get("grouping")
    groups: dict[str, list[str]] = {}
    if isinstance(grouping, Mapping):
        for label, members in grouping.items():
            if isinstance(members, list):
                groups[str(label)] = [str(m) for m in members]
    if not groups:
        # Fall back to sample.group facts.
        by_group: dict[str, list[str]] = {}
        for s in profile.get("samples", []) or []:
            if isinstance(s, Mapping):
                g = str(s.get("group", "") or "").strip()
                if g:
                    by_group.setdefault(g, []).append(str(s.get("sample_id", "")))
        groups = by_group
    return groups


def _donors_by_group(profile: Mapping[str, Any], groups: Mapping[str, list[str]]) -> dict[str, set[str]]:
    donor_of: dict[str, str] = {}
    for s in profile.get("samples", []) or []:
        if isinstance(s, Mapping):
            donor_of[str(s.get("sample_id", ""))] = str(s.get("donor_id", "") or "unknown")
    out: dict[str, set[str]] = {}
    for g, members in groups.items():
        out[g] = {donor_of.get(m, "unknown") for m in members}
    return out


def evaluate_rules(profile: Mapping[str, Any], research_spec: Mapping[str, Any] | None) -> list[Finding]:
    """Evaluate the applicable rules against a dataset profile deterministically."""
    findings: list[Finding] = []
    design = classify_design(profile)
    groups = _groups_from_profile(profile)
    spec = research_spec or {}

    # FEAS-GEN-001: >= two defined groups.
    if len(groups) >= 2:
        findings.append(Finding("FEAS-GEN-001", FINDING_PASS, SEVERITY_HARD, f"{len(groups)} comparison groups defined", {"groups": sorted(groups)}))
    else:
        findings.append(
            Finding("FEAS-GEN-001", FINDING_FAIL, SEVERITY_HARD, "fewer than two comparison groups; no comparison is possible", {"groups": sorted(groups)})
        )

    # FEAS-GEN-002: independent individuals per group.
    donors = _donors_by_group(profile, groups)
    unknown_donor = any("unknown" in d for d in donors.values())
    min_donors = min((len(d - {"unknown"}) for d in donors.values()), default=0)
    if len(groups) >= 2 and not unknown_donor and min_donors >= 2:
        findings.append(Finding("FEAS-GEN-002", FINDING_PASS, SEVERITY_HARD, "each group has >= 2 independent donors", {"min_donors_per_group": min_donors}))
    elif unknown_donor:
        findings.append(
            Finding(
                "FEAS-GEN-002",
                FINDING_FAIL,
                SEVERITY_HARD,
                "some samples have unknown donor; independent replication cannot be asserted",
                {"unknown_donor": True},
            )
        )
    else:
        findings.append(
            Finding("FEAS-GEN-002", FINDING_FAIL, SEVERITY_HARD, "fewer than two independent donors in a group", {"min_donors_per_group": min_donors})
        )

    # FEAS-GEN-003: tissue match (soft).
    requested_tissue = str(spec.get("tissue", "") or "").strip().lower()
    dataset_tissue = str(profile.get("tissue", "") or "").strip().lower()
    if not requested_tissue:
        findings.append(Finding("FEAS-GEN-003", FINDING_NOT_APPLICABLE, SEVERITY_SOFT, "no requested tissue to match against", {}))
    elif dataset_tissue and dataset_tissue == requested_tissue:
        findings.append(Finding("FEAS-GEN-003", FINDING_PASS, SEVERITY_SOFT, "dataset tissue matches the requested tissue", {"tissue": dataset_tissue}))
    else:
        findings.append(
            Finding(
                "FEAS-GEN-003",
                FINDING_WARN,
                SEVERITY_SOFT,
                f"dataset tissue {dataset_tissue!r} does not match requested {requested_tissue!r}",
                {"requested": requested_tissue, "dataset": dataset_tissue},
            )
        )

    # FEAS-GEN-004: confounder record (soft).
    facts = profile.get("metadata_facts", {}) if isinstance(profile.get("metadata_facts"), Mapping) else {}
    parsed = facts.get("parsed_fields", {}) if isinstance(facts, Mapping) else {}
    confounders_recorded = any(k in parsed for k in ("age", "sex", "batch", "disease", "intervention"))
    findings.append(
        Finding(
            "FEAS-GEN-004",
            FINDING_PASS if confounders_recorded else FINDING_WARN,
            SEVERITY_SOFT,
            "confounder fields recorded" if confounders_recorded else "no confounder fields recorded; residual confounding possible",
            {"recorded": sorted(k for k in ("age", "sex", "batch", "disease", "intervention") if k in parsed)},
        )
    )

    # FEAS-FILE-001: at least one downloadable file (hard).
    files = profile.get("files", []) or []
    downloadable = [f for f in files if isinstance(f, Mapping) and f.get("downloadable")]
    if downloadable:
        findings.append(Finding("FEAS-FILE-001", FINDING_PASS, SEVERITY_HARD, f"{len(downloadable)} downloadable file(s)", {"downloadable": len(downloadable)}))
    elif files:
        findings.append(
            Finding(
                "FEAS-FILE-001",
                FINDING_NEED_INFO,
                SEVERITY_HARD,
                "files are listed but none is confirmed downloadable; visibility is not availability",
                {"listed": len(files)},
            )
        )
    else:
        findings.append(Finding("FEAS-FILE-001", FINDING_FAIL, SEVERITY_HARD, "no analysis files listed", {}))

    if design == DESIGN_BULK:
        matrix_ok = any(isinstance(f, Mapping) and str(f.get("file_type", "")).lower() in {"counts", "matrix", "expression", "processed_matrix"} for f in files)
        if matrix_ok and len(groups) >= 2:
            findings.append(Finding("FEAS-BULK-001", FINDING_PASS, SEVERITY_HARD, "bulk matrix + grouping present", {}))
        elif not matrix_ok:
            findings.append(Finding("FEAS-BULK-001", FINDING_NEED_INFO, SEVERITY_HARD, "no compatible expression/count matrix file recorded", {}))
        else:
            findings.append(Finding("FEAS-BULK-001", FINDING_FAIL, SEVERITY_HARD, "bulk grouping is insufficient for a differential comparison", {}))
        platform_ok = bool(str(profile.get("platform", "") or "").strip())
        findings.append(
            Finding(
                "FEAS-BULK-002",
                FINDING_PASS if platform_ok else FINDING_WARN,
                SEVERITY_SOFT,
                "platform recorded" if platform_ok else "no platform / id-mapping recorded",
                {"platform": profile.get("platform", "")},
            )
        )

    if design == DESIGN_SINGLE_CELL:
        has_all_donors = bool(profile.get("samples")) and not unknown_donor
        if has_all_donors:
            findings.append(Finding("FEAS-SC-001", FINDING_PASS, SEVERITY_HARD, "sc/snRNA design has donor ids for every sample", {}))
        else:
            findings.append(
                Finding(
                    "FEAS-SC-001",
                    FINDING_FAIL,
                    SEVERITY_HARD,
                    "sc/snRNA design is missing donor ids; cells are not biological replicates",
                    {"unknown_donor": True},
                )
            )
        cell_annotation = "cell_type" in parsed or bool(facts.get("cell_annotation"))
        findings.append(
            Finding(
                "FEAS-SC-002",
                FINDING_PASS if cell_annotation else FINDING_WARN,
                SEVERITY_SOFT,
                "cell annotation / QC recorded" if cell_annotation else "no cell annotation / QC fields recorded",
                {},
            )
        )

    return findings


# =============================================================================
# T-10-06: suitability score (soft; never overrides a hard fail)
# =============================================================================
def suitability_score(profile: Mapping[str, Any], evidence_plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Match the evidence plan's minimum requirements against the profile facts.

    A soft 0..1 score plus the matched / unmet requirement lists.  It is advisory:
    the caller applies it *after* the hard rules, and it can never lift a hard
    failure (T-10-06).
    """
    axes = list((evidence_plan or {}).get("evidence_axes", []) or [])
    min_replication = (evidence_plan or {}).get("minimum_replication", {})
    required = int(min_replication.get("minimum_independent_sources", 1)) if isinstance(min_replication, Mapping) else 1
    groups = _groups_from_profile(profile)
    donors = _donors_by_group(profile, groups)
    min_donors = min((len(d - {"unknown"}) for d in donors.values()), default=0)
    checks: list[tuple[str, bool]] = [
        ("has_evidence_axes", bool(axes)),
        ("has_two_groups", len(groups) >= 2),
        (f"meets_min_replication_{required}", min_donors >= required),
        ("has_downloadable_file", any(isinstance(f, Mapping) and f.get("downloadable") for f in profile.get("files", []) or [])),
    ]
    met = [name for name, ok in checks if ok]
    unmet = [name for name, ok in checks if not ok]
    return {
        "score": round(len(met) / len(checks), 4),
        "met": met,
        "unmet": unmet,
        "authoritative": False,
        "note": "advisory only; cannot override a hard-failed rule",
    }


# =============================================================================
# T-10-07: DatasetFeasibilityReport
# =============================================================================
def assess_feasibility(
    profile: Mapping[str, Any],
    research_spec: Mapping[str, Any] | None,
    evidence_plan: Mapping[str, Any] | None,
    *,
    subquestion_id: str,
) -> dict[str, Any]:
    """Assess whether a dataset can answer a sub-question and return a report dict.

    Aggregates the rule findings into a bounded FEASIBILITY_DECISIONS verdict: any
    hard fail -> REJECT (``not_usable``); a hard ``need_info`` (or missing binding)
    -> NEED_MORE_INFORMATION (``insufficient``); soft warnings with no hard fail ->
    CONDITIONAL (``conditionally_usable``); otherwise ACCEPT (``usable``).  The
    produced report always passes :func:`validate_dataset_feasibility_report`.
    """
    research_spec_id = str((research_spec or {}).get("research_spec_id", "") or profile.get("research_spec_id", "") or "")
    evidence_plan_id = str((evidence_plan or {}).get("evidence_plan_id", "") or "")
    dataset_profile_id = str(profile.get("dataset_profile_id", "") or "")

    findings = evaluate_rules(profile, research_spec)
    findings_dicts = [f.to_dict() for f in findings]
    score = suitability_score(profile, evidence_plan)

    hard_fails = [f for f in findings if f.severity == SEVERITY_HARD and f.status == FINDING_FAIL]
    hard_need_info = [f for f in findings if f.severity == SEVERITY_HARD and f.status == FINDING_NEED_INFO]
    soft_warns = [f for f in findings if f.severity == SEVERITY_SOFT and f.status == FINDING_WARN]
    checked_facts = [f.rule_id for f in findings if f.status in {FINDING_PASS, FINDING_WARN}]

    reasons: list[str] = [f"{f.rule_id}: {f.message}" for f in findings if f.status in {FINDING_FAIL, FINDING_NEED_INFO, FINDING_WARN}]
    missing_facts: list[str] = [f"{f.rule_id}: {f.message}" for f in hard_need_info]
    blocking_gaps: list[str] = [f"{f.rule_id}: {f.message}" for f in hard_fails]

    if hard_fails:
        decision = REJECT
        ceiling = _INSUFFICIENT_CEILING
        if not reasons:
            reasons = ["dataset fails a hard feasibility rule"]
    elif hard_need_info or not evidence_plan_id:
        decision = NEED_MORE_INFORMATION
        ceiling = _INSUFFICIENT_CEILING
        if not evidence_plan_id:
            missing_facts.append("no evidence_plan binding available to judge sufficiency")
        if not missing_facts:
            missing_facts = ["required feasibility facts are missing or unconfirmed"]
        if not reasons:
            reasons = ["insufficient information to accept the dataset"]
    elif soft_warns:
        decision = CONDITIONAL
        ceiling = _CONDITIONAL_CEILING
        if not reasons:
            reasons = ["dataset is usable under recorded conditions"]
    else:
        decision = ACCEPT
        ceiling = None
        reasons = ["all hard feasibility rules pass"] + reasons

    conditional_notes: list[str] = []
    if decision == CONDITIONAL:
        conditional_notes = [f"precondition: address {f.rule_id} — {f.message}" for f in soft_warns]

    report = DatasetFeasibilityReport(
        research_spec_id=research_spec_id or "unknown_research_spec",
        subquestion_id=subquestion_id,
        dataset_profile_id=dataset_profile_id or "unknown_dataset_profile",
        decision=decision,
        evidence_plan_id=evidence_plan_id if decision in (ACCEPT, CONDITIONAL) else "",
        reasons=reasons,
        required_facts_checked=checked_facts if decision in (ACCEPT, CONDITIONAL) else [],
        missing_facts=missing_facts,
        blocking_gaps=blocking_gaps,
        conditional_use_notes=conditional_notes,
        imposed_claim_ceiling=ceiling if ceiling else "descriptive",
        status="draft",
        created_at="",
    ).to_dict()
    report["findings"] = findings_dicts
    report["suitability_score"] = score
    report["design_class"] = classify_design(profile)
    report["preconditions"] = list(conditional_notes)  # T-10-08
    return report


def feasibility_report_errors(report: Mapping[str, Any]) -> list[str]:
    """Convenience: run the core validator on a produced report (self-check)."""
    return validate_dataset_feasibility_report(dict(report))


# =============================================================================
# T-10-09: cross-dataset coverage matrix
# =============================================================================
def build_coverage_matrix(subquestion_ids: list[str], reports: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Every sub-question must have a data path or an explicit gap.

    A sub-question is *covered* when some report for it is usable /
    conditionally_usable.  Combination honesty (T-10-09): a sub-question covered
    only by conditional datasets is flagged ``conditional_only`` so "each dataset
    is fine alone but the whole is weak" stays visible.
    """
    by_sq: dict[str, list[Mapping[str, Any]]] = {sq: [] for sq in subquestion_ids}
    for r in reports:
        sq = str(r.get("subquestion_id", ""))
        if sq in by_sq:
            by_sq[sq].append(r)
    matrix: dict[str, Any] = {}
    gaps: list[dict[str, Any]] = []
    for sq in subquestion_ids:
        usable = [r for r in by_sq[sq] if r.get("decision") == ACCEPT]
        conditional = [r for r in by_sq[sq] if r.get("decision") == CONDITIONAL]
        has_path = bool(usable or conditional)
        entry = {
            "has_data_path": has_path,
            "usable_datasets": [r.get("dataset_profile_id", "") for r in usable],
            "conditional_datasets": [r.get("dataset_profile_id", "") for r in conditional],
            "conditional_only": has_path and not usable,
        }
        if not has_path:
            entry["gap"] = "no usable or conditionally-usable dataset for this sub-question"
            gaps.append({"subquestion_id": sq, "gap_type": "missing", "description": entry["gap"]})
        matrix[sq] = entry
    return {"matrix": matrix, "gaps": gaps, "all_covered": not gaps}


# =============================================================================
# T-10-10: file checksum registration + hard mismatch stop
# =============================================================================
def register_file_checksums(file_contents: Mapping[str, str]) -> dict[str, str]:
    """Register a deterministic content checksum per file (offline).

    ``file_contents`` maps a file name to its recorded content; the returned digest
    is a stable sha-256 hex over that content.  No real file is fetched.
    """
    return {name: hash_payload(content) for name, content in file_contents.items()}


def verify_file_checksums(recorded: Mapping[str, str], recomputed: Mapping[str, str]) -> list[str]:
    """Return errors for any checksum mismatch / missing / extra file (T-10-10).

    A non-empty result means *stop immediately* — the manifest must not lock.
    """
    errors: list[str] = []
    for name, digest in recorded.items():
        actual = recomputed.get(name)
        if actual is None:
            errors.append(f"file {name!r} has no recomputed checksum to verify")
        elif actual != digest:
            errors.append(f"checksum mismatch for {name!r}: recorded {digest} != recomputed {actual}")
    for name in recomputed:
        if name not in recorded:
            errors.append(f"recomputed file {name!r} has no recorded checksum")
    return errors


# =============================================================================
# T-10-11: SampleManifest (lane-local)
# =============================================================================
@dataclass(frozen=True)
class SampleManifest:
    """Per-sample inclusion/exclusion record; every exclusion carries a reason."""

    dataset_profile_id: str
    included_samples: list[dict[str, Any]] = field(default_factory=list)
    excluded_samples: list[dict[str, Any]] = field(default_factory=list)
    covariates: list[str] = field(default_factory=list)
    schema_version: str = CANONICAL_SCHEMA_VERSION
    sample_manifest_id: str = ""
    status: str = "draft"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "dataset_profile_id": self.dataset_profile_id,
            "included_samples": copy.deepcopy(self.included_samples),
            "excluded_samples": copy.deepcopy(self.excluded_samples),
            "covariates": list(self.covariates),
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
        }
        data["sample_manifest_id"] = self.sample_manifest_id or make_stable_id("sample_manifest", {"dataset_profile_id": self.dataset_profile_id})
        return data


def build_sample_manifest(profile: Mapping[str, Any], *, exclusions: Mapping[str, str] | None = None, covariates: list[str] | None = None) -> dict[str, Any]:
    """Build a sample manifest from a profile; every exclusion needs a reason.

    ``exclusions`` maps a ``sample_id`` to its exclusion reason (a rule or a human
    reason).  A sample listed for exclusion without a non-blank reason raises —
    a silent exclusion is never allowed (T-10-11).
    """
    exclusions = exclusions or {}
    for sid, reason in exclusions.items():
        if not str(reason or "").strip():
            raise ValueError(f"excluded sample {sid!r} must carry a non-blank reason")
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for s in profile.get("samples", []) or []:
        if not isinstance(s, Mapping):
            continue
        sid = str(s.get("sample_id", "") or "")
        if sid in exclusions:
            excluded.append({"sample_id": sid, "reason": str(exclusions[sid]), "group": s.get("group", ""), "donor_id": s.get("donor_id", "unknown")})
        else:
            included.append({"sample_id": sid, "group": s.get("group", ""), "donor_id": s.get("donor_id", "unknown")})
    return SampleManifest(
        dataset_profile_id=str(profile.get("dataset_profile_id", "") or ""),
        included_samples=included,
        excluded_samples=excluded,
        covariates=list(covariates or []),
    ).to_dict()


# =============================================================================
# T-10-12/13/14: DatasetManifest build / approval package / lock + supersede
# =============================================================================
CODE_MANIFEST_LOCKED = "MANIFEST_LOCKED"
CODE_MANIFEST_CHECKSUM_MISMATCH = "MANIFEST_CHECKSUM_MISMATCH"
CODE_MANIFEST_MISSING_REFERENCE = "MANIFEST_MISSING_REFERENCE"
CODE_MANIFEST_MALFORMED = "MANIFEST_MALFORMED"


def validate_dataset_manifest_lock(manifest: Mapping[str, Any]) -> list[str]:
    """Lane-local validator for a locked DatasetManifest (see report for consolidation).

    A locked manifest must reference an existing dataset (accession), carry file
    checksums, list at least one sample, bind at least one sub-question, use a
    positive integer version, and be ``locked``.  Every excluded sample keeps a
    reason.  Checksums must be valid sha-256 digests.
    """
    errors = common.validate_identifier(manifest.get("dataset_manifest_id", ""), "dataset_manifest_id")
    errors += common.validate_identifier(manifest.get("dataset_id", ""), "dataset_id")
    if not str(manifest.get("accession", "") or "").strip():
        errors.append("accession: a locked manifest must reference a real accession")
    checksums = manifest.get("file_checksums")
    if not isinstance(checksums, Mapping) or not checksums:
        errors.append("file_checksums: a locked manifest must carry at least one file checksum")
    else:
        for name, digest in checksums.items():
            errors += common.validate_hash(digest, f"file_checksums[{name}]")
    if not manifest.get("samples"):
        errors.append("samples: a locked manifest must list at least one sample")
    if not manifest.get("supports_subquestion_ids"):
        errors.append("supports_subquestion_ids: a locked manifest must bind at least one sub-question")
    version = manifest.get("manifest_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        errors.append("manifest_version: must be a positive integer")
    if manifest.get("locked") is not True:
        errors.append("locked: a formal-input manifest must be locked")
    for s in manifest.get("excluded_samples", []) or []:
        if isinstance(s, Mapping) and not str(s.get("reason", "") or "").strip():
            errors.append(f"excluded sample {s.get('sample_id', '?')!r} is missing a reason")
    return errors


def build_dataset_manifest(
    *,
    profile: Mapping[str, Any],
    sample_manifest: Mapping[str, Any],
    file_checksums: Mapping[str, str],
    supports_subquestion_ids: list[str],
    known_limitations: list[str] | None = None,
    manifest_version: int = 1,
) -> dict[str, Any]:
    """Build a *locked* DatasetManifest from verified, feasible inputs (T-10-12).

    Every referenced object version must be present: a blank dataset id /
    accession, no checksums, no samples, or no bound sub-question raises via the
    lane validator before the manifest is returned locked.
    """
    dataset_id = str(profile.get("dataset_id", "") or "")
    samples = list(sample_manifest.get("included_samples", []) or [])
    excluded = list(sample_manifest.get("excluded_samples", []) or [])
    manifest = DatasetManifest(
        dataset_manifest_id=make_stable_id("dataset_manifest", {"dataset_id": dataset_id, "version": manifest_version, "checksums": dict(file_checksums)}),
        dataset_id=dataset_id,
        accession=str(profile.get("accession", "") or ""),
        source_status=str(profile.get("source_status", "") or profile.get("source_class", "") or ""),
        samples=samples,
        excluded_samples=excluded,
        file_checksums=dict(file_checksums),
        supports_subquestion_ids=list(supports_subquestion_ids),
        known_limitations=list(known_limitations or []),
        manifest_version=manifest_version,
        locked=True,
        status="locked",
        created_at="",
    )
    data = {
        "dataset_manifest_id": manifest.dataset_manifest_id,
        "dataset_id": manifest.dataset_id,
        "accession": manifest.accession,
        "source_status": manifest.source_status,
        "samples": manifest.samples,
        "excluded_samples": manifest.excluded_samples,
        "file_checksums": manifest.file_checksums,
        "supports_subquestion_ids": manifest.supports_subquestion_ids,
        "known_limitations": manifest.known_limitations,
        "manifest_version": manifest.manifest_version,
        "locked": manifest.locked,
        "schema_version": manifest.schema_version,
        "status": manifest.status,
        "created_at": manifest.created_at,
    }
    errors = validate_dataset_manifest_lock(data)
    if errors:
        raise ValueError("cannot lock an invalid manifest: " + "; ".join(errors))
    return data


class ManifestLockError(RuntimeError):
    """Raised when code tries to mutate a locked manifest in place (T-10-14)."""


class LockedDatasetManifest:
    """An immutable wrapper: in-place update fails, supersede creates a new version.

    Holds a locked manifest dict.  :meth:`update` always raises
    :class:`ManifestLockError` (the T-10-14 UPDATE-fails guarantee).
    :meth:`supersede` returns a *new* :class:`LockedDatasetManifest` at the next
    version with a recorded supersede reason; the original is untouched.
    """

    def __init__(self, manifest: Mapping[str, Any]) -> None:
        errors = validate_dataset_manifest_lock(manifest)
        if errors:
            raise ValueError("LockedDatasetManifest requires a valid locked manifest: " + "; ".join(errors))
        self._manifest = copy.deepcopy(dict(manifest))

    @property
    def manifest(self) -> dict[str, Any]:
        return copy.deepcopy(self._manifest)

    @property
    def version(self) -> int:
        return int(self._manifest.get("manifest_version", 1))

    def update(self, *_args: Any, **_kwargs: Any) -> None:
        raise ManifestLockError("a locked DatasetManifest cannot be modified in place; create a new version via supersede()")

    def supersede(self, *, reason: str, changes: Mapping[str, Any] | None = None) -> LockedDatasetManifest:
        if not str(reason or "").strip():
            raise ValueError("superseding a manifest requires a non-blank reason")
        new_body = copy.deepcopy(self._manifest)
        for key, value in (changes or {}).items():
            if key in {"locked", "schema_version"}:
                continue
            new_body[key] = copy.deepcopy(value)
        new_version = self.version + 1
        new_body["manifest_version"] = new_version
        new_body["supersedes"] = self._manifest.get("dataset_manifest_id", "")
        new_body["supersede_reason"] = str(reason)
        new_body["dataset_manifest_id"] = make_stable_id(
            "dataset_manifest", {"dataset_id": new_body.get("dataset_id", ""), "version": new_version, "checksums": new_body.get("file_checksums", {})}
        )
        new_body["locked"] = True
        new_body["status"] = "locked"
        return LockedDatasetManifest(new_body)


def build_approval_package(manifest: Mapping[str, Any], reports: list[Mapping[str, Any]], coverage: Mapping[str, Any]) -> dict[str, Any]:
    """An inert G-D approval projection: inclusions/exclusions, licence, unknowns, coverage (T-10-13)."""
    return {
        "kind": "dataset_manifest_approval_package",
        "dataset_manifest_id": manifest.get("dataset_manifest_id", ""),
        "manifest_version": manifest.get("manifest_version", 1),
        "included_sample_count": len(manifest.get("samples", []) or []),
        "excluded_samples": [{"sample_id": s.get("sample_id", ""), "reason": s.get("reason", "")} for s in manifest.get("excluded_samples", []) or []],
        "known_limitations": list(manifest.get("known_limitations", []) or []),
        "feasibility_verdicts": [
            {"dataset_profile_id": r.get("dataset_profile_id", ""), "subquestion_id": r.get("subquestion_id", ""), "decision": r.get("decision", "")}
            for r in reports
        ],
        "coverage": copy.deepcopy(dict(coverage)),
        "authoritative": False,
        "note": "inert approval projection; approval authority is granted only through the approval lifecycle, never by this object",
    }


# =============================================================================
# T-10-15: explicit terminal / replan paths
# =============================================================================
TERMINAL_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
TERMINAL_NEED_MORE_INFORMATION = "NEED_MORE_INFORMATION"
TERMINAL_STATES = (TERMINAL_INSUFFICIENT_DATA, TERMINAL_NEED_MORE_INFORMATION)


def decide_terminal_path(coverage: Mapping[str, Any], reports: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Decide a legal terminal/replan path when no viable data exists (T-10-15).

    Returns ``None`` when at least one sub-question has a data path (the pipeline
    may continue).  Otherwise returns a terminal decision: ``INSUFFICIENT_DATA``
    when every dataset was rejected, else ``NEED_MORE_INFORMATION`` when the block
    is unresolved information.  This prevents compiling fake tasks over no data.
    """
    if coverage.get("all_covered"):
        return None
    decisions = {str(r.get("decision", "")) for r in reports}
    if decisions and decisions <= {REJECT}:
        state = TERMINAL_INSUFFICIENT_DATA
        message = "every candidate dataset was rejected; ending in an auditable INSUFFICIENT_DATA terminal state"
    else:
        state = TERMINAL_NEED_MORE_INFORMATION
        message = "no sub-question has a usable data path; more information is required before analysis can be compiled"
    return {"terminal_state": state, "message": message, "gaps": list(coverage.get("gaps", [])), "compiles_analysis": False}
