"""Tests for the offline SBOM entry point (WP-01d / T-01-11, ci/sbom.py).

The generator is a developer tool living outside the importable package, so it
is loaded here by file path. It is standard-library-only on every supported
Python: ``tomllib`` on 3.11+, and a tiny built-in fallback parser on 3.10
(no ``tomllib``, no third-party TOML reader). These tests therefore never skip —
the previously-skipped Python 3.10/no-``tomli`` path is covered by exercising the
fallback parser directly (``FallbackTomlParserTest``), regardless of the running
interpreter.
"""

import importlib.util
import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SBOM_PATH = _REPO_ROOT / "ci" / "sbom.py"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _load_sbom_module():
    spec = importlib.util.spec_from_file_location("ci_sbom_under_test", _SBOM_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


class FallbackTomlParserTest(unittest.TestCase):
    """Covers the Python 3.10/no-``tomllib`` path that previously could skip.

    The fallback parser must produce the *same* declared closure as stdlib
    ``tomllib`` on the real ``pyproject.toml``; otherwise the SBOM would silently
    differ on Python 3.10. These tests call the fallback directly so they run on
    every interpreter (including the 3.11 suite environment), never skipping.
    """

    @classmethod
    def setUpClass(cls):
        cls.sbom = _load_sbom_module()
        cls.text = _PYPROJECT.read_text(encoding="utf-8")

    def test_fallback_matches_tomllib_on_real_pyproject(self):
        import tomllib  # the 3.11 suite environment has stdlib tomllib

        via_tomllib = self.sbom._declared_from_project(tomllib.loads(self.text).get("project", {}))
        via_fallback = self.sbom._declared_from_project(self.sbom._fallback_project_table(self.text))
        self.assertEqual(sorted(via_fallback), sorted(via_tomllib))
        # And it actually parsed something — guard against a vacuous match.
        self.assertTrue(via_fallback)

    def test_fallback_extracts_runtime_and_groups(self):
        project = self.sbom._fallback_project_table(self.text)
        self.assertEqual(project.get("dependencies"), ["numpy>=1.24"])
        optional = project.get("optional-dependencies", {})
        self.assertEqual(optional.get("test"), ["pytest>=7"])
        self.assertEqual(
            optional.get("dev"),
            ["auto-bioinfo[test]", "ruff>=0.4", "mypy>=1.8", "coverage[toml]>=7"],
        )

    def test_fallback_declared_groups_and_self_reference(self):
        declared = self.sbom._declared_from_project(self.sbom._fallback_project_table(self.text))
        by_name = {name: group for name, group, _ in declared}
        self.assertEqual(by_name.get("numpy"), None)  # runtime closure
        self.assertEqual(by_name.get("pytest"), "test")
        self.assertEqual(by_name.get("ruff"), "dev")
        self.assertNotIn("auto-bioinfo", by_name)  # self-extra wiring dropped

    def test_fallback_ignores_unrelated_arrays(self):
        # Arrays under other tables (e.g. [tool.ruff.lint].select, multi-line
        # [tool.coverage.report].exclude_lines) must not leak into the project
        # table or break parsing of later [project.*] sections.
        sample = (
            "[tool.ruff.lint]\n"
            'select = ["E", "F", "I"]\n'
            "[tool.coverage.report]\n"
            "exclude_lines = [\n"
            '    "pragma: no cover",\n'
            '    "if __name__ == .__main__.:",\n'
            "]\n"
            "[project]\n"
            'dependencies = ["numpy>=1.24"]\n'
        )
        project = self.sbom._fallback_project_table(sample)
        self.assertEqual(project.get("dependencies"), ["numpy>=1.24"])
        self.assertNotIn("optional-dependencies", project)

    def test_strip_inline_comment_respects_quotes(self):
        strip = self.sbom._strip_inline_comment
        self.assertEqual(strip('key = "v"  # trailing').strip(), 'key = "v"')
        self.assertEqual(strip('name = "a#b"').strip(), 'name = "a#b"')
        self.assertEqual(strip("# whole line").strip(), "")


if __name__ == "__main__":
    unittest.main()
