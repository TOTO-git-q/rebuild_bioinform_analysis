"""Method registry + MethodContracts.

A MethodContract is the *only* thing that authorises an analysis node to run: it
declares the data the method accepts, the minimum statistical design, the QC it
requires, and — critically — the maximum claim level its outputs can ever
support (``claim_capability``).  "Having code that runs" is never sufficient;
the workflow compiler must bind every analysis task to an ACTIVE contract and a
passing CompatibilityDecision (requirement spec, stage 8).
"""

from __future__ import annotations

from typing import Any

from ..methods.bulk_deg import BulkDegMethod


def build_method_registry() -> dict[str, Any]:
    """Return {method_id: method adapter} for all registered methods."""
    methods = [BulkDegMethod()]
    return {m.method_id: m for m in methods}


def get_method(method_id: str) -> Any:
    registry = build_method_registry()
    if method_id not in registry:
        raise KeyError(f"unknown method_id: {method_id} (registered: {sorted(registry)})")
    return registry[method_id]


def compatibility_decision(method_id: str, dataset_profile: dict[str, Any]) -> dict[str, Any]:
    """Deterministically decide whether a method can run on a dataset profile.

    Hard contract conditions (modality, minimum replicates, group count) are
    checked here; an Agent may rank within the compatible set but may never
    override a hard failure (requirement spec, stage 8 gate).
    """
    method = get_method(method_id)
    contract = method.contract()
    reasons: list[str] = []

    modality = str(dataset_profile.get("modality", "")).lower()
    accepted = [m.lower() for m in contract["accepted_input_types"]]
    if modality not in accepted:
        reasons.append(f"modality {modality!r} not in accepted_input_types {accepted}")

    design = contract["minimum_sample_design"]
    group_sizes = dataset_profile.get("group_sizes") or {}
    if len(group_sizes) < design["groups"]:
        reasons.append(f"requires >= {design['groups']} groups, profile has {len(group_sizes)}")
    too_small = {g: n for g, n in group_sizes.items() if n < design["min_replicates_per_group"]}
    if too_small:
        reasons.append(f"groups below {design['min_replicates_per_group']} replicates: {too_small}")

    compatible = not reasons
    return {
        "method_contract_id": contract["method_contract_id"],
        "method_id": method_id,
        "dataset_id": dataset_profile.get("dataset_id", ""),
        "compatible": compatible,
        "reason": "compatible with hard contract conditions" if compatible else "; ".join(reasons),
        "claim_capability": contract["claim_capability"],
    }
