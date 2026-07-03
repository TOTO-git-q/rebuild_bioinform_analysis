"""WP-26 — a deterministic requirement-coverage matrix.

This module is the machine-readable answer to WP-26 T-26-13: it maps WP / task
IDs to the concrete route stage, module, or test that covers them, and — just as
importantly — lists what is *not* covered by the offline capstone routes as
explicit, honest gaps (never a silent "N/A").

It is pure data + a couple of pure helpers: no clock, no I/O, deterministic.
The acceptance test suite (``tests/test_wp26_*.py``) asserts against it so the
matrix can never drift from what the code actually does.
"""

from __future__ import annotations

from typing import Any

STATUS_COVERED = "covered"
STATUS_PARTIAL = "partial"
STATUS_GAP = "gap"
COVERAGE_STATUSES = (STATUS_COVERED, STATUS_PARTIAL, STATUS_GAP)

SCHEMA_VERSION = "auto_bioinfo.requirement_coverage/0.1"


# Each entry: (wp_id, task_or_req_id, requirement summary, status, covered_by).
# ``covered_by`` names the route stage / lane module / test that provides the
# evidence.  A GAP entry documents a deliberately out-of-scope item with the
# reason it is a gap in the offline capstone.
_ENTRIES: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    # ---- WP-16 : first real bulk RNA-seq route -------------------------------
    (
        "WP-16",
        "T-16-01",
        "Fixed, swappable bulk acceptance dataset (not hard-coded)",
        STATUS_COVERED,
        ("auto_bioinfo/fixtures/bulk_rnaseq_route/dataset_card.json", "routes.glue.load_route_dataset", "tests/test_wp16_bulk_route.py"),
    ),
    (
        "WP-16",
        "T-16-02",
        "Bulk file adapter: counts/expression + sample metadata",
        STATUS_COVERED,
        ("methods.bulk_deg", "routes.bulk_rnaseq.run_analysis_chain", "tests/test_wp16_bulk_route.py"),
    ),
    (
        "WP-16",
        "T-16-05",
        "bulk_deg runner with params sourced from the method contract",
        STATUS_COVERED,
        ("methods.bulk_deg.BulkDegMethod.run", "methods.contract_catalog", "tests/test_wp16_bulk_route.py"),
    ),
    (
        "WP-16",
        "T-16-06",
        "Standardised DEG table (effect, p, adjusted p, flags), stable ordering",
        STATUS_COVERED,
        ("methods.bulk_deg", "routes.glue.parse_deg_rows", "tests/test_wp16_bulk_route.py"),
    ),
    (
        "WP-16",
        "T-16-12",
        "Real run registers TaskRun + Artifact + run summary; no unregistered files",
        STATUS_COVERED,
        ("execution.fake_executor.execute_task", "workflow.artifact_registry.ArtifactRegistry", "tests/test_wp16_bulk_route.py"),
    ),
    (
        "WP-16",
        "T-16-13",
        "Negative routes: insufficient samples / group conflict / incompatible matrix terminate",
        STATUS_COVERED,
        ("routes.bulk_rnaseq (overrides: limit_group_size, wrong_modality)", "tests/test_wp26_adversarial.py"),
    ),
    (
        "WP-16",
        "T-16-07",
        "Basic plot generation referencing the standard result table only",
        STATUS_GAP,
        ("no plotting stage in the offline route (charts are out of MVP capstone scope)",),
    ),
    (
        "WP-16",
        "T-16-08",
        "Gene-set / sample-level pathway score route",
        STATUS_GAP,
        ("gene_set_score contract exists in catalog but has no offline runner wired",),
    ),
    (
        "WP-16",
        "T-16-09",
        "Enrichment route with universe/direction/db version",
        STATUS_GAP,
        ("enrichment contract exists in catalog but has no offline runner wired",),
    ),
    (
        "WP-16",
        "T-16-10",
        "Surface/secretome annotation join",
        STATUS_GAP,
        ("surface_secretome_annotation contract exists in catalog but has no offline runner wired",),
    ),
    (
        "WP-16",
        "T-16-14",
        "Performance / resource baseline artifact",
        STATUS_GAP,
        ("resource_usage is recorded on TaskRuns but no benchmark artifact is emitted",),
    ),
    # ---- WP-17 : sc/snRNA donor-level route + cross-dataset consistency ------
    (
        "WP-17",
        "T-17-01",
        "Fixed sc/snRNA acceptance dataset; code depends only on Manifest/Scope",
        STATUS_COVERED,
        ("auto_bioinfo/fixtures/scrna_donor_route/dataset_card.json", "routes.scrna_donor", "tests/test_wp17_scrna_route.py"),
    ),
    (
        "WP-17",
        "T-17-03",
        "Donor/sample/group/cell-type mapping; donor unknown never inferred",
        STATUS_COVERED,
        ("routes.scrna_donor._donor_samples", "routes.glue.pseudobulk_aggregate", "tests/test_wp17_scrna_route.py"),
    ),
    (
        "WP-17",
        "T-17-06",
        "donor x cell_type pseudobulk aggregation with unit verification",
        STATUS_COVERED,
        ("routes.glue.pseudobulk_aggregate", "tests/test_wp17_scrna_route.py"),
    ),
    (
        "WP-17",
        "T-17-08",
        "Donor-level pseudobulk DEG (donor is the statistical unit)",
        STATUS_COVERED,
        ("routes.scrna_donor.run_scrna_donor_route", "methods.contract_catalog scrna_pseudobulk_deg", "tests/test_wp17_scrna_route.py"),
    ),
    (
        "WP-17",
        "T-17-13",
        "Cross-dataset gene/effect-direction concordance + independence check",
        STATUS_COVERED,
        ("routes.glue.cross_dataset_concordance", "routes.scrna_donor.run_cross_dataset_consistency", "tests/test_wp17_scrna_route.py"),
    ),
    (
        "WP-17",
        "T-17-14",
        "Output consistent/conflicting/not-comparable/missing (not only agreeing positives)",
        STATUS_COVERED,
        ("routes.glue.cross_dataset_concordance", "tests/test_wp17_scrna_route.py"),
    ),
    (
        "WP-17",
        "T-17-15",
        "Adversarial: missing donor / imbalance rejected at the expected gate",
        STATUS_COVERED,
        ("routes.scrna_donor (overrides: unknown_donors)", "tests/test_wp26_adversarial.py"),
    ),
    (
        "WP-17",
        "T-17-05",
        "Cell annotation acceptance / controlled reconstruction interface",
        STATUS_GAP,
        ("the fixture ships a single pre-annotated cell type; no annotation-reconstruction stage is wired",),
    ),
    ("WP-17", "T-17-09", "Differential abundance route", STATUS_GAP, ("differential_abundance contract exists in catalog but has no offline runner wired",)),
    # ---- WP-26 : end-to-end acceptance, adversarial, coverage ----------------
    (
        "WP-26",
        "T-26-02",
        "Planning-only scenario (ResearchSpec/SubQuestion/EvidencePlan)",
        STATUS_COVERED,
        ("routes.bulk_rnaseq._run_planning", "tests/test_wp26_acceptance.py"),
    ),
    (
        "WP-26",
        "T-26-03",
        "Real resource discovery, verification, feasibility, lock",
        STATUS_COVERED,
        ("routes.bulk_rnaseq._run_resources", "tests/test_wp26_acceptance.py"),
    ),
    (
        "WP-26",
        "T-26-04",
        "General DAG / queue / worker / artifact / lineage",
        STATUS_COVERED,
        ("routes.bulk_rnaseq.run_analysis_chain", "tests/test_wp26_acceptance.py"),
    ),
    (
        "WP-26",
        "T-26-05",
        "Full bulk closed loop with positive+negative results and limits",
        STATUS_COVERED,
        ("routes.bulk_rnaseq.run_bulk_rnaseq_route", "tests/test_wp16_bulk_route.py"),
    ),
    (
        "WP-26",
        "T-26-06",
        "Full sc/snRNA donor-level closed loop; no-donor negative rejected",
        STATUS_COVERED,
        ("routes.scrna_donor.run_scrna_donor_route", "tests/test_wp17_scrna_route.py", "tests/test_wp26_adversarial.py"),
    ),
    (
        "WP-26",
        "T-26-07",
        "INSUFFICIENT_DATA scenario (no pseudo-claim)",
        STATUS_COVERED,
        ("routes.bulk_rnaseq (feasibility hard gate)", "tests/test_wp26_adversarial.py"),
    ),
    (
        "WP-26",
        "T-26-08",
        "METHOD_NOT_APPLICABLE and CONFLICTING_EVIDENCE terminals",
        STATUS_COVERED,
        ("routes.bulk_rnaseq (wrong_modality)", "evidence.claim_synthesis (conflict)", "tests/test_wp26_adversarial.py"),
    ),
    (
        "WP-26",
        "T-26-09",
        "Inject scope drift / RNA->secretion / correlation->causation / omitted negatives",
        STATUS_COVERED,
        ("evidence.question_alignment.detect_overclaims", "reporting.claim_lint", "tests/test_wp26_adversarial.py"),
    ),
    (
        "WP-26",
        "T-26-10",
        "Duplicate messages / worker crash / checksum mismatch (no duplicate formal artifact/claim)",
        STATUS_PARTIAL,
        (
            "execution.scheduler idempotency + resume idempotency test",
            "tests/test_wp26_adversarial.py",
            "gap: worker-crash recovery is covered by WP-25 tests, not re-driven through the route",
        ),
    ),
    (
        "WP-26",
        "T-26-11",
        "Clean-room reproduction bundle compared to original",
        STATUS_COVERED,
        ("reproduction.repro_bundle.build_bundle", "reproduction.clean_rerun.compare_results", "tests/test_wp26_acceptance.py"),
    ),
    (
        "WP-26",
        "T-26-12",
        "Reverse trace from final claim to OriginalRequest/data/params/run",
        STATUS_COVERED,
        ("reporting.trace_index.build_trace_index", "tests/test_wp26_acceptance.py"),
    ),
    (
        "WP-26",
        "T-26-13",
        "Requirement-coverage matrix + gaps (no unjustified N/A on a MUST)",
        STATUS_COVERED,
        ("routes.requirement_coverage.build_requirement_coverage_matrix", "tests/test_wp26_coverage_matrix.py"),
    ),
    (
        "WP-26",
        "T-26-14",
        "Explicit gap/limitation/backlog report (failures not hidden)",
        STATUS_COVERED,
        ("routes.requirement_coverage.coverage_gaps", "tests/test_wp26_coverage_matrix.py"),
    ),
    # ---- Design-principle level requirements exercised by the routes ---------
    (
        "R3.8",
        "conservative-failure",
        "Every terminal is a recorded legal stop, never a fabricated result",
        STATUS_COVERED,
        ("routes.route_run.TERMINAL_STATUSES", "tests/test_wp26_adversarial.py"),
    ),
    (
        "R3.7",
        "traceability-first",
        "Claim -> evidence -> artifact -> dataset chain is complete or blocking",
        STATUS_COVERED,
        ("reporting.trace_index", "evidence.question_alignment", "tests/test_wp26_acceptance.py"),
    ),
    (
        "R3.6",
        "evidence-before-story",
        "Only QC-passed, admitted evidence becomes a claim; ceiling never exceeded",
        STATUS_COVERED,
        ("evidence.admission", "evidence.claim_synthesis", "tests/test_wp26_adversarial.py"),
    ),
    (
        "CONSTITUTION",
        "offline-deterministic",
        "Pure/offline/deterministic; produced records carry empty created_at",
        STATUS_COVERED,
        ("routes.route_run.RouteRun", "tests/test_wp16_bulk_route.py", "tests/test_wp17_scrna_route.py"),
    ),
    (
        "PR-46",
        "offline-tool-layer",
        "Resource-discovery tool-selection reuses offline public-bio query planners (deny-by-default)",
        STATUS_COVERED,
        ("adapters.public_bio_tools.PublicBioToolAdapter", "routes.glue.select_discovery_tool_plan", "tests/test_wp16_bulk_route.py"),
    ),
    (
        "PR-46",
        "offline-capability-gate",
        "Resource-discovery preflight reuses the fail-closed capability registry (materialization denied)",
        STATUS_COVERED,
        ("adapters.capability_registry.resolve_decision", "routes.glue.capability_gate", "tests/test_wp26_adversarial.py"),
    ),
)


# The offline glue bridges the routes rely on, documented so the seam is auditable
# (each is a thin deterministic adapter, never an edit to a lane module).
_BRIDGES: tuple[dict[str, str], ...] = (
    {
        "bridge": "routes.glue.modality_token",
        "seam": "verification free-text modality ('bulk RNA-seq') -> method-lane controlled token ('bulk_expression_matrix')",
    },
    {"bridge": "routes.glue.build_recorded_dataset_adapter", "seam": "resources.discovery.run_search needs a recorded adapter keyed by the exact built query"},
    {
        "bridge": "routes.glue.build_verification_registry",
        "seam": "resources.verification.verify_candidate needs a recorded registry record for the fixture dataset",
    },
    {
        "bridge": "routes.glue.compat_profile",
        "seam": "verification DatasetProfile -> compatibility._extract_facts controlled shape (modality/unit/group_sizes/present_metadata)",
    },
    {"bridge": "routes.glue.qc_contract + qc_bundle", "seam": "coarse contract required_qc layer names -> concrete WP-18 rule ids + read-only QC bundle"},
    {"bridge": "routes.glue.parse_deg_rows", "seam": "bulk_deg wide DEG table columns -> evidence.admission result_table rows (gene/log2fc/fdr/significant)"},
    {
        "bridge": "routes.bulk_rnaseq._outcome_for",
        "seam": "real deterministic bulk_deg output -> execution.fake_executor RecordedOutcome (offline replay of a recorded result)",
    },
    {
        "bridge": "routes.glue.pseudobulk_aggregate",
        "seam": "WP-17: cell x gene matrix -> donor-level pseudobulk (cell -> donor statistical unit) before any DEG",
    },
    {
        "bridge": "routes.glue.cross_dataset_concordance",
        "seam": "WP-17: two independent donor-level DEG tables -> per-gene consistent/conflicting/not-comparable/missing",
    },
    {
        "bridge": "routes.glue.select_discovery_tool_plan",
        "seam": "resource discovery tool-selection -> adapters.public_bio_tools offline query planner (deny-by-default, never retrieves)",
    },
    {
        "bridge": "routes.glue.capability_gate",
        "seam": "resource-discovery preflight -> adapters.capability_registry fail-closed grant decisions (materialization denied, no executable grants)",
    },
)


def build_requirement_coverage_matrix() -> dict[str, Any]:
    """Return the deterministic requirement-coverage matrix as a plain dict."""
    entries = [
        {
            "wp_id": wp,
            "task_id": task,
            "requirement": req,
            "status": status,
            "covered_by": list(covered_by),
        }
        for (wp, task, req, status, covered_by) in _ENTRIES
    ]
    summary = {
        "total": len(entries),
        "covered": sum(1 for e in entries if e["status"] == STATUS_COVERED),
        "partial": sum(1 for e in entries if e["status"] == STATUS_PARTIAL),
        "gap": sum(1 for e in entries if e["status"] == STATUS_GAP),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": "",
        "entries": entries,
        "bridges": [dict(b) for b in _BRIDGES],
        "gaps": [f"{e['wp_id']} {e['task_id']}: {e['requirement']}" for e in entries if e["status"] == STATUS_GAP],
        "partials": [f"{e['wp_id']} {e['task_id']}: {e['requirement']}" for e in entries if e["status"] == STATUS_PARTIAL],
        "summary": summary,
    }


def coverage_gaps() -> list[str]:
    """The explicit, honest gap list (WP-26 T-26-14)."""
    return build_requirement_coverage_matrix()["gaps"]


def coverage_for(wp_id: str) -> list[dict[str, Any]]:
    """All matrix entries for one WP id."""
    return [e for e in build_requirement_coverage_matrix()["entries"] if e["wp_id"] == wp_id]


__all__ = [
    "build_requirement_coverage_matrix",
    "coverage_gaps",
    "coverage_for",
    "SCHEMA_VERSION",
    "STATUS_COVERED",
    "STATUS_PARTIAL",
    "STATUS_GAP",
    "COVERAGE_STATUSES",
]
