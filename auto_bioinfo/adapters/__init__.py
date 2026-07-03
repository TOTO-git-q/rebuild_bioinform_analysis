"""auto_bioinfo package."""

# Re-exports for the folded-in offline clean-room package (PR #46).  These import
# only stdlib + ``auto_bioinfo.core.ids`` — no network/subprocess libraries — so
# importing the adapters package stays side-effect-free and offline-safe.
from .capability_registry import (
    CapabilityGrantDescriptor,
    assert_no_executable_grants,
    build_capability_registry,
    grant_by_id,
    grant_descriptors,
    resolve_decision,
)
from .public_bio_tools import (
    MaterializationRejected,
    PublicBioToolAdapter,
    PublicBioToolSpec,
    build_public_bio_tool_registry,
)

__all__ = [
    "CapabilityGrantDescriptor",
    "assert_no_executable_grants",
    "build_capability_registry",
    "grant_by_id",
    "grant_descriptors",
    "resolve_decision",
    "MaterializationRejected",
    "PublicBioToolAdapter",
    "PublicBioToolSpec",
    "build_public_bio_tool_registry",
]
