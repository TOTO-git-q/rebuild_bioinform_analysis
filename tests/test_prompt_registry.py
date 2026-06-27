"""Unit tests for the local PromptRegistry contract foundation (WP-05b / T-05-02).

Covers, for the offline, deterministic registry-contract foundation:

- the :class:`RegisteredPrompt` value shape: stable identity / reference, the
  deterministic canonical template hash, and the ``to_dict`` projection,
- fail-closed record validation (malformed prompt id, malformed version, empty /
  whitespace / oversized template, malformed / missing target schema reference),
- the ``ensure_valid_prompt`` guard raising a bounded ``PromptRegistryError``,
- registration + lookup by exact id + version, duplicate-registration rejection,
  and ``expected_hash`` mismatch rejection at both register and resolve time,
- target-schema binding surviving registration and resolution,
- fail-closed unknown-prompt vs unknown-version lookup (no silent fallback to
  unregistered content), and
- deterministic, registration-order-independent registry serialization.
"""

import unittest

from auto_bioinfo.agent_gateway.prompt_registry import (
    CODE_DUPLICATE_REGISTRATION,
    CODE_EMPTY_TEMPLATE,
    CODE_HASH_MISMATCH,
    CODE_MALFORMED_PROMPT_ID,
    CODE_MALFORMED_RECORD,
    CODE_MALFORMED_TARGET_SCHEMA,
    CODE_MALFORMED_VERSION,
    CODE_TEMPLATE_TOO_LONG,
    CODE_UNKNOWN_PROMPT,
    CODE_UNKNOWN_VERSION,
    MAX_TEMPLATE_LENGTH,
    REASON_CODES,
    PromptRegistry,
    PromptRegistryError,
    RegisteredPrompt,
    ensure_valid_prompt,
    validate_prompt,
)


def _prompt(
    *,
    prompt_id: str = "report.summary",
    version: str = "1.0.0",
    template: str = "Summarize {{run}} in one paragraph.",
    target_schema: str = "report.summary/v1",
) -> RegisteredPrompt:
    return RegisteredPrompt(prompt_id=prompt_id, version=version, template=template, target_schema=target_schema)


class ValueShapeTest(unittest.TestCase):
    def test_key_and_reference_expose_stable_identity(self):
        prompt = _prompt()
        self.assertEqual(prompt.key, ("report.summary", "1.0.0"))
        self.assertEqual(prompt.reference, "report.summary@1.0.0")

    def test_template_hash_is_deterministic_and_content_sensitive(self):
        a = _prompt(template="hello world")
        b = _prompt(template="hello world")
        c = _prompt(template="hello world.")
        self.assertEqual(a.template_hash, b.template_hash)
        self.assertNotEqual(a.template_hash, c.template_hash)
        # Stable across repeated calls (no clock / randomness).
        self.assertEqual(a.template_hash, a.template_hash)

    def test_to_dict_is_deterministic_and_includes_hash(self):
        prompt = _prompt()
        self.assertEqual(
            prompt.to_dict(),
            {
                "prompt_id": "report.summary",
                "version": "1.0.0",
                "template": "Summarize {{run}} in one paragraph.",
                "target_schema": "report.summary/v1",
                "template_hash": prompt.template_hash,
            },
        )

    def test_all_reason_codes_are_unique(self):
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))


class RecordValidationTest(unittest.TestCase):
    def test_valid_record_has_no_errors(self):
        self.assertEqual(validate_prompt(_prompt()), [])

    def test_non_record_is_malformed(self):
        codes = {code for code, _ in validate_prompt({"prompt_id": "x"})}
        self.assertIn(CODE_MALFORMED_RECORD, codes)

    def test_malformed_prompt_id_fails_closed(self):
        for bad in ("", "  ", "Report Summary", "report..summary", "_leading"):
            codes = {code for code, _ in validate_prompt(_prompt(prompt_id=bad))}
            self.assertIn(CODE_MALFORMED_PROMPT_ID, codes, bad)

    def test_malformed_version_fails_closed(self):
        for bad in ("", " ", "v 1", "1/0", "-1.0"):
            codes = {code for code, _ in validate_prompt(_prompt(version=bad))}
            self.assertIn(CODE_MALFORMED_VERSION, codes, bad)

    def test_empty_or_whitespace_template_fails_closed(self):
        for bad in ("", "   ", "\n\t "):
            codes = {code for code, _ in validate_prompt(_prompt(template=bad))}
            self.assertIn(CODE_EMPTY_TEMPLATE, codes, repr(bad))

    def test_oversized_template_fails_closed(self):
        codes = {code for code, _ in validate_prompt(_prompt(template="x" * (MAX_TEMPLATE_LENGTH + 1)))}
        self.assertIn(CODE_TEMPLATE_TOO_LONG, codes)

    def test_malformed_target_schema_fails_closed(self):
        for bad in ("", "  ", "schema with spaces", "schema//v1"):
            codes = {code for code, _ in validate_prompt(_prompt(target_schema=bad))}
            self.assertIn(CODE_MALFORMED_TARGET_SCHEMA, codes, bad)

    def test_ensure_valid_prompt_raises_bounded_error(self):
        with self.assertRaises(PromptRegistryError) as ctx:
            ensure_valid_prompt(_prompt(prompt_id="Bad Id"))
        self.assertEqual(ctx.exception.code, CODE_MALFORMED_PROMPT_ID)
        self.assertIn(ctx.exception.code, REASON_CODES)

    def test_ensure_valid_prompt_returns_value_on_success(self):
        prompt = _prompt()
        self.assertIs(ensure_valid_prompt(prompt), prompt)


class RegistrationAndLookupTest(unittest.TestCase):
    def test_register_then_resolve_round_trips(self):
        registry = PromptRegistry()
        registered = registry.register(_prompt())
        resolved = registry.resolve("report.summary", "1.0.0")
        self.assertIs(resolved, registered)
        self.assertEqual(resolved.target_schema, "report.summary/v1")

    def test_constructor_registers_initial_prompts(self):
        registry = PromptRegistry([_prompt(), _prompt(version="2.0.0")])
        self.assertEqual(len(registry), 2)
        self.assertTrue(registry.contains("report.summary", "2.0.0"))
        self.assertEqual(registry.versions("report.summary"), ("1.0.0", "2.0.0"))
        self.assertEqual(registry.prompt_ids(), ("report.summary",))

    def test_register_rejects_malformed_record(self):
        registry = PromptRegistry()
        with self.assertRaises(PromptRegistryError) as ctx:
            registry.register(_prompt(template="   "))
        self.assertEqual(ctx.exception.code, CODE_EMPTY_TEMPLATE)
        self.assertEqual(len(registry), 0)

    def test_duplicate_registration_fails_closed(self):
        registry = PromptRegistry([_prompt()])
        with self.assertRaises(PromptRegistryError) as ctx:
            registry.register(_prompt(template="a different body entirely"))
        self.assertEqual(ctx.exception.code, CODE_DUPLICATE_REGISTRATION)
        # The original registration is unchanged (immutable version).
        self.assertEqual(registry.resolve("report.summary", "1.0.0").template, "Summarize {{run}} in one paragraph.")

    def test_distinct_versions_coexist(self):
        registry = PromptRegistry()
        registry.register(_prompt(version="1.0.0", template="v1 body"))
        registry.register(_prompt(version="2.0.0", template="v2 body"))
        self.assertEqual(registry.resolve("report.summary", "1.0.0").template, "v1 body")
        self.assertEqual(registry.resolve("report.summary", "2.0.0").template, "v2 body")


class HashBindingTest(unittest.TestCase):
    def test_register_with_matching_expected_hash_succeeds(self):
        prompt = _prompt()
        registry = PromptRegistry()
        registry.register(prompt, expected_hash=prompt.template_hash)
        self.assertTrue(registry.contains("report.summary", "1.0.0"))

    def test_register_with_mismatched_expected_hash_fails_closed(self):
        registry = PromptRegistry()
        with self.assertRaises(PromptRegistryError) as ctx:
            registry.register(_prompt(), expected_hash="deadbeef")
        self.assertEqual(ctx.exception.code, CODE_HASH_MISMATCH)
        self.assertEqual(len(registry), 0)

    def test_resolve_with_matching_expected_hash_returns_record(self):
        prompt = _prompt()
        registry = PromptRegistry([prompt])
        self.assertIs(registry.resolve("report.summary", "1.0.0", expected_hash=prompt.template_hash), prompt)

    def test_resolve_with_mismatched_expected_hash_fails_closed(self):
        registry = PromptRegistry([_prompt()])
        with self.assertRaises(PromptRegistryError) as ctx:
            registry.resolve("report.summary", "1.0.0", expected_hash="not-the-hash")
        self.assertEqual(ctx.exception.code, CODE_HASH_MISMATCH)


class UnknownLookupTest(unittest.TestCase):
    def test_unknown_prompt_id_fails_closed(self):
        registry = PromptRegistry([_prompt()])
        with self.assertRaises(PromptRegistryError) as ctx:
            registry.resolve("does.not.exist", "1.0.0")
        self.assertEqual(ctx.exception.code, CODE_UNKNOWN_PROMPT)

    def test_unknown_version_for_known_prompt_fails_closed(self):
        registry = PromptRegistry([_prompt()])
        with self.assertRaises(PromptRegistryError) as ctx:
            registry.resolve("report.summary", "9.9.9")
        self.assertEqual(ctx.exception.code, CODE_UNKNOWN_VERSION)

    def test_resolution_never_falls_back_to_another_version(self):
        # Only 1.0.0 is registered; asking for 2.0.0 must NOT silently return 1.0.0.
        registry = PromptRegistry([_prompt(version="1.0.0")])
        with self.assertRaises(PromptRegistryError):
            registry.resolve("report.summary", "2.0.0")
        self.assertFalse(registry.contains("report.summary", "2.0.0"))


class SerializationTest(unittest.TestCase):
    def test_registry_to_dict_is_registration_order_independent(self):
        forward = PromptRegistry()
        forward.register(_prompt(version="1.0.0", template="a"))
        forward.register(_prompt(version="2.0.0", template="b"))

        reverse = PromptRegistry()
        reverse.register(_prompt(version="2.0.0", template="b"))
        reverse.register(_prompt(version="1.0.0", template="a"))

        self.assertEqual(forward.to_dict(), reverse.to_dict())
        # Records are sorted by (prompt_id, version) and carry the bound hash.
        versions = [record["version"] for record in forward.to_dict()["prompts"]]
        self.assertEqual(versions, ["1.0.0", "2.0.0"])

    def test_to_dict_has_no_side_effects_on_registry(self):
        registry = PromptRegistry([_prompt()])
        before = len(registry)
        registry.to_dict()
        registry.to_dict()
        self.assertEqual(len(registry), before)


if __name__ == "__main__":
    unittest.main()
