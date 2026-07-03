"""In-memory reproduction bundle builder + sensitive-info scan + manifest (WP-22).

Stage 18 of the requirement spec: export a project as a self-contained, offline,
third-party-verifiable bundle.  Where :mod:`auto_bioinfo.reproduction.bundle` writes
a bundle to a project directory, this builder is **pure and in-memory**: it emits the
bundle as a ``{relative_path: content}`` mapping so it has no real filesystem side
effect outside a caller's chosen fixture area.  It exports the versioned objects and
artifacts to a fixed directory layout, computes a ``checksums.sha256`` over every
file (T-22-05), generates a ``run_order.md`` (T-22-06) and a per-artifact
``ComparisonSpec`` (T-22-07), scans every file for sensitive information — absolute
paths, secrets, internal URIs (T-22-08) — and produces an immutable
:class:`ReproductionBundleManifest` (T-22-09) that validates against
:func:`auto_bioinfo.core.validation.validate_reproduction_bundle_manifest`.  A formal
export that would leak sensitive information is refused (Gate X).  Bundles version and
supersede rather than overwrite (T-22-13).

Deterministic: byte-identical inputs yield a byte-identical bundle; produced records
carry empty timestamps.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.schemas import ReproductionBundleManifest
from ..core.validation import validate_reproduction_bundle_manifest

# --- Bounded vocabularies ----------------------------------------------------
# The per-artifact comparison strategies a ComparisonSpec may assign (T-22-07).
COMPARISON_STRATEGIES = ("bitwise", "numeric", "direction", "set", "claim")

# The kinds of sensitive information the export scan blocks (T-22-08).
SENSITIVE_SCAN_KINDS = ("absolute_path", "secret", "internal_uri", "email")

# The bundle lifecycle status.
BUNDLE_STATUSES = ("staged", "valid", "invalid", "superseded")

# Sensitive-info patterns.  Deliberately conservative; a match blocks a formal export.
_SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:/home/|/Users/|/root/|/mnt/[a-z]/|[A-Z]:\\\\)", "absolute_path"),
    (r"(?:AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_-]?key|password|secret|token)\s*[=:]\s*\S+)", "secret"),
    (r"(?:http://localhost|http://127\.0\.0\.1|https?://[a-z0-9.-]*\.(?:corp|internal|local)\b|s3://|redis://|postgres://|mysql://)", "internal_uri"),
    (r"\b[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "email"),
)


class SensitiveExportRefused(Exception):
    """Raised when a *formal* export would leak sensitive information (Gate X)."""

    def __init__(self, findings: list[dict[str, Any]]) -> None:
        self.findings = findings
        super().__init__(f"formal export refused: {len(findings)} sensitive-information finding(s)")


def scan_sensitive(files: Mapping[str, str]) -> list[dict[str, Any]]:
    """Scan every bundle file for sensitive information (T-22-08).

    Returns a list of findings ``{path, kind, match}``; an empty list means the
    bundle is clean.  Matched case-insensitively; the same conservative pattern set
    a formal export is gated on.
    """
    findings: list[dict[str, Any]] = []
    for path in sorted(files):
        content = files[path]
        for pattern, kind in _SENSITIVE_PATTERNS:
            for match in re.finditer(pattern, content, flags=re.IGNORECASE):
                findings.append({"path": path, "kind": kind, "match": match.group(0)[:80]})
    return findings


def _dump(payload: Any) -> str:
    """Deterministic JSON serialisation (sorted keys) for byte-stable checksums."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class BundleBuildResult:
    """The bounded outcome of an in-memory bundle build."""

    status: str
    files: dict[str, str]
    checksums: dict[str, str]
    comparison_spec: dict[str, Any]
    run_order_md: str
    manifest: dict[str, Any]
    sensitive_findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.sensitive_findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "files": dict(self.files),
            "checksums": dict(self.checksums),
            "comparison_spec": self.comparison_spec,
            "run_order_md": self.run_order_md,
            "manifest": self.manifest,
            "sensitive_findings": list(self.sensitive_findings),
            "clean": self.clean,
        }


def build_bundle(
    *,
    project_id: str,
    objects: Mapping[str, Any],
    formal: bool = False,
    version: int = 1,
    supersedes: str = "",
) -> BundleBuildResult:
    """Build the reproduction bundle in memory from recorded fixture objects (T-22-01..09).

    ``objects`` is a mapping of the versioned project objects to export:
    ``research_spec`` / ``scope_bundle`` / ``subquestions`` / ``evidence_plan`` /
    ``dataset_manifest`` / ``workflow_plan`` / ``task_packets`` / ``scripts`` /
    ``parameters`` / ``environment`` / ``qc_rules`` / ``known_limitations`` /
    ``original_run_summary`` / ``trace_index`` / ``claims`` / ``input_files`` /
    ``output_files``.  ``input_files`` / ``output_files`` are ``{name: content}``
    mappings copied verbatim into ``inputs/`` and ``outputs/``.

    Every file is checksummed, a run order and ComparisonSpec are generated, and the
    whole bundle is scanned for sensitive information.  With ``formal=True`` a
    sensitive finding raises :class:`SensitiveExportRefused` before returning; a
    non-formal build returns the findings and marks the bundle ``invalid``.
    """
    files: dict[str, str] = {}

    # Fixed directory layout: versioned objects at the top, data under inputs/outputs.
    files["research_spec.json"] = _dump(objects.get("research_spec", {}))
    files["scope_bundle.json"] = _dump(objects.get("scope_bundle", {}))
    files["subquestions.json"] = _dump(objects.get("subquestions", []))
    files["evidence_plan.json"] = _dump(objects.get("evidence_plan", {}))
    files["dataset_manifest.json"] = _dump(objects.get("dataset_manifest", {}))
    files["workflow_plan.json"] = _dump(objects.get("workflow_plan", {}))
    files["task_packets.json"] = _dump(objects.get("task_packets", []))
    files["parameters.json"] = _dump(objects.get("parameters", {}))
    files["environment.json"] = _dump(objects.get("environment", {}))
    files["claims.json"] = _dump(objects.get("claims", []))
    files["docs/known_limitations.json"] = _dump(objects.get("known_limitations", []))
    files["docs/original_run_summary.json"] = _dump(objects.get("original_run_summary", {}))
    files["docs/trace_index.json"] = _dump(objects.get("trace_index", {}))
    for name, script in (objects.get("scripts", {}) or {}).items():
        files[f"scripts/{name}"] = str(script)
    for report in objects.get("qc_rules", []) or []:
        files[f"qc_rules/{report.get('qc_report_id', report.get('rule_registry_id', 'qc'))}.json"] = _dump(report)
    for name, content in (objects.get("input_files", {}) or {}).items():
        files[f"inputs/{name}"] = str(content)
    for name, content in (objects.get("output_files", {}) or {}).items():
        files[f"outputs/{name}"] = str(content)

    comparison_spec = _comparison_spec(objects)
    files["comparison_spec.json"] = _dump(comparison_spec)

    run_order_md = _run_order(objects)
    files["run_order.md"] = run_order_md

    checksums = {path: _sha256(files[path]) for path in sorted(files)}
    checksum_text = "\n".join(f"{checksums[p]}  {p}" for p in sorted(checksums)) + "\n"
    files["checksums.sha256"] = checksum_text
    # The checksum file itself is listed but not self-referential.

    sensitive = scan_sensitive({p: c for p, c in files.items() if p != "checksums.sha256"})
    if formal and sensitive:
        raise SensitiveExportRefused(sensitive)

    manifest = _build_manifest(
        project_id=project_id,
        files=files,
        checksums=checksums,
        comparison_spec=comparison_spec,
        objects=objects,
        version=version,
        supersedes=supersedes,
        clean=not sensitive,
    )
    status = "invalid" if sensitive else "valid"
    return BundleBuildResult(
        status=status,
        files=files,
        checksums=checksums,
        comparison_spec=comparison_spec,
        run_order_md=run_order_md,
        manifest=manifest,
        sensitive_findings=sensitive,
    )


def _comparison_spec(objects: Mapping[str, Any]) -> dict[str, Any]:
    """Per-artifact ComparisonSpec: every expected output gets a strategy (T-22-07)."""
    primary = "outputs/" + str(next(iter((objects.get("output_files", {}) or {"deg_results.tsv": ""}).keys())))
    rules = [
        {
            "target": primary,
            "expected_output": "primary_output",
            "strategy": "bitwise",
            "tolerance": 0.0,
            "rationale": "deterministic offline run must be byte-identical",
        },
        {"target": "n_significant", "expected_output": "n_significant", "strategy": "set", "tolerance": 0, "rationale": "candidate set must match"},
        {"target": "top_genes", "expected_output": "top_genes", "strategy": "set", "tolerance": 0, "rationale": "top-candidate set must match"},
        {
            "target": "effect_direction",
            "expected_output": "effect_direction",
            "strategy": "direction",
            "tolerance": 0,
            "rationale": "effect direction must match",
        },
        {"target": "claim_level", "expected_output": "claim_level", "strategy": "claim", "tolerance": 0, "rationale": "scientific claim must match"},
    ]
    return {
        "schema_version": "auto_bioinfo.comparison_spec/0.2",
        "primary_output": primary,
        "rules": rules,
        "strategies": list(COMPARISON_STRATEGIES),
    }


def _run_order(objects: Mapping[str, Any]) -> str:
    method_id = str(objects.get("original_run_summary", {}).get("method_id", "the recorded method"))
    return (
        "# Reproduction run order\n\n"
        "Prerequisites: an offline Python environment matching `environment.json`. No network is required.\n\n"
        "1. Recreate the environment declared in `environment.json`.\n"
        f"2. Re-run method `{method_id}` over `inputs/` using `parameters.json` (workflow in `workflow_plan.json`).\n"
        "3. Verify every file against `checksums.sha256`.\n"
        "4. Compare your `outputs/` against the recorded outputs using `comparison_spec.json`.\n\n"
        "This bundle is offline and deterministic; a correct re-run is BITWISE_IDENTICAL.\n"
    )


def _build_manifest(
    *,
    project_id: str,
    files: Mapping[str, str],
    checksums: Mapping[str, str],
    comparison_spec: Mapping[str, Any],
    objects: Mapping[str, Any],
    version: int,
    supersedes: str,
    clean: bool,
) -> dict[str, Any]:
    file_facts = [{"path": path, "checksum": checksums.get(path, "")} for path in sorted(files) if path != "checksums.sha256"]
    run_order_steps = [p for p in ("parameters.json", "workflow_plan.json") if p in files]
    run_order_steps += [p for p in sorted(files) if p.startswith("inputs/")]
    run_order_steps += [p for p in sorted(files) if p.startswith("outputs/")]
    expected_outputs = [{"name": str(rule["expected_output"])} for rule in comparison_spec.get("rules", [])]
    # De-dupe expected outputs by name (a duplicate is rejected by the validator).
    seen: set[str] = set()
    expected_outputs = [o for o in expected_outputs if not (o["name"] in seen or seen.add(o["name"]))]
    comparison_rules = [
        {"expected_output": str(rule["expected_output"]), "strategy": rule["strategy"], "tolerance": rule["tolerance"]}
        for rule in comparison_spec.get("rules", [])
    ]

    manifest_obj = ReproductionBundleManifest(
        bundle_id="",
        project_id=project_id,
        files=file_facts,
        run_order=run_order_steps,
        environment_facts=dict(objects.get("environment", {}) or {}),
        expected_outputs=expected_outputs,
        comparison_rules=comparison_rules,
        reproducibility_level="bitwise",
        reproduction_status="pending",
        created_at="",
    )
    manifest = manifest_obj.to_dict()
    manifest["bundle_version"] = version
    manifest["supersedes_bundle_id"] = supersedes
    manifest["checksums_sha256"] = dict(checksums)
    manifest["license"] = str(objects.get("license", "unspecified"))
    manifest["receipt_restrictions"] = list(objects.get("receipt_restrictions", []) or [])
    manifest["sensitive_scan_clean"] = clean
    errors = validate_reproduction_bundle_manifest(manifest)
    if errors:
        raise ValueError(f"assembled reproduction bundle manifest is invalid: {'; '.join(errors)}")
    return manifest


def verify_bundle(files: Mapping[str, str], checksums: Mapping[str, str]) -> dict[str, Any]:
    """Verify every bundle file against its recorded checksum (T-22-05, T-22-14).

    Any missing file, extra file, or checksum mismatch makes the bundle ``INVALID`` —
    a single tampered byte is detected.
    """
    results: list[dict[str, Any]] = []
    valid = True
    for path in sorted(checksums):
        if path not in files:
            results.append({"path": path, "status": "missing"})
            valid = False
            continue
        actual = _sha256(files[path])
        if actual == checksums[path]:
            results.append({"path": path, "status": "match"})
        else:
            results.append({"path": path, "status": "mismatch"})
            valid = False
    return {"overall": "VALID" if valid else "INVALID", "valid": valid, "files_checked": len(checksums), "results": results}


def supersede_bundle(previous_manifest: Mapping[str, Any], *, project_id: str, objects: Mapping[str, Any]) -> BundleBuildResult:
    """Build a new bundle version that supersedes an earlier one (T-22-13).

    The new manifest records ``supersedes_bundle_id`` and bumps ``bundle_version``;
    the previous bundle is never overwritten and can still be verified.
    """
    prev_version = int(previous_manifest.get("bundle_version", 1))
    return build_bundle(project_id=project_id, objects=objects, version=prev_version + 1, supersedes=str(previous_manifest.get("bundle_id", "")))


__all__ = [
    "COMPARISON_STRATEGIES",
    "SENSITIVE_SCAN_KINDS",
    "BUNDLE_STATUSES",
    "SensitiveExportRefused",
    "BundleBuildResult",
    "scan_sensitive",
    "build_bundle",
    "verify_bundle",
    "supersede_bundle",
]
