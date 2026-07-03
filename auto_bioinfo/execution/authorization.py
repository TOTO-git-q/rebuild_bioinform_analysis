"""Execution authorization + preflight checks as inert control objects (WP-13).

Before any task may be *delivered* for execution, this module runs a deterministic
preflight over structured facts — input-artifact integrity, environment
resolvability, resource quota, network/sensitivity policy, output isolation, and
version/seed freeze — and only then mints an immutable
:class:`ExecutionAuthorization` snapshot (T-13-01..T-13-09).  A FAIL check, a
missing required approval, or a policy violation blocks authorization: nothing is
authorized without every gate passing.

Everything here is a pure function of its in-memory inputs: no real filesystem
read, no checksum computation, no container resolution, no network, no clock
read.  The caller supplies recorded facts (an artifact's recorded checksum, a
pinned implementation reference, the granted approval gates); the checks only
*compare* them.  Produced snapshots carry an empty ``created_at`` so
byte-identical inputs yield byte-identical authorizations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any

from ..core.ids import hash_payload, make_stable_id


def _freeze(value: Any) -> Any:
    """Recursively convert mappings/sequences into read-only structures.

    ``dict`` becomes a :class:`~types.MappingProxyType` and ``list``/``tuple``
    becomes a ``tuple``, all the way down, so a stored snapshot cannot be
    mutated in place through the object it is attached to.
    """
    if isinstance(value, (dict, MappingProxyType)):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    """Recursively convert frozen structures back into plain dict/list copies.

    Used by ``to_dict()`` so callers receive a defensive, JSON-friendly copy
    they may mutate without touching the immutable snapshot.
    """
    if isinstance(value, (dict, MappingProxyType)):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


# --- Bounded check vocabulary ------------------------------------------------
CHECK_PASS = "PASS"
CHECK_WARN = "WARN"
CHECK_FAIL = "FAIL"
CHECK_STATUSES = (CHECK_PASS, CHECK_WARN, CHECK_FAIL)

# Preflight check categories (bounded).
CAT_INPUT_INTEGRITY = "input_integrity"
CAT_ENVIRONMENT = "environment"
CAT_RESOURCES = "resources"
CAT_NETWORK_SECURITY = "network_security"
CAT_OUTPUT_ISOLATION = "output_isolation"
CAT_VERSION_FREEZE = "version_freeze"
CAT_APPROVAL = "approval"
CHECK_CATEGORIES = (
    CAT_INPUT_INTEGRITY,
    CAT_ENVIRONMENT,
    CAT_RESOURCES,
    CAT_NETWORK_SECURITY,
    CAT_OUTPUT_ISOLATION,
    CAT_VERSION_FREEZE,
    CAT_APPROVAL,
)

# --- Bounded authorization decision ------------------------------------------
AUTH_AUTHORIZED = "AUTHORIZED"
AUTH_BLOCKED = "BLOCKED"
AUTH_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
AUTH_DECISIONS = (AUTH_AUTHORIZED, AUTH_BLOCKED, AUTH_APPROVAL_REQUIRED)

# Artifact states that count as usable input (mirrors the WP-15 registry).
_VALID_ARTIFACT_STATES = ("VALID",)


@dataclass(frozen=True)
class PreflightFinding:
    """One structured preflight result (T-13-01)."""

    check_id: str
    category: str
    status: str
    reason: str
    task_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreflightReport:
    """The full preflight over a workflow plan (T-13-01)."""

    findings: list[PreflightFinding] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(f.status == CHECK_FAIL for f in self.findings)

    @property
    def warned(self) -> bool:
        return any(f.status == CHECK_WARN for f in self.findings)

    def by_status(self, status: str) -> list[PreflightFinding]:
        return [f for f in self.findings if f.status == status]

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "failed": self.failed,
            "warned": self.warned,
            "counts": {s: len(self.by_status(s)) for s in CHECK_STATUSES},
        }


@dataclass(frozen=True)
class AuthorizationRequest:
    """The recorded facts a preflight compares (never reads the world itself).

    ``task_packets`` are the compiled packets (each with ``task_id`` /
    ``expected_inputs`` / ``execution_fields`` / optional ``params`` and
    ``method_id``).  ``artifact_facts`` maps an input artifact id to its recorded
    ``{state, checksum_sha256, exists}``.  ``implementation_facts`` maps a method
    id to its recorded ``{code_commit, container_digest}``.  ``resource_status``
    records the available quota.  ``policy`` is a ProjectPolicy projection.
    ``granted_gates`` are the approval gates a human has granted.
    """

    project_id: str
    workflow_plan: dict[str, Any]
    task_packets: list[dict[str, Any]]
    artifact_facts: dict[str, dict[str, Any]] = field(default_factory=dict)
    implementation_facts: dict[str, dict[str, Any]] = field(default_factory=dict)
    resource_status: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    granted_gates: frozenset[str] = frozenset()
    required_gates: frozenset[str] = frozenset()


_FLOATING = ("latest", "", "head", "main", "master")


def _check_input_integrity(request: AuthorizationRequest) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    produced = {aid for outs in request.workflow_plan.get("expected_outputs", {}).values() for aid in outs}
    for packet in request.task_packets:
        task_id = str(packet.get("task_id", ""))
        for aid in packet.get("expected_inputs", []) or packet.get("planned_inputs", []):
            if aid in produced:
                continue  # produced by an upstream node; validated when that node runs
            fact = request.artifact_facts.get(aid)
            if fact is None:
                findings.append(
                    PreflightFinding(f"input_present::{aid}", CAT_INPUT_INTEGRITY, CHECK_FAIL, f"input artifact {aid!r} is not registered", task_id)
                )
                continue
            if fact.get("state") not in _VALID_ARTIFACT_STATES:
                findings.append(
                    PreflightFinding(
                        f"input_valid::{aid}", CAT_INPUT_INTEGRITY, CHECK_FAIL, f"input artifact {aid!r} state {fact.get('state')!r} is not VALID", task_id
                    )
                )
            checksum = str(fact.get("checksum_sha256", ""))
            expected = str(fact.get("expected_checksum_sha256", checksum))
            if checksum != expected:
                findings.append(
                    PreflightFinding(f"input_checksum::{aid}", CAT_INPUT_INTEGRITY, CHECK_FAIL, f"input artifact {aid!r} checksum mismatch", task_id)
                )
    return findings


def _check_environment(request: AuthorizationRequest) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    for packet in request.task_packets:
        method_id = str(packet.get("method_id", ""))
        if not method_id:
            continue
        task_id = str(packet.get("task_id", ""))
        impl = request.implementation_facts.get(method_id)
        if impl is None:
            findings.append(
                PreflightFinding(f"env_ref::{method_id}", CAT_ENVIRONMENT, CHECK_FAIL, f"no implementation reference for method {method_id!r}", task_id)
            )
            continue
        digest = str(impl.get("container_digest", "")).strip().lower()
        commit = str(impl.get("code_commit", "")).strip().lower()
        if digest in _FLOATING or digest.endswith(":latest") or not digest:
            findings.append(
                PreflightFinding(f"env_digest::{method_id}", CAT_ENVIRONMENT, CHECK_FAIL, f"method {method_id!r} container digest is floating/missing", task_id)
            )
        if commit in _FLOATING or not commit:
            findings.append(
                PreflightFinding(f"env_commit::{method_id}", CAT_ENVIRONMENT, CHECK_FAIL, f"method {method_id!r} code commit is floating/missing", task_id)
            )
    return findings


def _check_resources(request: AuthorizationRequest) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    avail_cpu = request.resource_status.get("cpu_available")
    avail_mem = request.resource_status.get("memory_mb_available")
    for packet in request.task_packets:
        task_id = str(packet.get("task_id", ""))
        exec_fields = packet.get("execution_fields", {})
        estimate = exec_fields.get("resource_estimate", {})
        if isinstance(avail_cpu, (int, float)) and isinstance(estimate.get("cpu"), (int, float)) and estimate["cpu"] > avail_cpu:
            findings.append(
                PreflightFinding(
                    f"res_cpu::{task_id}", CAT_RESOURCES, CHECK_FAIL, f"task {task_id} requests {estimate['cpu']} cpu > {avail_cpu} available", task_id
                )
            )
        if isinstance(avail_mem, (int, float)) and isinstance(estimate.get("memory_mb"), (int, float)) and estimate["memory_mb"] > avail_mem:
            findings.append(
                PreflightFinding(
                    f"res_mem::{task_id}", CAT_RESOURCES, CHECK_FAIL, f"task {task_id} requests {estimate['memory_mb']}MB > {avail_mem}MB available", task_id
                )
            )
        if not exec_fields.get("timeout_seconds"):
            findings.append(PreflightFinding(f"res_timeout::{task_id}", CAT_RESOURCES, CHECK_FAIL, f"task {task_id} has no timeout", task_id))
    return findings


def _check_network_security(request: AuthorizationRequest) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    sensitivity = str(request.policy.get("data_sensitivity", "unspecified"))
    policy_net = request.policy.get("network_policy", {})
    policy_egress = str(policy_net.get("egress", "deny")).lower()
    for packet in request.task_packets:
        task_id = str(packet.get("task_id", ""))
        exec_net = packet.get("execution_fields", {}).get("network_policy", {})
        egress = str(exec_net.get("egress", "deny")).lower()
        if egress == "allow" and policy_egress == "deny":
            findings.append(
                PreflightFinding(f"net_egress::{task_id}", CAT_NETWORK_SECURITY, CHECK_FAIL, f"task {task_id} requests egress but policy denies it", task_id)
            )
        if egress == "allow" and sensitivity in ("restricted", "sensitive", "phi"):
            findings.append(
                PreflightFinding(f"net_sensitive::{task_id}", CAT_NETWORK_SECURITY, CHECK_FAIL, f"sensitive data ({sensitivity}) may not egress", task_id)
            )
    return findings


def _check_output_isolation(request: AuthorizationRequest) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    for packet in request.task_packets:
        task_id = str(packet.get("task_id", ""))
        write_scope = str(packet.get("execution_fields", {}).get("write_scope", ""))
        if not write_scope:
            findings.append(PreflightFinding(f"out_scope::{task_id}", CAT_OUTPUT_ISOLATION, CHECK_FAIL, f"task {task_id} has no write scope", task_id))
            continue
        normalized = write_scope.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/") or normalized[1:2] == ":":
            findings.append(
                PreflightFinding(
                    f"out_escape::{task_id}", CAT_OUTPUT_ISOLATION, CHECK_FAIL, f"task {task_id} write scope {write_scope!r} escapes the sandbox", task_id
                )
            )
    return findings


def _check_version_freeze(request: AuthorizationRequest) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    for packet in request.task_packets:
        if packet.get("packet_type") != "AnalysisTaskPacket":
            continue
        task_id = str(packet.get("task_id", ""))
        params = packet.get("params", {})
        if not isinstance(params, dict):
            findings.append(
                PreflightFinding(f"freeze_params::{task_id}", CAT_VERSION_FREEZE, CHECK_FAIL, f"task {task_id} params are not a frozen object", task_id)
            )
            continue
        # A dynamic/unfrozen parameter marker is rejected; a missing seed is a warning.
        for key, value in params.items():
            if isinstance(value, str) and value.strip().lower() in ("dynamic", "auto", "runtime"):
                findings.append(
                    PreflightFinding(
                        f"freeze_dynamic::{task_id}::{key}", CAT_VERSION_FREEZE, CHECK_FAIL, f"task {task_id} param {key!r} is dynamic, not frozen", task_id
                    )
                )
        if "random_seed" not in params and "seed" not in params:
            findings.append(PreflightFinding(f"freeze_seed::{task_id}", CAT_VERSION_FREEZE, CHECK_WARN, f"task {task_id} records no random seed", task_id))
    return findings


def _check_approval(request: AuthorizationRequest) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    for gate in sorted(request.required_gates):
        if gate in request.granted_gates:
            findings.append(PreflightFinding(f"approval::{gate}", CAT_APPROVAL, CHECK_PASS, f"required gate {gate!r} is granted"))
        else:
            findings.append(PreflightFinding(f"approval::{gate}", CAT_APPROVAL, CHECK_FAIL, f"required gate {gate!r} is not granted"))
    return findings


_CHECKS = (
    _check_input_integrity,
    _check_environment,
    _check_resources,
    _check_network_security,
    _check_output_isolation,
    _check_version_freeze,
    _check_approval,
)


def run_preflight(request: AuthorizationRequest) -> PreflightReport:
    """Run every preflight check deterministically over the recorded facts."""
    findings: list[PreflightFinding] = []
    for check in _CHECKS:
        findings.extend(check(request))
    findings.sort(key=lambda f: (f.category, f.check_id))
    return PreflightReport(findings=findings)


@dataclass(frozen=True)
class ExecutionAuthorization:
    """An immutable authorization snapshot (T-13-09).

    Records the bounded decision, the object versions/hashes it authorized against
    (plan hash, packet ids, artifact checksums, policy hash), the granted gates,
    and the preflight report.  The snapshot *is* the authority: a scheduler may
    only deliver tasks named in an ``AUTHORIZED`` snapshot.  It grants nothing on
    its own beyond that record and is never edited in place.

    The dataclass is ``frozen`` and every stored container is deep-frozen in
    ``__post_init__`` (sequences → ``tuple``, mappings → read-only proxy), so
    neither reassigning a field nor mutating an exposed container can add or
    remove authority after ``authorize_execution()`` returns.  ``to_dict()``
    returns a defensive plain-``dict`` copy, so mutating that copy cannot reach
    back into the snapshot either.
    """

    project_id: str
    decision: str
    plan_hash: str
    authorized_task_ids: tuple[str, ...]
    snapshot_hash: str
    preflight: Mapping[str, Any]
    policy_hash: str = ""
    granted_gates: tuple[str, ...] = ()
    object_versions: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    reasons: tuple[str, ...] = ()
    authorization_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        # Deep-freeze every stored container regardless of what the caller
        # passed (list/dict/tuple), so the snapshot is immutable by construction.
        object.__setattr__(self, "authorized_task_ids", tuple(self.authorized_task_ids))
        object.__setattr__(self, "granted_gates", tuple(self.granted_gates))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "object_versions", _freeze(self.object_versions))
        object.__setattr__(self, "preflight", _freeze(self.preflight))

    @property
    def authorized(self) -> bool:
        return self.decision == AUTH_AUTHORIZED

    def authorizes(self, task_id: str) -> bool:
        return self.authorized and task_id in self.authorized_task_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "decision": self.decision,
            "plan_hash": self.plan_hash,
            "authorized_task_ids": list(self.authorized_task_ids),
            "snapshot_hash": self.snapshot_hash,
            "preflight": _thaw(self.preflight),
            "policy_hash": self.policy_hash,
            "granted_gates": list(self.granted_gates),
            "object_versions": _thaw(self.object_versions),
            "reasons": list(self.reasons),
            "authorization_id": self.authorization_id,
            "created_at": self.created_at,
        }


def authorize_execution(request: AuthorizationRequest, *, plan_hash: str = "") -> ExecutionAuthorization:
    """Run preflight and mint an immutable authorization snapshot.

    Decision precedence: a FAIL in any category → ``BLOCKED``; else a missing
    required approval → ``APPROVAL_REQUIRED``; else ``AUTHORIZED``.  Only an
    ``AUTHORIZED`` snapshot authorizes any task.
    """
    report = run_preflight(request)
    approval_fail = any(f.category == CAT_APPROVAL and f.status == CHECK_FAIL for f in report.findings)
    other_fail = any(f.category != CAT_APPROVAL and f.status == CHECK_FAIL for f in report.findings)

    if other_fail:
        decision = AUTH_BLOCKED
        reasons = [f.reason for f in report.by_status(CHECK_FAIL)]
        authorized_task_ids: list[str] = []
    elif approval_fail:
        decision = AUTH_APPROVAL_REQUIRED
        reasons = [f.reason for f in report.by_status(CHECK_FAIL) if f.category == CAT_APPROVAL]
        authorized_task_ids = []
    else:
        decision = AUTH_AUTHORIZED
        reasons = ["all preflight checks passed"]
        authorized_task_ids = sorted(str(p.get("task_id", "")) for p in request.task_packets if p.get("task_id"))

    policy_hash = hash_payload(request.policy) if request.policy else ""
    object_versions = {
        "plan_hash": plan_hash,
        "task_packet_ids": sorted(str(p.get("task_id", "")) for p in request.task_packets if p.get("task_id")),
        "input_checksums": {aid: fact.get("checksum_sha256", "") for aid, fact in sorted(request.artifact_facts.items())},
        "policy_hash": policy_hash,
    }
    snapshot_hash = hash_payload(
        {
            "project_id": request.project_id,
            "decision": decision,
            "object_versions": object_versions,
            "authorized_task_ids": authorized_task_ids,
            "granted_gates": sorted(request.granted_gates),
        }
    )
    return ExecutionAuthorization(
        project_id=request.project_id,
        decision=decision,
        plan_hash=plan_hash,
        authorized_task_ids=authorized_task_ids,
        snapshot_hash=snapshot_hash,
        preflight=report.to_dict(),
        policy_hash=policy_hash,
        granted_gates=sorted(request.granted_gates),
        object_versions=object_versions,
        reasons=reasons,
        authorization_id=make_stable_id("execution_authorization", {"project_id": request.project_id, "snapshot_hash": snapshot_hash}),
        created_at="",
    )


__all__ = [
    "CHECK_PASS",
    "CHECK_WARN",
    "CHECK_FAIL",
    "CHECK_STATUSES",
    "CHECK_CATEGORIES",
    "CAT_INPUT_INTEGRITY",
    "CAT_ENVIRONMENT",
    "CAT_RESOURCES",
    "CAT_NETWORK_SECURITY",
    "CAT_OUTPUT_ISOLATION",
    "CAT_VERSION_FREEZE",
    "CAT_APPROVAL",
    "AUTH_AUTHORIZED",
    "AUTH_BLOCKED",
    "AUTH_APPROVAL_REQUIRED",
    "AUTH_DECISIONS",
    "PreflightFinding",
    "PreflightReport",
    "AuthorizationRequest",
    "ExecutionAuthorization",
    "run_preflight",
    "authorize_execution",
]
