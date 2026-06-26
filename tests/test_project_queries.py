"""WP-04b / T-04-02: read-only control-plane project query layer.

Covers the single-project summary, timeline pagination / stable ordering, list
pagination with malformed / non-project directory handling, the blocker
projection (projection drift, human-review pause, safe-stop terminal, missing
snapshot), and the read-only guarantee that querying never creates or mutates
any project file.
"""

import json
import tempfile
import unittest
from pathlib import Path

from auto_bioinfo.control_plane import (
    CreateProjectCommand,
    ProjectListPage,
    ProjectNotFoundError,
    ProjectQueryError,
    ProjectSummary,
    create_project,
    get_project,
    list_projects,
    project_blockers,
    query_timeline,
)
from auto_bioinfo.control_plane.queries import (
    BLOCKER_HUMAN_REVIEW_REQUIRED,
    BLOCKER_PROJECTION_DRIFT,
    BLOCKER_SAFE_STOP_TERMINAL,
    BLOCKER_SNAPSHOT_MISSING,
)
from auto_bioinfo.core.store import load_project_state, transition_state


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


def _make_project(parent, name, **overrides):
    project_dir = Path(parent) / name
    create_project(_command(project_dir, **overrides))
    return project_dir


def _snapshot_tree(root):
    """Map every file under ``root`` to its bytes (for read-only assertions)."""
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


class SingleProjectQueryTest(unittest.TestCase):
    def test_get_project_returns_complete_deterministic_summary(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = _make_project(d, "proj_q_001")
            summary = get_project(project_dir)

            self.assertIsInstance(summary, ProjectSummary)
            self.assertEqual(summary.project_id, "proj_q_001")
            self.assertEqual(summary.title, "Demo project")
            self.assertEqual(summary.current_stage, "INTAKE")
            # Every reference resolves to a non-empty value.
            for ref in (
                summary.request_id,
                summary.original_request_hash,
                summary.active_policy_id,
                summary.project_state_id,
                summary.created_at,
                summary.updated_at,
            ):
                self.assertTrue(ref)
            self.assertEqual(summary.original_request_ref, "state/objects/original_request.json")
            self.assertEqual(summary.active_policy_ref, "state/objects/project_policy.json")
            # A healthy project is not blocked and has no drift.
            self.assertEqual(summary.drift, [])
            self.assertEqual(summary.blockers, [])
            self.assertFalse(summary.is_blocked)

    def test_summary_matches_persisted_records(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = _make_project(d, "proj_q_002")
            result = create_project(_command(project_dir))  # idempotent replay -> same refs
            summary = get_project(project_dir)
            self.assertEqual(summary.request_id, result.request_id)
            self.assertEqual(summary.active_policy_id, result.project_policy_id)
            self.assertEqual(summary.project_state_id, result.project_state_id)

    def test_get_project_is_deterministic_across_calls(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = _make_project(d, "proj_q_003")
            self.assertEqual(get_project(project_dir).to_dict(), get_project(project_dir).to_dict())

    def test_get_project_rejects_non_project_directory(self):
        with tempfile.TemporaryDirectory() as d:
            plain = Path(d) / "not_a_project"
            plain.mkdir()
            with self.assertRaises(ProjectNotFoundError):
                get_project(plain)


class TimelineQueryTest(unittest.TestCase):
    def _project_with_events(self, parent):
        project_dir = _make_project(parent, "proj_timeline")
        # Append two real transitions so the timeline has > 1 event.
        transition_state(project_dir, "QUESTION_RESOLVED", "QUESTION_RESOLVED", "system", [], "resolved")
        transition_state(project_dir, "SCOPE_RESOLVED", "SCOPE_RESOLVED", "system", [], "scoped")
        return project_dir

    def test_timeline_is_ordered_and_seq_indexed(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = self._project_with_events(d)
            page = query_timeline(project_dir)
            self.assertEqual(page.total, 3)
            self.assertEqual([e.seq for e in page.items], [0, 1, 2])
            self.assertEqual(page.items[0].event_type, "PROJECT_STATE_INITIALIZED")
            self.assertEqual(page.items[0].next_stage, "INTAKE")
            self.assertEqual([e.next_stage for e in page.items], ["INTAKE", "QUESTION_RESOLVED", "SCOPE_RESOLVED"])

    def test_timeline_pagination_page_boundaries_and_stable_ordering(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = self._project_with_events(d)
            full = query_timeline(project_dir).items
            page1 = query_timeline(project_dir, limit=2, offset=0)
            page2 = query_timeline(project_dir, limit=2, offset=2)
            self.assertEqual(page1.total, 3)
            self.assertEqual(page1.returned, 2)
            self.assertEqual(page2.returned, 1)
            # Concatenating the pages reproduces the full ordered timeline exactly.
            recombined = [e.seq for e in page1.items] + [e.seq for e in page2.items]
            self.assertEqual(recombined, [e.seq for e in full])
            # Offset past the end yields an empty (but well-formed) page.
            empty = query_timeline(project_dir, limit=2, offset=10)
            self.assertEqual(empty.returned, 0)
            self.assertEqual(empty.total, 3)

    def test_timeline_rejects_bad_pagination(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = _make_project(d, "proj_tl_bad")
            with self.assertRaises(ProjectQueryError):
                query_timeline(project_dir, offset=-1)
            with self.assertRaises(ProjectQueryError):
                query_timeline(project_dir, limit=-5)

    def test_timeline_rejects_non_project_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ProjectNotFoundError):
                query_timeline(Path(d) / "nope")


class ListProjectsTest(unittest.TestCase):
    def test_list_is_sorted_paginated_and_counts_only_real_projects(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("proj_c", "proj_a", "proj_b"):
                _make_project(d, name)
            # Noise that must never be counted as a project.
            (Path(d) / "plain_dir").mkdir()
            (Path(d) / "loose_file.txt").write_text("noise", encoding="utf-8")

            page = list_projects(d)
            self.assertIsInstance(page, ProjectListPage)
            self.assertEqual(page.total, 3)
            self.assertEqual([e.project_id for e in page.items], ["proj_a", "proj_b", "proj_c"])
            skipped_names = {s.name for s in page.skipped}
            self.assertIn("plain_dir", skipped_names)
            self.assertIn("loose_file.txt", skipped_names)

            # Pagination over the valid projects only.
            first = list_projects(d, limit=2, offset=0)
            second = list_projects(d, limit=2, offset=2)
            self.assertEqual([e.project_id for e in first.items], ["proj_a", "proj_b"])
            self.assertEqual([e.project_id for e in second.items], ["proj_c"])
            self.assertEqual(second.total, 3)

    def test_list_reports_malformed_project_as_skipped_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            _make_project(d, "good_proj")
            # A directory that *looks* like a project (has an event log) but whose
            # log is empty/corrupt must be reported, never counted as a project.
            bad = Path(d) / "bad_proj"
            (bad / "state").mkdir(parents=True)
            (bad / "state" / "events.jsonl").write_text("", encoding="utf-8")

            page = list_projects(d)
            self.assertEqual([e.project_id for e in page.items], ["good_proj"])
            self.assertEqual(page.total, 1)
            self.assertIn("bad_proj", {s.name for s in page.skipped})

    def test_list_rejects_missing_root_and_bad_pagination(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ProjectQueryError):
                list_projects(Path(d) / "no_such_root")
            _make_project(d, "p1")
            with self.assertRaises(ProjectQueryError):
                list_projects(d, offset=-1)


class BlockerProjectionTest(unittest.TestCase):
    def test_human_review_required_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = _make_project(d, "proj_hr")
            transition_state(project_dir, "HUMAN_REVIEW_REQUIRED", "HUMAN_REVIEW_REQUESTED", "system", [], "needs review")
            blockers = project_blockers(project_dir)
            self.assertEqual([b.kind for b in blockers], [BLOCKER_HUMAN_REVIEW_REQUIRED])
            self.assertEqual(blockers[0].stage, "HUMAN_REVIEW_REQUIRED")
            self.assertTrue(get_project(project_dir).is_blocked)

    def test_safe_stop_terminal_is_a_blocker_but_completed_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            failed = _make_project(d, "proj_failed")
            transition_state(failed, "FAILED", "FAILED", "system", [], "stopped")
            blockers = project_blockers(failed)
            self.assertEqual([b.kind for b in blockers], [BLOCKER_SAFE_STOP_TERMINAL])
            self.assertEqual(blockers[0].stage, "FAILED")

    def test_projection_drift_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = _make_project(d, "proj_drift")
            # Tamper the cached snapshot only; the log projection stays authoritative.
            snapshot = load_project_state(project_dir)
            snapshot["status"] = "tampered"
            (project_dir / "state" / "project_state.json").write_text(json.dumps(snapshot), encoding="utf-8")

            summary = get_project(project_dir)
            self.assertEqual(summary.current_stage, "INTAKE")  # rebuilt, not the tampered snapshot
            kinds = [b.kind for b in summary.blockers]
            self.assertEqual(kinds, [BLOCKER_PROJECTION_DRIFT])
            self.assertIn("status", summary.blockers[0].fields)
            self.assertTrue(any(item["field"] == "status" for item in summary.drift))

    def test_missing_snapshot_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            project_dir = _make_project(d, "proj_no_snapshot")
            (project_dir / "state" / "project_state.json").unlink()
            kinds = [b.kind for b in project_blockers(project_dir)]
            self.assertEqual(kinds, [BLOCKER_SNAPSHOT_MISSING])

    def test_blockers_reject_non_project_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ProjectNotFoundError):
                project_blockers(Path(d) / "ghost")


class ReadOnlyGuaranteeTest(unittest.TestCase):
    def test_queries_do_not_create_or_modify_project_files(self):
        with tempfile.TemporaryDirectory() as d:
            _make_project(d, "proj_ro_a")
            _make_project(d, "proj_ro_b")
            (Path(d) / "plain_dir").mkdir()
            (Path(d) / "loose.txt").write_text("x", encoding="utf-8")

            before = _snapshot_tree(d)
            # Exercise every read path.
            get_project(Path(d) / "proj_ro_a")
            query_timeline(Path(d) / "proj_ro_a")
            project_blockers(Path(d) / "proj_ro_a")
            list_projects(d)
            after = _snapshot_tree(d)

            self.assertEqual(before, after)
            # The non-project directory was never given a state/ side effect.
            self.assertFalse((Path(d) / "plain_dir" / "state").exists())


if __name__ == "__main__":
    unittest.main()
