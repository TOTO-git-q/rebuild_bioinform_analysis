"""Structured logging fields and a redacting JSON formatter (T-01-06).

The canonical fields required for later API / Worker correlation are:

    time, level, service, project, correlation, task_run

:func:`build_log_payload` is a pure builder (deterministic when given a clock)
used both directly and by :class:`JsonFormatter`, which adapts the standard
library :mod:`logging` to emit one redacted JSON object per record.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from .redaction import redact

# Canonical structured fields every record carries.
CANONICAL_FIELDS = ("time", "level", "service", "project", "correlation", "task_run")

# Standard ``LogRecord`` attributes we never copy into the structured ``fields``.
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName",
        # our injected structured keys, handled explicitly below
        "service", "project", "correlation", "task_run",
    }
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_log_payload(
    *,
    level: str,
    message: str,
    service: str,
    project: Optional[str] = None,
    correlation: Optional[str] = None,
    task_run: Optional[str] = None,
    fields: Optional[Mapping[str, Any]] = None,
    clock: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """Build a structured, redacted log payload.

    The canonical fields are always present; any extra ``fields`` are merged
    after redaction. ``clock`` (a callable returning an ISO timestamp string)
    is injectable for deterministic tests.
    """
    now = clock() if clock is not None else _utc_now_iso()
    payload: dict[str, Any] = {
        "time": now,
        "level": level,
        "service": service,
        "project": project,
        "correlation": correlation,
        "task_run": task_run,
        "message": redact(message),
    }
    if fields:
        for key, value in redact(dict(fields)).items():
            if key not in payload:
                payload[key] = value
    return payload


class JsonFormatter(logging.Formatter):
    """Format a :class:`logging.LogRecord` as a single redacted JSON line.

    Structured context (service / project / correlation / task_run) is read
    from record attributes (typically injected via ``extra=`` or a
    :class:`logging.LoggerAdapter`); defaults fill any that are absent.
    """

    def __init__(self, *, service: str = "auto_bioinfo") -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_")
        }
        payload = build_log_payload(
            level=record.levelname,
            message=record.getMessage(),
            service=getattr(record, "service", self._service),
            project=getattr(record, "project", None),
            correlation=getattr(record, "correlation", None),
            task_run=getattr(record, "task_run", None),
            fields=extra_fields,
            clock=lambda: datetime.fromtimestamp(record.created, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
        )
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def get_logger(
    service: str = "auto_bioinfo",
    *,
    project: Optional[str] = None,
    correlation: Optional[str] = None,
    task_run: Optional[str] = None,
    level: str = "INFO",
) -> logging.LoggerAdapter:
    """Return a stdlib logger wrapped to emit redacted structured JSON.

    The returned :class:`logging.LoggerAdapter` injects the structured context
    into every record. The implementation stays intentionally small and is
    safe to call repeatedly for the same service (handlers are not duplicated).
    """
    logger = logging.getLogger(f"auto_bioinfo.{service}")
    logger.setLevel(level)
    logger.propagate = False
    if not any(getattr(h, "_auto_bioinfo_json", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter(service=service))
        handler._auto_bioinfo_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    context = {
        "service": service,
        "project": project,
        "correlation": correlation,
        "task_run": task_run,
    }
    return logging.LoggerAdapter(logger, context)
