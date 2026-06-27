"""Local tool allowlist & Tool Broker contract (WP-05f / T-05-06).

The smallest *local* contract the future agent gateway (WP-05) needs so that —
before any real external tool, shell, subprocess, network, or provider call ever
exists — it can take an explicit, inert *tool call request*, check it against an
**explicit allowlist** of registered tool identities/versions, and return a
**bounded mediation decision as data only** — *without ever spawning a process,
opening a socket, importing a tool/SDK, reading a credential, reaching the
network, calling a paid service, or letting any content leave the process*.

This is the local mediation-contract foundation slice only.  It defines:

- bounded request / identity / argument data shapes (:class:`ToolCallRequest`) and a
  bounded allowlist entry (:class:`ToolSpec`) that names a tool identity, the exact
  versions it admits, whether it is enabled, an optional caller allowlist, and the
  single deterministic in-process handler that an *allowed* call may run;
- an explicit allowlist/registry contract (:class:`ToolRegistry`) that resolves a tool
  only by stable identity and **never silently falls back**: an unknown, malformed,
  disabled, version-mismatched, or caller-disallowed tool fails closed;
- a :class:`ToolBroker` that evaluates a request against the allowlist and, only for an
  authorized call whose arguments are bounded, serializable, and free of raw sensitive
  content, runs the registered handler and returns an inert :class:`ToolMediationDecision`
  carrying a bounded, redacted result — or, for everything else, a fail-closed ``denied``
  decision carrying only a bounded reason code and no result.

Design constraints (mirroring the WP-05a / WP-05b / WP-05c / WP-05d / WP-05e style):

- **Pure, deterministic, offline.**  No I/O whatsoever: no subprocess, shell, real
  tool, network, socket, HTTP client, provider SDK, environment/credential access,
  real clock, threads, or file/DB/queue side effect.  A mediation decision is a total
  function of its explicit in-memory inputs (the allowlist plus the request).  Any
  "execution" is only the in-process, caller-supplied **fake handler** the registered
  :class:`ToolSpec` carries; the handler contract is that it, too, stays inert.
- **Fail closed, no fallback.**  Every uncertainty resolves to a bounded, reason-coded
  ``denied`` decision (:data:`REASON_CODES`).  A malformed request/identity/arguments,
  an unknown / disabled / version-mismatched / caller-disallowed tool, an oversized or
  non-serializable argument payload, a raw sensitive argument, a handler that raises,
  or a malformed / oversized handler result all fail closed.  An unauthorized request
  can **never** fall back to a default or no-op allowed handler — there is no catch-all
  handler, and the handler is reached only after every allowlist check has passed.
- **No raw sensitive leak.**  An argument classified ``sensitive`` by the WP-05e
  contract (:func:`~auto_bioinfo.agent_gateway.context_builder.classify_field_sensitivity`)
  is blocked before any handler sees it; the admitted arguments are additionally
  redacted (:func:`~auto_bioinfo.observability.redaction.redact`) of inline secrets, and
  the returned result is redacted too — no raw credential-like value reaches a handler
  or a public projection.
- **Data only.**  The broker returns *data* to the caller: an inert
  :class:`ToolMediationDecision`.  It writes no project state, business object, event,
  artifact, queue/outbox record, ordinary domain table, report, or full-content log,
  and it mutates none of its inputs.

Out of scope for T-05-06 (and deliberately *not* implemented here): any real tool /
shell / subprocess / network / HTTP / MCP / OpenAPI / SDK integration or content
egress, real LLM/provider calls, raw-output artifact storage (T-05-07), provider /
model / prompt / tool-usage / timing audit records (T-05-08), budget / rate-limit /
circuit-breaker machinery (T-05-09), fake-model fixture expansion (T-05-10), the eval
framework (T-05-11), prompt approval / rollback (T-05-12), and any write of a tool
result into project state, events, artifacts, logs, or downstream domain/business
objects.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from auto_bioinfo.observability.redaction import redact

from .context_builder import SENSITIVITY_SENSITIVE, classify_field_sensitivity

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated.
MAX_TOOL_ID_LENGTH = 200
MAX_TOOL_VERSION_LENGTH = 100
MAX_CALLER_ID_LENGTH = 200
MAX_PROJECT_REF_LENGTH = 200
MAX_TOOL_VERSIONS = 64
MAX_ALLOWED_CALLERS = 256
MAX_TOOL_ARGUMENTS = 64
MAX_ARG_NAME_LENGTH = 200
MAX_PAYLOAD_DEPTH = 32
MAX_ARGUMENTS_BYTES = 65_536
MAX_RESULT_BYTES = 65_536

# --- Bounded mediation status vocabulary -------------------------------------
# ``allowed`` means the request passed every allowlist check and the registered
# handler produced a bounded, inert, redacted result.  ``denied`` is the
# fail-closed outcome for everything else; it never carries a result.
STATUS_ALLOWED = "allowed"
STATUS_DENIED = "denied"

STATUSES = (STATUS_ALLOWED, STATUS_DENIED)

# --- Stable reason codes -----------------------------------------------------
# Callers / a future gateway branch on these machine-readable codes, never the
# human message, so they must stay stable.
# request-shape failures (the request never reaches the allowlist):
CODE_MALFORMED_REQUEST = "TOOL_MALFORMED_REQUEST"
CODE_MALFORMED_IDENTITY = "TOOL_MALFORMED_IDENTITY"
CODE_MALFORMED_ARGUMENTS = "TOOL_MALFORMED_ARGUMENTS"
CODE_TOO_MANY_ARGUMENTS = "TOOL_TOO_MANY_ARGUMENTS"
CODE_ARGUMENTS_TOO_LARGE = "TOOL_ARGUMENTS_TOO_LARGE"
CODE_NONSERIALIZABLE_ARGUMENTS = "TOOL_NONSERIALIZABLE_ARGUMENTS"
CODE_SENSITIVE_ARGUMENT = "TOOL_SENSITIVE_ARGUMENT"
# allowlist failures (the identity is rejected against the registry):
CODE_UNKNOWN_TOOL = "TOOL_UNKNOWN"
CODE_TOOL_DISABLED = "TOOL_DISABLED"
CODE_VERSION_MISMATCH = "TOOL_VERSION_MISMATCH"
CODE_CALLER_NOT_ALLOWED = "TOOL_CALLER_NOT_ALLOWED"
# execution failures (an authorized handler misbehaves — still fail closed):
CODE_HANDLER_ERROR = "TOOL_HANDLER_ERROR"
CODE_MALFORMED_RESULT = "TOOL_MALFORMED_RESULT"
CODE_RESULT_TOO_LARGE = "TOOL_RESULT_TOO_LARGE"

REQUEST_CODES = (
    CODE_MALFORMED_REQUEST,
    CODE_MALFORMED_IDENTITY,
    CODE_MALFORMED_ARGUMENTS,
    CODE_TOO_MANY_ARGUMENTS,
    CODE_ARGUMENTS_TOO_LARGE,
    CODE_NONSERIALIZABLE_ARGUMENTS,
    CODE_SENSITIVE_ARGUMENT,
)

ALLOWLIST_CODES = (
    CODE_UNKNOWN_TOOL,
    CODE_TOOL_DISABLED,
    CODE_VERSION_MISMATCH,
    CODE_CALLER_NOT_ALLOWED,
)

EXECUTION_CODES = (
    CODE_HANDLER_ERROR,
    CODE_MALFORMED_RESULT,
    CODE_RESULT_TOO_LARGE,
)

REASON_CODES = REQUEST_CODES + ALLOWLIST_CODES + EXECUTION_CODES

# --- Registration-time codes (raised, not returned) --------------------------
# A malformed / duplicate allowlist entry is a *programming* error surfaced when
# the registry is built, distinct from the per-request mediation reason codes.
CODE_MALFORMED_TOOL_ID = "TOOL_REG_MALFORMED_ID"
CODE_MALFORMED_TOOL_VERSIONS = "TOOL_REG_MALFORMED_VERSIONS"
CODE_MALFORMED_ALLOWED_CALLERS = "TOOL_REG_MALFORMED_CALLERS"
CODE_MALFORMED_HANDLER = "TOOL_REG_MALFORMED_HANDLER"
CODE_DUPLICATE_TOOL = "TOOL_REG_DUPLICATE"

REGISTRY_CODES = (
    CODE_MALFORMED_TOOL_ID,
    CODE_MALFORMED_TOOL_VERSIONS,
    CODE_MALFORMED_ALLOWED_CALLERS,
    CODE_MALFORMED_HANDLER,
    CODE_DUPLICATE_TOOL,
)


class ToolBrokerError(Exception):
    """A fail-closed allowlist *registration* error carrying a bounded reason code.

    Raised only while building / mutating a :class:`ToolRegistry` (a malformed or
    duplicate :class:`ToolSpec`).  Per-*request* failures never raise — they resolve to
    a bounded ``denied`` :class:`ToolMediationDecision` instead.
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


# --- Small, pure predicates --------------------------------------------------


def _is_bounded_token(value: Any, max_length: int) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII token."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= max_length and all("\x20" <= ch <= "\x7e" for ch in value)


_PAYLOAD_NONSERIALIZABLE = "nonserializable"
_PAYLOAD_MALFORMED = "malformed"


class _InertPayloadError(Exception):
    """Internal: a value could not be normalized to a bounded, JSON-able payload.

    ``kind`` is :data:`_PAYLOAD_NONSERIALIZABLE` for a non-serializable leaf / key
    (e.g. a set, a ``bytes`` value, a non-string mapping key) and
    :data:`_PAYLOAD_MALFORMED` for an otherwise-malformed payload (over-deep nesting, a
    non-finite float), so the caller can map to the right bounded reason code.
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(f"payload is not a bounded JSON-able value ({kind})")


def _to_plain(value: Any, depth: int = 0) -> Any:
    """Normalize ``value`` to a bounded, plain, JSON-able structure or fail closed.

    Walks mappings / lists / tuples up to :data:`MAX_PAYLOAD_DEPTH` (an over-deep
    structure fails closed), normalizes every mapping to a plain ``dict`` (rejecting a
    non-string key) and every list/tuple to a plain ``list``, and admits only JSON
    scalar leaves (``str`` / ``bool`` / ``int`` / finite ``float`` / ``None``).  Any
    other leaf, a non-string mapping key, or a non-finite float raises
    :class:`_InertPayloadError`.  Pure; performs no I/O and mutates nothing.
    """
    if depth > MAX_PAYLOAD_DEPTH:
        raise _InertPayloadError(_PAYLOAD_MALFORMED)
    # ``bool`` is a subclass of ``int``; both are admissible JSON scalars.
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _InertPayloadError(_PAYLOAD_MALFORMED)
        return value
    if isinstance(value, Mapping):
        plain: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _InertPayloadError(_PAYLOAD_NONSERIALIZABLE)
            plain[key] = _to_plain(item, depth + 1)
        return plain
    if isinstance(value, (list, tuple)):
        return [_to_plain(item, depth + 1) for item in value]
    raise _InertPayloadError(_PAYLOAD_NONSERIALIZABLE)


def _payload_bytes(plain: Any) -> int:
    """Return the UTF-8 byte length of the canonical JSON encoding of ``plain``."""
    return len(json.dumps(plain, sort_keys=True, ensure_ascii=False).encode("utf-8"))


# --- Allowlist entry & registry ----------------------------------------------


# A handler is a deterministic, in-process, offline callable ``(arguments) -> result``
# that the registry binds to an allowed tool.  It receives the already bounded,
# sanitized (redacted) plain-dict arguments and must itself stay inert: it must never
# spawn a process, open a socket, read a credential, reach the network, touch the
# filesystem / clock / env, or mutate shared state.  A handler that raises is treated
# as a fail-closed execution fault (:data:`CODE_HANDLER_ERROR`); a handler that returns
# a non-bounded / non-serializable value fails closed (:data:`CODE_MALFORMED_RESULT`).
ToolHandler = Any


@dataclass(frozen=True)
class ToolSpec:
    """One bounded allowlist entry: an admitted tool identity + its inert handler.

    Fields:

    - ``tool_id`` — the stable tool identity (a bounded printable-ASCII token);
    - ``versions`` — the exact, non-empty set of admitted version strings; a request
      naming any other version is denied (:data:`CODE_VERSION_MISMATCH`);
    - ``handler`` — the single deterministic in-process callable an *allowed* call runs;
    - ``enabled`` — when ``False`` the tool is registered but every call is denied
      (:data:`CODE_TOOL_DISABLED`);
    - ``allowed_callers`` — when not ``None``, the explicit set of caller ids permitted
      to invoke this tool; a request from any other caller is denied
      (:data:`CODE_CALLER_NOT_ALLOWED`).  ``None`` means the tool is not caller-gated.

    The spec is validated (fail-closed) at registration; an instance is inert data.
    """

    tool_id: str
    versions: tuple[str, ...]
    handler: ToolHandler
    enabled: bool = True
    allowed_callers: tuple[str, ...] | None = None

    def admits_version(self, version: Any) -> bool:
        """True iff ``version`` is one of this tool's exactly admitted versions."""
        return isinstance(version, str) and version in self.versions

    def admits_caller(self, caller_id: Any) -> bool:
        """True iff this tool is not caller-gated, or ``caller_id`` is explicitly allowed."""
        if self.allowed_callers is None:
            return True
        return isinstance(caller_id, str) and caller_id in self.allowed_callers


class ToolRegistry:
    """An in-memory allowlist resolving tools only by explicit identity (no fallback).

    Registration validates the :class:`ToolSpec` (fail-closed) and rejects a duplicate
    ``tool_id``.  Resolution returns only an explicitly registered spec and **never
    silently falls back**: an unknown id resolves to ``None`` so the broker can fail
    closed with :data:`CODE_UNKNOWN_TOOL`.  Holding only inert specs / callables, the
    registry performs no I/O of its own.
    """

    def __init__(self, specs: Iterable[ToolSpec] | None = None) -> None:
        self._by_id: dict[str, ToolSpec] = {}
        for spec in specs or ():
            self.register(spec)

    def register(self, spec: Any) -> ToolSpec:
        """Register ``spec``; fail closed (raise) on a malformed or duplicate entry."""
        if not isinstance(spec, ToolSpec):
            raise ToolBrokerError(CODE_MALFORMED_HANDLER, "spec must be a ToolSpec")
        if not _is_bounded_token(spec.tool_id, MAX_TOOL_ID_LENGTH):
            raise ToolBrokerError(CODE_MALFORMED_TOOL_ID, "tool_id must be a non-blank, bounded, single-line printable-ASCII identifier")
        if not isinstance(spec.versions, tuple) or not spec.versions or len(spec.versions) > MAX_TOOL_VERSIONS:
            raise ToolBrokerError(CODE_MALFORMED_TOOL_VERSIONS, "versions must be a non-empty, bounded tuple")
        if any(not _is_bounded_token(version, MAX_TOOL_VERSION_LENGTH) for version in spec.versions) or len(set(spec.versions)) != len(spec.versions):
            raise ToolBrokerError(CODE_MALFORMED_TOOL_VERSIONS, "each version must be a unique, non-blank, bounded, printable-ASCII token")
        if spec.allowed_callers is not None:
            callers = spec.allowed_callers
            if (
                not isinstance(callers, tuple)
                or len(callers) > MAX_ALLOWED_CALLERS
                or any(not _is_bounded_token(caller, MAX_CALLER_ID_LENGTH) for caller in callers)
            ):
                raise ToolBrokerError(CODE_MALFORMED_ALLOWED_CALLERS, "allowed_callers must be None or a bounded tuple of caller ids")
        if not callable(spec.handler):
            raise ToolBrokerError(CODE_MALFORMED_HANDLER, f"handler for {spec.tool_id!r} must be callable")
        if not isinstance(spec.enabled, bool):
            raise ToolBrokerError(CODE_MALFORMED_HANDLER, "enabled must be a bool")
        if spec.tool_id in self._by_id:
            raise ToolBrokerError(CODE_DUPLICATE_TOOL, f"tool id {spec.tool_id!r} is already registered")
        self._by_id[spec.tool_id] = spec
        return spec

    def resolve(self, tool_id: Any) -> ToolSpec | None:
        """Return the registered spec for ``tool_id`` or ``None`` (the broker fails closed)."""
        return self._by_id.get(tool_id) if isinstance(tool_id, str) else None

    def contains(self, tool_id: Any) -> bool:
        """True iff ``tool_id`` is registered (a total, side-effect-free check)."""
        return isinstance(tool_id, str) and tool_id in self._by_id

    def tool_ids(self) -> tuple[str, ...]:
        """Return the registered tool ids in first-registration order."""
        return tuple(self._by_id)

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, tool_id: object) -> bool:
        return isinstance(tool_id, str) and tool_id in self._by_id


# --- Request & decision shapes -----------------------------------------------


@dataclass(frozen=True)
class ToolCallRequest:
    """An inert request to mediate one tool call against the allowlist.

    Fields:

    - ``tool_id`` — the requested tool identity;
    - ``version`` — the exact version requested (required; an absent / mismatched
      version is denied);
    - ``arguments`` — the bounded argument mapping (``name -> value``);
    - ``caller_id`` — the optional caller identity (required only for a caller-gated
      tool);
    - ``project_ref`` — an optional project / policy context reference echoed back on
      the decision for traceability.

    The request is inert data; the broker validates every field fail-closed at mediation
    time (an instance with malformed fields is permitted so a caller can prove the broker
    rejects it), and it is never mutated.
    """

    tool_id: Any
    version: Any = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    caller_id: Any = None
    project_ref: Any = None


@dataclass(frozen=True)
class ToolMediationDecision:
    """The inert result of a mediation: an authorized bounded result, or a deny reason.

    Fields:

    - ``status`` — one of :data:`STATUSES`;
    - ``reason_code`` — ``None`` when allowed, else the bounded deny code
      (:data:`REASON_CODES`);
    - ``tool_id`` / ``version`` — the requested identity (``None`` when it was too
      malformed to echo);
    - ``caller_id`` / ``project_ref`` — the request's caller / project context, echoed
      for traceability (``None`` when absent / malformed);
    - ``result`` — the bounded, redacted, inert handler result on an ``allowed``
      decision, else ``None``.  A ``denied`` decision never carries a result.

    The value is inert data returned to the caller; only the redacted result of an
    authorized call appears.  It is never written to project state, events, artifacts,
    domain tables, or full-content logs.
    """

    status: str
    reason_code: str | None
    tool_id: str | None
    version: str | None
    caller_id: str | None = None
    project_ref: str | None = None
    result: Any | None = None

    @property
    def allowed(self) -> bool:
        """True iff the call was authorized and produced an inert result."""
        return self.status == STATUS_ALLOWED

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "tool_id": self.tool_id,
            "version": self.version,
            "caller_id": self.caller_id,
            "project_ref": self.project_ref,
            "allowed": self.allowed,
            "result": self.result,
        }


class ToolBroker:
    """Mediates inert tool-call requests against an explicit allowlist, fail-closed.

    The broker holds a :class:`ToolRegistry` and exposes a single :meth:`mediate`
    method.  An authorized call (known, enabled, version- and caller-matched, with
    bounded, serializable, non-sensitive arguments) runs the registered handler and
    returns an ``allowed`` decision carrying a bounded, redacted result; everything else
    returns a fail-closed ``denied`` decision carrying only a bounded reason code.  The
    handler is reached **only** after every allowlist and argument check has passed, so
    an unauthorized request can never fall back to an allowed handler.
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry if registry is not None else ToolRegistry()

    @property
    def registry(self) -> ToolRegistry:
        """The allowlist this broker mediates against."""
        return self._registry

    def mediate(self, request: Any) -> ToolMediationDecision:
        """Evaluate ``request`` against the allowlist and return an inert decision.

        Resolves the request fail-closed in order: request shape, identity, allowlist
        membership, enabled state, exact version, caller policy, then bounded /
        serializable / non-sensitive arguments.  Only when every check passes does it
        run the registered handler (catching any exception) and validate / redact the
        result.  Writes nothing and mutates neither the request nor the registry.
        """
        if not isinstance(request, ToolCallRequest):
            return _denied(CODE_MALFORMED_REQUEST)

        # --- identity ---------------------------------------------------------
        if not _is_bounded_token(request.tool_id, MAX_TOOL_ID_LENGTH):
            return _denied(CODE_MALFORMED_IDENTITY)
        tool_id = request.tool_id
        if not _is_bounded_token(request.version, MAX_TOOL_VERSION_LENGTH):
            return _denied(CODE_MALFORMED_IDENTITY, tool_id=tool_id)
        version = request.version

        # --- caller / project context (optional, but bounded if present) ------
        if request.caller_id is not None and not _is_bounded_token(request.caller_id, MAX_CALLER_ID_LENGTH):
            return _denied(CODE_MALFORMED_REQUEST, tool_id=tool_id, version=version)
        caller_id = request.caller_id if isinstance(request.caller_id, str) else None
        if request.project_ref is not None and not _is_bounded_token(request.project_ref, MAX_PROJECT_REF_LENGTH):
            return _denied(CODE_MALFORMED_REQUEST, tool_id=tool_id, version=version, caller_id=caller_id)
        project_ref = request.project_ref if isinstance(request.project_ref, str) else None

        echo = {"tool_id": tool_id, "version": version, "caller_id": caller_id, "project_ref": project_ref}

        # --- allowlist resolution (fail closed, no fallback) ------------------
        spec = self._registry.resolve(tool_id)
        if spec is None:
            return _denied(CODE_UNKNOWN_TOOL, **echo)
        if not spec.enabled:
            return _denied(CODE_TOOL_DISABLED, **echo)
        if not spec.admits_version(version):
            return _denied(CODE_VERSION_MISMATCH, **echo)
        if not spec.admits_caller(caller_id):
            return _denied(CODE_CALLER_NOT_ALLOWED, **echo)

        # --- arguments: bounded, serializable, non-sensitive ------------------
        sanitized, arg_error = _sanitize_arguments(request.arguments)
        if arg_error is not None:
            return _denied(arg_error, **echo)

        # --- authorized execution (the ONLY place a handler runs) -------------
        try:
            raw_result = spec.handler(sanitized)
        except Exception:  # noqa: BLE001 - any handler fault must fail closed
            return _denied(CODE_HANDLER_ERROR, **echo)

        try:
            plain_result = _to_plain(raw_result)
        except _InertPayloadError:
            return _denied(CODE_MALFORMED_RESULT, **echo)
        if _payload_bytes(plain_result) > MAX_RESULT_BYTES:
            return _denied(CODE_RESULT_TOO_LARGE, **echo)

        return ToolMediationDecision(
            status=STATUS_ALLOWED,
            reason_code=None,
            result=redact(plain_result),
            **echo,
        )


def _sanitize_arguments(arguments: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(sanitized, None)`` for bounded, non-sensitive arguments, else ``(None, code)``.

    Rejects a non-mapping (:data:`CODE_MALFORMED_ARGUMENTS`), too many arguments
    (:data:`CODE_TOO_MANY_ARGUMENTS`), a malformed argument name
    (:data:`CODE_MALFORMED_ARGUMENTS`), any argument the WP-05e contract classifies as
    ``sensitive`` (:data:`CODE_SENSITIVE_ARGUMENT` — blocked *before* normalization so no
    raw sensitive value is ever touched further), a non-serializable / over-deep / non-
    finite value (:data:`CODE_NONSERIALIZABLE_ARGUMENTS` / :data:`CODE_MALFORMED_ARGUMENTS`),
    and an oversized payload (:data:`CODE_ARGUMENTS_TOO_LARGE`).  On success the admitted
    arguments are normalized to a plain dict and **redacted** of inline secrets so the
    handler never sees a raw credential-like value.
    """
    if not isinstance(arguments, Mapping):
        return None, CODE_MALFORMED_ARGUMENTS
    if len(arguments) > MAX_TOOL_ARGUMENTS:
        return None, CODE_TOO_MANY_ARGUMENTS

    for name, value in arguments.items():
        if not _is_bounded_token(name, MAX_ARG_NAME_LENGTH):
            return None, CODE_MALFORMED_ARGUMENTS
        # Block raw sensitive content before any further handling (fail closed).
        if classify_field_sensitivity(name, value) == SENSITIVITY_SENSITIVE:
            return None, CODE_SENSITIVE_ARGUMENT

    try:
        plain = _to_plain(dict(arguments))
    except _InertPayloadError as exc:
        return None, CODE_NONSERIALIZABLE_ARGUMENTS if exc.kind == _PAYLOAD_NONSERIALIZABLE else CODE_MALFORMED_ARGUMENTS
    if _payload_bytes(plain) > MAX_ARGUMENTS_BYTES:
        return None, CODE_ARGUMENTS_TOO_LARGE

    # Defensively redact inline secrets from admitted values before the handler runs.
    return redact(plain), None


def _denied(
    reason_code: str,
    *,
    tool_id: str | None = None,
    version: str | None = None,
    caller_id: str | None = None,
    project_ref: str | None = None,
) -> ToolMediationDecision:
    """Build a fail-closed ``denied`` decision that carries no result."""
    return ToolMediationDecision(
        status=STATUS_DENIED,
        reason_code=reason_code,
        tool_id=tool_id,
        version=version,
        caller_id=caller_id,
        project_ref=project_ref,
        result=None,
    )


__all__ = [
    "MAX_TOOL_ID_LENGTH",
    "MAX_TOOL_VERSION_LENGTH",
    "MAX_CALLER_ID_LENGTH",
    "MAX_PROJECT_REF_LENGTH",
    "MAX_TOOL_VERSIONS",
    "MAX_ALLOWED_CALLERS",
    "MAX_TOOL_ARGUMENTS",
    "MAX_ARG_NAME_LENGTH",
    "MAX_PAYLOAD_DEPTH",
    "MAX_ARGUMENTS_BYTES",
    "MAX_RESULT_BYTES",
    "STATUS_ALLOWED",
    "STATUS_DENIED",
    "STATUSES",
    "CODE_MALFORMED_REQUEST",
    "CODE_MALFORMED_IDENTITY",
    "CODE_MALFORMED_ARGUMENTS",
    "CODE_TOO_MANY_ARGUMENTS",
    "CODE_ARGUMENTS_TOO_LARGE",
    "CODE_NONSERIALIZABLE_ARGUMENTS",
    "CODE_SENSITIVE_ARGUMENT",
    "CODE_UNKNOWN_TOOL",
    "CODE_TOOL_DISABLED",
    "CODE_VERSION_MISMATCH",
    "CODE_CALLER_NOT_ALLOWED",
    "CODE_HANDLER_ERROR",
    "CODE_MALFORMED_RESULT",
    "CODE_RESULT_TOO_LARGE",
    "REQUEST_CODES",
    "ALLOWLIST_CODES",
    "EXECUTION_CODES",
    "REASON_CODES",
    "CODE_MALFORMED_TOOL_ID",
    "CODE_MALFORMED_TOOL_VERSIONS",
    "CODE_MALFORMED_ALLOWED_CALLERS",
    "CODE_MALFORMED_HANDLER",
    "CODE_DUPLICATE_TOOL",
    "REGISTRY_CODES",
    "ToolBrokerError",
    "ToolHandler",
    "ToolSpec",
    "ToolRegistry",
    "ToolCallRequest",
    "ToolMediationDecision",
    "ToolBroker",
]
