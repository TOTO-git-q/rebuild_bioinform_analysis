"""Command API idempotency and optimistic-concurrency contract (WP-04g / T-04-07).

The smallest deterministic, *local* contract layer the control plane needs so a
future HTTP adapter can answer two questions about a mutating command request
without ever applying it twice or clobbering a concurrent update:

1. *Idempotency* — was this exact command already accepted under this key?  A
   mutating command must carry a non-blank idempotency key; the same key with the
   *same* command/payload is a replay (the prior outcome should be returned, the
   command not re-applied), while the same key with a *different* command/payload
   is a conflict that fails closed.
2. *Optimistic concurrency* — does the caller's expected resource version still
   match the authoritative current version?  A stale or malformed expected
   version fails closed rather than overwriting a version the caller never saw.

Design constraints (WP-04g), mirroring the WP-04e/WP-04f control-plane style:

- **Pure and deterministic.** Every function here is a total function of its
  explicit in-memory inputs.  There is no I/O whatsoever: no file access, no
  network, no environment inspection, no real clock, no threads, async worker,
  DB, outbox, broker, queue, or command execution side effect.  The same input
  always yields the same result, and inputs are never mutated in place.
- **Fail closed.** Every uncertainty resolves to a *non-accepting* result.  A
  missing/blank/malformed/overlong idempotency key, a duplicated or malformed
  controlled header, a same-key payload conflict, and a stale or malformed
  expected version all yield a bounded error result, never silent acceptance.
- **Bounded vocabulary.** The result status is one of exactly five values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  A future HTTP adapter maps these categories to status
  codes; callers branch on the machine-readable code, never the human message.
- **Exact binding.** Every result records the exact command identity, idempotency
  key, canonical payload fingerprint, and the expected/current versions it
  considered, so the decision can be audited later.

This module defines a request/header *contract* only.  It does not open a socket,
register a route, run a real HTTP server, persist a key, execute a command, or
expose any CLI/OpenAPI surface — the prior-record lookup and any persistence are
the caller's responsibility; this layer only decides, purely, from the facts it
is handed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.ids import hash_payload

# --- Bounded controlled header names ----------------------------------------
# HTTP header names are case-insensitive, so every comparison is done against the
# lowercased form; these constants are the canonical (display) spellings.
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
EXPECTED_VERSION_HEADER = "If-Match-Version"

_IDEMPOTENCY_KEY_HEADER_LC = IDEMPOTENCY_KEY_HEADER.lower()
_EXPECTED_VERSION_HEADER_LC = EXPECTED_VERSION_HEADER.lower()
CONTROLLED_HEADERS = (IDEMPOTENCY_KEY_HEADER, EXPECTED_VERSION_HEADER)

# Bounds on an idempotency key: a non-blank, single-line token of visible ASCII
# (no spaces or control characters), capped so an unbounded key cannot be used to
# exhaust a downstream store.
MAX_IDEMPOTENCY_KEY_LENGTH = 200
# A version is a positive integer; cap its digit count so a pathologically long
# numeric string is rejected as malformed rather than parsed.
MAX_VERSION_DIGITS = 18

# --- Bounded status vocabulary ----------------------------------------------
STATUS_OK = "ok"
STATUS_DUPLICATE = "duplicate"
STATUS_IDEMPOTENCY_CONFLICT = "idempotency_conflict"
STATUS_VERSION_CONFLICT = "version_conflict"
STATUS_INVALID = "invalid"

STATUSES = (
    STATUS_OK,
    STATUS_DUPLICATE,
    STATUS_IDEMPOTENCY_CONFLICT,
    STATUS_VERSION_CONFLICT,
    STATUS_INVALID,
)

# --- Stable reason codes ----------------------------------------------------
# Callers branch on these, so they must stay stable.
# ok:
CODE_ACCEPTED = "COMMAND_ACCEPTED"
# duplicate:
CODE_IDEMPOTENT_REPLAY = "COMMAND_IDEMPOTENT_REPLAY"
# idempotency_conflict:
CODE_IDEMPOTENCY_CONFLICT = "COMMAND_IDEMPOTENCY_CONFLICT"
# version_conflict:
CODE_STALE_VERSION = "COMMAND_STALE_VERSION"
# invalid (fail closed):
CODE_MALFORMED_COMMAND = "COMMAND_MALFORMED_COMMAND"
CODE_MALFORMED_HEADERS = "COMMAND_MALFORMED_HEADERS"
CODE_DUPLICATE_HEADER = "COMMAND_DUPLICATE_HEADER"
CODE_MISSING_IDEMPOTENCY_KEY = "COMMAND_MISSING_IDEMPOTENCY_KEY"
CODE_MALFORMED_IDEMPOTENCY_KEY = "COMMAND_MALFORMED_IDEMPOTENCY_KEY"
CODE_IDEMPOTENCY_KEY_TOO_LONG = "COMMAND_IDEMPOTENCY_KEY_TOO_LONG"
CODE_MISSING_EXPECTED_VERSION = "COMMAND_MISSING_EXPECTED_VERSION"
CODE_MALFORMED_EXPECTED_VERSION = "COMMAND_MALFORMED_EXPECTED_VERSION"
CODE_MALFORMED_CURRENT_VERSION = "COMMAND_MALFORMED_CURRENT_VERSION"
CODE_PRIOR_RECORD_MISMATCH = "COMMAND_PRIOR_RECORD_MISMATCH"

REASON_CODES = (
    CODE_ACCEPTED,
    CODE_IDEMPOTENT_REPLAY,
    CODE_IDEMPOTENCY_CONFLICT,
    CODE_STALE_VERSION,
    CODE_MALFORMED_COMMAND,
    CODE_MALFORMED_HEADERS,
    CODE_DUPLICATE_HEADER,
    CODE_MISSING_IDEMPOTENCY_KEY,
    CODE_MALFORMED_IDEMPOTENCY_KEY,
    CODE_IDEMPOTENCY_KEY_TOO_LONG,
    CODE_MISSING_EXPECTED_VERSION,
    CODE_MALFORMED_EXPECTED_VERSION,
    CODE_MALFORMED_CURRENT_VERSION,
    CODE_PRIOR_RECORD_MISMATCH,
)

# The status each reason code resolves to, so a future adapter can map a category
# to a transport status without re-deriving it from the code.
_CODE_STATUS = {
    CODE_ACCEPTED: STATUS_OK,
    CODE_IDEMPOTENT_REPLAY: STATUS_DUPLICATE,
    CODE_IDEMPOTENCY_CONFLICT: STATUS_IDEMPOTENCY_CONFLICT,
    CODE_STALE_VERSION: STATUS_VERSION_CONFLICT,
    CODE_MALFORMED_COMMAND: STATUS_INVALID,
    CODE_MALFORMED_HEADERS: STATUS_INVALID,
    CODE_DUPLICATE_HEADER: STATUS_INVALID,
    CODE_MISSING_IDEMPOTENCY_KEY: STATUS_INVALID,
    CODE_MALFORMED_IDEMPOTENCY_KEY: STATUS_INVALID,
    CODE_IDEMPOTENCY_KEY_TOO_LONG: STATUS_INVALID,
    CODE_MISSING_EXPECTED_VERSION: STATUS_INVALID,
    CODE_MALFORMED_EXPECTED_VERSION: STATUS_INVALID,
    CODE_MALFORMED_CURRENT_VERSION: STATUS_INVALID,
    CODE_PRIOR_RECORD_MISMATCH: STATUS_INVALID,
}


def _is_positive_int(value: Any) -> bool:
    """A real positive integer — ``bool`` is excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_visible_ascii_token(value: str) -> bool:
    """True iff every character is visible ASCII (no spaces/controls, 0x21–0x7e)."""
    return bool(value) and all("\x21" <= ch <= "\x7e" for ch in value)


@dataclass(frozen=True)
class ParsedHeaders:
    """The parsed, normalised controlled headers of a command request.

    ``idempotency_key`` is the OWS-trimmed raw value of the idempotency header (an
    empty string when the header is absent).  ``expected_version`` is the parsed
    positive integer of the expected-version header, or ``None`` when the header
    is absent.  ``error_code``/``message`` are populated (and ``ok`` is ``False``)
    when the raw headers were duplicated or malformed — a parse failure is itself
    a fail-closed condition, never a silently-dropped header.
    """

    idempotency_key: str = ""
    expected_version: int | None = None
    ok: bool = True
    error_code: str = ""
    message: str = ""


def _collect_controlled_headers(headers: Any) -> dict[str, list[str]] | None:
    """Flatten ``headers`` to ``{lowercased_name: [values...]}`` for the two
    controlled headers, or ``None`` if the container/entries are malformed.

    Accepts a mapping (values may be a string or a list/tuple of strings) or an
    iterable of ``(name, value)`` pairs — the realistic multi-valued HTTP form,
    where the same header can legitimately appear more than once.  Header names
    are compared case-insensitively, so two differently-cased spellings of the
    same controlled header collapse to one bucket and are detected as a
    duplicate.  Never mutates the input.
    """
    collected: dict[str, list[str]] = {_IDEMPOTENCY_KEY_HEADER_LC: [], _EXPECTED_VERSION_HEADER_LC: []}
    if headers is None:
        return collected
    if isinstance(headers, Mapping):
        items: list[tuple[Any, Any]] = list(headers.items())
    elif isinstance(headers, (str, bytes)):
        # A bare string is not a header collection; reject rather than iterate it
        # character by character.
        return None
    else:
        try:
            items = [tuple(pair) for pair in headers]  # type: ignore[misc]
        except (TypeError, ValueError):
            return None

    for pair in items:
        if not isinstance(pair, tuple) or len(pair) != 2:
            return None
        name, value = pair
        if not isinstance(name, str):
            return None
        key = name.strip().lower()
        if key not in collected:
            continue  # An unrelated header; this contract only governs its own.
        if isinstance(value, (list, tuple)):
            parts = list(value)
        else:
            parts = [value]
        for part in parts:
            if not isinstance(part, str):
                return None
            collected[key].append(part)
    return collected


def parse_command_headers(headers: Any) -> ParsedHeaders:
    """Parse the controlled idempotency/expected-version headers, fail-closed.

    A duplicated controlled header (the same header supplied more than once, in
    any casing) or a structurally malformed header container yields a
    non-``ok`` :class:`ParsedHeaders`.  A present-but-unparseable expected-version
    value also fails closed; an absent expected-version header is permitted (it is
    only *required* when optimistic concurrency is being enforced — see
    :func:`evaluate_command_request`).
    """
    collected = _collect_controlled_headers(headers)
    if collected is None:
        return ParsedHeaders(
            ok=False,
            error_code=CODE_MALFORMED_HEADERS,
            message="headers must be a mapping or an iterable of (name, value) string pairs",
        )

    # A controlled header appearing more than once is ambiguous; fail closed
    # rather than guessing which occurrence is authoritative.
    for name_lc, values in collected.items():
        if len(values) > 1:
            return ParsedHeaders(
                ok=False,
                error_code=CODE_DUPLICATE_HEADER,
                message=f"controlled header {name_lc!r} was supplied {len(values)} times; exactly one is allowed",
            )

    key_values = collected[_IDEMPOTENCY_KEY_HEADER_LC]
    idempotency_key = key_values[0].strip(" \t") if key_values else ""

    version_values = collected[_EXPECTED_VERSION_HEADER_LC]
    expected_version: int | None = None
    if version_values:
        parsed = _parse_version_token(version_values[0])
        if parsed is None:
            return ParsedHeaders(
                idempotency_key=idempotency_key,
                ok=False,
                error_code=CODE_MALFORMED_EXPECTED_VERSION,
                message=f"expected-version header {version_values[0]!r} is not a positive integer",
            )
        expected_version = parsed

    return ParsedHeaders(idempotency_key=idempotency_key, expected_version=expected_version)


def _parse_version_token(raw: str) -> int | None:
    """Parse an expected-version header token to a positive int, or ``None``.

    Accepts only an OWS-trimmed, base-10 positive integer with no sign, no
    leading zeros, and a bounded digit count.  Everything else (blank, negative,
    zero, float, leading ``+``, overlong) is malformed and returns ``None``."""
    token = raw.strip(" \t")
    if not token or len(token) > MAX_VERSION_DIGITS:
        return None
    if token[0] == "0" or not token.isascii() or not token.isdigit():
        return None
    return int(token)


def command_fingerprint(command_type: Any, payload: Any) -> str:
    """A stable content fingerprint over the command's *identity* and payload.

    Two requests are "the same logical command" iff this fingerprint matches:
    the canonicalised ``(command_type, payload)`` is hashed with the same
    deterministic, key-order-independent serialisation the rest of the core uses,
    so reordering payload keys never changes the fingerprint while changing the
    command type or any payload fact does."""
    return hash_payload({"command_type": command_type, "payload": payload})


@dataclass(frozen=True)
class CommandRequest:
    """A mutating command API request, as a pure in-memory contract value.

    ``command_type`` names the command (e.g. ``"create_project"``); ``payload``
    is its canonicalisable argument object.  ``headers`` carries the raw HTTP
    headers (mapping or ``(name, value)`` pairs) from which the idempotency key
    and optimistic-concurrency expected version are parsed.  This object holds no
    transport, connection, or execution state — it is the parsed *facts* a future
    adapter would hand to :func:`evaluate_command_request`.
    """

    command_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    headers: Any = None

    def fingerprint(self) -> str:
        return command_fingerprint(self.command_type, self.payload)


@dataclass(frozen=True)
class CommandRecord:
    """What a caller persists for an accepted command, keyed by idempotency key.

    It is exactly the two facts a later request needs to tell a replay from a
    conflict: the ``idempotency_key`` and the canonical ``command_fingerprint``.
    This layer never stores it; the caller looks it up by key and passes it back
    in as ``prior`` on the next request bearing the same key.
    """

    idempotency_key: str
    command_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {"idempotency_key": self.idempotency_key, "command_fingerprint": self.command_fingerprint}


@dataclass(frozen=True)
class CommandApiResult:
    """The deterministic, reason-coded outcome of a command API admission check.

    ``status`` is one of :data:`STATUSES`; ``reason_code`` is one of
    :data:`REASON_CODES`.  ``binding`` records the exact command identity, key,
    fingerprint, and versions considered so the decision can be audited.
    ``accepted`` is the single proceed-and-apply outcome; ``is_replay`` flags a
    recognised idempotent duplicate (the caller should return the prior result
    without re-applying).
    """

    status: str
    reason_code: str
    message: str
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.status == STATUS_OK

    @property
    def is_replay(self) -> bool:
        return self.status == STATUS_DUPLICATE

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the result (stable key order)."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "accepted": self.accepted,
            "is_replay": self.is_replay,
            "binding": dict(self.binding),
        }


def _binding(
    *,
    command_type: Any,
    fingerprint: str,
    idempotency_key: str,
    expected_version: int | None,
    current_version: int | None,
) -> dict[str, Any]:
    """Assemble the deterministic identity/version binding for a result."""
    return {
        "command_type": command_type,
        "command_fingerprint": fingerprint,
        "idempotency_key": idempotency_key,
        "expected_version": expected_version,
        "current_version": current_version,
    }


def _result(
    reason_code: str,
    message: str,
    *,
    command_type: Any,
    fingerprint: str,
    idempotency_key: str,
    expected_version: int | None,
    current_version: int | None,
) -> CommandApiResult:
    return CommandApiResult(
        status=_CODE_STATUS[reason_code],
        reason_code=reason_code,
        message=message,
        binding=_binding(
            command_type=command_type,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            current_version=current_version,
        ),
    )


def _validate_idempotency_key(key: str) -> tuple[str, str] | None:
    """Return ``(reason_code, message)`` if ``key`` is unusable, else ``None``."""
    if not key:
        return (CODE_MISSING_IDEMPOTENCY_KEY, "a mutating command requires a non-blank Idempotency-Key header")
    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        return (
            CODE_IDEMPOTENCY_KEY_TOO_LONG,
            f"idempotency key length {len(key)} exceeds the maximum of {MAX_IDEMPOTENCY_KEY_LENGTH}",
        )
    if not _is_visible_ascii_token(key):
        return (
            CODE_MALFORMED_IDEMPOTENCY_KEY,
            "idempotency key must be a single-line token of visible ASCII (no spaces or control characters)",
        )
    return None


def evaluate_command_request(
    request: CommandRequest,
    *,
    prior: CommandRecord | None = None,
    current_version: int | None = None,
) -> CommandApiResult:
    """Decide whether a mutating command request may be applied, fail-closed.

    A pure, deterministic function returning a bounded :class:`CommandApiResult`
    (it never raises for a domain condition).  Precedence:

    1. Validate the command identity (non-blank ``command_type``, dict payload,
       canonicalisable content) and parse the controlled headers; a malformed or
       non-canonicalisable command or a duplicated/malformed header → ``invalid``
       (a non-canonicalisable payload fails closed rather than raising).
    2. Require a well-formed, non-blank, non-overlong idempotency key →
       otherwise ``invalid``.
    3. Idempotency: if a ``prior`` record exists for this key, a matching
       fingerprint is a replay (``duplicate`` — return the prior result, do not
       re-apply) and a differing fingerprint is an ``idempotency_conflict``.  A
       replay short-circuits before the version check, since the same logical
       command was already admitted.
    4. Optimistic concurrency: only when ``current_version`` is supplied, the
       expected-version header is required and must equal it; a missing/stale
       expected version → ``invalid``/``version_conflict``.
    5. Otherwise → ``ok`` (accepted; the caller may apply and then persist a
       :class:`CommandRecord`).
    """
    command_type = request.command_type

    # 1a. Command identity must be a non-blank type with a dict payload.  These
    #     are checked *before* fingerprinting: the fingerprint hashes the payload,
    #     so an invalid command/payload must fail closed with a bounded result
    #     rather than raising out of serialisation.  Malformed-command results
    #     bind an empty fingerprint, since hashing invalid content is exactly what
    #     must be avoided.
    if not (isinstance(command_type, str) and command_type.strip()):
        return _result(
            CODE_MALFORMED_COMMAND,
            "command_type must be a non-blank string",
            command_type=command_type,
            fingerprint="",
            idempotency_key="",
            expected_version=None,
            current_version=current_version,
        )
    if not isinstance(request.payload, dict):
        return _result(
            CODE_MALFORMED_COMMAND,
            "payload must be a (canonicalisable) object",
            command_type=command_type,
            fingerprint="",
            idempotency_key="",
            expected_version=None,
            current_version=current_version,
        )

    # 1b. Canonicalise/fingerprint the command.  A payload that cannot be
    #     canonicalised — e.g. a non-JSON-serialisable nested value or
    #     non-comparable dict keys — is a malformed command, not an exception;
    #     fail closed instead of letting serialisation raise.
    try:
        fingerprint = request.fingerprint()
    except (TypeError, ValueError) as exc:
        return _result(
            CODE_MALFORMED_COMMAND,
            f"payload is not canonicalisable: {exc}",
            command_type=command_type,
            fingerprint="",
            idempotency_key="",
            expected_version=None,
            current_version=current_version,
        )

    # 1b. Parse the controlled headers (duplicate/malformed → fail closed).
    parsed = parse_command_headers(request.headers)
    if not parsed.ok:
        return _result(
            parsed.error_code,
            parsed.message,
            command_type=command_type,
            fingerprint=fingerprint,
            idempotency_key=parsed.idempotency_key,
            expected_version=parsed.expected_version,
            current_version=current_version,
        )

    key = parsed.idempotency_key
    expected_version = parsed.expected_version

    # 2. A mutating command must carry a usable idempotency key.
    key_error = _validate_idempotency_key(key)
    if key_error is not None:
        code, message = key_error
        return _result(
            code,
            message,
            command_type=command_type,
            fingerprint=fingerprint,
            idempotency_key=key,
            expected_version=expected_version,
            current_version=current_version,
        )

    # 3. Idempotency: a prior record under this exact key decides replay vs.
    #    conflict.  A prior record handed in under a *different* key is a caller
    #    inconsistency and fails closed rather than being trusted.
    if prior is not None:
        if prior.idempotency_key != key:
            return _result(
                CODE_PRIOR_RECORD_MISMATCH,
                f"prior record is keyed {prior.idempotency_key!r}, not the request key {key!r}",
                command_type=command_type,
                fingerprint=fingerprint,
                idempotency_key=key,
                expected_version=expected_version,
                current_version=current_version,
            )
        if prior.command_fingerprint == fingerprint:
            return _result(
                CODE_IDEMPOTENT_REPLAY,
                "same idempotency key and identical command/payload; this is a replay (return the prior result, do not re-apply)",
                command_type=command_type,
                fingerprint=fingerprint,
                idempotency_key=key,
                expected_version=expected_version,
                current_version=current_version,
            )
        return _result(
            CODE_IDEMPOTENCY_CONFLICT,
            "idempotency key was reused with a different command or payload; refusing to apply (fail closed)",
            command_type=command_type,
            fingerprint=fingerprint,
            idempotency_key=key,
            expected_version=expected_version,
            current_version=current_version,
        )

    # 4. Optimistic concurrency, enforced only when the caller supplies the
    #    authoritative current version of the target resource.
    if current_version is not None:
        if not _is_positive_int(current_version):
            return _result(
                CODE_MALFORMED_CURRENT_VERSION,
                "current_version, when supplied, must be a positive integer",
                command_type=command_type,
                fingerprint=fingerprint,
                idempotency_key=key,
                expected_version=expected_version,
                current_version=current_version,
            )
        if expected_version is None:
            return _result(
                CODE_MISSING_EXPECTED_VERSION,
                f"this command requires an {EXPECTED_VERSION_HEADER} header for optimistic concurrency",
                command_type=command_type,
                fingerprint=fingerprint,
                idempotency_key=key,
                expected_version=expected_version,
                current_version=current_version,
            )
        if expected_version != current_version:
            return _result(
                CODE_STALE_VERSION,
                f"expected version {expected_version} does not match the current version {current_version}; the resource changed (fail closed)",
                command_type=command_type,
                fingerprint=fingerprint,
                idempotency_key=key,
                expected_version=expected_version,
                current_version=current_version,
            )

    # 5. Admitted: a fresh, well-formed command at the expected version.
    return _result(
        CODE_ACCEPTED,
        "command admitted; apply it and persist a CommandRecord under this idempotency key",
        command_type=command_type,
        fingerprint=fingerprint,
        idempotency_key=key,
        expected_version=expected_version,
        current_version=current_version,
    )


def record_for(request: CommandRequest, idempotency_key: str) -> CommandRecord:
    """Build the :class:`CommandRecord` a caller should persist after accepting
    ``request`` under ``idempotency_key`` (a pure convenience; stores nothing)."""
    return CommandRecord(idempotency_key=idempotency_key, command_fingerprint=request.fingerprint())


__all__ = [
    "IDEMPOTENCY_KEY_HEADER",
    "EXPECTED_VERSION_HEADER",
    "CONTROLLED_HEADERS",
    "MAX_IDEMPOTENCY_KEY_LENGTH",
    "MAX_VERSION_DIGITS",
    "STATUSES",
    "STATUS_OK",
    "STATUS_DUPLICATE",
    "STATUS_IDEMPOTENCY_CONFLICT",
    "STATUS_VERSION_CONFLICT",
    "STATUS_INVALID",
    "REASON_CODES",
    "CODE_ACCEPTED",
    "CODE_IDEMPOTENT_REPLAY",
    "CODE_IDEMPOTENCY_CONFLICT",
    "CODE_STALE_VERSION",
    "CODE_MALFORMED_COMMAND",
    "CODE_MALFORMED_HEADERS",
    "CODE_DUPLICATE_HEADER",
    "CODE_MISSING_IDEMPOTENCY_KEY",
    "CODE_MALFORMED_IDEMPOTENCY_KEY",
    "CODE_IDEMPOTENCY_KEY_TOO_LONG",
    "CODE_MISSING_EXPECTED_VERSION",
    "CODE_MALFORMED_EXPECTED_VERSION",
    "CODE_MALFORMED_CURRENT_VERSION",
    "CODE_PRIOR_RECORD_MISMATCH",
    "ParsedHeaders",
    "CommandRequest",
    "CommandRecord",
    "CommandApiResult",
    "command_fingerprint",
    "parse_command_headers",
    "evaluate_command_request",
    "record_for",
]
