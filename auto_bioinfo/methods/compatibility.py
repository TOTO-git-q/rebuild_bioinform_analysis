"""Deterministic method<->dataset compatibility + method plan (WP-11).

The decision half of stage 8.  Given an ACTIVE, admitted MethodContract (and its
machine-readable :class:`~auto_bioinfo.methods.contract_catalog.MethodRule`), a
factual dataset profile, and a sub-question with a claim ceiling, this module
produces an immutable :class:`~auto_bioinfo.core.schemas.CompatibilityDecision`
with a bounded verdict and recorded reasons (T-11-03/04/13), and ranks the
*compatible* methods into a :class:`MethodPlan` draft (T-11-14) — or emits the
``METHOD_NOT_APPLICABLE`` stop when nothing is compatible (T-11-15).

Hard failures (wrong modality, cell-level pseudo-replication, insufficient
design, missing background universe, non-independent datasets) are recorded as
``incompatible`` and can never be overridden by ranking: ranking only orders the
already-compatible set and never mutates a decision.  A method whose claim
capability is below what the sub-question asks is ``conditionally_compatible``
with a conservative imposed claim ceiling — it may contribute but never prove
above its capability (e.g. a gene-set score can never alone prove a mechanism).

Pure / offline / deterministic: no I/O, no clock read, no network, no
randomness; produced decisions carry an empty ``created_at``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import CLAIM_LEVELS, CompatibilityDecision
from ..core.validation import validate_compatibility_decision
from .contract_catalog import MethodRule
from .contract_registry import MethodRegistry

# --- Bounded compatibility reason codes --------------------------------------
COMPAT_OK = "COMPATIBLE"
COMPAT_CONDITIONAL_CLAIM_CAP = "CONDITIONAL_CLAIM_CAPPED"
COMPAT_CONDITIONAL_SOFT_REQUIREMENT = "CONDITIONAL_SOFT_REQUIREMENT_MISSING"
COMPAT_MODALITY_MISMATCH = "INCOMPATIBLE_MODALITY"
COMPAT_PSEUDOREPLICATION = "INCOMPATIBLE_PSEUDOREPLICATION"
COMPAT_STAT_UNIT_MISMATCH = "INCOMPATIBLE_STATISTICAL_UNIT"
COMPAT_INSUFFICIENT_DESIGN = "INCOMPATIBLE_INSUFFICIENT_DESIGN"
COMPAT_MISSING_GENE_UNIVERSE = "INCOMPATIBLE_MISSING_GENE_UNIVERSE"
COMPAT_NOT_INDEPENDENT = "INCOMPATIBLE_NOT_INDEPENDENT"
COMPAT_MISSING_METADATA = "INCOMPATIBLE_MISSING_METADATA"
COMPAT_INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"

COMPAT_CODES = (
    COMPAT_OK,
    COMPAT_CONDITIONAL_CLAIM_CAP,
    COMPAT_CONDITIONAL_SOFT_REQUIREMENT,
    COMPAT_MODALITY_MISMATCH,
    COMPAT_PSEUDOREPLICATION,
    COMPAT_STAT_UNIT_MISMATCH,
    COMPAT_INSUFFICIENT_DESIGN,
    COMPAT_MISSING_GENE_UNIVERSE,
    COMPAT_NOT_INDEPENDENT,
    COMPAT_MISSING_METADATA,
    COMPAT_INSUFFICIENT_INFORMATION,
)

# Method-plan statuses.
PLAN_DRAFTED = "method_plan_drafted"
PLAN_METHOD_NOT_APPLICABLE = "method_not_applicable"


def _min_claim(a: str, b: str) -> str:
    """The lower (more conservative) of two claim levels."""
    if a not in CLAIM_LEVELS:
        return b if b in CLAIM_LEVELS else "descriptive"
    if b not in CLAIM_LEVELS:
        return a
    return min(a, b, key=CLAIM_LEVELS.index)


@dataclass(frozen=True)
class _ProfileFacts:
    """The explicit dataset facts the evaluator compares against a MethodRule."""

    dataset_id: str
    modality: str
    statistical_unit: str
    group_sizes: dict[str, int]
    present_metadata: frozenset[str]
    has_gene_universe: bool
    independent_datasets: bool
    annotation_version: str
    modality_known: bool
    stat_unit_known: bool
    design_known: bool


def _extract_facts(profile: dict[str, Any]) -> _ProfileFacts:
    """Read the explicit facts from a dataset profile; nothing is inferred."""
    modality = str(profile.get("modality", "") or "").strip().lower()
    stat_unit = str(profile.get("statistical_unit", "") or "").strip().lower()

    group_sizes_raw = profile.get("group_sizes") or {}
    group_sizes: dict[str, int] = {}
    if isinstance(group_sizes_raw, dict):
        for key, value in group_sizes_raw.items():
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            group_sizes[str(key)] = value

    present: set[str] = set()
    for key in profile.get("present_metadata", []) if isinstance(profile.get("present_metadata"), list) else []:
        if isinstance(key, str) and key.strip():
            present.add(key.strip())
    metadata_facts = profile.get("metadata_facts")
    if isinstance(metadata_facts, dict):
        present.update(str(k) for k in metadata_facts if str(metadata_facts.get(k, "")).strip() != "")

    sample_count = profile.get("sample_count")
    design_known = bool(group_sizes) or (isinstance(sample_count, int) and not isinstance(sample_count, bool) and sample_count > 0)

    return _ProfileFacts(
        dataset_id=str(profile.get("dataset_id", "") or ""),
        modality=modality,
        statistical_unit=stat_unit,
        group_sizes=group_sizes,
        present_metadata=frozenset(present),
        has_gene_universe=bool(profile.get("has_gene_universe")),
        independent_datasets=bool(profile.get("independent_datasets")),
        annotation_version=str(profile.get("annotation_version", "") or "").strip(),
        modality_known=bool(modality),
        stat_unit_known=bool(stat_unit),
        design_known=design_known,
    )


@dataclass(frozen=True)
class _RuleVerdict:
    code: str
    reasons: tuple[str, ...]
    checked_facts: tuple[str, ...]
    blocking_facts: tuple[str, ...]
    missing_facts: tuple[str, ...]


def _apply_rule(rule: MethodRule, facts: _ProfileFacts) -> _RuleVerdict:
    """Deterministically evaluate the hard conditions of a rule over facts.

    Returns the verdict *code* plus the facts it checked / the blocking facts /
    the missing facts, so a decision can be honest about its basis.
    """
    checked: list[str] = []
    blocking: list[str] = []
    missing: list[str] = []

    # Unknown core facts → insufficient information (never a silent pass/fail).
    if not facts.modality_known:
        missing.append("modality")
    if not facts.stat_unit_known:
        missing.append("statistical_unit")
    if not facts.design_known:
        missing.append("sample_design")
    if missing:
        return _RuleVerdict(
            COMPAT_INSUFFICIENT_INFORMATION, ("core dataset facts are unknown; cannot decide compatibility",), tuple(checked), (), tuple(missing)
        )

    # Modality.
    checked.append(f"modality={facts.modality}")
    if facts.modality not in rule.accepted_modalities:
        blocking.append(f"modality {facts.modality!r} is not in accepted modalities {list(rule.accepted_modalities)}")
        return _RuleVerdict(COMPAT_MODALITY_MISMATCH, tuple(blocking), tuple(checked), tuple(blocking), ())

    # Statistical unit — pseudo-replication guard.
    checked.append(f"statistical_unit={facts.statistical_unit}")
    if facts.statistical_unit in rule.forbidden_statistical_units:
        blocking.append(f"statistical unit {facts.statistical_unit!r} is forbidden (pseudo-replication); method requires {rule.required_statistical_unit!r}")
        return _RuleVerdict(COMPAT_PSEUDOREPLICATION, tuple(blocking), tuple(checked), tuple(blocking), ())
    if facts.statistical_unit != rule.required_statistical_unit:
        blocking.append(f"statistical unit {facts.statistical_unit!r} does not match required {rule.required_statistical_unit!r}")
        return _RuleVerdict(COMPAT_STAT_UNIT_MISMATCH, tuple(blocking), tuple(checked), tuple(blocking), ())

    # Minimum design.
    n_groups = len(facts.group_sizes)
    checked.append(f"n_groups={n_groups}")
    if rule.min_groups >= 2:
        if n_groups < rule.min_groups:
            blocking.append(f"requires >= {rule.min_groups} groups, profile has {n_groups}")
            return _RuleVerdict(COMPAT_INSUFFICIENT_DESIGN, tuple(blocking), tuple(checked), tuple(blocking), ())
        too_small = {g: n for g, n in facts.group_sizes.items() if n < rule.min_replicates_per_group}
        if too_small:
            blocking.append(f"groups below {rule.min_replicates_per_group} replicates: {dict(sorted(too_small.items()))}")
            return _RuleVerdict(COMPAT_INSUFFICIENT_DESIGN, tuple(blocking), tuple(checked), tuple(blocking), ())

    # Required background universe (enrichment).
    if rule.requires_gene_universe:
        checked.append(f"has_gene_universe={facts.has_gene_universe}")
        if not facts.has_gene_universe:
            blocking.append("no background gene universe supplied; enrichment requires an explicit universe")
            return _RuleVerdict(COMPAT_MISSING_GENE_UNIVERSE, tuple(blocking), tuple(checked), tuple(blocking), ())

    # Independence (cross-dataset concordance / replication).
    if rule.requires_independent_datasets:
        checked.append(f"independent_datasets={facts.independent_datasets}")
        if not facts.independent_datasets:
            blocking.append("datasets are not independent; re-analysing the same dataset is not replication")
            return _RuleVerdict(COMPAT_NOT_INDEPENDENT, tuple(blocking), tuple(checked), tuple(blocking), ())

    # Required metadata keys.
    absent = [key for key in rule.required_metadata_keys if key not in facts.present_metadata]
    if absent:
        return _RuleVerdict(
            COMPAT_MISSING_METADATA,
            (f"required metadata missing: {absent}",),
            tuple(checked),
            (f"required metadata missing: {absent}",),
            tuple(absent),
        )
    checked.append(f"metadata_present={sorted(facts.present_metadata & set(rule.required_metadata_keys))}")

    # Annotation version (surface/secretome) — a versioned source is mandatory.
    if rule.requires_annotation_version:
        checked.append(f"annotation_version={facts.annotation_version or '<none>'}")
        if not facts.annotation_version:
            return _RuleVerdict(
                COMPAT_CONDITIONAL_SOFT_REQUIREMENT,
                ("annotation source version not recorded; usable only with a warning until a version is pinned",),
                tuple(checked),
                (),
                ("annotation_version",),
            )

    return _RuleVerdict(COMPAT_OK, ("all hard contract conditions satisfied",), tuple(checked), (), ())


def evaluate_compatibility(
    registry: MethodRegistry,
    method_id: str,
    dataset_profile: dict[str, Any],
    subquestion: dict[str, Any],
    *,
    evidence_plan_id: str,
) -> dict[str, Any]:
    """Return an immutable CompatibilityDecision dict for one method/dataset/SQ.

    A method that is not registered + ACTIVE + enabled is ``incompatible`` (it can
    never be selected).  Otherwise the machine rule is applied; the sub-question's
    claim ceiling caps the imposed ceiling so a compatible-but-under-powered method
    becomes ``conditionally_compatible``.  Raises nothing for a domain condition —
    every outcome is a recorded decision.
    """
    subquestion_id = str(subquestion.get("subquestion_id", "") or "")
    sq_ceiling = str(subquestion.get("claim_ceiling", "association") or "association")

    contract = registry.active_contract(method_id)
    if contract is None or registry.active_entry(method_id) is None:
        return _decision(
            dataset_id=str(dataset_profile.get("dataset_id", "") or ""),
            method_contract_id=make_stable_id("method_contract", {"method_id": method_id, "version": "unregistered"}),
            method_id=method_id,
            subquestion_id=subquestion_id,
            evidence_plan_id=evidence_plan_id,
            verdict="incompatible",
            reasons=[f"method {method_id!r} is not a registered, active, enabled contract; it may not be selected"],
            checked_facts=[],
            blocking_facts=[f"no active contract for {method_id!r}"],
            missing_facts=[],
            imposed_claim_ceiling="descriptive",
            code=COMPAT_MODALITY_MISMATCH,
        )

    entry = registry.active_entry(method_id)
    assert entry is not None
    rule = entry.rule
    contract_id = str(contract["method_contract_id"])
    capability = str(contract.get("claim_capability", "descriptive"))

    facts = _extract_facts(dataset_profile)
    verdict = _apply_rule(rule, facts)

    imposed = _min_claim(capability, sq_ceiling)

    if verdict.code == COMPAT_INSUFFICIENT_INFORMATION:
        return _decision(
            dataset_id=facts.dataset_id,
            method_contract_id=contract_id,
            method_id=method_id,
            subquestion_id=subquestion_id,
            evidence_plan_id=evidence_plan_id,
            verdict="insufficient_information",
            reasons=list(verdict.reasons),
            checked_facts=list(verdict.checked_facts),
            blocking_facts=[],
            missing_facts=list(verdict.missing_facts),
            imposed_claim_ceiling="descriptive",
            code=verdict.code,
        )

    if verdict.code in (COMPAT_OK, COMPAT_CONDITIONAL_SOFT_REQUIREMENT):
        # A soft-requirement miss or a claim-capability below the SQ ceiling both
        # make an otherwise-runnable method *conditionally* compatible.
        capped = CLAIM_LEVELS.index(capability) < CLAIM_LEVELS.index(sq_ceiling) if capability in CLAIM_LEVELS and sq_ceiling in CLAIM_LEVELS else False
        if verdict.code == COMPAT_CONDITIONAL_SOFT_REQUIREMENT or capped:
            reasons = list(verdict.reasons)
            if capped:
                reasons.append(f"method claim capability {capability!r} is below the sub-question ceiling {sq_ceiling!r}; the claim is capped at {imposed!r}")
            return _decision(
                dataset_id=facts.dataset_id,
                method_contract_id=contract_id,
                method_id=method_id,
                subquestion_id=subquestion_id,
                evidence_plan_id=evidence_plan_id,
                verdict="conditionally_compatible",
                reasons=reasons,
                checked_facts=list(verdict.checked_facts),
                blocking_facts=[],
                missing_facts=list(verdict.missing_facts),
                imposed_claim_ceiling=imposed,
                code=COMPAT_CONDITIONAL_SOFT_REQUIREMENT if verdict.code == COMPAT_CONDITIONAL_SOFT_REQUIREMENT else COMPAT_CONDITIONAL_CLAIM_CAP,
            )
        return _decision(
            dataset_id=facts.dataset_id,
            method_contract_id=contract_id,
            method_id=method_id,
            subquestion_id=subquestion_id,
            evidence_plan_id=evidence_plan_id,
            verdict="compatible",
            reasons=list(verdict.reasons),
            checked_facts=list(verdict.checked_facts),
            blocking_facts=[],
            missing_facts=[],
            imposed_claim_ceiling=imposed,
            code=COMPAT_OK,
        )

    # Any remaining code is a hard incompatibility.
    return _decision(
        dataset_id=facts.dataset_id,
        method_contract_id=contract_id,
        method_id=method_id,
        subquestion_id=subquestion_id,
        evidence_plan_id=evidence_plan_id,
        verdict="incompatible",
        reasons=list(verdict.reasons),
        checked_facts=list(verdict.checked_facts),
        blocking_facts=list(verdict.blocking_facts),
        missing_facts=list(verdict.missing_facts),
        imposed_claim_ceiling="descriptive",
        code=verdict.code,
    )


def _decision(
    *,
    dataset_id: str,
    method_contract_id: str,
    method_id: str,
    subquestion_id: str,
    evidence_plan_id: str,
    verdict: str,
    reasons: list[str],
    checked_facts: list[str],
    blocking_facts: list[str],
    missing_facts: list[str],
    imposed_claim_ceiling: str,
    code: str,
) -> dict[str, Any]:
    decision = CompatibilityDecision(
        dataset_id=dataset_id,
        method_contract_id=method_contract_id,
        compatible=verdict in ("compatible", "conditionally_compatible"),
        reason=reasons[0] if reasons else "",
        decision=verdict,
        method_id=method_id,
        subquestion_id=subquestion_id,
        evidence_plan_id=evidence_plan_id,
        reasons=list(reasons),
        checked_facts=list(checked_facts),
        blocking_facts=list(blocking_facts),
        missing_facts=list(missing_facts),
        imposed_claim_ceiling=imposed_claim_ceiling,
        status="draft",
        created_at="",
    ).to_dict()
    decision["reason_code"] = code
    return decision


# --- Method plan -------------------------------------------------------------


@dataclass
class MethodPlan:
    """A ranked plan over the *compatible* methods for one sub-question/dataset.

    Lane-local shared type (there is no MethodPlan in ``core/schemas``).  It binds
    the sub-question and dataset, names the primary and alternative method
    contracts (all drawn from the compatible/conditionally-compatible set), keeps
    the ranking rationale, and points at the immutable CompatibilityDecision ids it
    was built from.  Ranking never changes a decision: a hard incompatibility can
    never be ranked into the plan.  ``status`` is ``method_not_applicable`` when no
    method is compatible (the stage-8 stop; the compiler must not free-write code).
    """

    subquestion_id: str
    dataset_id: str
    status: str
    primary_method_id: str = ""
    alternative_method_ids: list[str] = field(default_factory=list)
    imposed_claim_ceiling: str = "descriptive"
    ranking_rationale: list[str] = field(default_factory=list)
    compatibility_decision_ids: list[str] = field(default_factory=list)
    incompatible_method_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    method_plan_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["method_plan_id"]:
            data["method_plan_id"] = make_stable_id(
                "method_plan",
                {
                    "subquestion_id": self.subquestion_id,
                    "dataset_id": self.dataset_id,
                    "primary_method_id": self.primary_method_id,
                    "alternative_method_ids": list(self.alternative_method_ids),
                },
            )
        return data


# Ranking weights: prefer a fully-compatible verdict over a conditional one, then
# a higher claim capability, then a stable alphabetical method id tiebreak.
_VERDICT_RANK = {"compatible": 0, "conditionally_compatible": 1}


def build_method_plan(
    registry: MethodRegistry,
    dataset_profile: dict[str, Any],
    subquestion: dict[str, Any],
    *,
    evidence_plan_id: str,
    candidate_method_ids: list[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate candidates, then rank the compatible ones into a MethodPlan draft.

    Returns ``(method_plan_dict, decisions)``.  Every candidate produces an
    immutable CompatibilityDecision; the plan is drafted from the accepted subset
    only.  When no candidate is compatible the plan status is
    ``method_not_applicable`` and no method is selected — the stage-8 stop.
    """
    candidates = candidate_method_ids if candidate_method_ids is not None else registry.active_method_ids()
    dataset_id = str(dataset_profile.get("dataset_id", "") or "")
    subquestion_id = str(subquestion.get("subquestion_id", "") or "")

    decisions: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    incompatible: list[str] = []
    for method_id in sorted(candidates):
        decision = evaluate_compatibility(registry, method_id, dataset_profile, subquestion, evidence_plan_id=evidence_plan_id)
        decisions.append(decision)
        if decision["decision"] in ("compatible", "conditionally_compatible"):
            accepted.append(decision)
        else:
            incompatible.append(method_id)

    if not accepted:
        plan = MethodPlan(
            subquestion_id=subquestion_id,
            dataset_id=dataset_id,
            status=PLAN_METHOD_NOT_APPLICABLE,
            incompatible_method_ids=sorted(incompatible),
            compatibility_decision_ids=[d["compatibility_decision_id"] for d in decisions],
            reasons=["no compatible method for this sub-question/dataset; stop rather than free-write code (METHOD_NOT_APPLICABLE)"],
            created_at="",
        )
        return plan.to_dict(), decisions

    def sort_key(decision: dict[str, Any]) -> tuple[int, int, str]:
        contract = registry.active_contract(decision["method_id"]) or {}
        capability = str(contract.get("claim_capability", "descriptive"))
        cap_rank = -CLAIM_LEVELS.index(capability) if capability in CLAIM_LEVELS else 0
        return (_VERDICT_RANK.get(decision["decision"], 9), cap_rank, decision["method_id"])

    accepted.sort(key=sort_key)
    primary = accepted[0]
    alternatives = accepted[1:]
    rationale = [f"{d['method_id']}: verdict={d['decision']}, imposed_ceiling={d.get('imposed_claim_ceiling') or 'n/a'}" for d in accepted]
    plan = MethodPlan(
        subquestion_id=subquestion_id,
        dataset_id=dataset_id,
        status=PLAN_DRAFTED,
        primary_method_id=primary["method_id"],
        alternative_method_ids=[d["method_id"] for d in alternatives],
        imposed_claim_ceiling=str(primary.get("imposed_claim_ceiling") or "descriptive"),
        ranking_rationale=rationale,
        compatibility_decision_ids=[d["compatibility_decision_id"] for d in decisions],
        incompatible_method_ids=sorted(incompatible),
        reasons=["ranked within the compatible set; ranking does not change any compatibility decision"],
        created_at="",
    )
    return plan.to_dict(), decisions


def decision_is_valid(decision: dict[str, Any]) -> bool:
    """True when a produced decision passes the core schema validator."""
    return not validate_compatibility_decision(decision)


__all__ = [
    "COMPAT_OK",
    "COMPAT_CONDITIONAL_CLAIM_CAP",
    "COMPAT_CONDITIONAL_SOFT_REQUIREMENT",
    "COMPAT_MODALITY_MISMATCH",
    "COMPAT_PSEUDOREPLICATION",
    "COMPAT_STAT_UNIT_MISMATCH",
    "COMPAT_INSUFFICIENT_DESIGN",
    "COMPAT_MISSING_GENE_UNIVERSE",
    "COMPAT_NOT_INDEPENDENT",
    "COMPAT_MISSING_METADATA",
    "COMPAT_INSUFFICIENT_INFORMATION",
    "COMPAT_CODES",
    "PLAN_DRAFTED",
    "PLAN_METHOD_NOT_APPLICABLE",
    "MethodPlan",
    "evaluate_compatibility",
    "build_method_plan",
    "decision_is_valid",
]
