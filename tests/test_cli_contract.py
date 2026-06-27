"""Unit tests for the local CLI command contract foundation (WP-04i / T-04-09).

Covers, for the bounded ``bioctl`` command vocabulary:

- valid command parsing (space-separated and inline ``--name=value`` forms,
  repeated ``--set`` payload options) mapped onto an admitted command decision,
- missing/malformed arguments (no command, unknown command/subcommand, missing
  subcommand, unknown option, missing option value, missing required option,
  unexpected positional, malformed numeric option, malformed/overlong argv),
- duplicate and conflicting options (a non-repeatable option twice, a repeated
  ``--set`` key),
- bounded, deterministic result serialisation and a stable exit-code category,
- deterministic reason codes (CLI-level and mapped-through contract codes),
- integration with the touched WP-04g command-API contract (version conflict,
  missing/malformed key and version, blank command type), and
- purity / totality: no mutation of the supplied argv, stable repeated results,
  and a never-raising fail-closed result for a table of malformed inputs.
"""

import contextlib
import io
import unittest

from auto_bioinfo.control_plane.cli_contract import (
    CLI_REASON_CODES,
    CLI_STATUS_OK,
    CLI_STATUS_REJECTED,
    CLI_STATUS_USAGE_ERROR,
    CLI_STATUSES,
    CODE_DUPLICATE_OPTION,
    CODE_INPUT_TOO_LONG,
    CODE_MALFORMED_ARGV,
    CODE_MALFORMED_OPTION,
    CODE_MISSING_OPTION_VALUE,
    CODE_MISSING_REQUIRED_OPTION,
    CODE_MISSING_SUBCOMMAND,
    CODE_NO_COMMAND,
    CODE_TOO_MANY_ARGS,
    CODE_UNEXPECTED_ARGUMENT,
    CODE_UNKNOWN_COMMAND,
    CODE_UNKNOWN_OPTION,
    CODE_UNKNOWN_SUBCOMMAND,
    EXIT_CODES,
    MAX_ARGV_ITEMS,
    MAX_TOKEN_LENGTH,
    CliResult,
    main,
    run_cli,
)
from auto_bioinfo.control_plane.command_api import (
    CODE_ACCEPTED,
    CODE_MALFORMED_COMMAND,
    CODE_MALFORMED_EXPECTED_VERSION,
    CODE_MISSING_IDEMPOTENCY_KEY,
    CODE_STALE_VERSION,
    REASON_CODES,
)


def _admit(*opts: str) -> list[str]:
    return ["command", "admit", *opts]


class ValidCommandParsingTest(unittest.TestCase):
    def test_accepted_command_minimal(self):
        result = run_cli(_admit("--type", "create_project", "--key", "abc123"))
        self.assertIsInstance(result, CliResult)
        self.assertEqual(result.status, CLI_STATUS_OK)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.reason_code, CODE_ACCEPTED)
        self.assertTrue(result.stdout)
        self.assertEqual(result.stderr, "")

    def test_inline_option_form(self):
        result = run_cli(_admit("--type=create_project", "--key=abc123"))
        self.assertEqual(result.status, CLI_STATUS_OK)
        self.assertEqual(result.reason_code, CODE_ACCEPTED)

    def test_payload_set_options_are_collected_and_sorted(self):
        result = run_cli(_admit("--type", "create_project", "--key", "k1", "--set", "title=Demo", "--set", "n=3"))
        self.assertEqual(result.status, CLI_STATUS_OK)
        self.assertEqual(result.binding["payload_keys"], ["n", "title"])

    def test_binding_records_command_path_and_decision(self):
        result = run_cli(_admit("--type", "create_project", "--key", "abc123"))
        self.assertEqual(result.binding["command_path"], ["command", "admit"])
        self.assertEqual(result.binding["command_type"], "create_project")
        # The mapped underlying decision is carried for audit.
        self.assertEqual(result.binding["decision"]["reason_code"], CODE_ACCEPTED)
        self.assertEqual(len(result.binding["decision"]["binding"]["command_fingerprint"]), 64)

    def test_version_match_is_accepted(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--expected-version", "2", "--current-version", "2"))
        self.assertEqual(result.status, CLI_STATUS_OK)
        self.assertEqual(result.reason_code, CODE_ACCEPTED)


class MissingAndMalformedArgsTest(unittest.TestCase):
    def test_no_command(self):
        result = run_cli([])
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
        self.assertEqual(result.reason_code, CODE_NO_COMMAND)
        self.assertEqual(result.exit_code, 2)

    def test_unknown_command(self):
        result = run_cli(["frobnicate"])
        self.assertEqual(result.reason_code, CODE_UNKNOWN_COMMAND)

    def test_missing_subcommand(self):
        result = run_cli(["command"])
        self.assertEqual(result.reason_code, CODE_MISSING_SUBCOMMAND)

    def test_unknown_subcommand(self):
        result = run_cli(["command", "frobnicate"])
        self.assertEqual(result.reason_code, CODE_UNKNOWN_SUBCOMMAND)

    def test_unknown_option(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--bogus", "x"))
        self.assertEqual(result.reason_code, CODE_UNKNOWN_OPTION)

    def test_missing_option_value_at_end(self):
        result = run_cli(_admit("--type"))
        self.assertEqual(result.reason_code, CODE_MISSING_OPTION_VALUE)

    def test_missing_option_value_followed_by_option(self):
        # A following token that itself looks like an option is not swallowed.
        result = run_cli(_admit("--type", "--key", "k"))
        self.assertEqual(result.reason_code, CODE_MISSING_OPTION_VALUE)

    def test_missing_required_option(self):
        result = run_cli(_admit("--key", "k"))
        self.assertEqual(result.reason_code, CODE_MISSING_REQUIRED_OPTION)

    def test_unexpected_positional_argument(self):
        result = run_cli(_admit("positional"))
        self.assertEqual(result.reason_code, CODE_UNEXPECTED_ARGUMENT)

    def test_malformed_current_version(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--current-version", "not-a-number"))
        self.assertEqual(result.reason_code, CODE_MALFORMED_OPTION)
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)

    def test_argv_must_be_a_list(self):
        result = run_cli("command admit")  # a bare string is not an argv list
        self.assertEqual(result.reason_code, CODE_MALFORMED_ARGV)

    def test_argv_items_must_be_strings(self):
        result = run_cli(["command", "admit", "--type", 5])  # type: ignore[list-item]
        self.assertEqual(result.reason_code, CODE_MALFORMED_ARGV)

    def test_too_many_arguments(self):
        result = run_cli(["command"] * (MAX_ARGV_ITEMS + 1))
        self.assertEqual(result.reason_code, CODE_TOO_MANY_ARGS)

    def test_overlong_token(self):
        result = run_cli(_admit("--type", "x" * (MAX_TOKEN_LENGTH + 1)))
        self.assertEqual(result.reason_code, CODE_INPUT_TOO_LONG)


class DuplicateAndConflictingOptionsTest(unittest.TestCase):
    def test_duplicate_single_value_option(self):
        result = run_cli(_admit("--type", "t", "--type", "u", "--key", "k"))
        self.assertEqual(result.reason_code, CODE_DUPLICATE_OPTION)

    def test_duplicate_payload_key(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--set", "a=1", "--set", "a=2"))
        self.assertEqual(result.reason_code, CODE_DUPLICATE_OPTION)

    def test_malformed_set_value_without_equals(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--set", "noequals"))
        self.assertEqual(result.reason_code, CODE_MALFORMED_OPTION)

    def test_malformed_set_value_blank_key(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--set", "=value"))
        self.assertEqual(result.reason_code, CODE_MALFORMED_OPTION)


class ContractIntegrationTest(unittest.TestCase):
    """The CLI delegates semantic validity to the WP-04g command API and maps its
    bounded reason code through unchanged."""

    def test_missing_key_maps_to_command_api_reason(self):
        result = run_cli(_admit("--type", "t"))
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
        self.assertEqual(result.reason_code, CODE_MISSING_IDEMPOTENCY_KEY)

    def test_blank_command_type_maps_to_malformed_command(self):
        result = run_cli(_admit("--type=", "--key", "k"))
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
        self.assertEqual(result.reason_code, CODE_MALFORMED_COMMAND)

    def test_malformed_expected_version_maps_through(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--expected-version", "abc"))
        self.assertEqual(result.status, CLI_STATUS_USAGE_ERROR)
        self.assertEqual(result.reason_code, CODE_MALFORMED_EXPECTED_VERSION)

    def test_stale_version_is_a_domain_rejection(self):
        result = run_cli(_admit("--type", "t", "--key", "k", "--expected-version", "1", "--current-version", "2"))
        self.assertEqual(result.status, CLI_STATUS_REJECTED)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.reason_code, CODE_STALE_VERSION)
        self.assertTrue(result.stderr)
        self.assertEqual(result.stdout, "")

    def test_mapped_reason_codes_are_from_the_command_api_vocabulary(self):
        for argv in (
            _admit("--type", "create_project", "--key", "k"),
            _admit("--type", "t"),
            _admit("--type=", "--key", "k"),
            _admit("--type", "t", "--key", "k", "--expected-version", "1", "--current-version", "2"),
        ):
            reason = run_cli(argv).reason_code
            self.assertIn(reason, REASON_CODES, msg=argv)


class ResultSerialisationTest(unittest.TestCase):
    def test_to_dict_is_deterministic_and_bounded(self):
        first = run_cli(_admit("--type", "create_project", "--key", "k")).to_dict()
        second = run_cli(_admit("--type", "create_project", "--key", "k")).to_dict()
        self.assertEqual(first, second)
        self.assertEqual(
            list(first.keys()),
            ["status", "exit_code", "reason_code", "ok", "stdout", "stderr", "binding"],
        )

    def test_status_and_exit_code_are_bounded(self):
        for argv in ([], ["frob"], _admit("--type", "create_project", "--key", "k")):
            result = run_cli(argv)
            self.assertIn(result.status, CLI_STATUSES)
            self.assertEqual(result.exit_code, EXIT_CODES[result.status])

    def test_cli_reason_codes_are_stable_set(self):
        # Every CLI-level reason code a parse failure can emit is declared.
        for code in (
            CODE_NO_COMMAND,
            CODE_UNKNOWN_COMMAND,
            CODE_MISSING_SUBCOMMAND,
            CODE_UNKNOWN_SUBCOMMAND,
            CODE_UNKNOWN_OPTION,
            CODE_MISSING_OPTION_VALUE,
            CODE_DUPLICATE_OPTION,
            CODE_MISSING_REQUIRED_OPTION,
            CODE_UNEXPECTED_ARGUMENT,
            CODE_MALFORMED_OPTION,
            CODE_MALFORMED_ARGV,
            CODE_INPUT_TOO_LONG,
            CODE_TOO_MANY_ARGS,
        ):
            self.assertIn(code, CLI_REASON_CODES)


class PurityAndTotalityTest(unittest.TestCase):
    def test_argv_is_not_mutated(self):
        argv = _admit("--type", "create_project", "--key", "k", "--set", "a=1")
        snapshot = list(argv)
        run_cli(argv)
        self.assertEqual(argv, snapshot)

    def test_repeated_evaluation_is_stable(self):
        argv = _admit("--type", "t", "--key", "k", "--expected-version", "1", "--current-version", "2")
        reasons = {run_cli(list(argv)).reason_code for _ in range(5)}
        self.assertEqual(reasons, {CODE_STALE_VERSION})

    def test_never_raises_on_malformed_inputs(self):
        malformed = [
            None,
            "string-not-list",
            123,
            [1, 2, 3],
            ["command", "admit", None],
            ["command", "admit", "--set", "=="],
            ["command", "admit", "--type", "t", "--key", "k", "--current-version", "-1"],
            ["", "", ""],
            ["command", "admit", "--type", "t", "--key", "k", "extra"],
        ]
        for argv in malformed:
            result = run_cli(argv)  # type: ignore[arg-type]
            self.assertIsInstance(result, CliResult)
            self.assertIn(result.status, CLI_STATUSES)


class MainWrapperTest(unittest.TestCase):
    def test_main_returns_exit_code_and_prints_stdout(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["command", "admit", "--type", "create_project", "--key", "k"])
        self.assertEqual(code, 0)
        self.assertIn(CODE_ACCEPTED, out.getvalue())

    def test_main_returns_usage_exit_code_on_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["frobnicate"])
        self.assertEqual(code, 2)
        self.assertTrue(err.getvalue())


if __name__ == "__main__":
    unittest.main()
