"""Reproduction bundle builder + comparator.

Exports a self-contained bundle a third party can re-run offline: the locked
inputs, the exact parameters + software versions, the produced outputs, the QC
rules, the claims, a ``checksums.sha256`` over everything, and a
``comparison_spec`` describing how a re-run should be compared.  ``compare_bundle``
re-reads a (re-run) bundle and grades it against the recorded checksums.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ..core.ids import make_stable_id
from ..core.provenance import authoritative_release, describe_dataset_origin
from ..core.schemas import now_iso
from ..execution.objects import read_object
from ..execution.runs import load_claims, load_evidence_items, load_qc_reports, load_task_runs

CONSISTENCY_LEVELS = [
    "BITWISE_IDENTICAL",
    "NUMERICALLY_EQUIVALENT_WITHIN_TOLERANCE",
    "SAME_CANDIDATE_SET",
    "SAME_SCIENTIFIC_CLAIM",
    "NOT_REPRODUCED",
    "NOT_COMPARABLE",
]


class FormalExportRefused(Exception):
    """Raised when a *formal* export is requested for a project whose
    authoritative release is ``DEMONSTRATION_ONLY``.  No formal export artifact
    is produced — the caller must surface a non-zero exit (Gate 4)."""

    def __init__(self, release: dict[str, Any]) -> None:
        self.release = release
        reasons = ", ".join(release.get("reasons", [])) or "INELIGIBLE"
        super().__init__(f"formal export refused: release is {release.get('release_status')} ({reasons})")


def compute_project_release(project_dir: str | Path) -> dict[str, Any]:
    """Recompute the project's authoritative release through the single gate
    (persisted ScientificEligibilityDecision + active ProjectPolicy), without
    building any bundle.  Lets the CLI gate ``export --formal`` *before* it would
    write any artifact."""
    project_dir = Path(project_dir)
    policy = read_object(project_dir, "project_policy", {})
    return authoritative_release(
        read_object(project_dir, "scientific_eligibility_decision", {}),
        policy=policy,
        claims=load_claims(project_dir),
        evidence_items=load_evidence_items(project_dir),
    )


def build_reproduction_bundle(project_dir: str | Path, *, formal: bool = False) -> dict[str, Any]:
    """Build the reproduction bundle.

    A plain (``formal=False``) export always carries the ``DEMONSTRATION_ONLY``
    watermark for an ineligible project.  A ``formal=True`` export is the Gate 4
    formal-output door: if the authoritative release is not eligible it raises
    :class:`FormalExportRefused` *before writing anything*, so no formal export
    artifact can ever be produced for a demonstration run.
    """
    project_dir = Path(project_dir)
    if formal:
        guard = compute_project_release(project_dir)
        if not guard["scientific_output_eligible"]:
            raise FormalExportRefused(guard)
    bundle = project_dir / "reproduction_bundle"
    if bundle.exists():
        shutil.rmtree(bundle)
    (bundle / "inputs").mkdir(parents=True, exist_ok=True)
    (bundle / "outputs").mkdir(parents=True, exist_ok=True)
    (bundle / "qc_rules").mkdir(parents=True, exist_ok=True)

    manifest = read_object(project_dir, "dataset_manifest", {})
    method_result = read_object(project_dir, "method_result", {})
    research_spec = read_object(project_dir, "research_spec", {})
    workflow = read_object(project_dir, "workflow_plan", {})
    artifact = read_object(project_dir, "registered_artifact", {})
    policy = read_object(project_dir, "project_policy", {})
    execution_mode = policy.get("execution_mode", "DEMO")
    # Authoritative eligibility gate: recompute from the persisted decision +
    # active policy; never trust the cached flag on a Claim/EvidenceItem.
    release = authoritative_release(
        read_object(project_dir, "scientific_eligibility_decision", {}),
        policy=policy,
        claims=load_claims(project_dir),
        evidence_items=load_evidence_items(project_dir),
    )
    eligible = release["scientific_output_eligible"]
    release_status = release["release_status"]

    # Copy locked inputs and produced outputs into the bundle.
    for _name, rel in manifest.get("materialized_files", {}).items():
        src = project_dir / rel
        if src.exists():
            shutil.copyfile(src, bundle / "inputs" / Path(rel).name)
    if artifact.get("path") and (project_dir / artifact["path"]).exists():
        shutil.copyfile(project_dir / artifact["path"], bundle / "outputs" / Path(artifact["path"]).name)

    _dump(bundle / "research_spec.json", research_spec)
    _dump(bundle / "workflow_plan.json", workflow)
    _dump(bundle / "dataset_manifest.json", manifest)
    _dump(bundle / "parameters.json", method_result.get("params", {}))
    _dump(bundle / "environment.json", method_result.get("software_versions", {}))
    _dump(bundle / "claims.json", load_claims(project_dir))
    _dump(bundle / "evidence_items.json", load_evidence_items(project_dir))
    for report in load_qc_reports(project_dir):
        _dump(bundle / "qc_rules" / f"{report['qc_report_id']}.json", report)

    original_summary = {
        "project_id": project_dir.name,
        "method_id": method_result.get("method_id"),
        "method_version": method_result.get("version"),
        "n_genes": method_result.get("n_genes"),
        "n_significant": method_result.get("n_significant"),
        "group_sizes": method_result.get("group_sizes"),
        "task_runs": load_task_runs(project_dir),
    }
    _dump(bundle / "original_run_summary.json", original_summary)

    comparison_spec = {
        "schema_version": "auto_bioinfo.comparison_spec/0.1",
        "primary_output": f"outputs/{Path(artifact.get('path', 'deg_results.tsv')).name}",
        "rules": [
            {"target": "primary_output", "expected_level": "BITWISE_IDENTICAL", "tolerance": 0.0},
            {"target": "n_significant", "expected_level": "SAME_CANDIDATE_SET", "tolerance": 0},
        ],
        "consistency_levels": CONSISTENCY_LEVELS,
    }
    _dump(bundle / "comparison_spec.json", comparison_spec)

    checksums = _write_checksums(bundle)
    run_order = (
        "# Reproduction run order\n\n"
        "1. Recreate the environment in `environment.json`.\n"
        "2. Re-run method `" + str(method_result.get("method_id")) + "` on `inputs/` with `parameters.json`.\n"
        "3. Compare your `outputs/` against the recorded `checksums.sha256` using `comparison_spec.json`.\n"
        "\nThis bundle is offline and deterministic; a correct re-run is BITWISE_IDENTICAL.\n"
    )
    (bundle / "run_order.md").write_text(run_order, encoding="utf-8")
    demo_banner = (
        f"> ⚠️ **{release_status}** (execution_mode = `{execution_mode}`). This bundle reproduces a "
        f"DEMONSTRATION run; its claims are NOT formal scientific evidence and must not be exported as research results.\n\n"
        if not eligible
        else f"> execution_mode = `{execution_mode}` · release_status = `{release_status}`.\n\n"
    )
    # Gate 8: the inputs line is generated from the *actual* source_class of the
    # locked dataset, never a hard-coded "committed fixture" string.  A REAL run
    # backed by real data must not be described as a fixture.
    origin_line = describe_dataset_origin(
        manifest.get("source_class", "LEGACY_UNKNOWN"),
        accession=str(manifest.get("accession", "") or ""),
    )
    (bundle / "README.md").write_text(
        f"# Reproduction bundle for project `{project_dir.name}`\n\n"
        + demo_banner
        + "Self-contained, offline, deterministic. See `run_order.md` and `comparison_spec.json`.\n"
        + origin_line + "\n",
        encoding="utf-8",
    )

    manifest_obj = {
        "reproduction_bundle_id": make_stable_id("reproduction_bundle", {"project_id": project_dir.name, "checksums": checksums}),
        "project_id": project_dir.name,
        "execution_mode": execution_mode,
        "release_status": release_status,
        "scientific_output_eligible": eligible,
        "export_type": "FORMAL" if formal else "DEMONSTRATION",
        "bundle_dir": "reproduction_bundle",
        "files": sorted(checksums.keys()),
        "checksums_sha256": checksums,
        "comparison_spec": "reproduction_bundle/comparison_spec.json",
        "run_order": "reproduction_bundle/run_order.md",
        "generated_at": now_iso(),
        "status": "ready",
    }
    return manifest_obj


def compare_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    """Re-verify a bundle's files against its recorded ``checksums.sha256``."""
    bundle = Path(bundle_dir)
    recorded = _read_checksums(bundle / "checksums.sha256")
    results: list[dict[str, Any]] = []
    overall = "BITWISE_IDENTICAL"
    for rel, expected in sorted(recorded.items()):
        path = bundle / rel
        if not path.exists():
            results.append({"file": rel, "level": "NOT_REPRODUCED", "reason": "missing"})
            overall = "NOT_REPRODUCED"
            continue
        actual = _sha256(path)
        if actual == expected:
            results.append({"file": rel, "level": "BITWISE_IDENTICAL"})
        else:
            results.append({"file": rel, "level": "NOT_REPRODUCED", "reason": "checksum mismatch"})
            overall = "NOT_REPRODUCED"
    return {"bundle_dir": str(bundle), "overall_level": overall, "files_checked": len(recorded), "results": results}


# --- helpers ----------------------------------------------------------------

def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksums(bundle: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            checksums[str(path.relative_to(bundle))] = _sha256(path)
    lines = [f"{digest}  {rel}" for rel, digest in sorted(checksums.items())]
    (bundle / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksums


def _read_checksums(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, rel = line.split("  ", 1)
            out[rel] = digest
    return out
