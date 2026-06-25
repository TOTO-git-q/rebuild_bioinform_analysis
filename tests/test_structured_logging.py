import io
import json
import logging
import unittest

from auto_bioinfo.config import load_config
from auto_bioinfo.observability import (
    CANONICAL_FIELDS,
    JsonFormatter,
    REDACTED,
    build_log_payload,
    get_logger,
    is_sensitive_key,
    redact,
)


_FIXED_CLOCK = lambda: "2026-06-25T00:00:00.000000Z"


class RedactionTest(unittest.TestCase):
    def test_sensitive_keys_detected(self):
        for key in ("password", "db_password", "api_token", "Authorization", "secret_key"):
            self.assertTrue(is_sensitive_key(key), key)
        for key in ("service", "project", "message", "count"):
            self.assertFalse(is_sensitive_key(key), key)

    def test_redacts_sensitive_keys(self):
        out = redact({"user": "alice", "password": "hunter2"})
        self.assertEqual(out["user"], "alice")
        self.assertEqual(out["password"], REDACTED)

    def test_redacts_nested_sensitive_keys(self):
        out = redact({"db": {"host": "db", "secret_key": "abc123"}, "items": [{"token": "t"}]})
        self.assertEqual(out["db"]["host"], "db")
        self.assertEqual(out["db"]["secret_key"], REDACTED)
        self.assertEqual(out["items"][0]["token"], REDACTED)

    def test_redacts_inline_bearer_token(self):
        out = redact("called api with Authorization: Bearer abcdef123456")
        self.assertNotIn("abcdef123456", out)
        self.assertIn(REDACTED, out)

    def test_redacts_url_embedded_credentials_in_value(self):
        out = redact({"dsn_note": "connecting to postgresql://app:s3cr3t@db/x"})
        self.assertNotIn("s3cr3t", out["dsn_note"])
        self.assertIn(REDACTED, out["dsn_note"])


class BuildLogPayloadTest(unittest.TestCase):
    def test_payload_has_all_canonical_fields(self):
        payload = build_log_payload(
            level="INFO", message="hi", service="api",
            project="proj1", correlation="corr1", task_run="tr1", clock=_FIXED_CLOCK,
        )
        for field in CANONICAL_FIELDS:
            self.assertIn(field, payload)
        self.assertEqual(payload["time"], "2026-06-25T00:00:00.000000Z")
        self.assertEqual(payload["service"], "api")
        self.assertEqual(payload["project"], "proj1")
        self.assertEqual(payload["correlation"], "corr1")
        self.assertEqual(payload["task_run"], "tr1")
        self.assertEqual(payload["message"], "hi")

    def test_extra_fields_are_redacted(self):
        payload = build_log_payload(
            level="INFO", message="m", service="api",
            fields={"db_host": "db", "db_password": "hunter2"}, clock=_FIXED_CLOCK,
        )
        self.assertEqual(payload["db_host"], "db")
        self.assertEqual(payload["db_password"], REDACTED)

    def test_secret_value_absent_from_serialized_payload(self):
        secret = "super-secret-value-xyz"
        payload = build_log_payload(
            level="INFO", message=f"authorized with Bearer {secret}", service="api",
            fields={"api_key": secret, "token": secret}, clock=_FIXED_CLOCK,
        )
        serialized = json.dumps(payload)
        self.assertNotIn(secret, serialized)


class JsonFormatterTest(unittest.TestCase):
    def _capture(self, service="api", **extra):
        logger = logging.getLogger("test.jsonformatter")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.propagate = False
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter(service=service))
        logger.addHandler(handler)
        logger.info("hello", extra=extra)
        handler.flush()
        return stream.getvalue().strip()

    def test_formatter_emits_valid_json_with_canonical_fields(self):
        line = self._capture(project="p1", correlation="c1", task_run="t1")
        obj = json.loads(line)
        for field in CANONICAL_FIELDS:
            self.assertIn(field, obj)
        self.assertEqual(obj["service"], "api")
        self.assertEqual(obj["project"], "p1")
        self.assertEqual(obj["level"], "INFO")
        self.assertEqual(obj["message"], "hello")

    def test_formatter_redacts_secret_extra(self):
        secret = "leak-me-not-12345"
        line = self._capture(api_token=secret)
        self.assertNotIn(secret, line)
        obj = json.loads(line)
        self.assertEqual(obj["api_token"], REDACTED)


class GetLoggerTest(unittest.TestCase):
    def test_get_logger_does_not_duplicate_handlers(self):
        a = get_logger("worker")
        b = get_logger("worker")
        self.assertEqual(len(a.logger.handlers), len(b.logger.handlers))
        self.assertEqual(len(a.logger.handlers), 1)


class ConfigLoggingIntegrationTest(unittest.TestCase):
    def test_logging_config_public_dict_does_not_leak_secret(self):
        env = {
            "AUTO_BIOINFO_ENV": "test",
            "AUTO_BIOINFO_DATABASE_URL": "postgresql://app@db/x",
            "AUTO_BIOINFO_DB_PASSWORD": "should-never-appear-in-logs",
        }
        cfg = load_config(env)
        payload = build_log_payload(
            level="INFO", message="startup", service=cfg.service,
            fields={"config": cfg.public_dict()}, clock=_FIXED_CLOCK,
        )
        self.assertNotIn("should-never-appear-in-logs", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
