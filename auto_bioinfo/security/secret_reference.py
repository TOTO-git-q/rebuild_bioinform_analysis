"""Secret *reference* provider and payload secret-scanner (WP-23 / T-23-03, T-23-11).

The requirement spec is emphatic: logs, APIs, and ``TaskPacket``s must **never**
carry plaintext secrets — a secret is addressed only by an opaque *reference*, and
a secret scan of any outbound payload must find **zero** plaintext.

This module models exactly that, and *only* that.  It holds **no real key
material** and reads **no real secret store**: a :class:`SecretReference` is an
inert pointer (e.g. ``secret://vault/ncbi-api-key``) that a future infrastructure
adapter *would* resolve at the edge — resolution is explicitly out of scope and
this module never returns, embeds, generates, or logs any real credential.  The
scanner is a pure, deterministic detector that a caller runs over an in-memory
payload before it would be logged / sent, so a leak fails closed.

Design constraints (WP-23):

- **Pure and deterministic, and inert.** Every function is a total function of its
  explicit in-memory inputs.  No I/O, no environment/credential read, no clock, no
  network, no persistence.  Inputs are never mutated.  **No test, fixture, or code
  path here ever contains real key material** — the scanner's detectors are
  structural/entropy heuristics, and its own docstrings/patterns hold no secret.
- **Reference, never material.** :func:`resolve_reference` returns a *reference
  handle projection*, never a secret value.  A :class:`SecretReference` that
  smells like inline material (looks like a bearer token / private-key block /
  high-entropy blob rather than a ``scheme://path`` pointer) is rejected.
- **Fail closed.** A payload that carries anything secret-like — a sensitive key
  whose value is not itself a bare reference, an inline ``Bearer`` token, a
  ``key=<blob>`` assignment, a private-key PEM header, or a long high-entropy
  token — is reported as a finding, and :func:`assert_no_plaintext_secret` treats
  any finding as a blocking condition.
- **Bounded vocabulary.** Scan outcomes use a small, stable set of finding kinds
  (:data:`FINDING_KINDS`); callers branch on the machine-readable kind.

It reuses :mod:`auto_bioinfo.observability.redaction`'s sensitive-key notion so the
security scanner and the logging redactor agree on what "sensitive" means.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..observability.redaction import is_sensitive_key

# --- Reference scheme --------------------------------------------------------
# A secret is addressed only by an opaque reference of the form
# ``<scheme>://<path>`` where scheme names a *reference provider*, never a
# transport that could carry material.  These are the only permitted schemes.
REFERENCE_SCHEMES = ("secret", "vault", "ref", "kms", "ssm")
_REFERENCE_RE = re.compile(r"^(?P<scheme>[a-z][a-z0-9+.-]*)://(?P<path>[A-Za-z0-9][A-Za-z0-9._/-]*)$")

MAX_REFERENCE_LENGTH = 512

# --- Bounded finding kinds (what a scan can flag) ----------------------------
FINDING_SENSITIVE_KEY_PLAINTEXT = "SENSITIVE_KEY_PLAINTEXT"
FINDING_INLINE_BEARER = "INLINE_BEARER_TOKEN"
FINDING_INLINE_ASSIGNMENT = "INLINE_SECRET_ASSIGNMENT"
FINDING_PRIVATE_KEY_BLOCK = "PRIVATE_KEY_BLOCK"
FINDING_HIGH_ENTROPY_TOKEN = "HIGH_ENTROPY_TOKEN"
FINDING_CONNECTION_STRING_CREDENTIALS = "CONNECTION_STRING_CREDENTIALS"

FINDING_KINDS = (
    FINDING_SENSITIVE_KEY_PLAINTEXT,
    FINDING_INLINE_BEARER,
    FINDING_INLINE_ASSIGNMENT,
    FINDING_PRIVATE_KEY_BLOCK,
    FINDING_HIGH_ENTROPY_TOKEN,
    FINDING_CONNECTION_STRING_CREDENTIALS,
)

# --- Detector patterns (structural — they hold no real secret) ---------------
# ``Bearer <token>`` where the token is non-trivial.
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._+/=-]{8,}")
# ``key = value`` / ``key: value`` assignments for a sensitive-looking name.
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?key|private[_-]?key|credential)\s*[=:]\s*\S{6,}"
)
# A PEM/OpenSSH private-key block header (structural marker only).
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")
# scheme://user:pass@host connection-string authority with inline credentials.
_CONN_CRED_RE = re.compile(r"(?i)[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s:/@]+@")

# A high-entropy token heuristic: a long unbroken alnum/base64-ish run whose
# Shannon entropy per char is high enough to look like a random secret rather
# than prose, an id, or a hash-like reference the caller intends to expose.
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_-]{24,}")
_HIGH_ENTROPY_BITS_PER_CHAR = 3.5


def is_secret_reference(value: Any) -> bool:
    """True iff ``value`` is a well-formed opaque secret *reference* string.

    A reference is ``<scheme>://<path>`` with ``scheme`` in
    :data:`REFERENCE_SCHEMES`; it is a *pointer*, never material.
    """
    if not isinstance(value, str) or not (0 < len(value) <= MAX_REFERENCE_LENGTH):
        return False
    match = _REFERENCE_RE.match(value)
    if match is None:
        return False
    return match.group("scheme") in REFERENCE_SCHEMES


def _shannon_entropy_bits_per_char(text: str) -> float:
    """Shannon entropy (bits/char) of ``text`` — a pure structural measure."""
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(text)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _looks_like_high_entropy_secret(token: str) -> bool:
    """True iff ``token`` looks like a random high-entropy secret blob."""
    if len(token) < 24:
        return False
    # A reference-looking or plainly-structured token (few distinct chars) is not
    # treated as a secret; a high per-char entropy random blob is.
    return _shannon_entropy_bits_per_char(token) >= _HIGH_ENTROPY_BITS_PER_CHAR and len(set(token)) >= 12


@dataclass(frozen=True)
class SecretReference:
    """An inert pointer to a secret held in an external store — never material.

    ``ref`` is an opaque ``<scheme>://<path>`` string (see
    :data:`REFERENCE_SCHEMES`).  ``description`` is optional non-sensitive prose.
    This object never carries, resolves, or logs the underlying value.
    """

    ref: str
    description: str = ""

    @property
    def is_valid(self) -> bool:
        return is_secret_reference(self.ref)

    @property
    def scheme(self) -> str:
        match = _REFERENCE_RE.match(self.ref) if isinstance(self.ref, str) else None
        return match.group("scheme") if match else ""

    def to_dict(self) -> dict[str, Any]:
        """A projection carrying only the reference and its description — no value."""
        return {"ref": self.ref, "description": self.description, "is_valid": self.is_valid, "scheme": self.scheme}


class SecretReferenceError(ValueError):
    """A secret reference was malformed or looked like inline material (fail closed)."""


def resolve_reference(reference: Any) -> dict[str, Any]:
    """Return an inert *reference handle projection* — **never** a secret value.

    This is the whole public "resolution" surface: it validates that
    ``reference`` is a well-formed opaque pointer and echoes back only the
    reference metadata (scheme + path), so a caller can carry a resolvable handle
    through a ``TaskPacket`` without ever materialising a credential.  Actually
    fetching the secret is the job of a future edge adapter and is out of scope;
    this function raises :class:`SecretReferenceError` rather than ever returning
    material.
    """
    ref_value = reference.ref if isinstance(reference, SecretReference) else reference
    if not isinstance(ref_value, str) or not is_secret_reference(ref_value):
        raise SecretReferenceError(f"not a well-formed opaque secret reference: {ref_value!r}")
    match = _REFERENCE_RE.match(ref_value)
    assert match is not None  # guaranteed by is_secret_reference
    return {
        "ref": ref_value,
        "scheme": match.group("scheme"),
        "path": match.group("path"),
        "resolved": False,  # this module never fetches material; a handle only
        "note": "reference handle only; no secret material is ever returned by this offline provider",
    }


@dataclass(frozen=True)
class SecretFinding:
    """One place a scan found (or suspected) plaintext secret material.

    ``kind`` is one of :data:`FINDING_KINDS`; ``path`` is the dotted/indexed
    location inside the payload; ``key`` is the offending mapping key (when any).
    No finding ever echoes the suspected secret value itself — only its location
    and a redacted marker — so the *finding* can be logged safely.
    """

    kind: str
    path: str
    key: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "key": self.key, "detail": self.detail}


@dataclass(frozen=True)
class SecretScanResult:
    """The deterministic outcome of scanning a payload for plaintext secrets."""

    findings: tuple[SecretFinding, ...] = ()

    @property
    def clean(self) -> bool:
        """True iff no plaintext secret was found (the required outbound state)."""
        return len(self.findings) == 0

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({f.kind for f in self.findings}))

    def to_dict(self) -> dict[str, Any]:
        return {"clean": self.clean, "findings": [f.to_dict() for f in self.findings], "kinds": list(self.kinds())}


def _scan_text(text: str, path: str, key: str, findings: list[SecretFinding]) -> None:
    """Append findings for any inline secret material in a single string value.

    A bare, well-formed secret *reference* is explicitly *not* a finding — that is
    the intended safe representation.
    """
    if is_secret_reference(text):
        return
    if _PRIVATE_KEY_RE.search(text):
        findings.append(SecretFinding(FINDING_PRIVATE_KEY_BLOCK, path, key, "value contains a PRIVATE KEY block header"))
    if _BEARER_RE.search(text):
        findings.append(SecretFinding(FINDING_INLINE_BEARER, path, key, "value contains an inline Bearer token"))
    if _ASSIGNMENT_RE.search(text):
        findings.append(SecretFinding(FINDING_INLINE_ASSIGNMENT, path, key, "value contains an inline secret assignment"))
    if _CONN_CRED_RE.search(text):
        findings.append(SecretFinding(FINDING_CONNECTION_STRING_CREDENTIALS, path, key, "value contains a connection string with inline credentials"))
    for token in _TOKEN_RE.findall(text):
        if _looks_like_high_entropy_secret(token):
            findings.append(SecretFinding(FINDING_HIGH_ENTROPY_TOKEN, path, key, "value contains a high-entropy token that looks like a raw secret"))
            break


def _scan(value: Any, path: str, key: str, findings: list[SecretFinding]) -> None:
    if isinstance(value, Mapping):
        for k, v in value.items():
            child_path = f"{path}.{k}" if path else str(k)
            # A sensitive-named key whose value is not itself a bare reference is a
            # plaintext-secret finding regardless of the value's shape.
            if is_sensitive_key(k) and not (isinstance(v, str) and is_secret_reference(v)):
                if isinstance(v, (str, int, float)) and str(v).strip():
                    findings.append(SecretFinding(FINDING_SENSITIVE_KEY_PLAINTEXT, child_path, str(k), "sensitive-named field carries a non-reference value"))
            _scan(v, child_path, str(k), findings)
    elif isinstance(value, str):
        _scan_text(value, path, key, findings)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _scan(item, f"{path}[{index}]", "", findings)


def scan_payload_for_secrets(payload: Any) -> SecretScanResult:
    """Scan an arbitrary in-memory payload for plaintext secret material.

    Pure and deterministic: it walks mappings / sequences / strings and reports
    every place plaintext secret material appears, without ever copying the
    suspected value into a finding.  A well-formed opaque secret *reference* is
    never a finding.  Returns a :class:`SecretScanResult`; ``result.clean`` is the
    required "safe to log / send" state.
    """
    findings: list[SecretFinding] = []
    _scan(payload, "", "", findings)
    return SecretScanResult(findings=tuple(findings))


def assert_no_plaintext_secret(payload: Any) -> None:
    """Raise :class:`SecretReferenceError` if ``payload`` carries any plaintext secret.

    The fail-closed enforcement wrapper for a boundary (log write / API response /
    TaskPacket build): a single finding blocks the payload.  The raised message
    names the finding *kinds and locations* only, never the suspected value.
    """
    result = scan_payload_for_secrets(payload)
    if not result.clean:
        locations = ", ".join(f"{f.kind}@{f.path or '<root>'}" for f in result.findings)
        raise SecretReferenceError(f"payload carries plaintext secret material and must not cross this boundary: {locations}")


__all__ = [
    "REFERENCE_SCHEMES",
    "MAX_REFERENCE_LENGTH",
    "FINDING_SENSITIVE_KEY_PLAINTEXT",
    "FINDING_INLINE_BEARER",
    "FINDING_INLINE_ASSIGNMENT",
    "FINDING_PRIVATE_KEY_BLOCK",
    "FINDING_HIGH_ENTROPY_TOKEN",
    "FINDING_CONNECTION_STRING_CREDENTIALS",
    "FINDING_KINDS",
    "is_secret_reference",
    "SecretReference",
    "SecretReferenceError",
    "resolve_reference",
    "SecretFinding",
    "SecretScanResult",
    "scan_payload_for_secrets",
    "assert_no_plaintext_secret",
]
