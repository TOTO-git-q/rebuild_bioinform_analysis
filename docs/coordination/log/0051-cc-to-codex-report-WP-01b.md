---
turn: 0051
from: CC
to: CODEX
type: REPORT
ref: WP-01b
status: OPEN
date: 2026-06-25
---

# REPORT — WP-01b: configuration model + structured logging / redaction

Handles WORK_ORDER turn 0050. Implemented **T-01-03** (unified configuration
model) and **T-01-06** (structured logging fields + sensitive-field filtering)
only. Awaiting Codex independent review.

## Branch / PR / HEAD

- Work branch: `rebuild/wp-01b-config-logging` (pushed to origin).
- PR: **#4** → base `rebuild/auto-bioinfo-core`, state **OPEN**, `mergeable: MERGEABLE`.
- Base baseline: `rebuild/auto-bioinfo-core` @ merge commit `d8311272eab40c3e0038459dd41671ade7536ce4`.
- Full 40-char head SHA: `ecce8f2b95acead55f4f670b3ce4035c9bef6370`.

## Changed files (all NEW, additive only)

```
A  auto_bioinfo/config/__init__.py
A  auto_bioinfo/config/settings.py
A  auto_bioinfo/observability/__init__.py
A  auto_bioinfo/observability/logging.py
A  auto_bioinfo/observability/redaction.py
A  tests/test_config_model.py
A  tests/test_structured_logging.py
```

No existing file modified; no preserved module deleted; CLI / import entry
points unchanged (config + logging are standalone, not wired into the existing
pipeline/CLI, so no product behavior changed).

## T-01-03 → file/test mapping (configuration model)

| Requirement | Code location | Test (class.method) |
|---|---|---|
| Distinguish env vars / non-sensitive / secret refs | `auto_bioinfo/config/settings.py` `FieldKind`, `CONFIG_FIELDS`, `SECRET_FIELDS` | `test_config_model.ConfigCategoriesTest.test_three_categories_are_distinguished`, `.test_secret_fields_are_all_secret_refs` |
| Build resolved config from environment | `settings.py:load_config`, `AppConfig` | `test_config_model.LoadConfigTest.test_full_env_returns_appconfig`, `.test_defaults_applied_for_optional_fields` |
| Required config fails fast, non-secret message | `settings.py:load_config` (missing/invalid collection → `ConfigError`) | `LoadConfigTest.test_missing_required_config_fails_fast`, `.test_invalid_choice_fails_fast`, `.test_invalid_log_level_fails_fast` |
| Secret = reference/name, value never stored/logged | `settings.py:SecretRef` (`resolve()` lazy, `__repr__` shows ref only), `AppConfig.public_dict` | `SecretReferenceTest.test_secret_refs_hold_names_not_values`, `.test_secret_value_resolved_lazily_and_not_stored`, `.test_unset_secret_resolves_to_none`, `.test_public_dict_excludes_secret_values` |
| Secrets not rendered in errors (no value echo) | `settings.py:_database_url_has_embedded_password` + guard in `load_config` | `DatabaseUrlPasswordGuardTest.test_embedded_password_in_url_rejected`, `.test_url_without_credentials_is_accepted` |

## T-01-06 → file/test mapping (structured logging + redaction)

| Requirement | Code location | Test (class.method) |
|---|---|---|
| Canonical fields time/level/service/project/correlation/task_run | `auto_bioinfo/observability/logging.py` `CANONICAL_FIELDS`, `build_log_payload`, `JsonFormatter` | `test_structured_logging.BuildLogPayloadTest.test_payload_has_all_canonical_fields`, `JsonFormatterTest.test_formatter_emits_valid_json_with_canonical_fields` |
| Redaction of sensitive keys & values | `auto_bioinfo/observability/redaction.py` `redact`, `is_sensitive_key`, `SENSITIVE_KEY_PATTERN`, inline value patterns | `RedactionTest.test_sensitive_keys_detected`, `.test_redacts_sensitive_keys`, `.test_redacts_nested_sensitive_keys`, `.test_redacts_inline_bearer_token`, `.test_redacts_url_embedded_credentials_in_value` |
| Tests proving secrets not emitted in logs | redaction applied in `build_log_payload` / `JsonFormatter` | `BuildLogPayloadTest.test_extra_fields_are_redacted`, `.test_secret_value_absent_from_serialized_payload`, `JsonFormatterTest.test_formatter_redacts_secret_extra`, `ConfigLoggingIntegrationTest.test_logging_config_public_dict_does_not_leak_secret` |
| Small/reusable logger for later API/Worker | `logging.py:get_logger` (LoggerAdapter, no handler duplication) | `GetLoggerTest.test_get_logger_does_not_duplicate_handlers` |

## Validation commands and real results

Environment: `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform`.

1. New modules (verbose):
   `python3 -m unittest tests.test_config_model tests.test_structured_logging`
   → `Ran 25 tests` … `OK`.

2. Full suite:
   `python3 -m unittest discover -t . -s tests -p "test_*.py"`
   → `Ran 138 tests in 0.584s` … `OK` (113 baseline + 25 new).

3. Import smoke:
   `python3 -c "import auto_bioinfo; import auto_bioinfo.config; import auto_bioinfo.observability; print('import ok')"`
   → `import ok`.

4. Preserved CLI entry point:
   `python3 -m auto_bioinfo --help` → exit code 0.

5. `git diff --check` → clean (no whitespace/conflict errors).

6. Secret scan over changed files (rg over AWS keys, PEM private keys, GitHub/Slack
   tokens, `key=value` secret assignments), values masked — never printed:
   the only matches are obviously-fake **test placeholder** strings (e.g.
   `secret = "..."` inside the two new test files); no real credentials in any
   committed file. Source modules contain only secret *references* (env-var
   names) and the `***REDACTED***` placeholder.

## Scope / guardrail confirmation

- WP-01b only. **NOT started**: WP-01c, CI / `.github/workflows`, Docker / Compose /
  Dockerfile / container image, database migrations, SBOM, PR/change template,
  Nextflow, GEO, LLM, DESeq2, or any business/scientific analysis logic; **WP-02 NOT started**.
- **R0-02 was NOT started.**
- No hard stop touched (no real human-source data, no external LLM/service, no paid
  service, no public deploy, no destructive/irreversible op, no credential expansion).
- **Nothing was self-merged.** PR #4 left OPEN for CEO merge authority via Codex.
- No coordination system / ruleset / branch-protection / safety-limit change.

Self-reported green is self-reported only; PR #4 awaits Codex independent review.
