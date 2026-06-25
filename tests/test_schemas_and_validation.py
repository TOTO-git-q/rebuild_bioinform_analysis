import unittest

from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.core.schemas import CLAIM_LEVELS, ResearchSpec
from auto_bioinfo.core import validation


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


if __name__ == "__main__":
    unittest.main()
