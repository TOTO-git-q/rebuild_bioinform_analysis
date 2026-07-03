"""Inert network-access policy objects for resource discovery (WP-08 / T-08-12).

The plan asks for a domain allowlist, a rate limit, a User-Agent and a credential
*reference* so that "未授权域名调用被阻止" — an unauthorized domain call is
blocked.  Crucially this is a **policy object, not live enforcement**: nothing
here opens a socket, reaches the network, reads an environment variable, or holds
a real secret.  A policy is an inert, reviewable description of what *would* be
permitted, and :meth:`evaluate` is a pure function returning a bounded, reason-
coded :class:`NetworkAccessDecision` *as data* — the offline discovery auditor
consults that decision before it replays a fixture, so an out-of-allowlist or
over-budget call fails closed exactly as a live gate later would, without any
real network machinery existing yet.

Design constraints (mirroring the house contract style):

- **Pure, deterministic, offline.**  No I/O of any kind: no socket, HTTP client,
  DNS, environment/credential read, clock read, randomness, or side effect.  A
  decision is a total function of the policy plus the explicit call description
  (domain + a caller-supplied prior-call count for the rate check).  Inputs are
  never mutated.
- **Fail closed.**  Every uncertainty resolves to a ``blocked`` decision with a
  stable reason code (:data:`NETWORK_REASON_CODES`).  An unknown / non-allowlisted
  domain, an over-budget call, a missing User-Agent, or an inline (non-reference)
  credential is blocked.
- **No secret material.**  A credential is only ever a *reference* (an indirection
  token such as ``env:GEO_API_KEY`` or ``secret_ref:...``), never an inline value;
  an inline-looking credential is rejected before it can be recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- Bounded decision + reason vocabularies ----------------------------------
NETWORK_ALLOWED = "allowed"
NETWORK_BLOCKED = "blocked"
NETWORK_DECISIONS = (NETWORK_ALLOWED, NETWORK_BLOCKED)

CODE_NETWORK_ALLOWED = "NETWORK_ALLOWED"
CODE_DOMAIN_NOT_ALLOWLISTED = "NETWORK_DOMAIN_NOT_ALLOWLISTED"
CODE_DOMAIN_MALFORMED = "NETWORK_DOMAIN_MALFORMED"
CODE_RATE_LIMIT_EXCEEDED = "NETWORK_RATE_LIMIT_EXCEEDED"
CODE_USER_AGENT_MISSING = "NETWORK_USER_AGENT_MISSING"
CODE_CREDENTIAL_REFERENCE_INVALID = "NETWORK_CREDENTIAL_REFERENCE_INVALID"

NETWORK_REASON_CODES = (
    CODE_NETWORK_ALLOWED,
    CODE_DOMAIN_NOT_ALLOWLISTED,
    CODE_DOMAIN_MALFORMED,
    CODE_RATE_LIMIT_EXCEEDED,
    CODE_USER_AGENT_MISSING,
    CODE_CREDENTIAL_REFERENCE_INVALID,
)

# A credential value must be a *reference* using one of these indirection schemes;
# anything else is treated as a possible inline secret and rejected.
_CREDENTIAL_REFERENCE_SCHEMES = ("env:", "secret_ref:", "vault:", "keyring:")


def _is_credential_reference(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    return any(text.startswith(scheme) and len(text) > len(scheme) for scheme in _CREDENTIAL_REFERENCE_SCHEMES)


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().rstrip(".")


@dataclass(frozen=True)
class NetworkAccessDecision:
    """The inert, reason-coded outcome of a policy evaluation.

    ``decision`` is one of :data:`NETWORK_DECISIONS`; ``reason_code`` is one of
    :data:`NETWORK_REASON_CODES`.  ``checked`` records which sub-checks ran so the
    decision is auditable.  It confers no authority and is never a grant to make a
    real call — it only describes what the (future) live gate would permit.
    """

    decision: str
    reason_code: str
    message: str
    domain: str = ""
    checked: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == NETWORK_ALLOWED

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason_code": self.reason_code,
            "message": self.message,
            "domain": self.domain,
            "allowed": self.allowed,
            "checked": list(self.checked),
        }


@dataclass(frozen=True)
class NetworkAccessPolicy:
    """An inert description of the network access the project would permit.

    ``allowed_domains`` is the explicit allowlist (matched case-insensitively);
    ``max_calls_per_run`` is a per-run call budget (a deterministic count, never a
    wall-clock rate); ``user_agent`` is the identifying UA string that must be
    present; ``credential_reference`` is an optional indirection token (never an
    inline secret).  The policy performs no enforcement itself — a caller passes a
    call description to :meth:`evaluate` and branches on the returned decision.
    """

    allowed_domains: tuple[str, ...] = ()
    max_calls_per_run: int = 0
    user_agent: str = ""
    credential_reference: str = ""

    def __post_init__(self) -> None:
        # A credential, if given, must be a reference — never an inline secret.
        # Fail closed at construction so a bad reference can never be recorded.
        if self.credential_reference and not _is_credential_reference(self.credential_reference):
            raise ValueError(f"credential_reference must be an indirection token ({', '.join(_CREDENTIAL_REFERENCE_SCHEMES)}...), never an inline secret")

    def allowlisted(self, domain: str) -> bool:
        norm = _normalize_domain(domain)
        return bool(norm) and norm in {_normalize_domain(d) for d in self.allowed_domains}

    def evaluate(self, *, domain: str, prior_calls: int = 0) -> NetworkAccessDecision:
        """Decide whether a call to ``domain`` would be permitted (data only).

        ``prior_calls`` is the caller-tracked count of calls already made this run,
        so the rate check stays a deterministic budget rather than a clock read.
        Checks run in a stable order and the first failure fails closed.
        """
        checked: list[str] = []
        norm = _normalize_domain(domain)

        checked.append("domain_wellformed")
        if not norm:
            return NetworkAccessDecision(NETWORK_BLOCKED, CODE_DOMAIN_MALFORMED, "domain is blank or malformed", domain=norm, checked=checked)

        checked.append("domain_allowlist")
        if not self.allowlisted(domain):
            return NetworkAccessDecision(NETWORK_BLOCKED, CODE_DOMAIN_NOT_ALLOWLISTED, f"domain {norm!r} is not in the allowlist", domain=norm, checked=checked)

        checked.append("user_agent")
        if not self.user_agent.strip():
            return NetworkAccessDecision(NETWORK_BLOCKED, CODE_USER_AGENT_MISSING, "policy declares no identifying User-Agent", domain=norm, checked=checked)

        checked.append("credential_reference")
        if self.credential_reference and not _is_credential_reference(self.credential_reference):
            return NetworkAccessDecision(
                NETWORK_BLOCKED, CODE_CREDENTIAL_REFERENCE_INVALID, "credential_reference is not a valid indirection token", domain=norm, checked=checked
            )

        checked.append("rate_limit")
        if self.max_calls_per_run > 0 and prior_calls >= self.max_calls_per_run:
            return NetworkAccessDecision(
                NETWORK_BLOCKED,
                CODE_RATE_LIMIT_EXCEEDED,
                f"per-run call budget {self.max_calls_per_run} reached ({prior_calls} prior calls)",
                domain=norm,
                checked=checked,
            )

        return NetworkAccessDecision(NETWORK_ALLOWED, CODE_NETWORK_ALLOWED, f"call to {norm!r} is within policy", domain=norm, checked=checked)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_domains": list(self.allowed_domains),
            "max_calls_per_run": self.max_calls_per_run,
            "user_agent": self.user_agent,
            # Only the *reference* is ever recorded; there is no secret to redact.
            "credential_reference": self.credential_reference,
        }
