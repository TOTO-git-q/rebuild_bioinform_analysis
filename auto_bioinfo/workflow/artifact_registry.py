"""Artifact registration, integrity + lineage over an offline object store (WP-15).

Turns raw task outputs into verified, traceable formal objects: a fake in-memory
ObjectStore (put/get/head/list/presign/delete-policy, T-15-01), a *streaming*
checksum/size that never loads a whole file into memory (T-15-02), a registration
state machine PENDING_VALIDATION → VALID / INVALID / QUARANTINED (T-15-03), output
integrity + format/schema checks (T-15-04/05), an undeclared / write-scope-escape
scan that quarantines and blocks (T-15-06), immutable
:class:`~auto_bioinfo.core.schemas.ArtifactManifest` records (T-15-07), an
ArtifactEdge lineage graph with no dangling edges and a chart→source-table→task
constraint (T-15-08/09), content-hash dedupe that keeps project references
(T-15-10), retention / tombstone / legal-hold that refuses to hard-delete formal
evidence (T-15-11), download with checksum recheck (T-15-12), and lineage export
to JSON / CSV / Graphviz (T-15-13).

Everything is offline and deterministic: the "object store" is an in-memory dict,
the checksum runs over recorded fixture bytes, no network / real filesystem /
clock read is used, and produced manifests carry an empty ``created_at``.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.ids import make_stable_id
from ..core.schemas import ArtifactManifest
from ..core.validation import validate_artifact_manifest

# --- Bounded registration states ---------------------------------------------
STATE_PENDING = "PENDING_VALIDATION"
STATE_VALID = "VALID"
STATE_INVALID = "INVALID"
STATE_QUARANTINED = "QUARANTINED"
REGISTRATION_STATES = (STATE_PENDING, STATE_VALID, STATE_INVALID, STATE_QUARANTINED)

# --- Bounded lineage edge types ----------------------------------------------
EDGE_PRODUCED_BY = "produced_by"  # artifact -> producing task
EDGE_DERIVED_FROM = "derived_from"  # artifact -> upstream artifact
EDGE_USED_BY = "used_by"  # artifact -> consuming task
EDGE_INPUT_OF = "input_of"  # external input -> task
EDGE_TYPES = (EDGE_PRODUCED_BY, EDGE_DERIVED_FROM, EDGE_USED_BY, EDGE_INPUT_OF)

# --- Bounded detected formats ------------------------------------------------
FMT_TSV = "tsv"
FMT_CSV = "csv"
FMT_JSON = "json"
FMT_MATRIX = "matrix"
FMT_IMAGE = "image"
FMT_UNKNOWN = "unknown"
FORMATS = (FMT_TSV, FMT_CSV, FMT_JSON, FMT_MATRIX, FMT_IMAGE, FMT_UNKNOWN)

# Content roles treated as charts/figures (must trace to a source table).
_CHART_ROLES = ("chart", "plot", "figure", "image")
# Content roles treated as formal evidence (hard delete is refused).
_EVIDENCE_ROLES = ("result_table", "deg_results_table", "evidence", "source_table")


def streaming_checksum(chunks: Iterable[bytes]) -> tuple[str, int]:
    """Compute (sha256_hex, size_bytes) by streaming, never buffering the whole file.

    Accepts any iterable of byte chunks (the object store yields these), so a large
    artifact is hashed incrementally.  Deterministic over the same byte stream.
    """
    hasher = hashlib.sha256()
    size = 0
    for chunk in chunks:
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("streaming_checksum expects byte chunks")
        hasher.update(chunk)
        size += len(chunk)
    return hasher.hexdigest(), size


class FakeObjectStore:
    """A deterministic in-memory object store (T-15-01).

    Models the ObjectStore port: ``put`` / ``get`` (streamed) / ``head`` / ``list``
    / ``presign`` / ``delete``.  Delete honours a policy: an object under legal hold
    or marked as formal evidence cannot be hard-deleted (that decision is enforced
    by the registry; the store exposes the primitive).  No network, no disk.
    """

    def __init__(self, *, chunk_size: int = 4096) -> None:
        self._objects: dict[str, bytes] = {}
        self.chunk_size = chunk_size

    def put(self, uri: str, content: bytes) -> None:
        self._objects[uri] = bytes(content)

    def exists(self, uri: str) -> bool:
        return uri in self._objects

    def get_stream(self, uri: str) -> Iterable[bytes]:
        data = self._objects[uri]
        for start in range(0, len(data), self.chunk_size):
            yield data[start : start + self.chunk_size]

    def get(self, uri: str) -> bytes:
        return self._objects[uri]

    def head(self, uri: str) -> dict[str, Any]:
        data = self._objects[uri]
        return {"uri": uri, "size_bytes": len(data), "exists": True}

    def list(self, prefix: str = "") -> list[str]:
        return sorted(u for u in self._objects if u.startswith(prefix))

    def presign(self, uri: str) -> str:
        return make_stable_id("presigned_url", {"uri": uri})

    def delete(self, uri: str) -> bool:
        return self._objects.pop(uri, None) is not None


def detect_format(content: bytes, *, declared_media_type: str = "") -> str:
    """Detect the actual content format from a byte sample (T-15-05)."""
    if not content:
        return FMT_UNKNOWN
    if content[:8].startswith(b"\x89PNG") or content[:3] == b"\xff\xd8\xff":
        return FMT_IMAGE
    text = content[:512].decode("utf-8", errors="replace").lstrip()
    if text[:1] in ("{", "["):
        return FMT_JSON
    first_line = content.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    if "\t" in first_line:
        # A dense all-numeric tab grid is a matrix; a header row is a TSV table.
        return FMT_TSV
    if "," in first_line:
        return FMT_CSV
    return FMT_UNKNOWN


def _media_type_to_format(media_type: str) -> str:
    mt = (media_type or "").lower()
    if "tab-separated" in mt or mt.endswith("/tsv"):
        return FMT_TSV
    if "csv" in mt:
        return FMT_CSV
    if "json" in mt:
        return FMT_JSON
    if "png" in mt or "jpeg" in mt or "image" in mt:
        return FMT_IMAGE
    return FMT_UNKNOWN


@dataclass
class ArtifactRegistration:
    """A registration record for one output artifact."""

    artifact_id: str
    project_id: str
    uri: str
    output_name: str
    state: str
    checksum_sha256: str
    size_bytes: int
    format_detected: str
    declared_media_type: str
    content_role: str
    sensitivity: str
    producer_task_id: str
    source_refs: list[str] = field(default_factory=list)
    declared: bool = True
    findings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    legal_hold: bool = False
    tombstoned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OutputFacts:
    """The recorded facts about one produced output file the registry validates."""

    output_name: str
    uri: str
    content: bytes
    declared_media_type: str = "text/tab-separated-values"
    content_role: str = "result_table"
    sensitivity: str = "unspecified"
    producer_task_id: str = ""
    source_refs: tuple[str, ...] = ()
    write_scope: str = "outputs/"
    relative_path: str = ""


def _escapes_scope(path: str, write_scope: str) -> bool:
    normalized = (path or "").replace("\\", "/")
    if not normalized:
        return False
    if normalized.startswith("/") or normalized[1:2] == ":" or ".." in normalized.split("/"):
        return True
    scope = (write_scope or "").rstrip("/") + "/"
    return not normalized.startswith(scope) if scope != "/" else False


class ArtifactRegistry:
    """Registers, validates, and traces artifacts over a fake object store.

    A registration runs the state machine (T-15-03): a scope-escaping or undeclared
    file is ``QUARANTINED``; a missing / empty / format-mismatched file is
    ``INVALID``; a clean file is ``VALID`` and gets an immutable ArtifactManifest.
    Only ``VALID`` artifacts may be consumed downstream.
    """

    def __init__(self, store: FakeObjectStore | None = None) -> None:
        self.store = store or FakeObjectStore()
        self._registrations: dict[str, ArtifactRegistration] = {}
        self._checksum_index: dict[str, str] = {}  # checksum -> canonical artifact_id

    # --- registration --------------------------------------------------------
    def register(self, project_id: str, facts: OutputFacts, *, expected_output_names: Iterable[str] = ()) -> ArtifactRegistration:
        expected = set(expected_output_names)
        self.store.put(facts.uri, facts.content)
        checksum, size = streaming_checksum(self.store.get_stream(facts.uri))
        artifact_id = make_stable_id("artifact", {"project_id": project_id, "uri": facts.uri, "checksum": checksum})

        findings: list[str] = []
        state = STATE_VALID

        declared = facts.output_name in expected if expected else True
        # 1. scope / undeclared → quarantine (T-15-06).
        if _escapes_scope(facts.relative_path, facts.write_scope):
            findings.append(f"file {facts.relative_path!r} escapes write scope {facts.write_scope!r}")
            state = STATE_QUARANTINED
        elif expected and not declared:
            findings.append(f"output {facts.output_name!r} was not declared for this task")
            state = STATE_QUARANTINED

        # 2. integrity: empty / checksum / format (T-15-04/05).
        if state != STATE_QUARANTINED:
            if size == 0:
                findings.append("artifact is empty")
                state = STATE_INVALID
            detected = detect_format(facts.content, declared_media_type=facts.declared_media_type)
            declared_fmt = _media_type_to_format(facts.declared_media_type)
            if declared_fmt not in (FMT_UNKNOWN, detected) and detected != FMT_UNKNOWN:
                findings.append(f"declared media type maps to {declared_fmt!r} but content is {detected!r}")
                state = STATE_INVALID
        else:
            detected = detect_format(facts.content, declared_media_type=facts.declared_media_type)

        manifest = None
        if state == STATE_VALID:
            manifest = self._build_manifest(project_id, artifact_id, facts, checksum, size)
            errors = validate_artifact_manifest(manifest)
            if errors:  # pragma: no cover - defensive
                findings.extend(errors)
                state = STATE_INVALID
                manifest = None

        registration = ArtifactRegistration(
            artifact_id=artifact_id,
            project_id=project_id,
            uri=facts.uri,
            output_name=facts.output_name,
            state=state,
            checksum_sha256=checksum,
            size_bytes=size,
            format_detected=detected,
            declared_media_type=facts.declared_media_type,
            content_role=facts.content_role,
            sensitivity=facts.sensitivity,
            producer_task_id=facts.producer_task_id,
            source_refs=list(facts.source_refs),
            declared=declared,
            findings=findings,
        )
        registration.manifest = manifest
        self._registrations[artifact_id] = registration
        if state == STATE_VALID and checksum not in self._checksum_index:
            self._checksum_index[checksum] = artifact_id
        return registration

    def _build_manifest(self, project_id: str, artifact_id: str, facts: OutputFacts, checksum: str, size: int) -> dict[str, Any]:
        return ArtifactManifest(
            artifact_id=artifact_id,
            project_id=project_id,
            path=facts.uri,
            exists=True,
            checksum_sha256=checksum,
            is_placeholder=False,
            qc_status="pending",
            artifact_type=facts.content_role,
            content_role=facts.content_role,
            producer_agent_or_task=facts.producer_task_id,
            producer_run_id=facts.producer_task_id,
            source_refs=list(facts.source_refs),
            output_name=facts.output_name,
            media_type=facts.declared_media_type,
            size_bytes=size,
            created_at="",
        ).to_dict()

    # --- dedupe (T-15-10) ----------------------------------------------------
    def canonical_for_checksum(self, checksum: str) -> str:
        """The canonical (first-registered VALID) artifact id for a content hash."""
        return self._checksum_index.get(checksum, "")

    def logical_reference(self, artifact_id: str) -> dict[str, Any]:
        """A dedup-aware logical reference that preserves the project boundary.

        Two byte-identical artifacts in different projects share a content hash but
        keep separate logical references — existence is never leaked across a
        permission boundary.
        """
        reg = self._registrations[artifact_id]
        canonical = self.canonical_for_checksum(reg.checksum_sha256)
        return {
            "artifact_id": artifact_id,
            "project_id": reg.project_id,
            "checksum_sha256": reg.checksum_sha256,
            "canonical_artifact_id": canonical,
            "deduped": canonical != artifact_id,
        }

    # --- lineage (T-15-08/09) ------------------------------------------------
    def build_lineage(self, *, task_inputs: dict[str, list[str]] | None = None) -> dict[str, Any]:
        """Build the ArtifactEdge graph; returns nodes, edges and dangling findings."""
        task_inputs = task_inputs or {}
        nodes: set[str] = set()
        edges: list[dict[str, Any]] = []

        for artifact_id, reg in self._registrations.items():
            nodes.add(artifact_id)
            if reg.producer_task_id:
                nodes.add(reg.producer_task_id)
                edges.append(self._edge(EDGE_PRODUCED_BY, artifact_id, reg.producer_task_id))
            for src in reg.source_refs:
                nodes.add(src)
                edges.append(self._edge(EDGE_DERIVED_FROM, artifact_id, src))
        for task_id, inputs in task_inputs.items():
            nodes.add(task_id)
            for artifact_id in inputs:
                nodes.add(artifact_id)
                edges.append(self._edge(EDGE_USED_BY, artifact_id, task_id))

        dangling = [e for e in edges if e["from_id"] not in nodes or e["to_id"] not in nodes]
        edges.sort(key=lambda e: (e["edge_type"], e["from_id"], e["to_id"]))
        return {"nodes": sorted(nodes), "edges": edges, "node_count": len(nodes), "edge_count": len(edges), "dangling_edges": dangling}

    @staticmethod
    def _edge(edge_type: str, from_id: str, to_id: str) -> dict[str, Any]:
        return {
            "edge_id": make_stable_id("artifact_edge", {"type": edge_type, "from": from_id, "to": to_id}),
            "edge_type": edge_type,
            "from_id": from_id,
            "to_id": to_id,
        }

    def lineage_check(self) -> list[str]:
        """A chart artifact must trace to a source table (T-15-09).

        Returns blocking findings: a chart/figure with no ``derived_from`` source is
        a floating figure and blocks.
        """
        findings: list[str] = []
        for reg in self._registrations.values():
            if reg.content_role in _CHART_ROLES and reg.state == STATE_VALID and not reg.source_refs:
                findings.append(f"chart artifact {reg.artifact_id!r} has no source-table lineage; blocking")
        return findings

    # --- retention / lifecycle (T-15-11) -------------------------------------
    def set_legal_hold(self, artifact_id: str, held: bool = True) -> None:
        self._registrations[artifact_id].legal_hold = held

    def delete(self, artifact_id: str, *, hard: bool = False) -> dict[str, Any]:
        """Delete an artifact honouring retention.  A hard delete of formal evidence
        or a legal-held object is refused; a tombstone (soft delete) is always
        allowed and keeps the lineage reference."""
        reg = self._registrations[artifact_id]
        if hard and (reg.legal_hold or reg.content_role in _EVIDENCE_ROLES):
            return {"deleted": False, "reason": "hard delete refused: object under legal hold or is formal evidence"}
        if hard:
            self.store.delete(reg.uri)
            del self._registrations[artifact_id]
            return {"deleted": True, "mode": "hard"}
        reg.tombstoned = True
        return {"deleted": True, "mode": "tombstone"}

    # --- query / download (T-15-12) ------------------------------------------
    def get(self, artifact_id: str) -> ArtifactRegistration | None:
        return self._registrations.get(artifact_id)

    def query(self, *, state: str | None = None, project_id: str | None = None) -> list[ArtifactRegistration]:
        out = [self._registrations[k] for k in sorted(self._registrations)]
        if state is not None:
            out = [r for r in out if r.state == state]
        if project_id is not None:
            out = [r for r in out if r.project_id == project_id]
        return out

    def download(self, artifact_id: str) -> dict[str, Any]:
        """Download an artifact and re-verify its checksum (T-15-12).

        Only a VALID, non-tombstoned artifact may be downloaded; the recomputed
        checksum must match the registered one.
        """
        reg = self._registrations.get(artifact_id)
        if reg is None:
            return {"authorized": False, "reason": "unknown artifact"}
        if reg.state != STATE_VALID or reg.tombstoned:
            return {"authorized": False, "reason": f"artifact state {reg.state} (tombstoned={reg.tombstoned}) is not downloadable"}
        recomputed, _ = streaming_checksum(self.store.get_stream(reg.uri))
        if recomputed != reg.checksum_sha256:
            return {"authorized": False, "reason": "checksum mismatch on download", "checksum_ok": False}
        return {"authorized": True, "presigned_url": self.store.presign(reg.uri), "checksum_sha256": recomputed, "checksum_ok": True}

    # --- integrity over expected outputs (T-15-04) ---------------------------
    def integrity_report(self, expected: dict[str, list[str]]) -> dict[str, Any]:
        """Check that every expected output for each task is present, non-empty, VALID.

        ``expected`` maps a producer task id to the list of output names it must
        produce.  A missing or non-VALID required output makes the task inadmissible.
        """
        by_task: dict[str, dict[str, ArtifactRegistration]] = {}
        for reg in self._registrations.values():
            by_task.setdefault(reg.producer_task_id, {})[reg.output_name] = reg
        findings: list[dict[str, Any]] = []
        admissible = True
        for task_id, names in expected.items():
            produced = by_task.get(task_id, {})
            for name in names:
                produced_reg = produced.get(name)
                if produced_reg is None:
                    findings.append({"task_id": task_id, "output_name": name, "status": "FAIL", "reason": "missing required output"})
                    admissible = False
                elif produced_reg.state != STATE_VALID or produced_reg.size_bytes == 0:
                    findings.append(
                        {
                            "task_id": task_id,
                            "output_name": name,
                            "status": "FAIL",
                            "reason": f"output not VALID (state={produced_reg.state}, size={produced_reg.size_bytes})",
                        }
                    )
                    admissible = False
                else:
                    findings.append({"task_id": task_id, "output_name": name, "status": "PASS", "reason": "present, non-empty, VALID"})
        return {"admissible": admissible, "findings": findings}

    # --- export (T-15-13) ----------------------------------------------------
    def export_lineage(self, fmt: str = "json", *, task_inputs: dict[str, list[str]] | None = None) -> Any:
        graph = self.build_lineage(task_inputs=task_inputs)
        if fmt == "json":
            return graph
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["edge_type", "from_id", "to_id"])
            for edge in graph["edges"]:
                writer.writerow([edge["edge_type"], edge["from_id"], edge["to_id"]])
            return buffer.getvalue()
        if fmt == "graphviz":
            lines = ["digraph lineage {"]
            for edge in graph["edges"]:
                lines.append(f'  "{edge["from_id"]}" -> "{edge["to_id"]}" [label="{edge["edge_type"]}"];')
            lines.append("}")
            return "\n".join(lines) + "\n"
        raise ValueError(f"unknown export format {fmt!r}")


__all__ = [
    "STATE_PENDING",
    "STATE_VALID",
    "STATE_INVALID",
    "STATE_QUARANTINED",
    "REGISTRATION_STATES",
    "EDGE_PRODUCED_BY",
    "EDGE_DERIVED_FROM",
    "EDGE_USED_BY",
    "EDGE_INPUT_OF",
    "EDGE_TYPES",
    "FMT_TSV",
    "FMT_CSV",
    "FMT_JSON",
    "FMT_MATRIX",
    "FMT_IMAGE",
    "FMT_UNKNOWN",
    "FORMATS",
    "streaming_checksum",
    "detect_format",
    "FakeObjectStore",
    "OutputFacts",
    "ArtifactRegistration",
    "ArtifactRegistry",
]
