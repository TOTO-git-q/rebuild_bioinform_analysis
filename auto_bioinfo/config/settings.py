"""Configuration model, loader and secret-reference types (T-01-03).

Design goals (see package docstring):

* Distinguish environment variables, non-sensitive config and secret references.
* Fail fast on missing/invalid required config with explicit, **non-secret**
  error messages (only config *keys* / env-var *names* are ever named).
* Never store, log, render or example a secret *value* — only references.

The model intentionally stays small: just enough for later API / Worker
services to resolve their environment and locate their secrets, without
building runtime infrastructure here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid.

    By construction the message references only config keys / environment
    variable *names* and never embeds a secret value.
    """


class FieldKind(str, Enum):
    """The three configuration categories the model distinguishes."""

    ENV = "env"  # runtime-provided value read from the environment
    NON_SENSITIVE = "non_sensitive"  # static, safe-to-log config value
    SECRET_REF = "secret_ref"  # a reference/name to a secret, never the value


# Placeholder used when a sensitive value must be shown in a safe view/example.
REDACTED = "***REDACTED***"


@dataclass(frozen=True)
class ConfigField:
    """Declarative description of a single configuration field."""

    key: str  # attribute name on AppConfig
    env_var: str  # source environment variable name
    kind: FieldKind
    required: bool = False
    default: Optional[str] = None
    choices: Optional[tuple[str, ...]] = None
    description: str = ""


@dataclass(frozen=True)
class SecretRef:
    """A *reference* to a secret — never the secret value itself.

    ``name`` is the logical secret name; ``env_var`` is the environment
    variable (or secret-manager key) that holds the actual value at runtime.
    The value is resolved lazily via :meth:`resolve` and is never stored on
    this object, captured in ``repr``, or written to logs.
    """

    name: str
    env_var: str

    def resolve(self, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
        """Return the secret value from the environment, or ``None`` if unset.

        The value is returned to the caller for immediate use and is never
        retained on this object.
        """
        import os

        env = os.environ if environ is None else environ
        return env.get(self.env_var)

    def __repr__(self) -> str:  # pragma: no cover - trivial, but keep explicit
        # Only the reference (name + env-var name) is shown; never a value.
        return f"SecretRef(name={self.name!r}, env_var={self.env_var!r})"


# --- Field registry ---------------------------------------------------------
#
# Non-sensitive / environment fields. ``database_url`` is required and carries
# NO embedded password (the password is supplied separately via a secret ref),
# which is why it has no default and triggers fail-fast when unset.
CONFIG_FIELDS: tuple[ConfigField, ...] = (
    ConfigField(
        key="environment",
        env_var="AUTO_BIOINFO_ENV",
        kind=FieldKind.NON_SENSITIVE,
        required=True,
        default="dev",
        choices=("dev", "test", "prod"),
        description="Deployment environment.",
    ),
    ConfigField(
        key="service",
        env_var="AUTO_BIOINFO_SERVICE",
        kind=FieldKind.ENV,
        required=False,
        default="auto_bioinfo",
        description="Logical service / component name (used in structured logs).",
    ),
    ConfigField(
        key="log_level",
        env_var="AUTO_BIOINFO_LOG_LEVEL",
        kind=FieldKind.ENV,
        required=False,
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        description="Root log level.",
    ),
    ConfigField(
        key="database_url",
        env_var="AUTO_BIOINFO_DATABASE_URL",
        kind=FieldKind.ENV,
        required=True,
        default=None,
        description="Postgres connection URL WITHOUT an embedded password "
        "(the password is supplied separately via a secret reference).",
    ),
)

# Secret references. Only the *reference* (logical name + env-var name) is part
# of the config model; values are resolved lazily at the point of use.
SECRET_FIELDS: tuple[ConfigField, ...] = (
    ConfigField(
        key="database_password",
        env_var="AUTO_BIOINFO_DB_PASSWORD",
        kind=FieldKind.SECRET_REF,
        required=False,
        description="Reference to the Postgres password secret.",
    ),
    ConfigField(
        key="object_store_secret_key",
        env_var="AUTO_BIOINFO_OBJECT_STORE_SECRET_KEY",
        kind=FieldKind.SECRET_REF,
        required=False,
        description="Reference to the object-store secret key.",
    ),
)


@dataclass(frozen=True)
class AppConfig:
    """Resolved, validated application configuration.

    Non-sensitive fields hold their concrete values. ``secret_refs`` maps a
    logical secret name to a :class:`SecretRef` (a reference only — never a
    value). The whole object is therefore safe to render via
    :meth:`public_dict`.
    """

    environment: str
    service: str
    log_level: str
    database_url: str
    secret_refs: Mapping[str, SecretRef]

    def public_dict(self) -> dict[str, object]:
        """Return a non-sensitive view that is safe to log.

        Secret references are rendered as their env-var *names*; secret values
        are never resolved here.
        """
        return {
            "environment": self.environment,
            "service": self.service,
            "log_level": self.log_level,
            "database_url": self.database_url,
            "secret_refs": {name: ref.env_var for name, ref in self.secret_refs.items()},
        }


def _database_url_has_embedded_password(url: str) -> bool:
    """True if a URL appears to embed credentials as ``scheme://user:pass@host``."""
    if "://" not in url:
        return False
    authority = url.split("://", 1)[1].split("/", 1)[0]
    if "@" not in authority:
        return False
    userinfo = authority.rsplit("@", 1)[0]
    return ":" in userinfo


def load_config(
    environ: Optional[Mapping[str, str]] = None,
    *,
    fields: tuple[ConfigField, ...] = CONFIG_FIELDS,
    secret_fields: tuple[ConfigField, ...] = SECRET_FIELDS,
) -> AppConfig:
    """Build an :class:`AppConfig` from the environment, failing fast.

    Raises :class:`ConfigError` (naming only keys / env-var names, never
    values) when a required field is missing, a value is outside its allowed
    ``choices``, or a database URL embeds a password instead of using the
    secret reference.
    """
    import os

    env = os.environ if environ is None else environ

    missing: list[str] = []
    invalid: list[str] = []
    resolved: dict[str, str] = {}

    for field in fields:
        raw = env.get(field.env_var)
        value = raw if raw is not None else field.default
        if value is None:
            if field.required:
                missing.append(field.env_var)
            continue
        if field.choices is not None and value not in field.choices:
            # Non-sensitive choice fields only; safe to name the allowed set.
            invalid.append(f"{field.env_var} (allowed: {', '.join(field.choices)})")
            continue
        resolved[field.key] = value

    if missing:
        raise ConfigError(
            "Missing required configuration: " + ", ".join(sorted(missing))
        )
    if invalid:
        raise ConfigError(
            "Invalid configuration value(s): " + ", ".join(sorted(invalid))
        )

    db_url = resolved.get("database_url", "")
    if db_url and _database_url_has_embedded_password(db_url):
        # Do NOT echo the URL — it contains a secret.
        raise ConfigError(
            "AUTO_BIOINFO_DATABASE_URL must not embed a password; supply the "
            "password via the AUTO_BIOINFO_DB_PASSWORD secret reference instead."
        )

    secret_refs: dict[str, SecretRef] = {
        field.key: SecretRef(name=field.key, env_var=field.env_var)
        for field in secret_fields
    }

    return AppConfig(
        environment=resolved["environment"],
        service=resolved["service"],
        log_level=resolved["log_level"],
        database_url=resolved["database_url"],
        secret_refs=secret_refs,
    )
