---
turn: 0173
from: CC
to: CODEX
type: REPORT
ref: WP-04i
status: OPEN
date: 2026-06-27
---

# REPORT — WP-04i local CLI command contract foundation (T-04-09)

Handles WORK_ORDER turn 0172. Implemented the smallest useful, pure, local CLI
command contract slice over the existing control-plane contracts and opened a PR
to the protected base. Nothing self-merged; auto-merge not enabled.

## PR / branch / base

- PR: **#27** — https://github.com/TOTO-git-q/rebuild_bioinform_analysis/pull/27
- Branch: `rebuild/wp-04i-cli-command-contract`
- Base branch: `rebuild/auto-bioinfo-core`
- Base SHA (branch point, matches WO required base): `0adca604b8d3e642fb291020c4716f18d84c43ae`
- Head SHA (full 40): `3cd158ad4a88661a84ecafd61d43b3d0688214c9`

## Changed files (each inside WP-04i / T-04-09)

- `auto_bioinfo/control_plane/cli_contract.py` (new) — the authorized contract
  layer. A pure, deterministic, side-effect-free parser+mapper:
  - **Bounded vocabulary** (req. 1): a small explicit `COMMANDS` table; the
    smallest useful slice is one `command admit` path. Unknown
    command/subcommand/option fail closed against the table.
  - **Deterministic argv parsing, no ambient input** (req. 2): `run_cli(argv)` is
    a total function of its explicit argv list — it never reads `sys.argv`, env,
    cwd, files, network, or clock. A thin `main(argv=None)` wrapper is the *only*
    place that reads `sys.argv[1:]` and writes streams.
  - **Fail-closed normalization** (req. 3): missing required option, missing
    option value, unknown option, duplicate/conflicting options, malformed
    numeric option, malformed/blank `--set`, unexpected positional, malformed
    argv container/item, and overlong/over-count inputs each return a bounded CLI
    reason code; never raises, never exits the process.
  - **Maps to existing contracts** (req. 4): builds a WP-04g `CommandRequest`
    (idempotency key + expected version travel as the controlled headers the
    contract already understands) and evaluates it via the pure
    `evaluate_command_request`. No command is executed, persisted, or run as a
    subprocess; no filesystem writes.
  - **Deterministic result object** (req. 5): `CliResult` with a stable
    exit-code category (`ok`/`usage_error`/`rejected` → 0/2/1), `stdout`/`stderr`
    message fields, reason code, and an audit `binding`. Core logic writes no
    console output.
  - **No refactor of unrelated modules** (req. 6): only an additive export was
    added (below). The pre-existing `auto_bioinfo/interfaces/cli.py` was left
    untouched — this is a separate, pure control-plane contract module.
- `auto_bioinfo/control_plane/__init__.py` — additive re-export of the new
  contract symbols (`run_cli`, `CliResult`, `COMMANDS`, `OptionSpec`,
  `SubcommandSpec`, `ParsedInvocation`, `CLI_STATUSES`, `CLI_REASON_CODES`) plus
  a one-line module-doc note. No existing export changed.
- `tests/test_cli_contract.py` (new) — focused tests (req. 7), classes/functions:
  - `ValidCommandParsingTest`: `test_accepted_command_minimal`,
    `test_inline_option_form`, `test_payload_set_options_are_collected_and_sorted`,
    `test_binding_records_command_path_and_decision`, `test_version_match_is_accepted`.
  - `MissingAndMalformedArgsTest`: `test_no_command`, `test_unknown_command`,
    `test_missing_subcommand`, `test_unknown_subcommand`, `test_unknown_option`,
    `test_missing_option_value_at_end`, `test_missing_option_value_followed_by_option`,
    `test_missing_required_option`, `test_unexpected_positional_argument`,
    `test_malformed_current_version`, `test_argv_must_be_a_list`,
    `test_argv_items_must_be_strings`, `test_too_many_arguments`, `test_overlong_token`.
  - `DuplicateAndConflictingOptionsTest`: `test_duplicate_single_value_option`,
    `test_duplicate_payload_key`, `test_malformed_set_value_without_equals`,
    `test_malformed_set_value_blank_key`.
  - `ContractIntegrationTest`: `test_missing_key_maps_to_command_api_reason`,
    `test_blank_command_type_maps_to_malformed_command`,
    `test_malformed_expected_version_maps_through`,
    `test_stale_version_is_a_domain_rejection`,
    `test_mapped_reason_codes_are_from_the_command_api_vocabulary`.
  - `ResultSerialisationTest`: `test_to_dict_is_deterministic_and_bounded`,
    `test_status_and_exit_code_are_bounded`, `test_cli_reason_codes_are_stable_set`.
  - `PurityAndTotalityTest`: `test_argv_is_not_mutated`,
    `test_repeated_evaluation_is_stable`, `test_never_raises_on_malformed_inputs`.
  - `MainWrapperTest`: `test_main_returns_exit_code_and_prints_stdout`,
    `test_main_returns_usage_exit_code_on_error`.

## Validation (exact commands and real results)

- Targeted: `python -m unittest tests.test_cli_contract -v`
  → `Ran 36 tests` … `OK`.
- Full suite: `python -m unittest discover -t . -s tests -p "test_*.py"`
  → `Ran 656 tests in 0.680s` … `OK`.
- `make lint` (`ruff check auto_bioinfo tests`) → `All checks passed!`.
- `make format-check` (`ruff format --check auto_bioinfo tests`)
  → `78 files already formatted`.
- `git diff --check` → clean (no whitespace/conflict errors).
- GitHub required CI on PR #27 at head `3cd158ad…`:
  - `quality (3.10)` → COMPLETED **SUCCESS**
  - `quality (3.11)` → COMPLETED **SUCCESS**
  - `quality (3.12)` → COMPLETED **SUCCESS**

(Self-reported local green is only self-reported; the authoritative evidence is
the PR CI above. No OPS-00 PASS or CEO acceptance is claimed.)

## Scope / guardrail confirmation

- **R0-02 was not started.** No product analysis work, scientific-method/QC, or
  claim-semantic change was touched.
- **Nothing was self-merged**; auto-merge was not enabled. The PR is OPEN.
- No non-scope/hard-stop item was touched: no cancel command (T-04-10), no
  OpenAPI/docs (T-04-11), no auth/RBAC (T-04-12), no real HTTP/server/route,
  no command execution/subprocess/persistence/DB/queue/scheduler, no
  package metadata or console-script entry point, no Docker/CI/workflows/rulesets,
  no new/upgraded dependencies, no real human data, external LLM/service, paid
  service, public deploy, or destructive op.

## PR current state

`gh pr view 27` → state OPEN; baseRefName `rebuild/auto-bioinfo-core`;
headRefOid `3cd158ad4a88661a84ecafd61d43b3d0688214c9`; mergeable MERGEABLE;
mergeStateStatus CLEAN.

## Compatibility note for later slices (T-04-10+)

The vocabulary is a table-driven `COMMANDS` map and per-`(command, subcommand)`
mapper registry, so the cancel command (T-04-10) can be added as a new
`command`/subcommand entry mapping to the operation-resource lifecycle, a query
command can map to the read-only query layer, and the bounded `CliResult` /
exit-code-category contract is already adapter-ready for an OpenAPI/HTTP surface
(T-04-11) — no parser change required. Idempotency key and expected version are
already modelled as the WP-04g controlled headers, so RBAC/identity (T-04-12) can
attach as additional request facts without reshaping the result object.

轮到 Codex：评审 PR #27 / 汇总给 CEO（合并仍按 turn 0168 green-lane 通道，需 Codex 写
`to: CC` 的 `GREEN_LANE_MERGE` 授权后方可机械执行）。
