"""Deterministic network-egress allowlist guard (WP-23 / T-23-04, T-23-13).

The requirement spec demands that every outbound access from a Worker / tool /
gateway be constrained to an explicit **domain + protocol + port + task-type**
allowlist, and that an unauthorised destination (and adversarial URI shapes such
as embedded credentials, IP literals, or path-traversal authorities) be *blocked*
and auditable rather than merely documented.

This module realises that as a pure policy object and a fail-closed decision.  It
performs **no real network access whatsoever**: it neither resolves DNS, opens a
socket, nor validates that a host exists — it only decides, from the explicit
facts a caller supplies, whether a described egress *would be permitted* by the
policy.  "Enforcement" here is a deterministic policy *value*; a real network
layer, if ever built, would consult this decision, but none is used or authorised
here.

Design constraints (WP-23), mirroring the WP-04/WP-06 house style:

- **Pure and deterministic.** :func:`evaluate_egress` and every helper is a total
  function of its explicit in-memory inputs.  No I/O: no DNS, no socket, no
  environment/credential read, no clock, no subprocess, no persistence.  Inputs
  are never mutated.  The decision carries an empty binding order that is stable,
  so byte-identical inputs yield a byte-identical projection.
- **Fail closed.** Every uncertainty resolves to a *non-allowing* decision: a
  blank/malformed request, an unknown protocol, a port outside the rule, a
  task-type the rule does not cover, an embedded credential (``user:pass@host``),
  a raw IP-literal host, a host carrying a path/query/whitespace, and a
  destination matching **no** rule all fail closed.  A default-deny applies when
  nothing matches.
- **No implicit wildcards.** A rule matches a host exactly; a subdomain is
  permitted **only** when the rule explicitly sets ``allow_subdomains=True``.
  There is no catch-all ``*`` destination.
- **Bounded vocabulary.** The decision status is one of exactly three values
  (:data:`STATUSES`) and the reason is one of a small, stable set of codes
  (:data:`REASON_CODES`).  Callers branch on the machine-readable code.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# --- Bounds ------------------------------------------------------------------
MAX_HOST_LENGTH = 253  # the DNS name length ceiling; a longer host is malformed
MAX_LABEL_LENGTH = 63
MIN_PORT = 1
MAX_PORT = 65535

# --- Bounded protocol vocabulary ---------------------------------------------
# Only these application protocols may ever be named; anything else is unknown.
# (No ``ftp``/``file``/``gopher`` etc. — an unlisted scheme fails closed.)
PROTOCOL_HTTPS = "https"
PROTOCOL_HTTP = "http"
PROTOCOLS = (PROTOCOL_HTTPS, PROTOCOL_HTTP)

# --- Bounded status vocabulary -----------------------------------------------
STATUS_ALLOW = "allow"
STATUS_DENY = "deny"
STATUS_INVALID = "invalid"

STATUSES = (STATUS_ALLOW, STATUS_DENY, STATUS_INVALID)

# --- Stable reason codes -----------------------------------------------------
# allow:
CODE_ALLOW = "EGRESS_ALLOW"
# deny (a legitimate refusal — the request is well-formed but not permitted):
CODE_HOST_NOT_ALLOWED = "EGRESS_HOST_NOT_ALLOWED"
CODE_PROTOCOL_NOT_ALLOWED = "EGRESS_PROTOCOL_NOT_ALLOWED"
CODE_PORT_NOT_ALLOWED = "EGRESS_PORT_NOT_ALLOWED"
CODE_TASK_TYPE_NOT_ALLOWED = "EGRESS_TASK_TYPE_NOT_ALLOWED"
CODE_NO_MATCHING_RULE = "EGRESS_NO_MATCHING_RULE"
# invalid (fail closed — the request/policy itself is malformed or adversarial):
CODE_MALFORMED_REQUEST = "EGRESS_MALFORMED_REQUEST"
CODE_MALFORMED_HOST = "EGRESS_MALFORMED_HOST"
CODE_EMBEDDED_CREDENTIALS = "EGRESS_EMBEDDED_CREDENTIALS"
CODE_IP_LITERAL_HOST = "EGRESS_IP_LITERAL_HOST"
CODE_MALFORMED_PORT = "EGRESS_MALFORMED_PORT"
CODE_MALFORMED_PROTOCOL = "EGRESS_MALFORMED_PROTOCOL"
CODE_MALFORMED_TASK_TYPE = "EGRESS_MALFORMED_TASK_TYPE"
CODE_MALFORMED_POLICY = "EGRESS_MALFORMED_POLICY"

REASON_CODES = (
    CODE_ALLOW,
    CODE_HOST_NOT_ALLOWED,
    CODE_PROTOCOL_NOT_ALLOWED,
    CODE_PORT_NOT_ALLOWED,
    CODE_TASK_TYPE_NOT_ALLOWED,
    CODE_NO_MATCHING_RULE,
    CODE_MALFORMED_REQUEST,
    CODE_MALFORMED_HOST,
    CODE_EMBEDDED_CREDENTIALS,
    CODE_IP_LITERAL_HOST,
    CODE_MALFORMED_PORT,
    CODE_MALFORMED_PROTOCOL,
    CODE_MALFORMED_TASK_TYPE,
    CODE_MALFORMED_POLICY,
)

_CODE_STATUS = {
    CODE_ALLOW: STATUS_ALLOW,
    CODE_HOST_NOT_ALLOWED: STATUS_DENY,
    CODE_PROTOCOL_NOT_ALLOWED: STATUS_DENY,
    CODE_PORT_NOT_ALLOWED: STATUS_DENY,
    CODE_TASK_TYPE_NOT_ALLOWED: STATUS_DENY,
    CODE_NO_MATCHING_RULE: STATUS_DENY,
    CODE_MALFORMED_REQUEST: STATUS_INVALID,
    CODE_MALFORMED_HOST: STATUS_INVALID,
    CODE_EMBEDDED_CREDENTIALS: STATUS_INVALID,
    CODE_IP_LITERAL_HOST: STATUS_INVALID,
    CODE_MALFORMED_PORT: STATUS_INVALID,
    CODE_MALFORMED_PROTOCOL: STATUS_INVALID,
    CODE_MALFORMED_TASK_TYPE: STATUS_INVALID,
    CODE_MALFORMED_POLICY: STATUS_INVALID,
}


# --- Small, pure predicates --------------------------------------------------


def _is_real_int(value: Any) -> bool:
    """A real integer — ``bool`` excluded (it subclasses ``int``)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_valid_port(value: Any) -> bool:
    """True iff ``value`` is an integer port in the valid range."""
    return _is_real_int(value) and MIN_PORT <= value <= MAX_PORT


def normalize_host(host: Any) -> str | None:
    """Return the normalised host (lowercased, trailing dot stripped), or ``None``.

    A host is *malformed* — returns ``None`` — when it is not a plain DNS name:
    empty, over-long, containing whitespace / a scheme / a path / a query /
    an ``@`` (embedded credentials) / a ``:`` (port glued on) / an empty label,
    or a label outside DNS label rules.  This is intentionally strict so an
    adversarial authority string cannot slip past as a bare host.
    """
    if not isinstance(host, str):
        return None
    candidate = host.strip()
    if not candidate or len(candidate) > MAX_HOST_LENGTH:
        return None
    # Reject anything that is clearly not a bare hostname.
    for bad in ("/", "\\", "@", ":", "?", "#", " ", "\t", "\n", "\r", "%"):
        if bad in candidate:
            return None
    candidate = candidate.rstrip(".").lower()
    if not candidate:
        return None
    labels = candidate.split(".")
    for label in labels:
        if not label or len(label) > MAX_LABEL_LENGTH:
            return None
        if not all(ch.isalnum() or ch == "-" for ch in label):
            return None
        if label.startswith("-") or label.endswith("-"):
            return None
    return candidate


def is_ip_literal(host: str) -> bool:
    """True iff ``host`` looks like a raw IPv4 literal (fail closed to a name).

    A raw IP destination bypasses name-based allowlisting, so it is refused: the
    policy names *hosts*, not addresses.  IPv6 literals never survive
    :func:`normalize_host` (they carry ``:``), so only the dotted-quad shape needs
    an explicit check here.
    """
    parts = host.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and len(part) <= 3 and 0 <= int(part) <= 255 for part in parts)


# --- The policy value objects ------------------------------------------------


@dataclass(frozen=True)
class EgressRule:
    """One allowlist entry: a host, the protocols/ports/task-types it permits.

    - ``host`` — the exact DNS name this rule authorises (normalised on build);
    - ``protocols`` — the permitted protocols (a subset of :data:`PROTOCOLS`);
    - ``ports`` — the permitted destination ports;
    - ``task_types`` — the task types allowed to use this destination; an empty
      set means "no task type is permitted" (fail closed), never "all";
    - ``allow_subdomains`` — when ``True``, a strict subdomain of ``host`` also
      matches (``a.b.example.org`` matches ``example.org``); otherwise only the
      exact host matches.  There is no wildcard host token.

    This is plain caller-supplied data; it grants nothing on its own —
    :func:`evaluate_egress` interprets it.
    """

    host: str
    protocols: frozenset[str] = field(default_factory=frozenset)
    ports: frozenset[int] = field(default_factory=frozenset)
    task_types: frozenset[str] = field(default_factory=frozenset)
    allow_subdomains: bool = False

    def matches_host(self, host: str) -> bool:
        rule_host = normalize_host(self.host)
        if rule_host is None:
            return False
        if host == rule_host:
            return True
        if self.allow_subdomains and host.endswith("." + rule_host):
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "protocols": sorted(self.protocols),
            "ports": sorted(self.ports),
            "task_types": sorted(self.task_types),
            "allow_subdomains": self.allow_subdomains,
        }


@dataclass(frozen=True)
class EgressPolicy:
    """An ordered bundle of :class:`EgressRule` grants (default-deny otherwise)."""

    rules: tuple[EgressRule, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"rules": [rule.to_dict() for rule in self.rules]}


@dataclass(frozen=True)
class EgressRequest:
    """The described outbound access a caller wants a decision on (inert facts)."""

    host: str
    protocol: str
    port: int
    task_type: str

    def to_dict(self) -> dict[str, Any]:
        return {"host": self.host, "protocol": self.protocol, "port": self.port, "task_type": self.task_type}


@dataclass(frozen=True)
class EgressDecision:
    """The deterministic, reason-coded outcome of an egress evaluation."""

    status: str
    reason_code: str
    message: str
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.status == STATUS_ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "allowed": self.allowed,
            "binding": dict(self.binding),
        }


def _validate_rule(rule: Any) -> str | None:
    """Return a message if a single rule is structurally malformed, else ``None``."""
    if not isinstance(rule, EgressRule):
        return "each rule must be an EgressRule"
    if normalize_host(rule.host) is None:
        return f"rule host {rule.host!r} is not a valid bare DNS name"
    if not isinstance(rule.protocols, (frozenset, set, frozenset)):
        return "rule protocols must be a set"
    for proto in rule.protocols:
        if proto not in PROTOCOLS:
            return f"rule protocol {proto!r} is not a known protocol"
    for port in rule.ports:
        if not is_valid_port(port):
            return f"rule port {port!r} is not a valid port"
    for task_type in rule.task_types:
        if not isinstance(task_type, str) or not task_type.strip():
            return "each rule task_type must be a non-blank string"
    if not isinstance(rule.allow_subdomains, bool):
        return "rule allow_subdomains must be a bool"
    return None


def evaluate_egress(request: Any, policy: Any) -> EgressDecision:
    """Decide whether ``request`` is a permitted egress under ``policy``, fail-closed.

    A pure, deterministic function returning a bounded :class:`EgressDecision`
    (never raises for a domain condition, never mutates its inputs, performs no
    network/DNS/socket/clock access).  Precedence:

    1. The request and policy must be well-formed values → otherwise ``invalid``.
    2. The host must normalise to a bare DNS name, must not be an IP literal, and
       must not carry embedded credentials → otherwise ``invalid``.
    3. The protocol/port/task-type must each be well-formed → otherwise ``invalid``.
    4. Find rules matching the host.  None → ``deny`` (``no matching rule``).  Of
       the host-matching rules, the protocol, then port, then task-type must be
       permitted by at least one; the first failing dimension yields the
       corresponding ``deny`` code.  A rule permitting all three → ``allow``.
    """
    binding: dict[str, Any] = {
        "host": None,
        "normalized_host": None,
        "protocol": None,
        "port": None,
        "task_type": None,
        "matched_rule_hosts": [],
    }

    def _decide(code: str, message: str) -> EgressDecision:
        return EgressDecision(status=_CODE_STATUS[code], reason_code=code, message=message, binding=dict(binding))

    if not isinstance(request, EgressRequest):
        return _decide(CODE_MALFORMED_REQUEST, "request must be an EgressRequest carrying host/protocol/port/task_type")
    if not isinstance(policy, EgressPolicy):
        return _decide(CODE_MALFORMED_POLICY, "policy must be an EgressPolicy")

    binding["host"] = request.host
    binding["protocol"] = request.protocol
    binding["port"] = request.port
    binding["task_type"] = request.task_type

    # Adversarial-shape checks before anything is matched.
    if isinstance(request.host, str) and "@" in request.host:
        return _decide(CODE_EMBEDDED_CREDENTIALS, "host carries embedded credentials (user:pass@host); refused (fail closed)")
    host = normalize_host(request.host)
    if host is None:
        return _decide(CODE_MALFORMED_HOST, f"host {request.host!r} is not a valid bare DNS name")
    if is_ip_literal(host):
        return _decide(CODE_IP_LITERAL_HOST, "host is a raw IP literal; the allowlist names hosts, not addresses (fail closed)")
    binding["normalized_host"] = host

    if not isinstance(request.protocol, str) or request.protocol not in PROTOCOLS:
        if not isinstance(request.protocol, str) or not request.protocol.strip():
            return _decide(CODE_MALFORMED_PROTOCOL, "protocol must be a non-blank string")
        # A well-formed but unknown scheme fails closed as malformed (it is not a
        # recognised protocol the guard can reason about).
        return _decide(CODE_MALFORMED_PROTOCOL, f"protocol {request.protocol!r} is not a known protocol")
    if not is_valid_port(request.port):
        return _decide(CODE_MALFORMED_PORT, f"port {request.port!r} is not a valid port (1..65535)")
    if not isinstance(request.task_type, str) or not request.task_type.strip():
        return _decide(CODE_MALFORMED_TASK_TYPE, "task_type must be a non-blank string")

    for rule in policy.rules:
        rule_error = _validate_rule(rule)
        if rule_error is not None:
            return _decide(CODE_MALFORMED_POLICY, rule_error)

    matching = [rule for rule in policy.rules if rule.matches_host(host)]
    binding["matched_rule_hosts"] = [normalize_host(rule.host) for rule in matching]
    if not matching:
        return _decide(CODE_NO_MATCHING_RULE, f"no allowlist rule matches host {host!r}; egress denied by default (fail closed)")

    # A destination is allowed iff a single host-matching rule permits the
    # protocol AND the port AND the task type.  Report the first dimension no
    # matching rule satisfies (protocol → port → task_type) for an auditable reason.
    protocol_ok = [rule for rule in matching if request.protocol in rule.protocols]
    if not protocol_ok:
        return _decide(CODE_PROTOCOL_NOT_ALLOWED, f"protocol {request.protocol!r} is not permitted for host {host!r}")
    port_ok = [rule for rule in protocol_ok if request.port in rule.ports]
    if not port_ok:
        return _decide(CODE_PORT_NOT_ALLOWED, f"port {request.port} is not permitted for host {host!r}")
    task_ok = [rule for rule in port_ok if request.task_type in rule.task_types]
    if not task_ok:
        return _decide(CODE_TASK_TYPE_NOT_ALLOWED, f"task_type {request.task_type!r} is not permitted for host {host!r}")

    return _decide(CODE_ALLOW, f"egress to {host!r} over {request.protocol}:{request.port} for task {request.task_type!r} is permitted")


def build_policy(rules: Iterable[EgressRule]) -> EgressPolicy:
    """Convenience constructor: freeze an iterable of rules into an :class:`EgressPolicy`."""
    return EgressPolicy(rules=tuple(rules))


__all__ = [
    "MAX_HOST_LENGTH",
    "MAX_LABEL_LENGTH",
    "MIN_PORT",
    "MAX_PORT",
    "PROTOCOL_HTTPS",
    "PROTOCOL_HTTP",
    "PROTOCOLS",
    "STATUS_ALLOW",
    "STATUS_DENY",
    "STATUS_INVALID",
    "STATUSES",
    "CODE_ALLOW",
    "CODE_HOST_NOT_ALLOWED",
    "CODE_PROTOCOL_NOT_ALLOWED",
    "CODE_PORT_NOT_ALLOWED",
    "CODE_TASK_TYPE_NOT_ALLOWED",
    "CODE_NO_MATCHING_RULE",
    "CODE_MALFORMED_REQUEST",
    "CODE_MALFORMED_HOST",
    "CODE_EMBEDDED_CREDENTIALS",
    "CODE_IP_LITERAL_HOST",
    "CODE_MALFORMED_PORT",
    "CODE_MALFORMED_PROTOCOL",
    "CODE_MALFORMED_TASK_TYPE",
    "CODE_MALFORMED_POLICY",
    "REASON_CODES",
    "is_valid_port",
    "normalize_host",
    "is_ip_literal",
    "EgressRule",
    "EgressPolicy",
    "EgressRequest",
    "EgressDecision",
    "evaluate_egress",
    "build_policy",
]
