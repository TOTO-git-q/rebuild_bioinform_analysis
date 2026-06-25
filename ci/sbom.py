#!/usr/bin/env python3
"""Minimal, offline SBOM generator for auto-bioinfo (WP-01d / T-01-11).

Emits a CycloneDX 1.5 JSON Software Bill of Materials for the dependency closure
that auto-bioinfo *declares*. The declared set is the committed source of truth —
``pyproject.toml`` (``[project.dependencies]`` and
``[project.optional-dependencies]``) — read with the standard-library
``tomllib`` (Python 3.11+; falls back to ``tomli`` on 3.10 if installed). Each
declared component is then enriched with its
*resolved* version and license, read from installed package metadata via
``importlib.metadata``. No third-party SBOM tool and no new dependency are
required.

Design notes
------------
- Stdlib only. Runs fully offline; it never reaches the network. Inputs are the
  committed ``pyproject.toml`` plus package metadata already installed locally.
- Source of truth is the manifest, not the environment. The component *set*
  comes from ``pyproject.toml`` so the inventory cannot silently drift with a
  stale editable install; installed metadata only supplies resolved
  versions/licenses (best-effort, marked ``UNKNOWN`` / version-less when a
  dependency is not installed).
- Deterministic. Components are sorted and no wall-clock timestamp is embedded,
  so repeated runs against the same inputs are byte-identical (consistent with
  the project's reproduction-bundle guarantee).
- Scope. This is a *lightweight entry point*, not a fully attested SBOM. A
  richer, signed, multi-platform SBOM (e.g. via ``cyclonedx-py`` or
  ``pip-audit``) would add a dev dependency and a CI artifact policy; that path
  is documented in ``docs/audit/dependency_inventory.md`` and deferred to a
  later, separately authorized work order.

Usage
-----
    python ci/sbom.py            # write CycloneDX JSON to stdout
    python ci/sbom.py -o sbom.json
    make sbom                    # same, via the developer Makefile
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib import metadata
from pathlib import Path

PROJECT = "auto-bioinfo"
SPEC_VERSION = "1.5"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Splits a requirement string into (name, specifier), dropping extras and markers,
# e.g. "numpy>=1.24" -> ("numpy", ">=1.24"); "coverage[toml]>=7" -> ("coverage", ">=7").
_REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*([^;]*)")


def _parse_requirement(raw: str) -> tuple[str, str]:
    match = _REQ_RE.match(raw)
    if not match:
        return raw.strip(), ""
    return match.group(1), match.group(2).strip()


def _load_declared(pyproject: Path = PYPROJECT) -> list[tuple[str, str | None, str]]:
    """Return ``(name, group, specifier)`` for every declared dependency.

    ``group`` is ``None`` for the runtime closure (``[project.dependencies]``),
    otherwise the optional-group name (``test`` / ``dev``). A group entry that
    merely pulls in the project's own extra (``auto-bioinfo[test]``) is skipped:
    it is group wiring, not a distinct package.
    """
    try:
        import tomllib  # stdlib on Python 3.11+
    except ModuleNotFoundError:  # Python 3.10: optional backport, if present
        import tomli as tomllib  # type: ignore[no-redef]

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    out: list[tuple[str, str | None, str]] = []
    seen: set[tuple[str, str | None]] = set()

    def add(raw: str, group: str | None) -> None:
        name, spec = _parse_requirement(raw)
        if not name or name.lower() == PROJECT.lower():
            return
        key = (name.lower(), group)
        if key in seen:
            return
        seen.add(key)
        out.append((name, group, spec))

    for raw in project.get("dependencies", []):
        add(raw, None)
    for group, members in (project.get("optional-dependencies", {}) or {}).items():
        for raw in members:
            add(raw, group)
    return out


def _installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _license_id(name: str) -> str:
    """Best-effort SPDX-ish license string from installed metadata."""
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "UNKNOWN"
    # PEP 639 modern field first, then classifiers, then the legacy free-text.
    expr = meta.get("License-Expression")
    if expr:
        return expr.strip()
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License :: "):
            return classifier.rsplit("::", 1)[-1].strip()
    legacy = meta.get("License")
    if legacy and legacy.strip() and "\n" not in legacy.strip():
        return legacy.strip()
    return "UNKNOWN"


def build_sbom(pyproject: Path = PYPROJECT) -> dict:
    """Build a CycloneDX 1.5 document for the declared closure in ``pyproject``."""
    root_version = _installed_version(PROJECT) or "0.1.0"
    components = []
    for name, group, spec in sorted(_load_declared(pyproject), key=lambda t: (t[0].lower(), t[1] or "")):
        version = _installed_version(name)
        properties = [{"name": "auto-bioinfo:group", "value": group or "runtime"}]
        if spec:
            properties.append({"name": "auto-bioinfo:declared", "value": spec})
        component = {
            "type": "library",
            "name": name,
            "bom-ref": f"{name}@{version}" if version else name,
            "licenses": [{"license": {"id": _license_id(name)}}],
            "properties": properties,
        }
        if version:
            component["version"] = version
        components.append(component)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": PROJECT,
                "version": root_version,
                "licenses": [{"license": {"id": "MIT"}}],
            },
            "tools": [{"name": "auto-bioinfo ci/sbom.py", "vendor": "auto-bioinfo"}],
        },
        "components": components,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a minimal CycloneDX SBOM for auto-bioinfo (offline, stdlib only).")
    parser.add_argument("-o", "--output", help="Write SBOM JSON here instead of stdout.")
    args = parser.parse_args(argv)

    if not PYPROJECT.exists():
        print(f"error: cannot find {PYPROJECT}", file=sys.stderr)
        return 1

    document = json.dumps(build_sbom(), indent=2, sort_keys=False) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(document)
    else:
        sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
