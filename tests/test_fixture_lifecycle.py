"""Fixture lifecycle and isolation tests (WP-01c / T-01-09).

These tests encode the fixture lifecycle rules documented in ``tests/README.md``
as executable checks:

* committed fixtures are synthetic, offline and read-only reference data;
* helper-built fixtures live under the **system temp dir**, never inside the
  repo and never in a database or object store;
* temp workspaces are cleaned up (no residue left behind);
* fixtures are deterministic (same inputs -> identical bytes);
* no real / sensitive human-source data is present.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import auto_bioinfo
from auto_bioinfo.adapters.fixture_resources import FixtureResourceAdapter
from tests import _helpers
from tests._helpers import real_like_fixture, temp_workspace, tiny_fixture

PACKAGE_DIR = Path(auto_bioinfo.__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
COMMITTED_FIXTURE_DIR = PACKAGE_DIR / "fixtures" / "bulk_deg_demo"
TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


class CommittedFixtureTest(unittest.TestCase):
    """The one committed fixture is synthetic, offline and self-contained."""

    def test_committed_fixture_files_present(self):
        for name in ("counts.tsv", "samples.tsv", "dataset_card.json"):
            self.assertTrue((COMMITTED_FIXTURE_DIR / name).is_file(), name)

    def test_committed_card_declares_offline_synthetic_provenance(self):
        card = json.loads((COMMITTED_FIXTURE_DIR / "dataset_card.json").read_text(encoding="utf-8"))
        # Offline: served from a local cache, not fetched from a network source.
        self.assertEqual(card["retrieval_mode"], "LOCAL_CACHE")
        # Honestly labelled synthetic fixture, not fabricated-as-real data.
        self.assertEqual(card["source_class"], "SYNTHETIC_FIXTURE")
        self.assertEqual(card["source_status"], "committed_fixture")
        self.assertIn("synthetic", card["organism"])

    def test_adapter_materialize_only_touches_local_files(self):
        adapter = FixtureResourceAdapter()
        profile = {"files": {"counts": "counts.tsv", "samples": "samples.tsv"}}
        with temp_workspace() as dest:
            out = adapter.materialize(profile, str(dest))
            for logical, path in out.items():
                p = Path(path)
                self.assertTrue(p.is_file(), logical)
                # Materialised strictly into the caller-provided local dir.
                self.assertEqual(p.parent.resolve(), dest.resolve())


class TempFixtureIsolationTest(unittest.TestCase):
    """Helper-built fixtures are isolated from the repo / DB / object store."""

    def test_tiny_fixture_lives_under_system_temp_not_repo(self):
        base = tiny_fixture().resolve()
        self.assertTrue(base.is_dir())
        # Under the system temp dir...
        self.assertTrue(str(base).startswith(str(TEMP_ROOT)), base)
        # ...and never written into the repository tree.
        self.assertNotIn(str(REPO_ROOT), str(base))

    def test_tiny_fixture_is_self_contained_and_offline(self):
        base = tiny_fixture()
        for name in ("counts.tsv", "samples.tsv", "dataset_card.json"):
            self.assertTrue((base / name).is_file(), name)
        card = json.loads((base / "dataset_card.json").read_text(encoding="utf-8"))
        self.assertEqual(card["retrieval_mode"], "LOCAL_CACHE")
        self.assertEqual(card["source_class"], "SYNTHETIC_FIXTURE")

    def test_real_like_fixture_is_a_synthetic_test_double(self):
        # Relabelled as PUBLIC_DATABASE for the eligibility-gate tests, but the
        # bytes are the same deterministic synthetic fixture — no real data.
        base = real_like_fixture()
        card = json.loads((base / "dataset_card.json").read_text(encoding="utf-8"))
        self.assertEqual(card["source_class"], "PUBLIC_DATABASE")
        self.assertEqual(card["retrieval_mode"], "LOCAL_CACHE")
        counts = (base / "counts.tsv").read_text(encoding="utf-8")
        self.assertIn("GENE_UP", counts)


class TempLifecycleTest(unittest.TestCase):
    """Temp workspaces are cleaned up; the suite leaves no residue."""

    def test_temp_workspace_context_manager_cleans_up(self):
        with temp_workspace() as ws:
            marker = ws / "scratch.txt"
            marker.write_text("x", encoding="utf-8")
            self.assertTrue(marker.is_file())
            captured = ws
        self.assertFalse(captured.exists(), "temp_workspace must remove its dir on exit")

    def test_fixture_temp_roots_are_registered_and_sweepable(self):
        before = len(_helpers._TEMP_ROOTS)
        tiny_fixture()
        self.assertGreater(len(_helpers._TEMP_ROOTS), before)
        # The atexit sweep removes every registered root.
        roots = list(_helpers._TEMP_ROOTS)
        _helpers._cleanup_temp_roots()
        self.assertEqual(_helpers._TEMP_ROOTS, [])
        for root in roots:
            self.assertFalse(root.exists(), root)


class DeterminismTest(unittest.TestCase):
    def test_tiny_fixture_is_byte_deterministic(self):
        a = tiny_fixture(3, 3)
        b = tiny_fixture(3, 3)
        self.assertEqual(
            (a / "counts.tsv").read_bytes(),
            (b / "counts.tsv").read_bytes(),
        )
        self.assertEqual(
            (a / "samples.tsv").read_bytes(),
            (b / "samples.tsv").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
