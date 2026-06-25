"""Constrained final report builder.

Renders a human-readable + machine-readable report strictly from *already
synthesised* claims, evidence and QC.  It never creates new claims, never raises
a claim level, and never free-summarises raw files — every reported statement
maps back to a Claim id (requirement spec, stage 17).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core.ids import make_stable_id
from .core.provenance import authoritative_release
from .core.schemas import now_iso
from .execution.objects import read_object
from .execution.runs import load_claims, load_evidence_items, load_qc_reports


def build_final_report(project_dir: str | Path) -> dict[str, Any]:
    project_dir = Path(project_dir)
    spec = read_object(project_dir, "research_spec", {})
    scope = read_object(project_dir, "scope_bundle", {})
    profile = read_object(project_dir, "dataset_profile", {})
    manifest = read_object(project_dir, "dataset_manifest", {})
    workflow = read_object(project_dir, "workflow_plan", {})
    method_result = read_object(project_dir, "method_result", {})
    subs = read_object(project_dir, "subquestions", [])
    alignment = read_object(project_dir, "question_alignment_report", {})
    claims = load_claims(project_dir)
    evidence = load_evidence_items(project_dir)
    qc_reports = load_qc_reports(project_dir)
    policy = read_object(project_dir, "project_policy", {})
    execution_mode = policy.get("execution_mode", "DEMO")
    # Authoritative eligibility gate: recompute from the persisted decision +
    # active policy; the cached flag on a Claim is only a display cache.
    release = authoritative_release(
        read_object(project_dir, "scientific_eligibility_decision", {}),
        policy=policy,
        claims=claims,
        evidence_items=evidence,
        artifact=read_object(project_dir, "registered_artifact", {}),
        dataset_profile=profile,
    )
    eligible = release["scientific_output_eligible"]
    release_status = release["release_status"]

    structured = {
        "schema_version": "auto_bioinfo.final_report/0.1",
        "project_id": project_dir.name,
        "execution_mode": execution_mode,
        "release_status": release_status,
        "scientific_output_eligible": eligible,
        "demonstration_only": not eligible,
        "original_question": spec.get("research_question", ""),
        "normalized_spec": {k: spec.get(k) for k in ("organism", "tissue", "comparison_groups", "claim_ceiling", "open_questions", "assumptions")},
        "scope": {"species": scope.get("species", []), "tissue": scope.get("tissues", []), "condition": scope.get("conditions", [])},
        "dataset": {"dataset_id": profile.get("dataset_id"), "accession": profile.get("accession"), "source_status": profile.get("source_status"), "file_checksums": manifest.get("file_checksums", {})},
        "method": {"workflow": workflow.get("workflow_name"), "method_contract_id": workflow.get("method_contract_id"), "params": method_result.get("params", {}), "software_versions": method_result.get("software_versions", {})},
        "qc_summary": [{"qc_report_id": r["qc_report_id"], "overall_status": r["overall_status"], "decision": r.get("decision")} for r in qc_reports],
        "subquestion_answers": _subquestion_answers(subs, claims, alignment),
        "claims": claims,
        "evidence_items": evidence,
        "alignment_decision": alignment.get("final_decision", ""),
        "limitations": sorted({lim for c in claims for lim in c.get("limitations", [])}),
        "unanswered": [c for c in alignment.get("coverage_by_subquestion", []) if c.get("status") != "covered"],
        "generated_at": now_iso(),
    }

    reports_dir = project_dir / "state" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "report.json").write_text(json.dumps(structured, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md = _render_markdown(structured)
    (reports_dir / "report.md").write_text(md, encoding="utf-8")

    return {
        "final_report_id": make_stable_id("final_report", {"project_id": project_dir.name, "claim_ids": [c["claim_id"] for c in claims]}),
        "report_paths": {"markdown": "state/reports/report.md", "structured_json": "state/reports/report.json"},
        "claim_ids": [c["claim_id"] for c in claims],
        "evidence_item_ids": [e["evidence_item_id"] for e in evidence],
        "alignment_decision": alignment.get("final_decision", ""),
        "execution_mode": execution_mode,
        "release_status": release_status,
        "scientific_output_eligible": eligible,
        "generated_at": now_iso(),
        "status": "draft" if alignment.get("final_decision") == "approve" else "review_required",
    }


def _subquestion_answers(subs: list[dict[str, Any]], claims: list[dict[str, Any]], alignment: dict[str, Any]) -> list[dict[str, Any]]:
    coverage = {c["subquestion_id"]: c for c in alignment.get("coverage_by_subquestion", [])}
    out = []
    for sub in subs:
        sid = sub["subquestion_id"]
        supporting = [c for c in claims if sid in c.get("supports_subquestion_ids", [])]
        out.append(
            {
                "subquestion_id": sid,
                "question": sub.get("question", ""),
                "status": coverage.get(sid, {}).get("status", "unknown"),
                "claim_ids": [c["claim_id"] for c in supporting],
                "claim_texts": [c["text"] for c in supporting],
            }
        )
    return out


def _render_markdown(s: dict[str, Any]) -> str:
    watermark = (
        f"> ⚠️ **{s['release_status']}** — execution_mode = `{s['execution_mode']}`, "
        f"scientific_output_eligible = `{s['scientific_output_eligible']}`.\n"
        f"> The claims below are NOT formal scientific evidence and must not be exported as research results."
        if not s["scientific_output_eligible"]
        else f"> Execution mode: `{s['execution_mode']}` · release_status: `{s['release_status']}`."
    )
    lines = [
        f"# Auto-Bioinfo Report — {s['project_id']}",
        "",
        watermark,
        "",
        f"_Generated: {s['generated_at']}  ·  Alignment decision: **{s['alignment_decision']}**_",
        "",
        "## 1. Question",
        f"- Original: {s['original_question']}",
        f"- Comparison groups: {s['normalized_spec'].get('comparison_groups')}",
        f"- Claim ceiling: {s['normalized_spec'].get('claim_ceiling')}",
        "",
        "## 2. Dataset",
        f"- `{s['dataset'].get('dataset_id')}` ({s['dataset'].get('accession')}, source: {s['dataset'].get('source_status')})",
        f"- File checksums: {s['dataset'].get('file_checksums')}",
        "",
        "## 3. Method",
        f"- {s['method'].get('workflow')} · contract `{s['method'].get('method_contract_id')}`",
        f"- Params: {s['method'].get('params')}",
        f"- Software: {s['method'].get('software_versions')}",
        "",
        "## 4. QC summary",
    ]
    for q in s["qc_summary"]:
        lines.append(f"- {q['qc_report_id']}: **{q['overall_status']}** ({q['decision']})")
    lines += ["", "## 5. Sub-question answers"]
    for ans in s["subquestion_answers"]:
        lines.append(f"- [{ans['status']}] {ans['question']}")
        for text in ans["claim_texts"]:
            lines.append(f"    - {text}")
    lines += ["", "## 6. Claims (bounded by ceiling)"]
    for c in s["claims"]:
        lines.append(f"- ({c['claim_level']}) {c['text']}  ·  evidence: {c['evidence_item_refs']}")
    lines += ["", "## 7. Limitations"]
    lines += [f"- {lim}" for lim in s["limitations"]]
    if s["unanswered"]:
        lines += ["", "## 8. Unanswered / not covered"]
        lines += [f"- {u['subquestion_id']}: {u['status']}" for u in s["unanswered"]]
    lines += ["", "## 9. Traceability", "Every claim above references EvidenceItem ids, which reference QC-passed Artifact ids with content checksums, produced by a recorded TaskRun bound to a MethodContract. See `state/` ledgers and the reproduction bundle."]
    return "\n".join(lines) + "\n"
