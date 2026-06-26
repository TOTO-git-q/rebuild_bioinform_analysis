"""WP-04d / T-04-04: transition definition skeletons for the main states.

These tests pin the new metadata-only layer in
:mod:`auto_bioinfo.core.transition_definitions`:

- the canonical main-state-path skeleton built by
  :func:`build_main_path_definitions` covers every forward edge of
  ``state.MAIN_SEQUENCE`` and invents no states;
- listing / lookup / serialisation are deterministic;
- every defined transition's target is an edge the WP-04c
  :class:`TransitionRegistry` accepts;
- registration fails closed with stable error *codes* on unknown states, an
  edge the transition registry rejects (target mismatch), a duplicate edge, a
  duplicate command id, a duplicate event id, a blank id, or a malformed entry;
  and
- the whole slice is side-effect free (no project file is ever created).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.core import state
from auto_bioinfo.core.state_machine import TransitionRegistry
from auto_bioinfo.core.transition_definitions import (
    CODE_DEF_BLANK_ID,
    CODE_DEF_DUPLICATE_COMMAND_ID,
    CODE_DEF_DUPLICATE_EDGE,
    CODE_DEF_DUPLICATE_EVENT_ID,
    CODE_DEF_MALFORMED,
    CODE_DEF_TARGET_MISMATCH,
    CODE_DEF_UNKNOWN_SOURCE_STATE,
    CODE_DEF_UNKNOWN_TARGET_STATE,
    DEFINITION_ERROR_CODES,
    CommandSkeleton,
    EventSkeleton,
    TransitionDefinition,
    TransitionDefinitionError,
    TransitionDefinitionRegistry,
    build_main_path_definitions,
)

# The canonical forward main-state path: every adjacent pair in MAIN_SEQUENCE.
FORWARD_EDGES = list(zip(state.MAIN_SEQUENCE, state.MAIN_SEQUENCE[1:], strict=False))


def _canonical_registry() -> TransitionRegistry:
    return TransitionRegistry.from_table(state.LINEAR_NEXT)


class CanonicalSkeletonTest(unittest.TestCase):
    def test_covers_every_forward_main_sequence_edge(self):
        defs = build_main_path_definitions()
        self.assertEqual(defs.edges(), sorted(FORWARD_EDGES))
        # 15 main states -> 14 forward edges; COMPLETED is terminal (no out-edge).
        self.assertEqual(len(defs), len(state.MAIN_SEQUENCE) - 1)
        self.assertEqual(len(defs), 14)

    def test_each_definition_target_accepted_by_transition_registry(self):
        # The core T-04-04 contract: every definition's edge is one the WP-04c
        # TransitionRegistry already accepts. None describes a forbidden edge.
        registry = _canonical_registry()
        defs = build_main_path_definitions(registry)
        for d in defs.definitions():
            with self.subTest(edge=d.edge):
                self.assertTrue(registry.is_registered(d.source, d.target))

    def test_explicit_empty_registry_is_honoured_and_fails_closed(self):
        # An explicitly-supplied registry — even an empty one — is an explicit
        # validation surface and must never be silently replaced by the default
        # canonical registry. An empty registry accepts no edge, so building the
        # canonical path must fail closed with the target-mismatch code rather
        # than succeed against the defaulted-in canonical registry.
        empty = TransitionRegistry()
        self.assertEqual(len(empty), 0)
        with self.assertRaises(TransitionDefinitionError) as ctx:
            build_main_path_definitions(empty)
        self.assertEqual(ctx.exception.code, CODE_DEF_TARGET_MISMATCH)

    def test_definitions_use_only_canonical_states(self):
        defs = build_main_path_definitions()
        for d in defs.definitions():
            with self.subTest(edge=d.edge):
                self.assertIn(d.source, state.STAGES)
                self.assertIn(d.target, state.STAGES)

    def test_table_driven_command_and_event_skeletons(self):
        # Table-driven: assert the exact skeleton bound to every forward edge.
        defs = build_main_path_definitions()
        for source, target in FORWARD_EDGES:
            with self.subTest(edge=(source, target)):
                d = defs.get(source, target)
                self.assertIsNotNone(d)
                self.assertEqual(d.command.id, f"CMD_ADVANCE_TO_{target}")
                self.assertEqual(d.command.type, "command")
                self.assertEqual(d.event.id, f"EVT_{target}_ENTERED")
                self.assertEqual(d.event.type, "event")

    def test_command_and_event_ids_are_unique(self):
        defs = build_main_path_definitions()
        self.assertEqual(len(defs.command_ids()), len(defs))
        self.assertEqual(len(defs.event_ids()), len(defs))


class DeterminismTest(unittest.TestCase):
    def test_definitions_listing_is_sorted_by_edge(self):
        defs = build_main_path_definitions()
        listed = [d.edge for d in defs.definitions()]
        self.assertEqual(listed, sorted(listed))

    def test_listing_is_repeatable(self):
        defs = build_main_path_definitions()
        self.assertEqual(defs.to_table(), defs.to_table())
        self.assertEqual(defs.command_ids(), defs.command_ids())
        self.assertEqual(defs.event_ids(), defs.event_ids())

    def test_two_builds_serialise_identically(self):
        self.assertEqual(build_main_path_definitions().to_table(), build_main_path_definitions().to_table())

    def test_to_dict_is_fully_ordered_and_complete(self):
        defs = build_main_path_definitions()
        first = defs.get("INTAKE", "QUESTION_RESOLVED")
        self.assertEqual(
            first.to_dict(),
            {
                "source": "INTAKE",
                "target": "QUESTION_RESOLVED",
                "command": {"id": "CMD_ADVANCE_TO_QUESTION_RESOLVED", "type": "command"},
                "event": {"id": "EVT_QUESTION_RESOLVED_ENTERED", "type": "event"},
                "guard_ref": "",
                "label": "advance INTAKE -> QUESTION_RESOLVED",
            },
        )


class LookupTest(unittest.TestCase):
    def setUp(self):
        self.defs = build_main_path_definitions()

    def test_get_by_edge(self):
        d = self.defs.get("INTAKE", "QUESTION_RESOLVED")
        self.assertEqual(d.edge, ("INTAKE", "QUESTION_RESOLVED"))
        self.assertIsNone(self.defs.get("INTAKE", "COMPLETED"))
        self.assertIsNone(self.defs.get("NOT_A_STAGE", "INTAKE"))

    def test_by_command_id(self):
        d = self.defs.by_command_id("CMD_ADVANCE_TO_QUESTION_RESOLVED")
        self.assertEqual(d.edge, ("INTAKE", "QUESTION_RESOLVED"))
        self.assertIsNone(self.defs.by_command_id("NOPE"))

    def test_by_event_id(self):
        d = self.defs.by_event_id("EVT_QUESTION_RESOLVED_ENTERED")
        self.assertEqual(d.edge, ("INTAKE", "QUESTION_RESOLVED"))
        self.assertIsNone(self.defs.by_event_id("NOPE"))

    def test_membership(self):
        self.assertIn(("INTAKE", "QUESTION_RESOLVED"), self.defs)
        self.assertNotIn(("INTAKE", "COMPLETED"), self.defs)
        self.assertNotIn("not-a-tuple", self.defs)


class GuardRefFieldTest(unittest.TestCase):
    def test_guard_ref_is_optional_metadata_only(self):
        # The guard_ref field is supported (reserved for a later slice) but
        # stores a plain hook-name string; no guard is consulted or executed.
        defs = TransitionDefinitionRegistry(_canonical_registry())
        d = defs.define(
            "INTAKE",
            "QUESTION_RESOLVED",
            command_id="CMD_X",
            event_id="EVT_X",
            guard_ref="needs_question_resolution",
        )
        self.assertEqual(d.guard_ref, "needs_question_resolution")
        self.assertEqual(defs.get("INTAKE", "QUESTION_RESOLVED").guard_ref, "needs_question_resolution")


class RejectionTest(unittest.TestCase):
    def setUp(self):
        self.defs = TransitionDefinitionRegistry(_canonical_registry())

    def _define_ok(self):
        return self.defs.define("INTAKE", "QUESTION_RESOLVED", command_id="CMD_A", event_id="EVT_A")

    def test_unknown_source_rejected(self):
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("NOT_A_STAGE", "QUESTION_RESOLVED", command_id="CMD_A", event_id="EVT_A")
        self.assertEqual(ctx.exception.code, CODE_DEF_UNKNOWN_SOURCE_STATE)
        self.assertEqual(len(self.defs), 0)

    def test_unknown_target_rejected(self):
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("INTAKE", "NOT_A_STAGE", command_id="CMD_A", event_id="EVT_A")
        self.assertEqual(ctx.exception.code, CODE_DEF_UNKNOWN_TARGET_STATE)

    def test_target_mismatch_with_transition_registry_rejected(self):
        # INTAKE -> REPORT_READY is a real pair of states but not an allowed
        # edge in the canonical transition registry: it must fail closed.
        self.assertFalse(_canonical_registry().is_registered("INTAKE", "REPORT_READY"))
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("INTAKE", "REPORT_READY", command_id="CMD_A", event_id="EVT_A")
        self.assertEqual(ctx.exception.code, CODE_DEF_TARGET_MISMATCH)

    def test_duplicate_edge_rejected(self):
        self._define_ok()
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("INTAKE", "QUESTION_RESOLVED", command_id="CMD_B", event_id="EVT_B")
        self.assertEqual(ctx.exception.code, CODE_DEF_DUPLICATE_EDGE)
        self.assertEqual(len(self.defs), 1)

    def test_duplicate_command_id_rejected(self):
        self._define_ok()
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("QUESTION_RESOLVED", "SCOPE_RESOLVED", command_id="CMD_A", event_id="EVT_B")
        self.assertEqual(ctx.exception.code, CODE_DEF_DUPLICATE_COMMAND_ID)
        self.assertEqual(len(self.defs), 1)

    def test_duplicate_event_id_rejected(self):
        self._define_ok()
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("QUESTION_RESOLVED", "SCOPE_RESOLVED", command_id="CMD_B", event_id="EVT_A")
        self.assertEqual(ctx.exception.code, CODE_DEF_DUPLICATE_EVENT_ID)
        self.assertEqual(len(self.defs), 1)

    def test_blank_command_id_rejected(self):
        for bad in ("", "   ", None, 123):
            with self.subTest(bad=bad):
                reg = TransitionDefinitionRegistry(_canonical_registry())
                with self.assertRaises(TransitionDefinitionError) as ctx:
                    reg.define("INTAKE", "QUESTION_RESOLVED", command_id=bad, event_id="EVT_A")
                self.assertEqual(ctx.exception.code, CODE_DEF_BLANK_ID)

    def test_blank_event_id_rejected(self):
        for bad in ("", "   ", None, 123):
            with self.subTest(bad=bad):
                reg = TransitionDefinitionRegistry(_canonical_registry())
                with self.assertRaises(TransitionDefinitionError) as ctx:
                    reg.define("INTAKE", "QUESTION_RESOLVED", command_id="CMD_A", event_id=bad)
                self.assertEqual(ctx.exception.code, CODE_DEF_BLANK_ID)

    def test_blank_command_type_rejected_as_malformed(self):
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("INTAKE", "QUESTION_RESOLVED", command_id="CMD_A", event_id="EVT_A", command_type="  ")
        self.assertEqual(ctx.exception.code, CODE_DEF_MALFORMED)

    def test_ids_are_stripped_for_dedup(self):
        # A whitespace-padded id is canonicalised, so a padded duplicate is still
        # caught (the strip is not a loophole around dedup).
        self.defs.define("INTAKE", "QUESTION_RESOLVED", command_id="  CMD_A  ", event_id="EVT_A")
        self.assertIsNotNone(self.defs.by_command_id("CMD_A"))
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.define("QUESTION_RESOLVED", "SCOPE_RESOLVED", command_id="CMD_A", event_id="EVT_B")
        self.assertEqual(ctx.exception.code, CODE_DEF_DUPLICATE_COMMAND_ID)

    def test_malformed_non_definition_rejected(self):
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.register({"source": "INTAKE", "target": "QUESTION_RESOLVED"})
        self.assertEqual(ctx.exception.code, CODE_DEF_MALFORMED)

    def test_malformed_skeleton_types_rejected(self):
        bad = TransitionDefinition(
            source="INTAKE",
            target="QUESTION_RESOLVED",
            command="not-a-skeleton",  # type: ignore[arg-type]
            event=EventSkeleton(id="EVT_A"),
        )
        with self.assertRaises(TransitionDefinitionError) as ctx:
            self.defs.register(bad)
        self.assertEqual(ctx.exception.code, CODE_DEF_MALFORMED)

    def test_registry_requires_transition_registry(self):
        with self.assertRaises(TransitionDefinitionError) as ctx:
            TransitionDefinitionRegistry("not-a-registry")  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.code, CODE_DEF_MALFORMED)

    def test_every_rejection_code_is_declared(self):
        # Exhaustive: each raised code is part of the published contract.
        cases = [
            lambda: self.defs.define("NOPE", "QUESTION_RESOLVED", command_id="C", event_id="E"),
            lambda: self.defs.define("INTAKE", "NOPE", command_id="C", event_id="E"),
            lambda: self.defs.define("INTAKE", "REPORT_READY", command_id="C", event_id="E"),
        ]
        for case in cases:
            try:
                case()
            except TransitionDefinitionError as exc:
                self.assertIn(exc.code, DEFINITION_ERROR_CODES)


class CompatibilityTest(unittest.TestCase):
    def test_skeletons_carry_no_executable_behaviour(self):
        # CommandSkeleton / EventSkeleton are inert records: id + type only.
        cmd = CommandSkeleton(id="CMD_A")
        evt = EventSkeleton(id="EVT_A")
        self.assertEqual(cmd.to_dict(), {"id": "CMD_A", "type": "command"})
        self.assertEqual(evt.to_dict(), {"id": "EVT_A", "type": "event"})
        self.assertFalse(callable(cmd))
        self.assertFalse(callable(evt))

    def test_default_registry_derives_from_canonical_linear_table(self):
        # Building without an explicit registry still only accepts canonical
        # edges (proving it derived from state.LINEAR_NEXT).
        defs = build_main_path_definitions()
        self.assertEqual(len(defs), len(FORWARD_EDGES))


class SideEffectFreeTest(unittest.TestCase):
    def test_building_and_listing_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = Path(d) / "proj"
            project_dir.mkdir()
            defs = build_main_path_definitions()
            defs.to_table()
            defs.definitions()
            defs.command_ids()
            defs.get("INTAKE", "QUESTION_RESOLVED")
            try:
                defs.define("INTAKE", "REPORT_READY", command_id="C", event_id="E")
            except TransitionDefinitionError:
                pass
            self.assertEqual(list(project_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
