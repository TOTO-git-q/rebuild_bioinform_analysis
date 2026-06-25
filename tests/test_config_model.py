import unittest

from auto_bioinfo.config import (
    AppConfig,
    ConfigError,
    FieldKind,
    SecretRef,
    CONFIG_FIELDS,
    SECRET_FIELDS,
    load_config,
)


def _full_env(**overrides):
    env = {
        "AUTO_BIOINFO_ENV": "test",
        "AUTO_BIOINFO_SERVICE": "api",
        "AUTO_BIOINFO_LOG_LEVEL": "DEBUG",
        "AUTO_BIOINFO_DATABASE_URL": "postgresql://app@db:5432/auto_bioinfo",
    }
    env.update(overrides)
    return env


class ConfigCategoriesTest(unittest.TestCase):
    def test_three_categories_are_distinguished(self):
        kinds = {f.kind for f in CONFIG_FIELDS} | {f.kind for f in SECRET_FIELDS}
        self.assertIn(FieldKind.ENV, kinds)
        self.assertIn(FieldKind.NON_SENSITIVE, kinds)
        self.assertIn(FieldKind.SECRET_REF, kinds)

    def test_secret_fields_are_all_secret_refs(self):
        self.assertTrue(SECRET_FIELDS)
        self.assertTrue(all(f.kind is FieldKind.SECRET_REF for f in SECRET_FIELDS))


class LoadConfigTest(unittest.TestCase):
    def test_full_env_returns_appconfig(self):
        cfg = load_config(_full_env())
        self.assertIsInstance(cfg, AppConfig)
        self.assertEqual(cfg.environment, "test")
        self.assertEqual(cfg.service, "api")
        self.assertEqual(cfg.log_level, "DEBUG")
        self.assertEqual(cfg.database_url, "postgresql://app@db:5432/auto_bioinfo")

    def test_defaults_applied_for_optional_fields(self):
        cfg = load_config({"AUTO_BIOINFO_DATABASE_URL": "postgresql://app@db/x"})
        self.assertEqual(cfg.environment, "dev")
        self.assertEqual(cfg.service, "auto_bioinfo")
        self.assertEqual(cfg.log_level, "INFO")

    def test_missing_required_config_fails_fast(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config({"AUTO_BIOINFO_ENV": "test"})  # no DATABASE_URL
        msg = str(ctx.exception)
        self.assertIn("AUTO_BIOINFO_DATABASE_URL", msg)

    def test_invalid_choice_fails_fast(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(_full_env(AUTO_BIOINFO_ENV="staging"))
        self.assertIn("AUTO_BIOINFO_ENV", str(ctx.exception))

    def test_invalid_log_level_fails_fast(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(_full_env(AUTO_BIOINFO_LOG_LEVEL="LOUD"))
        self.assertIn("AUTO_BIOINFO_LOG_LEVEL", str(ctx.exception))


class SecretReferenceTest(unittest.TestCase):
    def test_secret_refs_hold_names_not_values(self):
        cfg = load_config(_full_env())
        self.assertIn("database_password", cfg.secret_refs)
        ref = cfg.secret_refs["database_password"]
        self.assertIsInstance(ref, SecretRef)
        self.assertEqual(ref.env_var, "AUTO_BIOINFO_DB_PASSWORD")

    def test_secret_value_resolved_lazily_and_not_stored(self):
        cfg = load_config(_full_env(AUTO_BIOINFO_DB_PASSWORD="hunter2-do-not-store"))
        ref = cfg.secret_refs["database_password"]
        # The reference object never embeds the value...
        self.assertNotIn("hunter2-do-not-store", repr(ref))
        # ...but can resolve it on demand from the environment.
        self.assertEqual(
            ref.resolve(_full_env(AUTO_BIOINFO_DB_PASSWORD="hunter2-do-not-store")),
            "hunter2-do-not-store",
        )

    def test_unset_secret_resolves_to_none(self):
        cfg = load_config(_full_env())
        self.assertIsNone(cfg.secret_refs["object_store_secret_key"].resolve({}))

    def test_public_dict_excludes_secret_values(self):
        secret = "top-secret-token-value"
        cfg = load_config(_full_env(AUTO_BIOINFO_DB_PASSWORD=secret))
        view = cfg.public_dict()
        flat = repr(view)
        self.assertNotIn(secret, flat)
        # secret refs are rendered as env-var names only
        self.assertEqual(view["secret_refs"]["database_password"], "AUTO_BIOINFO_DB_PASSWORD")


class DatabaseUrlPasswordGuardTest(unittest.TestCase):
    def test_embedded_password_in_url_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(_full_env(AUTO_BIOINFO_DATABASE_URL="postgresql://app:s3cr3t@db/x"))
        msg = str(ctx.exception)
        # error must name the env var but never echo the secret value
        self.assertIn("AUTO_BIOINFO_DATABASE_URL", msg)
        self.assertNotIn("s3cr3t", msg)

    def test_url_without_credentials_is_accepted(self):
        cfg = load_config(_full_env(AUTO_BIOINFO_DATABASE_URL="postgresql://app@db:5432/x"))
        self.assertEqual(cfg.database_url, "postgresql://app@db:5432/x")


if __name__ == "__main__":
    unittest.main()
