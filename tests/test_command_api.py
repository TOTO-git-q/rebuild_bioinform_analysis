"""Unit tests for the command API idempotency / optimistic-concurrency contract
(WP-04g / T-04-07).

Covers, for the bounded status/reason vocabulary:

- success (a fresh, well-formed command admitted),
- a missing idempotency key,
- a same-key replay (identical command/payload → duplicate) and a same-key
  conflict (different command or payload → fail closed),
- a stale expected version and a malformed expected version,
- duplicated and malformed controlled headers (fail closed), case-insensitive
  header handling, and the missing-expected-version case under enforced
  concurrency,
- deterministic, key-order-independent payload fingerprinting and deterministic
  result serialisation, and
- purity: no mutation of the supplied request/headers/payload and no I/O.
"""

import unittest

from auto_bioinfo.control_plane.command_api import (
    CODE_ACCEPTED,
    CODE_DUPLICATE_HEADER,
    CODE_IDEMPOTENCY_CONFLICT,
    CODE_IDEMPOTENCY_KEY_TOO_LONG,
    CODE_IDEMPOTENT_REPLAY,
    CODE_MALFORMED_COMMAND,
    CODE_MALFORMED_CURRENT_VERSION,
    CODE_MALFORMED_EXPECTED_VERSION,
    CODE_MALFORMED_HEADERS,
    CODE_MALFORMED_IDEMPOTENCY_KEY,
    CODE_MISSING_EXPECTED_VERSION,
    CODE_MISSING_IDEMPOTENCY_KEY,
    CODE_PRIOR_RECORD_MISMATCH,
    CODE_STALE_VERSION,
    EXPECTED_VERSION_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    MAX_IDEMPOTENCY_KEY_LENGTH,
    REASON_CODES,
    STATUS_DUPLICATE,
    STATUS_IDEMPOTENCY_CONFLICT,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_VERSION_CONFLICT,
    STATUSES,
    CommandRecord,
    CommandRequest,
    command_fingerprint,
    evaluate_command_request,
    parse_command_headers,
    record_for,
)

KEY = "idem-key-0001"


def _headers(key=KEY, version=None, extra=None):
    h = {}
    if key is not None:
        h[IDEMPOTENCY_KEY_HEADER] = key
    if version is not None:
        h[EXPECTED_VERSION_HEADER] = version
    if extra:
        h.update(extra)
    return h


def _request(command_type="create_project", payload=None, key=KEY, version=None, extra=None):
    return CommandRequest(
        command_type=command_type,
        payload={"title": "Demo", "n": 3} if payload is None else payload,
        headers=_headers(key=key, version=version, extra=extra),
    )


class VocabularyTest(unittest.TestCase):
    def test_status_and_reason_vocabularies_are_bounded_and_stable(self):
        self.assertEqual(
            STATUSES,
            (STATUS_OK, STATUS_DUPLICATE, STATUS_IDEMPOTENCY_CONFLICT, STATUS_VERSION_CONFLICT, STATUS_INVALID),
        )
        self.assertEqual(len(REASON_CODES), len(set(REASON_CODES)))
        self.assertTrue(all(isinstance(c, str) and c.startswith("COMMAND_") for c in REASON_CODES))


class SuccessTest(unittest.TestCase):
    def test_fresh_well_formed_command_is_accepted(self):
        result = evaluate_command_request(_request())
        self.assertEqual(result.status, STATUS_OK)
        self.assertEqual(result.reason_code, CODE_ACCEPTED)
        self.assertTrue(result.accepted)
        self.assertFalse(result.is_replay)
        self.assertEqual(result.binding["idempotency_key"], KEY)
        self.assertEqual(result.binding["command_fingerprint"], command_fingerprint("create_project", {"title": "Demo", "n": 3}))

    def test_accepted_at_matching_expected_version(self):
        result = evaluate_command_request(_request(version="5"), current_version=5)
        self.assertEqual(result.reason_code, CODE_ACCEPTED)
        self.assertEqual(result.binding["expected_version"], 5)
        self.assertEqual(result.binding["current_version"], 5)


class MissingOrMalformedKeyTest(unittest.TestCase):
    def test_missing_idempotency_key_fails_closed(self):
        result = evaluate_command_request(_request(key=None))
        self.assertEqual(result.status, STATUS_INVALID)
        self.assertEqual(result.reason_code, CODE_MISSING_IDEMPOTENCY_KEY)
        self.assertFalse(result.accepted)

    def test_blank_idempotency_key_is_missing(self):
        result = evaluate_command_request(_request(key="   "))
        self.assertEqual(result.reason_code, CODE_MISSING_IDEMPOTENCY_KEY)

    def test_key_with_internal_whitespace_is_malformed(self):
        result = evaluate_command_request(_request(key="bad key"))
        self.assertEqual(result.reason_code, CODE_MALFORMED_IDEMPOTENCY_KEY)

    def test_overlong_key_is_rejected(self):
        result = evaluate_command_request(_request(key="k" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1)))
        self.assertEqual(result.reason_code, CODE_IDEMPOTENCY_KEY_TOO_LONG)


class MalformedCommandTest(unittest.TestCase):
    def test_blank_command_type_is_rejected(self):
        result = evaluate_command_request(CommandRequest(command_type="  ", payload={}, headers=_headers()))
        self.assertEqual(result.reason_code, CODE_MALFORMED_COMMAND)

    def test_non_dict_payload_is_rejected(self):
        result = evaluate_command_request(CommandRequest(command_type="create_project", payload=[1, 2], headers=_headers()))
        self.assertEqual(result.reason_code, CODE_MALFORMED_COMMAND)

    def test_non_serialisable_non_dict_payload_fails_closed_without_raising(self):
        # A non-dict payload that is itself not JSON-serialisable must be rejected
        # as a bounded invalid result, never raise out of fingerprinting.
        request = CommandRequest(command_type="create_project", payload=object(), headers=_headers())
        result = evaluate_command_request(request)
        self.assertEqual(result.status, STATUS_INVALID)
        self.assertEqual(result.reason_code, CODE_MALFORMED_COMMAND)
        self.assertFalse(result.accepted)
        self.assertEqual(result.binding["command_fingerprint"], "")

    def test_dict_payload_with_non_serialisable_nested_value_fails_closed(self):
        # A dict payload that passes the shape check but contains a nested value
        # that cannot be canonicalised must fail closed, not raise TypeError.
        request = CommandRequest(command_type="create_project", payload={"x": object()}, headers=_headers())
        result = evaluate_command_request(request)
        self.assertEqual(result.status, STATUS_INVALID)
        self.assertEqual(result.reason_code, CODE_MALFORMED_COMMAND)
        self.assertFalse(result.accepted)
        self.assertEqual(result.binding["command_fingerprint"], "")

    def test_non_string_non_serialisable_command_type_fails_closed(self):
        # A non-string command_type that is also not JSON-serialisable must be
        # rejected by the identity check before any fingerprinting is attempted.
        request = CommandRequest(command_type=object(), payload={}, headers=_headers())
        result = evaluate_command_request(request)
        self.assertEqual(result.status, STATUS_INVALID)
        self.assertEqual(result.reason_code, CODE_MALFORMED_COMMAND)
        self.assertFalse(result.accepted)
        self.assertEqual(result.binding["command_fingerprint"], "")

    def test_non_comparable_dict_keys_fail_closed(self):
        # sort_keys canonicalisation cannot order mixed-type keys; that must fail
        # closed as a malformed command rather than raise TypeError.
        request = CommandRequest(command_type="create_project", payload={1: "a", "b": 2}, headers=_headers())
        result = evaluate_command_request(request)
        self.assertEqual(result.status, STATUS_INVALID)
        self.assertEqual(result.reason_code, CODE_MALFORMED_COMMAND)
        self.assertEqual(result.binding["command_fingerprint"], "")


class IdempotencyReplayAndConflictTest(unittest.TestCase):
    def test_same_key_same_payload_is_a_replay(self):
        request = _request()
        prior = record_for(request, KEY)
        result = evaluate_command_request(request, prior=prior)
        self.assertEqual(result.status, STATUS_DUPLICATE)
        self.assertEqual(result.reason_code, CODE_IDEMPOTENT_REPLAY)
        self.assertTrue(result.is_replay)
        self.assertFalse(result.accepted)

    def test_same_key_different_payload_is_a_conflict(self):
        first = _request(payload={"title": "Demo", "n": 3})
        prior = record_for(first, KEY)
        second = _request(payload={"title": "Demo", "n": 4})  # same key, different fact
        result = evaluate_command_request(second, prior=prior)
        self.assertEqual(result.status, STATUS_IDEMPOTENCY_CONFLICT)
        self.assertEqual(result.reason_code, CODE_IDEMPOTENCY_CONFLICT)

    def test_same_key_different_command_type_is_a_conflict(self):
        first = _request(command_type="create_project")
        prior = record_for(first, KEY)
        second = _request(command_type="delete_project")
        result = evaluate_command_request(second, prior=prior)
        self.assertEqual(result.reason_code, CODE_IDEMPOTENCY_CONFLICT)

    def test_prior_keyed_under_a_different_key_fails_closed(self):
        request = _request()
        prior = CommandRecord(idempotency_key="some-other-key", command_fingerprint=request.fingerprint())
        result = evaluate_command_request(request, prior=prior)
        self.assertEqual(result.reason_code, CODE_PRIOR_RECORD_MISMATCH)

    def test_replay_short_circuits_before_version_check(self):
        # A recognised replay returns duplicate even if the version is now stale —
        # the same logical command was already admitted.
        request = _request(version="2")
        prior = record_for(request, KEY)
        result = evaluate_command_request(request, prior=prior, current_version=9)
        self.assertEqual(result.reason_code, CODE_IDEMPOTENT_REPLAY)


class OptimisticConcurrencyTest(unittest.TestCase):
    def test_stale_expected_version_fails_closed(self):
        result = evaluate_command_request(_request(version="4"), current_version=7)
        self.assertEqual(result.status, STATUS_VERSION_CONFLICT)
        self.assertEqual(result.reason_code, CODE_STALE_VERSION)
        self.assertEqual(result.binding["expected_version"], 4)
        self.assertEqual(result.binding["current_version"], 7)

    def test_missing_expected_version_when_enforced_fails_closed(self):
        result = evaluate_command_request(_request(version=None), current_version=2)
        self.assertEqual(result.reason_code, CODE_MISSING_EXPECTED_VERSION)

    def test_malformed_expected_version_fails_closed(self):
        for bad in ("0", "-1", "1.5", "+3", "02", "abc", "9" * 40):
            result = evaluate_command_request(_request(version=bad), current_version=1)
            self.assertEqual(result.reason_code, CODE_MALFORMED_EXPECTED_VERSION, bad)

    def test_malformed_current_version_fails_closed(self):
        result = evaluate_command_request(_request(version="1"), current_version=0)
        self.assertEqual(result.reason_code, CODE_MALFORMED_CURRENT_VERSION)

    def test_expected_version_ignored_when_not_enforced(self):
        # With no current_version supplied, optimistic concurrency is not enforced;
        # a present, well-formed expected version is simply recorded.
        result = evaluate_command_request(_request(version="3"))
        self.assertEqual(result.reason_code, CODE_ACCEPTED)
        self.assertEqual(result.binding["expected_version"], 3)


class HeaderParsingTest(unittest.TestCase):
    def test_case_insensitive_headers_are_parsed(self):
        request = CommandRequest(
            command_type="create_project",
            payload={"x": 1},
            headers=[("IDEMPOTENCY-KEY", KEY), ("if-match-version", "2")],
        )
        result = evaluate_command_request(request, current_version=2)
        self.assertEqual(result.reason_code, CODE_ACCEPTED)
        self.assertEqual(result.binding["idempotency_key"], KEY)

    def test_duplicate_controlled_header_fails_closed(self):
        request = CommandRequest(
            command_type="create_project",
            payload={"x": 1},
            headers=[("Idempotency-Key", KEY), ("idempotency-key", "other")],
        )
        result = evaluate_command_request(request)
        self.assertEqual(result.reason_code, CODE_DUPLICATE_HEADER)

    def test_duplicate_identical_controlled_header_still_fails_closed(self):
        request = CommandRequest(
            command_type="create_project",
            payload={"x": 1},
            headers=[("Idempotency-Key", KEY), ("Idempotency-Key", KEY)],
        )
        result = evaluate_command_request(request)
        self.assertEqual(result.reason_code, CODE_DUPLICATE_HEADER)

    def test_malformed_header_container_fails_closed(self):
        for bad in ("not-a-mapping", [("only-one-element",)], [("Idempotency-Key", 5)], [(5, "v")]):
            result = evaluate_command_request(CommandRequest(command_type="c", payload={}, headers=bad))
            self.assertEqual(result.status, STATUS_INVALID, bad)
            self.assertEqual(result.reason_code, CODE_MALFORMED_HEADERS, bad)

    def test_parse_command_headers_directly_reports_duplicate(self):
        parsed = parse_command_headers([("Idempotency-Key", "a"), ("idempotency-key", "b")])
        self.assertFalse(parsed.ok)
        self.assertEqual(parsed.error_code, CODE_DUPLICATE_HEADER)

    def test_parse_command_headers_absent_headers_ok(self):
        parsed = parse_command_headers(None)
        self.assertTrue(parsed.ok)
        self.assertEqual(parsed.idempotency_key, "")
        self.assertIsNone(parsed.expected_version)

    def test_unrelated_headers_are_ignored(self):
        request = CommandRequest(
            command_type="create_project",
            payload={"x": 1},
            headers={"Idempotency-Key": KEY, "Content-Type": "application/json", "X-Trace": "abc"},
        )
        result = evaluate_command_request(request)
        self.assertEqual(result.reason_code, CODE_ACCEPTED)


class DeterminismAndFingerprintTest(unittest.TestCase):
    def test_fingerprint_is_key_order_independent(self):
        self.assertEqual(
            command_fingerprint("c", {"a": 1, "b": 2}),
            command_fingerprint("c", {"b": 2, "a": 1}),
        )

    def test_fingerprint_changes_with_command_type_or_payload(self):
        base = command_fingerprint("c", {"a": 1})
        self.assertNotEqual(base, command_fingerprint("d", {"a": 1}))
        self.assertNotEqual(base, command_fingerprint("c", {"a": 2}))

    def test_result_serialisation_is_deterministic(self):
        request = _request()
        first = evaluate_command_request(request).to_dict()
        second = evaluate_command_request(request).to_dict()
        self.assertEqual(first, second)
        self.assertEqual(
            list(first.keys()),
            ["status", "reason_code", "message", "accepted", "is_replay", "binding"],
        )


class PurityTest(unittest.TestCase):
    def test_inputs_are_not_mutated(self):
        payload = {"title": "Demo", "n": 3}
        headers = {IDEMPOTENCY_KEY_HEADER: KEY, EXPECTED_VERSION_HEADER: "2"}
        request = CommandRequest(command_type="create_project", payload=payload, headers=headers)
        evaluate_command_request(request, current_version=2)
        self.assertEqual(payload, {"title": "Demo", "n": 3})
        self.assertEqual(headers, {IDEMPOTENCY_KEY_HEADER: KEY, EXPECTED_VERSION_HEADER: "2"})

    def test_repeated_evaluation_is_stable(self):
        request = _request(version="2")
        outcomes = {evaluate_command_request(request, current_version=2).reason_code for _ in range(5)}
        self.assertEqual(outcomes, {CODE_ACCEPTED})


if __name__ == "__main__":
    unittest.main()
