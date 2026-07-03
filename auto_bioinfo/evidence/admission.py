"""EvidenceItem admission gate and evidence registry (WP-19).

Stage 14 of the requirement spec: only an observation that passed the mandated QC
may become a structured :class:`~auto_bioinfo.core.schemas.EvidenceItem`, and every
admitted item must carry full lineage (dataset / task-run / artifact / sub-question
/ method-contract version) and an ``allowed_claim_level`` that is the **lower** of
every applicable ceiling.  A result that did **not** pass QC is never turned into
formal evidence; it is archived as a bounded ``NON_ADMISSIBLE_RESULT`` marker so a
report can never misread it as evidence (T-19-09).  Negative, conflicting and
failed-to-replicate evidence is kept and is **not** hidden by default (T-19-08).

Everything here is pure, offline and deterministic: it reads only its in-memory
fixture inputs, performs no I/O / network / clock read / subprocess, never mutates
its inputs, and every produced record carries an empty ``created_at`` so
byte-identical inputs yield a byte-identical result.  The admission gate reuses the
WP-18 QC decision (or a plain QC report's ``overall_status``) and never re-runs QC;
:func:`auto_bioinfo.core.validation.validate_evidence_item` validates the shape of
every admitted item.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import (
    CANONICAL_SCHEMA_VERSION,
    CLAIM_LEVELS,
    EVIDENCE_REPLICATION_STATUSES,
    EvidenceItem,
)
from ..core.validation import validate_evidence_item

# --- Bounded vocabularies ----------------------------------------------------
# The admission verdict.  Exactly two: an observation is either admitted as formal
# evidence or archived as non-admissible — there is no silent third state.
ADMISSION_DECISIONS = ("admitted", "non_admissible")

# The four-way support classification (T-19-06).  ``inconclusive`` is distinct from
# ``neutral``: a non-significant result under adequate power is neutral, but a
# non-significant result under *inadequate* power is inconclusive (absence of
# evidence is not evidence of absence).  The EvidenceItem schema field
# ``supports_or_opposes`` only admits EVIDENCE_DIRECTIONS, so ``inconclusive`` is
# recorded in the richer ``evidence_relation`` field and mapped to ``neutral`` there.
EVIDENCE_RELATIONS = ("supports", "opposes", "neutral", "inconclusive")
_RELATION_TO_DIRECTION = {"supports": "supports", "opposes": "opposes", "neutral": "neutral", "inconclusive": "neutral"}

# Replication statuses (reuse the shared vocabulary).
REPLICATION_STATUSES = EVIDENCE_REPLICATION_STATUSES

# Why a result was refused formal admission.
NON_ADMISSIBLE_REASONS = (
    "QC_NOT_PASSED",
    "NO_LINEAGE",
    "MISSING_ARTIFACT",
    "POLICY_WARNINGS_NOT_ACCEPTED",
    "MALFORMED_RESULT",
)

# The QC decision each admission branch accepts.  A PASS always admits; a
# PASS_WITH_WARNINGS admits only when the active policy accepts warnings; every
# other decision (RETRY / REPLAN / REJECT / NEED_HUMAN_REVIEW / fail) is refused.
_ADMITTING_DECISIONS = ("PASS", "PASS_WITH_WARNINGS")

# The per-QC-decision claim-level cap (T-19-05).  A clean PASS imposes no QC cap
# (the other ceilings still apply); a PASS_WITH_WARNINGS caps evidence at
# ``association`` because an un-clean run should not underwrite a stronger claim.
_QC_CLAIM_CAP = {"PASS": CLAIM_LEVELS[-1], "PASS_WITH_WARNINGS": "association"}


def _min_level(*levels: str) -> str:
    """The lowest (most conservative) of the given claim levels.

    An unknown level is treated as the floor, so an unrecognised ceiling can only
    lower — never raise — the result.
    """
    indices = [CLAIM_LEVELS.index(level) if level in CLAIM_LEVELS else 0 for level in levels if level]
    return CLAIM_LEVELS[min(indices)] if indices else CLAIM_LEVELS[0]


def qc_decision_of(qc_report: Mapping[str, Any]) -> str:
    """Return the QC decision, from a WP-18 report's ``decision`` or a plain report."""
    decision = qc_report.get("decision")
    if isinstance(decision, str) and decision:
        return decision
    overall = str(qc_report.get("overall_status", ""))
    return {"pass": "PASS", "pass_with_warnings": "PASS_WITH_WARNINGS", "fail": "REJECT"}.get(overall, "REJECT")


def compute_allowed_claim_level(
    *,
    method_capability: str,
    subquestion_ceiling: str,
    project_ceiling: str,
    qc_decision: str,
) -> str:
    """The admitted evidence's hard ``allowed_claim_level`` (T-19-05).

    Table-driven and monotone: the result is the lowest of the method contract's
    capability, the sub-question's ceiling, the project ceiling, and the QC-derived
    cap.  Any one ceiling can only pull the level down.
    """
    qc_cap = _QC_CLAIM_CAP.get(qc_decision, CLAIM_LEVELS[0])
    return _min_level(method_capability, subquestion_ceiling, project_ceiling, qc_cap)


def classify_relation(
    *,
    n_significant: int,
    expected_direction: str,
    observed_direction: str,
    adequately_powered: bool,
) -> str:
    """Classify an observation as supports / opposes / neutral / inconclusive (T-19-06).

    A significant result in the planned direction *supports*; a significant result in
    the opposite direction *opposes*.  A non-significant result is *neutral* only when
    the design was adequately powered; otherwise it is *inconclusive* — a
    non-significant result never silently becomes "no effect".
    """
    if n_significant > 0:
        if expected_direction and observed_direction and observed_direction != expected_direction:
            return "opposes"
        return "supports"
    return "neutral" if adequately_powered else "inconclusive"


def resolve_replication_status(
    *,
    source_dataset_ids: list[str],
    prior_dataset_ids: list[str] | None = None,
    same_cohort: bool = False,
) -> str:
    """Resolve the replication status honestly (T-19-07).

    A single dataset is ``single_dataset``.  Multiple datasets that reuse the same
    cohort are ``multi_dataset`` but never ``replicated`` — reprocessing one cohort
    is not independent replication.  Independent datasets are ``replicated``.
    """
    datasets = {d for d in source_dataset_ids if d}
    if len(datasets) <= 1:
        return "single_dataset"
    if same_cohort or (prior_dataset_ids and datasets & {d for d in prior_dataset_ids if d} and same_cohort):
        return "multi_dataset"
    return "replicated"


@dataclass
class AdmissionOutcome:
    """The bounded outcome of an evidence-admission attempt.

    Exactly one of ``evidence_item`` (when ``decision == 'admitted'``) or
    ``non_admissible_marker`` (when ``decision == 'non_admissible'``) is populated.
    ``reason_code`` explains a refusal (one of :data:`NON_ADMISSIBLE_REASONS`).
    """

    decision: str
    reason_code: str = ""
    message: str = ""
    evidence_item: dict[str, Any] | None = None
    non_admissible_marker: dict[str, Any] | None = None

    @property
    def admitted(self) -> bool:
        return self.decision == "admitted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason_code": self.reason_code,
            "message": self.message,
            "admitted": self.admitted,
            "evidence_item": self.evidence_item,
            "non_admissible_marker": self.non_admissible_marker,
        }


def _lineage_from(
    method_result: Mapping[str, Any], artifact_manifest: Mapping[str, Any], dataset_profile: Mapping[str, Any], subquestion: Mapping[str, Any]
) -> dict[str, list[str]]:
    return {
        "artifact_ids": [artifact_manifest.get("artifact_id", "")] if artifact_manifest.get("artifact_id") else [],
        "source_dataset_ids": [dataset_profile.get("dataset_id", "")] if dataset_profile.get("dataset_id") else [],
        "source_task_run_ids": [method_result.get("task_run_id", "")] if method_result.get("task_run_id") else [],
        "subquestion_ids": [subquestion.get("subquestion_id", "")] if subquestion.get("subquestion_id") else [],
    }


def _non_admissible_marker(
    *,
    reason_code: str,
    message: str,
    method_result: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any],
    qc_report: Mapping[str, Any],
    subquestion: Mapping[str, Any],
) -> dict[str, Any]:
    """A bounded ``NON_ADMISSIBLE_RESULT`` archive marker (T-19-09).

    It is deliberately *not* an EvidenceItem: it records that a result was archived
    without becoming evidence, with the QC verdict and lineage, so a report can never
    mistake it for admitted evidence.
    """
    marker_id = make_stable_id(
        "non_admissible_result",
        {"artifact_id": artifact_manifest.get("artifact_id", ""), "task_run_id": method_result.get("task_run_id", ""), "reason": reason_code},
    )
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "record_type": "NON_ADMISSIBLE_RESULT",
        "non_admissible_result_id": marker_id,
        "reason_code": reason_code,
        "message": message,
        "artifact_id": artifact_manifest.get("artifact_id", ""),
        "task_run_id": method_result.get("task_run_id", ""),
        "subquestion_id": subquestion.get("subquestion_id", ""),
        "qc_report_id": qc_report.get("qc_report_id", ""),
        "qc_decision": qc_decision_of(qc_report),
        "is_formal_evidence": False,
        "created_at": "",
        "status": "archived",
    }


def admit_evidence(
    *,
    result_table: list[Mapping[str, Any]],
    method_result: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any],
    qc_report: Mapping[str, Any],
    dataset_profile: Mapping[str, Any],
    scope_bundle: Mapping[str, Any],
    subquestion: Mapping[str, Any],
    contract: Mapping[str, Any],
    project_ceiling: str,
    allow_warnings: bool = False,
    eligibility_decision: Mapping[str, Any] | None = None,
) -> AdmissionOutcome:
    """Run the evidence-admission gate over a recorded fixture result (T-19-01..07).

    Fail-closed precedence: (1) the QC decision must be admitting (a REJECT / RETRY /
    REPLAN / NEED_HUMAN_REVIEW, or a PASS_WITH_WARNINGS under a policy that does not
    accept warnings, is archived, never admitted); (2) full lineage
    (artifact / dataset / task-run / sub-question) is mandatory — a result with no
    lineage is refused; (3) the observation is extracted, the four-way relation and
    replication status are classified, and the ``allowed_claim_level`` is computed as
    the lowest applicable ceiling; the built :class:`EvidenceItem` must pass
    :func:`validate_evidence_item` or it is refused as malformed.
    """
    decision = qc_decision_of(qc_report)
    # Gate 1: QC decision.
    if decision not in _ADMITTING_DECISIONS:
        return AdmissionOutcome(
            "non_admissible",
            "QC_NOT_PASSED",
            f"QC decision {decision!r} does not admit evidence",
            non_admissible_marker=_non_admissible_marker(
                reason_code="QC_NOT_PASSED",
                message=f"QC decision {decision!r}",
                method_result=method_result,
                artifact_manifest=artifact_manifest,
                qc_report=qc_report,
                subquestion=subquestion,
            ),
        )
    if decision == "PASS_WITH_WARNINGS" and not allow_warnings:
        return AdmissionOutcome(
            "non_admissible",
            "POLICY_WARNINGS_NOT_ACCEPTED",
            "QC decision PASS_WITH_WARNINGS but the active policy does not accept warnings",
            non_admissible_marker=_non_admissible_marker(
                reason_code="POLICY_WARNINGS_NOT_ACCEPTED",
                message="warnings not accepted",
                method_result=method_result,
                artifact_manifest=artifact_manifest,
                qc_report=qc_report,
                subquestion=subquestion,
            ),
        )

    # Gate 2: lineage is mandatory (T-19-02, T-19-04).
    lineage = _lineage_from(method_result, artifact_manifest, dataset_profile, subquestion)
    if not (lineage["artifact_ids"] and lineage["source_dataset_ids"] and lineage["source_task_run_ids"] and lineage["subquestion_ids"]):
        return AdmissionOutcome(
            "non_admissible",
            "NO_LINEAGE",
            f"evidence requires full lineage; got {lineage}",
            non_admissible_marker=_non_admissible_marker(
                reason_code="NO_LINEAGE",
                message="incomplete lineage",
                method_result=method_result,
                artifact_manifest=artifact_manifest,
                qc_report=qc_report,
                subquestion=subquestion,
            ),
        )
    if artifact_manifest.get("exists") is not True or artifact_manifest.get("is_placeholder") is True:
        return AdmissionOutcome(
            "non_admissible",
            "MISSING_ARTIFACT",
            "artifact is missing or a placeholder",
            non_admissible_marker=_non_admissible_marker(
                reason_code="MISSING_ARTIFACT",
                message="artifact missing/placeholder",
                method_result=method_result,
                artifact_manifest=artifact_manifest,
                qc_report=qc_report,
                subquestion=subquestion,
            ),
        )

    # Gate 3: build the EvidenceItem (T-19-03).
    item = _build_evidence_item(
        result_table=result_table,
        method_result=method_result,
        artifact_manifest=artifact_manifest,
        qc_report=qc_report,
        dataset_profile=dataset_profile,
        scope_bundle=scope_bundle,
        subquestion=subquestion,
        contract=contract,
        project_ceiling=project_ceiling,
        qc_decision=decision,
        eligibility_decision=eligibility_decision,
    )
    errors = validate_evidence_item(item)
    if errors:
        return AdmissionOutcome(
            "non_admissible",
            "MALFORMED_RESULT",
            "; ".join(errors),
            non_admissible_marker=_non_admissible_marker(
                reason_code="MALFORMED_RESULT",
                message="; ".join(errors),
                method_result=method_result,
                artifact_manifest=artifact_manifest,
                qc_report=qc_report,
                subquestion=subquestion,
            ),
        )
    return AdmissionOutcome("admitted", "ADMITTED", "observation admitted as formal evidence", evidence_item=item)


def _build_evidence_item(
    *,
    result_table: list[Mapping[str, Any]],
    method_result: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any],
    qc_report: Mapping[str, Any],
    dataset_profile: Mapping[str, Any],
    scope_bundle: Mapping[str, Any],
    subquestion: Mapping[str, Any],
    contract: Mapping[str, Any],
    project_ceiling: str,
    qc_decision: str,
    eligibility_decision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    rows = list(result_table)
    sig = [r for r in rows if _truthy(r.get("significant"))]
    sig_sorted = sorted(sig, key=lambda r: (float(r.get("fdr", 1.0)), str(r.get("gene", ""))))
    top = [str(r.get("gene", "")) for r in sig_sorted[:10]]
    max_abs_lfc = max((abs(float(r.get("log2_fold_change", 0.0))) for r in rows), default=0.0)

    params = contract.get("parameters", {}) or {}
    allowed = compute_allowed_claim_level(
        method_capability=str(contract.get("claim_capability", "association")),
        subquestion_ceiling=str(subquestion.get("claim_ceiling", project_ceiling)),
        project_ceiling=project_ceiling,
        qc_decision=qc_decision,
    )
    relation = classify_relation(
        n_significant=len(sig),
        expected_direction=str(subquestion.get("expected_direction", "")),
        observed_direction=str(method_result.get("observed_direction", "")),
        adequately_powered=bool(method_result.get("adequately_powered", True)),
    )
    replication = resolve_replication_status(
        source_dataset_ids=[dataset_profile.get("dataset_id", "")],
        prior_dataset_ids=list(method_result.get("prior_dataset_ids", []) or []),
        same_cohort=bool(method_result.get("same_cohort", False)),
    )
    group_a = method_result.get("group_a", "")
    group_b = method_result.get("group_b", "")
    observation = (
        f"{len(sig)} of {len(rows)} genes show significant bulk-RNA differential expression "
        f"between {group_a} and {group_b} (relation={relation}, replication={replication})."
    )
    limitations = [
        "RNA differential expression is association-level evidence; it does not establish protein abundance, secretion, or causality.",
    ]
    if replication == "single_dataset":
        limitations.append("Single dataset; results are not independently replicated.")
    if relation == "inconclusive":
        limitations.append("Non-significant under inadequate power; absence of evidence is not evidence of absence.")
    limitations.extend(dataset_profile.get("known_limitations", []) or [])

    item = EvidenceItem(
        evidence_item_id="",
        artifact_id=artifact_manifest.get("artifact_id", ""),
        review_status="negative" if relation in ("opposes", "inconclusive") else "audited",
        subquestion_ids=[subquestion.get("subquestion_id", "")],
        source_dataset_ids=[dataset_profile.get("dataset_id", "")],
        source_task_run_ids=[method_result.get("task_run_id", "")],
        observation=observation,
        effect_summary={
            "n_genes": len(rows),
            "n_significant": len(sig),
            "top_significant_genes": top,
            "max_abs_log2_fold_change": round(max_abs_lfc, 4),
        },
        uncertainty={
            "statistical_test": method_result.get("statistical_test", "welch_t_test"),
            "fdr_method": "benjamini_hochberg",
            "significance_alpha": params.get("significance_alpha", 0.05),
            "log2fc_threshold": params.get("log2fc_threshold", 1.0),
        },
        evidence_type=str(contract.get("evidence_type", "bulk_rna_differential_expression")),
        scope={
            "species": list(scope_bundle.get("species", []) or []),
            "tissue": list(scope_bundle.get("tissues", []) or []),
            "condition": list(scope_bundle.get("conditions", []) or []),
        },
        qc_status="pass" if qc_decision == "PASS" else "pass_with_warnings",
        allowed_claim_level=allowed,
        supports_or_opposes=_RELATION_TO_DIRECTION[relation],
        replication_status=replication,
        limitations=limitations,
    )
    data = item.to_dict()
    # Record the four-way relation and the method-contract version alongside lineage.
    data["evidence_relation"] = relation
    data["method_contract_version"] = contract.get("version", contract.get("method_contract_version", ""))
    data["qc_report_id"] = qc_report.get("qc_report_id", "")
    data["created_at"] = ""
    return data


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


class EvidenceRegistry:
    """An append-only registry of admitted evidence and non-admissible markers (T-19-11).

    Formal evidence and non-admissible markers are stored in separate pools so a
    query can never confuse them.  Queries default to *including* negative /
    opposing / inconclusive evidence — negative evidence is never hidden by default
    (T-19-08).  Retraction marks an item (and any claim that used it) stale without
    physically deleting the history (T-19-10).
    """

    def __init__(self) -> None:
        self._evidence: list[dict[str, Any]] = []
        self._non_admissible: list[dict[str, Any]] = []
        self._retracted: dict[str, dict[str, Any]] = {}

    def admit(self, outcome: AdmissionOutcome) -> str:
        """Record an admission outcome; return the stored record id."""
        if outcome.admitted and outcome.evidence_item is not None:
            self._evidence.append(dict(outcome.evidence_item))
            return str(outcome.evidence_item["evidence_item_id"])
        if outcome.non_admissible_marker is not None:
            self._non_admissible.append(dict(outcome.non_admissible_marker))
            return str(outcome.non_admissible_marker["non_admissible_result_id"])
        return ""

    def evidence_items(self, *, include_retracted: bool = False) -> list[dict[str, Any]]:
        return [e for e in self._evidence if include_retracted or e["evidence_item_id"] not in self._retracted]

    def non_admissible_markers(self) -> list[dict[str, Any]]:
        return list(self._non_admissible)

    def query(
        self,
        *,
        subquestion_id: str | None = None,
        direction: str | None = None,
        relation: str | None = None,
        qc_status: str | None = None,
        dataset_id: str | None = None,
        include_negative: bool = True,
        include_retracted: bool = False,
    ) -> list[dict[str, Any]]:
        """Query the formal evidence pool by scope / direction / QC / dataset (T-19-11).

        ``include_negative`` defaults to ``True`` so opposing / inconclusive evidence
        is returned unless a caller *explicitly* opts out — negative evidence is never
        silently filtered.
        """
        results = []
        for item in self.evidence_items(include_retracted=include_retracted):
            if subquestion_id is not None and subquestion_id not in (item.get("subquestion_ids") or []):
                continue
            if direction is not None and item.get("supports_or_opposes") != direction:
                continue
            if relation is not None and item.get("evidence_relation") != relation:
                continue
            if qc_status is not None and item.get("qc_status") != qc_status:
                continue
            if dataset_id is not None and dataset_id not in (item.get("source_dataset_ids") or []):
                continue
            if not include_negative and item.get("supports_or_opposes") in ("opposes", "neutral"):
                continue
            results.append(item)
        return results

    def negative_evidence(self) -> list[dict[str, Any]]:
        """The negative / opposing / inconclusive evidence, always retained (T-19-08)."""
        return [e for e in self.evidence_items() if e.get("evidence_relation") in ("opposes", "inconclusive") or e.get("supports_or_opposes") == "opposes"]

    def retract(self, evidence_item_id: str, *, reason: str, dependent_claim_ids: list[str] | None = None) -> dict[str, Any]:
        """Retract an evidence item and mark dependent claims stale (T-19-10).

        The item is *not* physically removed — it is marked retracted and excluded
        from default queries — and the returned event lists the claims that must be
        marked stale.  Retraction is idempotent.
        """
        event = {
            "schema_version": CANONICAL_SCHEMA_VERSION,
            "record_type": "EVIDENCE_RETRACTION",
            "evidence_item_id": evidence_item_id,
            "reason": reason,
            "stale_claim_ids": list(dependent_claim_ids or []),
            "created_at": "",
            "status": "retracted",
        }
        self._retracted[evidence_item_id] = event
        return event

    def is_retracted(self, evidence_item_id: str) -> bool:
        return evidence_item_id in self._retracted


__all__ = [
    "ADMISSION_DECISIONS",
    "EVIDENCE_RELATIONS",
    "REPLICATION_STATUSES",
    "NON_ADMISSIBLE_REASONS",
    "AdmissionOutcome",
    "EvidenceRegistry",
    "admit_evidence",
    "compute_allowed_claim_level",
    "classify_relation",
    "resolve_replication_status",
    "qc_decision_of",
]
