"""Hexagonal *ports* — the seams the domain core depends on.

These ``Protocol`` definitions are the only contract the application layer knows
about.  The lightweight, offline, deterministic adapters under
``auto_bioinfo.adapters`` / ``auto_bioinfo.methods`` implement them today.  The
heavier production adapters named in ``docs/adr`` (PostgreSQL event store, S3 /
MinIO object store, Nextflow workflow engine, a network LLM provider) are
*reserved*: they will implement these same protocols without the domain core
changing.  Each reserved port is marked below with ``RESERVED``.

Keeping these as protocols (structural typing) means the adapters do not need to
import or subclass anything — they just have to match the shape — which keeps the
dependency arrow pointing inward (adapters -> ports -> domain), never outward.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PlannerPort(Protocol):
    """Turns a natural-language question into structured planning objects.

    The default adapter is a deterministic, offline rule-based planner so tests
    never need a paid LLM or the network.  RESERVED production adapter: a
    provider-agnostic LLM gateway (its output must still pass the same schema +
    claim-ceiling validators; the LLM never writes domain state directly).
    """

    def normalize_question(self, project_id: str, question: str) -> dict[str, Any]:
        """Return a ResearchSpec dict (never inventing un-stated facts)."""

    def decompose(self, research_spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Return SubQuestion dicts."""

    def plan_evidence(self, research_spec: dict[str, Any], subquestions: list[dict[str, Any]]) -> dict[str, Any]:
        """Return an EvidencePlan dict."""

    def resolve_scope(self, research_spec: dict[str, Any], subquestions: list[dict[str, Any]]) -> dict[str, Any]:
        """Return a ScopeBundle dict."""


@runtime_checkable
class ResourceDiscoveryPort(Protocol):
    """Discovers + verifies candidate datasets through a real tool, not memory.

    The default adapter serves committed offline fixtures (clearly labelled as
    fixtures).  RESERVED production adapters: GEO / Europe PMC / annotation
    sources reached over an audited HTTP tool broker with recorded responses.
    A dataset may only be reported ``verified`` when backed by real metadata —
    never from an ``AUTO_``/``MOCK_`` accession (enforced in ``core.validation``).
    """

    def discover(self, research_spec: dict[str, Any], evidence_plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Return ResourceCandidate dicts."""

    def profile(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Return a verified DatasetProfile dict (or raise if not verifiable)."""

    def materialize(self, dataset_profile: dict[str, Any], dest_dir: str) -> dict[str, str]:
        """Copy/download the dataset files into ``dest_dir``; return {name: path}."""


@runtime_checkable
class AnalysisMethodPort(Protocol):
    """A registered, versioned analysis method bound to a MethodContract.

    The default adapters are deterministic in-process Python methods (e.g.
    ``bulk_deg``).  RESERVED production adapters: containerised methods and a
    Nextflow workflow executor running the *same* MethodContract.
    """

    method_id: str
    version: str

    def contract(self) -> dict[str, Any]:
        """Return the MethodContract dict (claim capability, required inputs, ...)."""

    def run(self, *, inputs: dict[str, str], params: dict[str, Any], out_dir: str) -> dict[str, Any]:
        """Execute and return a structured result (paths, metrics, seed, status)."""


@runtime_checkable
class ObjectStorePort(Protocol):
    """Stores artifacts addressed by content checksum.

    The default adapter is the local filesystem under the project directory.
    RESERVED production adapter: an S3 / MinIO bucket.  Either way artifacts are
    addressed by ``sha256`` content hash, never by mutable path.
    """

    def put(self, project_dir: str, relative_path: str, data: bytes) -> dict[str, Any]: ...

    def open(self, project_dir: str, relative_path: str) -> bytes: ...


@runtime_checkable
class EventStorePort(Protocol):
    """Append-only authoritative event log + state projection.

    The default adapter is JSONL on disk (``core.store``).  RESERVED production
    adapter: a PostgreSQL event store with an outbox and optimistic
    concurrency.  The domain only relies on: append an event, load events,
    rebuild the state projection.
    """

    def append_event(self, project_dir: str, event: dict[str, Any]) -> dict[str, Any]: ...

    def load_events(self, project_dir: str) -> list[dict[str, Any]]: ...

    def load_state(self, project_dir: str) -> dict[str, Any]: ...
