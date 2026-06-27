"""Local structured-output admission contract (WP-05c / T-05-03, WP-05d / T-05-04).

The smallest *local* contract layer the future agent gateway (WP-05) needs so it
can take a resolved registered prompt plus an already-returned, inert
:class:`~auto_bioinfo.agent_gateway.llm_provider.LLMResponse`, **parse** the model
text into structured data, **validate** it against the prompt's registered target
schema, optionally run a **bounded local repair retry** over explicit response
candidates, and return an **admission decision as data only** — *without ever
opening a socket, importing a provider SDK, reading a credential, reaching the
network, calling a paid service, or letting any content leave the process*.

This is the foundation slice only.  It defines:

- strict, fail-closed parsing of a provider response's text into structured data
  (:func:`parse_structured_output`): malformed JSON, multiple top-level payloads,
  an empty payload, a non-finite number, an oversized payload, or an unsupported
  top-level shape each fail closed with a stable reason code;
- a bounded local JSON-schema *subset* validator (:func:`validate_instance`) plus a
  small, offline :class:`SchemaRegistry` that resolves a schema only by stable id
  (and optional content hash) and **never silently falls back**;
- a deterministic admission entry point (:func:`admit_structured_output`) that binds
  a response to the prompt's exact registered ``target_schema`` (no silent schema
  fallback), runs a bounded local repair retry over an explicit candidate sequence,
  and returns an inert :class:`AdmissionDecision` — an accepted parsed object plus
  prompt/schema binding metadata, or a rejection reason plus bounded per-attempt
  summaries;
- a local **domain semantic validator hook** (WP-05d / T-05-04): an offline
  :class:`SemanticValidatorRegistry` plus :class:`SemanticValidationResult` so a
  deterministic semantic validator runs *after* schema admission and *before* an
  accepted object is returned, resolved only by explicit id (no silent fall-back to
  no-op validation), failing closed when a requested validator is unknown, raises, or
  returns a malformed result, and treating a clean semantic rejection as a repairable
  content failure within the existing bounded retry.

Design constraints (WP-05c), mirroring the WP-05a / WP-05b / WP-04 contract style:

- **Pure, deterministic, offline.**  No I/O whatsoever: no network, socket, HTTP
  client, provider SDK, environment/credential access, real clock, threads, or
  file/DB/queue side effect.  An admission decision is a total function of its
  explicit in-memory inputs (a prompt registry, a schema registry, and a candidate
  response sequence).
- **No real repair.**  "Repair retry" here is a *local deterministic contract* over
  an explicit, caller-supplied sequence of inert response candidates (e.g. produced
  in a test by :class:`~auto_bioinfo.agent_gateway.llm_provider.FakeLLMProvider`).
  There is no real provider call, network call, SDK, credential, paid service, or
  content egress, and attempt records are bounded summaries (index + outcome code),
  never full prompt/response logs.
- **Fail closed, no fallback.**  Every uncertainty resolves to a bounded, reason-coded
  rejection (:data:`REASON_CODES`).  A malformed/forged response, malformed JSON, a
  schema violation, an unknown/mismatched/drifted schema, an unregistered prompt or
  version, a template-hash mismatch, or repair exhaustion all fail closed — never a
  silent acceptance and never a fallback to another prompt, version, or schema.
- **Data only.**  Admission returns *data* to the caller: an inert
  :class:`AdmissionDecision`.  It writes no project state, business object, event,
  artifact, queue/outbox record, ordinary domain table, or full-content log, and it
  mutates no domain object.

Out of scope for T-05-03 / T-05-04 (and deliberately *not* implemented here): any real
provider/HTTP/SDK integration or content egress, the sensitive content classifier /
egress policy (T-05-05), the tool
broker (T-05-06), raw-output artifact storage / audit / budget / rate-limit /
circuit-breaker machinery (T-05-07..11), prompt authoring / version approval /
rollback (T-05-12), and any write of an accepted output into project state, events,
artifacts, logs, or downstream domain/business objects.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import islice
from typing import Any

from auto_bioinfo.core.ids import hash_payload

from .llm_provider import LLMResponse, validate_response
from .prompt_registry import PromptRegistry, PromptRegistryError, RegisteredPrompt

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated.
MAX_OUTPUT_TEXT_LENGTH = 200_000
MAX_SCHEMA_ID_LENGTH = 200
MAX_VALIDATOR_ID_LENGTH = 200
MAX_VALIDATION_DEPTH = 32
MAX_REPAIR_ATTEMPTS = 8
DEFAULT_MAX_ATTEMPTS = 3
# A bound on how many semantic validators a single admission may request, so an
# unbounded request list cannot turn one admission into unbounded work.
MAX_SEMANTIC_VALIDATORS = 16

# --- Bounded admission status vocabulary -------------------------------------
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"

STATUSES = (STATUS_ACCEPTED, STATUS_REJECTED)

# --- Bounded JSON-schema-subset type vocabulary ------------------------------
# The subset of JSON-schema ``type`` values this local validator understands; a
# schema naming any other type is malformed and fails closed at registration.
SCHEMA_TYPE_OBJECT = "object"
SCHEMA_TYPE_ARRAY = "array"
SCHEMA_TYPE_STRING = "string"
SCHEMA_TYPE_INTEGER = "integer"
SCHEMA_TYPE_NUMBER = "number"
SCHEMA_TYPE_BOOLEAN = "boolean"
SCHEMA_TYPE_NULL = "null"

SCHEMA_TYPES = (
    SCHEMA_TYPE_OBJECT,
    SCHEMA_TYPE_ARRAY,
    SCHEMA_TYPE_STRING,
    SCHEMA_TYPE_INTEGER,
    SCHEMA_TYPE_NUMBER,
    SCHEMA_TYPE_BOOLEAN,
    SCHEMA_TYPE_NULL,
)

# Keywords the bounded subset validator recognises.  A schema using any other
# keyword is malformed and fails closed (so a caller cannot believe an unsupported
# constraint is being enforced when it is not).
SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "title",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
    }
)

# --- Stable reason codes -----------------------------------------------------
# Callers / a future gateway branch on these machine-readable codes, never the
# human message, so they must stay stable.
# parsing:
CODE_EMPTY_PAYLOAD = "ADMIT_EMPTY_PAYLOAD"
CODE_MALFORMED_JSON = "ADMIT_MALFORMED_JSON"
CODE_MULTIPLE_PAYLOADS = "ADMIT_MULTIPLE_PAYLOADS"
CODE_NON_FINITE_NUMBER = "ADMIT_NON_FINITE_NUMBER"
CODE_PAYLOAD_TOO_LARGE = "ADMIT_PAYLOAD_TOO_LARGE"
CODE_UNSUPPORTED_SHAPE = "ADMIT_UNSUPPORTED_SHAPE"
# schema registry / definition:
CODE_MALFORMED_SCHEMA_ID = "ADMIT_MALFORMED_SCHEMA_ID"
CODE_MALFORMED_SCHEMA = "ADMIT_MALFORMED_SCHEMA"
CODE_DUPLICATE_SCHEMA = "ADMIT_DUPLICATE_SCHEMA"
CODE_UNKNOWN_SCHEMA = "ADMIT_UNKNOWN_SCHEMA"
CODE_SCHEMA_DRIFT = "ADMIT_SCHEMA_DRIFT"
# validation / admission:
CODE_SCHEMA_VIOLATION = "ADMIT_SCHEMA_VIOLATION"
CODE_SCHEMA_MISMATCH = "ADMIT_SCHEMA_MISMATCH"
CODE_MALFORMED_RESPONSE = "ADMIT_MALFORMED_RESPONSE"
CODE_MALFORMED_MAX_ATTEMPTS = "ADMIT_MALFORMED_MAX_ATTEMPTS"
CODE_NO_CANDIDATES = "ADMIT_NO_CANDIDATES"
CODE_REPAIR_EXHAUSTED = "ADMIT_REPAIR_EXHAUSTED"
# semantic validator registry / definition (T-05-04):
CODE_MALFORMED_VALIDATOR_ID = "ADMIT_MALFORMED_VALIDATOR_ID"
CODE_MALFORMED_VALIDATOR = "ADMIT_MALFORMED_VALIDATOR"
CODE_DUPLICATE_VALIDATOR = "ADMIT_DUPLICATE_VALIDATOR"
CODE_UNKNOWN_VALIDATOR = "ADMIT_UNKNOWN_VALIDATOR"
# semantic validation / admission (T-05-04):
CODE_MALFORMED_VALIDATOR_REQUEST = "ADMIT_MALFORMED_VALIDATOR_REQUEST"
CODE_SEMANTIC_REJECTED = "ADMIT_SEMANTIC_REJECTED"
CODE_SEMANTIC_VALIDATOR_ERROR = "ADMIT_SEMANTIC_VALIDATOR_ERROR"
CODE_MALFORMED_VALIDATOR_RESULT = "ADMIT_MALFORMED_VALIDATOR_RESULT"

PARSE_CODES = (
    CODE_EMPTY_PAYLOAD,
    CODE_MALFORMED_JSON,
    CODE_MULTIPLE_PAYLOADS,
    CODE_NON_FINITE_NUMBER,
    CODE_PAYLOAD_TOO_LARGE,
    CODE_UNSUPPORTED_SHAPE,
)

SCHEMA_CODES = (
    CODE_MALFORMED_SCHEMA_ID,
    CODE_MALFORMED_SCHEMA,
    CODE_DUPLICATE_SCHEMA,
    CODE_UNKNOWN_SCHEMA,
    CODE_SCHEMA_DRIFT,
)

ADMISSION_CODES = (
    CODE_SCHEMA_VIOLATION,
    CODE_SCHEMA_MISMATCH,
    CODE_MALFORMED_RESPONSE,
    CODE_MALFORMED_MAX_ATTEMPTS,
    CODE_NO_CANDIDATES,
    CODE_REPAIR_EXHAUSTED,
)

# Semantic validator registry / resolution failures (T-05-04): a malformed/duplicate
# validator definition or an unknown requested validator id.  ``CODE_UNKNOWN_VALIDATOR``
# is the no-silent-fallback failure when a requested validator is not registered.
VALIDATOR_REGISTRY_CODES = (
    CODE_MALFORMED_VALIDATOR_ID,
    CODE_MALFORMED_VALIDATOR,
    CODE_DUPLICATE_VALIDATOR,
    CODE_UNKNOWN_VALIDATOR,
)

# Semantic admission failures (T-05-04): a malformed request list, a content-level
# semantic rejection (repairable), or a validator that raised / returned a malformed
# result (a fault in the validator, not the content — not repairable).
SEMANTIC_CODES = (
    CODE_MALFORMED_VALIDATOR_REQUEST,
    CODE_SEMANTIC_REJECTED,
    CODE_SEMANTIC_VALIDATOR_ERROR,
    CODE_MALFORMED_VALIDATOR_RESULT,
)

# Note: prompt-binding failures (unknown prompt / unknown version / template-hash
# mismatch) are surfaced verbatim from the prompt registry's own stable
# ``PromptRegistryError.code`` set, so an admission decision can carry the precise
# binding reason without this module re-declaring those codes.
REASON_CODES = PARSE_CODES + SCHEMA_CODES + ADMISSION_CODES + VALIDATOR_REGISTRY_CODES + SEMANTIC_CODES

# Per-attempt failures a bounded local *repair* retry may meaningfully attempt to
# fix with a subsequent candidate (a content-level problem).  A structurally
# invalid response object, a binding failure, or a validator fault is not
# "repairable" content and stops the retry early.  A *semantic rejection* (the
# validator ran cleanly and judged the content invalid) is content-level and
# repairable, so a later candidate may still be accepted within the attempt bound.
REPAIRABLE_CODES = PARSE_CODES + (CODE_SCHEMA_VIOLATION, CODE_SEMANTIC_REJECTED)


class StructuredOutputError(Exception):
    """A bounded, reason-coded structured-output failure.

    ``code`` is one of :data:`REASON_CODES`; ``message`` is a human-readable
    explanation a caller may surface but should never branch on (branch on
    ``code``).  Raised by :func:`parse_structured_output` and the
    :class:`SchemaRegistry`; it carries no I/O, transport, or provider state.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# --- Small, pure predicates --------------------------------------------------


def _is_positive_int(value: Any) -> bool:
    """A real positive integer — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_real_int(value: Any) -> bool:
    """A real integer — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_real_number(value: Any) -> bool:
    """A real, finite ``int``/``float`` — ``bool`` is excluded (it subclasses ``int``)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def is_repairable(code: Any) -> bool:
    """True iff ``code`` is a content-level failure a later candidate may repair.

    A pure repair-decision predicate (the local "repair retry" has no real provider
    call): a parse failure or schema violation is repairable; a structurally invalid
    response object or a binding failure is not.
    """
    return code in REPAIRABLE_CODES


# --- Strict response-text parsing --------------------------------------------


def _reject_constant(token: str) -> Any:
    """Reject the JSON non-finite constants (``NaN``/``Infinity``/``-Infinity``).

    Passed to :func:`json.loads` as ``parse_constant`` so a non-finite literal fails
    closed rather than silently entering domain state as ``float('inf')``/``nan``.
    """
    raise StructuredOutputError(CODE_NON_FINITE_NUMBER, f"non-finite JSON constant {token!r} is not permitted")


def _assert_finite(value: Any, depth: int = 0) -> None:
    """Recursively reject any non-finite float and any over-deep nesting.

    Numeric literals such as ``1e400`` parse to ``float('inf')`` without going
    through ``parse_constant``, so the parsed structure is walked explicitly.  The
    depth bound is a fail-closed guard against pathologically nested payloads.
    """
    if depth > MAX_VALIDATION_DEPTH:
        raise StructuredOutputError(CODE_UNSUPPORTED_SHAPE, f"payload nesting exceeds the maximum depth of {MAX_VALIDATION_DEPTH}")
    if isinstance(value, float) and not math.isfinite(value):
        raise StructuredOutputError(CODE_NON_FINITE_NUMBER, "payload contains a non-finite number")
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_finite(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_finite(item, depth + 1)


def parse_structured_output(text: Any) -> dict[str, Any]:
    """Parse a provider response's text into a structured object, fail-closed.

    The text must be a single JSON *object* (the structured-output shape this slice
    admits).  Failures map to stable reason codes:

    - non-string / empty / whitespace-only text → :data:`CODE_EMPTY_PAYLOAD`;
    - text longer than :data:`MAX_OUTPUT_TEXT_LENGTH` → :data:`CODE_PAYLOAD_TOO_LARGE`;
    - more than one top-level JSON value (trailing data) → :data:`CODE_MULTIPLE_PAYLOADS`;
    - otherwise malformed JSON → :data:`CODE_MALFORMED_JSON`;
    - a non-finite number (``NaN``/``Infinity``/``1e400``) → :data:`CODE_NON_FINITE_NUMBER`;
    - a valid JSON value that is not a top-level object → :data:`CODE_UNSUPPORTED_SHAPE`.

    Returns the parsed ``dict`` on success.  Performs no I/O and mutates nothing.
    """
    if not isinstance(text, str):
        raise StructuredOutputError(CODE_EMPTY_PAYLOAD, "response text must be a string")
    if len(text) > MAX_OUTPUT_TEXT_LENGTH:
        raise StructuredOutputError(CODE_PAYLOAD_TOO_LARGE, f"response text length {len(text)} exceeds the maximum of {MAX_OUTPUT_TEXT_LENGTH}")
    stripped = text.strip()
    if not stripped:
        raise StructuredOutputError(CODE_EMPTY_PAYLOAD, "response text is empty or whitespace only")
    try:
        parsed = json.loads(stripped, parse_constant=_reject_constant)
    except StructuredOutputError:
        raise
    except json.JSONDecodeError as exc:
        if exc.msg.startswith("Extra data"):
            raise StructuredOutputError(CODE_MULTIPLE_PAYLOADS, "response text contains more than one top-level JSON value") from exc
        raise StructuredOutputError(CODE_MALFORMED_JSON, f"response text is not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise StructuredOutputError(CODE_UNSUPPORTED_SHAPE, "structured output must be a JSON object")
    _assert_finite(parsed)
    return parsed


# --- Bounded local JSON-schema-subset validation -----------------------------


def validate_schema_definition(schema: Any, depth: int = 0) -> list[str]:
    """Return a list of problems with a schema *definition* (empty == valid).

    Validates that ``schema`` uses only the supported bounded subset: a known
    ``type``, an object ``properties`` map of sub-schemas, a ``required`` list of
    strings, a boolean ``additionalProperties``, an ``items`` sub-schema, an ``enum``
    list, and simple numeric/length/size bounds.  An unknown keyword or type fails
    closed so a caller never believes an unsupported constraint is enforced.
    """
    if depth > MAX_VALIDATION_DEPTH:
        return [f"schema nesting exceeds the maximum depth of {MAX_VALIDATION_DEPTH}"]
    if not isinstance(schema, Mapping):
        return ["schema must be a mapping"]
    errors: list[str] = []

    unknown = [key for key in schema if key not in SUPPORTED_SCHEMA_KEYWORDS]
    if unknown:
        errors.append(f"schema uses unsupported keyword(s) {sorted(unknown)!r}")

    if "type" not in schema:
        errors.append("schema must declare a 'type'")
    elif schema["type"] not in SCHEMA_TYPES:
        errors.append(f"schema type {schema['type']!r} is not one of {SCHEMA_TYPES}")

    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, Mapping):
            errors.append("'properties' must be a mapping")
        else:
            for name, sub in properties.items():
                if not isinstance(name, str) or not name:
                    errors.append("each property name must be a non-empty string")
                    continue
                errors.extend(f"properties.{name}: {problem}" for problem in validate_schema_definition(sub, depth + 1))

    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not all(isinstance(name, str) and name for name in required):
            errors.append("'required' must be a list of non-empty strings")

    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        errors.append("'additionalProperties' must be a boolean")

    if "items" in schema:
        errors.extend(f"items: {problem}" for problem in validate_schema_definition(schema["items"], depth + 1))

    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        errors.append("'enum' must be a non-empty list")

    for bound in ("minimum", "maximum"):
        if bound in schema and not _is_real_number(schema[bound]):
            errors.append(f"'{bound}' must be a finite number")
    for bound in ("minLength", "maxLength", "minItems", "maxItems"):
        if bound in schema and (not _is_real_int(schema[bound]) or schema[bound] < 0):
            errors.append(f"'{bound}' must be a non-negative integer")

    return errors


def _matches_type(instance: Any, json_type: str) -> bool:
    """True iff ``instance`` matches a single JSON-schema-subset ``type``."""
    if json_type == SCHEMA_TYPE_OBJECT:
        return isinstance(instance, dict)
    if json_type == SCHEMA_TYPE_ARRAY:
        return isinstance(instance, list)
    if json_type == SCHEMA_TYPE_STRING:
        return isinstance(instance, str)
    if json_type == SCHEMA_TYPE_INTEGER:
        return _is_real_int(instance)
    if json_type == SCHEMA_TYPE_NUMBER:
        return _is_real_number(instance)
    if json_type == SCHEMA_TYPE_BOOLEAN:
        return isinstance(instance, bool)
    if json_type == SCHEMA_TYPE_NULL:
        return instance is None
    return False


def validate_instance(instance: Any, schema: Any, depth: int = 0, path: str = "$") -> list[str]:
    """Return a list of human-readable problems validating ``instance`` against ``schema``.

    A bounded local subset of JSON-schema (see :func:`validate_schema_definition`).
    An empty list means the instance is valid under the schema.  The function is pure
    and performs no I/O.
    """
    if depth > MAX_VALIDATION_DEPTH:
        return [f"{path}: instance nesting exceeds the maximum depth of {MAX_VALIDATION_DEPTH}"]
    if not isinstance(schema, Mapping):
        return [f"{path}: schema must be a mapping"]
    errors: list[str] = []

    json_type = schema.get("type")
    if json_type is not None and not _matches_type(instance, json_type):
        errors.append(f"{path}: expected type {json_type!r}")
        # A type mismatch makes deeper, type-specific checks meaningless.
        return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value is not one of the permitted enum members")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string longer than maxLength {schema['maxLength']}")

    if _is_real_number(instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: value below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: value above maximum {schema['maximum']}")

    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for name, sub in properties.items():
                if name in instance:
                    errors.extend(validate_instance(instance[name], sub, depth + 1, f"{path}.{name}"))
            if schema.get("additionalProperties") is False:
                extra = [name for name in instance if name not in properties]
                if extra:
                    errors.append(f"{path}: additional properties not permitted: {sorted(extra)!r}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: array shorter than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: array longer than maxItems {schema['maxItems']}")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(instance):
                errors.extend(validate_instance(item, item_schema, depth + 1, f"{path}[{index}]"))

    return errors


# --- The schema registry -----------------------------------------------------


def _is_bounded_token(value: Any, max_length: int) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII token."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length and all("\x20" <= ch <= "\x7e" for ch in value)


def _is_bounded_schema_id(value: Any) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII id."""
    return _is_bounded_token(value, MAX_SCHEMA_ID_LENGTH)


class SchemaRegistry:
    """An in-memory registry resolving schemas only by explicit id (+ optional hash).

    Registration validates the schema *definition* (fail-closed) and rejects a
    duplicate id.  Resolution returns only an explicitly registered schema and
    **never silently falls back**: an unknown id raises :data:`CODE_UNKNOWN_SCHEMA`,
    and a supplied ``expected_hash`` that does not match the registered schema's
    content hash raises :data:`CODE_SCHEMA_DRIFT`.  Both register and resolve are
    pure with respect to the outside world — no I/O, inert data only.
    """

    def __init__(self, schemas: Mapping[str, Any] | Iterable[tuple[str, Any]] | None = None) -> None:
        self._by_id: dict[str, dict[str, Any]] = {}
        if schemas is None:
            items: Iterable[tuple[str, Any]] = ()
        elif isinstance(schemas, Mapping):
            items = schemas.items()
        else:
            items = schemas
        for schema_id, schema in items:
            self.register(schema_id, schema)

    def register(self, schema_id: Any, schema: Any, *, expected_hash: str | None = None) -> dict[str, Any]:
        """Register ``schema`` under ``schema_id``; fail closed on a malformed/duplicate/drifted entry."""
        if not _is_bounded_schema_id(schema_id):
            raise StructuredOutputError(CODE_MALFORMED_SCHEMA_ID, "schema_id must be a non-blank, bounded, single-line printable-ASCII identifier")
        definition_errors = validate_schema_definition(schema)
        if definition_errors:
            raise StructuredOutputError(CODE_MALFORMED_SCHEMA, f"schema {schema_id!r} is malformed: {definition_errors[0]}")
        # Store a deep, plain-dict copy so a later caller mutation cannot drift a
        # registered schema, and so the content hash is stable.
        stored = json.loads(json.dumps(schema, sort_keys=True))
        schema_hash = hash_payload(stored)
        if expected_hash is not None and schema_hash != expected_hash:
            raise StructuredOutputError(CODE_SCHEMA_DRIFT, f"schema hash for {schema_id!r} ({schema_hash}) does not match expected_hash ({expected_hash})")
        if schema_id in self._by_id:
            raise StructuredOutputError(CODE_DUPLICATE_SCHEMA, f"schema id {schema_id!r} is already registered")
        self._by_id[schema_id] = stored
        return stored

    def resolve(self, schema_id: Any, *, expected_hash: str | None = None) -> dict[str, Any]:
        """Return the registered schema for ``schema_id`` or fail closed (no fallback)."""
        schema = self._by_id.get(schema_id)
        if schema is None:
            raise StructuredOutputError(CODE_UNKNOWN_SCHEMA, f"no schema is registered under id {schema_id!r}")
        if expected_hash is not None:
            schema_hash = hash_payload(schema)
            if schema_hash != expected_hash:
                raise StructuredOutputError(CODE_SCHEMA_DRIFT, f"schema hash for {schema_id!r} ({schema_hash}) does not match expected_hash ({expected_hash})")
        return schema

    def schema_hash(self, schema_id: Any) -> str:
        """Return the content hash of the registered schema for ``schema_id`` (fail-closed)."""
        return hash_payload(self.resolve(schema_id))

    def contains(self, schema_id: Any) -> bool:
        """True iff ``schema_id`` is registered (a total, side-effect-free check)."""
        return schema_id in self._by_id

    def schema_ids(self) -> tuple[str, ...]:
        """Return the registered schema ids in first-registration order."""
        return tuple(self._by_id)

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, schema_id: object) -> bool:
        return schema_id in self._by_id

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the whole registry (entries sorted by id)."""
        return {"schemas": {schema_id: self._by_id[schema_id] for schema_id in sorted(self._by_id)}}


# --- Domain semantic validator hook (T-05-04) --------------------------------
#
# A *semantic* validator runs only after a candidate has parsed to a JSON object
# and validated against the prompt's exact registered target schema.  It expresses
# a deterministic, local, offline domain rule the schema alone cannot — e.g. "the
# claimed ``score`` is consistent with the reported ``tags``" — over the already
# admitted structured object plus inert local context/config.  A validator returns
# a :class:`SemanticValidationResult`; it must never open a socket, read a
# credential, reach the network, or mutate shared state.  A validator that *raises*
# or returns a non-result is treated as a fault in the validator (fail closed, not
# repairable); a validator that *cleanly judges the content invalid* is a content
# rejection a later candidate may still repair within the attempt bound.


SemanticValidator = Any  # a callable ``(structured_object, context) -> SemanticValidationResult``


@dataclass(frozen=True)
class SemanticValidationResult:
    """The inert verdict of one semantic validator over an admitted object.

    ``valid`` is the only field a caller should branch on: ``True`` accepts the
    object for this validator, ``False`` is a bounded semantic rejection.  ``message``
    is an optional human-readable note (never branch on it; it is not retained on the
    bounded :class:`AdmissionAttempt`).  Construct with :meth:`accept` / :meth:`reject`.
    """

    valid: bool
    message: str | None = None

    @classmethod
    def accept(cls) -> SemanticValidationResult:
        """A passing verdict."""
        return cls(valid=True)

    @classmethod
    def reject(cls, message: str | None = None) -> SemanticValidationResult:
        """A failing (semantic-rejection) verdict, with an optional human note."""
        return cls(valid=False, message=message)

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the verdict (stable key order)."""
        return {"valid": self.valid, "message": self.message}


def _is_semantic_result(value: Any) -> bool:
    """True iff ``value`` is a well-formed :class:`SemanticValidationResult`."""
    return isinstance(value, SemanticValidationResult) and isinstance(value.valid, bool)


class SemanticValidatorRegistry:
    """An in-memory registry resolving semantic validators only by explicit id.

    Registration requires a non-blank bounded printable-ASCII id and a callable
    validator, and rejects a duplicate id (fail-closed).  Resolution returns only an
    explicitly registered validator and **never silently falls back**: an unknown id
    raises :data:`CODE_UNKNOWN_VALIDATOR` so a requested-but-missing validator can
    never degrade into a silent no-op.  Holding only inert callables, the registry
    performs no I/O of its own.
    """

    def __init__(self, validators: Mapping[str, Any] | Iterable[tuple[str, Any]] | None = None) -> None:
        self._by_id: dict[str, SemanticValidator] = {}
        if validators is None:
            items: Iterable[tuple[str, Any]] = ()
        elif isinstance(validators, Mapping):
            items = validators.items()
        else:
            items = validators
        for validator_id, validator in items:
            self.register(validator_id, validator)

    def register(self, validator_id: Any, validator: Any) -> None:
        """Register ``validator`` under ``validator_id``; fail closed on a malformed/duplicate entry."""
        if not _is_bounded_token(validator_id, MAX_VALIDATOR_ID_LENGTH):
            raise StructuredOutputError(CODE_MALFORMED_VALIDATOR_ID, "validator_id must be a non-blank, bounded, single-line printable-ASCII identifier")
        if not callable(validator):
            raise StructuredOutputError(CODE_MALFORMED_VALIDATOR, f"validator {validator_id!r} must be callable")
        if validator_id in self._by_id:
            raise StructuredOutputError(CODE_DUPLICATE_VALIDATOR, f"validator id {validator_id!r} is already registered")
        self._by_id[validator_id] = validator

    def resolve(self, validator_id: Any) -> SemanticValidator:
        """Return the registered validator for ``validator_id`` or fail closed (no fallback)."""
        validator = self._by_id.get(validator_id)
        if validator is None:
            raise StructuredOutputError(CODE_UNKNOWN_VALIDATOR, f"no semantic validator is registered under id {validator_id!r}")
        return validator

    def contains(self, validator_id: Any) -> bool:
        """True iff ``validator_id`` is registered (a total, side-effect-free check)."""
        return validator_id in self._by_id

    def validator_ids(self) -> tuple[str, ...]:
        """Return the registered validator ids in first-registration order."""
        return tuple(self._by_id)

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, validator_id: object) -> bool:
        return validator_id in self._by_id


# --- Admission result shapes -------------------------------------------------


@dataclass(frozen=True)
class AdmissionAttempt:
    """A bounded summary of one repair attempt — index + outcome, never full content.

    ``reason_code`` is ``None`` when the attempt was accepted, else one of
    :data:`REASON_CODES`.  No prompt text, response text, or parsed payload is
    retained here — only the bounded outcome a future audit could safely keep.
    """

    index: int
    accepted: bool
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the attempt (stable key order)."""
        return {"index": self.index, "accepted": self.accepted, "reason_code": self.reason_code}


@dataclass(frozen=True)
class AdmissionDecision:
    """The inert result of an admission: accepted data + binding, or a rejection reason.

    Fields:

    - ``status`` — one of :data:`STATUSES`;
    - ``reason_code`` — ``None`` when accepted, else the bounded rejection code;
    - ``prompt_id`` / ``version`` / ``template_hash`` / ``target_schema`` — the prompt
      identity the response was bound to (``template_hash`` / ``target_schema`` are
      ``None`` when binding failed before the prompt resolved);
    - ``schema_id`` / ``schema_hash`` — the exact schema the response was held to
      (``None`` when binding failed before the schema resolved);
    - ``accepted_object`` — the parsed structured object on acceptance, else ``None``;
    - ``attempts`` — bounded per-candidate summaries;
    - ``max_attempts`` — the bound the repair retry honoured;
    - ``applied_semantic_validators`` — the ordered ids of the semantic validators the
      admission was held to (empty when none were requested or the failure happened
      before the semantic gate was resolved), so an accepted decision records which
      semantic gate it passed rather than leaving it implicit.

    The value is inert data returned to the caller; it is never written to project
    state, events, artifacts, domain tables, or full-content logs.
    """

    status: str
    reason_code: str | None
    prompt_id: str | None
    version: str | None
    template_hash: str | None
    target_schema: str | None
    schema_id: str | None
    schema_hash: str | None
    accepted_object: dict[str, Any] | None
    attempts: tuple[AdmissionAttempt, ...] = ()
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    applied_semantic_validators: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        """True iff the response was admitted under the exact registered target schema."""
        return self.status == STATUS_ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "prompt_id": self.prompt_id,
            "version": self.version,
            "template_hash": self.template_hash,
            "target_schema": self.target_schema,
            "schema_id": self.schema_id,
            "schema_hash": self.schema_hash,
            "accepted_object": self.accepted_object,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "max_attempts": self.max_attempts,
            "applied_semantic_validators": list(self.applied_semantic_validators),
        }


def _reject(
    reason_code: str,
    *,
    prompt: RegisteredPrompt | None = None,
    prompt_id: Any = None,
    version: Any = None,
    schema_id: str | None = None,
    schema_hash: str | None = None,
    attempts: tuple[AdmissionAttempt, ...] = (),
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    applied_semantic_validators: tuple[str, ...] = (),
) -> AdmissionDecision:
    """Build a rejected :class:`AdmissionDecision` with whatever binding is known."""
    return AdmissionDecision(
        status=STATUS_REJECTED,
        reason_code=reason_code,
        prompt_id=prompt.prompt_id if prompt is not None else (prompt_id if isinstance(prompt_id, str) else None),
        version=prompt.version if prompt is not None else (version if isinstance(version, str) else None),
        template_hash=prompt.template_hash if prompt is not None else None,
        target_schema=prompt.target_schema if prompt is not None else None,
        schema_id=schema_id,
        schema_hash=schema_hash,
        accepted_object=None,
        attempts=attempts,
        max_attempts=max_attempts,
        applied_semantic_validators=applied_semantic_validators,
    )


def _resolve_semantic_plan(
    semantic_validators: SemanticValidatorRegistry | Mapping[str, Any] | None,
    semantic_validator_ids: Iterable[str] | None,
) -> tuple[list[tuple[str, SemanticValidator]] | None, str | None]:
    """Resolve the ordered ``(id, validator)`` plan to run, or a fail-closed reason code.

    Returns ``(plan, None)`` on success — ``plan`` is empty when no semantic validation
    was requested (the existing schema-only admission), else the validators in requested
    order.  Returns ``(None, code)`` when the request list is malformed
    (:data:`CODE_MALFORMED_VALIDATOR_REQUEST`), a validator definition is malformed, or a
    requested id is unknown (:data:`CODE_UNKNOWN_VALIDATOR`) — never a silent no-op.  No
    candidate is consumed here, so a bad semantic configuration fails closed *before* any
    candidate is touched.
    """
    if semantic_validator_ids is None:
        return [], None
    # A bare string / bytes / mapping is never a valid *list of ids* (a string is
    # iterable but would silently iterate characters).
    if isinstance(semantic_validator_ids, (str, bytes, Mapping)):
        return None, CODE_MALFORMED_VALIDATOR_REQUEST
    try:
        requested = list(semantic_validator_ids)
    except TypeError:
        return None, CODE_MALFORMED_VALIDATOR_REQUEST
    if len(requested) > MAX_SEMANTIC_VALIDATORS:
        return None, CODE_MALFORMED_VALIDATOR_REQUEST
    if any(not _is_bounded_token(vid, MAX_VALIDATOR_ID_LENGTH) for vid in requested):
        return None, CODE_MALFORMED_VALIDATOR_REQUEST
    if len(set(requested)) != len(requested):
        return None, CODE_MALFORMED_VALIDATOR_REQUEST
    if not requested:
        return [], None

    # Normalize the available validators into a registry; never silently fall back.
    if isinstance(semantic_validators, SemanticValidatorRegistry):
        registry = semantic_validators
    elif semantic_validators is None:
        registry = SemanticValidatorRegistry()
    elif isinstance(semantic_validators, Mapping):
        try:
            registry = SemanticValidatorRegistry(semantic_validators)
        except StructuredOutputError as exc:
            return None, exc.code
    else:
        return None, CODE_MALFORMED_VALIDATOR_REQUEST

    plan: list[tuple[str, SemanticValidator]] = []
    for vid in requested:
        try:
            plan.append((vid, registry.resolve(vid)))
        except StructuredOutputError as exc:
            return None, exc.code
    return plan, None


def _run_semantic_validators(
    parsed: dict[str, Any],
    plan: list[tuple[str, SemanticValidator]],
    context: Mapping[str, Any],
) -> tuple[str, str | None]:
    """Run the semantic ``plan`` over an admitted object; return ``(outcome, reason_code)``.

    ``outcome`` is ``"accept"`` (every validator passed), ``"reject"`` (a validator
    cleanly judged the content invalid — :data:`CODE_SEMANTIC_REJECTED`, repairable by a
    later candidate), or ``"fatal"`` (a validator raised —
    :data:`CODE_SEMANTIC_VALIDATOR_ERROR` — or returned a malformed result —
    :data:`CODE_MALFORMED_VALIDATOR_RESULT`; a fault in the validator, not repairable).
    Each validator sees a private deep copy of the object, so it can neither mutate the
    object that may be accepted nor leak mutations to a later validator, and is run in
    requested order with short-circuit on the first non-accepting outcome.
    """
    for _validator_id, validator in plan:
        candidate_object = json.loads(json.dumps(parsed))
        try:
            result = validator(candidate_object, context)
        except Exception:
            # Fail closed on *any* validator fault — a broken validator must never be
            # mistaken for a passing one.
            return "fatal", CODE_SEMANTIC_VALIDATOR_ERROR
        if not _is_semantic_result(result):
            return "fatal", CODE_MALFORMED_VALIDATOR_RESULT
        if not result.valid:
            return "reject", CODE_SEMANTIC_REJECTED
    return "accept", None


def admit_structured_output(
    *,
    prompt_registry: PromptRegistry,
    prompt_id: Any,
    version: Any,
    schema_registry: SchemaRegistry,
    candidates: Iterable[LLMResponse],
    expected_template_hash: str | None = None,
    expected_schema_id: str | None = None,
    expected_schema_hash: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    semantic_validators: SemanticValidatorRegistry | Mapping[str, Any] | None = None,
    semantic_validator_ids: Iterable[str] | None = None,
    semantic_context: Mapping[str, Any] | None = None,
) -> AdmissionDecision:
    """Admit a structured response under a prompt's exact registered target schema.

    Resolves the prompt by stable identity (fail-closed, optionally pinned to
    ``expected_template_hash``), binds to the prompt's registered ``target_schema``
    (an ``expected_schema_id`` that disagrees fails closed — no silent fallback),
    resolves that schema (optionally pinned to ``expected_schema_hash``), then runs a
    bounded local repair retry over ``candidates`` (each an inert
    :class:`LLMResponse`): the first candidate that is a structurally valid response,
    parses to a JSON object, validates under the exact target schema, **and** passes
    every requested semantic validator is **accepted**; otherwise admission **fails
    closed**.  Returns an inert :class:`AdmissionDecision` and writes nothing.

    Semantic validation (T-05-04) is the optional gate that runs *after* schema
    admission and *before* a candidate is returned: ``semantic_validator_ids`` names,
    in order, the validators (resolved from ``semantic_validators`` — a
    :class:`SemanticValidatorRegistry` or a plain ``{id: callable}`` mapping) that each
    accepted object must pass, and ``semantic_context`` is inert local config handed to
    every validator.  A requested-but-unknown validator, a malformed request list, or a
    malformed validator definition fails closed up-front (no candidate consumed, no
    silent fall-back to no-op validation).  A candidate the schema accepts but a
    validator *cleanly rejects* is a repairable content failure, so a later candidate
    may still be accepted within the bound; a validator that *raises* or returns a
    malformed result is a fault in the validator and stops the retry early (fail
    closed).  When no validators are requested, admission is exactly the WP-05c
    schema-only behaviour.

    ``max_attempts`` bounds the retry to ``1..MAX_REPAIR_ATTEMPTS``; candidates beyond
    the bound are never tried — semantic validation runs only on candidates already
    within the bound and never consumes an extra one.  A structurally invalid response
    candidate stops the retry early (it is not repairable content).
    """
    if not _is_positive_int(max_attempts) or max_attempts > MAX_REPAIR_ATTEMPTS:
        return _reject(CODE_MALFORMED_MAX_ATTEMPTS, prompt_id=prompt_id, version=version, max_attempts=DEFAULT_MAX_ATTEMPTS)

    # 1. Resolve the prompt by stable identity; never fall back to unregistered.
    try:
        prompt = prompt_registry.resolve(prompt_id, version, expected_hash=expected_template_hash)
    except PromptRegistryError as exc:
        return _reject(exc.code, prompt_id=prompt_id, version=version, max_attempts=max_attempts)

    # 2. Bind to the prompt's registered target schema; reject a disagreeing caller
    #    id rather than silently honouring it.
    schema_id = prompt.target_schema
    if expected_schema_id is not None and expected_schema_id != schema_id:
        return _reject(CODE_SCHEMA_MISMATCH, prompt=prompt, schema_id=schema_id, max_attempts=max_attempts)

    # 3. Resolve that exact schema; unknown/drifted fails closed.
    try:
        schema = schema_registry.resolve(schema_id, expected_hash=expected_schema_hash)
    except StructuredOutputError as exc:
        return _reject(exc.code, prompt=prompt, schema_id=schema_id, max_attempts=max_attempts)
    schema_hash = hash_payload(schema)

    # 3b. Resolve the requested semantic-validator plan up-front, before any candidate
    #     is consumed: a malformed request, malformed validator, or unknown validator
    #     fails closed here with no silent fall-back to no-op validation.
    plan, plan_error = _resolve_semantic_plan(semantic_validators, semantic_validator_ids)
    if plan_error is not None:
        return _reject(plan_error, prompt=prompt, schema_id=schema_id, schema_hash=schema_hash, max_attempts=max_attempts)
    applied = tuple(vid for vid, _ in plan)
    if plan and semantic_context is not None and not isinstance(semantic_context, Mapping):
        return _reject(
            CODE_MALFORMED_VALIDATOR_REQUEST,
            prompt=prompt,
            schema_id=schema_id,
            schema_hash=schema_hash,
            max_attempts=max_attempts,
            applied_semantic_validators=applied,
        )
    context: Mapping[str, Any] = semantic_context if isinstance(semantic_context, Mapping) else {}

    # 4. Bounded local repair retry over the candidate sequence.  Consume the
    #    candidate iterable *lazily* and pull at most ``max_attempts`` items —
    #    ``islice`` never advances the source past the bound, so a candidate beyond
    #    ``max_attempts`` (which could do work, block, or raise while being produced)
    #    is never tried/consumed.  ``consumed`` distinguishes the zero-candidate case
    #    (``CODE_NO_CANDIDATES``) from bounded exhaustion (``CODE_REPAIR_EXHAUSTED``).
    attempts: list[AdmissionAttempt] = []
    consumed = 0
    for index, candidate in enumerate(islice(candidates, max_attempts)):
        consumed += 1
        if validate_response(candidate):
            attempts.append(AdmissionAttempt(index=index, accepted=False, reason_code=CODE_MALFORMED_RESPONSE))
            # A structurally invalid response is not repairable content: stop closed.
            return _reject(
                CODE_MALFORMED_RESPONSE,
                prompt=prompt,
                schema_id=schema_id,
                schema_hash=schema_hash,
                attempts=tuple(attempts),
                max_attempts=max_attempts,
                applied_semantic_validators=applied,
            )
        try:
            parsed = parse_structured_output(candidate.message.content)
        except StructuredOutputError as exc:
            attempts.append(AdmissionAttempt(index=index, accepted=False, reason_code=exc.code))
            continue
        violations = validate_instance(parsed, schema)
        if violations:
            attempts.append(AdmissionAttempt(index=index, accepted=False, reason_code=CODE_SCHEMA_VIOLATION))
            continue
        # Schema admission passed; run the optional semantic gate before accepting.
        outcome, semantic_code = _run_semantic_validators(parsed, plan, context)
        if outcome == "reject":
            # A clean semantic rejection is repairable: a later candidate may pass.
            attempts.append(AdmissionAttempt(index=index, accepted=False, reason_code=semantic_code))
            continue
        if outcome == "fatal":
            # A validator that raised / returned a malformed result is a fault in the
            # validator, not repairable content: stop the retry closed.
            attempts.append(AdmissionAttempt(index=index, accepted=False, reason_code=semantic_code))
            return _reject(
                semantic_code,
                prompt=prompt,
                schema_id=schema_id,
                schema_hash=schema_hash,
                attempts=tuple(attempts),
                max_attempts=max_attempts,
                applied_semantic_validators=applied,
            )
        attempts.append(AdmissionAttempt(index=index, accepted=True, reason_code=None))
        return AdmissionDecision(
            status=STATUS_ACCEPTED,
            reason_code=None,
            prompt_id=prompt.prompt_id,
            version=prompt.version,
            template_hash=prompt.template_hash,
            target_schema=prompt.target_schema,
            schema_id=schema_id,
            schema_hash=schema_hash,
            accepted_object=parsed,
            attempts=tuple(attempts),
            max_attempts=max_attempts,
            applied_semantic_validators=applied,
        )

    # 5a. No candidates were available at all — fail closed with the dedicated code.
    if consumed == 0:
        return _reject(
            CODE_NO_CANDIDATES,
            prompt=prompt,
            schema_id=schema_id,
            schema_hash=schema_hash,
            max_attempts=max_attempts,
            applied_semantic_validators=applied,
        )

    # 5b. Every bounded attempt failed — fail closed.
    return _reject(
        CODE_REPAIR_EXHAUSTED,
        prompt=prompt,
        schema_id=schema_id,
        schema_hash=schema_hash,
        attempts=tuple(attempts),
        max_attempts=max_attempts,
        applied_semantic_validators=applied,
    )


__all__ = [
    "MAX_OUTPUT_TEXT_LENGTH",
    "MAX_SCHEMA_ID_LENGTH",
    "MAX_VALIDATOR_ID_LENGTH",
    "MAX_VALIDATION_DEPTH",
    "MAX_REPAIR_ATTEMPTS",
    "DEFAULT_MAX_ATTEMPTS",
    "MAX_SEMANTIC_VALIDATORS",
    "STATUS_ACCEPTED",
    "STATUS_REJECTED",
    "STATUSES",
    "SCHEMA_TYPE_OBJECT",
    "SCHEMA_TYPE_ARRAY",
    "SCHEMA_TYPE_STRING",
    "SCHEMA_TYPE_INTEGER",
    "SCHEMA_TYPE_NUMBER",
    "SCHEMA_TYPE_BOOLEAN",
    "SCHEMA_TYPE_NULL",
    "SCHEMA_TYPES",
    "SUPPORTED_SCHEMA_KEYWORDS",
    "CODE_EMPTY_PAYLOAD",
    "CODE_MALFORMED_JSON",
    "CODE_MULTIPLE_PAYLOADS",
    "CODE_NON_FINITE_NUMBER",
    "CODE_PAYLOAD_TOO_LARGE",
    "CODE_UNSUPPORTED_SHAPE",
    "CODE_MALFORMED_SCHEMA_ID",
    "CODE_MALFORMED_SCHEMA",
    "CODE_DUPLICATE_SCHEMA",
    "CODE_UNKNOWN_SCHEMA",
    "CODE_SCHEMA_DRIFT",
    "CODE_SCHEMA_VIOLATION",
    "CODE_SCHEMA_MISMATCH",
    "CODE_MALFORMED_RESPONSE",
    "CODE_MALFORMED_MAX_ATTEMPTS",
    "CODE_NO_CANDIDATES",
    "CODE_REPAIR_EXHAUSTED",
    "CODE_MALFORMED_VALIDATOR_ID",
    "CODE_MALFORMED_VALIDATOR",
    "CODE_DUPLICATE_VALIDATOR",
    "CODE_UNKNOWN_VALIDATOR",
    "CODE_MALFORMED_VALIDATOR_REQUEST",
    "CODE_SEMANTIC_REJECTED",
    "CODE_SEMANTIC_VALIDATOR_ERROR",
    "CODE_MALFORMED_VALIDATOR_RESULT",
    "PARSE_CODES",
    "SCHEMA_CODES",
    "ADMISSION_CODES",
    "VALIDATOR_REGISTRY_CODES",
    "SEMANTIC_CODES",
    "REASON_CODES",
    "REPAIRABLE_CODES",
    "StructuredOutputError",
    "is_repairable",
    "parse_structured_output",
    "validate_schema_definition",
    "validate_instance",
    "SchemaRegistry",
    "SemanticValidator",
    "SemanticValidationResult",
    "SemanticValidatorRegistry",
    "AdmissionAttempt",
    "AdmissionDecision",
    "admit_structured_output",
]
