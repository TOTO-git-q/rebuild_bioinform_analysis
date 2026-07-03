"""Adversarial boundary tests for the operon clean-room integration.

These guard the integration surface this branch owns, not one module:

* no quarantined / vendor asset path lands in the integration directories;
* the new offline modules import no network/subprocess libraries;
* importing the adapters package has no side effects (import stability).

The path scans are scoped to the directories this integration is responsible for
(``auto_bioinfo/`` and the added ``docs`` subtrees). Pre-existing, unrelated
repo content is intentionally *not* policed here.
"""

import importlib
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Directories this branch is responsible for (relative to repo root).
INTEGRATION_DIRS = (
    "auto_bioinfo",
    "docs/audit",
    "docs/rebuild",
    "docs/tools",
    "tests",
)

# Tokens that must never appear in a committed path (see
# docs/audit/operon_quarantine_boundary.md).
QUARANTINE_PATH_TOKENS = (
    "vendor_extracted",
    "bun_section",
    ".bun",
    "web-dist",
    "sharp-runtime",
    "micromamba",
    "seccomp",
    "operon_nested_assets_workspace",
    "gpt_upload_pack",
    "cleanroom_rebuild",
)

_SKIP_DIRS = {".git", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache"}


def _iter_integration_paths():
    for rel_dir in INTEGRATION_DIRS:
        base = REPO_ROOT / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            yield path


class QuarantinePathExclusionTest(unittest.TestCase):
    def test_no_quarantined_path_in_integration_dirs(self):
        offenders = []
        for path in _iter_integration_paths():
            rel = str(path.relative_to(REPO_ROOT))
            for token in QUARANTINE_PATH_TOKENS:
                if token in rel:
                    offenders.append(rel)
        self.assertEqual(offenders, [], f"quarantined paths present: {offenders}")

    def test_no_binary_or_archive_artifacts_in_integration_dirs(self):
        bad_suffixes = {".zip", ".tar", ".gz", ".bin", ".so", ".woff", ".woff2", ".ttf"}
        offenders = [str(p.relative_to(REPO_ROOT)) for p in _iter_integration_paths() if p.is_file() and p.suffix.lower() in bad_suffixes]
        self.assertEqual(offenders, [], f"binary/archive artifacts present: {offenders}")


class NoNetworkImportTest(unittest.TestCase):
    def test_new_offline_modules_have_no_network_imports(self):
        import inspect

        for mod_name in (
            "auto_bioinfo.adapters.public_bio_tools",
            "auto_bioinfo.adapters.capability_registry",
        ):
            mod = importlib.import_module(mod_name)
            source = inspect.getsource(mod)
            for forbidden in ("import socket", "import requests", "import urllib", "import http", "import subprocess", "socket.", "urllib.", "subprocess."):
                self.assertNotIn(forbidden, source, f"{mod_name}: forbidden {forbidden!r}")


class ImportStabilityTest(unittest.TestCase):
    def test_importing_adapters_package_is_safe(self):
        pkg = importlib.import_module("auto_bioinfo.adapters")
        for name in ("PublicBioToolAdapter", "build_public_bio_tool_registry", "MaterializationRejected"):
            self.assertTrue(hasattr(pkg, name), name)

    def test_existing_adapter_imports_still_work(self):
        # Adding re-exports must not break the direct-import paths in use today.
        from auto_bioinfo.adapters.fixture_resources import FixtureResourceAdapter
        from auto_bioinfo.adapters.offline_planner import OfflineDeterministicPlanner

        self.assertTrue(callable(OfflineDeterministicPlanner))
        self.assertTrue(callable(FixtureResourceAdapter))


if __name__ == "__main__":
    unittest.main()
