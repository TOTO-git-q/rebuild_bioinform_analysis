"""Agent gateway (WP-05) — the provider-agnostic LLM seam and its local contracts.

The agent gateway is where the system will, in future work packages, turn an
explicit prompt into a structured, validated model response without letting the
LLM write domain state directly.  WP-05a / T-05-01 delivers only the foundation:
a small provider-agnostic :class:`LLMProvider` ``Protocol`` plus deterministic,
serializable request / message / usage / response value shapes, bounded
fail-closed validators, and an offline, deterministic :class:`FakeLLMProvider`
for tests.

Everything here is local, deterministic, and offline: no network, no provider
SDK, no credential/environment access, no real clock, and no content egress.  A
provider call returns inert *data* to the caller; it never writes project state,
events, artifacts, or full-content logs.  The reserved production adapter (a real
network LLM provider reached through an audited tool broker) would implement the
same :class:`LLMProvider` protocol without the gateway changing — mirroring the
reserved ports in :mod:`auto_bioinfo.ports`.

WP-05b / T-05-02 adds the local :class:`PromptRegistry` contract foundation: a
deterministic, offline registry that resolves a prompt only by stable identity
(prompt id + exact version), binds it to a canonical template hash and a target
schema reference, and never silently falls back to unregistered content.

Later T-05 slices (structured-output admission, semantic validator hook, egress
policy, tool broker, audit/usage/budget machinery) are out of scope for this
foundation.
"""

from __future__ import annotations

from .llm_provider import (
    CODE_CONTENT_TOO_LONG,
    CODE_EMPTY_MESSAGES,
    CODE_FORBIDDEN_METADATA,
    CODE_MALFORMED_CONTENT,
    CODE_MALFORMED_FINISH_REASON,
    CODE_MALFORMED_MAX_TOKENS,
    CODE_MALFORMED_MESSAGES,
    CODE_MALFORMED_METADATA,
    CODE_MALFORMED_MODEL,
    CODE_MALFORMED_PROVIDER,
    CODE_MALFORMED_RESPONSE,
    CODE_MALFORMED_ROLE,
    CODE_MALFORMED_STOP,
    CODE_MALFORMED_TEMPERATURE,
    CODE_MALFORMED_USAGE,
    CODE_NEGATIVE_TOKENS,
    CODE_TOKENS_TOO_LARGE,
    CODE_TOO_MANY_MESSAGES,
    CODE_USAGE_INCONSISTENT,
    FINISH_CONTENT_FILTER,
    FINISH_ERROR,
    FINISH_LENGTH,
    FINISH_REASONS,
    FINISH_STOP,
    FORBIDDEN_METADATA_KEY_MARKERS,
    REASON_CODES,
    REQUEST_CODES,
    RESPONSE_CODES,
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_USER,
    ROLES,
    USAGE_CODES,
    FakeLLMProvider,
    LLMContractError,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ensure_valid_request,
    ensure_valid_response,
    validate_message,
    validate_request,
    validate_response,
    validate_usage,
)
from .prompt_registry import (
    CODE_DUPLICATE_REGISTRATION,
    CODE_EMPTY_TEMPLATE,
    CODE_HASH_MISMATCH,
    CODE_MALFORMED_PROMPT_ID,
    CODE_MALFORMED_RECORD,
    CODE_MALFORMED_TARGET_SCHEMA,
    CODE_MALFORMED_VERSION,
    CODE_TEMPLATE_TOO_LONG,
    CODE_UNKNOWN_PROMPT,
    CODE_UNKNOWN_VERSION,
    MAX_PROMPT_ID_LENGTH,
    MAX_TARGET_SCHEMA_ID_LENGTH,
    MAX_TEMPLATE_LENGTH,
    MAX_VERSION_LENGTH,
    RECORD_CODES,
    REGISTRY_CODES,
    PromptRegistry,
    PromptRegistryError,
    RegisteredPrompt,
    ensure_valid_prompt,
    validate_prompt,
)
from .prompt_registry import REASON_CODES as PROMPT_REASON_CODES

__all__ = [
    "CODE_CONTENT_TOO_LONG",
    "CODE_EMPTY_MESSAGES",
    "CODE_FORBIDDEN_METADATA",
    "CODE_MALFORMED_CONTENT",
    "CODE_MALFORMED_FINISH_REASON",
    "CODE_MALFORMED_MAX_TOKENS",
    "CODE_MALFORMED_MESSAGES",
    "CODE_MALFORMED_METADATA",
    "CODE_MALFORMED_MODEL",
    "CODE_MALFORMED_PROVIDER",
    "CODE_MALFORMED_RESPONSE",
    "CODE_MALFORMED_ROLE",
    "CODE_MALFORMED_STOP",
    "CODE_MALFORMED_TEMPERATURE",
    "CODE_MALFORMED_USAGE",
    "CODE_NEGATIVE_TOKENS",
    "CODE_TOKENS_TOO_LARGE",
    "CODE_TOO_MANY_MESSAGES",
    "CODE_USAGE_INCONSISTENT",
    "FINISH_CONTENT_FILTER",
    "FINISH_ERROR",
    "FINISH_LENGTH",
    "FINISH_REASONS",
    "FINISH_STOP",
    "FORBIDDEN_METADATA_KEY_MARKERS",
    "REASON_CODES",
    "REQUEST_CODES",
    "RESPONSE_CODES",
    "ROLE_ASSISTANT",
    "ROLE_SYSTEM",
    "ROLE_USER",
    "ROLES",
    "USAGE_CODES",
    "FakeLLMProvider",
    "LLMContractError",
    "LLMMessage",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMUsage",
    "ensure_valid_request",
    "ensure_valid_response",
    "validate_message",
    "validate_request",
    "validate_response",
    "validate_usage",
    "CODE_DUPLICATE_REGISTRATION",
    "CODE_EMPTY_TEMPLATE",
    "CODE_HASH_MISMATCH",
    "CODE_MALFORMED_PROMPT_ID",
    "CODE_MALFORMED_RECORD",
    "CODE_MALFORMED_TARGET_SCHEMA",
    "CODE_MALFORMED_VERSION",
    "CODE_TEMPLATE_TOO_LONG",
    "CODE_UNKNOWN_PROMPT",
    "CODE_UNKNOWN_VERSION",
    "MAX_PROMPT_ID_LENGTH",
    "MAX_TARGET_SCHEMA_ID_LENGTH",
    "MAX_TEMPLATE_LENGTH",
    "MAX_VERSION_LENGTH",
    "RECORD_CODES",
    "REGISTRY_CODES",
    "PROMPT_REASON_CODES",
    "PromptRegistry",
    "PromptRegistryError",
    "RegisteredPrompt",
    "ensure_valid_prompt",
    "validate_prompt",
]
