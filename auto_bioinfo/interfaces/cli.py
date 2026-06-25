"""Thin CLI over the core services (``run`` / ``resume`` / ``inspect`` / ``export`` / ``validate``).

The CLI carries no business logic: it only wires arguments into the same
``Pipeline`` / store / reproduction services the (future) API would use.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..core.store import load_events, load_project_state
from ..pipeline import Pipeline
from ..reproduction.bundle import build_reproduction_bundle, compare_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bioauto", description="Automated bioinformatics closed-loop core (lightweight, offline).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Create a project and run the closed loop end to end.")
    p_run.add_argument("--project", required=True, help="Project directory to create/use.")
    p_run.add_argument("--question", required=True, help="Natural-language research question.")

    p_resume = sub.add_parser("resume", help="Resume an existing project from its persisted stage.")
    p_resume.add_argument("--project", required=True)

    p_inspect = sub.add_parser("inspect", help="Show stage, claims, QC and alignment for a project.")
    p_inspect.add_argument("--project", required=True)
    p_inspect.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    p_export = sub.add_parser("export", help="Build/locate the reproduction bundle.")
    p_export.add_argument("--project", required=True)

    p_validate = sub.add_parser("validate", help="Replay the event log and re-verify the reproduction bundle checksums.")
    p_validate.add_argument("--project", required=True)

    args = parser.parse_args(argv)
    project = Path(args.project)

    if args.command == "run":
        summary = Pipeline().run(project, args.question)
        _print_summary(summary)
        return 0 if summary["current_stage"] in {"COMPLETED", "HUMAN_REVIEW_REQUIRED"} else 0

    if args.command == "resume":
        summary = Pipeline().run(project)
        _print_summary(summary)
        return 0

    if args.command == "inspect":
        summary = Pipeline().inspect(project)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_summary(summary)
        return 0

    if args.command == "export":
        manifest = build_reproduction_bundle(project)
        print(f"Reproduction bundle: {project / manifest['bundle_dir']}")
        print(f"  files: {len(manifest['files'])}  ·  id: {manifest['reproduction_bundle_id']}")
        return 0

    if args.command == "validate":
        result = _validate(project)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    return 2


def _validate(project: Path) -> dict:
    state = load_project_state(project)
    events = load_events(project)
    # The current stage must be the last stage the event log transitioned into.
    event_stages = [e["next_stage"] for e in events if e.get("next_stage")]
    replay_ok = bool(event_stages) and event_stages[-1] == state["current_stage"]
    bundle_dir = project / "reproduction_bundle"
    bundle = compare_bundle(bundle_dir) if bundle_dir.exists() else {"overall_level": "NOT_COMPARABLE", "files_checked": 0}
    ok = replay_ok and bundle["overall_level"] in {"BITWISE_IDENTICAL", "NUMERICALLY_EQUIVALENT_WITHIN_TOLERANCE"}
    return {
        "ok": ok,
        "project_id": state["project_id"],
        "current_stage": state["current_stage"],
        "event_replay_matches_state": replay_ok,
        "event_count": len(events),
        "reproduction_bundle": bundle,
    }


def _print_summary(summary: dict) -> None:
    print(f"project : {summary['project_id']}")
    print(f"stage   : {summary['current_stage']}")
    print(f"history : {' -> '.join(summary.get('stage_history', []))}")
    claims = summary.get("claims", [])
    print(f"claims  : {len(claims)}")
    for c in claims:
        print(f"   ({c['claim_level']}) {c['text']}")
    alignment = summary.get("alignment", {})
    if alignment:
        print(f"alignment: {alignment.get('final_decision')}")
    report = summary.get("final_report", {})
    if report:
        print(f"report  : {report.get('report_paths', {}).get('markdown')}")
    bundle = summary.get("reproduction_bundle", {})
    if bundle:
        print(f"bundle  : reproduction_bundle/ ({len(bundle.get('files', []))} files)")


if __name__ == "__main__":
    sys.exit(main())
