from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .ids import make_stable_id
from .schemas import now_iso

ARTIFACT_REGISTRY_SCHEMA_VERSION = "v5.artifact_registry/0.1"
DEFAULT_CHECKSUM_CHUNK_BYTES = 1024 * 1024


def compute_file_sha256(path: str | Path) -> str:
    import hashlib

    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(DEFAULT_CHECKSUM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_manifest(
    project_dir: str | Path,
    relative_path: str | Path,
    producer: str,
    artifact_type: str,
    expected_by_task_ids: list[str],
    supports_subquestion_ids: list[str],
    *,
    producer_run_id: str = "",
    schema_name: str = "",
    evidence_item_refs: list[str] | None = None,
    qc_status: str = "pending",
    limitations: list[str] | None = None,
    is_placeholder: bool = False,
) -> dict[str, Any]:
    project_dir = Path(project_dir)
    relative_path_text = str(relative_path).replace("\\", "/")
    artifact_path = project_dir / relative_path_text
    exists = artifact_path.exists() and artifact_path.is_file()
    checksum = compute_file_sha256(artifact_path) if exists else ""
    size_bytes = artifact_path.stat().st_size if exists else 0
    table_profile = _profile_table_artifact(artifact_path) if exists else {}
    artifact_id = make_stable_id(
        "artifact",
        {
            "project_id": project_dir.name,
            "path": relative_path_text,
            "checksum_sha256": checksum,
            "is_placeholder": is_placeholder,
            "artifact_type": artifact_type,
        },
    )
    manifest = {
        "schema_version": ARTIFACT_REGISTRY_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "project_id": project_dir.name,
        "path": relative_path_text,
        "artifact_type": artifact_type,
        "producer_agent_or_task": producer,
        "producer_run_id": producer_run_id,
        "created_at": now_iso(),
        "checksum_sha256": checksum,
        "size_bytes": size_bytes,
        "exists": exists,
        "schema_name": schema_name or _infer_schema_name(relative_path_text, artifact_type),
        "expected_by_task_ids": expected_by_task_ids,
        "supports_subquestion_ids": supports_subquestion_ids,
        "evidence_item_refs": evidence_item_refs or [],
        "qc_status": qc_status,
        "limitations": limitations or [],
        "is_placeholder": is_placeholder,
    }
    manifest.update(table_profile)
    return manifest


def write_artifact_manifest(project_dir: str | Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = Path(project_dir) / "state" / "artifact_registry.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n")
    return manifest


def load_artifact_registry(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir) / "state" / "artifact_registry.jsonl"
    if not path.exists():
        return []
    manifests = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            manifests.append(json.loads(line))
    return manifests


def register_artifact(
    project_dir: str | Path,
    relative_path: str | Path,
    producer: str,
    artifact_type: str,
    expected_by_task_ids: list[str],
    supports_subquestion_ids: list[str],
    **kwargs: Any,
) -> dict[str, Any]:
    manifest = build_artifact_manifest(
        project_dir,
        relative_path,
        producer,
        artifact_type,
        expected_by_task_ids,
        supports_subquestion_ids,
        **kwargs,
    )
    write_artifact_manifest(project_dir, manifest)
    return manifest


def validate_artifact_for_evidence(manifest: dict[str, Any]) -> list[str]:
    required = [
        "artifact_id",
        "project_id",
        "path",
        "artifact_type",
        "producer_agent_or_task",
        "producer_run_id",
        "created_at",
        "checksum_sha256",
        "size_bytes",
        "exists",
        "schema_name",
        "expected_by_task_ids",
        "supports_subquestion_ids",
        "evidence_item_refs",
        "qc_status",
        "limitations",
        "is_placeholder",
    ]
    errors = []
    for field in required:
        if field not in manifest or manifest[field] is None:
            errors.append(f"{field}: missing required field")
    if manifest.get("exists") is not True:
        errors.append("artifact cannot enter evidence synthesis when exists=false")
    if manifest.get("is_placeholder") is True:
        errors.append("artifact cannot enter evidence synthesis when is_placeholder=true")
    if not manifest.get("checksum_sha256"):
        errors.append("artifact requires checksum_sha256 based on file content")
    if manifest.get("qc_status") in {"fail", "failed", "rejected"}:
        errors.append(f"artifact cannot enter evidence synthesis when qc_status={manifest.get('qc_status')}")
    if not isinstance(manifest.get("expected_by_task_ids"), list):
        errors.append("expected_by_task_ids: expected list")
    if not isinstance(manifest.get("supports_subquestion_ids"), list):
        errors.append("supports_subquestion_ids: expected list")
    if not isinstance(manifest.get("evidence_item_refs"), list):
        errors.append("evidence_item_refs: expected list")
    if not isinstance(manifest.get("limitations"), list):
        errors.append("limitations: expected list")
    return errors


def _profile_table_artifact(path: Path, max_rows: int = 10000) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in {".csv", ".tsv"}:
        return {}
    delimiter = "," if suffix == ".csv" else "\t"
    row_count = 0
    column_names: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            column_names = next(reader)
        except StopIteration:
            return {"row_count": 0, "column_names": []}
        for row_count, _ in enumerate(reader, start=1):
            if row_count >= max_rows:
                return {"row_count": row_count, "row_count_is_truncated": True, "column_names": column_names}
    return {"row_count": row_count, "row_count_is_truncated": False, "column_names": column_names}


def _infer_schema_name(relative_path: str, artifact_type: str) -> str:
    suffix = Path(relative_path).suffix.lower().lstrip(".")
    if suffix in {"csv", "tsv"}:
        return f"{artifact_type}_{suffix}_table"
    if suffix:
        return f"{artifact_type}_{suffix}"
    return artifact_type or "artifact"
