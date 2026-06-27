"""Local CLI command contract foundation (WP-04i / T-04-09).

The smallest deterministic, *local* contract layer the control plane needs so a
future command-line adapter can turn an explicit ``argv`` list into a bounded,
reason-coded result over the existing control-plane contracts — **without ever
running anything, touching the filesystem, or writing to the real console**.

This is the CLI counterpart to the WP-04g command API: where
:func:`auto_bioinfo.control_plane.command_api.evaluate_command_request` decides,
purely, whether a mutating command may be applied, this module decides, purely,
how a caller-supplied ``argv`` *parses* into such a command request and projects
the resulting decision into a stable CLI result (exit-code category, stdout/stderr
message fields, reason code, and an audit binding).  "CLI" here is modelled as
deterministic argument parsing and command-result mapping only — never as a real
deployment, shell side effect, public interface, subprocess, or packaging step.

Design constraints (WP-04i), mirroring the WP-04g command-API and WP-04h
operation-resource style:

- **Pure and deterministic.** :func:`run_cli` and every helper here is a total
  function of its explicit ``argv`` argument.  There is no I/O whatsoever: it
  never reads ``sys.argv``, environment variables, the current working directory,
  files, the network, or a real clock, and it never writes to ``stdout`` /
  ``stderr`` or executes a command.  The same ``argv`` always yields the same
  :class:`CliResult`, and the input list is never mutated.  A thin
  :func:`main` wrapper reads ``sys.argv[1:]`` and prints the result, but it is the
  *only* place that touches the process environment — the core stays directly
  testable and side-effect free.
- **Fail closed.** Every uncertainty resolves to a *non-success* result.  A
  malformed ``argv`` container, an unknown command/subcommand, an unknown or
  duplicated option, a missing required option or option value, a malformed
  numeric option, an unexpected positional argument, and an overlong/blank input
  all yield a bounded ``usage_error`` result with a stable reason code — never an
  unhandled exception and never a process exit.  Semantic command validity is
  delegated to the underlying contract, whose own fail-closed reason code is
  mapped through unchanged.
- **Bounded vocabulary.** The recognised commands/subcommands and their options
  are a small explicit table (:data:`COMMANDS`); the result status is one of
  exactly three exit-code categories (:data:`CLI_STATUSES`); the CLI's own reason
  codes are a small, stable set (:data:`CLI_REASON_CODES`).  A successfully parsed
  command maps to its underlying contract's reason code
  (:data:`auto_bioinfo.control_plane.command_api.REASON_CODES`).  Callers branch
  on the machine-readable code, never the human message.
- **Exact binding.** Every result records the command path it dispatched to and
  the exact parsed facts (command type, idempotency key, versions, payload keys)
  plus the underlying decision it considered, so the CLI outcome can be audited.

This module defines a *contract* only.  It does not register a console-script
entry point, open a socket, run a real server, execute a command, spawn a
subprocess, persist anything, or expose an OpenAPI surface — those are out of
scope for T-04-09 (see the cancel/OpenAPI/auth slices T-04-10..12).  It only
parses and maps, purely, from the ``argv`` it is handed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .command_api import (
    EXPECTED_VERSION_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    STATUS_DUPLICATE,
    STATUS_IDEMPOTENCY_CONFLICT,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_VERSION_CONFLICT,
    CommandApiResult,
    CommandRequest,
    evaluate_command_request,
)

# --- The program name (display only; no entry point is registered) ----------
PROGRAM = "bioctl"

# --- Bounds (so an unbounded input cannot exhaust a downstream parser) -------
# A caller may not hand in an unbounded argv, an unbounded token, or an unbounded
# payload; each fails closed with a bounded reason code rather than being parsed.
MAX_ARGV_ITEMS = 128
MAX_TOKEN_LENGTH = 1024
MAX_PAYLOAD_ENTRIES = 64

# --- Bounded exit-code categories -------------------------------------------
# A future adapter maps the category to a process exit code; the numeric codes
# here are the stable convention (0 success, 2 usage error, 1 domain rejection).
CLI_STATUS_OK = "ok"
CLI_STATUS_USAGE_ERROR = "usage_error"
CLI_STATUS_REJECTED = "rejected"

CLI_STATUSES = (CLI_STATUS_OK, CLI_STATUS_USAGE_ERROR, CLI_STATUS_REJECTED)

EXIT_CODES: dict[str, int] = {
    CLI_STATUS_OK: 0,
    CLI_STATUS_USAGE_ERROR: 2,
    CLI_STATUS_REJECTED: 1,
}

# --- Stable CLI-level reason codes (parse / usage failures) ------------------
# Callers branch on these, so they must stay stable.  A successfully parsed and
# evaluated command instead carries its underlying contract's reason code.
CODE_OK = "CLI_OK"
CODE_MALFORMED_ARGV = "CLI_MALFORMED_ARGV"
CODE_INPUT_TOO_LONG = "CLI_INPUT_TOO_LONG"
CODE_TOO_MANY_ARGS = "CLI_TOO_MANY_ARGS"
CODE_NO_COMMAND = "CLI_NO_COMMAND"
CODE_UNKNOWN_COMMAND = "CLI_UNKNOWN_COMMAND"
CODE_MISSING_SUBCOMMAND = "CLI_MISSING_SUBCOMMAND"
CODE_UNKNOWN_SUBCOMMAND = "CLI_UNKNOWN_SUBCOMMAND"
CODE_UNKNOWN_OPTION = "CLI_UNKNOWN_OPTION"
CODE_MISSING_OPTION_VALUE = "CLI_MISSING_OPTION_VALUE"
CODE_DUPLICATE_OPTION = "CLI_DUPLICATE_OPTION"
CODE_MISSING_REQUIRED_OPTION = "CLI_MISSING_REQUIRED_OPTION"
CODE_UNEXPECTED_ARGUMENT = "CLI_UNEXPECTED_ARGUMENT"
CODE_MALFORMED_OPTION = "CLI_MALFORMED_OPTION"

CLI_REASON_CODES = (
    CODE_OK,
    CODE_MALFORMED_ARGV,
    CODE_INPUT_TOO_LONG,
    CODE_TOO_MANY_ARGS,
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
)

# How an underlying command-API status maps onto a CLI exit-code category: an
# accepted command (or a recognised idempotent replay) is a success; a key/version
# conflict is a domain rejection (the caller may retry with fresh facts); anything
# the contract deems invalid is a usage error.
_COMMAND_STATUS_TO_CLI: dict[str, str] = {
    STATUS_OK: CLI_STATUS_OK,
    STATUS_DUPLICATE: CLI_STATUS_OK,
    STATUS_IDEMPOTENCY_CONFLICT: CLI_STATUS_REJECTED,
    STATUS_VERSION_CONFLICT: CLI_STATUS_REJECTED,
    STATUS_INVALID: CLI_STATUS_USAGE_ERROR,
}


# --- The bounded command/option vocabulary ----------------------------------


@dataclass(frozen=True)
class OptionSpec:
    """One recognised ``--option`` of a subcommand.

    ``required`` options must appear (their *value* may still be empty — semantic
    validity is the underlying contract's job).  A ``repeatable`` option may
    appear more than once and collects a list of values; a non-repeatable option
    appearing twice is a fail-closed duplicate.
    """

    name: str
    required: bool = False
    repeatable: bool = False


@dataclass(frozen=True)
class SubcommandSpec:
    """A subcommand's recognised options and a one-line help summary."""

    summary: str
    options: tuple[OptionSpec, ...]

    def option(self, name: str) -> OptionSpec | None:
        for opt in self.options:
            if opt.name == name:
                return opt
        return None


# Option names for the `command admit` subcommand.
OPT_TYPE = "--type"
OPT_KEY = "--key"
OPT_EXPECTED_VERSION = "--expected-version"
OPT_CURRENT_VERSION = "--current-version"
OPT_SET = "--set"

# The smallest useful slice (T-04-09): a single `command admit` path that maps an
# explicit argv onto the WP-04g command-API admission decision.  The table is
# deliberately small and explicit so an unknown command/subcommand/option fails
# closed, and so later slices (cancel, query, operation) can be added as new
# entries without changing the parser.
COMMANDS: dict[str, dict[str, SubcommandSpec]] = {
    "command": {
        "admit": SubcommandSpec(
            summary="Evaluate whether a mutating command request may be admitted (idempotency + optimistic concurrency).",
            options=(
                OptionSpec(OPT_TYPE, required=True),
                OptionSpec(OPT_KEY),
                OptionSpec(OPT_EXPECTED_VERSION),
                OptionSpec(OPT_CURRENT_VERSION),
                OptionSpec(OPT_SET, repeatable=True),
            ),
        ),
    },
}


# --- The deterministic CLI result -------------------------------------------


@dataclass(frozen=True)
class CliResult:
    """The deterministic, reason-coded outcome of a CLI invocation.

    ``status`` is one of :data:`CLI_STATUSES` (the exit-code category) and
    ``exit_code`` is its stable numeric code.  ``reason_code`` is a stable
    :data:`CLI_REASON_CODES` value for a parse/usage failure, or the underlying
    contract's reason code for a successfully parsed command.  ``stdout`` and
    ``stderr`` carry the human-readable message text a thin wrapper would print
    (exactly one is non-empty); this object never writes to a real stream.
    ``binding`` records the dispatched command path and parsed facts so the
    decision can be audited.
    """

    status: str
    exit_code: int
    reason_code: str
    stdout: str = ""
    stderr: str = ""
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == CLI_STATUS_OK

    def to_dict(self) -> dict[str, Any]:
        """A deterministic projection of the result (stable key order)."""
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "reason_code": self.reason_code,
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "binding": dict(self.binding),
        }


def _result(status: str, reason_code: str, *, stdout: str = "", stderr: str = "", binding: dict[str, Any] | None = None) -> CliResult:
    return CliResult(
        status=status,
        exit_code=EXIT_CODES[status],
        reason_code=reason_code,
        stdout=stdout,
        stderr=stderr,
        binding=dict(binding or {}),
    )


def _usage(reason_code: str, message: str, *, binding: dict[str, Any] | None = None) -> CliResult:
    """A fail-closed usage error: non-zero exit, message on stderr."""
    return _result(CLI_STATUS_USAGE_ERROR, reason_code, stderr=f"{PROGRAM}: {message}", binding=binding)


# --- The parsed invocation (intermediate value) -----------------------------


@dataclass(frozen=True)
class ParsedInvocation:
    """A successfully parsed argv: the command path plus normalised options."""

    command: str
    subcommand: str
    singles: dict[str, str]
    repeated: dict[str, list[str]]


def _validate_argv(argv: Any) -> CliResult | None:
    """Return a fail-closed :class:`CliResult` if ``argv`` is unusable, else ``None``.

    ``argv`` must be a list of single-line strings, each within
    :data:`MAX_TOKEN_LENGTH`, and the list within :data:`MAX_ARGV_ITEMS`.  A
    non-list container, a non-string item, an overlong token, or an overlong list
    fails closed rather than being parsed.
    """
    if not isinstance(argv, list):
        return _usage(CODE_MALFORMED_ARGV, "argv must be a list of strings")
    if len(argv) > MAX_ARGV_ITEMS:
        return _usage(CODE_TOO_MANY_ARGS, f"too many arguments ({len(argv)} > {MAX_ARGV_ITEMS})")
    for item in argv:
        if not isinstance(item, str):
            return _usage(CODE_MALFORMED_ARGV, "every argv item must be a string")
        if len(item) > MAX_TOKEN_LENGTH:
            return _usage(CODE_INPUT_TOO_LONG, f"an argument exceeds the maximum length of {MAX_TOKEN_LENGTH}")
    return None


def _parse_options(spec: SubcommandSpec, tokens: list[str], path_binding: dict[str, Any]) -> ParsedInvocation | CliResult:
    """Parse ``--option value`` / ``--option=value`` tokens against ``spec``, fail-closed.

    A value may be supplied inline (``--name=value``) or as the following token
    (``--name value``); a following token that itself looks like an option (starts
    with ``--``) is treated as a missing value rather than silently consumed.  An
    unknown option, a non-repeatable option supplied twice, a missing value, and an
    unexpected positional argument each fail closed with a stable reason code.
    """
    singles: dict[str, str] = {}
    repeated: dict[str, list[str]] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("--"):
            return _usage(
                CODE_UNEXPECTED_ARGUMENT,
                f"unexpected positional argument {token!r}; options must start with '--'",
                binding=path_binding,
            )
        if "=" in token:
            name, value = token.split("=", 1)
            i += 1
        else:
            name = token
            if i + 1 >= len(tokens) or tokens[i + 1].startswith("--"):
                return _usage(CODE_MISSING_OPTION_VALUE, f"option {name!r} requires a value", binding=path_binding)
            value = tokens[i + 1]
            i += 2

        opt = spec.option(name)
        if opt is None:
            return _usage(CODE_UNKNOWN_OPTION, f"unknown option {name!r}", binding=path_binding)
        if opt.repeatable:
            repeated.setdefault(name, []).append(value)
        else:
            if name in singles:
                return _usage(CODE_DUPLICATE_OPTION, f"option {name!r} may be given at most once", binding=path_binding)
            singles[name] = value

    missing = [opt.name for opt in spec.options if opt.required and opt.name not in singles]
    if missing:
        return _usage(
            CODE_MISSING_REQUIRED_OPTION,
            f"missing required option(s): {', '.join(missing)}",
            binding=path_binding,
        )
    return ParsedInvocation(
        command=str(path_binding["command_path"][0]),
        subcommand=str(path_binding["command_path"][1]),
        singles=singles,
        repeated=repeated,
    )


def _parse_payload(pairs: list[str], path_binding: dict[str, Any]) -> dict[str, str] | CliResult:
    """Build a payload dict from repeated ``--set key=value`` tokens, fail-closed.

    A ``--set`` value must be ``key=value`` with a non-blank key; a repeated key,
    a value missing its ``=``, or more than :data:`MAX_PAYLOAD_ENTRIES` entries
    fails closed rather than silently dropping or overwriting a key.
    """
    payload: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            return _usage(CODE_MALFORMED_OPTION, f"{OPT_SET} value {raw!r} must be of the form key=value", binding=path_binding)
        key, value = raw.split("=", 1)
        if not key:
            return _usage(CODE_MALFORMED_OPTION, f"{OPT_SET} value {raw!r} has a blank key", binding=path_binding)
        if key in payload:
            return _usage(CODE_DUPLICATE_OPTION, f"{OPT_SET} key {key!r} was supplied more than once", binding=path_binding)
        if len(payload) >= MAX_PAYLOAD_ENTRIES:
            return _usage(CODE_TOO_MANY_ARGS, f"too many {OPT_SET} entries (max {MAX_PAYLOAD_ENTRIES})", binding=path_binding)
        payload[key] = value
    return payload


def _parse_current_version(raw: str, path_binding: dict[str, Any]) -> int | CliResult:
    """Parse ``--current-version`` into a base-10 integer, fail-closed.

    Only an ASCII digit string is accepted; anything else is a malformed option.
    Positivity (``>= 1``) is left to the command-API contract, which maps a
    non-positive current version to its own bounded reason code.
    """
    token = raw.strip()
    if not token or not token.isascii() or not token.isdigit():
        return _usage(CODE_MALFORMED_OPTION, f"{OPT_CURRENT_VERSION} {raw!r} must be a non-negative integer", binding=path_binding)
    return int(token)


# --- Per-subcommand mappers (parsed argv -> existing contract decision) ------


def _map_command_admit(parsed: ParsedInvocation, path_binding: dict[str, Any]) -> CliResult:
    """Map a parsed ``command admit`` invocation onto the WP-04g admission decision.

    Builds a :class:`~auto_bioinfo.control_plane.command_api.CommandRequest` from
    the parsed options (the idempotency key and expected version travel as the
    controlled headers the contract already understands) and evaluates it via
    :func:`~auto_bioinfo.control_plane.command_api.evaluate_command_request`.  The
    bounded decision is projected onto a CLI exit-code category; the contract's own
    reason code is mapped through unchanged.  No command is executed or persisted.
    """
    command_type = parsed.singles[OPT_TYPE]

    payload = _parse_payload(parsed.repeated.get(OPT_SET, []), path_binding)
    if isinstance(payload, CliResult):
        return payload

    headers: list[tuple[str, str]] = []
    if OPT_KEY in parsed.singles:
        headers.append((IDEMPOTENCY_KEY_HEADER, parsed.singles[OPT_KEY]))
    if OPT_EXPECTED_VERSION in parsed.singles:
        headers.append((EXPECTED_VERSION_HEADER, parsed.singles[OPT_EXPECTED_VERSION]))

    current_version: int | None = None
    if OPT_CURRENT_VERSION in parsed.singles:
        cv = _parse_current_version(parsed.singles[OPT_CURRENT_VERSION], path_binding)
        if isinstance(cv, CliResult):
            return cv
        current_version = cv

    request = CommandRequest(command_type=command_type, payload=dict(payload), headers=headers)
    decision = evaluate_command_request(request, current_version=current_version)
    return _project_command_decision(decision, parsed, path_binding, payload_keys=sorted(payload))


def _project_command_decision(
    decision: CommandApiResult,
    parsed: ParsedInvocation,
    path_binding: dict[str, Any],
    *,
    payload_keys: list[str],
) -> CliResult:
    """Project a command-API decision onto a deterministic :class:`CliResult`."""
    status = _COMMAND_STATUS_TO_CLI[decision.status]
    binding = dict(path_binding)
    binding.update(
        {
            "command_type": parsed.singles.get(OPT_TYPE, ""),
            "idempotency_key": parsed.singles.get(OPT_KEY, ""),
            "expected_version": parsed.singles.get(OPT_EXPECTED_VERSION, ""),
            "current_version": parsed.singles.get(OPT_CURRENT_VERSION, ""),
            "payload_keys": payload_keys,
            "decision": decision.to_dict(),
        }
    )
    if status == CLI_STATUS_OK:
        stdout = f"{decision.status}: {decision.reason_code} — {decision.message}"
        return CliResult(
            status=status,
            exit_code=EXIT_CODES[status],
            reason_code=decision.reason_code,
            stdout=stdout,
            binding=binding,
        )
    return CliResult(
        status=status,
        exit_code=EXIT_CODES[status],
        reason_code=decision.reason_code,
        stderr=f"{PROGRAM}: {decision.status}: {decision.reason_code} — {decision.message}",
        binding=binding,
    )


# A mapper per (command, subcommand) so dispatch stays explicit and bounded.
_MAPPERS = {
    ("command", "admit"): _map_command_admit,
}


# --- Public entry points -----------------------------------------------------


def run_cli(argv: list[str]) -> CliResult:
    """Parse and evaluate ``argv`` purely, returning a bounded :class:`CliResult`.

    A total function of its explicit ``argv`` list: it never reads ``sys.argv``,
    the environment, the clock, or the filesystem, never writes to a real stream,
    and never raises for a parse or domain condition — every failure is a
    fail-closed :class:`CliResult` with a stable reason code.  Dispatch is driven
    by the bounded :data:`COMMANDS` table; an unknown command/subcommand/option or
    a missing required option is a usage error, while a successfully parsed command
    is mapped onto its underlying control-plane contract decision.
    """
    invalid = _validate_argv(argv)
    if invalid is not None:
        return invalid
    if not argv:
        return _usage(CODE_NO_COMMAND, f"no command given; expected one of: {', '.join(sorted(COMMANDS))}")

    command = argv[0]
    subcommands = COMMANDS.get(command)
    if subcommands is None:
        return _usage(CODE_UNKNOWN_COMMAND, f"unknown command {command!r}; expected one of: {', '.join(sorted(COMMANDS))}")

    rest = argv[1:]
    if not rest:
        return _usage(
            CODE_MISSING_SUBCOMMAND,
            f"command {command!r} requires a subcommand; expected one of: {', '.join(sorted(subcommands))}",
            binding={"command_path": [command]},
        )

    subcommand = rest[0]
    spec = subcommands.get(subcommand)
    if spec is None:
        return _usage(
            CODE_UNKNOWN_SUBCOMMAND,
            f"unknown subcommand {subcommand!r} for {command!r}; expected one of: {', '.join(sorted(subcommands))}",
            binding={"command_path": [command]},
        )

    path_binding: dict[str, Any] = {"program": PROGRAM, "command_path": [command, subcommand]}
    parsed = _parse_options(spec, rest[1:], path_binding)
    if isinstance(parsed, CliResult):
        return parsed

    mapper = _MAPPERS[(command, subcommand)]
    return mapper(parsed, path_binding)


def main(argv: list[str] | None = None) -> int:
    """Thin process wrapper around :func:`run_cli`.

    This is the *only* function in the module that touches the process
    environment: it reads ``sys.argv[1:]`` when ``argv`` is ``None`` and prints the
    result's ``stdout`` / ``stderr`` text before returning the numeric exit code.
    All parsing and decision logic lives in the side-effect-free :func:`run_cli`.
    """
    import sys

    result = run_cli(list(sys.argv[1:]) if argv is None else list(argv))
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.exit_code


__all__ = [
    "PROGRAM",
    "MAX_ARGV_ITEMS",
    "MAX_TOKEN_LENGTH",
    "MAX_PAYLOAD_ENTRIES",
    "CLI_STATUS_OK",
    "CLI_STATUS_USAGE_ERROR",
    "CLI_STATUS_REJECTED",
    "CLI_STATUSES",
    "EXIT_CODES",
    "CODE_OK",
    "CODE_MALFORMED_ARGV",
    "CODE_INPUT_TOO_LONG",
    "CODE_TOO_MANY_ARGS",
    "CODE_NO_COMMAND",
    "CODE_UNKNOWN_COMMAND",
    "CODE_MISSING_SUBCOMMAND",
    "CODE_UNKNOWN_SUBCOMMAND",
    "CODE_UNKNOWN_OPTION",
    "CODE_MISSING_OPTION_VALUE",
    "CODE_DUPLICATE_OPTION",
    "CODE_MISSING_REQUIRED_OPTION",
    "CODE_UNEXPECTED_ARGUMENT",
    "CODE_MALFORMED_OPTION",
    "CLI_REASON_CODES",
    "COMMANDS",
    "OptionSpec",
    "SubcommandSpec",
    "ParsedInvocation",
    "CliResult",
    "run_cli",
    "main",
]
