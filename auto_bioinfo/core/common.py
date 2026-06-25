"""Common cross-cutting contract types and validators (WP-02a / T-02-01).

These are the horizontal primitives every higher-level schema reuses: stable
identifiers, schema versions, actors, timestamps, content hashes, and external
identifiers (PMID / DOI / GEO accessions ...).  They are deliberately small,
offline, and deterministic — the same input always serialises and validates the
same way, with **no** network lookups.

The module completes the existing stdlib/dataclass core rather than starting a
parallel one: it reuses :func:`auto_bioinfo.core.ids.hash_payload` for the
canonical serialisation/content hash, and the execution-mode vocabulary stays in
:mod:`auto_bioinfo.core.provenance` (imported lazily inside the validator so the
two modules do not import-cycle).

Two failure styles are offered so callers can pick what fits:

- pure validators returning ``list[str]`` of human-readable errors (the same
  convention as :mod:`auto_bioinfo.core.validation`); and
- :class:`SchemaValidationError` plus :func:`ensure_valid` / the dataclass
  ``validate()`` methods, for callers that want an explicit raise.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from typing import Any

from .ids import hash_payload

# --- Vocabularies -----------------------------------------------------------

# Who performed an action.  Distinct from the per-run execution_mode vocabulary
# (DEMO/TEST/REAL) which lives in :mod:`auto_bioinfo.core.provenance`.
ACTOR_TYPES = ("human", "agent", "system")

# External identifier schemes this offline core can structurally verify by
# *format*.  Verification here is identity/format verifiability (no network); a
# claim of ``verified=True`` additionally requires a recorded source.
EXTERNAL_ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "PMID": re.compile(r"^[1-9][0-9]{0,8}$"),
    "DOI": re.compile(r"^10\.[0-9]{4,9}/\S+$"),
    "GEO": re.compile(r"^G(SE|SM|PL|DS)[0-9]+$"),
    "SRA": re.compile(r"^(SR|ER|DR)[APRSXZ][0-9]+$"),
    "ENA": re.compile(r"^[A-Z]{1,6}[0-9]{5,}$"),
    "ARRAYEXPRESS": re.compile(r"^E-[A-Z]{4}-[0-9]+$"),
}

# A stable internal id: lowercase token, no whitespace, conservative charset.
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]*$")
# Canonical schema version, e.g. ``v5.canonical/0.1``.
_SCHEMA_VERSION_PATTERN = re.compile(r"^v[0-9]+\.[a-z0-9_]+/[0-9]+\.[0-9]+$")
# A sha-256 content hash: 64 lowercase hex characters.
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SchemaValidationError(ValueError):
    """Raised when a contract value fails validation and the caller wants a
    hard, explicit failure rather than an error list."""


def ensure_valid(errors: list[str], context: str = "value") -> None:
    """Raise :class:`SchemaValidationError` if ``errors`` is non-empty."""
    if errors:
        raise SchemaValidationError(f"{context}: " + "; ".join(errors))


# --- Deterministic serialisation --------------------------------------------


def canonical_json(payload: Any) -> str:
    """Serialise ``payload`` deterministically (sorted keys, compact, UTF-8).

    Identical to the canonicalisation :func:`auto_bioinfo.core.ids.hash_payload`
    hashes over, exposed on its own so contract values have one stable wire form.
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(payload: Any) -> str:
    """Stable sha-256 content hash over :func:`canonical_json` of ``payload``."""
    return hash_payload(payload)


# --- Scalar validators (pure, return error lists) ---------------------------


def validate_identifier(value: Any, field: str = "id") -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{field}: missing or empty identifier"]
    if not _ID_PATTERN.match(value):
        return [f"{field}: {value!r} is not a valid identifier (lowercase token, no whitespace)"]
    return []


def validate_schema_version(value: Any, field: str = "schema_version") -> list[str]:
    if not isinstance(value, str) or not value:
        return [f"{field}: missing schema version"]
    if not _SCHEMA_VERSION_PATTERN.match(value):
        return [f"{field}: {value!r} is not a valid schema version (expected e.g. 'v5.canonical/0.1')"]
    return []


def validate_hash(value: Any, field: str = "hash") -> list[str]:
    if not isinstance(value, str) or not value:
        return [f"{field}: missing hash"]
    if not _SHA256_PATTERN.match(value):
        return [f"{field}: {value!r} is not a valid lowercase sha-256 hex digest"]
    return []


def validate_timestamp(value: Any, field: str = "timestamp") -> list[str]:
    """An ISO-8601, timezone-aware timestamp.  Naive (no offset) values fail —
    an unanchored wall-clock time is not a verifiable contract value."""
    if not isinstance(value, str) or not value:
        return [f"{field}: missing timestamp"]
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return [f"{field}: {value!r} is not a valid ISO-8601 timestamp"]
    if parsed.tzinfo is None:
        return [f"{field}: {value!r} is timezone-naive; an explicit UTC offset is required"]
    return []


def validate_actor(actor: Any, field: str = "actor") -> list[str]:
    """Validate either an :class:`Actor` or its dict projection."""
    data = actor.to_dict() if isinstance(actor, Actor) else actor
    if not isinstance(data, dict):
        return [f"{field}: actor must be an object with actor_type and actor_id"]
    errors: list[str] = []
    if data.get("actor_type") not in ACTOR_TYPES:
        errors.append(f"{field}.actor_type: must be one of {', '.join(ACTOR_TYPES)}")
    if not str(data.get("actor_id", "") or "").strip():
        errors.append(f"{field}.actor_id: missing required actor id")
    return errors


def validate_external_identifier(identifier: Any, field: str = "external_identifier") -> list[str]:
    """Validate an :class:`ExternalIdentifier` or its dict projection.

    An identifier whose value does not match its scheme's format is *not
    verifiable* and fails explicitly.  A ``verified=True`` claim additionally
    requires a recorded ``verification_source`` — the offline core never accepts
    a bare "trust me, it's verified" boolean.
    """
    data = identifier.to_dict() if isinstance(identifier, ExternalIdentifier) else identifier
    if not isinstance(data, dict):
        return [f"{field}: external identifier must be an object with scheme and value"]
    errors: list[str] = []
    scheme = str(data.get("scheme", "") or "").upper()
    value = str(data.get("value", "") or "")
    if scheme not in EXTERNAL_ID_PATTERNS:
        errors.append(f"{field}.scheme: {scheme!r} is not a recognised external identifier scheme")
    elif not value:
        errors.append(f"{field}.value: missing required identifier value")
    elif not EXTERNAL_ID_PATTERNS[scheme].match(value):
        errors.append(f"{field}.value: {value!r} is not a verifiable {scheme} identifier")
    if data.get("verified") is True and not str(data.get("verification_source", "") or "").strip():
        errors.append(f"{field}: verified=true requires a recorded verification_source")
    return errors


# --- Dataclasses ------------------------------------------------------------


@dataclass
class Actor:
    """Who performed an action: a human, an automated agent, or the system."""

    actor_type: str
    actor_id: str
    display_name: str = ""

    def errors(self) -> list[str]:
        return validate_actor(self)

    def validate(self) -> None:
        ensure_valid(self.errors(), "Actor")

    def to_dict(self) -> dict[str, Any]:
        return {"actor_type": self.actor_type, "actor_id": self.actor_id, "display_name": self.display_name}


@dataclass
class ExternalIdentifier:
    """A reference into an external registry (PMID / DOI / GEO ...).

    ``verified`` records whether the reference was actually checked against a
    real source; it may only be ``True`` when ``verification_source`` is set.
    """

    scheme: str
    value: str
    verified: bool = False
    verification_source: str = ""

    def errors(self) -> list[str]:
        return validate_external_identifier(self)

    def validate(self) -> None:
        ensure_valid(self.errors(), "ExternalIdentifier")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "value": self.value,
            "verified": self.verified,
            "verification_source": self.verification_source,
        }


# --- Minimal JSON-schema derivation (stdlib only) ---------------------------

_JSON_TYPES: dict[type, str] = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def _json_type_for(annotation: Any) -> str:
    """Best-effort JSON-schema type for a dataclass field annotation.

    Annotations may be runtime types or (with ``from __future__ import
    annotations``) strings; both are handled without importing typing machinery.
    """
    if isinstance(annotation, type):
        return _JSON_TYPES.get(annotation, "string")
    text = str(annotation)
    if text.startswith("list") or text.startswith("List"):
        return "array"
    if text.startswith("dict") or text.startswith("Dict"):
        return "object"
    for py_type, name in _JSON_TYPES.items():
        if text.startswith(py_type.__name__):
            return name
    return "string"


def dataclass_json_schema(cls: type) -> dict[str, Any]:
    """Derive a minimal, stable JSON-schema snapshot for a dataclass.

    Required fields are those without a default (or default factory).  This is a
    deterministic, dependency-free projection used for schema snapshot tests; it
    is intentionally minimal (no nested $ref resolution)."""
    if not is_dataclass(cls):
        raise SchemaValidationError(f"{cls!r} is not a dataclass")
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in fields(cls):
        properties[f.name] = {"type": _json_type_for(f.type)}
        has_default = f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
        if not has_default:
            required.append(f.name)
    return {"title": cls.__name__, "type": "object", "properties": properties, "required": required}
