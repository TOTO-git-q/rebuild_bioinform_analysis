"""Local sensitive-content classification & minimum-context contract (WP-05e / T-05-05).

The smallest *local* contract the future agent gateway (WP-05) needs so that —
before any model/provider call ever exists — it can take a project's governance
:class:`~auto_bioinfo.core.schemas.ProjectPolicy` (or a policy-shaped mapping)
plus an explicit set of candidate context fields, **classify** each field by
sensitivity, **build the minimum allowed context** from only the explicitly
requested fields, **redact** inline secrets from the values that are admitted,
and return an **inert build decision as data only** — *without ever opening a
socket, importing a provider SDK, reading a credential, reaching the network,
calling a paid service, or letting any content leave the process*.

This is the local pre-egress foundation slice only.  It defines:

- a bounded sensitivity vocabulary (:data:`SENSITIVITIES`) and a deterministic
  classifier (:func:`classify_field_sensitivity`) that fuses a caller-declared
  field sensitivity with name-based and value-based detection.  Detection can
  only *escalate* a field's sensitivity, never downgrade it, and an undeclared /
  unrecognised sensitivity resolves to :data:`SENSITIVITY_UNKNOWN` (fail closed);
- a minimum-context builder (:func:`build_model_context`) that considers **only
  the explicitly requested fields** (it rejects broad / full-object context by
  default), admits a field to the model context only when the policy permits its
  sensitivity tier, blocks every ``sensitive`` field, withholds every ``unknown``
  field, redacts inline secrets from each admitted value, and returns an inert
  :class:`ContextBuildDecision`;
- inert result shapes (:class:`ContextFieldOutcome`, :class:`ContextBuildDecision`)
  whose public projections (``to_dict``) carry only field *names*, classified
  sensitivities, inclusion flags and bounded reason codes — never the raw value of
  a withheld / sensitive field.

Design constraints (mirroring the WP-05a / WP-05b / WP-05c / WP-05d contract style):

- **Pure, deterministic, offline.**  No I/O whatsoever: no network, socket, HTTP
  client, provider SDK, environment/credential access, real clock, threads, or
  file/DB/queue side effect.  A build decision is a total function of its explicit
  in-memory inputs (a policy, the candidate fields, and the requested-field list).
- **Fail closed, no fallback.**  Every uncertainty resolves to a bounded,
  reason-coded outcome (:data:`REASON_CODES`).  A missing / malformed policy, a
  malformed request, an unknown field, an ``unknown``-sensitivity field, or an
  explicitly ``sensitive`` field never silently enters the model context.  A
  ``sensitive`` field is **always** blocked from raw egress; a policy can never be
  configured to admit ``sensitive`` content (that would fail closed as a malformed
  policy).
- **No raw-value leak.**  Only the redacted values of *admitted* (public / policy-
  allowed) fields appear in the returned context; a withheld field contributes only
  its name, classified sensitivity and reason code.  The caller's raw input mapping
  is never copied into the decision.
- **Data only.**  The builder returns *data* to the caller: an inert
  :class:`ContextBuildDecision`.  It writes no project state, business object,
  event, artifact, queue/outbox record, ordinary domain table, or full-content log,
  and it mutates none of its inputs.

Out of scope for T-05-05 (and deliberately *not* implemented here): any real
provider/HTTP/SDK integration or content egress, the tool broker (T-05-06),
raw-output artifact storage / audit / budget / rate-limit / circuit-breaker
machinery (T-05-07..11), prompt authoring / approval / rollback (T-05-12), and any
write of a built context into project state, events, artifacts, logs, or downstream
domain/business objects.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.core.schemas import ProjectPolicy
from auto_bioinfo.observability.redaction import REDACTED, is_sensitive_key, redact

# --- Bounds (so an unbounded input cannot exhaust a downstream store) ---------
# Every limit below is a fail-closed guard: an input exceeding it is *malformed*,
# never silently truncated.
MAX_CONTEXT_FIELDS = 256
MAX_FIELD_NAME_LENGTH = 200
MAX_VALUE_SCAN_DEPTH = 32

# --- Bounded sensitivity vocabulary ------------------------------------------
# The tiers a context field can carry.  ``public`` is freely admissible; ``internal``
# is admissible only when the policy explicitly permits it; ``sensitive`` is never
# admitted as raw content; ``unknown`` is the fail-closed default for any field whose
# sensitivity was neither declared nor detectable.
SENSITIVITY_PUBLIC = "public"
SENSITIVITY_INTERNAL = "internal"
SENSITIVITY_SENSITIVE = "sensitive"
SENSITIVITY_UNKNOWN = "unknown"

SENSITIVITIES = (
    SENSITIVITY_PUBLIC,
    SENSITIVITY_INTERNAL,
    SENSITIVITY_SENSITIVE,
    SENSITIVITY_UNKNOWN,
)

# The tiers a caller may *declare* for a field (``unknown`` is a resolved state, not
# a declaration), and the tiers a policy may permit as its egress ceiling (``public``
# or ``internal`` only — ``sensitive`` egress can never be configured).
DECLARABLE_SENSITIVITIES = (SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_SENSITIVE)
POLICY_EGRESS_TIERS = (SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL)

# --- Bounded build-status vocabulary -----------------------------------------
STATUS_BUILT = "built"
STATUS_BLOCKED = "blocked"

STATUSES = (STATUS_BUILT, STATUS_BLOCKED)

# --- Stable reason codes -----------------------------------------------------
# Callers / a future gateway branch on these machine-readable codes, never the
# human message, so they must stay stable.
# build-level (a fail-closed *blocked* decision — no field is admitted):
CODE_MISSING_POLICY = "CTX_MISSING_POLICY"
CODE_MALFORMED_POLICY = "CTX_MALFORMED_POLICY"
CODE_MALFORMED_FIELDS = "CTX_MALFORMED_FIELDS"
CODE_MALFORMED_REQUEST = "CTX_MALFORMED_REQUEST"
CODE_TOO_MANY_FIELDS = "CTX_TOO_MANY_FIELDS"
# field-level (a withheld field within an otherwise-built context):
CODE_SENSITIVE_BLOCKED = "CTX_SENSITIVE_BLOCKED"
CODE_UNKNOWN_SENSITIVITY = "CTX_UNKNOWN_SENSITIVITY"
CODE_POLICY_DISALLOWED = "CTX_POLICY_DISALLOWED"
CODE_UNKNOWN_FIELD = "CTX_UNKNOWN_FIELD"

BUILD_CODES = (
    CODE_MISSING_POLICY,
    CODE_MALFORMED_POLICY,
    CODE_MALFORMED_FIELDS,
    CODE_MALFORMED_REQUEST,
    CODE_TOO_MANY_FIELDS,
)

FIELD_CODES = (
    CODE_SENSITIVE_BLOCKED,
    CODE_UNKNOWN_SENSITIVITY,
    CODE_POLICY_DISALLOWED,
    CODE_UNKNOWN_FIELD,
)

REASON_CODES = BUILD_CODES + FIELD_CODES

# Inline value markers that *escalate* an otherwise non-sensitive field to
# ``sensitive``.  A field whose free-text value advertises its own sensitivity
# (``SENSITIVE``/``CONFIDENTIAL``/``PHI``/``PII``/...) must never enter the model
# context as raw content even if the caller declared it public.
_SENSITIVE_VALUE_PATTERN = re.compile(r"(?i)\b(sensitive|confidential|restricted|secret|private|phi|pii)\b")


# --- Small, pure predicates --------------------------------------------------


def _is_bounded_field_name(value: Any) -> bool:
    """True iff ``value`` is a non-blank, bounded, single-line printable-ASCII name."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_FIELD_NAME_LENGTH and all("\x20" <= ch <= "\x7e" for ch in value)


def _value_looks_sensitive(value: Any, depth: int = 0) -> bool:
    """True iff ``value`` (walked recursively) advertises sensitive content.

    A free-text string matching :data:`_SENSITIVE_VALUE_PATTERN`, a mapping key that
    names a credential-like field (:func:`is_sensitive_key`), or a structure nested
    beyond :data:`MAX_VALUE_SCAN_DEPTH` (which is treated as sensitive — fail closed)
    all return ``True``.  Pure; performs no I/O and mutates nothing.
    """
    if depth > MAX_VALUE_SCAN_DEPTH:
        # An over-deep structure cannot be scanned within the bound: fail closed.
        return True
    if isinstance(value, str):
        return bool(_SENSITIVE_VALUE_PATTERN.search(value))
    if isinstance(value, Mapping):
        for key, item in value.items():
            if is_sensitive_key(key) or _value_looks_sensitive(item, depth + 1):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_value_looks_sensitive(item, depth + 1) for item in value)
    return False


def classify_field_sensitivity(name: Any, value: Any, declared: Any = None) -> str:
    """Classify a single field's effective sensitivity (one of :data:`SENSITIVITIES`).

    Detection can only *escalate*: a credential-like ``name`` (:func:`is_sensitive_key`)
    or a value advertising its own sensitivity forces :data:`SENSITIVITY_SENSITIVE`,
    overriding any softer caller declaration.  Otherwise a valid ``declared`` tier is
    honoured, and an absent / unrecognised declaration resolves to
    :data:`SENSITIVITY_UNKNOWN` (fail closed).  Pure and deterministic.
    """
    if is_sensitive_key(name) or _value_looks_sensitive(value):
        return SENSITIVITY_SENSITIVE
    if declared in DECLARABLE_SENSITIVITIES:
        return declared
    return SENSITIVITY_UNKNOWN


# --- Policy resolution -------------------------------------------------------


@dataclass(frozen=True)
class _ResolvedPolicy:
    """The bounded, normalized egress view extracted from a caller's policy."""

    policy_ref: str
    max_egress_sensitivity: str


def _resolve_policy(policy: Any) -> tuple[_ResolvedPolicy | None, str | None]:
    """Normalize a :class:`ProjectPolicy` / policy-shaped mapping to an egress view.

    Returns ``(resolved, None)`` on success, else ``(None, code)`` with a bounded
    build code: :data:`CODE_MISSING_POLICY` when ``policy`` is ``None`` and
    :data:`CODE_MALFORMED_POLICY` when it is neither a :class:`ProjectPolicy` nor a
    mapping, carries a non-mapping ``export_policy``, or configures an egress ceiling
    outside :data:`POLICY_EGRESS_TIERS` (a ``sensitive``/``unknown`` egress ceiling can
    never be configured — that fails closed as a malformed policy).
    """
    if policy is None:
        return None, CODE_MISSING_POLICY

    if isinstance(policy, ProjectPolicy):
        export_policy: Any = policy.export_policy
        policy_ref = policy.policy_id()
    elif isinstance(policy, Mapping):
        export_policy = policy.get("export_policy", {})
        ref = policy.get("project_policy_id")
        policy_ref = (
            ref
            if isinstance(ref, str) and ref
            else make_stable_id(
                "context_policy",
                {
                    "project_id": policy.get("project_id", ""),
                    "data_sensitivity": policy.get("data_sensitivity", ""),
                    "export_policy": export_policy if isinstance(export_policy, Mapping) else None,
                },
            )
        )
    else:
        return None, CODE_MALFORMED_POLICY

    if not isinstance(export_policy, Mapping):
        return None, CODE_MALFORMED_POLICY

    max_egress = export_policy.get("max_context_sensitivity", SENSITIVITY_PUBLIC)
    if max_egress not in POLICY_EGRESS_TIERS:
        # An absent ceiling defaults to PUBLIC above; an explicitly configured
        # ``sensitive``/``unknown``/garbage ceiling is a malformed policy (fail closed).
        return None, CODE_MALFORMED_POLICY

    return _ResolvedPolicy(policy_ref=policy_ref, max_egress_sensitivity=max_egress), None


def _admit(sensitivity: str, max_egress: str) -> str | None:
    """Return ``None`` if a field of ``sensitivity`` may be admitted, else a reason code.

    ``public`` is always admissible; ``internal`` only when the policy ceiling is
    ``internal``; ``sensitive`` is never admissible (:data:`CODE_SENSITIVE_BLOCKED`);
    ``unknown`` fails closed (:data:`CODE_UNKNOWN_SENSITIVITY`).
    """
    if sensitivity == SENSITIVITY_SENSITIVE:
        return CODE_SENSITIVE_BLOCKED
    if sensitivity == SENSITIVITY_UNKNOWN:
        return CODE_UNKNOWN_SENSITIVITY
    if sensitivity == SENSITIVITY_INTERNAL and max_egress != SENSITIVITY_INTERNAL:
        return CODE_POLICY_DISALLOWED
    return None


# --- Admitted-value normalization (so redaction can fully walk the value) ----


def _to_redactable(value: Any, depth: int = 0) -> Any:
    """Return ``value`` with every nested generic ``Mapping`` normalized to a plain ``dict``.

    The shared redactor (:func:`~auto_bioinfo.observability.redaction.redact`) only
    recurses into concrete ``dict`` / ``list`` / ``tuple``; a generic
    :class:`~collections.abc.Mapping` subclass (e.g. :class:`types.MappingProxyType`)
    would otherwise reach ``included_context`` / ``to_dict()`` *unredacted* and could
    leak an inline secret (an admitted, policy-allowed value still must be redacted).
    Converting every nested mapping to ``dict`` (and walking lists / tuples) lets the
    redactor mask the whole structure.  An over-deep structure fails closed to
    :data:`REDACTED` so no raw content can ever leak past the scan bound.  Pure;
    performs no I/O and mutates nothing (it returns fresh containers).
    """
    if depth > MAX_VALUE_SCAN_DEPTH:
        # Unscannable within the bound: fail closed rather than emit raw content.
        return REDACTED
    if isinstance(value, Mapping):
        return {key: _to_redactable(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_to_redactable(item, depth + 1) for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    return value


# --- Request collection ------------------------------------------------------


def _collect_requested(requested_fields: Any) -> tuple[list[str] | None, str | None]:
    """Collect a bounded, de-duplicated list of requested field names, or fail closed.

    Returns ``(names, None)`` on success.  Returns ``(None, code)`` for a malformed
    request: a string/bytes/mapping (never a valid *list of names*), a non-iterable,
    an iterable that raises while advancing, a malformed name, a duplicate name
    (:data:`CODE_MALFORMED_REQUEST`), or more than :data:`MAX_CONTEXT_FIELDS` names
    (:data:`CODE_TOO_MANY_FIELDS`).  At most ``MAX_CONTEXT_FIELDS + 1`` items are ever
    consumed, so a caller generator can never be advanced into unbounded work.
    """
    if isinstance(requested_fields, (str, bytes, Mapping)):
        return None, CODE_MALFORMED_REQUEST
    try:
        iterator = iter(requested_fields)
    except TypeError:
        return None, CODE_MALFORMED_REQUEST

    collected: list[str] = []
    seen: set[str] = set()
    for _ in range(MAX_CONTEXT_FIELDS + 1):
        try:
            name = next(iterator)
        except StopIteration:
            return collected, None
        except Exception:  # noqa: BLE001 - a misbehaving request name must fail closed
            return None, CODE_MALFORMED_REQUEST
        if not _is_bounded_field_name(name):
            return None, CODE_MALFORMED_REQUEST
        if name in seen:
            return None, CODE_MALFORMED_REQUEST
        seen.add(name)
        collected.append(name)
    # Reached MAX_CONTEXT_FIELDS + 1 pulls without exhaustion => too many names.
    return None, CODE_TOO_MANY_FIELDS


# --- Result shapes -----------------------------------------------------------


@dataclass(frozen=True)
class ContextFieldOutcome:
    """The inert per-field verdict of a context build — name + classification only.

    ``reason_code`` is ``None`` when the field was admitted, else one of
    :data:`FIELD_CODES`.  No raw value is retained here: only the field ``name``, its
    classified ``sensitivity``, and whether it was ``included`` — the bounded outcome a
    future audit could safely keep.
    """

    name: str
    sensitivity: str
    included: bool
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the outcome (stable key order)."""
        return {
            "name": self.name,
            "sensitivity": self.sensitivity,
            "included": self.included,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class ContextBuildDecision:
    """The inert result of a minimum-context build: admitted context, or a block reason.

    Fields:

    - ``status`` — one of :data:`STATUSES`;
    - ``reason_code`` — ``None`` when built, else the bounded build-level block code
      (:data:`BUILD_CODES`) for a fail-closed ``blocked`` decision;
    - ``policy_ref`` — the stable id of the policy the build was held to (``None`` when
      the policy could not be resolved);
    - ``max_egress_sensitivity`` — the policy's resolved egress ceiling (``None`` when
      the policy could not be resolved);
    - ``included_context`` — the minimal admitted context as ``name -> redacted value``
      (only public / policy-allowed fields, each value passed through redaction);
    - ``field_outcomes`` — the per-field verdicts in requested order.

    The value is inert data returned to the caller.  Only redacted values of *admitted*
    fields appear in ``included_context``; a withheld / sensitive field never
    contributes its raw value to any public projection.  It is never written to project
    state, events, artifacts, domain tables, or full-content logs.
    """

    status: str
    reason_code: str | None
    policy_ref: str | None
    max_egress_sensitivity: str | None
    included_context: dict[str, Any]
    field_outcomes: tuple[ContextFieldOutcome, ...] = ()

    @property
    def usable(self) -> bool:
        """True iff the context was built (and is therefore safe for model input)."""
        return self.status == STATUS_BUILT

    @property
    def included_fields(self) -> tuple[str, ...]:
        """The admitted field names, in requested order."""
        return tuple(outcome.name for outcome in self.field_outcomes if outcome.included)

    def withheld(self) -> tuple[ContextFieldOutcome, ...]:
        """The per-field outcomes that were *not* admitted, in requested order."""
        return tuple(outcome for outcome in self.field_outcomes if not outcome.included)

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the decision (stable key order).

        ``included_context`` carries only redacted values of admitted fields; no raw
        value of a withheld / sensitive field is ever present.
        """
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "policy_ref": self.policy_ref,
            "max_egress_sensitivity": self.max_egress_sensitivity,
            "usable": self.usable,
            "included_context": {key: self.included_context[key] for key in sorted(self.included_context)},
            "field_outcomes": [outcome.to_dict() for outcome in self.field_outcomes],
        }


def _blocked(reason_code: str, *, policy: _ResolvedPolicy | None = None) -> ContextBuildDecision:
    """Build a fail-closed ``blocked`` decision that admits no field."""
    return ContextBuildDecision(
        status=STATUS_BLOCKED,
        reason_code=reason_code,
        policy_ref=policy.policy_ref if policy is not None else None,
        max_egress_sensitivity=policy.max_egress_sensitivity if policy is not None else None,
        included_context={},
        field_outcomes=(),
    )


def build_model_context(
    *,
    policy: ProjectPolicy | Mapping[str, Any] | None,
    fields: Mapping[str, Any] | None,
    requested_fields: Iterable[str],
    declared_sensitivities: Mapping[str, str] | None = None,
) -> ContextBuildDecision:
    """Build the minimum allowed model context from explicitly requested fields.

    Resolves ``policy`` to an egress ceiling (fail-closed: a missing / malformed
    policy blocks the whole build), then considers **only** the names in
    ``requested_fields`` — broad / full-object context is rejected by default because
    an unrequested field is never read.  For each requested field it classifies the
    effective sensitivity (caller-declared via ``declared_sensitivities``, escalated by
    name/value detection), admits the field only when the policy permits its tier,
    blocks every ``sensitive`` field, withholds every ``unknown`` field and every field
    absent from ``fields``, and redacts inline secrets from each admitted value.
    Returns an inert :class:`ContextBuildDecision` and writes nothing.

    Even when some fields are withheld, the returned context is still ``usable`` for
    model input: it carries only the admitted, redacted, policy-allowed fields.  Only a
    build-level fault (missing/malformed policy, malformed fields mapping, malformed or
    over-bound request) yields a ``blocked``, non-usable decision.
    """
    resolved, policy_error = _resolve_policy(policy)
    if policy_error is not None:
        return _blocked(policy_error)
    assert resolved is not None  # for type-checkers; guaranteed by the branch above

    if fields is None:
        available: Mapping[str, Any] = {}
    elif isinstance(fields, Mapping):
        available = fields
    else:
        return _blocked(CODE_MALFORMED_FIELDS, policy=resolved)

    if declared_sensitivities is not None and not isinstance(declared_sensitivities, Mapping):
        return _blocked(CODE_MALFORMED_REQUEST, policy=resolved)
    declared: Mapping[str, Any] = declared_sensitivities if isinstance(declared_sensitivities, Mapping) else {}

    requested, request_error = _collect_requested(requested_fields)
    if request_error is not None:
        return _blocked(request_error, policy=resolved)
    assert requested is not None  # guaranteed by the branch above

    included_context: dict[str, Any] = {}
    outcomes: list[ContextFieldOutcome] = []
    for name in requested:
        if name not in available:
            # A requested-but-absent field is withheld (fail closed): never invent it,
            # never silently widen to a broad object.
            outcomes.append(ContextFieldOutcome(name=name, sensitivity=SENSITIVITY_UNKNOWN, included=False, reason_code=CODE_UNKNOWN_FIELD))
            continue
        value = available[name]
        sensitivity = classify_field_sensitivity(name, value, declared.get(name))
        deny_code = _admit(sensitivity, resolved.max_egress_sensitivity)
        if deny_code is not None:
            # Withheld: only the name + classification + reason survive — never the value.
            outcomes.append(ContextFieldOutcome(name=name, sensitivity=sensitivity, included=False, reason_code=deny_code))
            continue
        # Admitted: normalize generic mappings then redact inline secrets defensively
        # so no raw value (string, dict, or generic ``Mapping`` subclass) leaks.
        included_context[name] = redact(_to_redactable(value))
        outcomes.append(ContextFieldOutcome(name=name, sensitivity=sensitivity, included=True, reason_code=None))

    return ContextBuildDecision(
        status=STATUS_BUILT,
        reason_code=None,
        policy_ref=resolved.policy_ref,
        max_egress_sensitivity=resolved.max_egress_sensitivity,
        included_context=included_context,
        field_outcomes=tuple(outcomes),
    )


__all__ = [
    "MAX_CONTEXT_FIELDS",
    "MAX_FIELD_NAME_LENGTH",
    "MAX_VALUE_SCAN_DEPTH",
    "SENSITIVITY_PUBLIC",
    "SENSITIVITY_INTERNAL",
    "SENSITIVITY_SENSITIVE",
    "SENSITIVITY_UNKNOWN",
    "SENSITIVITIES",
    "DECLARABLE_SENSITIVITIES",
    "POLICY_EGRESS_TIERS",
    "STATUS_BUILT",
    "STATUS_BLOCKED",
    "STATUSES",
    "CODE_MISSING_POLICY",
    "CODE_MALFORMED_POLICY",
    "CODE_MALFORMED_FIELDS",
    "CODE_MALFORMED_REQUEST",
    "CODE_TOO_MANY_FIELDS",
    "CODE_SENSITIVE_BLOCKED",
    "CODE_UNKNOWN_SENSITIVITY",
    "CODE_POLICY_DISALLOWED",
    "CODE_UNKNOWN_FIELD",
    "BUILD_CODES",
    "FIELD_CODES",
    "REASON_CODES",
    "classify_field_sensitivity",
    "ContextFieldOutcome",
    "ContextBuildDecision",
    "build_model_context",
]
