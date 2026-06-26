"""WP-04a / T-04-01: CreateProject command handler.

Covers success, verbatim original-request preservation, hash/ref stability,
initial policy binding, timeline reconstruction from the event log, and the
idempotent-retry / same-key-conflict contract (consistent with WP-03b).
"""

import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.control_plane import (
    CreateProjectCommand,
    CreateProjectConflict,
    CreateProjectError,
    create_project,
)
from auto_bioinfo.core.ids import make_stable_id
from auto_bioinfo.core.store import (
    PROJECT_INITIALIZED_EVENT,
    load_events,
    load_state,
    verify_projection,
)
from auto_bioinfo.core.validation import validate_original_request, validate_project_policy
from auto_bioinfo.execution.objects import read_object


def _command(project_dir, **overrides):
    base = dict(
        project_dir=str(project_dir),
        title="Demo project",
        original_text="Is GENEX up-regulated in disease vs control?",
        execution_mode="DEMO",
        automation_level="A1",
    )
    base.update(overrides)
    return CreateProjectCommand(**base)


class CreateProjectSuccessTest(unittest.TestCase):
    def test_create_project_returns_complete_result_and_persists_records(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_demo_001"
            result = create_project(_command(project_dir))

            self.assertEqual(result.project_id, "proj_demo_001")
            self.assertTrue(result.created)
            self.assertFalse(result.idempotent_replay)
            self.assertEqual(result.current_stage, "INTAKE")
            # Every reference in the result is non-empty and resolvable.
            for ref in (result.request_id, result.project_policy_id, result.project_state_id, result.event_id, result.idempotency_key):
                self.assertTrue(ref)

            request = read_object(project_dir, "original_request", {})
            policy = read_object(project_dir, "project_policy", {})
            project = read_object(project_dir, "project", {})
            self.assertEqual(request["request_id"], result.request_id)
            self.assertEqual(policy["project_policy_id"], result.project_policy_id)
            self.assertEqual(project["request_ids"], [result.request_id])
            self.assertEqual(project["active_policy_id"], result.project_policy_id)
            # The persisted contract objects are themselves valid.
            self.assertEqual(validate_original_request(request), [])
            self.assertEqual(validate_project_policy(policy), [])


class OriginalRequestVerbatimTest(unittest.TestCase):
    def test_original_text_is_stored_verbatim_and_hash_bound(self):
        text = "  Compare  TUMOR vs NORMAL — keep   spacing & punctuation!  "
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_verbatim"
            create_project(_command(project_dir, original_text=text))
            request = read_object(project_dir, "original_request", {})
            # Stored byte-for-byte; normalisation never overwrites the original.
            self.assertEqual(request["original_text"], text)
            self.assertEqual(request["normalized_text"], "")
            # The recorded hash independently checks the original (validator agrees).
            self.assertEqual(validate_original_request(request), [])


class HashAndRefStabilityTest(unittest.TestCase):
    def test_ids_and_hashes_are_deterministic(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            # Same project_id + same payload => same content-addressed refs.
            a = create_project(_command(Path(d1) / "proj_stable"))
            b = create_project(_command(Path(d2) / "proj_stable"))
            self.assertEqual(a.request_id, b.request_id)
            self.assertEqual(a.project_policy_id, b.project_policy_id)
            self.assertEqual(a.idempotency_key, b.idempotency_key)
            pol_a = read_object(Path(d1) / "proj_stable", "project_policy", {})
            pol_b = read_object(Path(d2) / "proj_stable", "project_policy", {})
            self.assertEqual(pol_a["content_hash"], pol_b["content_hash"])


class InitialPolicyBindingTest(unittest.TestCase):
    def test_state_is_bound_to_the_exact_policy_reference(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_bind"
            result = create_project(_command(project_dir, execution_mode="DEMO"))
            state = load_state(project_dir)
            policy = read_object(project_dir, "project_policy", {})
            self.assertEqual(state["project_policy_ref"], policy["project_policy_id"])
            self.assertEqual(state["project_policy_ref"], result.project_policy_id)
            self.assertEqual(state["execution_mode"], policy["execution_mode"])


class TimelineReconstructionTest(unittest.TestCase):
    def test_creation_is_provable_from_the_event_log_alone(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_timeline"
            result = create_project(_command(project_dir))

            events = load_events(project_dir)
            self.assertEqual(len(events), 1)
            creation = events[0]
            self.assertEqual(creation["event_type"], PROJECT_INITIALIZED_EVENT)
            self.assertEqual(creation["previous_stage"], "")
            self.assertEqual(creation["next_stage"], "INTAKE")
            self.assertEqual(creation["event_id"], result.event_id)
            self.assertEqual(creation["payload"]["project_policy_ref"], result.project_policy_id)

            # The verbatim request is recoverable from the timeline: the request id
            # recomputed from the event's recorded question matches the stored one.
            recomputed = make_stable_id(
                "original_request",
                {"project_id": result.project_id, "original_text": creation["payload"]["user_question"]},
            )
            self.assertEqual(recomputed, result.request_id)

            # State rebuilt purely from the log matches the cached snapshot (no drift).
            self.assertEqual(load_state(project_dir)["current_stage"], "INTAKE")
            self.assertEqual(verify_projection(project_dir), [])


class IdempotencyTest(unittest.TestCase):
    def test_true_retry_returns_existing_record_without_a_second_event(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_retry"
            first = create_project(_command(project_dir, command_id="cmd-001"))
            second = create_project(_command(project_dir, command_id="cmd-001"))

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertTrue(second.idempotent_replay)
            self.assertEqual(first.request_id, second.request_id)
            self.assertEqual(first.project_policy_id, second.project_policy_id)
            self.assertEqual(first.event_id, second.event_id)
            self.assertEqual(len(load_events(project_dir)), 1)

    def test_derived_key_makes_byte_identical_replays_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_derived"
            create_project(_command(project_dir))
            second = create_project(_command(project_dir))
            self.assertTrue(second.idempotent_replay)
            self.assertEqual(len(load_events(project_dir)), 1)

    def test_same_key_conflicting_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_conflict"
            create_project(_command(project_dir, command_id="cmd-x", original_text="question A"))
            with self.assertRaises(CreateProjectConflict):
                create_project(_command(project_dir, command_id="cmd-x", original_text="question B (different)"))
            # The original project is untouched: still one event, original request kept.
            self.assertEqual(len(load_events(project_dir)), 1)
            self.assertEqual(read_object(project_dir, "original_request", {})["original_text"], "question A")

    def test_existing_project_with_different_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj_existing"
            create_project(_command(project_dir, original_text="question A"))
            # No explicit key + different payload => different derived key => refused.
            with self.assertRaises(CreateProjectError):
                create_project(_command(project_dir, original_text="totally different question"))
            self.assertEqual(len(load_events(project_dir)), 1)


class InvalidInputTest(unittest.TestCase):
    def test_invalid_project_directory_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "Invalid Name"  # uppercase + whitespace
            with self.assertRaises(CreateProjectError):
                create_project(_command(project_dir))


if __name__ == "__main__":
    unittest.main()
