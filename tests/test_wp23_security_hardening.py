"""Unit tests for the WP-23 security-hardening policy layer.

Covers, over synthetic in-memory facts only (no real network, no real secret
material, no persistence, no clock):

- egress allowlist: an allowed host/protocol/port/task-type is permitted; an
  unauthorised host / protocol / port / task-type is denied; adversarial URIs
  (embedded credentials, IP literals, path-bearing hosts) fail closed;
- secret references: a well-formed opaque reference is accepted and never
  resolves to material; a payload carrying plaintext secrets (sensitive key,
  bearer token, private-key block, high-entropy blob, connection-string creds) is
  reported and blocked; a payload of bare references stays clean;
- data-egress policy: artifact sensitivity inherits the max input; a downgrade
  needs approval; restricted fields do not cross a boundary; a retained object
  cannot be deleted without a lawful tombstone;
- RBAC hardening: least-privilege capability matrix; self-approval / self-review
  blocked; cross-project access blocked; audit-log write always denied; sensitive
  audit read is admin-only; the hardened layer is only ever stricter than the base
  RBAC contract;
- determinism: identical inputs yield identical projections; inputs are not
  mutated.
"""

import copy
import socket
import unittest

from auto_bioinfo.control_plane.auth_rbac import (
    AccessRequest,
    AuthorizationPolicy,
    Permission,
    Principal,
    ResourceRef,
    Role,
)
from auto_bioinfo.security import data_egress_policy as dep
from auto_bioinfo.security import domain_allowlist as da
from auto_bioinfo.security import rbac_hardening as rh
from auto_bioinfo.security import secret_reference as sr


def _sample_policy() -> da.EgressPolicy:
    return da.build_policy(
        [
            da.EgressRule(
                host="eutils.ncbi.nlm.nih.gov",
                protocols=frozenset({da.PROTOCOL_HTTPS}),
                ports=frozenset({443}),
                task_types=frozenset({"dataset_discovery"}),
                allow_subdomains=False,
            ),
            da.EgressRule(
                host="ebi.ac.uk",
                protocols=frozenset({da.PROTOCOL_HTTPS}),
                ports=frozenset({443}),
                task_types=frozenset({"dataset_discovery", "literature"}),
                allow_subdomains=True,
            ),
        ]
    )


class EgressAllowlistTests(unittest.TestCase):
    def test_allowed_destination(self):
        d = da.evaluate_egress(
            da.EgressRequest(host="eutils.ncbi.nlm.nih.gov", protocol="https", port=443, task_type="dataset_discovery"),
            _sample_policy(),
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason_code, da.CODE_ALLOW)

    def test_subdomain_only_when_opted_in(self):
        allowed = da.evaluate_egress(
            da.EgressRequest(host="www.ebi.ac.uk", protocol="https", port=443, task_type="literature"),
            _sample_policy(),
        )
        self.assertTrue(allowed.allowed)
        # ncbi rule does not allow subdomains
        denied = da.evaluate_egress(
            da.EgressRequest(host="sub.eutils.ncbi.nlm.nih.gov", protocol="https", port=443, task_type="dataset_discovery"),
            _sample_policy(),
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason_code, da.CODE_NO_MATCHING_RULE)

    def test_unauthorized_host_denied(self):
        d = da.evaluate_egress(
            da.EgressRequest(host="evil.example.com", protocol="https", port=443, task_type="dataset_discovery"),
            _sample_policy(),
        )
        self.assertEqual(d.status, da.STATUS_DENY)
        self.assertEqual(d.reason_code, da.CODE_NO_MATCHING_RULE)

    def test_protocol_port_task_denied(self):
        p = _sample_policy()
        proto = da.evaluate_egress(da.EgressRequest("eutils.ncbi.nlm.nih.gov", "http", 443, "dataset_discovery"), p)
        # http is a known protocol but the rule only permits https -> not allowed
        self.assertEqual(proto.reason_code, da.CODE_PROTOCOL_NOT_ALLOWED)
        # a genuinely unknown scheme fails closed as malformed
        unknown = da.evaluate_egress(da.EgressRequest("eutils.ncbi.nlm.nih.gov", "ftp", 443, "dataset_discovery"), p)
        self.assertEqual(unknown.reason_code, da.CODE_MALFORMED_PROTOCOL)
        port = da.evaluate_egress(da.EgressRequest("eutils.ncbi.nlm.nih.gov", "https", 8080, "dataset_discovery"), p)
        self.assertEqual(port.reason_code, da.CODE_PORT_NOT_ALLOWED)
        task = da.evaluate_egress(da.EgressRequest("eutils.ncbi.nlm.nih.gov", "https", 443, "model_upload"), p)
        self.assertEqual(task.reason_code, da.CODE_TASK_TYPE_NOT_ALLOWED)

    def test_adversarial_uris_fail_closed(self):
        p = _sample_policy()
        creds = da.evaluate_egress(da.EgressRequest("user:pass@ebi.ac.uk", "https", 443, "literature"), p)
        self.assertEqual(creds.reason_code, da.CODE_EMBEDDED_CREDENTIALS)
        ip = da.evaluate_egress(da.EgressRequest("127.0.0.1", "https", 443, "literature"), p)
        self.assertEqual(ip.reason_code, da.CODE_IP_LITERAL_HOST)
        path = da.evaluate_egress(da.EgressRequest("ebi.ac.uk/../etc/passwd", "https", 443, "literature"), p)
        self.assertEqual(path.reason_code, da.CODE_MALFORMED_HOST)

    def test_malformed_request_and_policy(self):
        self.assertEqual(da.evaluate_egress(object(), _sample_policy()).reason_code, da.CODE_MALFORMED_REQUEST)
        self.assertEqual(
            da.evaluate_egress(da.EgressRequest("ebi.ac.uk", "https", 443, "literature"), object()).reason_code,
            da.CODE_MALFORMED_POLICY,
        )

    def test_deterministic_and_no_network(self):
        req = da.EgressRequest("ebi.ac.uk", "https", 443, "literature")
        p = _sample_policy()
        orig = socket.socket
        try:
            socket.socket = None  # any socket use would explode
            a = da.evaluate_egress(req, p).to_dict()
            b = da.evaluate_egress(req, p).to_dict()
        finally:
            socket.socket = orig
        self.assertEqual(a, b)

    def test_status_and_reason_bounded(self):
        d = da.evaluate_egress(da.EgressRequest("ebi.ac.uk", "https", 443, "literature"), _sample_policy())
        self.assertIn(d.status, da.STATUSES)
        self.assertIn(d.reason_code, da.REASON_CODES)


class SecretReferenceTests(unittest.TestCase):
    def test_valid_reference(self):
        ref = sr.SecretReference(ref="secret://vault/ncbi-api-key")
        self.assertTrue(ref.is_valid)
        self.assertEqual(ref.scheme, "secret")
        handle = sr.resolve_reference(ref)
        self.assertFalse(handle["resolved"])
        self.assertNotIn("value", handle)  # never material

    def test_reject_non_reference(self):
        with self.assertRaises(sr.SecretReferenceError):
            sr.resolve_reference("just-a-plain-string")

    def test_clean_payload_of_references(self):
        payload = {"api_key": "secret://vault/key", "description": "public info", "nested": {"token": "vault://team/t1"}}
        result = sr.scan_payload_for_secrets(payload)
        self.assertTrue(result.clean)

    def test_sensitive_key_plaintext_flagged(self):
        payload = {"api_key": "plainlookingvalue123", "note": "ok"}
        result = sr.scan_payload_for_secrets(payload)
        self.assertFalse(result.clean)
        self.assertIn(sr.FINDING_SENSITIVE_KEY_PLAINTEXT, result.kinds())

    def test_inline_secret_shapes_flagged(self):
        bearer = sr.scan_payload_for_secrets({"h": "Authorization: Bearer abcdef123456ZZZ"})
        self.assertIn(sr.FINDING_INLINE_BEARER, bearer.kinds())
        pem = sr.scan_payload_for_secrets(["-----BEGIN RSA PRIVATE KEY-----"])
        self.assertIn(sr.FINDING_PRIVATE_KEY_BLOCK, pem.kinds())
        conn = sr.scan_payload_for_secrets({"db": "postgres://u:p@host/db"})
        self.assertIn(sr.FINDING_CONNECTION_STRING_CREDENTIALS, conn.kinds())

    def test_high_entropy_token_flagged(self):
        # a synthetic high-entropy blob (not a real secret) under a non-sensitive key
        blob = "Zk3Qx9Lm2Pq7Rt5Wv8Yb1Nc4Hd6Jf0Ag"
        result = sr.scan_payload_for_secrets({"opaque": blob})
        self.assertIn(sr.FINDING_HIGH_ENTROPY_TOKEN, result.kinds())

    def test_assert_no_plaintext_secret_raises_and_hides_value(self):
        try:
            sr.assert_no_plaintext_secret({"password": "hunter2plaintext"})
        except sr.SecretReferenceError as exc:
            self.assertNotIn("hunter2plaintext", str(exc))
        else:
            self.fail("expected SecretReferenceError")

    def test_findings_never_echo_value(self):
        result = sr.scan_payload_for_secrets({"h": "Bearer supersecrettoken12345"})
        for f in result.findings:
            self.assertNotIn("supersecrettoken12345", f.to_dict()["detail"])


class DataEgressPolicyTests(unittest.TestCase):
    def test_artifact_inherits_max_sensitivity(self):
        d = dep.inherit_artifact_sensitivity([dep.SENSITIVITY_PUBLIC, dep.SENSITIVITY_RESTRICTED, dep.SENSITIVITY_INTERNAL])
        self.assertTrue(d.allowed)
        self.assertEqual(d.level, dep.SENSITIVITY_RESTRICTED)

    def test_high_sensitive_input_cannot_auto_public(self):
        d = dep.inherit_artifact_sensitivity([dep.SENSITIVITY_SECRET])
        self.assertEqual(d.level, dep.SENSITIVITY_SECRET)
        self.assertNotEqual(d.level, dep.SENSITIVITY_PUBLIC)

    def test_downgrade_needs_approval(self):
        needs = dep.evaluate_downgrade(dep.SENSITIVITY_RESTRICTED, dep.SENSITIVITY_PUBLIC)
        self.assertEqual(needs.status, dep.STATUS_NEEDS_APPROVAL)
        ok = dep.evaluate_downgrade(dep.SENSITIVITY_RESTRICTED, dep.SENSITIVITY_PUBLIC, approval_granted=True)
        self.assertTrue(ok.allowed)
        up = dep.evaluate_downgrade(dep.SENSITIVITY_PUBLIC, dep.SENSITIVITY_RESTRICTED)
        self.assertEqual(up.reason_code, dep.CODE_NOT_A_DOWNGRADE)

    def test_external_send_blocks_restricted(self):
        fields = [
            dep.DataField("accession", dep.SENSITIVITY_PUBLIC),
            dep.DataField("donor_id", dep.SENSITIVITY_RESTRICTED, maskable=False),
        ]
        d = dep.evaluate_external_send(fields, destination_max_sensitivity=dep.SENSITIVITY_INTERNAL)
        self.assertFalse(d.allowed)
        self.assertIn("donor_id", d.blocked_fields)
        self.assertEqual(d.payload, {})

    def test_external_send_masks_maskable(self):
        fields = [
            dep.DataField("accession", dep.SENSITIVITY_PUBLIC),
            dep.DataField("email", dep.SENSITIVITY_RESTRICTED, maskable=True),
        ]
        d = dep.evaluate_external_send(fields, destination_max_sensitivity=dep.SENSITIVITY_INTERNAL)
        self.assertTrue(d.allowed)
        self.assertIn("email", d.masked_fields)
        self.assertEqual(d.payload["email"], dep.REDACTED)

    def test_deletion_guard(self):
        free = dep.evaluate_deletion(dep.DeletionRequest("obj1"))
        self.assertTrue(free.allowed)
        retained = dep.evaluate_deletion(dep.DeletionRequest("obj2", has_retained_evidence=True))
        self.assertEqual(retained.reason_code, dep.CODE_DELETE_BLOCKED_RETAINED)
        lawful = dep.evaluate_deletion(
            dep.DeletionRequest("obj2", has_audit_link=True, tombstone={"reason": "gdpr", "approved_by": "admin1", "retained_reference": "audit://e1"})
        )
        self.assertTrue(lawful.allowed)

    def test_malformed_sensitivity(self):
        self.assertEqual(dep.inherit_artifact_sensitivity(["NOPE"]).reason_code, dep.CODE_MALFORMED)
        self.assertEqual(dep.evaluate_downgrade("A", "B").reason_code, dep.CODE_MALFORMED)


class RbacHardeningTests(unittest.TestCase):
    def test_capability_matrix_least_privilege(self):
        self.assertTrue(rh.evaluate_capability([rh.ROLE_RESEARCHER], rh.CAP_SUBMIT).allowed)
        # researcher cannot review
        self.assertEqual(rh.evaluate_capability([rh.ROLE_RESEARCHER], rh.CAP_REVIEW).reason_code, rh.CODE_MISSING_CAPABILITY)
        self.assertTrue(rh.evaluate_capability([rh.ROLE_REVIEWER], rh.CAP_APPROVE).allowed)

    def test_self_approval_blocked(self):
        p = Principal(actor_id="alice", roles=("reviewer",))
        sub = rh.SubmissionRef(submission_id="s1", author_id="alice", project="proj1")
        d = rh.evaluate_separation_of_duties(p, rh.CAP_APPROVE, sub)
        self.assertEqual(d.reason_code, rh.CODE_SELF_APPROVAL)

    def test_self_review_blocked(self):
        p = Principal(actor_id="bob", roles=("reviewer",))
        sub = rh.SubmissionRef(submission_id="s2", author_id="bob", project="proj1")
        self.assertEqual(rh.evaluate_separation_of_duties(p, rh.CAP_REVIEW, sub).reason_code, rh.CODE_SELF_REVIEW)

    def test_review_of_others_allowed(self):
        p = Principal(actor_id="carol", roles=("reviewer",))
        sub = rh.SubmissionRef(submission_id="s3", author_id="dave", project="proj1")
        self.assertTrue(rh.evaluate_separation_of_duties(p, rh.CAP_REVIEW, sub).allowed)

    def test_cross_project_blocked(self):
        self.assertEqual(rh.evaluate_cross_project("projA", "projB").reason_code, rh.CODE_CROSS_PROJECT)
        self.assertTrue(rh.evaluate_cross_project("projA", "projA").allowed)

    def test_audit_write_always_immutable(self):
        self.assertEqual(rh.evaluate_audit_access([rh.ROLE_ADMIN], rh.AUDIT_WRITE).reason_code, rh.CODE_AUDIT_IMMUTABLE)

    def test_sensitive_audit_admin_only(self):
        self.assertEqual(rh.evaluate_audit_access([rh.ROLE_RESEARCHER], rh.AUDIT_READ_SENSITIVE).reason_code, rh.CODE_AUDIT_NOT_PRIVILEGED)
        self.assertTrue(rh.evaluate_audit_access([rh.ROLE_ADMIN], rh.AUDIT_READ_SENSITIVE).allowed)
        self.assertTrue(rh.evaluate_audit_access([rh.ROLE_RESEARCHER], rh.AUDIT_READ).allowed)

    def test_hardened_access_only_stricter_than_base(self):
        policy = AuthorizationPolicy(
            roles=(Role(name="operator", permissions=(Permission(action="operation.cancel", effect="allow", project="proj1"),)),),
        )
        req = AccessRequest(
            principal=Principal(actor_id="op1", roles=("operator",)),
            action="operation.cancel",
            resource=ResourceRef(resource_type="operation", project="proj1"),
        )
        same = rh.evaluate_hardened_access(req, policy=policy, actor_project="proj1")
        self.assertTrue(same.allowed)
        cross = rh.evaluate_hardened_access(req, policy=policy, actor_project="proj2")
        self.assertEqual(cross.reason_code, rh.CODE_CROSS_PROJECT)

    def test_hardened_carries_base_denial(self):
        policy = AuthorizationPolicy(roles=(Role(name="operator", permissions=()),))
        req = AccessRequest(
            principal=Principal(actor_id="op1", roles=("operator",)),
            action="operation.cancel",
            resource=ResourceRef(resource_type="operation", project="proj1"),
        )
        d = rh.evaluate_hardened_access(req, policy=policy, actor_project="proj1")
        self.assertEqual(d.reason_code, rh.CODE_BASE_NOT_ALLOWED)

    def test_inputs_not_mutated(self):
        p = Principal(actor_id="alice", roles=("reviewer",))
        sub = rh.SubmissionRef(submission_id="s1", author_id="bob", project="proj1")
        before = copy.deepcopy((p, sub))
        rh.evaluate_separation_of_duties(p, rh.CAP_REVIEW, sub)
        self.assertEqual(before, (p, sub))


if __name__ == "__main__":
    unittest.main()
