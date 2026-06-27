"""Local, deterministic OpenAPI contract/spec foundation (WP-04k / T-04-11).

The smallest *local* OpenAPI layer the control plane needs: a deterministic,
side-effect-free description of the command/operation/cancel/CLI shapes already
implemented in :mod:`auto_bioinfo.control_plane`.  It is a **contract document**,
not a running service.  Nothing here opens a socket, registers a route, starts a
web server, imports an HTTP framework, reads a clock, touches the filesystem or
network, or enforces an authorization policy.  :func:`build_openapi_spec` returns
a plain ``dict`` assembled from explicit literals and the *bounded vocabularies of
the existing contracts* (their status / reason-code / category tuples are imported
directly, so the spec can never drift from the code it describes), and
:func:`spec_to_json` serialises it deterministically with the standard library.

Design constraints (WP-04k), mirroring the WP-04g..j control-plane style:

- **Pure and deterministic.** Every function is a total function of its explicit
  inputs.  Building the spec twice yields equal dicts and byte-identical canonical
  JSON; inputs are never mutated.  No third-party OpenAPI package is required.
- **Bound to existing contracts.** Every path, ``operationId``, component schema,
  header/parameter, status category, and reason-code enum projects an existing
  local contract (command API idempotency/concurrency, operation-resource
  lifecycle, cancel-command decision, CLI result) — see
  :data:`IMPLEMENTED_OPERATIONS` and :data:`_CONTRACT_ENUMS`.  The spec invents no
  server, storage, worker, or permission behaviour.
- **Fail closed on inconsistency.** :func:`validate_openapi_spec` rejects a spec
  with duplicate operation ids, ``$ref``\\s to missing components, operations that
  do not bind to an implemented contract, status/reason-code enums that do not
  match the bounded vocabulary, or any accidental ``security`` /
  ``securitySchemes`` requirement (auth/RBAC is a later WP-04l slice, not here).
- **Bounded transport projections.** Idempotency key, optimistic-concurrency
  expected version, operation status polling/result categories, and the
  cancel-command outcome are projected as bounded headers/parameters/enums only.
"""

from __future__ import annotations

import json
from typing import Any

from . import cancel_command as _cancel
from . import command_api as _command
from .cli_contract import CLI_REASON_CODES, CLI_STATUSES
from .operation_resource import ERROR_CODES, OPERATION_STATUSES, PROJECTION_CATEGORIES

# The OpenAPI dialect this document targets.  3.0.x is chosen for the broadest
# tool compatibility; the structure stays within the 3.x-common subset.
OPENAPI_VERSION = "3.0.3"

# A purely local, non-routable server entry.  It documents that these shapes are a
# local contract projection, not a deployed/hosted endpoint — there is no real
# host, scheme, or port here.
LOCAL_SERVER_URL = "local:///auto-bioinfo/control-plane"

# Controlled transport headers, re-exported from the command API so the spec and
# the code share one source of truth for their names.
IDEMPOTENCY_KEY_HEADER = _command.IDEMPOTENCY_KEY_HEADER
EXPECTED_VERSION_HEADER = _command.EXPECTED_VERSION_HEADER

# --- Stable validation issue codes ------------------------------------------
# Callers branch on these, so they must stay stable.
CODE_MALFORMED_SPEC = "OPENAPI_MALFORMED_SPEC"
CODE_DUPLICATE_OPERATION_ID = "OPENAPI_DUPLICATE_OPERATION_ID"
CODE_MISSING_REF = "OPENAPI_MISSING_REF"
CODE_UNIMPLEMENTED_OPERATION = "OPENAPI_UNIMPLEMENTED_OPERATION"
CODE_MALFORMED_ENUM = "OPENAPI_MALFORMED_ENUM"
CODE_UNEXPECTED_SECURITY = "OPENAPI_UNEXPECTED_SECURITY"

VALIDATION_CODES = (
    CODE_MALFORMED_SPEC,
    CODE_DUPLICATE_OPERATION_ID,
    CODE_MISSING_REF,
    CODE_UNIMPLEMENTED_OPERATION,
    CODE_MALFORMED_ENUM,
    CODE_UNEXPECTED_SECURITY,
)

# --- The implemented-contract registry --------------------------------------
# Every ``operationId`` the spec exposes must name an existing pure control-plane
# decision function (a "binds to an existing local contract" guarantee).  The
# value is the dotted path of the backing callable, so a test can assert it is
# importable and the validator can reject an operationId that names no contract.
IMPLEMENTED_OPERATIONS: dict[str, str] = {
    "admitCommand": "auto_bioinfo.control_plane.command_api.evaluate_command_request",
    "getOperation": "auto_bioinfo.control_plane.operation_resource.project_operation",
    "cancelOperation": "auto_bioinfo.control_plane.cancel_command.evaluate_cancel_request",
    "runCli": "auto_bioinfo.control_plane.cli_contract.run_cli",
}


def _dedup_preserving_order(*groups: tuple[str, ...]) -> list[str]:
    """Concatenate ``groups`` into one list, dropping later duplicates.

    Deterministic: the first occurrence of each value wins and relative order is
    preserved, so the result is a stable function of the inputs.
    """
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for value in group:
            if value not in seen:
                seen.add(value)
                out.append(value)
    return out


# The CLI result's reason code is either a CLI parse/usage code or the underlying
# contract's reason code (the CLI dispatches onto the command API / cancel
# contract), so its bounded vocabulary is the union of all three, order-stable.
CLI_RESULT_REASON_CODES: tuple[str, ...] = tuple(_dedup_preserving_order(CLI_REASON_CODES, _command.REASON_CODES, _cancel.REASON_CODES))

# --- Enum bindings: (schema, field) -> the bounded contract vocabulary -------
# The validator checks each of these against the enum actually present in the
# spec, so a status/reason-code enum that drifts from the contract is rejected as
# malformed.  Each tuple is imported straight from the owning contract module.
_CONTRACT_ENUMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("CommandApiResult", "status"): _command.STATUSES,
    ("CommandApiResult", "reason_code"): _command.REASON_CODES,
    ("OperationRecord", "status"): OPERATION_STATUSES,
    ("OperationProjection", "category"): PROJECTION_CATEGORIES,
    ("OperationProjection", "error_code"): ERROR_CODES,
    ("CancelDecision", "status"): _cancel.STATUSES,
    ("CancelDecision", "reason_code"): _cancel.REASON_CODES,
    ("CliResult", "status"): CLI_STATUSES,
    ("CliResult", "reason_code"): CLI_RESULT_REASON_CODES,
}


def _enum(schema: str, field: str) -> list[str]:
    """The bounded enum for ``schema.field``, as a fresh list (spec-ready)."""
    return list(_CONTRACT_ENUMS[(schema, field)])


def _ref(name: str) -> dict[str, str]:
    """A ``$ref`` to a component schema."""
    return {"$ref": f"#/components/schemas/{name}"}


def _param_ref(name: str) -> dict[str, str]:
    """A ``$ref`` to a reusable component parameter."""
    return {"$ref": f"#/components/parameters/{name}"}


def _string(**extra: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    schema.update(extra)
    return schema


def _json_response(description: str, schema_name: str) -> dict[str, Any]:
    """A single ``application/json`` 200 response bound to a component schema."""
    return {
        "200": {
            "description": description,
            "content": {"application/json": {"schema": _ref(schema_name)}},
        }
    }


# --- Component schemas (bound to each contract's ``to_dict`` shape) ----------


def _build_schemas() -> dict[str, Any]:
    """The component schemas, each mirroring an existing contract's projection."""
    return {
        # command_api.CommandApiResult.binding
        "CommandApiBinding": {
            "type": "object",
            "description": "Audit binding recorded by the command-API admission decision.",
            "properties": {
                "command_type": _string(nullable=True),
                "command_fingerprint": _string(),
                "idempotency_key": _string(),
                "expected_version": {"type": "integer", "nullable": True},
                "current_version": {"type": "integer", "nullable": True},
            },
        },
        # command_api.CommandApiResult.to_dict
        "CommandApiResult": {
            "type": "object",
            "description": "Deterministic, reason-coded outcome of a mutating-command admission check (idempotency + optimistic concurrency).",
            "required": ["status", "reason_code", "accepted", "is_replay"],
            "properties": {
                "status": _string(enum=_enum("CommandApiResult", "status")),
                "reason_code": _string(enum=_enum("CommandApiResult", "reason_code")),
                "message": _string(),
                "accepted": {"type": "boolean"},
                "is_replay": {"type": "boolean"},
                "binding": _ref("CommandApiBinding"),
            },
        },
        # operation_resource.OperationRecord.to_dict
        "OperationRecord": {
            "type": "object",
            "description": "A long-running command's operation as a bounded lifecycle value.",
            "required": ["operation_id", "command_type", "status", "is_terminal"],
            "properties": {
                "operation_id": _string(),
                "command_type": _string(),
                "command_fingerprint": _string(),
                "idempotency_key": _string(),
                "status": _string(enum=_enum("OperationRecord", "status")),
                "is_terminal": {"type": "boolean"},
                "result": {"type": "object", "nullable": True},
                "error": {"type": "object", "nullable": True},
                "created_at": _string(nullable=True),
                "updated_at": _string(nullable=True),
            },
        },
        # operation_resource.OperationProjection.to_dict (status polling / result)
        "OperationProjection": {
            "type": "object",
            "description": "Transport-facing projection of an operation for status polling; malformed facts fail closed to the 'malformed' category.",
            "required": ["category", "terminal"],
            "properties": {
                "category": _string(enum=_enum("OperationProjection", "category")),
                "terminal": {"type": "boolean"},
                "operation": _ref("OperationRecord"),
                "error_code": _string(enum=_enum("OperationProjection", "error_code") + [""]),
                "message": _string(),
            },
        },
        # cancel_command.CancelDecision.binding
        "CancelBinding": {
            "type": "object",
            "description": "Audit binding recorded by the cancel-command decision.",
            "properties": {
                "operation_id": _string(nullable=True),
                "command_type": _string(nullable=True),
                "idempotency_key": _string(nullable=True),
                "command_fingerprint": _string(),
                "expected_version": {"type": "integer", "nullable": True},
                "current_version": {"type": "integer", "nullable": True},
                "operation_status": _string(nullable=True),
                "authority_keys": {"type": "array", "items": _string()},
            },
        },
        # cancel_command.CancelDecision.to_dict
        "CancelDecision": {
            "type": "object",
            "description": "Deterministic, reason-coded outcome of a cancel-command evaluation; 'operation' is the projected cancelled record (no real worker is touched).",
            "required": ["status", "reason_code", "cancelled"],
            "properties": {
                "status": _string(enum=_enum("CancelDecision", "status")),
                "reason_code": _string(enum=_enum("CancelDecision", "reason_code")),
                "message": _string(),
                "cancelled": {"type": "boolean"},
                "binding": _ref("CancelBinding"),
                "operation": {**_ref("OperationRecord"), "nullable": True},
            },
        },
        # cli_contract.CliResult.to_dict
        "CliResult": {
            "type": "object",
            "description": "Deterministic, reason-coded outcome of a parsed CLI invocation mapped onto a control-plane decision.",
            "required": ["status", "exit_code", "reason_code", "ok"],
            "properties": {
                "status": _string(enum=_enum("CliResult", "status")),
                "exit_code": {"type": "integer"},
                "reason_code": _string(enum=_enum("CliResult", "reason_code")),
                "ok": {"type": "boolean"},
                "stdout": _string(),
                "stderr": _string(),
                "binding": {"type": "object"},
            },
        },
        # --- Request bodies (bounded inputs to the existing contracts) -------
        "CommandRequestBody": {
            "type": "object",
            "description": "A mutating command request body; the idempotency key and expected version travel as controlled headers.",
            "required": ["command_type"],
            "properties": {
                "command_type": _string(),
                "payload": {"type": "object"},
            },
        },
        "CancelRequestBody": {
            "type": "object",
            "description": "Explicit facts a cancel request supplies; the operation state is described explicitly (no server-side fabrication of identity).",
            "required": ["command_type", "operation"],
            "properties": {
                "command_type": _string(),
                "reason": _string(nullable=True),
                "operation": _ref("OperationRecord"),
            },
        },
        "CliRequestBody": {
            "type": "object",
            "description": "An explicit argv vector parsed deterministically by the CLI contract.",
            "required": ["argv"],
            "properties": {"argv": {"type": "array", "items": _string()}},
        },
    }


def _build_parameters() -> dict[str, Any]:
    """Reusable component parameters: the bounded transport projections."""
    return {
        "IdempotencyKeyHeader": {
            "name": IDEMPOTENCY_KEY_HEADER,
            "in": "header",
            "required": True,
            "description": "Idempotency key binding the mutating command's identity; same key + same payload is a replay, same key + different payload fails closed.",
            "schema": _string(maxLength=_command.MAX_IDEMPOTENCY_KEY_LENGTH),
        },
        "ExpectedVersionHeader": {
            "name": EXPECTED_VERSION_HEADER,
            "in": "header",
            "required": False,
            "description": "Optimistic-concurrency expected version; a stale/malformed value fails closed rather than overwriting an unseen version.",
            "schema": _string(pattern="^[1-9][0-9]*$"),
        },
        "OperationIdPath": {
            "name": "operationId",
            "in": "path",
            "required": True,
            "description": "Stable identity of the target operation.",
            "schema": _string(maxLength=_command.MAX_IDEMPOTENCY_KEY_LENGTH),
        },
    }


def _build_paths() -> dict[str, Any]:
    """The path table; each operationId binds to an implemented contract."""
    return {
        "/commands": {
            "post": {
                "operationId": "admitCommand",
                "summary": "Evaluate whether a mutating command may be admitted, replayed, or fails closed (command-API idempotency/concurrency contract).",
                "parameters": [_param_ref("IdempotencyKeyHeader"), _param_ref("ExpectedVersionHeader")],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("CommandRequestBody")}},
                },
                "responses": _json_response("The admission decision.", "CommandApiResult"),
            }
        },
        "/operations/{operationId}": {
            "parameters": [_param_ref("OperationIdPath")],
            "get": {
                "operationId": "getOperation",
                "summary": "Project a tracked operation for status polling (accepted / succeeded / failed / cancelled / malformed).",
                "responses": _json_response("The operation projection.", "OperationProjection"),
            },
        },
        "/operations/{operationId}/cancel": {
            "parameters": [_param_ref("OperationIdPath")],
            "post": {
                "operationId": "cancelOperation",
                "summary": "Evaluate whether a tracked operation may move to the bounded 'cancelled' terminal state, given its explicit current facts.",
                "parameters": [_param_ref("IdempotencyKeyHeader"), _param_ref("ExpectedVersionHeader")],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("CancelRequestBody")}},
                },
                "responses": _json_response("The cancel decision.", "CancelDecision"),
            },
        },
        "/cli/invocations": {
            "post": {
                "operationId": "runCli",
                "summary": "Evaluate an explicit argv vector through the deterministic CLI command contract.",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("CliRequestBody")}},
                },
                "responses": _json_response("The CLI result.", "CliResult"),
            }
        },
    }


def build_openapi_spec() -> dict[str, Any]:
    """Build the deterministic local OpenAPI 3.x contract document.

    A pure function: it reads no external state, performs no I/O, and returns a
    freshly-constructed ``dict`` (so a caller may mutate the result without
    affecting a later build).  The bounded enums are imported from the owning
    contract modules, so the document cannot drift from the code it describes.
    Deliberately carries **no** ``security`` / ``securitySchemes`` block —
    auth/RBAC is a later WP-04l slice, and :func:`validate_openapi_spec` rejects
    any such block appearing here.
    """
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "auto_bioinfo control plane (local contract)",
            "version": "0.4.11",
            "description": (
                "Local, deterministic OpenAPI projection of the auto_bioinfo control-plane "
                "command/operation/cancel/CLI contracts. This is a contract document only: "
                "no running HTTP server, deployment, persistence, worker, or authorization is implied."
            ),
        },
        "servers": [{"url": LOCAL_SERVER_URL, "description": "Local, non-routable contract projection (not a deployed endpoint)."}],
        "paths": _build_paths(),
        "components": {
            "parameters": _build_parameters(),
            "schemas": _build_schemas(),
        },
    }


def spec_to_json(spec: dict[str, Any] | None = None, *, canonical: bool = False) -> str:
    """Serialise the spec deterministically with the standard library.

    ``canonical=True`` emits compact, key-sorted JSON (byte-stable regardless of
    dict construction order) suitable for hashing/fixtures; otherwise it emits a
    stably-ordered, indented document.  Performs no file or network I/O — it only
    returns the string.  When ``spec`` is ``None`` a fresh :func:`build_openapi_spec`
    is serialised.
    """
    if spec is None:
        spec = build_openapi_spec()
    if canonical:
        return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return json.dumps(spec, indent=2, ensure_ascii=True)


# --- Validation -------------------------------------------------------------


def _iter_refs(node: Any) -> list[str]:
    """Collect every ``$ref`` string anywhere in ``node`` (depth-first)."""
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(_iter_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_iter_refs(item))
    return refs


def _resolve_local_ref(spec: dict[str, Any], ref: str) -> bool:
    """True iff ``ref`` (``#/a/b/c``) resolves to a present node in ``spec``."""
    if not ref.startswith("#/"):
        return False
    node: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def _operation_items(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Yield ``(path, http_method, operation)`` for every operation object."""
    methods = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
    out: list[tuple[str, str, dict[str, Any]]] = []
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return out
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in methods:
            op = item.get(method)
            if isinstance(op, dict):
                out.append((path, method, op))
    return out


def _has_security(spec: dict[str, Any]) -> bool:
    """True iff the spec carries any auth/security requirement (forbidden here)."""
    if spec.get("security"):
        return True
    components = spec.get("components")
    if isinstance(components, dict) and components.get("securitySchemes"):
        return True
    return any(op.get("security") for _, _, op in _operation_items(spec))


def validate_openapi_spec(spec: Any) -> list[tuple[str, str]]:
    """Return ``[(code, message), ...]`` for every way ``spec`` is inconsistent.

    An empty list means the spec is internally consistent and bound to existing
    contracts.  Fail-closed checks, each pairing a stable :data:`VALIDATION_CODES`
    code with a message:

    1. structural — ``openapi`` / ``info`` / ``paths`` / ``components.schemas``
       must be present and well-typed;
    2. no auth/security — a ``security`` block, per-operation ``security``, or
       ``components.securitySchemes`` is rejected (auth/RBAC is WP-04l, not here);
    3. unique operation ids — a duplicated ``operationId`` is rejected;
    4. implemented contracts — every ``operationId`` must name a contract in
       :data:`IMPLEMENTED_OPERATIONS`;
    5. resolvable refs — every ``$ref`` must resolve to a present local node;
    6. bounded enums — each registered status/reason-code enum must equal its
       contract's bounded vocabulary.
    """
    issues: list[tuple[str, str]] = []
    if not isinstance(spec, dict):
        return [(CODE_MALFORMED_SPEC, "spec must be a dict")]

    # 1. Structural.
    if not isinstance(spec.get("openapi"), str) or not spec["openapi"].startswith("3."):
        issues.append((CODE_MALFORMED_SPEC, "openapi must be a 3.x version string"))
    if not isinstance(spec.get("info"), dict):
        issues.append((CODE_MALFORMED_SPEC, "info must be an object"))
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        issues.append((CODE_MALFORMED_SPEC, "paths must be a non-empty object"))
    components = spec.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    if not isinstance(schemas, dict):
        issues.append((CODE_MALFORMED_SPEC, "components.schemas must be an object"))

    # 2. No auth/security before WP-04l.
    if _has_security(spec):
        issues.append((CODE_UNEXPECTED_SECURITY, "spec must not declare any security requirement or securityScheme before WP-04l"))

    operations = _operation_items(spec)

    # 3. Unique operation ids + 4. implemented-contract binding.
    seen_ids: set[str] = set()
    for path, method, op in operations:
        op_id = op.get("operationId")
        if not isinstance(op_id, str) or not op_id:
            issues.append((CODE_MALFORMED_SPEC, f"{method.upper()} {path} is missing a string operationId"))
            continue
        if op_id in seen_ids:
            issues.append((CODE_DUPLICATE_OPERATION_ID, f"operationId {op_id!r} is declared more than once"))
        seen_ids.add(op_id)
        if op_id not in IMPLEMENTED_OPERATIONS:
            issues.append((CODE_UNIMPLEMENTED_OPERATION, f"operationId {op_id!r} does not bind to an implemented control-plane contract"))

    # 5. Every $ref resolves locally.
    for ref in _iter_refs(spec):
        if not _resolve_local_ref(spec, ref):
            issues.append((CODE_MISSING_REF, f"$ref {ref!r} does not resolve to a present component"))

    # 6. Bounded enums match the owning contract's vocabulary.
    if isinstance(schemas, dict):
        for (schema_name, field), expected in _CONTRACT_ENUMS.items():
            schema = schemas.get(schema_name)
            if not isinstance(schema, dict):
                issues.append((CODE_MALFORMED_ENUM, f"schema {schema_name!r} is missing for enum field {field!r}"))
                continue
            prop = schema.get("properties", {}).get(field) if isinstance(schema.get("properties"), dict) else None
            enum = prop.get("enum") if isinstance(prop, dict) else None
            if not isinstance(enum, list):
                issues.append((CODE_MALFORMED_ENUM, f"{schema_name}.{field} must declare an enum"))
                continue
            extra = set(enum) - set(expected) - {""}
            missing = set(expected) - set(enum)
            if extra or missing:
                issues.append(
                    (
                        CODE_MALFORMED_ENUM,
                        f"{schema_name}.{field} enum does not match the bounded contract vocabulary (unexpected={sorted(extra)}, missing={sorted(missing)})",
                    )
                )
    return issues


__all__ = [
    "OPENAPI_VERSION",
    "LOCAL_SERVER_URL",
    "IDEMPOTENCY_KEY_HEADER",
    "EXPECTED_VERSION_HEADER",
    "CODE_MALFORMED_SPEC",
    "CODE_DUPLICATE_OPERATION_ID",
    "CODE_MISSING_REF",
    "CODE_UNIMPLEMENTED_OPERATION",
    "CODE_MALFORMED_ENUM",
    "CODE_UNEXPECTED_SECURITY",
    "VALIDATION_CODES",
    "IMPLEMENTED_OPERATIONS",
    "CLI_RESULT_REASON_CODES",
    "build_openapi_spec",
    "spec_to_json",
    "validate_openapi_spec",
]
