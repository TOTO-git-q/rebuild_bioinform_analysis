import unittest

from auto_bioinfo.core import common, validation
from auto_bioinfo.core.common import Actor, ExternalIdentifier, SchemaValidationError, dataclass_json_schema
from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.core.schemas import (
    CLAIM_LEVELS,
    ApprovalDecision,
    ApprovalRequest,
    OriginalRequest,
    Project,
    ProjectPolicy,
    ResearchSpec,
)


class SchemaTest(unittest.TestCase):
    def test_stable_id_is_deterministic_and_content_addressed(self):
        a = make_stable_id("x", {"k": 1, "j": 2})
        b = make_stable_id("x", {"j": 2, "k": 1})  # key order must not matter
        self.assertEqual(a, b)
        self.assertNotEqual(a, make_stable_id("x", {"k": 1, "j": 3}))

    def test_research_spec_roundtrip_and_id(self):
        spec = ResearchSpec(research_question="q", project_id="p", organism="human").to_dict()
        self.assertTrue(spec["research_spec_id"].startswith("research_spec_"))
        self.assertEqual(spec["organism"], "human")
        self.assertEqual(spec["claim_ceiling"], "association")


class ValidationGuardrailTest(unittest.TestCase):
    def test_verified_dataset_cannot_be_mock(self):
        bad = {"verified": True, "source_status": "mock_placeholder", "accession": "AUTO_X"}
        self.assertTrue(validation.validate_no_unknown_verified_dataset(bad))
        good = {"verified": True, "source_status": "committed_fixture", "accession": "FIXTURE-1"}
        self.assertEqual(validation.validate_no_unknown_verified_dataset(good), [])

    def test_claim_ceiling_blocks_overclaim(self):
        self.assertTrue(validation.validate_claim_ceiling({"claim_level": "causal_support"}, "association"))
        self.assertEqual(validation.validate_claim_ceiling({"claim_level": "association"}, "association"), [])

    def test_claim_levels_are_ordered(self):
        self.assertEqual(CLAIM_LEVELS[0], "descriptive")
        self.assertLess(CLAIM_LEVELS.index("association"), CLAIM_LEVELS.index("causal_support"))


# --- WP-02a / T-02-01: common cross-cutting contract types -------------------


class CommonContractTypesTest(unittest.TestCase):
    """T-02-01: deterministic serialisation + explicit failure for IDs, schema
    versions, actors, timestamps, hashes, and external identifiers."""

    def test_canonical_json_is_deterministic_and_key_order_independent(self):
        self.assertEqual(common.canonical_json({"b": 1, "a": 2}), common.canonical_json({"a": 2, "b": 1}))
        self.assertEqual(common.canonical_json({"a": 2, "b": 1}), '{"a":2,"b":1}')
        self.assertEqual(common.content_hash({"a": 1}), common.content_hash({"a": 1}))

    def test_identifier_validation_positive_and_negative(self):
        self.assertEqual(common.validate_identifier("research_spec_ab12cd34"), [])
        self.assertEqual(common.validate_identifier("project.v1-2"), [])
        self.assertTrue(common.validate_identifier(""))  # empty
        self.assertTrue(common.validate_identifier("has space"))  # whitespace
        self.assertTrue(common.validate_identifier("UPPER"))  # not lowercase token
        self.assertTrue(common.validate_identifier(123))  # not a string

    def test_schema_version_validation(self):
        self.assertEqual(common.validate_schema_version("v5.canonical/0.1"), [])
        self.assertTrue(common.validate_schema_version("5.canonical.0.1"))  # malformed
        self.assertTrue(common.validate_schema_version(""))

    def test_hash_validation_requires_64_lowercase_hex(self):
        good = common.content_hash({"x": 1})
        self.assertEqual(common.validate_hash(good), [])
        self.assertTrue(common.validate_hash("ABC"))  # too short / uppercase
        self.assertTrue(common.validate_hash(good.upper()))  # uppercase rejected
        self.assertTrue(common.validate_hash(""))

    def test_timestamp_validation_requires_timezone(self):
        self.assertEqual(common.validate_timestamp("2026-06-26T12:00:00+00:00"), [])
        self.assertTrue(common.validate_timestamp("2026-06-26T12:00:00"))  # naive, no offset
        self.assertTrue(common.validate_timestamp("not-a-time"))
        self.assertTrue(common.validate_timestamp(""))

    def test_actor_validation_and_explicit_raise(self):
        ok = Actor(actor_type="human", actor_id="alice")
        self.assertEqual(ok.errors(), [])
        ok.validate()  # does not raise
        self.assertTrue(Actor(actor_type="robot", actor_id="x").errors())  # bad type
        self.assertTrue(Actor(actor_type="human", actor_id="").errors())  # empty id
        with self.assertRaises(SchemaValidationError):
            Actor(actor_type="robot", actor_id="").validate()

    def test_external_identifier_format_verifiability(self):
        self.assertEqual(ExternalIdentifier(scheme="PMID", value="123456").errors(), [])
        self.assertEqual(ExternalIdentifier(scheme="GEO", value="GSE12345").errors(), [])
        self.assertEqual(ExternalIdentifier(scheme="DOI", value="10.1000/xyz123").errors(), [])
        # boundary: shortest valid PMID
        self.assertEqual(ExternalIdentifier(scheme="PMID", value="1").errors(), [])
        # negative: value does not match scheme -> unverifiable
        self.assertTrue(ExternalIdentifier(scheme="PMID", value="GSE1").errors())
        self.assertTrue(ExternalIdentifier(scheme="UNKNOWN", value="x").errors())

    def test_external_identifier_verified_requires_source(self):
        self.assertTrue(ExternalIdentifier(scheme="PMID", value="123", verified=True).errors())
        self.assertEqual(
            ExternalIdentifier(scheme="PMID", value="123", verified=True, verification_source="eutils").errors(),
            [],
        )


# --- WP-02a / T-02-02: Project & Policy and Approval contracts ---------------


class OriginalRequestContractTest(unittest.TestCase):
    def _req(self, **kw):
        base = dict(project_id="proj_1", original_text="Find DEGs in GSE12345 between treated and control.")
        base.update(kw)
        return OriginalRequest(**base)

    def test_original_text_is_hash_bound_and_id_stable(self):
        data = self._req().to_dict()
        self.assertTrue(data["request_id"].startswith("original_request_"))
        self.assertEqual(data["original_text_sha256"], common.content_hash(data["original_text"]))
        self.assertEqual(validation.validate_original_request(data), [])

    def test_normalization_does_not_overwrite_original(self):
        req = self._req()
        normalized = req.with_normalized_text("normalized question")
        self.assertEqual(normalized["original_text"], req.original_text)
        self.assertEqual(normalized["normalized_text"], "normalized question")
        # the hash still tracks the original, and validation still passes
        self.assertEqual(normalized["original_text_sha256"], common.content_hash(req.original_text))
        self.assertEqual(validation.validate_original_request(normalized), [])

    def test_tampered_original_text_is_detected(self):
        data = self._req().to_dict()
        data["original_text"] = "SOMETHING ELSE"  # edit the original, leave the hash stale
        errors = validation.validate_original_request(data)
        self.assertTrue(any("does not match original_text" in e for e in errors))

    def test_empty_original_text_fails(self):
        data = self._req(original_text="").to_dict()
        self.assertTrue(validation.validate_original_request(data))


class ProjectPolicyContractTest(unittest.TestCase):
    def _policy(self, **kw):
        base = dict(project_id="proj_1", execution_mode="DEMO", automation_level="A1")
        base.update(kw)
        return ProjectPolicy(**base)

    def test_policy_is_content_hashable_and_stable_id(self):
        a = self._policy().to_dict()
        b = self._policy().to_dict()
        self.assertEqual(a["project_policy_id"], b["project_policy_id"])
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertTrue(a["project_policy_id"].startswith("project_policy_"))
        self.assertEqual(validation.validate_project_policy(a), [])

    def test_policy_validates_binding_mode_and_version(self):
        self.assertTrue(validation.validate_project_policy(self._policy(execution_mode="BOGUS").to_dict()))
        self.assertTrue(validation.validate_project_policy(self._policy(automation_level="A9").to_dict()))
        self.assertTrue(validation.validate_project_policy(self._policy(policy_version=0).to_dict()))
        self.assertTrue(validation.validate_project_policy(self._policy(project_id="").to_dict()))

    def test_tampered_policy_breaks_hash_and_id(self):
        data = self._policy().to_dict()
        data["execution_mode"] = "REAL"  # flip mode, leave hash/id stale
        errors = validation.validate_project_policy(data)
        self.assertTrue(any("content_hash" in e for e in errors))
        self.assertTrue(any("project_policy_id" in e for e in errors))

    def test_boundary_lowest_and_highest_automation_levels(self):
        self.assertEqual(validation.validate_project_policy(self._policy(automation_level="A0").to_dict()), [])
        self.assertEqual(validation.validate_project_policy(self._policy(automation_level="A3").to_dict()), [])


class ApprovalContractTest(unittest.TestCase):
    def _request(self, **kw):
        base = dict(project_id="proj_1", subject_type="ResearchSpec", subject_id="rs_1", subject_version=2, gate="G-Q")
        base.update(kw)
        return ApprovalRequest(**base)

    def _decision(self, request_dict, **kw):
        base = dict(
            approval_request_id=request_dict["approval_request_id"],
            project_id=request_dict["project_id"],
            subject_type=request_dict["subject_type"],
            subject_id=request_dict["subject_id"],
            subject_version=request_dict["subject_version"],
            decision="approved",
        )
        base.update(kw)
        return ApprovalDecision(**base)

    def test_request_binds_subject_version(self):
        data = self._request().to_dict()
        self.assertTrue(data["approval_request_id"].startswith("approval_request_"))
        self.assertEqual(validation.validate_approval_request(data), [])
        self.assertTrue(validation.validate_approval_request(self._request(subject_version=0).to_dict()))
        self.assertTrue(validation.validate_approval_request(self._request(state="bogus").to_dict()))

    def test_decision_must_bind_exact_subject(self):
        req = self._request().to_dict()
        good = self._decision(req).to_dict()
        self.assertEqual(validation.validate_approval_decision(good, request=req), [])
        # decision pointing at a different version is rejected against the request
        bad = self._decision(req, subject_version=1).to_dict()
        errors = validation.validate_approval_decision(bad, request=req)
        self.assertTrue(any("same subject" in e for e in errors))

    def test_decision_enum_and_version_validation(self):
        req = self._request().to_dict()
        self.assertTrue(validation.validate_approval_decision(self._decision(req, decision="maybe").to_dict()))
        self.assertTrue(validation.validate_approval_decision(self._decision(req, subject_version=0).to_dict()))

    def test_cannot_approve_superseded_version_as_current(self):
        req = self._request(subject_version=2).to_dict()
        decision = self._decision(req).to_dict()  # approves version 2
        # current is version 3 -> approving the superseded v2 as current is blocked
        errors = validation.validate_approval_decision(decision, request=req, current_version=3)
        self.assertTrue(any("superseded" in e for e in errors))
        # approving the current version is fine
        self.assertEqual(validation.validate_approval_decision(decision, request=req, current_version=2), [])


class SchemaSnapshotTest(unittest.TestCase):
    """JSON-schema snapshot coverage for the WP-02a slice using the stdlib-only
    project helper (no new dependency)."""

    def test_required_fields_snapshot_is_stable(self):
        expected_required = {
            Project: ["project_id", "title"],
            OriginalRequest: ["project_id", "original_text"],
            ProjectPolicy: ["project_id", "execution_mode"],
            ApprovalRequest: ["project_id", "subject_type", "subject_id", "subject_version", "gate"],
            ApprovalDecision: ["approval_request_id", "project_id", "subject_type", "subject_id", "subject_version", "decision"],
        }
        for cls, required in expected_required.items():
            schema = dataclass_json_schema(cls)
            self.assertEqual(schema["type"], "object")
            self.assertEqual(schema["title"], cls.__name__)
            self.assertEqual(schema["required"], required)
            for name in required:
                self.assertIn(name, schema["properties"])

    def test_property_types_are_derived(self):
        schema = dataclass_json_schema(ProjectPolicy)
        self.assertEqual(schema["properties"]["policy_version"]["type"], "integer")
        self.assertEqual(schema["properties"]["network_policy"]["type"], "object")
        self.assertEqual(schema["properties"]["project_id"]["type"], "string")

    def test_non_dataclass_raises(self):
        with self.assertRaises(SchemaValidationError):
            dataclass_json_schema(int)


if __name__ == "__main__":
    unittest.main()
