"""Sensitive key/value redaction for structured logs (T-01-06).

Two complementary filters:

* **key-based** — any mapping key whose name matches a sensitive pattern
  (password, token, secret, api_key, authorization, credential, ...) has its
  value replaced wholesale with :data:`REDACTED`;
* **value-based** — inline secret-like substrings (``Bearer <token>``,
  ``password=...`` style assignments) inside free-text values are masked even
  when the surrounding key is not itself sensitive.

The functions are pure and recurse through nested dicts / lists / tuples so a
caller can redact an arbitrary log payload before it is serialized.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***REDACTED***"

# Keys whose *value* must never be logged. Matched case-insensitively as a
# substring of the key name, so e.g. ``db_password`` and ``api_token`` match.
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?key|private[_-]?key|authorization|credential|bearer|"
    r"session|cookie|passphrase)"
)

# Inline secret-like substrings inside free-text values, each paired with a
# replacement callable that masks only the secret portion.
_INLINE_VALUE_PATTERNS = (
    # Authorization: Bearer <token>  ->  Bearer ***REDACTED***
    (re.compile(r"(?i)\b(bearer)\s+\S+"), lambda m: f"{m.group(1)} {REDACTED}"),
    # key = value / key: value  ->  key=***REDACTED***
    (
        re.compile(
            r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
            r"secret[_-]?key|authorization|credential)(\s*[=:]\s*)\S+"
        ),
        lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}",
    ),
    # credentials embedded in a URL authority: scheme://user:pass@host
    (
        re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s:/@]+(@)"),
        lambda m: f"{m.group(1)}{REDACTED}{m.group(2)}",
    ),
)


def is_sensitive_key(key: Any) -> bool:
    """True if ``key`` names a field whose value must be redacted."""
    return isinstance(key, str) and bool(SENSITIVE_KEY_PATTERN.search(key))


def _redact_text(text: str) -> str:
    redacted = text
    for pattern, repl in _INLINE_VALUE_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted


def redact(value: Any, *, _key: Any = None) -> Any:
    """Return a redacted copy of ``value``.

    Mappings, lists and tuples are walked recursively. A value under a
    sensitive key is fully replaced; free-text strings are scanned for inline
    secrets regardless of their key.
    """
    if is_sensitive_key(_key):
        return REDACTED

    if isinstance(value, dict):
        return {k: redact(v, _key=k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        redacted = [redact(item, _key=None) for item in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    if isinstance(value, str):
        return _redact_text(value)
    return value
