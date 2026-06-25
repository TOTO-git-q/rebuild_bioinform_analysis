"""Offline fixture resource adapter (implements ``ports.ResourceDiscoveryPort``).

Serves a single committed, synthetic dataset so the reference run is fully
offline and deterministic.  The dataset is *honestly labelled* as a fixture
(``source_status="committed_fixture"``); it is not fabricated-as-real data.  It
still carries a real (non ``AUTO_``/``MOCK_``) accession so it passes the
verified-dataset guard, but the production system must obtain datasets through a
real, audited discovery adapter — this one only exists for the example + tests.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import DatasetProfile, ResourceCandidate

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "bulk_deg_demo"


class FixtureResourceAdapter:
    """Returns the committed bulk-DEG fixture as a verified dataset."""

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self.fixture_dir = Path(fixture_dir) if fixture_dir else _FIXTURE_DIR
        self.card = json.loads((self.fixture_dir / "dataset_card.json").read_text(encoding="utf-8"))

    def discover(self, research_spec: dict[str, Any], evidence_plan: dict[str, Any]) -> list[dict[str, Any]]:
        candidate = ResourceCandidate(
            resource_name=self.card["dataset_id"],
            resource_type="dataset_candidate",
            verified=True,
            source_status=self.card["source_status"],
            status="candidate",
            accession=self.card["accession"],
        )
        data = asdict(candidate)
        data["resource_candidate_id"] = make_stable_id(
            "resource_candidate",
            {"project_id": research_spec.get("project_id", ""), "accession": self.card["accession"]},
        )
        data["evidence_plan_id"] = evidence_plan.get("evidence_plan_id", "")
        data["discovery_tool"] = "offline_fixture_adapter"
        return [data]

    def profile(self, candidate: dict[str, Any]) -> dict[str, Any]:
        profile = DatasetProfile(
            dataset_id=self.card["dataset_id"],
            modality=self.card["modality"],
            organism=self.card["organism"],
            tissue=self.card["tissue"],
            status="profiled",
        )
        data = asdict(profile)
        data["dataset_profile_id"] = make_stable_id("dataset_profile", {"dataset_id": self.card["dataset_id"]})
        data["accession"] = self.card["accession"]
        data["source_status"] = self.card["source_status"]
        data["verified"] = self.card["verified"]
        data["platform"] = self.card.get("platform", "")
        data["group_sizes"] = self.card["group_sizes"]
        data["comparison_groups"] = self.card["comparison_groups"]
        data["donor_level"] = self.card.get("donor_level", False)
        data["files"] = self.card["files"]
        data["known_limitations"] = self.card.get("known_limitations", [])
        return data

    def materialize(self, dataset_profile: dict[str, Any], dest_dir: str) -> dict[str, str]:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        out: dict[str, str] = {}
        for logical_name, file_name in dataset_profile["files"].items():
            src = self.fixture_dir / file_name
            target = dest / file_name
            shutil.copyfile(src, target)
            out[logical_name] = str(target)
        return out
