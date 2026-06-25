"""Structured logging and sensitive-field redaction (T-01-06).

Provides a small, reusable structured-logging layer for later API / Worker
services. Every emitted record carries the canonical fields
(``time``, ``level``, ``service``, ``project``, ``correlation``, ``task_run``)
and is passed through key/value redaction so secrets and secret-like values are
never written to logs.
"""

from .logging import (
    CANONICAL_FIELDS,
    JsonFormatter,
    build_log_payload,
    get_logger,
)
from .redaction import REDACTED, SENSITIVE_KEY_PATTERN, is_sensitive_key, redact

__all__ = [
    "REDACTED",
    "SENSITIVE_KEY_PATTERN",
    "is_sensitive_key",
    "redact",
    "CANONICAL_FIELDS",
    "JsonFormatter",
    "build_log_payload",
    "get_logger",
]
