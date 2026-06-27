"""Tests for the local OpenAPI contract/spec foundation (WP-04k / T-04-11).

These tests pin the deterministic, side-effect-free OpenAPI projection of the
existing control-plane contracts: that the spec generates deterministically, that
every path/operation binds to an implemented contract, that its status/reason-code
enums match the *bounded vocabulary of the owning module* (so the document cannot
drift from the code), that the validator rejects every inconsistency it promises
to (missing refs, duplicate operation ids, unimplemented operations, malformed
enums, accidental auth/security), and that the module has no I/O / clock / network
/ web-server side effects.
"""

from __future__ import annotations

import copy
import importlib
import json
import unittest

from auto_bioinfo.control_plane import (
    build_openapi_spec,
    openapi_contract,
    spec_to_json,
    validate_openapi_spec,
)
from auto_bioinfo.control_plane import cancel_command as cancel_mod
from auto_bioinfo.control_plane import command_api as command_mod
from auto_bioinfo.control_plane.cli_contract import CLI_REASON_CODES, CLI_STATUSES
from auto_bioinfo.control_plane.operation_resource import (
    ERROR_CODES,
    OPERATION_STATUSES,
    PROJECTION_CATEGORIES,
)


def _schema(spec: dict, name: str) -> dict:
    return spec["components"]["schemas"][name]


def _enum(spec: dict, name: str, field: str) -> list:
    return _schema(spec, name)["properties"][field]["enum"]


class DeterministicGenerationTest(unittest.TestCase):
    def test_two_builds_are_equal(self) -> None:
        self.assertEqual(build_openapi_spec(), build_openapi_spec())

    def test_builds_are_independent_objects(self) -> None:
        first = build_openapi_spec()
        first["paths"]["/commands"]["post"]["operationId"] = "tampered"
        # A later build must not see the mutation: build returns a fresh object.
        self.assertEqual(build_openapi_spec()["paths"]["/commands"]["post"]["operationId"], "admitCommand")

    def test_canonical_json_is_byte_stable(self) -> None:
        self.assertEqual(spec_to_json(canonical=True), spec_to_json(canonical=True))
        # Order-independent: a re-keyed copy serialises to the same canonical bytes.
        spec = build_openapi_spec()
        reordered = json.loads(json.dumps(spec))
        self.assertEqual(spec_to_json(spec, canonical=True), spec_to_json(reordered, canonical=True))

    def test_indented_json_round_trips(self) -> None:
        spec = build_openapi_spec()
        self.assertEqual(json.loads(spec_to_json(spec)), spec)

    def test_spec_to_json_with_no_arg_builds_default(self) -> None:
        self.assertEqual(json.loads(spec_to_json()), build_openapi_spec())


class StructureAndCoverageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = build_openapi_spec()

    def test_is_openapi_3x(self) -> None:
        self.assertTrue(self.spec["openapi"].startswith("3."))

    def test_required_paths_present(self) -> None:
        for path in ("/commands", "/operations/{operationId}", "/operations/{operationId}/cancel", "/cli/invocations"):
            self.assertIn(path, self.spec["paths"])

    def test_each_operation_id_binds_to_an_implemented_contract(self) -> None:
        ids = {op["operationId"] for item in self.spec["paths"].values() for method, op in item.items() if method in ("get", "post", "put", "delete", "patch")}
        self.assertEqual(ids, set(openapi_contract.IMPLEMENTED_OPERATIONS))

    def test_implemented_operations_are_importable_callables(self) -> None:
        for dotted in openapi_contract.IMPLEMENTED_OPERATIONS.values():
            module_name, attr = dotted.rsplit(".", 1)
            module = importlib.import_module(module_name)
            self.assertTrue(callable(getattr(module, attr)), dotted)

    def test_required_component_schemas_present(self) -> None:
        for name in (
            "CommandApiResult",
            "OperationRecord",
            "OperationProjection",
            "CancelDecision",
            "CliResult",
        ):
            self.assertIn(name, self.spec["components"]["schemas"])

    def test_transport_headers_projected_as_parameters(self) -> None:
        params = self.spec["components"]["parameters"]
        self.assertEqual(params["IdempotencyKeyHeader"]["name"], command_mod.IDEMPOTENCY_KEY_HEADER)
        self.assertEqual(params["IdempotencyKeyHeader"]["in"], "header")
        self.assertEqual(params["ExpectedVersionHeader"]["name"], command_mod.EXPECTED_VERSION_HEADER)
        self.assertTrue(params["IdempotencyKeyHeader"]["required"])

    def test_no_security_block_by_default(self) -> None:
        self.assertNotIn("security", self.spec)
        self.assertNotIn("securitySchemes", self.spec["components"])


class EnumBindingTest(unittest.TestCase):
    """Each enum must equal the owning contract's bounded vocabulary."""

    def setUp(self) -> None:
        self.spec = build_openapi_spec()

    def test_command_result_status_and_reason_codes(self) -> None:
        self.assertEqual(_enum(self.spec, "CommandApiResult", "status"), list(command_mod.STATUSES))
        self.assertEqual(_enum(self.spec, "CommandApiResult", "reason_code"), list(command_mod.REASON_CODES))

    def test_operation_status_and_categories(self) -> None:
        self.assertEqual(_enum(self.spec, "OperationRecord", "status"), list(OPERATION_STATUSES))
        self.assertEqual(_enum(self.spec, "OperationProjection", "category"), list(PROJECTION_CATEGORIES))
        # The malformed-projection error_code is the bounded ERROR_CODES plus "".
        self.assertEqual(set(_enum(self.spec, "OperationProjection", "error_code")), set(ERROR_CODES) | {""})

    def test_cancel_status_and_reason_codes(self) -> None:
        self.assertEqual(_enum(self.spec, "CancelDecision", "status"), list(cancel_mod.STATUSES))
        self.assertEqual(_enum(self.spec, "CancelDecision", "reason_code"), list(cancel_mod.REASON_CODES))

    def test_cli_status_and_union_reason_codes(self) -> None:
        self.assertEqual(_enum(self.spec, "CliResult", "status"), list(CLI_STATUSES))
        union = _enum(self.spec, "CliResult", "reason_code")
        # CLI parse codes and both dispatched contracts' codes are all covered.
        for code in CLI_REASON_CODES:
            self.assertIn(code, union)
        for code in command_mod.REASON_CODES:
            self.assertIn(code, union)
        for code in cancel_mod.REASON_CODES:
            self.assertIn(code, union)
        # No duplicates: the union is order-stable and deduplicated.
        self.assertEqual(len(union), len(set(union)))


class ValidationAcceptsGoodSpecTest(unittest.TestCase):
    def test_generated_spec_is_valid(self) -> None:
        self.assertEqual(validate_openapi_spec(build_openapi_spec()), [])


class ValidationRejectsBadSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = build_openapi_spec()

    def _codes(self, spec: dict) -> set:
        return {code for code, _ in validate_openapi_spec(spec)}

    def test_non_dict_rejected(self) -> None:
        self.assertIn(openapi_contract.CODE_MALFORMED_SPEC, self._codes(["not", "a", "spec"]))

    def test_missing_paths_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["paths"] = {}
        self.assertIn(openapi_contract.CODE_MALFORMED_SPEC, self._codes(spec))

    def test_dangling_ref_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["paths"]["/commands"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/DoesNotExist"}
        self.assertIn(openapi_contract.CODE_MISSING_REF, self._codes(spec))

    def test_duplicate_operation_id_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["paths"]["/cli/invocations"]["post"]["operationId"] = "admitCommand"
        self.assertIn(openapi_contract.CODE_DUPLICATE_OPERATION_ID, self._codes(spec))

    def test_unimplemented_operation_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["paths"]["/cli/invocations"]["post"]["operationId"] = "deleteEverything"
        self.assertIn(openapi_contract.CODE_UNIMPLEMENTED_OPERATION, self._codes(spec))

    def test_malformed_status_enum_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["components"]["schemas"]["CommandApiResult"]["properties"]["status"]["enum"] = ["ok", "definitely_not_a_status"]
        self.assertIn(openapi_contract.CODE_MALFORMED_ENUM, self._codes(spec))

    def test_missing_enum_value_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        # Drop a legitimate status value: the enum no longer matches the contract.
        spec["components"]["schemas"]["CommandApiResult"]["properties"]["status"]["enum"] = ["ok"]
        self.assertIn(openapi_contract.CODE_MALFORMED_ENUM, self._codes(spec))

    def test_top_level_security_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["security"] = [{"apiKey": []}]
        self.assertIn(openapi_contract.CODE_UNEXPECTED_SECURITY, self._codes(spec))

    def test_security_scheme_component_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["components"]["securitySchemes"] = {"apiKey": {"type": "apiKey", "in": "header", "name": "X-Key"}}
        self.assertIn(openapi_contract.CODE_UNEXPECTED_SECURITY, self._codes(spec))

    def test_per_operation_security_rejected(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["paths"]["/commands"]["post"]["security"] = [{"apiKey": []}]
        self.assertIn(openapi_contract.CODE_UNEXPECTED_SECURITY, self._codes(spec))


class NoSideEffectsTest(unittest.TestCase):
    """The module must be a pure contract layer: no I/O, clock, net, or server."""

    def test_module_source_has_no_forbidden_imports(self) -> None:
        import inspect

        source = inspect.getsource(openapi_contract)
        for forbidden in (
            "import os",
            "import socket",
            "import http",
            "import urllib",
            "import requests",
            "import subprocess",
            "import threading",
            "import asyncio",
            "import time",
            "from fastapi",
            "from flask",
            "open(",
            "datetime.now",
        ):
            self.assertNotIn(forbidden, source, forbidden)

    def test_build_takes_no_required_arguments(self) -> None:
        import inspect

        sig = inspect.signature(build_openapi_spec)
        self.assertEqual([p for p in sig.parameters.values() if p.default is inspect.Parameter.empty], [])


if __name__ == "__main__":
    unittest.main()
