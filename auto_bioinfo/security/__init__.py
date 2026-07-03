"""Lane-4 security-hardening policy layer (WP-23).

A small family of **pure, offline, deterministic** policy objects and enforcement
checks that turn the requirement spec's security controls into reviewable domain
decisions rather than live network / credential machinery:

- :mod:`auto_bioinfo.security.domain_allowlist` — a network *egress* guard: a
  domain/protocol/port/task-type allowlist that fails closed on an unauthorised
  destination (T-23-04, T-23-13);
- :mod:`auto_bioinfo.security.secret_reference` — a secret *reference* provider
  and a payload scanner: this system models **references only**, never real key
  material, and rejects a payload that carries anything secret-like (T-23-03,
  T-23-11);
- :mod:`auto_bioinfo.security.data_egress_policy` — data-sensitivity
  classification, artifact-sensitivity inheritance, downgrade-approval gating, and
  a field-level external-send decision so restricted data cannot cross a boundary
  (T-23-06, T-23-07, T-23-10);
- :mod:`auto_bioinfo.security.rbac_hardening` — a separation-of-duties layer over
  the merged :mod:`auto_bioinfo.control_plane.auth_rbac` contract: self-approval,
  reviewing one's own work, cross-project access, over-permission, and privileged
  audit-log access all fail closed (T-23-01, T-23-02, T-23-08).

Every module is a total function of its explicit in-memory inputs: no network,
no real secret access, no clock read, no persistence, no subprocess.  Enforcement
is a bounded, reason-coded *decision value* — never a real grant, a real network
call, or real key material.
"""
