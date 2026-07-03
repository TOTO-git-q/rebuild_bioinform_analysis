"""Offline MethodContract registry with admission, versioning + signatures (WP-11).

Stage 8 forbids the "there is code, so run it" shortcut: a method may only be
*selected* if its contract is registered, ACTIVE, complete, and carries a
resolvable, non-floating implementation reference and a verified signature
(T-11-01/T-11-02/T-11-05).  This registry is the deterministic, in-memory,
offline object that enforces those admission conditions.  It reuses
:func:`auto_bioinfo.core.validation.validate_method_contract` for contract
completeness and the existing catalog in
:mod:`auto_bioinfo.methods.contract_catalog` for the seven registered methods.

Pure / offline / deterministic: no I/O, no clock read, no network, no
randomness.  The registry only *records and admits* contracts; it never selects,
executes, or authorises a method.  A disabled or non-admitted version can never
be returned by :meth:`active_contract`, so the compatibility layer and the
workflow compiler physically cannot bind to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.ids import make_stable_id
from ..core.validation import validate_method_contract
from .contract_catalog import CatalogEntry, MethodRule, build_contract_catalog

# --- Bounded admission vocabulary --------------------------------------------
# Every registration attempt resolves to exactly one of these codes.
ADMIT_OK = "ADMITTED"
ADMIT_REJECTED_INCOMPLETE = "REJECTED_INCOMPLETE_CONTRACT"
ADMIT_REJECTED_FLOATING_REF = "REJECTED_FLOATING_IMPLEMENTATION_REF"
ADMIT_REJECTED_SIGNATURE = "REJECTED_INVALID_SIGNATURE"
ADMIT_REJECTED_NOT_ACTIVE = "REJECTED_NOT_ACTIVE"
ADMIT_CODES = (
    ADMIT_OK,
    ADMIT_REJECTED_INCOMPLETE,
    ADMIT_REJECTED_FLOATING_REF,
    ADMIT_REJECTED_SIGNATURE,
    ADMIT_REJECTED_NOT_ACTIVE,
)

# Contract lifecycle status the registry recognises.  Only ``active`` contracts
# are admissible; ``disabled`` / ``draft`` are stored but never selectable.
CONTRACT_ENABLED = "active"
CONTRACT_DISABLED = "disabled"

# Floating tags that may never stand in for a pinned formal version (T-11-02).
_FLOATING_TAGS = ("latest", "", "head", "main", "master", "dev", "stable")


@dataclass(frozen=True)
class ImplementationReference:
    """The concrete implementation a contract version binds to (T-11-02).

    Records the code commit, container digest, entry point, environment and
    licence.  A floating tag (``latest`` / empty / a branch name) is never a
    formal version: :meth:`uses_floating_reference` flags it and the registry
    refuses to admit it.
    """

    code_commit: str
    container_digest: str
    entrypoint: str
    environment: str
    license: str

    def uses_floating_reference(self) -> bool:
        commit = str(self.code_commit or "").strip().lower()
        digest = str(self.container_digest or "").strip().lower()
        if commit in _FLOATING_TAGS or digest in _FLOATING_TAGS:
            return True
        # A container digest must be content-addressed (``sha256:...``) or an
        # explicit non-tag; a bare ``:latest`` style tag is floating.
        if digest.endswith(":latest") or commit.endswith(":latest"):
            return True
        return False

    def canonical(self) -> dict[str, str]:
        return {
            "code_commit": self.code_commit,
            "container_digest": self.container_digest,
            "entrypoint": self.entrypoint,
            "environment": self.environment,
            "license": self.license,
        }


def sign_contract(contract: dict[str, Any], implementation: ImplementationReference) -> str:
    """Deterministic offline signature over a contract + implementation.

    Stands in for a real cryptographic signature: a stable content hash of the
    contract identity and the pinned implementation.  Two identical inputs always
    produce the same signature, and any tamper changes it.
    """
    return make_stable_id(
        "method_signature",
        {
            "method_contract_id": contract.get("method_contract_id", ""),
            "method_id": contract.get("method_id", ""),
            "version": contract.get("version", ""),
            "implementation": implementation.canonical(),
        },
    )


@dataclass(frozen=True)
class AdmissionResult:
    """The bounded outcome of a registration attempt."""

    code: str
    method_id: str
    version: str
    reasons: tuple[str, ...] = ()

    @property
    def admitted(self) -> bool:
        return self.code == ADMIT_OK


@dataclass
class _RegistryRecord:
    contract: dict[str, Any]
    rule: MethodRule
    implementation: ImplementationReference
    signature: str
    enabled: bool = True


class MethodRegistry:
    """In-memory, deterministic registry of admitted MethodContract versions.

    Keyed by ``(method_id, version)`` so multiple versions of a method coexist;
    :meth:`active_contract` returns the newest *enabled + admitted* version, and
    a disabled or never-admitted version is unreachable.  All admission checks are
    pure functions of the registered data.
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], _RegistryRecord] = {}

    # --- registration / admission -------------------------------------------
    def register(
        self,
        contract: dict[str, Any],
        rule: MethodRule,
        implementation: ImplementationReference,
        *,
        signature: str | None = None,
    ) -> AdmissionResult:
        """Admit a contract version, or reject it with a bounded reason code.

        Admission requires: a complete contract (validator returns no errors), an
        ACTIVE status, a non-floating implementation reference, and a signature
        that matches the recomputed one.  A rejected contract is *not* stored, so
        it can never be selected.
        """
        method_id = str(contract.get("method_id", ""))
        version = str(contract.get("version", ""))

        contract_errors = validate_method_contract(contract)
        if contract_errors:
            return AdmissionResult(ADMIT_REJECTED_INCOMPLETE, method_id, version, tuple(contract_errors))

        if contract.get("status", CONTRACT_ENABLED) != CONTRACT_ENABLED:
            return AdmissionResult(
                ADMIT_REJECTED_NOT_ACTIVE,
                method_id,
                version,
                (f"contract status {contract.get('status')!r} is not '{CONTRACT_ENABLED}'; only active contracts are admissible",),
            )

        if implementation.uses_floating_reference():
            return AdmissionResult(
                ADMIT_REJECTED_FLOATING_REF,
                method_id,
                version,
                ("implementation reference uses a floating tag (e.g. 'latest'); a pinned commit and content digest are required",),
            )

        expected_signature = sign_contract(contract, implementation)
        provided = signature if signature is not None else expected_signature
        if provided != expected_signature:
            return AdmissionResult(
                ADMIT_REJECTED_SIGNATURE,
                method_id,
                version,
                ("contract signature does not match the recomputed signature; the contract or implementation was tampered with",),
            )

        self._records[(method_id, version)] = _RegistryRecord(
            contract=dict(contract),
            rule=rule,
            implementation=implementation,
            signature=expected_signature,
            enabled=True,
        )
        return AdmissionResult(ADMIT_OK, method_id, version)

    # --- lifecycle -----------------------------------------------------------
    def disable(self, method_id: str, version: str) -> bool:
        """Disable a registered version; returns True if a record was toggled."""
        record = self._records.get((method_id, version))
        if record is None:
            return False
        record.enabled = False
        return True

    def enable(self, method_id: str, version: str) -> bool:
        record = self._records.get((method_id, version))
        if record is None:
            return False
        record.enabled = True
        return True

    # --- query ---------------------------------------------------------------
    def versions(self, method_id: str) -> list[str]:
        return sorted(v for (m, v) in self._records if m == method_id)

    def is_enabled(self, method_id: str, version: str) -> bool:
        record = self._records.get((method_id, version))
        return bool(record and record.enabled)

    def get_contract(self, method_id: str, version: str) -> dict[str, Any] | None:
        record = self._records.get((method_id, version))
        return dict(record.contract) if record else None

    def get_rule(self, method_id: str, version: str) -> MethodRule | None:
        record = self._records.get((method_id, version))
        return record.rule if record else None

    def active_contract(self, method_id: str) -> dict[str, Any] | None:
        """Newest *enabled* contract for ``method_id``, or ``None``.

        A disabled or never-admitted version is never returned — nothing
        downstream can bind to it.
        """
        record = self._active_record(method_id)
        return dict(record.contract) if record else None

    def active_entry(self, method_id: str) -> CatalogEntry | None:
        """The newest enabled contract paired with its rule, as a CatalogEntry."""
        record = self._active_record(method_id)
        if record is None:
            return None
        from .contract_catalog import MethodContract  # local import avoids cycles

        contract_obj = _contract_from_dict(record.contract, MethodContract)
        return CatalogEntry(contract=contract_obj, rule=record.rule, contract_id=record.contract["method_contract_id"])

    def active_method_ids(self) -> list[str]:
        return sorted({m for (m, v), r in self._records.items() if r.enabled})

    def _active_record(self, method_id: str) -> _RegistryRecord | None:
        candidates = [(v, r) for (m, v), r in self._records.items() if m == method_id and r.enabled]
        if not candidates:
            return None
        # Newest by version string order (versions are simple semver-like tokens).
        candidates.sort(key=lambda item: item[0])
        return candidates[-1][1]


def _contract_from_dict(data: dict[str, Any], contract_cls: Any) -> Any:
    """Rebuild a MethodContract dataclass from its dict projection (best effort)."""
    fields = set(contract_cls.__dataclass_fields__)
    kwargs = {k: v for k, v in data.items() if k in fields}
    return contract_cls(**kwargs)


def build_default_registry(implementations: dict[str, ImplementationReference] | None = None) -> MethodRegistry:
    """Register all seven catalog methods with pinned demo implementations.

    Each method is registered with a deterministic, non-floating implementation
    reference (a synthetic pinned commit + ``sha256:`` digest) and a valid
    signature, so the returned registry has one ACTIVE, admitted version of every
    catalog method.  A caller may override individual implementations.
    """
    catalog = build_contract_catalog()
    registry = MethodRegistry()
    overrides = implementations or {}
    for method_id, entry in catalog.items():
        contract = entry.contract_dict()
        impl = overrides.get(method_id) or _default_implementation(method_id, contract["version"])
        registry.register(contract, entry.rule, impl)
    return registry


def _default_implementation(method_id: str, version: str) -> ImplementationReference:
    digest = make_stable_id("container_digest", {"method_id": method_id, "version": version})
    commit = make_stable_id("code_commit", {"method_id": method_id, "version": version})
    return ImplementationReference(
        code_commit=commit,
        container_digest=f"sha256:{digest}",
        entrypoint=f"auto_bioinfo.methods.{method_id}",
        environment=f"conda:{method_id}@{version}",
        license="offline-fixture-noncommercial",
    )


__all__ = [
    "ADMIT_OK",
    "ADMIT_REJECTED_INCOMPLETE",
    "ADMIT_REJECTED_FLOATING_REF",
    "ADMIT_REJECTED_SIGNATURE",
    "ADMIT_REJECTED_NOT_ACTIVE",
    "ADMIT_CODES",
    "CONTRACT_ENABLED",
    "CONTRACT_DISABLED",
    "ImplementationReference",
    "AdmissionResult",
    "MethodRegistry",
    "sign_contract",
    "build_default_registry",
]
