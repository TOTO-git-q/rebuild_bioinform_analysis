"""Inert capability-grant *descriptor* registry (clean-room, deny-by-default).

This module records the capability-grant taxonomy recovered by static analysis
(see ``docs/rebuild/agent_runtime_capability_classes.md``) as **inert data**. A
descriptor documents *what a future approval gate would require*; it grants
**nothing** at runtime.

Design guarantees (proven in ``tests/test_capability_registry.py``):

* No descriptor is executable. ``CapabilityGrantDescriptor.is_executable()`` is
  always ``False`` and there is no code path that runs a capability.
* **Deny-over-allow**: ``resolve_decision`` returns ``"deny"`` whenever any deny
  reason is present *or* a required binding is missing — an ``allow`` intent can
  never override a deny. The best possible outcome is
  ``"eligible_for_manual_approval"``, which still requires an out-of-band human
  gate before anything could run.

Nothing here opens a socket, spawns a process, or touches the network.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

CAPABILITY_REGISTRY_VERSION = "0.1.0-cleanroom"

# Decision vocabulary. Note there is deliberately no "execute" / "granted"
# terminal state: the strongest outcome merely marks a request as eligible for a
# separate manual approval.
DECISION_DENY = "deny"
DECISION_ELIGIBLE_FOR_MANUAL_APPROVAL = "eligible_for_manual_approval"


@dataclass(frozen=True)
class CapabilityGrantDescriptor:
    """Inert descriptor of a capability gate. Grants no execution."""

    grant_id: str
    title: str
    capability: str
    approval_gate: str
    required_bindings: tuple[str, ...]
    denial_defaults: tuple[str, ...]
    project_subsystem: str

    # Hard-wired: a descriptor is never executable. This is a field with a fixed
    # default rather than a method-only flag so it is visible in ``to_dict``.
    executable_by_default: bool = False

    def is_executable(self) -> bool:
        """Descriptors never authorise execution."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Clean-room grant taxonomy. Each grant is fail-closed: it lists the bindings a
# future request must supply and the default reasons it is denied.
_GRANTS: tuple[CapabilityGrantDescriptor, ...] = (
    CapabilityGrantDescriptor(
        "grant_network_query_plan",
        "Network query planning only",
        "network.query_plan",
        "A1_NETWORK_QUERY_PLAN",
        ("project_id", "tool_id", "query_hash", "caller_id"),
        ("missing_binding", "unknown_tool", "sensitive_argument"),
        "PublicBioToolAdapter",
    ),
    CapabilityGrantDescriptor(
        "grant_dataset_materialization",
        "Dataset materialization",
        "data.materialize",
        "A2_DATASET_MATERIALIZATION",
        ("project_id", "dataset_id", "dataset_version", "destination_scope"),
        ("unverified_dataset", "missing_license", "human_data_without_authorization"),
        "ResourceDiscoveryPort",
    ),
    CapabilityGrantDescriptor(
        "grant_local_method_exec",
        "Local deterministic method execution",
        "exec.local_method",
        "A1_LOCAL_EXEC",
        ("project_id", "method_contract_id", "task_id", "input_hashes"),
        ("contract_mismatch", "path_scope_violation", "missing_input_hash"),
        "AnalysisMethodPort",
    ),
    CapabilityGrantDescriptor(
        "grant_container_exec",
        "Container or workflow execution",
        "exec.container",
        "A2_CONTAINER_EXEC",
        ("project_id", "workflow_id", "image_digest", "task_id"),
        ("mutable_image_tag", "missing_resource_limits", "unapproved_mount"),
        "ExecutionProfile",
    ),
    CapabilityGrantDescriptor(
        "grant_remote_exec",
        "Remote compute execution",
        "exec.remote",
        "A3_REMOTE_EXEC",
        ("project_id", "provider", "job_spec_hash", "cost_limit"),
        ("missing_cost_limit", "missing_credentials_policy", "unapproved_provider"),
        "ExecutionProfile",
    ),
    CapabilityGrantDescriptor(
        "grant_connector_attach",
        "Attach a connector manifest",
        "connector.attach",
        "A2_CONNECTOR_ATTACH",
        ("project_id", "connector_id", "manifest_hash", "transport"),
        ("unknown_transport", "missing_terms", "wildcard_connector"),
        "ConnectorRegistry",
    ),
    CapabilityGrantDescriptor(
        "grant_export_bundle",
        "Export reproduction or report bundle",
        "data.export",
        "A2_EXPORT",
        ("project_id", "bundle_id", "sensitivity_scan_hash"),
        ("missing_scan", "restricted_data_present", "unverified_artifact_hash"),
        "ReportExporter",
    ),
)

_GRANTS_BY_ID: dict[str, CapabilityGrantDescriptor] = {g.grant_id: g for g in _GRANTS}


def grant_descriptors() -> tuple[CapabilityGrantDescriptor, ...]:
    """Return the full inert grant taxonomy (stable order)."""
    return _GRANTS


def grant_by_id(grant_id: str) -> CapabilityGrantDescriptor:
    try:
        return _GRANTS_BY_ID[grant_id]
    except KeyError as exc:
        raise KeyError(f"unknown capability grant: {grant_id!r}") from exc


def resolve_decision(
    grant_id: str,
    *,
    provided_bindings: Iterable[str] = (),
    deny_reasons: Iterable[str] = (),
    allow_intent: bool = False,
) -> dict[str, Any]:
    """Resolve a hypothetical grant request; **deny always wins**.

    ``allow_intent`` models a caller *asking* to allow the capability. It can
    never override a deny reason or a missing required binding. The strongest
    result is ``eligible_for_manual_approval`` — never "execute".
    """
    grant = grant_by_id(grant_id)
    provided = set(provided_bindings)
    reasons = list(deny_reasons)

    missing = [b for b in grant.required_bindings if b not in provided]
    if missing:
        reasons.append(f"missing_binding:{','.join(missing)}")

    if reasons:  # deny-over-allow: any reason denies, regardless of allow_intent
        decision = DECISION_DENY
    elif allow_intent:
        decision = DECISION_ELIGIBLE_FOR_MANUAL_APPROVAL
    else:
        # No explicit allow intent -> stay denied by default.
        decision = DECISION_DENY
        reasons.append("no_allow_intent_default_deny")

    return {
        "grant_id": grant.grant_id,
        "capability": grant.capability,
        "approval_gate": grant.approval_gate,
        "decision": decision,
        "reasons": reasons,
        "executable": False,  # never; this registry authorises no execution
        "version": CAPABILITY_REGISTRY_VERSION,
    }


def build_capability_registry(grant_ids: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """Return ``{grant_id: descriptor dict}`` for interface completeness."""
    ids = list(grant_ids) if grant_ids is not None else list(_GRANTS_BY_ID)
    return {gid: grant_by_id(gid).to_dict() for gid in ids}


def assert_no_executable_grants(registry: Mapping[str, Any] | None = None) -> bool:
    """Return ``True`` iff every descriptor is non-executable (used by tests)."""
    grants = _GRANTS if registry is None else (grant_by_id(gid) for gid in registry)
    return all(not g.is_executable() and g.executable_by_default is False for g in grants)
