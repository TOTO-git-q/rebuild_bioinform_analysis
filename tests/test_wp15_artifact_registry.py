"""WP-15 tests: artifact registration, integrity, and lineage."""

from __future__ import annotations

import unittest

from auto_bioinfo.core.validation import validate_artifact_manifest
from auto_bioinfo.workflow.artifact_registry import (
    FMT_JSON,
    FMT_TSV,
    STATE_INVALID,
    STATE_QUARANTINED,
    STATE_VALID,
    ArtifactRegistry,
    FakeObjectStore,
    OutputFacts,
    detect_format,
    streaming_checksum,
)

_TSV = b"gene\tlog2fc\tfdr\nGENE1\t1.5\t0.01\nGENE2\t-2.0\t0.02\n"


def _facts(output_name="deg_results_table", uri="proj1/outputs/deg.tsv", content=_TSV, **kw):
    base = dict(
        output_name=output_name,
        uri=uri,
        content=content,
        declared_media_type="text/tab-separated-values",
        content_role="result_table",
        producer_task_id="dag_task_analysis",
    )
    base.update(kw)
    return OutputFacts(**base)


class StreamingChecksumTest(unittest.TestCase):
    def test_matches_full_hash(self):
        import hashlib

        checksum, size = streaming_checksum([_TSV[:10], _TSV[10:]])
        self.assertEqual(checksum, hashlib.sha256(_TSV).hexdigest())
        self.assertEqual(size, len(_TSV))

    def test_deterministic(self):
        a = streaming_checksum([_TSV])
        b = streaming_checksum([_TSV])
        self.assertEqual(a, b)


class FormatDetectionTest(unittest.TestCase):
    def test_tsv(self):
        self.assertEqual(detect_format(_TSV), FMT_TSV)

    def test_json(self):
        self.assertEqual(detect_format(b'{"a": 1}'), FMT_JSON)

    def test_png_image(self):
        from auto_bioinfo.workflow.artifact_registry import FMT_IMAGE

        self.assertEqual(detect_format(b"\x89PNG\r\n\x1a\n"), FMT_IMAGE)


class ObjectStoreTest(unittest.TestCase):
    def test_put_get_head_list_presign_delete(self):
        store = FakeObjectStore()
        store.put("a/b.tsv", _TSV)
        self.assertTrue(store.exists("a/b.tsv"))
        self.assertEqual(store.get("a/b.tsv"), _TSV)
        self.assertEqual(store.head("a/b.tsv")["size_bytes"], len(_TSV))
        self.assertEqual(store.list("a/"), ["a/b.tsv"])
        self.assertTrue(store.presign("a/b.tsv"))
        self.assertTrue(store.delete("a/b.tsv"))
        self.assertFalse(store.exists("a/b.tsv"))


class RegistrationStateTest(unittest.TestCase):
    def setUp(self):
        self.reg = ArtifactRegistry()

    def test_clean_output_is_valid_with_manifest(self):
        r = self.reg.register("proj1", _facts(), expected_output_names=["deg_results_table"])
        self.assertEqual(r.state, STATE_VALID)
        self.assertIsNotNone(r.manifest)
        self.assertEqual(validate_artifact_manifest(r.manifest), [])

    def test_empty_file_invalid(self):
        r = self.reg.register("proj1", _facts(content=b""), expected_output_names=["deg_results_table"])
        self.assertEqual(r.state, STATE_INVALID)

    def test_format_mismatch_invalid(self):
        # Declared JSON but content is a TSV table.
        r = self.reg.register("proj1", _facts(declared_media_type="application/json"), expected_output_names=["deg_results_table"])
        self.assertEqual(r.state, STATE_INVALID)

    def test_json_declared_unknown_content_invalid(self):
        # Declared JSON but content is not JSON at all (Blocker 1 regression):
        # a known declared media type over unrecognized content must fail closed.
        r = self.reg.register(
            "proj1",
            _facts(uri="proj1/outputs/report.json", content=b"not json at all", declared_media_type="application/json"),
            expected_output_names=["deg_results_table"],
        )
        self.assertEqual(r.state, STATE_INVALID)

    def test_json_declared_malformed_content_invalid(self):
        # Declared JSON, sniffs as JSON (leading brace) but does not parse.
        r = self.reg.register(
            "proj1",
            _facts(uri="proj1/outputs/report.json", content=b"{not valid json", declared_media_type="application/json"),
            expected_output_names=["deg_results_table"],
        )
        self.assertEqual(r.state, STATE_INVALID)

    def test_json_declared_valid_content_valid(self):
        # A valid JSON object under a JSON declaration still registers VALID.
        r = self.reg.register(
            "proj1",
            _facts(uri="proj1/outputs/report.json", content=b'{"result": true}', declared_media_type="application/json"),
            expected_output_names=["deg_results_table"],
        )
        self.assertEqual(r.state, STATE_VALID)

    def test_tsv_declared_not_a_table_invalid(self):
        # Declared TSV but content has no tab-delimited table (Blocker 1 regression).
        r = self.reg.register(
            "proj1",
            _facts(content=b"just one column no tabs no commas\n"),
            expected_output_names=["deg_results_table"],
        )
        self.assertEqual(r.state, STATE_INVALID)

    def test_tsv_declared_ragged_columns_invalid(self):
        # Declared TSV but rows have inconsistent column counts.
        r = self.reg.register(
            "proj1",
            _facts(content=b"gene\tlog2fc\tfdr\nGENE1\t1.5\n"),
            expected_output_names=["deg_results_table"],
        )
        self.assertEqual(r.state, STATE_INVALID)

    def test_undeclared_output_quarantined(self):
        r = self.reg.register("proj1", _facts(output_name="sneaky"), expected_output_names=["deg_results_table"])
        self.assertEqual(r.state, STATE_QUARANTINED)

    def test_scope_escape_quarantined(self):
        r = self.reg.register("proj1", _facts(relative_path="../escape.tsv", write_scope="outputs/"), expected_output_names=["deg_results_table"])
        self.assertEqual(r.state, STATE_QUARANTINED)

    def test_registration_deterministic(self):
        r1 = self.reg.register("proj1", _facts(), expected_output_names=["deg_results_table"])
        reg2 = ArtifactRegistry()
        r2 = reg2.register("proj1", _facts(), expected_output_names=["deg_results_table"])
        self.assertEqual(r1.to_dict(), r2.to_dict())


class IntegrityReportTest(unittest.TestCase):
    def test_missing_required_output_inadmissible(self):
        reg = ArtifactRegistry()
        reg.register("proj1", _facts(), expected_output_names=["deg_results_table"])
        report = reg.integrity_report({"dag_task_analysis": ["deg_results_table", "missing_extra"]})
        self.assertFalse(report["admissible"])

    def test_all_present_admissible(self):
        reg = ArtifactRegistry()
        reg.register("proj1", _facts(), expected_output_names=["deg_results_table"])
        report = reg.integrity_report({"dag_task_analysis": ["deg_results_table"]})
        self.assertTrue(report["admissible"])


class LineageTest(unittest.TestCase):
    def setUp(self):
        self.reg = ArtifactRegistry()
        # A source table produced by a task.
        self.table = self.reg.register(
            "proj1", _facts(output_name="deg_results_table", uri="proj1/outputs/deg.tsv"), expected_output_names=["deg_results_table"]
        )

    def test_produced_by_and_derived_from_edges(self):
        # A chart derived from the source table.
        chart_content = b"\x89PNG\r\n\x1a\n"
        self.reg.register(
            "proj1",
            _facts(
                output_name="volcano",
                uri="proj1/outputs/volcano.png",
                content=chart_content,
                declared_media_type="image/png",
                content_role="chart",
                source_refs=(self.table.artifact_id,),
            ),
            expected_output_names=["volcano"],
        )
        graph = self.reg.build_lineage(task_inputs={"dag_task_analysis": ["artifact_prep"]})
        self.assertEqual(graph["dangling_edges"], [])
        types = {e["edge_type"] for e in graph["edges"]}
        self.assertIn("produced_by", types)
        self.assertIn("derived_from", types)
        self.assertIn("used_by", types)

    def test_chart_without_source_blocks(self):
        chart_content = b"\x89PNG\r\n\x1a\n"
        self.reg.register(
            "proj1",
            _facts(output_name="orphan_chart", uri="proj1/outputs/orphan.png", content=chart_content, declared_media_type="image/png", content_role="chart"),
            expected_output_names=["orphan_chart"],
        )
        findings = self.reg.lineage_check()
        self.assertTrue(any("no source-table lineage" in f for f in findings))

    def test_missing_source_ref_dangles_and_blocks(self):
        # Blocker 2 regression: a chart whose source ref was never registered must
        # NOT silently become a valid graph node. The derived_from edge must be
        # reported as dangling, and lineage_check must block the chart.
        chart_content = b"\x89PNG\r\n\x1a\n"
        chart = self.reg.register(
            "proj1",
            _facts(
                output_name="ghost_chart",
                uri="proj1/outputs/ghost.png",
                content=chart_content,
                declared_media_type="image/png",
                content_role="chart",
                source_refs=("artifact_missing_source",),
            ),
            expected_output_names=["ghost_chart"],
        )
        graph = self.reg.build_lineage()
        self.assertNotIn("artifact_missing_source", graph["nodes"])
        self.assertTrue(any(e["to_id"] == "artifact_missing_source" and e["edge_type"] == "derived_from" for e in graph["dangling_edges"]))
        findings = self.reg.lineage_check()
        self.assertTrue(any(chart.artifact_id in f and "artifact_missing_source" in f for f in findings))

    def test_registered_source_ref_is_not_dangling(self):
        # A source ref that resolves to a registered artifact is a real node.
        chart_content = b"\x89PNG\r\n\x1a\n"
        self.reg.register(
            "proj1",
            _facts(
                output_name="volcano",
                uri="proj1/outputs/volcano.png",
                content=chart_content,
                declared_media_type="image/png",
                content_role="chart",
                source_refs=(self.table.artifact_id,),
            ),
            expected_output_names=["volcano"],
        )
        graph = self.reg.build_lineage()
        self.assertEqual(graph["dangling_edges"], [])
        self.assertEqual(self.reg.lineage_check(), [])

    def test_export_counts_match(self):
        graph = self.reg.build_lineage()
        json_graph = self.reg.export_lineage("json")
        self.assertEqual(json_graph["edge_count"], graph["edge_count"])
        csv_out = self.reg.export_lineage("csv")
        self.assertIn("edge_type", csv_out)
        gv = self.reg.export_lineage("graphviz")
        self.assertIn("digraph", gv)


class DedupeAndRetentionTest(unittest.TestCase):
    def test_dedupe_keeps_project_boundary(self):
        reg = ArtifactRegistry()
        a = reg.register("proj1", _facts(uri="proj1/outputs/deg.tsv"), expected_output_names=["deg_results_table"])
        b = reg.register("proj2", _facts(uri="proj2/outputs/deg.tsv"), expected_output_names=["deg_results_table"])
        # Same content hash, different projects: canonical is the first; the second
        # is deduped but keeps its own project reference.
        self.assertEqual(a.checksum_sha256, b.checksum_sha256)
        ref_b = reg.logical_reference(b.artifact_id)
        self.assertEqual(ref_b["project_id"], "proj2")
        self.assertTrue(ref_b["deduped"])

    def test_hard_delete_evidence_refused(self):
        reg = ArtifactRegistry()
        r = reg.register("proj1", _facts(content_role="result_table"), expected_output_names=["deg_results_table"])
        result = reg.delete(r.artifact_id, hard=True)
        self.assertFalse(result["deleted"])

    def test_legal_hold_blocks_hard_delete(self):
        reg = ArtifactRegistry()
        r = reg.register("proj1", _facts(content_role="run_log"), expected_output_names=["deg_results_table"])
        reg.set_legal_hold(r.artifact_id, True)
        self.assertFalse(reg.delete(r.artifact_id, hard=True)["deleted"])

    def test_tombstone_allowed(self):
        reg = ArtifactRegistry()
        r = reg.register("proj1", _facts(content_role="run_log"), expected_output_names=["deg_results_table"])
        # run_log is not formal evidence, but a soft tombstone is always allowed.
        self.assertEqual(reg.delete(r.artifact_id, hard=False)["mode"], "tombstone")


class DownloadTest(unittest.TestCase):
    def test_valid_download_checksum_ok(self):
        reg = ArtifactRegistry()
        r = reg.register("proj1", _facts(), expected_output_names=["deg_results_table"])
        result = reg.download(r.artifact_id)
        self.assertTrue(result["authorized"])
        self.assertTrue(result["checksum_ok"])

    def test_quarantined_not_downloadable(self):
        reg = ArtifactRegistry()
        r = reg.register("proj1", _facts(output_name="sneaky"), expected_output_names=["deg_results_table"])
        self.assertFalse(reg.download(r.artifact_id)["authorized"])

    def test_tampered_store_detected_on_download(self):
        reg = ArtifactRegistry()
        r = reg.register("proj1", _facts(), expected_output_names=["deg_results_table"])
        # Tamper the underlying object; download must detect the checksum mismatch.
        reg.store.put(r.uri, _TSV + b"tampered")
        result = reg.download(r.artifact_id)
        self.assertFalse(result["authorized"])
        self.assertFalse(result["checksum_ok"])


if __name__ == "__main__":
    unittest.main()
