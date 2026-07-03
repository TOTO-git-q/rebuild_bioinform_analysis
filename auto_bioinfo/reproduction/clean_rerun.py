"""Clean deterministic re-run + seven-level result comparison (WP-22).

Stage 18 of the requirement spec: re-execute the bundle in a *clean* workdir (never
reusing the original run's workdir) and compare the reproduced result against the
original (T-22-10..12).  Because the whole system is offline and inert, the "clean
container re-run" is modelled as a **deterministic offline re-execution of recorded
fixture task records** in a fresh in-memory workdir: :func:`run_clean_rerun` recomputes
each task's output from its recorded inputs with a pure function, so a faithful bundle
reproduces byte-identically.  :func:`compare_results` grades each target with its
ComparisonSpec strategy into one of exactly **seven** bounded levels
(:data:`COMPARISON_LEVELS`), records the tolerances applied, and
:func:`classify_failure` sorts a non-reproduction into one of five bounded causes
(:data:`FAILURE_CLASSES`) — never a bare "failed".

Pure, offline, deterministic; produced records carry empty timestamps.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# The seven bounded comparison levels, ordered strongest → weakest (T-22-11).
COMPARISON_LEVELS = (
    "BITWISE_IDENTICAL",
    "NUMERICALLY_EQUIVALENT_WITHIN_TOLERANCE",
    "SAME_CANDIDATE_SET",
    "SAME_DIRECTION",
    "SAME_SCIENTIFIC_CLAIM",
    "NOT_REPRODUCED",
    "NOT_COMPARABLE",
)
_LEVEL_RANK = {level: idx for idx, level in enumerate(COMPARISON_LEVELS)}

# The five bounded reproduction-failure causes (T-22-12).
FAILURE_CLASSES = ("environment", "input", "numeric", "method", "scientifically_incomparable")


def render_deg_tsv(rows: Sequence[Mapping[str, Any]]) -> str:
    """Render DEG rows to a deterministic TSV (sorted by gene) — the recompute step."""
    header = "gene\tlog2_fold_change\tfdr\tsignificant"
    body = [
        f"{r.get('gene', '')}\t{float(r.get('log2_fold_change', 0.0)):.6f}\t{float(r.get('fdr', 1.0)):.6f}\t{str(bool(r.get('significant'))).lower()}"
        for r in sorted(rows, key=lambda r: str(r.get("gene", "")))
    ]
    return "\n".join([header, *body]) + "\n"


def run_clean_rerun(task_records: Sequence[Mapping[str, Any]], *, workdir_label: str = "clean_rerun") -> dict[str, Any]:
    """Re-execute recorded fixture task records in a fresh in-memory workdir (T-22-10).

    Each task record carries ``task_id``, ``output_name`` and its recorded ``rows``;
    the rerun recomputes the output deterministically (never reads the original
    workdir).  Returns ``{workdir, reproduced_outputs: {name: content}, task_run_ids}``.
    """
    workdir = f"{workdir_label}::isolated"  # a fresh, isolated workdir label, never the original
    reproduced: dict[str, str] = {}
    task_run_ids: list[str] = []
    for record in task_records:
        name = str(record.get("output_name", record.get("task_id", "output")))
        reproduced[name] = render_deg_tsv(record.get("rows", []))
        task_run_ids.append(f"rerun::{record.get('task_id', '')}")
    return {"workdir": workdir, "reproduced_outputs": reproduced, "task_run_ids": task_run_ids, "created_at": ""}


def _compare_target(strategy: str, original: Any, reproduced: Any, tolerance: float) -> str:
    """Grade a single target under its strategy into a seven-level result."""
    if original is None or reproduced is None:
        return "NOT_COMPARABLE"
    if strategy == "bitwise":
        return "BITWISE_IDENTICAL" if original == reproduced else "NOT_REPRODUCED"
    if strategy == "numeric":
        if not _numeric_pair(original, reproduced):
            return "NOT_COMPARABLE"
        if float(original) == float(reproduced):
            return "BITWISE_IDENTICAL"
        return "NUMERICALLY_EQUIVALENT_WITHIN_TOLERANCE" if abs(float(original) - float(reproduced)) <= tolerance else "NOT_REPRODUCED"
    if strategy == "set":
        return "SAME_CANDIDATE_SET" if _as_set(original) == _as_set(reproduced) else "NOT_REPRODUCED"
    if strategy == "direction":
        return "SAME_DIRECTION" if _sign(original) == _sign(reproduced) else "NOT_REPRODUCED"
    if strategy == "claim":
        return "SAME_SCIENTIFIC_CLAIM" if str(original) == str(reproduced) else "NOT_REPRODUCED"
    return "NOT_COMPARABLE"


def compare_results(
    original: Mapping[str, Any],
    reproduced: Mapping[str, Any],
    comparison_spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare original vs reproduced per the ComparisonSpec (T-22-11).

    ``original`` / ``reproduced`` map each rule ``target`` to its value.  Returns a
    per-target level, the overall (weakest) level, and the tolerances applied.  A
    target missing from either side is ``NOT_COMPARABLE``.
    """
    results: list[dict[str, Any]] = []
    tolerances: dict[str, float] = {}
    overall_rank = 0
    for rule in comparison_spec.get("rules", []):
        target = str(rule.get("target", rule.get("expected_output", "")))
        strategy = str(rule.get("strategy", "bitwise"))
        tolerance = float(rule.get("tolerance", 0.0) or 0.0)
        tolerances[target] = tolerance
        if target not in original or target not in reproduced:
            level = "NOT_COMPARABLE"
        else:
            level = _compare_target(strategy, original[target], reproduced[target], tolerance)
        results.append({"target": target, "strategy": strategy, "level": level, "tolerance": tolerance})
        # NOT_COMPARABLE should not silently dominate a genuine mismatch ranking, but it
        # is still the weakest; track the max rank to surface the weakest outcome.
        overall_rank = max(overall_rank, _LEVEL_RANK[level])
    overall = COMPARISON_LEVELS[overall_rank] if results else "NOT_COMPARABLE"
    reproduced_ok = overall_rank <= _LEVEL_RANK["SAME_SCIENTIFIC_CLAIM"]
    return {
        "overall_level": overall,
        "reproduced": reproduced_ok,
        "results": results,
        "tolerances": tolerances,
        "consistency_levels": list(COMPARISON_LEVELS),
        "created_at": "",
    }


def classify_failure(context: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a reproduction failure into one of five bounded causes (T-22-12).

    ``context`` records the comparison facts: ``environment_match`` /
    ``input_checksum_match`` / ``method_match`` / ``scope_comparable`` and the
    numeric-only-difference flag.  Precedence: environment → input → method →
    scientifically-incomparable → numeric.  Never a bare "failed".
    """
    if not context.get("environment_match", True):
        cause = "environment"
    elif not context.get("input_checksum_match", True):
        cause = "input"
    elif not context.get("method_match", True):
        cause = "method"
    elif not context.get("scope_comparable", True):
        cause = "scientifically_incomparable"
    else:
        cause = "numeric"
    return {"failure_class": cause, "context": dict(context), "created_at": ""}


# --- helpers ----------------------------------------------------------------


def _numeric_pair(a: Any, b: Any) -> bool:
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool)


def _as_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(v) for v in value}
    return {str(value)}


def _sign(value: Any) -> int:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0
    return (num > 0) - (num < 0)


__all__ = [
    "COMPARISON_LEVELS",
    "FAILURE_CLASSES",
    "render_deg_tsv",
    "run_clean_rerun",
    "compare_results",
    "classify_failure",
]
