#!/usr/bin/env python3
"""Minimal, offline SBOM generator for auto-bioinfo (WP-01d / T-01-11).

Emits a CycloneDX 1.5 JSON Software Bill of Materials for the dependency closure
that auto-bioinfo *declares*. The declared set is the committed source of truth —
``pyproject.toml`` (``[project.dependencies]`` and
``[project.optional-dependencies]``). It is read with the standard-library
``tomllib`` on Python 3.11+, and on Python 3.10 — where ``tomllib`` does not
exist — with a tiny built-in fallback that parses *only* the two dependency
fields this tool reads (see ``_fallback_project_table``). No third-party TOML
reader is imported, so the tool is genuinely standard-library-only and adds no
dependency across the project's full ``requires-python = ">=3.10"`` range. Each
declared component is then enriched with its *resolved* version and license,
read from installed package metadata via ``importlib.metadata``. No third-party
SBOM tool and no new dependency are required.

Design notes
------------
- Stdlib only, on every supported Python. Runs fully offline; it never reaches
  the network. Inputs are the committed ``pyproject.toml`` plus package metadata
  already installed locally.
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


# Matches a single- or double-quoted TOML basic/literal string; used only to
# pull dependency-array members out of the two fields the fallback parser reads.
_TOML_STR_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'')


def _strip_inline_comment(line: str) -> str:
    """Drop a trailing ``#`` comment that is not inside a quoted string."""
    quote: str | None = None
    for i, ch in enumerate(line):
        if quote is not None:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return line[:i]
    return line


def _fallback_project_table(text: str) -> dict:
    """Minimal stdlib-only parse of the ``[project]`` fields this tool reads.

    Used on Python 3.10, where ``tomllib`` is absent and no third-party TOML
    reader is assumed. It deliberately understands *only* string arrays under
    ``[project].dependencies`` and ``[project.optional-dependencies].<group>``
    — exactly what :func:`_declared_from_project` consumes — and nothing else of
    the TOML grammar. Any other table or field is ignored (its multi-line arrays
    are still consumed so they cannot be misread as keys/headers). This keeps the
    SBOM entry point stdlib-only across ``requires-python = ">=3.10"`` without
    pulling in a real TOML reader; on 3.11+ the robust stdlib ``tomllib`` is used
    instead.
    """
    project: dict = {}
    optional: dict = {}
    table: str | None = None
    collecting: list | None = None  # the array literal currently being filled

    def members(value: str) -> list[str]:
        return [m.group(1) if m.group(1) is not None else m.group(2) for m in _TOML_STR_RE.finditer(value)]

    def is_closed(value: str) -> bool:
        # The array closes on a ``]`` that is not inside a quoted string (e.g.
        # the ``]`` in ``"auto-bioinfo[test]"`` must not end the array).
        return "]" in _TOML_STR_RE.sub("", value)

    for raw_line in text.splitlines():
        line = _strip_inline_comment(raw_line).strip()
        if not line:
            continue
        if collecting is not None:
            collecting.extend(members(line))
            if is_closed(line):
                collecting = None
            continue
        if line.startswith("[") and line.endswith("]"):
            table = line[1:-1].strip()
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip().strip("\"'")
        value = value.strip()
        if not value.startswith("["):
            continue
        target: list = members(value)
        if table == "project" and key == "dependencies":
            project["dependencies"] = target
        elif table == "project.optional-dependencies":
            optional[key] = target
        # else: an array we don't care about — still consume it below so its
        # continuation lines aren't misparsed as keys/table headers.
        if not is_closed(value):
            collecting = target

    if optional:
        project["optional-dependencies"] = optional
    return project


def _read_project_table(text: str) -> dict:
    """Return the ``[project]`` table, via stdlib ``tomllib`` or the 3.10 fallback."""
    try:
        import tomllib  # stdlib on Python 3.11+
    except ModuleNotFoundError:  # Python 3.10: no stdlib TOML reader
        return _fallback_project_table(text)
    return tomllib.loads(text).get("project", {})


def _declared_from_project(project: dict) -> list[tuple[str, str | None, str]]:
    """Return ``(name, group, specifier)`` for every declared dependency.

    ``group`` is ``None`` for the runtime closure (``[project.dependencies]``),
    otherwise the optional-group name (``test`` / ``dev``). A group entry that
    merely pulls in the project's own extra (``auto-bioinfo[test]``) is skipped:
    it is group wiring, not a distinct package.
    """
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
    for group, group_members in (project.get("optional-dependencies", {}) or {}).items():
        for raw in group_members:
            add(raw, group)
    return out


def _load_declared(pyproject: Path = PYPROJECT) -> list[tuple[str, str | None, str]]:
    """Load and parse the declared dependency closure from ``pyproject``."""
    return _declared_from_project(_read_project_table(pyproject.read_text(encoding="utf-8")))


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
