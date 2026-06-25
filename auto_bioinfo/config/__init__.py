"""Unified project configuration model (T-01-03).

Separates three distinct categories of configuration so later services
(API / Worker) can be wired without ever placing secret *values* into code,
logs, error messages, or committed examples:

1. **environment variables** — runtime-provided settings read from the process
   environment (``FieldKind.ENV``);
2. **non-sensitive config values** — static, safe-to-log settings such as the
   deployment environment or log level (``FieldKind.NON_SENSITIVE``);
3. **secret references** — the *name / location* of a secret (an env-var name or
   secret-manager key), never the secret value itself (``FieldKind.SECRET_REF``).

Required configuration fails fast with explicit, non-secret error messages.
"""

from .settings import (
    CONFIG_FIELDS,
    SECRET_FIELDS,
    AppConfig,
    ConfigError,
    ConfigField,
    FieldKind,
    SecretRef,
    load_config,
)

__all__ = [
    "AppConfig",
    "ConfigError",
    "ConfigField",
    "FieldKind",
    "SecretRef",
    "CONFIG_FIELDS",
    "SECRET_FIELDS",
    "load_config",
]
