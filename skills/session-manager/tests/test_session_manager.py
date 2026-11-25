import importlib.util
import io
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_manager.py"
spec = importlib.util.spec_from_file_location("session_manager", SCRIPT)
sm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm)


class SessionManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / ".session-manager"
        self.templates = SCRIPT.parents[1] / "templates"
        self.patches = [
            patch.object(sm, "ROOT", self.root),
            patch.object(sm, "STATE", self.state),
            patch.object(sm, "CONFIG", self.state / "config.json"),
            patch.object(sm, "SESSION", self.state / "SESSION.md"),
            patch.object(sm, "TASKS", self.state / "TASKS.md"),
            patch.object(sm, "DB", self.state / "index.sqlite"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_init_preserves_existing_project_context(self):
        (self.root / "PROJECT_CONTEXT.md").write_text("user content", encoding="utf-8")
        self.assertEqual(sm.init(), 0)
        self.assertEqual((self.root / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"), "user content")
        self.assertTrue(self.state.exists())

    def test_task_blocks_ignores_html_comments(self):
        sm.init()
        self.assertEqual(sm.task_blocks(), [])

    def test_task_start_creates_record_and_increments_id(self):
        sm.init()
        self.assertEqual(sm.task_start("Investigate matching"), 0)
        self.assertEqual(sm.task_start("Add regression test"), 0)
        tasks = sm.task_blocks()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["title"], "Add regression test")
        self.assertEqual(tasks[1]["title"], "Investigate matching")
        self.assertTrue(tasks[1]["id"].endswith("-001"))
        self.assertTrue(tasks[0]["id"].endswith("-002"))
        self.assertEqual(tasks[0]["status"], "in_progress")

    def test_status_lists_active_and_excludes_completed(self):
        sm.init()
        sm.task_start("Active task")
        sm.task_start("Done task")
        tasks_path = self.state / "TASKS.md"
        tasks_text = tasks_path.read_text(encoding="utf-8").replace("- Status: in_progress", "- Status: completed", 1)
        tasks_path.write_text(tasks_text, encoding="utf-8")

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(sm.status(), 0)
        out = buf.getvalue()
        self.assertIn("Tasks: 2 total, 1 active", out)
        self.assertIn("Active task", out)
        self.assertNotIn("Done task", out)

    def test_handoff_requires_init_and_updates_timestamp(self):
        self.assertEqual(sm.handoff(), 2)
        sm.init()
        self.assertEqual(sm.handoff(), 0)
        session_text = (self.state / "SESSION.md").read_text(encoding="utf-8")
        self.assertRegex(session_text, r"(?m)^- Updated: \d{4}-\d{2}-\d{2}T")

    def test_index_rebuild_indexes_tasks_and_decisions(self):
        sm.init()
        sm.task_start("Build index")
        adr = self.state / "decisions" / "0001-use-sqlite.md"
        adr.write_text("# ADR-0001: Use SQLite index\n\n- Status: accepted\n", encoding="utf-8")

        self.assertEqual(sm.index_rebuild(), 0)
        with closing(sqlite3.connect(sm.DB)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
            decision = conn.execute("SELECT id, title, status FROM decisions").fetchone()
            self.assertEqual(decision, ("0001", "ADR-0001: Use SQLite index", "accepted"))

    def test_audit_passes_after_init(self):
        sm.init()
        self.assertEqual(sm.audit(), 0)

    def test_audit_detects_missing_files_invalid_config_duplicates_and_drift(self):
        self.assertEqual(sm.audit(), 1)
        sm.init()
        sm.task_start("Initial task")
        self.assertEqual(sm.index_rebuild(), 0)
        self.assertEqual(sm.audit(), 0)

        # Manual Markdown edit without rebuilding index should report drift.
        tasks_path = self.state / "TASKS.md"
        tasks_path.write_text(
            tasks_path.read_text(encoding="utf-8")
            + "\n### SM-20260101-999 — Unindexed task\n- Status: in_progress\n- Objective: Drift\n- Acceptance criteria:\n  - [ ] ok\n- Next action: test\n",
            encoding="utf-8",
        )
        self.assertEqual(sm.audit(), 1)
        self.assertEqual(sm.index_rebuild(), 0)
        self.assertEqual(sm.audit(), 0)

        # Duplicate task IDs should fail audit.
        tasks_path = self.state / "TASKS.md"
        first_id = sm.task_blocks()[0]["id"]
        dup_text = tasks_path.read_text(encoding="utf-8") + f"\n### {first_id} — Duplicate\n- Status: in_progress\n"
        tasks_path.write_text(dup_text, encoding="utf-8")
        self.assertEqual(sm.audit(), 1)

        # Corrupt config.json should fail audit.
        (self.state / "config.json").write_text("{not-json", encoding="utf-8")
        self.assertEqual(sm.audit(), 1)

    def test_cli_end_to_end(self):
        cmds = [
            [sys.executable, str(SCRIPT), "init"],
            [sys.executable, str(SCRIPT), "task", "start", "CLI", "smoke", "test"],
            [sys.executable, str(SCRIPT), "status"],
            [sys.executable, str(SCRIPT), "handoff"],
            [sys.executable, str(SCRIPT), "index", "rebuild"],
            [sys.executable, str(SCRIPT), "audit"],
        ]
        for cmd in cmds:
            res = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, check=False)
            self.assertEqual(res.returncode, 0, f"{cmd} failed: {res.stdout}\n{res.stderr}")


if __name__ == "__main__":
    unittest.main()
