"""WP-09 resource verification + metadata factualisation tests (T-09-01..12)."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_dataset_profile
from auto_bioinfo.resources.verification import (
    ACCESS_RESTRICTED,
    INCOMPLETE,
    LICENSE_NEED_MORE_INFORMATION,
    REJECTED,
    VERIFIED,
    AnnotationSourceProfile,
    PaperProfile,
    RegistryRecord,
    VerificationRegistry,
    apply_human_correction,
    classify_license,
    dataset_completeness,
    parse_dataset_metadata,
    verify_candidate,
    verify_paper_dataset_relation,
)

FULL_META = {
    "organism": "human",
    "tissue": "liver",
    "platform": "GPL11154",
    "modality": "bulk RNA-seq",
    "disease": "hepatocellular carcinoma",
    "age": "55",
    "sex": "F",
    "batch": "b1",
    "species": ["human"],
    "samples": [
        {"sample_id": "S1", "group": "tumor", "donor_id": "D1"},
        {"sample_id": "S2", "group": "tumor", "donor_id": "D2"},
        {"sample_id": "S3", "group": "normal", "donor_id": "D3"},
        {"sample_id": "S4", "group": "normal"},  # donor unstated
    ],
    "files": [{"name": "counts.tsv", "file_type": "counts", "downloadable": True, "size_bytes": 2048}],
}


def _dataset_candidate(namespace="GEO", identifier="GSE111111"):
    return {
        "namespace": namespace,
        "identifier": identifier,
        "accession": identifier,
        "discovery_domain": "dataset",
        "resource_type": "dataset_candidate",
        "resource_name": "x",
    }


class ParseMetadataTests(unittest.TestCase):
    def test_fields_carry_source_and_confidence(self):
        parsed = parse_dataset_metadata(FULL_META)
        self.assertEqual(parsed["fields"]["organism"], {"value": "human", "source_location": "metadata.organism", "confidence": 1.0})
        self.assertIn("intervention", parsed["missing_fields"])

    def test_missing_donor_is_explicit_unknown_not_guessed(self):
        parsed = parse_dataset_metadata(FULL_META)
        s4 = next(s for s in parsed["samples"] if s["sample_id"] == "S4")
        self.assertEqual(s4["donor_id"], "unknown")
        self.assertFalse(s4["donor_known"])

    def test_file_visibility_separate_from_downloadability(self):
        parsed = parse_dataset_metadata({"files": [{"name": "raw.fastq", "downloadable": False}]})
        f = parsed["files"][0]
        self.assertTrue(f["visible"])
        self.assertFalse(f["downloadable"])

    def test_parse_is_deterministic_golden(self):
        self.assertEqual(parse_dataset_metadata(FULL_META), parse_dataset_metadata(FULL_META))


class VerifyDatasetTests(unittest.TestCase):
    def test_verified_dataset_profile_is_valid(self):
        reg = VerificationRegistry(
            {("GEO", "GSE111111"): RegistryRecord(existence="exists", raw_metadata=FULL_META, source_uri="u", access="open", license="CC-BY")}
        )
        vr = verify_candidate(_dataset_candidate(), reg)
        self.assertEqual(vr.verdict, VERIFIED)
        self.assertEqual(vr.record["verification_level"], "METADATA_VERIFIED")
        self.assertEqual(validate_dataset_profile(vr.profile), [])
        self.assertTrue(vr.record["raw_metadata_checksum"])  # T-09-02

    def test_candidate_without_identifier_never_verified(self):
        reg = VerificationRegistry({})
        vr = verify_candidate({"namespace": "", "identifier": "", "discovery_domain": "dataset"}, reg)
        self.assertEqual(vr.verdict, REJECTED)
        self.assertEqual(vr.reason_code, "VERIFY_NO_IDENTIFIER")

    def test_not_found_is_rejected(self):
        reg = VerificationRegistry({})
        vr = verify_candidate(_dataset_candidate(identifier="GSE999999"), reg)
        self.assertEqual(vr.verdict, REJECTED)
        self.assertEqual(vr.record["existence_status"], "not_found")

    def test_redirect_is_followed(self):
        reg = VerificationRegistry(
            {
                ("GEO", "GSE_OLD1"): RegistryRecord(existence="redirected", redirect_to={"namespace": "GEO", "identifier": "GSE111111"}),
                ("GEO", "GSE111111"): RegistryRecord(existence="exists", raw_metadata=FULL_META, license="CC-BY", access="open"),
            }
        )
        vr = verify_candidate(_dataset_candidate(identifier="GSE_OLD1"), reg)
        self.assertEqual(vr.verdict, VERIFIED)
        self.assertIsNotNone(vr.record["redirect"])

    def test_access_restricted(self):
        reg = VerificationRegistry({("GEO", "GSE111111"): RegistryRecord(existence="access_restricted", access="controlled")})
        vr = verify_candidate(_dataset_candidate(), reg)
        self.assertEqual(vr.verdict, ACCESS_RESTRICTED)

    def test_incomplete_when_required_fact_missing(self):
        meta = {k: v for k, v in FULL_META.items() if k != "platform"}
        reg = VerificationRegistry({("GEO", "GSE111111"): RegistryRecord(existence="exists", raw_metadata=meta, license="CC-BY", access="open")})
        vr = verify_candidate(_dataset_candidate(), reg)
        self.assertEqual(vr.verdict, INCOMPLETE)
        self.assertIn("missing_required_facts", vr.record)

    def test_controlled_license_makes_access_restricted(self):
        reg = VerificationRegistry({("GEO", "GSE111111"): RegistryRecord(existence="exists", raw_metadata=FULL_META, access="controlled", license="")})
        vr = verify_candidate(_dataset_candidate(), reg)
        self.assertEqual(vr.verdict, ACCESS_RESTRICTED)

    def test_license_need_more_information(self):
        rec = RegistryRecord(existence="exists", raw_metadata=FULL_META, access="open", license="")
        self.assertEqual(classify_license(rec), LICENSE_NEED_MORE_INFORMATION)

    def test_completeness_score_advisory_only(self):
        reg = VerificationRegistry({("GEO", "GSE111111"): RegistryRecord(existence="exists", raw_metadata=FULL_META, license="CC-BY", access="open")})
        vr = verify_candidate(_dataset_candidate(), reg)
        score = dataset_completeness(vr.profile)
        self.assertFalse(score["authoritative"])
        self.assertGreater(score["score"], 0.0)


class VerifyPaperTests(unittest.TestCase):
    def test_paper_verified_with_identifier(self):
        reg = VerificationRegistry(
            {("PMID", "12345678"): RegistryRecord(existence="exists", raw_metadata={"title": "A study"}, evidence_type="expression_association")}
        )
        cand = {"namespace": "PMID", "identifier": "12345678", "discovery_domain": "literature", "resource_type": "paper_candidate", "resource_name": "A study"}
        vr = verify_candidate(cand, reg)
        self.assertEqual(vr.verdict, VERIFIED)
        self.assertEqual(vr.profile["evidence_type"], "expression_association")

    def test_mechanism_not_overstated_without_recorded_assay(self):
        reg = VerificationRegistry(
            {
                ("PMID", "12345678"): RegistryRecord(
                    existence="exists", raw_metadata={"title": "t"}, evidence_type="mechanistic", experimental_assay_recorded=False
                )
            }
        )
        cand = {"namespace": "PMID", "identifier": "12345678", "discovery_domain": "literature"}
        vr = verify_candidate(cand, reg)
        self.assertEqual(vr.profile["evidence_type"], "expression_association")  # downgraded
        self.assertIn("evidence_downgrade", vr.record)

    def test_mechanism_kept_with_recorded_assay(self):
        reg = VerificationRegistry(
            {
                ("PMID", "12345678"): RegistryRecord(
                    existence="exists", raw_metadata={"title": "t"}, evidence_type="mechanistic", experimental_assay_recorded=True
                )
            }
        )
        cand = {"namespace": "PMID", "identifier": "12345678", "discovery_domain": "literature"}
        vr = verify_candidate(cand, reg)
        self.assertEqual(vr.profile["evidence_type"], "mechanistic")

    def test_paper_profile_id_deterministic(self):
        p = PaperProfile(paper_id="", namespace="PMID", identifier="1").to_dict()
        p2 = PaperProfile(paper_id="", namespace="PMID", identifier="1").to_dict()
        self.assertEqual(p["paper_id"], p2["paper_id"])


class VerifyAnnotationTests(unittest.TestCase):
    def test_annotation_missing_version_limits_reproduction(self):
        reg = VerificationRegistry(
            {("GO", "GO:0006915"): RegistryRecord(existence="exists", raw_metadata={"name": "apoptosis"}, version="", entity_scope=["gene"])}
        )
        cand = {"namespace": "GO", "identifier": "GO:0006915", "discovery_domain": "annotation", "resource_type": "annotation_candidate"}
        vr = verify_candidate(cand, reg)
        self.assertEqual(vr.verdict, INCOMPLETE)
        self.assertTrue(vr.profile["reproduction_limited"])

    def test_annotation_verified_with_version_and_scope(self):
        reg = VerificationRegistry(
            {
                ("GO", "GO:0006915"): RegistryRecord(
                    existence="exists", raw_metadata={"name": "apoptosis"}, version="2024-01", entity_scope=["gene"], evidence_tier="curated"
                )
            }
        )
        cand = {"namespace": "GO", "identifier": "GO:0006915", "discovery_domain": "annotation"}
        vr = verify_candidate(cand, reg)
        self.assertEqual(vr.verdict, VERIFIED)
        self.assertEqual(vr.profile["evidence_tier"], "curated")

    def test_annotation_default_tier_not_experimental(self):
        p = AnnotationSourceProfile(annotation_source_id="", namespace="GO", identifier="x").to_dict()
        self.assertNotEqual(p["evidence_tier"], "experimentally_validated")


class RelationTests(unittest.TestCase):
    def test_title_similarity_alone_is_unsupported(self):
        paper = RegistryRecord(existence="exists", declared_relations=[])
        out = verify_paper_dataset_relation(paper, ("GEO", "GSE111111"), title_similarity=0.99)
        self.assertEqual(out["status"], "unsupported")

    def test_declared_cross_reference_verified(self):
        paper = RegistryRecord(existence="exists", declared_relations=[{"namespace": "GEO", "identifier": "GSE111111"}])
        out = verify_paper_dataset_relation(paper, ("geo", "gse111111"), title_similarity=0.1)
        self.assertEqual(out["status"], "verified")


class HumanCorrectionTests(unittest.TestCase):
    def test_correction_preserves_original_and_bumps_version(self):
        profile = {"tissue": "liver", "profile_version": 1}
        updated = apply_human_correction(profile, field_name="tissue", corrected_value="hepatocyte", evidence="curator note", actor="human:alice")
        self.assertEqual(updated["tissue"], "hepatocyte")
        self.assertEqual(updated["profile_version"], 2)
        self.assertEqual(updated["corrections"][0]["original_tool_value"], "liver")
        self.assertEqual(profile["tissue"], "liver")  # original not mutated

    def test_correction_requires_evidence_and_actor(self):
        with self.assertRaises(ValueError):
            apply_human_correction({"tissue": "liver"}, field_name="tissue", corrected_value="x", evidence="", actor="human")
        with self.assertRaises(ValueError):
            apply_human_correction({"tissue": "liver"}, field_name="tissue", corrected_value="x", evidence="note", actor="")


if __name__ == "__main__":
    unittest.main()
