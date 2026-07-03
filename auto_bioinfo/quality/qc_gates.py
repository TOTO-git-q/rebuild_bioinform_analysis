"""Four-layer QC rule registry, deterministic engine, and advancement gate (WP-18).

This is the *rule-driven* four-layer QC engine (Execution / Data / Statistical /
Biological) that the requirement spec (stage 13) places between a raw run and
scientific evidence.  Where :mod:`auto_bioinfo.quality.qc_engine` hard-codes a
fixed check list, this module drives QC from a **queryable, version-frozen QC Rule
Registry** (T-18-01): every check is a registered :class:`QCRule` with an id,
layer, version, applies-to selector, severity and action, and every result is a
structured :class:`QCFinding` bound to the exact artifact / sample / gene-set /
task-run / sub-question it concerns (T-18-11) — never a bare boolean.

The engine (T-18-02..08) is a **pure, offline, deterministic** function of the
recorded fixture artifacts handed to it: it reads only its in-memory inputs,
performs no I/O, no network, no clock read, no subprocess, and never mutates the
audited unit — the audited unit cannot change the result it is being judged by.
It records ``required_qc`` coverage (T-18-09): a contract-required rule that was
not executed (or came back ``not_assessed``) can never PASS.  A composite decision
(T-18-10) maps the findings to one of exactly six bounded verdicts
(:data:`QC_DECISIONS`); the advancement gate (:func:`qc_gate_admits`) admits only a
PASS — or a PASS_WITH_WARNINGS when policy explicitly allows accepted warnings —
so a failing hard gate blocks advancement to Evidence admission.  Every finding is
scoped, every decision is explainable, and a human review override
(:func:`apply_human_review`) may *accept* a warning under policy but can never
erase a finding (T-18-13).

Determinism: the produced :class:`QCReport`-shaped dict carries an empty
``created_at`` so byte-identical inputs yield a byte-identical report.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION

# --- Bounded QC vocabularies -------------------------------------------------
# The four QC layers, kept in sync with core.schemas.QC_CHECK_LAYERS.
QC_LAYERS = ("execution", "data", "statistical", "biological")

# Per-finding status.  ``not_assessed`` keeps an honest "the tool could not judge
# this" distinct from a ``pass`` — a required rule that is ``not_assessed`` blocks
# a PASS rather than being silently treated as clean (T-18-05, T-18-09).
FINDING_STATUSES = ("pass", "warn", "fail", "not_assessed")

# Per-rule severity (how bad a failure of this rule is).
SEVERITIES = ("info", "warning", "error", "critical")

# The action a *failing* rule demands.  Callers branch on the action, never the
# message.  ``advisory`` never blocks; the others feed the composite decision.
RULE_ACTIONS = (
    "advisory",
    "warn_only",
    "require_retry",
    "require_replan",
    "require_human_review",
    "block_reject",
)

# The six bounded composite QC decisions (T-18-10).  Only PASS / PASS_WITH_WARNINGS
# may reach Evidence admission (and PASS_WITH_WARNINGS only under an allowing policy).
QC_DECISIONS = (
    "PASS",
    "PASS_WITH_WARNINGS",
    "RETRY",
    "REPLAN",
    "REJECT",
    "NEED_HUMAN_REVIEW",
)

# The QCReport.overall_status shape (matches core.schemas.QC_OVERALL_STATUSES so the
# produced report validates against validate_qc_report).
_OVERALL_PASS = "pass"
_OVERALL_WARN = "pass_with_warnings"
_OVERALL_FAIL = "fail"


@dataclass(frozen=True)
class QCRule:
    """A single registered, version-frozen QC rule (T-18-01).

    ``applies_to`` is a coarse selector (``"all"`` or a modality/evidence tag) used
    only to decide whether the rule runs against a given fixture bundle; it is not a
    biological authority.  ``severity`` and ``action`` are fixed at registration so
    the composite decision is deterministic and explainable.
    """

    rule_id: str
    layer: str
    version: str
    applies_to: str
    severity: str
    action: str
    description: str


# A rule evaluator is a pure function of the fixture bundle returning
# ``(status, reason, scope, metric)``.  ``status`` is one of FINDING_STATUSES.
_Evaluator = Callable[[Mapping[str, Any]], "tuple[str, str, dict[str, Any], dict[str, Any]]"]


def _artifact_scope(bundle: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    artifact = bundle.get("artifact_manifest", {}) or {}
    method = bundle.get("method_result", {}) or {}
    scope = {
        "artifact_id": artifact.get("artifact_id", ""),
        "task_run_id": method.get("task_run_id", ""),
        "subquestion_ids": list(bundle.get("subquestion_ids", []) or []),
    }
    scope.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    return scope


# --- Execution-layer evaluators (T-18-03) -----------------------------------


def _eval_method_succeeded(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    status = str(method.get("status", ""))
    ok = status == "succeeded"
    return ("pass" if ok else "fail", f"method status={status or 'missing'}", _artifact_scope(bundle), {"status": status})


def _eval_output_exists(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    art = bundle.get("artifact_manifest", {}) or {}
    size = int(art.get("size_bytes", 0) or 0)
    ok = art.get("exists") is True and size > 0 and not art.get("is_placeholder", False)
    return (
        "pass" if ok else "fail",
        f"exists={art.get('exists')} size_bytes={size} placeholder={art.get('is_placeholder', False)}",
        _artifact_scope(bundle),
        {"size_bytes": size},
    )


def _eval_expected_outputs(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    outputs = method.get("outputs", {}) or {}
    expected = bundle.get("expected_outputs", ["deg_results_table"]) or []
    missing = [name for name in expected if name not in outputs]
    ok = not missing
    return (
        "pass" if ok else "fail",
        ("all expected outputs present" if ok else f"missing expected outputs: {missing}"),
        _artifact_scope(bundle),
        {"missing": missing},
    )


def _eval_no_error_log(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    errors = list(method.get("log_errors", []) or [])
    warnings = list(method.get("log_warnings", []) or [])
    if errors:
        return ("fail", f"execution log recorded {len(errors)} error(s): {errors[:3]}", _artifact_scope(bundle), {"n_errors": len(errors)})
    if warnings:
        return ("warn", f"execution log recorded {len(warnings)} warning(s): {warnings[:3]}", _artifact_scope(bundle), {"n_warnings": len(warnings)})
    return ("pass", "execution log is clean", _artifact_scope(bundle), {})


# --- Data-layer evaluators (T-18-04) ----------------------------------------


def _group_sizes(bundle: Mapping[str, Any]) -> dict[str, int]:
    method = bundle.get("method_result", {}) or {}
    profile = bundle.get("dataset_profile", {}) or {}
    sizes = method.get("group_sizes") or profile.get("group_sizes") or {}
    return {str(k): int(v) for k, v in sizes.items()}


def _eval_group_count(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    contract = bundle.get("contract", {}) or {}
    design = contract.get("minimum_sample_design", {}) or {}
    need = int(design.get("groups", 2))
    sizes = _group_sizes(bundle)
    ok = len(sizes) >= need
    return ("pass" if ok else "fail", f"groups={list(sizes)} (need >= {need})", _artifact_scope(bundle), {"n_groups": len(sizes)})


def _eval_nonempty_matrix(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    n_genes = int(method.get("n_genes", 0) or 0)
    ok = n_genes > 0
    return ("pass" if ok else "fail", f"n_genes={n_genes}", _artifact_scope(bundle), {"n_genes": n_genes})


def _eval_sample_matrix_alignment(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    n_samples = int(method.get("n_samples", sum(_group_sizes(bundle).values())) or 0)
    labelled = int(method.get("n_labelled_samples", n_samples) or 0)
    ok = n_samples > 0 and n_samples == labelled
    reason = "sample count matches label count" if ok else f"sample/label mismatch: n_samples={n_samples} labelled={labelled}"
    return ("pass" if ok else "fail", reason, _artifact_scope(bundle), {"n_samples": n_samples, "n_labelled": labelled})


def _eval_checksum_present(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    art = bundle.get("artifact_manifest", {}) or {}
    ok = bool(art.get("checksum_sha256"))
    return ("pass" if ok else "fail", "artifact has a content checksum" if ok else "artifact is missing a content checksum", _artifact_scope(bundle), {})


def _eval_id_mapping(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    unmapped = int(method.get("n_unmapped_ids", 0) or 0)
    total = int(method.get("n_genes", 0) or 0)
    if total <= 0:
        return ("not_assessed", "no gene ids to map", _artifact_scope(bundle), {})
    frac = unmapped / total
    if frac == 0:
        return ("pass", "all gene ids mapped", _artifact_scope(bundle), {"unmapped_fraction": 0.0})
    status = "fail" if frac > 0.2 else "warn"
    return (status, f"{unmapped}/{total} gene ids unmapped (fraction={round(frac, 4)})", _artifact_scope(bundle), {"unmapped_fraction": round(frac, 4)})


# --- single-cell / snRNA data QC (T-18-05) ----------------------------------


def _eval_sc_quality_metrics(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    sc = bundle.get("sc_metrics")
    if not isinstance(sc, Mapping):
        # Tool capability insufficient / not a single-cell run: explicit NOT_ASSESSED,
        # never a silent pass (T-18-05).
        return ("not_assessed", "no single-cell QC metrics recorded; doublet/ambient not assessed", _artifact_scope(bundle), {})
    doublet = float(sc.get("doublet_rate", 0.0) or 0.0)
    ambient = float(sc.get("ambient_rna_fraction", 0.0) or 0.0)
    if doublet > 0.25 or ambient > 0.5:
        return (
            "fail",
            f"single-cell QC out of range: doublet_rate={doublet} ambient_rna_fraction={ambient}",
            _artifact_scope(bundle),
            {"doublet_rate": doublet, "ambient_rna_fraction": ambient},
        )
    if doublet > 0.1 or ambient > 0.2:
        return (
            "warn",
            f"single-cell QC elevated: doublet_rate={doublet} ambient_rna_fraction={ambient}",
            _artifact_scope(bundle),
            {"doublet_rate": doublet, "ambient_rna_fraction": ambient},
        )
    return (
        "pass",
        f"single-cell QC within range: doublet_rate={doublet} ambient_rna_fraction={ambient}",
        _artifact_scope(bundle),
        {"doublet_rate": doublet, "ambient_rna_fraction": ambient},
    )


# --- Statistical-layer evaluators (T-18-06, T-18-07) ------------------------


def _eval_min_replicates(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    contract = bundle.get("contract", {}) or {}
    design = contract.get("minimum_sample_design", {}) or {}
    min_rep = int(design.get("min_replicates_per_group", 2))
    sizes = _group_sizes(bundle)
    below = {g: n for g, n in sizes.items() if n < min_rep}
    ok = not below
    reason = f"all groups >= {min_rep} replicates" if ok else f"groups below {min_rep} replicates: {below}"
    return ("pass" if ok else "fail", reason, _artifact_scope(bundle), {"below_min": below, "min_replicates": min_rep})


def _eval_unit_is_sample(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    contract = bundle.get("contract", {}) or {}
    unit = contract.get("statistical_unit")
    ok = unit == "sample"
    reason = "statistical unit is 'sample' (no pseudo-replication)" if ok else f"statistical_unit={unit!r}; cells/reads as units is pseudo-replication"
    return ("pass" if ok else "fail", reason, _artifact_scope(bundle), {"statistical_unit": unit})


def _eval_multiple_testing(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    corrected = method.get("multiple_testing_correction", "benjamini_hochberg")
    ok = bool(corrected) and corrected != "none"
    reason = f"multiple-testing correction={corrected}" if ok else "no multiple-testing correction applied across genes"
    return ("pass" if ok else "fail", reason, _artifact_scope(bundle), {"correction": corrected})


def _eval_outlier_sensitivity(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    method = bundle.get("method_result", {}) or {}
    single = method.get("single_sample_driven")
    if single is None:
        return ("not_assessed", "no sensitivity/leave-one-out record; single-sample influence not assessed", _artifact_scope(bundle), {})
    if bool(single):
        return (
            "warn",
            "result is driven by a single sample (leave-one-out flips significance); block or flag for review",
            _artifact_scope(bundle),
            {"single_sample_driven": True},
        )
    return ("pass", "result is robust to leave-one-out sensitivity", _artifact_scope(bundle), {"single_sample_driven": False})


# --- Biological-layer evaluators (T-18-08) ----------------------------------


def _eval_claim_capability_matches(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    profile = bundle.get("dataset_profile", {}) or {}
    contract = bundle.get("contract", {}) or {}
    modality = str(profile.get("modality", "")).lower()
    capability = str(contract.get("claim_capability", ""))
    is_rna = "rna" in modality or "expression" in modality
    # RNA/expression evidence is capped at association: a capability above that on
    # RNA data is a preset over-reach and is blocked (T-18-08).
    over = is_rna and capability not in ("", "descriptive", "association")
    if over:
        return (
            "fail",
            f"modality={modality} but claim_capability={capability}; RNA expression cannot support protein/secretion/causal claims",
            _artifact_scope(bundle),
            {"modality": modality, "capability": capability},
        )
    return (
        "pass",
        f"modality={modality}, claim_capability={capability} within data ceiling",
        _artifact_scope(bundle),
        {"modality": modality, "capability": capability},
    )


def _eval_marker_specificity(bundle: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    bio = bundle.get("biological")
    if not isinstance(bio, Mapping):
        return ("not_assessed", "no biological marker context recorded; specificity not assessed", _artifact_scope(bundle), {})
    cross = bool(bio.get("cross_species_extrapolation", False))
    if cross:
        return ("warn", "candidate relies on cross-species extrapolation; specificity is uncertain", _artifact_scope(bundle), {"cross_species": True})
    return ("pass", "marker specificity context recorded within species/tissue", _artifact_scope(bundle), {"cross_species": False})


# --- The default, version-frozen QC Rule Registry (T-18-01) ------------------

_REGISTRY_VERSION = "auto_bioinfo.qc_rules/0.1"

_EVALUATORS: dict[str, _Evaluator] = {
    "execution.method_succeeded": _eval_method_succeeded,
    "execution.output_exists": _eval_output_exists,
    "execution.expected_outputs_present": _eval_expected_outputs,
    "execution.log_clean": _eval_no_error_log,
    "data.group_count": _eval_group_count,
    "data.nonempty_matrix": _eval_nonempty_matrix,
    "data.sample_matrix_alignment": _eval_sample_matrix_alignment,
    "data.checksum_present": _eval_checksum_present,
    "data.id_mapping": _eval_id_mapping,
    "data.sc_quality_metrics": _eval_sc_quality_metrics,
    "statistical.min_replicates": _eval_min_replicates,
    "statistical.unit_is_sample": _eval_unit_is_sample,
    "statistical.multiple_testing": _eval_multiple_testing,
    "statistical.outlier_sensitivity": _eval_outlier_sensitivity,
    "biological.claim_capability_matches_data": _eval_claim_capability_matches,
    "biological.marker_specificity": _eval_marker_specificity,
}

DEFAULT_QC_RULES: tuple[QCRule, ...] = (
    QCRule("execution.method_succeeded", "execution", _REGISTRY_VERSION, "all", "critical", "block_reject", "Method process exited successfully."),
    QCRule(
        "execution.output_exists",
        "execution",
        _REGISTRY_VERSION,
        "all",
        "critical",
        "block_reject",
        "Declared primary output exists, is non-empty and not a placeholder.",
    ),
    QCRule("execution.expected_outputs_present", "execution", _REGISTRY_VERSION, "all", "error", "require_retry", "All contract-expected outputs are present."),
    QCRule("execution.log_clean", "execution", _REGISTRY_VERSION, "all", "warning", "warn_only", "Execution log carries no unresolved error entries."),
    QCRule("data.group_count", "data", _REGISTRY_VERSION, "all", "error", "require_replan", "Enough comparison groups exist for the requested contrast."),
    QCRule("data.nonempty_matrix", "data", _REGISTRY_VERSION, "all", "critical", "block_reject", "The analysed matrix is non-empty."),
    QCRule(
        "data.sample_matrix_alignment",
        "data",
        _REGISTRY_VERSION,
        "all",
        "error",
        "require_replan",
        "Samples and the matrix are aligned (no misregistered labels).",
    ),
    QCRule("data.checksum_present", "data", _REGISTRY_VERSION, "all", "error", "require_retry", "The artifact carries a content checksum."),
    QCRule("data.id_mapping", "data", _REGISTRY_VERSION, "all", "warning", "warn_only", "Gene identifiers map cleanly to the reference."),
    QCRule(
        "data.sc_quality_metrics",
        "data",
        _REGISTRY_VERSION,
        "single_cell",
        "error",
        "require_replan",
        "Single-cell doublet/ambient metrics are within range (else NOT_ASSESSED).",
    ),
    QCRule("statistical.min_replicates", "statistical", _REGISTRY_VERSION, "all", "error", "require_replan", "Every group meets the minimum replicate count."),
    QCRule(
        "statistical.unit_is_sample",
        "statistical",
        _REGISTRY_VERSION,
        "all",
        "critical",
        "block_reject",
        "The statistical unit is the sample (no pseudo-replication).",
    ),
    QCRule(
        "statistical.multiple_testing",
        "statistical",
        _REGISTRY_VERSION,
        "all",
        "error",
        "require_retry",
        "A multiple-testing correction was applied across genes.",
    ),
    QCRule(
        "statistical.outlier_sensitivity",
        "statistical",
        _REGISTRY_VERSION,
        "all",
        "warning",
        "require_human_review",
        "The result is not driven by a single influential sample.",
    ),
    QCRule(
        "biological.claim_capability_matches_data",
        "biological",
        _REGISTRY_VERSION,
        "all",
        "critical",
        "block_reject",
        "The declared claim capability does not exceed what the data modality can support.",
    ),
    QCRule(
        "biological.marker_specificity",
        "biological",
        _REGISTRY_VERSION,
        "evidence_candidate",
        "warning",
        "warn_only",
        "Marker specificity does not rely on unstated cross-species extrapolation.",
    ),
)


class QCRuleRegistry:
    """A queryable, version-frozen registry of QC rules (T-18-01).

    Rules are immutable once constructed; :meth:`freeze` returns a stable content
    hash so a report can pin the exact registry version it was judged under.  The
    registry does not run QC — it only *describes* the rules.
    """

    def __init__(self, rules: tuple[QCRule, ...] = DEFAULT_QC_RULES, *, version: str = _REGISTRY_VERSION) -> None:
        self.version = version
        self._rules: tuple[QCRule, ...] = tuple(rules)
        self._by_id: dict[str, QCRule] = {r.rule_id: r for r in self._rules}

    @property
    def rules(self) -> tuple[QCRule, ...]:
        return self._rules

    def get(self, rule_id: str) -> QCRule | None:
        return self._by_id.get(rule_id)

    def for_layer(self, layer: str) -> tuple[QCRule, ...]:
        return tuple(r for r in self._rules if r.layer == layer)

    def rule_ids(self) -> tuple[str, ...]:
        return tuple(r.rule_id for r in self._rules)

    def freeze(self) -> str:
        """A stable content id for this exact rule set (for report pinning)."""
        return make_stable_id(
            "qc_rule_registry",
            {"version": self.version, "rules": [(r.rule_id, r.layer, r.version, r.severity, r.action) for r in self._rules]},
        )


DEFAULT_REGISTRY = QCRuleRegistry()


@dataclass(frozen=True)
class QCFinding:
    """A single scoped QC finding (T-18-11) — never a bare boolean.

    ``scope`` binds the finding to the artifact / task-run / sample / gene-set /
    sub-question it concerns, so a downstream reader knows exactly what a failure
    invalidates.
    """

    finding_id: str
    rule_id: str
    layer: str
    status: str
    severity: str
    action: str
    reason: str
    scope: dict[str, Any] = field(default_factory=dict)
    metric: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "check_id": self.rule_id,
            "layer": self.layer,
            "status": self.status,
            "severity": self.severity,
            "action": self.action,
            "reason": self.reason,
            "detail": self.reason,
            "scope": dict(self.scope),
            "artifact_id": self.scope.get("artifact_id", ""),
            "metric": dict(self.metric),
        }


def _applies(rule: QCRule, bundle: Mapping[str, Any]) -> bool:
    if rule.applies_to == "all":
        return True
    if rule.applies_to == "single_cell":
        modality = str((bundle.get("dataset_profile", {}) or {}).get("modality", "")).lower()
        return "single" in modality or "sc" in modality or "sn" in modality or bundle.get("sc_metrics") is not None
    if rule.applies_to == "evidence_candidate":
        return bundle.get("biological") is not None
    return True


def run_qc(
    bundle: Mapping[str, Any],
    *,
    registry: QCRuleRegistry = DEFAULT_REGISTRY,
    allow_warnings: bool = False,
) -> dict[str, Any]:
    """Run the rule-driven four-layer QC engine over a recorded fixture bundle.

    ``bundle`` is a read-only mapping of recorded artifacts:
    ``method_result`` / ``artifact_manifest`` / ``dataset_profile`` / ``contract``
    (and optional ``sc_metrics`` / ``biological`` / ``subquestion_ids`` /
    ``expected_outputs``).  ``contract['required_qc']`` (optional) lists the rule ids
    the method contract mandates; a required rule that did not run or came back
    ``not_assessed`` blocks a PASS (T-18-09).  ``allow_warnings`` records whether the
    active policy permits a PASS_WITH_WARNINGS to advance (the gate re-checks it).

    Returns a QCReport-shaped dict (validates against
    :func:`auto_bioinfo.core.validation.validate_qc_report`) enriched with the
    scoped ``findings``, the six-value ``decision`` (:data:`QC_DECISIONS`), the
    ``required_qc_coverage`` record and the pinned ``rule_registry_id``.  The input
    is never mutated; ``created_at`` is empty for determinism.
    """
    findings: list[QCFinding] = []
    executed: set[str] = set()
    for rule in registry.rules:
        if not _applies(rule, bundle):
            continue
        evaluator = _EVALUATORS.get(rule.rule_id)
        if evaluator is None:
            continue
        status, reason, scope, metric = evaluator(bundle)
        executed.add(rule.rule_id)
        finding_id = make_stable_id("qc_finding", {"rule_id": rule.rule_id, "artifact_id": scope.get("artifact_id", ""), "status": status})
        findings.append(QCFinding(finding_id, rule.rule_id, rule.layer, status, rule.severity, rule.action, reason, scope, metric))

    coverage = _required_qc_coverage(bundle, findings, executed, registry)
    checks = _findings_to_checks(findings)
    overall = _overall_status(findings)
    decision = _composite_decision(findings, coverage, overall)

    report_id = make_stable_id(
        "qc_report",
        {
            "artifact_id": (bundle.get("artifact_manifest", {}) or {}).get("artifact_id", ""),
            "checks": [c["check_id"] for c in checks],
            "overall_status": overall,
            "decision": decision,
        },
    )
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "qc_report_id": report_id,
        "artifact_id": (bundle.get("artifact_manifest", {}) or {}).get("artifact_id", ""),
        "overall_status": overall,
        "decision": decision,
        "checks": checks,
        "findings": [f.to_dict() for f in findings],
        "blocking_findings": [f.to_dict() for f in findings if f.status == "fail"],
        "not_assessed": [f.to_dict() for f in findings if f.status == "not_assessed"],
        "required_qc_coverage": coverage,
        "rule_registry_id": registry.freeze(),
        "policy_allows_warnings": bool(allow_warnings),
        "created_at": "",
        "status": "recorded",
    }


def _findings_to_checks(findings: list[QCFinding]) -> list[dict[str, Any]]:
    """Project findings into validate_qc_report-compatible checks.

    A ``not_assessed`` finding is surfaced as a ``warn`` check whose reason is
    prefixed ``NOT_ASSESSED`` so it stays visible and blocks a clean PASS while
    keeping the report shape valid (statuses are limited to pass/warn/fail there).
    """
    checks: list[dict[str, Any]] = []
    for finding in findings:
        data = finding.to_dict()
        if finding.status == "not_assessed":
            data = dict(data)
            data["status"] = "warn"
            data["reason"] = f"NOT_ASSESSED: {finding.reason}"
            data["detail"] = data["reason"]
        checks.append(data)
    return checks


def _overall_status(findings: list[QCFinding]) -> str:
    if any(f.status == "fail" for f in findings):
        return _OVERALL_FAIL
    if any(f.status in ("warn", "not_assessed") for f in findings):
        return _OVERALL_WARN
    return _OVERALL_PASS


def _required_qc_coverage(
    bundle: Mapping[str, Any],
    findings: list[QCFinding],
    executed: set[str],
    registry: QCRuleRegistry,
) -> dict[str, Any]:
    contract = bundle.get("contract", {}) or {}
    required = [str(r) for r in (contract.get("required_qc") or [])]
    status_by_rule = {f.rule_id: f.status for f in findings}
    not_executed = [r for r in required if r not in executed]
    not_assessed = [r for r in required if status_by_rule.get(r) == "not_assessed"]
    unknown = [r for r in required if registry.get(r) is None]
    complete = not not_executed and not not_assessed
    return {
        "required": required,
        "not_executed": not_executed,
        "not_assessed": not_assessed,
        "unknown_rules": unknown,
        "complete": complete,
    }


def _composite_decision(findings: list[QCFinding], coverage: Mapping[str, Any], overall: str) -> str:
    """Map findings + coverage to one of the six bounded QC decisions (T-18-10).

    The mapping is deterministic and precedence-ordered: a hard REJECT dominates,
    then a mandated human review, then replan, then retry, then a coverage gap
    (which can never PASS), then warnings, then a clean PASS.
    """
    failed = [f for f in findings if f.status == "fail"]
    if any(f.action == "block_reject" for f in failed):
        return "REJECT"
    if any(f.action == "require_human_review" and f.status in ("fail", "warn") for f in findings):
        return "NEED_HUMAN_REVIEW"
    if any(f.action == "require_replan" for f in failed):
        return "REPLAN"
    if any(f.action == "require_retry" for f in failed):
        return "RETRY"
    if failed:
        # A remaining failure with no stronger action still cannot pass.
        return "REJECT"
    if not coverage.get("complete", True):
        # A missing / not-assessed required rule may never PASS (T-18-09).
        return "NEED_HUMAN_REVIEW"
    if overall == _OVERALL_WARN:
        return "PASS_WITH_WARNINGS"
    return "PASS"


# --- Advancement gate (exit criterion) --------------------------------------

QC_ADMITTING_DECISIONS = ("PASS", "PASS_WITH_WARNINGS")


def qc_gate_admits(report: Mapping[str, Any], *, allow_warnings: bool | None = None) -> tuple[bool, str]:
    """The hard QC gate between a run and Evidence admission (exit criterion).

    Admits only a PASS, or a PASS_WITH_WARNINGS when policy allows accepted warnings
    (``allow_warnings``, defaulting to the report's recorded
    ``policy_allows_warnings``).  Every other decision — RETRY / REPLAN / REJECT /
    NEED_HUMAN_REVIEW — blocks advancement.  Returns ``(admitted, reason)``.
    """
    decision = str(report.get("decision", ""))
    allow = report.get("policy_allows_warnings", False) if allow_warnings is None else allow_warnings
    if decision == "PASS":
        return (True, "QC decision PASS admits the artifact to Evidence admission")
    if decision == "PASS_WITH_WARNINGS":
        if allow:
            return (True, "QC decision PASS_WITH_WARNINGS admitted under a policy that accepts warnings")
        return (False, "QC decision PASS_WITH_WARNINGS blocked: active policy does not accept warnings")
    return (False, f"QC decision {decision!r} is not an admitting decision (only PASS / policy-allowed PASS_WITH_WARNINGS advance)")


# --- Local rerun proposal (T-18-12) -----------------------------------------


def propose_remediation(report: Mapping[str, Any]) -> dict[str, Any]:
    """Propose a *local* rerun for the failing/blocked findings (T-18-12).

    Lists the affected scopes, the reason, and the *bounded* parameters a rerun may
    vary — never significance thresholds.  Tuning ``significance_alpha`` /
    ``fdr_threshold`` / ``log2fc_threshold`` for significance is explicitly
    forbidden and recorded as such.
    """
    forbidden = ("significance_alpha", "fdr_threshold", "log2fc_threshold", "p_value")
    proposals: list[dict[str, Any]] = []
    for finding in report.get("findings", []):
        if finding.get("status") not in ("fail", "not_assessed"):
            continue
        proposals.append(
            {
                "rule_id": finding.get("rule_id"),
                "layer": finding.get("layer"),
                "affected_scope": finding.get("scope", {}),
                "reason": finding.get("reason"),
                "recommended_action": finding.get("action"),
                "mutable_parameters": [],
                "forbidden_parameters": list(forbidden),
            }
        )
    return {
        "qc_report_id": report.get("qc_report_id"),
        "decision": report.get("decision"),
        "proposals": proposals,
        "note": "Reruns may correct data/pipeline defects only; adjusting thresholds to reach significance is forbidden.",
        "status": "proposed",
    }


# --- Human review override (T-18-13) ----------------------------------------


def apply_human_review(
    report: Mapping[str, Any],
    *,
    accept_warnings: bool,
    reviewer: str,
    note: str,
    policy_allows_override: bool = True,
) -> dict[str, Any]:
    """Record a human review over a QC report (T-18-13).

    A reviewer may *accept* warnings (turning a PASS_WITH_WARNINGS into an admitted
    outcome) only when policy allows it and no ``fail`` finding remains; the review
    can never erase a finding — the original decision and every finding are
    preserved verbatim.  Returns an immutable review record (never mutates the
    report).
    """
    has_fail = any(f.get("status") == "fail" for f in report.get("findings", []))
    original = str(report.get("decision", ""))
    if not policy_allows_override:
        effective, outcome = original, "override_not_permitted"
    elif has_fail:
        # A fail can never be accepted away — findings are preserved, decision stands.
        effective, outcome = original, "rejected_fail_present"
    elif accept_warnings and original == "PASS_WITH_WARNINGS":
        effective, outcome = "PASS_WITH_WARNINGS", "warnings_accepted"
    else:
        effective, outcome = original, "no_change"
    return {
        "qc_report_id": report.get("qc_report_id"),
        "reviewer": reviewer,
        "note": note,
        "original_decision": original,
        "effective_decision": effective,
        "warnings_accepted": outcome == "warnings_accepted",
        "outcome": outcome,
        "preserved_findings": list(report.get("findings", [])),
        "created_at": "",
        "status": "reviewed",
    }


def qc_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """A compact, machine-readable QC summary (T-18-15); never rewrites the report."""
    findings = report.get("findings", [])
    by_layer: dict[str, dict[str, int]] = {layer: {"pass": 0, "warn": 0, "fail": 0, "not_assessed": 0} for layer in QC_LAYERS}
    for finding in findings:
        layer = finding.get("layer", "")
        status = finding.get("status", "")
        if layer in by_layer and status in by_layer[layer]:
            by_layer[layer][status] += 1
    return {
        "qc_report_id": report.get("qc_report_id"),
        "artifact_id": report.get("artifact_id"),
        "decision": report.get("decision"),
        "overall_status": report.get("overall_status"),
        "n_findings": len(findings),
        "n_blocking": len(report.get("blocking_findings", [])),
        "required_qc_complete": report.get("required_qc_coverage", {}).get("complete"),
        "by_layer": by_layer,
    }


__all__ = [
    "QC_LAYERS",
    "FINDING_STATUSES",
    "SEVERITIES",
    "RULE_ACTIONS",
    "QC_DECISIONS",
    "QC_ADMITTING_DECISIONS",
    "QCRule",
    "QCRuleRegistry",
    "QCFinding",
    "DEFAULT_QC_RULES",
    "DEFAULT_REGISTRY",
    "run_qc",
    "qc_gate_admits",
    "propose_remediation",
    "apply_human_review",
    "qc_summary",
]
