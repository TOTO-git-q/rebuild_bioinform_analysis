"""Append-only JSONL persistence for execution-stage records.

TaskRuns, QCReports, EvidenceItems and Claims are each stored in their own
append-only ``state/*.jsonl`` ledger.  Appends are idempotent on the record's
stable id: re-appending the same record (e.g. on resume / a duplicate message)
does not create a second row, which is what makes the pipeline safe to re-run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LEDGERS = {
    "task_run": ("task_runs.jsonl", "task_run_id"),
    "qc_report": ("qc_reports.jsonl", "qc_report_id"),
    "evidence_item": ("evidence_items.jsonl", "evidence_item_id"),
    "claim": ("claims.jsonl", "claim_id"),
}


def _path(project_dir: str | Path, kind: str) -> Path:
    filename, _ = _LEDGERS[kind]
    path = Path(project_dir) / "state" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append(project_dir: str | Path, kind: str, record: dict[str, Any]) -> dict[str, Any]:
    _, id_field = _LEDGERS[kind]
    record_id = record.get(id_field)
    path = _path(project_dir, kind)
    existing_ids = {row.get(id_field) for row in _load(project_dir, kind)}
    if record_id in existing_ids:
        return record  # idempotent: already recorded
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def _load(project_dir: str | Path, kind: str) -> list[dict[str, Any]]:
    filename, _ = _LEDGERS[kind]
    path = Path(project_dir) / "state" / filename
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_task_run(project_dir: str | Path, record: dict[str, Any]) -> dict[str, Any]:
    return _append(project_dir, "task_run", record)


def load_task_runs(project_dir: str | Path) -> list[dict[str, Any]]:
    return _load(project_dir, "task_run")


def write_qc_report(project_dir: str | Path, record: dict[str, Any]) -> dict[str, Any]:
    return _append(project_dir, "qc_report", record)


def load_qc_reports(project_dir: str | Path) -> list[dict[str, Any]]:
    return _load(project_dir, "qc_report")


def write_evidence_item(project_dir: str | Path, record: dict[str, Any]) -> dict[str, Any]:
    return _append(project_dir, "evidence_item", record)


def load_evidence_items(project_dir: str | Path) -> list[dict[str, Any]]:
    return _load(project_dir, "evidence_item")


def write_claim(project_dir: str | Path, record: dict[str, Any]) -> dict[str, Any]:
    return _append(project_dir, "claim", record)


def load_claims(project_dir: str | Path) -> list[dict[str, Any]]:
    return _load(project_dir, "claim")
