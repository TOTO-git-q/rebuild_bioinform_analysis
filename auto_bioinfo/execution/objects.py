"""Typed object persistence (one latest version per object type per project).

The vertical slice produces exactly one of each planning object, so they are
written to stable, type-named files under ``state/objects/``.  This keeps resume
trivial: any stage can reload the objects it needs by name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _objects_dir(project_dir: str | Path) -> Path:
    path = Path(project_dir) / "state" / "objects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_object(project_dir: str | Path, name: str, payload: Any) -> dict[str, Any]:
    path = _objects_dir(project_dir) / f"{name}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return object_ref(project_dir, name, payload)


def read_object(project_dir: str | Path, name: str, default: Any = None) -> Any:
    path = _objects_dir(project_dir) / f"{name}.json"
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def object_ref(project_dir: str | Path, name: str, payload: Any = None) -> dict[str, Any]:
    payload = payload if payload is not None else read_object(project_dir, name, {})
    object_id = ""
    if isinstance(payload, dict):
        for key in (f"{name}_id", "research_spec_id", "scope_bundle_id", "evidence_plan_id", "dataset_profile_id", "dataset_manifest_id", "workflow_plan_id"):
            if payload.get(key):
                object_id = payload[key]
                break
    object_type = "".join(part.capitalize() for part in name.split("_"))
    return {"object_type": object_type, "object_id": object_id, "path": f"state/objects/{name}.json"}
