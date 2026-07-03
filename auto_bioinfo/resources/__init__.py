"""Local/offline resource-closure stage contracts (WP-08 / WP-09 / WP-10, phases 5-7).

This package holds the *local, deterministic, offline* command contracts for the
resource-closure lane: real resource *discovery & search audit* (WP-08),
resource *verification & metadata factualisation* (WP-09), and *data feasibility
assessment & DatasetManifest lock* (WP-10) — turning a frozen
:class:`~auto_bioinfo.core.schemas.EvidencePlan` into audited candidates, verified
profiles, feasibility reports and, finally, a locked
:class:`~auto_bioinfo.core.schemas.DatasetManifest` — **before** any real search,
data acquisition, approval grant, event emission, persistence, or pipeline
transition.

Every module mirrors the :mod:`auto_bioinfo.intake` / :mod:`auto_bioinfo.planning`
contract style: pure and total over explicit in-memory inputs, no I/O of any kind,
no wall-clock read (produced drafts carry an empty ``created_at`` so byte-identical
inputs yield byte-identical output), bounded status/reason-code vocabularies, and
results that are inert reviewable data — never authoritative, never persisted,
never a grant to execute.  The only "tool" access is through the offline replay
adapters in :mod:`auto_bioinfo.adapters.offline_search`; no real network / API /
GEO / PubMed call is ever made.
"""

from .discovery import (
    RankingProposal,
    SearchQuery,
    SearchQueryResult,
    SearchRun,
    SearchStopDecision,
    build_search_query,
    decide_stop,
    dedupe_candidates,
    normalize_candidate,
    propose_ranking,
    run_search,
)
from .feasibility import (
    FEASIBILITY_RULES,
    Finding,
    LockedDatasetManifest,
    ManifestLockError,
    SampleManifest,
    assess_feasibility,
    build_approval_package,
    build_coverage_matrix,
    build_dataset_manifest,
    build_sample_manifest,
    classify_design,
    decide_terminal_path,
    evaluate_rules,
    register_file_checksums,
    suitability_score,
    validate_dataset_manifest_lock,
    verify_file_checksums,
)
from .search_policy import NetworkAccessDecision, NetworkAccessPolicy
from .verification import (
    AnnotationSourceProfile,
    PaperProfile,
    RegistryRecord,
    VerificationRegistry,
    VerificationResult,
    apply_human_correction,
    classify_license,
    dataset_completeness,
    parse_dataset_metadata,
    verify_candidate,
    verify_paper_dataset_relation,
)

__all__ = [
    "FEASIBILITY_RULES",
    "AnnotationSourceProfile",
    "Finding",
    "LockedDatasetManifest",
    "ManifestLockError",
    "NetworkAccessDecision",
    "NetworkAccessPolicy",
    "PaperProfile",
    "RankingProposal",
    "RegistryRecord",
    "SampleManifest",
    "SearchQuery",
    "SearchQueryResult",
    "SearchRun",
    "SearchStopDecision",
    "VerificationRegistry",
    "VerificationResult",
    "apply_human_correction",
    "assess_feasibility",
    "build_approval_package",
    "build_coverage_matrix",
    "build_dataset_manifest",
    "build_sample_manifest",
    "build_search_query",
    "classify_design",
    "classify_license",
    "dataset_completeness",
    "decide_stop",
    "decide_terminal_path",
    "dedupe_candidates",
    "evaluate_rules",
    "normalize_candidate",
    "parse_dataset_metadata",
    "propose_ranking",
    "register_file_checksums",
    "run_search",
    "suitability_score",
    "validate_dataset_manifest_lock",
    "verify_candidate",
    "verify_file_checksums",
    "verify_paper_dataset_relation",
]
