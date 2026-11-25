import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import session_manager as sm  # noqa: E402
from sm_core import find_workspace_root, resolve_paths  # noqa: E402
from sm_db import LATEST_SCHEMA_VERSION, ensure_schema, get_schema_version  # noqa: E402
from sm_router import route_request  # noqa: E402

CLI = SCRIPTS_DIR / "session_manager.py"


def _run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CLI), "--workspace", str(cwd), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


class FullModulesIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_workspace_discovery_and_custom_config_prefix_and_archive(self):
        res = _run_cli(self.root, "init")
        self.assertEqual(res.returncode, 0, res.stderr)

        cfg_path = self.root / ".session-manager" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["task_id_prefix"] = "AGY"
        cfg["archive_completed"] = True
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        nested = self.root / "src" / "pkg"
        nested.mkdir(parents=True)
        self.assertEqual(find_workspace_root(nested), self.root.resolve())

        r_start = _run_cli(
            self.root,
            "task",
            "start",
            "Ship modular CLI",
            "--criterion",
            "Tests pass",
            "--json",
        )
        self.assertEqual(r_start.returncode, 0, r_start.stderr)
        task = json.loads(r_start.stdout)
        self.assertTrue(task["id"].startswith("AGY-"))

        # Must block completion while criterion is unchecked.
        r_fail = _run_cli(self.root, "task", "complete", task["id"])
        self.assertEqual(r_fail.returncode, 1)

        # Check criterion, add progress/evidence, and complete -> should archive.
        self.assertEqual(
            _run_cli(
                self.root,
                "task",
                "update",
                task["id"],
                "--progress",
                "Implemented CLI",
                "--check-criterion",
                "1",
            ).returncode,
            0,
        )
        r_done = _run_cli(
            self.root,
            "task",
            "complete",
            task["id"],
            "--evidence",
            "unittest ok",
            "--json",
        )
        self.assertEqual(r_done.returncode, 0, r_done.stderr)
        done_payload = json.loads(r_done.stdout)
        self.assertTrue(done_payload["completed"])
        self.assertIsNotNone(done_payload["archived"])
        self.assertTrue(Path(done_payload["archived"]).exists())

    def test_task_blockers_cancel_and_sqlite_v1_migration(self):
        _run_cli(self.root, "init")
        db_path = self.root / ".session-manager" / "index.sqlite"
        # Simulate legacy v1 database without schema_migrations.
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE tasks (
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
                  created_at TEXT, updated_at TEXT, source_path TEXT NOT NULL
                );
                CREATE TABLE decisions (
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT, source_path TEXT NOT NULL
                );
                """
            )
        ver = ensure_schema(db_path)
        self.assertEqual(ver, LATEST_SCHEMA_VERSION)
        self.assertEqual(get_schema_version(db_path), LATEST_SCHEMA_VERSION)

        t1 = json.loads(_run_cli(self.root, "task", "start", "Blocked task", "--json").stdout)
        _run_cli(self.root, "task", "update", t1["id"], "--blocker", "Waiting on API spec")
        blocked = json.loads(_run_cli(self.root, "task", "list", "--blocked", "--json").stdout)
        self.assertEqual(len(blocked["tasks"]), 1)
        self.assertEqual(blocked["tasks"][0]["status"], "blocked")

        self.assertEqual(_run_cli(self.root, "task", "cancel", t1["id"], "--reason", "Superseded").returncode, 0)
        q_rows = json.loads(_run_cli(self.root, "index", "query", "--table", "tasks", "--json").stdout)
        self.assertEqual(q_rows["rows"][0]["status"], "cancelled")

    def test_decisions_conflicts_supersedes_and_context_update(self):
        _run_cli(self.root, "init")
        t1 = json.loads(_run_cli(self.root, "task", "start", "Storage design", "--json").stdout)

        r1 = _run_cli(
            self.root,
            "decision",
            "record",
            "Use SQLite local cache",
            "--context",
            "Need fast local queries",
            "--decision",
            "Use SQLite index rebuilt from Markdown",
            "--task",
            t1["id"],
            "--json",
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)
        p1 = json.loads(r1.stdout)
        self.assertEqual(p1["decision"]["id"], "0001")
        self.assertTrue(p1["context_updated"])
        ctx_text = (self.root / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("ADR-0001", ctx_text)

        # Overlapping active ADR without supersedes triggers conflict warning.
        r2 = _run_cli(
            self.root,
            "decision",
            "record",
            "SQLite local cache encryption",
            "--decision",
            "Use SQLite local cache with custom pragmas",
            "--json",
        )
        p2 = json.loads(r2.stdout)
        self.assertTrue(len(p2["conflicts"]) >= 1)

        # Recording a third decision that supersedes 0001 marks 0001 superseded.
        r3 = _run_cli(
            self.root,
            "decision",
            "record",
            "Adopt SQLite FTS5 local cache",
            "--supersedes",
            "0001",
            "--json",
        )
        self.assertEqual(r3.returncode, 0, r3.stderr)
        d1 = json.loads(_run_cli(self.root, "decision", "show", "0001", "--json").stdout)
        self.assertEqual(d1["status"], "superseded")
        self.assertEqual(d1["superseded_by"], "ADR-0003")

    def test_git_recovery_and_verified_handoff(self):
        # Set up a real git repo in temp workspace if git is installed.
        git_check = subprocess.run(["git", "--version"], capture_output=True, check=False)
        if git_check.returncode != 0:
            self.skipTest("git not available")

        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.root, check=True)
        (self.root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        (self.root / "composer.json").write_text('{"name":"demo/app","require":{"php":">=8.2"}}', encoding="utf-8")
        (self.root / ".agent" / "skills").mkdir(parents=True)
        (self.root / ".codex" / "skills").mkdir(parents=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.root, capture_output=True, check=True)

        # Recovery before init should reconstruct inferences safely.
        rec_pre = json.loads(_run_cli(self.root, "recover", "--json").stdout)
        self.assertFalse(rec_pre["initialized"])
        self.assertTrue(any("pyproject.toml" in inf for inf in rec_pre["inferences"]))
        self.assertTrue(any("composer.json" in inf for inf in rec_pre["inferences"]))
        inst_paths = {i["path"] for i in rec_pre["instructions"]}
        self.assertIn(".agent/skills", inst_paths)
        self.assertIn(".codex/skills", inst_paths)

        _run_cli(self.root, "init")
        t = json.loads(_run_cli(self.root, "task", "start", "Implement feature X", "--json").stdout)
        (self.root / "feature.py").write_text("print('wip')\n", encoding="utf-8")

        rec_post = json.loads(_run_cli(self.root, "recover", "--json").stdout)
        self.assertEqual(rec_post["interrupted_task"]["id"], t["id"])
        self.assertEqual(rec_post["git"]["branch"], "main")
        self.assertTrue(any("feature.py" in d for d in rec_post["git"]["dirty_files"]))

        ho = _run_cli(
            self.root,
            "handoff",
            "--summary",
            "Implemented draft feature X",
            "--command",
            "unittest: ok",
            "--next-action",
            "Add edge-case tests",
            "--json",
        )
        self.assertEqual(ho.returncode, 0, ho.stderr)
        ho_data = json.loads(ho.stdout)
        self.assertTrue(ho_data["verified"])
        session_md = (self.root / ".session-manager" / "SESSION.md").read_text(encoding="utf-8")
        self.assertIn("Implemented draft feature X", session_md)
        self.assertIn("feature.py", session_md)
        self.assertIn(t["id"], session_md)

    def test_optimize_diagnostics_and_baseline_comparison(self):
        _run_cli(self.root, "init")
        _run_cli(self.root, "index", "rebuild")
        sample_py = self.root / "work.py"
        sample_py.write_text("total = sum(range(1000))\n", encoding="utf-8")

        r1 = _run_cli(
            self.root,
            "optimize",
            "Diagnose startup",
            "--cmd",
            f'"{sys.executable}" -c "print(1)"',
            "--runs",
            "2",
            "--query",
            "SELECT * FROM tasks WHERE status = 'in_progress'",
            "--profile-py",
            "work.py",
            "--save-baseline",
            "--json",
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)
        p1 = json.loads(r1.stdout)
        self.assertEqual(p1["benchmark"]["runs"], 2)
        self.assertIn("query_plan", p1["sqlite"])
        self.assertIn("elapsed_ms", p1["python_profile"])
        self.assertTrue((self.root / ".session-manager" / "notes" / "perf-baseline.json").exists())

        r2 = _run_cli(self.root, "optimize", "Re-check", "--compare", "--json")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        p2 = json.loads(r2.stdout)
        self.assertIn("comparison", p2)

    def test_audit_security_links_oversized_and_autofix(self):
        _run_cli(self.root, "init")
        _run_cli(self.root, "task", "start", "Audit test")
        _run_cli(self.root, "index", "rebuild")

        # Introduce manual Markdown drift + broken link + secret exposure.
        tasks_path = self.root / ".session-manager" / "TASKS.md"
        tasks_path.write_text(
            tasks_path.read_text(encoding="utf-8")
            + "\n### SM-20260101-998 — Unindexed manual task\n- Status: in_progress\n- Objective: Drift\n- Acceptance criteria:\n  - [ ] ok\n- Next action: fix\n",
            encoding="utf-8",
        )
        ctx = self.root / "PROJECT_CONTEXT.md"
        ctx.write_text(
            ctx.read_text(encoding="utf-8") + "\nSee [missing](docs/nonexistent.md)\nkey = sk-1234567890abcdefghij1234\n",
            encoding="utf-8",
        )
        r_aud = _run_cli(self.root, "audit", "--fix", "--json")
        self.assertEqual(r_aud.returncode, 1)
        report = json.loads(r_aud.stdout)
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("BROKEN_LINK", codes)
        self.assertIn("SECRET_EXPOSURE", codes)
        # Drift should have been auto-fixed by --fix!
        self.assertNotIn("SQLITE_DRIFT", codes)
        self.assertTrue(any("Rebuilt SQLite index" in fx for fx in report["applied_fixes"]))

    def test_router_typos_natural_language_and_safety_gate(self):
        r1 = route_request("/session-manager optmize o sistema está lento")
        self.assertEqual(r1["module"], "optimize")
        self.assertEqual(r1["risk"], "reversible")

        r2 = route_request("Quero retomar de onde parei ontem")
        self.assertEqual(r2["module"], "recover")

        r3 = route_request("/session-manager git push --force origin main")
        self.assertEqual(r3["risk"], "destructive")
        self.assertEqual(r3["interaction_mode"], "require_approval")

    def test_adapters_status_and_non_destructive_install(self):
        r_status = _run_cli(self.root, "adapter", "status", "--json")
        self.assertEqual(r_status.returncode, 0)
        st = json.loads(r_status.stdout)
        self.assertIn("antigravity", st["adapters"])
        self.assertIn("claude-code", st["adapters"])
        self.assertIn("codex", st["adapters"])

        r_dry = _run_cli(self.root, "adapter", "install", "antigravity", "--dry-run", "--json")
        self.assertEqual(r_dry.returncode, 0)
        self.assertFalse((self.root / ".agents" / "workflows" / "session-manager.md").exists())

        r_inst = _run_cli(self.root, "adapter", "install", "claude-code")
        self.assertEqual(r_inst.returncode, 0)
        self.assertTrue((self.root / ".claude" / "commands" / "session-manager.md").is_file())

        # Preserves existing AGENTS.md instead of overwriting.
        (self.root / "AGENTS.md").write_text("# Existing rules\n", encoding="utf-8")
        r_exists = _run_cli(self.root, "adapter", "install", "codex")
        self.assertEqual(r_exists.returncode, 1)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), "# Existing rules\n")


if __name__ == "__main__":
    unittest.main()
