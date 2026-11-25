#!/usr/bin/env python3
"""Versioned SQLite index/cache management with schema migrations."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from sm_core import SkillPaths, now_iso, relpath

LATEST_SCHEMA_VERSION = 2


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _apply_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT,
          updated_at TEXT,
          source_path TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS decisions (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          status TEXT,
          source_path TEXT NOT NULL
        );
        """
    )


def _apply_v2(conn: sqlite3.Connection) -> None:
    task_cols = _table_columns(conn, "tasks")
    for col, ddl in [
        ("objective", "TEXT DEFAULT ''"),
        ("next_action", "TEXT DEFAULT ''"),
        ("blockers", "TEXT DEFAULT ''"),
        ("acceptance_total", "INTEGER DEFAULT 0"),
        ("acceptance_done", "INTEGER DEFAULT 0"),
        ("related_decisions", "TEXT DEFAULT ''"),
    ]:
        if col not in task_cols:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {ddl}")

    decision_cols = _table_columns(conn, "decisions")
    for col, ddl in [
        ("decision_date", "TEXT DEFAULT ''"),
        ("summary", "TEXT DEFAULT ''"),
        ("superseded_by", "TEXT DEFAULT ''"),
    ]:
        if col not in decision_cols:
            conn.execute(f"ALTER TABLE decisions ADD COLUMN {col} {ddl}")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS task_decision_links (
          task_id TEXT NOT NULL,
          decision_id TEXT NOT NULL,
          PRIMARY KEY (task_id, decision_id)
        );
        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recorded_at TEXT NOT NULL,
          branch TEXT NOT NULL,
          active_task_id TEXT NOT NULL,
          summary TEXT NOT NULL,
          source_path TEXT NOT NULL
        );
        """
    )


MIGRATIONS: list[tuple[int, str, Any]] = [
    (1, "Initial tasks and decisions tables", _apply_v1),
    (2, "Extended task/decision metadata, links, and sessions log", _apply_v2),
]


def ensure_schema(db_path: Path) -> int:
    """Create or migrate the SQLite index database to the latest schema version."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL,
              description TEXT NOT NULL
            )
            """
        )
        applied = {
            row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, description, fn in MIGRATIONS:
            if version not in applied:
                fn(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                    (version, now_iso(), description),
                )
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)


def get_schema_version(db_path: Path) -> int:
    """Return the applied schema version, or 0 if uninitialized/missing."""
    if not db_path.exists():
        return 0
    with closing(sqlite3.connect(db_path)) as conn:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not has_table:
            return 0
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)


def sync_index(paths: SkillPaths, tasks: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> int:
    """Rebuild tasks, decisions, and links tables from authoritative Markdown."""
    version = ensure_schema(paths.database_file)
    tasks_rel = relpath(paths.tasks_file, paths.root)
    with closing(sqlite3.connect(paths.database_file)) as conn, conn:
        conn.execute("DELETE FROM task_decision_links")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM decisions")
        for task in tasks:
            related = task.get("decisions", [])
            related_str = ",".join(related)
            blockers_str = "; ".join(task.get("blockers", []))
            criteria = task.get("acceptance_criteria", [])
            done_count = sum(1 for item in criteria if item.get("done"))
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks (
                  id, title, status, created_at, updated_at, source_path,
                  objective, next_action, blockers, acceptance_total, acceptance_done, related_decisions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task["id"],
                    task["title"],
                    task["status"],
                    task.get("created", ""),
                    task.get("updated", ""),
                    tasks_rel,
                    task.get("objective", ""),
                    task.get("next_action", ""),
                    blockers_str,
                    len(criteria),
                    done_count,
                    related_str,
                ),
            )
            for did in related:
                conn.execute(
                    "INSERT OR IGNORE INTO task_decision_links (task_id, decision_id) VALUES (?, ?)",
                    (task["id"], did),
                )

        for dec in decisions:
            conn.execute(
                """
                INSERT OR REPLACE INTO decisions (
                  id, title, status, source_path, decision_date, summary, superseded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dec["id"],
                    dec["title"],
                    dec.get("status", ""),
                    dec["source_path"],
                    dec.get("date", ""),
                    dec.get("decision", ""),
                    dec.get("superseded_by", ""),
                ),
            )
    return version


def record_session_event(
    paths: SkillPaths, branch: str, active_task_id: str, summary: str
) -> None:
    """Append a session snapshot metadata row to SQLite."""
    ensure_schema(paths.database_file)
    with closing(sqlite3.connect(paths.database_file)) as conn, conn:
        conn.execute(
            """
            INSERT INTO sessions (recorded_at, branch, active_task_id, summary, source_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                now_iso(str(paths.config.get("timezone", "UTC"))),
                branch,
                active_task_id,
                summary,
                relpath(paths.session_file, paths.root),
            ),
        )


def query_tasks(
    db_path: Path, status: str | None = None, text: str | None = None
) -> list[dict[str, Any]]:
    """Query indexed tasks from SQLite."""
    if not db_path.exists():
        return []
    ensure_schema(db_path)
    sql = (
        "SELECT id, title, status, created_at, updated_at, objective, next_action, "
        "blockers, acceptance_total, acceptance_done, related_decisions FROM tasks WHERE 1=1"
    )
    params: list[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if text:
        sql += " AND (id LIKE ? OR title LIKE ? OR objective LIKE ? OR next_action LIKE ?)"
        like = f"%{text}%"
        params.extend([like, like, like, like])
    sql += " ORDER BY updated_at DESC, id DESC"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_decisions(
    db_path: Path, status: str | None = None, text: str | None = None
) -> list[dict[str, Any]]:
    """Query indexed decisions from SQLite."""
    if not db_path.exists():
        return []
    ensure_schema(db_path)
    sql = (
        "SELECT id, title, status, decision_date, summary, superseded_by, source_path "
        "FROM decisions WHERE 1=1"
    )
    params: list[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if text:
        sql += " AND (id LIKE ? OR title LIKE ? OR summary LIKE ?)"
        like = f"%{text}%"
        params.extend([like, like, like])
    sql += " ORDER BY id ASC"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def inspect_db_drift(
    db_path: Path, tasks: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> list[str]:
    """Compare SQLite contents and schema against authoritative Markdown records."""
    issues: list[str] = []
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA quick_check").fetchone()
            has_mig = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            if not has_mig:
                issues.append("INDEX: SQLite schema is unversioned (run index rebuild)")
                return issues
            ver_row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            if int(ver_row[0] or 0) < LATEST_SCHEMA_VERSION:
                issues.append("INDEX: SQLite schema is outdated (run index rebuild)")
                return issues
            db_tasks = set(conn.execute("SELECT id, title, status FROM tasks").fetchall())
            db_decisions = set(conn.execute("SELECT id, title, status FROM decisions").fetchall())
    except sqlite3.Error as exc:
        return [f"INDEX: SQLite database is unreadable or incomplete: {exc}"]

    md_tasks = {(t["id"], t["title"], t["status"]) for t in tasks}
    if db_tasks != md_tasks:
        issues.append("DRIFT: SQLite tasks index is out of sync with TASKS.md (run index rebuild)")

    md_decisions = {(d["id"], d["title"], d.get("status", "")) for d in decisions}
    if db_decisions != md_decisions:
        issues.append("DRIFT: SQLite decisions index is out of sync with decisions/*.md (run index rebuild)")

    return issues
