"""Tests for the offline SBOM entry point (WP-01d / T-01-11, ci/sbom.py).

The generator is a developer tool living outside the importable package, so it
is loaded here by file path. The suite environment is Python 3.11 (stdlib
``tomllib``); on a bare 3.10 without the ``tomli`` backport these tests skip,
matching the generator's documented requirement.
"""

import importlib.util
import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SBOM_PATH = _REPO_ROOT / "ci" / "sbom.py"

try:  # the generator needs a TOML reader to parse pyproject.toml
    import tomllib  # noqa: F401

    _HAVE_TOML = True
except ModuleNotFoundError:
    try:
        import tomli  # noqa: F401

        _HAVE_TOML = True
    except ModuleNotFoundError:
        _HAVE_TOML = False


def _load_sbom_module():
    spec = importlib.util.spec_from_file_location("ci_sbom_under_test", _SBOM_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(_HAVE_TOML, "no TOML reader available (Python <3.11 without tomli)")
class SbomGeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sbom = _load_sbom_module()
        cls.doc = cls.sbom.build_sbom()
        cls.by_name = {c["name"]: c for c in cls.doc["components"]}

    def test_cyclonedx_envelope(self):
        self.assertEqual(self.doc["bomFormat"], "CycloneDX")
        self.assertEqual(self.doc["specVersion"], "1.5")
        root = self.doc["metadata"]["component"]
        self.assertEqual(root["name"], "auto-bioinfo")
        self.assertEqual(root["licenses"][0]["license"]["id"], "MIT")

    def test_declared_components_present(self):
        # Source of truth is pyproject.toml, so the full declared closure must
        # appear regardless of editable-install freshness (incl. coverage/dev).
        for name in ("numpy", "pytest", "ruff", "mypy", "coverage"):
            self.assertIn(name, self.by_name, f"{name} missing from SBOM")

    def test_group_classification(self):
        self._assert_group("numpy", "runtime")
        self._assert_group("pytest", "test")
        self._assert_group("ruff", "dev")
        self._assert_group("coverage", "dev")

    def _assert_group(self, name, expected):
        props = {p["name"]: p["value"] for p in self.by_name[name]["properties"]}
        self.assertEqual(props.get("auto-bioinfo:group"), expected)

    def test_self_reference_excluded(self):
        # 'auto-bioinfo[test]' wiring in the dev extra is not a component.
        self.assertNotIn("auto-bioinfo", self.by_name)

    def test_components_sorted(self):
        names = [c["name"] for c in self.doc["components"]]
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_deterministic_output(self):
        first = json.dumps(self.sbom.build_sbom(), sort_keys=False)
        second = json.dumps(self.sbom.build_sbom(), sort_keys=False)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
