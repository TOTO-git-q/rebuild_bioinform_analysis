"""Unit tests for the WP-27 release-readiness object and evolution boundary.

Covers, over synthetic in-memory facts (no deployment, no network, no clock):

- release readiness: ready only when every hard-stop gate passed WITH evidence;
  a failed gate, an unreported gate, or a passed-but-no-evidence gate each blocks
  (fail closed); the sensitive-data tier adds extra gates;
- release manifest: complete only when every component is pinned; missing
  components reported;
- evolution boundary: in-scope / out-of-scope classification; an unknown feature
  defaults to unknown (never auto-in-scope);
- the WP-27 docs exist.
"""

import os
import unittest

from auto_bioinfo.ops import release_readiness as rr


def _all_core_pass():
    return [rr.GateResult(gid, passed=True, evidence_ref=f"evidence://{gid}") for gid in rr.required_gate_ids()]


class ReleaseReadinessTests(unittest.TestCase):
    def test_ready_when_all_core_gates_pass_with_evidence(self):
        d = rr.evaluate_release_readiness(_all_core_pass())
        self.assertTrue(d.ready)
        self.assertEqual(d.reason_code, rr.CODE_READY)
        self.assertEqual(d.unmet_gates, ())

    def test_failed_gate_blocks(self):
        results = _all_core_pass()
        results[0] = rr.GateResult(results[0].gate_id, passed=False, evidence_ref="evidence://x")
        d = rr.evaluate_release_readiness(results)
        self.assertFalse(d.ready)
        self.assertEqual(d.reason_code, rr.CODE_BLOCKED_UNMET_GATE)
        self.assertIn(rr.GATE_SECURITY_SCAN, d.unmet_gates)

    def test_passed_without_evidence_blocks(self):
        results = _all_core_pass()
        results[0] = rr.GateResult(results[0].gate_id, passed=True, evidence_ref="")
        d = rr.evaluate_release_readiness(results)
        self.assertFalse(d.ready)
        self.assertEqual(d.reason_code, rr.CODE_BLOCKED_MISSING_EVIDENCE)

    def test_missing_gate_blocks(self):
        results = _all_core_pass()[:-1]  # drop one required gate
        d = rr.evaluate_release_readiness(results)
        self.assertFalse(d.ready)
        self.assertEqual(d.reason_code, rr.CODE_BLOCKED_MISSING_GATE)

    def test_sensitive_data_tier_adds_gates(self):
        # core all pass but sensitive tier not reported -> blocked when required
        d = rr.evaluate_release_readiness(_all_core_pass(), include_sensitive_data=True)
        self.assertFalse(d.ready)
        self.assertIn(rr.GATE_PRIVACY, d.unmet_gates)
        # now include the sensitive gates
        full = _all_core_pass() + [rr.GateResult(g.gate_id, passed=True, evidence_ref=f"evidence://{g.gate_id}") for g in rr.SENSITIVE_DATA_GATES]
        ready = rr.evaluate_release_readiness(full, include_sensitive_data=True)
        self.assertTrue(ready.ready)

    def test_malformed_fails_closed(self):
        self.assertEqual(rr.evaluate_release_readiness("nope").reason_code, rr.CODE_MALFORMED)
        self.assertEqual(rr.evaluate_release_readiness([object()]).reason_code, rr.CODE_MALFORMED)

    def test_status_vocab_bounded(self):
        self.assertIn(rr.evaluate_release_readiness(_all_core_pass()).status, rr.STATUSES)


class ReleaseManifestTests(unittest.TestCase):
    def test_complete_manifest(self):
        versions = {c: f"{c}-v1" for c in rr.MANIFEST_COMPONENTS}
        result = rr.build_release_manifest(versions)
        self.assertTrue(result.complete)
        self.assertEqual(result.missing_components, ())

    def test_incomplete_manifest_reports_missing(self):
        versions = {"code": "abc123"}
        result = rr.build_release_manifest(versions)
        self.assertFalse(result.complete)
        self.assertIn("schema", result.missing_components)

    def test_blank_component_is_missing(self):
        versions = {c: f"{c}-v1" for c in rr.MANIFEST_COMPONENTS}
        versions["image"] = "   "
        result = rr.build_release_manifest(versions)
        self.assertFalse(result.complete)
        self.assertIn("image", result.missing_components)


class EvolutionBoundaryTests(unittest.TestCase):
    def test_in_scope(self):
        self.assertEqual(rr.classify_feature("task_execution_and_qc"), rr.SCOPE_IN)

    def test_out_of_scope(self):
        self.assertEqual(rr.classify_feature("multi_tenant_billing"), rr.SCOPE_OUT)
        self.assertEqual(rr.classify_feature("production_sensitive_data_processing"), rr.SCOPE_OUT)

    def test_unknown_defaults_unknown(self):
        self.assertEqual(rr.classify_feature("some_new_idea"), rr.SCOPE_UNKNOWN)
        self.assertEqual(rr.classify_feature(None), rr.SCOPE_UNKNOWN)

    def test_scope_lists_disjoint(self):
        self.assertEqual(rr.IN_SCOPE_FEATURES & rr.OUT_OF_SCOPE_FEATURES, frozenset())


class Wp27DocsTests(unittest.TestCase):
    def test_docs_present(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("wp27_release_ops_handoff.md", "wp27_evolution_boundary.md", "wp27_operator_runbook.md"):
            path = os.path.join(here, "docs", "rebuild", name)
            self.assertTrue(os.path.isfile(path), f"missing WP-27 doc: {name}")
            with open(path, encoding="utf-8") as handle:
                self.assertGreater(len(handle.read()), 200)


if __name__ == "__main__":
    unittest.main()
