#!/usr/bin/env python3
"""Core workspace discovery, configuration, Git, and template helpers."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "adapters"

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "project_context": "PROJECT_CONTEXT.md",
    "state_dir": ".session-manager",
    "session_file": ".session-manager/SESSION.md",
    "tasks_file": ".session-manager/TASKS.md",
    "database_file": ".session-manager/index.sqlite",
    "timezone": "UTC",
    "task_id_prefix": "SM",
    "sqlite_gitignored_by_default": True,
    "max_session_lines": 150,
    "max_session_bytes": 12288,
    "archive_completed": False,
}

WORKSPACE_MARKERS = (
    ".session-manager",
    "PROJECT_CONTEXT.md",
    ".git",
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    "pyproject.toml",
    "package.json",
)

AGENT_INSTRUCTION_CANDIDATES = (
    ("AGENTS.md", "codex/cross-agent"),
    ("CLAUDE.md", "claude-code"),
    ("CODEX.md", "codex"),
    ("GEMINI.md", "antigravity/gemini"),
    (".cursorrules", "cursor"),
    (".github/copilot-instructions.md", "copilot"),
    (".agents/skills", "antigravity-skills"),
    (".agent/skills", "antigravity-skills"),
    (".agent/workflows", "antigravity-workflows"),
    (".claude/commands", "claude-commands"),
    (".codex/skills", "codex-skills"),
)


@dataclass(frozen=True)
class SkillPaths:
    """Resolved workspace paths and merged configuration for Session Manager."""

    root: Path
    state_dir: Path
    config_file: Path
    project_context: Path
    session_file: Path
    tasks_file: Path
    database_file: Path
    decisions_dir: Path
    notes_dir: Path
    archive_dir: Path
    config: dict[str, Any]
    config_error: str | None = None


def now_iso(tz_name: str = "UTC") -> str:
    """Return an ISO-8601 timestamp without microseconds."""
    tz = timezone.utc
    if tz_name and tz_name.upper() != "UTC" and ZoneInfo is not None:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
    return datetime.now(tz).replace(microsecond=0).isoformat()


def today_compact(tz_name: str = "UTC") -> str:
    """Return YYYYMMDD date stamp in configured timezone."""
    tz = timezone.utc
    if tz_name and tz_name.upper() != "UTC" and ZoneInfo is not None:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
    return datetime.now(tz).strftime("%Y%m%d")


def find_workspace_root(start: Path | None = None) -> Path:
    """Locate the nearest workspace root by walking up from `start`."""
    origin = (start or Path.cwd()).resolve()
    candidates = [origin, *origin.parents]
    for marker in (".session-manager", "PROJECT_CONTEXT.md", ".git"):
        for directory in candidates:
            if (directory / marker).exists():
                return directory
    for directory in candidates:
        if any((directory / marker).exists() for marker in WORKSPACE_MARKERS):
            return directory
    return origin


def _resolve_under_root(root: Path, rel_or_path: str, fallback: str) -> Path:
    raw = str(rel_or_path or fallback).strip() or fallback
    target = (root / raw).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return (root / fallback).resolve()
    return target


def load_config(root: Path, state_dir: Path | None = None) -> tuple[dict[str, Any], str | None]:
    """Load `.session-manager/config.json` merged over defaults."""
    cfg = dict(DEFAULT_CONFIG)
    cfg_path = (state_dir or (root / DEFAULT_CONFIG["state_dir"])) / "config.json"
    if not cfg_path.exists():
        return cfg, None
    try:
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return cfg, f"{cfg_path.name} must contain a JSON object"
        cfg.update(loaded)
        return cfg, None
    except (json.JSONDecodeError, OSError) as exc:
        return cfg, str(exc)


def resolve_paths(root: Path | None = None) -> SkillPaths:
    """Resolve all Session Manager paths from workspace root and config.json."""
    workspace = (root or find_workspace_root()).resolve()
    default_state = workspace / DEFAULT_CONFIG["state_dir"]
    cfg, cfg_error = load_config(workspace, default_state)
    state_dir = _resolve_under_root(workspace, str(cfg.get("state_dir")), DEFAULT_CONFIG["state_dir"])
    if state_dir != default_state and (state_dir / "config.json").exists():
        cfg, cfg_error = load_config(workspace, state_dir)

    return SkillPaths(
        root=workspace,
        state_dir=state_dir,
        config_file=state_dir / "config.json",
        project_context=_resolve_under_root(
            workspace, str(cfg.get("project_context")), DEFAULT_CONFIG["project_context"]
        ),
        session_file=_resolve_under_root(
            workspace, str(cfg.get("session_file")), DEFAULT_CONFIG["session_file"]
        ),
        tasks_file=_resolve_under_root(
            workspace, str(cfg.get("tasks_file")), DEFAULT_CONFIG["tasks_file"]
        ),
        database_file=_resolve_under_root(
            workspace, str(cfg.get("database_file")), DEFAULT_CONFIG["database_file"]
        ),
        decisions_dir=state_dir / "decisions",
        notes_dir=state_dir / "notes",
        archive_dir=state_dir / "archive",
        config=cfg,
        config_error=cfg_error,
    )


def read_template(name: str) -> str:
    """Read a bundled template file by filename."""
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def write_missing(path: Path, content: str) -> bool:
    """Write `content` only when `path` does not already exist."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def relpath(path: Path, root: Path) -> str:
    """Return a normalized relative path string when inside `root`."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def run_git(root: Path, *args: str, timeout: int = 5) -> tuple[bool, str]:
    """Run a read-only Git command in `root`, degrading gracefully if unavailable."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout).strip()
    return True, proc.stdout.rstrip()


def git_snapshot(root: Path, log_limit: int = 5) -> dict[str, Any]:
    """Collect non-destructive Git repository metadata for recovery and handoff."""
    ok_top, top_out = run_git(root, "rev-parse", "--show-toplevel")
    if not ok_top:
        return {
            "available": False,
            "is_repo": False,
            "branch": "",
            "dirty_files": [],
            "recent_commits": [],
            "diff_stat": "",
            "note": top_out or "Git repository not detected",
        }

    ok_branch, branch = run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    ok_status, status_out = run_git(root, "status", "--short")
    ok_log, log_out = run_git(root, "log", f"-n{log_limit}", "--oneline")
    ok_stat, diff_stat = run_git(root, "diff", "--stat")

    dirty = [line.rstrip() for line in status_out.splitlines() if line.strip()] if ok_status else []
    commits = [line.strip() for line in log_out.splitlines() if line.strip()] if ok_log else []
    return {
        "available": True,
        "is_repo": True,
        "toplevel": top_out,
        "branch": branch if ok_branch else "HEAD",
        "dirty_files": dirty,
        "recent_commits": commits,
        "diff_stat": diff_stat if ok_stat else "",
        "note": "",
    }


def discover_agent_instructions(root: Path) -> list[dict[str, str]]:
    """Discover existing platform-specific agent instruction files in `root`."""
    found: list[dict[str, str]] = []
    for rel, platform in AGENT_INSTRUCTION_CANDIDATES:
        candidate = root / rel
        if candidate.exists():
            kind = "directory" if candidate.is_dir() else "file"
            found.append({"path": rel, "platform": platform, "kind": kind})
    return found
