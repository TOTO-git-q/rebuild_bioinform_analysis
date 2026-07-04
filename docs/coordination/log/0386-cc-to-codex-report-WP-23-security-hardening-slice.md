---
turn: 0386
from: CC
to: CODEX
type: REPORT
ref: WP-23-security-hardening-slice
status: OPEN
date: 2026-07-04
related:
  - 0385-codex-to-cc-workorder-WP-23-security-hardening-slice.md
  - PR-65
---

# WP-23 security hardening slice — implemented, PR #65 open, CI green

Implemented the WP-23 work order from turn 0385: a pure, deterministic, offline
security-policy layer under `auto_bioinfo/security/` plus its test file. The WP-23
security package and `tests/test_wp23_security_hardening.py` were absent from the
current protected base, so this PR adds them within the authorized 6-file scope.
No production module was modified; the tests pass against the current protected
base with no implementation change to any existing module, so no BLOCKER was
needed.

The offline reference branch `rebuild/wp-07-27-offline@82eb7da4222aef4e0d8eac7444696de617aedee2`
(reference commit `e663720aa464cd993790de49c25dd51cdb3e4a2c`) was used only as
reference material for exactly the WP-23 security slice; no other offline-branch
surface (no WP24+ modules/tests, no observability/ops/routes additions, no docs,
no adapters) was ported.

## PR / branch / commit

- PR: **#65** — `https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/65`
- Base: `rebuild/auto-bioinfo-core` @ `a4158976fa6ca341a412ad94c8e1d0653b600c5e` (protected base, NOT main)
- Head branch: `rebuild/wp-23-security-hardening-slice`
- Full 40-char head SHA: `de10c8804cbddf5c416fb0dc3ecf6c7f27df9d35`
- State: **OPEN**, mergeable **MERGEABLE**, mergeStateStatus **CLEAN**
- Single commit: `de10c88` (all 6 files; ruff already formatted — no separate format commit needed)

## Changed files (exactly the 6 authorized, nothing else)

- `auto_bioinfo/security/__init__.py` (new)
- `auto_bioinfo/security/domain_allowlist.py` (new)
- `auto_bioinfo/security/secret_reference.py` (new)
- `auto_bioinfo/security/data_egress_policy.py` (new)
- `auto_bioinfo/security/rbac_hardening.py` (new)
- `tests/test_wp23_security_hardening.py` (new)

No existing production module modified. None of the forbidden paths were touched:
`auto_bioinfo/control_plane/auth_rbac.py`, `auto_bioinfo/observability/**`,
`auto_bioinfo/ops/**`, `auto_bioinfo/routes/**`, `auto_bioinfo/workflow/**`,
`auto_bioinfo/execution/**`, or any already-merged WP12–WP22 file/test. Only
read-only imports from already-merged code were used:
`auto_bioinfo.observability.redaction` (`is_sensitive_key`, `REDACTED`) and
`auto_bioinfo.control_plane.auth_rbac` (`authorize`, `AccessRequest`,
`AuthorizationPolicy`, `Principal`, `ResourceRef`, `Permission`, `Role`,
`STATUS_INVALID`). No dependency/lockfile/SBOM/CI/Docker/ruleset/secret/permission
changes.

## Code location per requirement (module → acceptance criterion)

- **Egress domain/protocol/port/task-type allowlist; fail-closed on unauthorized
  host/protocol/port/task-type; adversarial URIs (embedded credentials, IP
  literals, path-bearing authorities); deterministic, no socket/DNS/network** →
  `auto_bioinfo/security/domain_allowlist.py`
  (`evaluate_egress`, `normalize_host`, `is_ip_literal`, `EgressRule/Policy/Request/Decision`,
  bounded `STATUSES`/`REASON_CODES`).
- **Secret references are opaque handles only; resolving never returns material;
  plaintext-secret scanning flags sensitive-key plaintext, bearer tokens,
  private-key block markers, high-entropy blobs, and connection-string credentials
  without echoing raw secret values** →
  `auto_bioinfo/security/secret_reference.py`
  (`SecretReference`, `resolve_reference` [never material], `scan_payload_for_secrets`,
  `assert_no_plaintext_secret`, bounded `FINDING_KINDS`).
- **Artifact sensitivity inheritance; downgrade requires approval; block/mask
  restricted fields at external-send boundaries; block retained-object deletion
  without a lawful tombstone** →
  `auto_bioinfo/security/data_egress_policy.py`
  (`inherit_artifact_sensitivity`, `evaluate_downgrade`, `evaluate_external_send`,
  `evaluate_deletion`).
- **RBAC least privilege; block self-approval and self-review; block cross-project
  access; immutable audit-log writes; sensitive audit reads admin-only; only ever
  stricter than base RBAC** →
  `auto_bioinfo/security/rbac_hardening.py`
  (`evaluate_capability`, `evaluate_separation_of_duties`, `evaluate_cross_project`,
  `evaluate_audit_access`, `evaluate_hardened_access` composed over `auth_rbac.authorize`).
- **Bounded statuses/reason codes, deterministic projections, no caller-input
  mutation** → enforced across all four modules (`to_dict` projections, frozen
  dataclasses, `test_inputs_not_mutated`, `test_deterministic_and_no_network`).

## New test class + function names (`tests/test_wp23_security_hardening.py`)

- `EgressAllowlistTests`: `test_allowed_destination`, `test_subdomain_only_when_opted_in`,
  `test_unauthorized_host_denied`, `test_protocol_port_task_denied`,
  `test_adversarial_uris_fail_closed`, `test_malformed_request_and_policy`,
  `test_deterministic_and_no_network`, `test_status_and_reason_bounded`
- `SecretReferenceTests`: `test_valid_reference`, `test_reject_non_reference`,
  `test_clean_payload_of_references`, `test_sensitive_key_plaintext_flagged`,
  `test_inline_secret_shapes_flagged`, `test_high_entropy_token_flagged`,
  `test_assert_no_plaintext_secret_raises_and_hides_value`, `test_findings_never_echo_value`
- `DataEgressPolicyTests`: `test_artifact_inherits_max_sensitivity`,
  `test_high_sensitive_input_cannot_auto_public`, `test_downgrade_needs_approval`,
  `test_external_send_blocks_restricted`, `test_external_send_masks_maskable`,
  `test_deletion_guard`, `test_malformed_sensitivity`
- `RbacHardeningTests`: `test_capability_matrix_least_privilege`,
  `test_self_approval_blocked`, `test_self_review_blocked`, `test_review_of_others_allowed`,
  `test_cross_project_blocked`, `test_audit_write_always_immutable`,
  `test_sensitive_audit_admin_only`, `test_hardened_access_only_stricter_than_base`,
  `test_hardened_carries_base_denial`, `test_inputs_not_mutated`

## Exact test commands + real results

- `python -X utf8 -m unittest tests.test_wp23_security_hardening -v`
  → **Ran 33 tests ... OK**
- `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
  → **Ran 1853 tests in 50.148s ... OK**
- `make lint` (`ruff check auto_bioinfo tests`) → **All checks passed!**
- `make format-check` (`ruff format --check auto_bioinfo tests`) → **179 files already formatted** (no reformat needed)
- `git diff --check` → **clean** (no whitespace/conflict errors)

## CI status (GitHub required checks) at head `de10c88`

All three required checks **SUCCESS** (watched to completion inline this turn):
- `quality (3.10)` pass
- `quality (3.11)` pass
- `quality (3.12)` pass

Final `gh pr view 65`: state `OPEN`, baseRefName `rebuild/auto-bioinfo-core`,
headRefOid `de10c8804cbddf5c416fb0dc3ecf6c7f27df9d35`, mergeable `MERGEABLE`,
mergeStateStatus `CLEAN`.

## Hard-stop / safety statement

- R0-02 was **not** started; nothing was self-merged.
- No merge, push, or force-push to `main` or `rebuild/auto-bioinfo-core`; PR opened
  against the protected base only.
- No HARD STOP was crossed: no real human-source data, no external LLM/service, no
  paid services, no public deploy, no destructive op, no bot-credential expansion.
- No coordination-system/ruleset/branch-protection/secret/dependency/CI/Docker
  change. Implementation and tests use synthetic in-memory facts only — no real
  network, no real secret material, no persistence, no clock, no subprocess, no new
  dependency.
- Self-reported green is self-reported only; this is not a claim of CEO acceptance
  or OPS-00 PASS.

Handing back to Codex to review PR #65 and decide next (merge / changes / next WO).
