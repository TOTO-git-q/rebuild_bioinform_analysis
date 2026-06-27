"""Local prompt registry contract foundation (WP-05b / T-05-02).

The smallest *local* contract layer the future agent gateway (WP-05) needs so the
rest of the system can resolve a prompt only by **stable identity (prompt id +
exact version)** and confirm it against a **deterministic template hash** and a
**target schema reference**, **without ever rendering a prompt for egress, opening
a socket, importing a provider SDK, reading a credential, reaching the network, or
calling any external service**.

This is the foundation slice only.  It defines:

- a deterministic, serializable :class:`RegisteredPrompt` value shape — prompt id,
  version, template text, target schema reference, plus a derived canonical
  template hash and ``to_dict`` projection;
- bounded, fail-closed validators + a bounded :class:`PromptRegistryError` so a
  malformed id / version / empty template / missing-or-malformed target schema /
  hash mismatch fails closed with a stable reason code rather than silently
  entering domain state;
- an in-memory :class:`PromptRegistry` that registers and resolves prompts only by
  explicit prompt id + exact version and **never silently falls back** to
  unregistered content, rejecting duplicate registrations and unknown lookups.

Design constraints (WP-05b), mirroring the WP-05a / WP-04 contract style:

- **Pure, deterministic, offline.**  No I/O whatsoever: no network, socket, HTTP
  client, provider SDK, environment/credential access, real clock, threads, or
  file/DB/queue side effect.  A registry result is a total function of its explicit
  in-memory registrations.
- **Stable identity.**  A prompt is addressed by an opaque, bounded ``prompt_id``
  and an exact ``version``; the registry resolves only an explicitly registered
  ``(prompt_id, version)`` pair.
- **Fail closed.**  Every uncertainty resolves to a bounded, reason-coded error
  (:data:`REASON_CODES`).  A malformed id/version, empty/oversized template,
  missing/malformed target schema reference, hash mismatch, duplicate registration,
  or unknown prompt/version lookup raises :class:`PromptRegistryError` or surfaces
  via :func:`validate_prompt` — never a silent acceptance or fallback.
- **Data only.**  Registration and resolution return *data* to the caller.  They
  call no LLM/provider, render no content for egress, write no project state,
  event, artifact, ordinary domain table, or full-content log.  A
  :class:`RegisteredPrompt` is an inert value, never a side effect.

Out of scope for T-05-02 (and deliberately *not* implemented here): any real
provider/HTTP/SDK integration or content egress, structured-output parsing /
schema-repair / gateway admission (T-05-03), the domain semantic validator hook
(T-05-04), the sensitive content classifier / egress policy (T-05-05), the tool
broker (T-05-06), and any audit-record / budget / rate-limit / approval-workflow /
rollback machinery (T-05-07..12).  Template *rendering* (variable substitution)
and any prompt content egress are likewise out of scope.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from auto_bioinfo.core.ids import hash_payload

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated.
MAX_PROMPT_ID_LENGTH = 200
MAX_VERSION_LENGTH = 64
MAX_TEMPLATE_LENGTH = 200_000
MAX_TARGET_SCHEMA_ID_LENGTH = 200

# --- Identity grammars -------------------------------------------------------
# A prompt id is a lowercase, dotted/dashed/underscored slug so identity is stable
# and order-independent; a version is a slightly looser bounded token (so common
# schemes like ``1``, ``1.0.0``, ``v2``, ``2026-06-27`` all parse); a target schema
# reference additionally allows ``/`` so a namespaced schema id like
# ``report.summary/v1`` parses.  Anything outside the grammar fails closed.
_PROMPT_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$")
_TARGET_SCHEMA_RE = re.compile(r"^[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*$")

# --- Stable reason codes -----------------------------------------------------
# Callers / a future gateway branch on these machine-readable codes, never the
# human message, so they must stay stable.
CODE_MALFORMED_PROMPT_ID = "PROMPT_MALFORMED_ID"
CODE_MALFORMED_VERSION = "PROMPT_MALFORMED_VERSION"
CODE_EMPTY_TEMPLATE = "PROMPT_EMPTY_TEMPLATE"
CODE_TEMPLATE_TOO_LONG = "PROMPT_TEMPLATE_TOO_LONG"
CODE_MALFORMED_TARGET_SCHEMA = "PROMPT_MALFORMED_TARGET_SCHEMA"
CODE_MALFORMED_RECORD = "PROMPT_MALFORMED_RECORD"
CODE_HASH_MISMATCH = "PROMPT_HASH_MISMATCH"
CODE_DUPLICATE_REGISTRATION = "PROMPT_DUPLICATE_REGISTRATION"
CODE_UNKNOWN_PROMPT = "PROMPT_UNKNOWN_PROMPT"
CODE_UNKNOWN_VERSION = "PROMPT_UNKNOWN_VERSION"

# Problems an individual record can have (shape/grammar/bounds).
RECORD_CODES = (
    CODE_MALFORMED_RECORD,
    CODE_MALFORMED_PROMPT_ID,
    CODE_MALFORMED_VERSION,
    CODE_EMPTY_TEMPLATE,
    CODE_TEMPLATE_TOO_LONG,
    CODE_MALFORMED_TARGET_SCHEMA,
)

# Problems registration / resolution against a registry can raise.
REGISTRY_CODES = (
    CODE_HASH_MISMATCH,
    CODE_DUPLICATE_REGISTRATION,
    CODE_UNKNOWN_PROMPT,
    CODE_UNKNOWN_VERSION,
)

REASON_CODES = RECORD_CODES + REGISTRY_CODES


class PromptRegistryError(Exception):
    """A bounded, reason-coded prompt-registry failure.

    ``code`` is one of :data:`REASON_CODES`; ``message`` is a human-readable
    explanation a caller may surface but should never branch on (branch on
    ``code``).  This is the fail-closed signal a malformed record, a hash mismatch,
    a duplicate registration, or an unknown lookup produces — it carries no I/O,
    transport, or provider state.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# --- Small, pure predicate ---------------------------------------------------


def _is_bounded_match(value: Any, pattern: re.Pattern[str], max_length: int) -> bool:
    """True iff ``value`` is a non-blank string within ``max_length`` matching ``pattern``."""
    return isinstance(value, str) and 0 < len(value) <= max_length and pattern.match(value) is not None


# --- The registered-prompt value shape ---------------------------------------


@dataclass(frozen=True)
class RegisteredPrompt:
    """One registered prompt version, as a pure in-memory contract value.

    Fields:

    - ``prompt_id`` — an opaque, bounded, stable prompt identifier (slug grammar);
    - ``version`` — the exact bounded version token this record represents;
    - ``template`` — the prompt template *text*, stored inert (never rendered or
      sent anywhere by this contract);
    - ``target_schema`` — a bounded reference/identifier naming the structured-output
      schema a future gateway must hold the model response to.

    The value is inert data; constructing it performs no I/O.  ``template_hash`` is a
    deterministic content hash derived from the template, so a caller can bind a
    resolved prompt to an exact template body (a forged or drifted template fails
    closed at :meth:`PromptRegistry.resolve` when an ``expected_hash`` is supplied).
    """

    prompt_id: str
    version: str
    template: str
    target_schema: str

    @property
    def key(self) -> tuple[str, str]:
        """The stable ``(prompt_id, version)`` identity this record is addressed by."""
        return (self.prompt_id, self.version)

    @property
    def reference(self) -> str:
        """A human-readable ``prompt_id@version`` reference (for messages, not parsing)."""
        return f"{self.prompt_id}@{self.version}"

    @property
    def template_hash(self) -> str:
        """A deterministic, canonical content hash over the template text.

        Reuses the core canonical-hash facility so two records with the same template
        share a hash regardless of how they were constructed; a single character
        difference yields a different hash.
        """
        return hash_payload({"template": self.template})

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the record (stable key order).

        Includes the derived ``template_hash`` so a validator-friendly test (or a
        future gateway) can confirm the identity-to-template binding from the dict
        alone.
        """
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "template": self.template,
            "target_schema": self.target_schema,
            "template_hash": self.template_hash,
        }


def validate_prompt(prompt: Any) -> list[tuple[str, str]]:
    """Return a list of ``(code, message)`` problems with ``prompt`` (empty == valid).

    Validates only the record's own shape/grammar/bounds — it performs no registry
    lookup and no hash comparison (those are :class:`PromptRegistry` concerns).
    """
    if not isinstance(prompt, RegisteredPrompt):
        return [(CODE_MALFORMED_RECORD, "prompt must be a RegisteredPrompt")]
    errors: list[tuple[str, str]] = []

    if not _is_bounded_match(prompt.prompt_id, _PROMPT_ID_RE, MAX_PROMPT_ID_LENGTH):
        errors.append((CODE_MALFORMED_PROMPT_ID, "prompt_id must be a bounded lowercase slug (e.g. 'report.summary')"))

    if not _is_bounded_match(prompt.version, _VERSION_RE, MAX_VERSION_LENGTH):
        errors.append((CODE_MALFORMED_VERSION, "version must be a bounded token (e.g. '1', '1.0.0', 'v2')"))

    if not isinstance(prompt.template, str) or not prompt.template.strip():
        errors.append((CODE_EMPTY_TEMPLATE, "template must be a non-empty, non-whitespace string"))
    elif len(prompt.template) > MAX_TEMPLATE_LENGTH:
        errors.append((CODE_TEMPLATE_TOO_LONG, f"template length {len(prompt.template)} exceeds the maximum of {MAX_TEMPLATE_LENGTH}"))

    if not _is_bounded_match(prompt.target_schema, _TARGET_SCHEMA_RE, MAX_TARGET_SCHEMA_ID_LENGTH):
        errors.append((CODE_MALFORMED_TARGET_SCHEMA, "target_schema must be a bounded schema reference (e.g. 'report.summary/v1')"))

    return errors


def ensure_valid_prompt(prompt: Any) -> RegisteredPrompt:
    """Return ``prompt`` unchanged if valid, else raise :class:`PromptRegistryError`.

    A fail-closed guard: the first reason code is raised so a malformed record never
    enters the registry.
    """
    errors = validate_prompt(prompt)
    if errors:
        code, message = errors[0]
        raise PromptRegistryError(code, message)
    return prompt


# --- The registry ------------------------------------------------------------


class PromptRegistry:
    """An in-memory registry resolving prompts only by explicit id + exact version.

    Registration validates the record (fail-closed) and rejects a duplicate
    ``(prompt_id, version)``.  Resolution returns only an explicitly registered
    record and **never silently falls back** to unregistered content: an unknown
    prompt id or an unknown version for a known id raises a bounded
    :class:`PromptRegistryError`.  Both register and resolve are pure with respect to
    the outside world — they perform no I/O and return inert data.
    """

    def __init__(self, prompts: Iterable[RegisteredPrompt] | None = None) -> None:
        # Keyed by (prompt_id, version) for exact-version resolution; dict preserves
        # insertion order so projections are deterministic given a stable input.
        self._by_key: dict[tuple[str, str], RegisteredPrompt] = {}
        for prompt in prompts or ():
            self.register(prompt)

    def register(self, prompt: RegisteredPrompt, *, expected_hash: str | None = None) -> RegisteredPrompt:
        """Register ``prompt``; fail closed on a malformed record, hash mismatch, or duplicate.

        When ``expected_hash`` is supplied it must equal the record's
        :attr:`RegisteredPrompt.template_hash`, so a caller can pin the exact template
        body it intends to register; a mismatch raises rather than registering drifted
        content.  Re-registering an existing ``(prompt_id, version)`` is rejected — a
        prompt version is immutable once registered.
        """
        ensure_valid_prompt(prompt)
        if expected_hash is not None and prompt.template_hash != expected_hash:
            raise PromptRegistryError(
                CODE_HASH_MISMATCH,
                f"template hash for {prompt.reference} ({prompt.template_hash}) does not match expected_hash ({expected_hash})",
            )
        if prompt.key in self._by_key:
            raise PromptRegistryError(CODE_DUPLICATE_REGISTRATION, f"prompt version {prompt.reference} is already registered")
        self._by_key[prompt.key] = prompt
        return prompt

    def resolve(self, prompt_id: Any, version: Any, *, expected_hash: str | None = None) -> RegisteredPrompt:
        """Return the registered record for ``(prompt_id, version)`` or fail closed.

        Resolution never falls back to unregistered content: an unknown ``prompt_id``
        raises :data:`CODE_UNKNOWN_PROMPT`; a known ``prompt_id`` with an unregistered
        ``version`` raises :data:`CODE_UNKNOWN_VERSION`.  When ``expected_hash`` is
        supplied it must equal the resolved record's template hash, otherwise
        :data:`CODE_HASH_MISMATCH` is raised — so a caller can confirm the resolved
        template is exactly the one it expects.
        """
        record = self._by_key.get((prompt_id, version))
        if record is None:
            if not any(pid == prompt_id for pid, _ in self._by_key):
                raise PromptRegistryError(CODE_UNKNOWN_PROMPT, f"no prompt is registered under id {prompt_id!r}")
            raise PromptRegistryError(CODE_UNKNOWN_VERSION, f"prompt {prompt_id!r} has no registered version {version!r}")
        if expected_hash is not None and record.template_hash != expected_hash:
            raise PromptRegistryError(
                CODE_HASH_MISMATCH,
                f"template hash for {record.reference} ({record.template_hash}) does not match expected_hash ({expected_hash})",
            )
        return record

    def contains(self, prompt_id: Any, version: Any) -> bool:
        """True iff ``(prompt_id, version)`` is registered (a total, side-effect-free check)."""
        return (prompt_id, version) in self._by_key

    def versions(self, prompt_id: Any) -> tuple[str, ...]:
        """Return the registered versions for ``prompt_id`` in registration order (empty if none)."""
        return tuple(version for (pid, version) in self._by_key if pid == prompt_id)

    def prompt_ids(self) -> tuple[str, ...]:
        """Return the distinct registered prompt ids in first-registration order."""
        seen: dict[str, None] = {}
        for pid, _ in self._by_key:
            seen.setdefault(pid, None)
        return tuple(seen)

    def __len__(self) -> int:
        """The number of registered ``(prompt_id, version)`` records."""
        return len(self._by_key)

    def __contains__(self, key: object) -> bool:
        """Membership by exact ``(prompt_id, version)`` tuple key."""
        return key in self._by_key

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the whole registry (records sorted by key).

        Sorting by ``(prompt_id, version)`` makes the projection independent of
        registration order, so it is stable for validator-friendly tests.
        """
        records = [self._by_key[key].to_dict() for key in sorted(self._by_key)]
        return {"prompts": records}


__all__ = [
    "MAX_PROMPT_ID_LENGTH",
    "MAX_VERSION_LENGTH",
    "MAX_TEMPLATE_LENGTH",
    "MAX_TARGET_SCHEMA_ID_LENGTH",
    "CODE_MALFORMED_PROMPT_ID",
    "CODE_MALFORMED_VERSION",
    "CODE_EMPTY_TEMPLATE",
    "CODE_TEMPLATE_TOO_LONG",
    "CODE_MALFORMED_TARGET_SCHEMA",
    "CODE_MALFORMED_RECORD",
    "CODE_HASH_MISMATCH",
    "CODE_DUPLICATE_REGISTRATION",
    "CODE_UNKNOWN_PROMPT",
    "CODE_UNKNOWN_VERSION",
    "RECORD_CODES",
    "REGISTRY_CODES",
    "REASON_CODES",
    "PromptRegistryError",
    "RegisteredPrompt",
    "PromptRegistry",
    "validate_prompt",
    "ensure_valid_prompt",
]
