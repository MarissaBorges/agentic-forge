#!/usr/bin/env python3
"""Context Recovery and Session Handoff automation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sm_core import (
    SkillPaths,
    discover_agent_instructions,
    git_snapshot,
    now_iso,
    relpath,
)
from sm_db import record_session_event
from sm_decisions import parse_decisions
from sm_tasks import parse_tasks


def _read_trimmed(path: Path, max_lines: int = 80) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[:max_lines]


def _extract_session_bullets(text: str, heading: str) -> list[str]:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text)
    if not match:
        return []
    items: list[str] = []
    for line in match.group(1).splitlines():
        cleaned = re.sub(r"^(?:-|\d+\.)\s*", "", line).strip()
        if cleaned and not cleaned.startswith("Command:") and not cleaned.startswith("Result:"):
            items.append(cleaned)
    return items


def _infer_project_stack(root: Path) -> list[str]:
    signals: list[str] = []
    if (root / "composer.json").exists():
        try:
            comp = json.loads((root / "composer.json").read_text(encoding="utf-8"))
            name = comp.get("name") or root.name
            php_ver = comp.get("require", {}).get("php", "")
            ver_note = f", php {php_ver}" if php_ver else ""
            signals.append(f"PHP project '{name}' (composer.json detected{ver_note})")
        except Exception:
            signals.append("PHP project (composer.json detected)")
    if (root / "pyproject.toml").exists():
        signals.append("Python project (pyproject.toml detected)")
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            name = pkg.get("name") or root.name
            signals.append(f"Node/JS project '{name}' (package.json detected)")
        except Exception:
            signals.append("Node/JS project (package.json detected)")
    if (root / "Cargo.toml").exists():
        signals.append("Rust project (Cargo.toml detected)")
    if (root / "go.mod").exists():
        signals.append("Go project (go.mod detected)")
    if (root / "SKILL.md").exists():
        signals.append("Agent skill package (SKILL.md detected)")
    for doc_name in ("README.md", "tasks.md", "PRODUCT.md", "DESIGN.md", "docs/architecture.md"):
        if (root / doc_name).exists():
            signals.append(f"Existing project documentation/plan found: {doc_name}")
    return signals


def build_recovery_report(paths: SkillPaths) -> dict[str, Any]:
    """Selectively inspect workspace state and separate facts, inferences, and unknowns."""
    instructions = discover_agent_instructions(paths.root)
    git = git_snapshot(paths.root)
    tasks = parse_tasks(paths)
    decisions = parse_decisions(paths)

    active_tasks = [t for t in tasks if t["status"] not in ("completed", "cancelled")]
    blocked_tasks = [t for t in active_tasks if t["status"] == "blocked" or t.get("blockers")]
    interrupted = next((t for t in active_tasks if t["status"] == "in_progress"), None)
    if not interrupted and active_tasks:
        interrupted = active_tasks[0]

    confirmed_facts: list[str] = [f"Workspace root: {paths.root}"]
    inferences: list[str] = []
    unknowns: list[str] = []

    if instructions:
        inst_list = ", ".join(f"{i['path']} ({i['platform']})" for i in instructions)
        confirmed_facts.append(f"Agent instructions found: {inst_list}")
    else:
        unknowns.append("No platform instruction files found (AGENTS.md, CLAUDE.md, CODEX.md, GEMINI.md).")

    if git["is_repo"]:
        confirmed_facts.append(
            f"Git branch: {git['branch']} | Uncommitted changes: {len(git['dirty_files'])}"
        )
        if git["recent_commits"]:
            confirmed_facts.append(f"Latest commit: {git['recent_commits'][0]}")
    else:
        unknowns.append(f"Git state unavailable ({git.get('note', 'not a git repository')}).")

    # Selective reads
    session_exists = paths.session_file.exists()
    context_exists = paths.project_context.exists()
    tasks_exists = paths.tasks_file.exists()

    if context_exists:
        ctx_text = paths.project_context.read_text(encoding="utf-8")
        last_verified = re.search(r"Last verified:\s*(.+)", ctx_text)
        if last_verified and "YYYY-MM-DD" not in last_verified.group(1):
            confirmed_facts.append(f"PROJECT_CONTEXT.md last verified: {last_verified.group(1).strip()}")
        else:
            unknowns.append("PROJECT_CONTEXT.md exists but 'Last verified' is still placeholder YYYY-MM-DD.")
    else:
        unknowns.append("PROJECT_CONTEXT.md is missing; reconstructing baseline facts from repository markers.")
        inferences.extend(_infer_project_stack(paths.root))

    last_checkpoint = ""
    if session_exists:
        sess_text = paths.session_file.read_text(encoding="utf-8")
        upd = re.search(r"^- Updated:\s*(.+)$", sess_text, flags=re.M)
        last_checkpoint = upd.group(1).strip() if upd else ""
        if last_checkpoint:
            confirmed_facts.append(f"Last SESSION.md checkpoint: {last_checkpoint}")
        else:
            unknowns.append("SESSION.md exists but has no recorded handoff timestamp.")
    else:
        unknowns.append("SESSION.md is missing (run `init` or `handoff` to create a session snapshot).")

    if tasks_exists:
        confirmed_facts.append(
            f"Tasks: {len(active_tasks)} active ({len(blocked_tasks)} blocked) out of {len(tasks)} total."
        )
        if interrupted:
            confirmed_facts.append(
                f"Primary active/interrupted task: {interrupted['id']} [{interrupted['status']}] {interrupted['title']}"
            )
    else:
        unknowns.append("TASKS.md is missing.")

    if decisions:
        accepted = [d for d in decisions if d.get("status") == "accepted"]
        confirmed_facts.append(f"Decisions: {len(decisions)} ADR(s), {len(accepted)} accepted.")

    if interrupted and git.get("dirty_files"):
        inferences.append(
            f"Uncommitted files ({len(git['dirty_files'])}) likely belong to active task {interrupted['id']} — verify with git diff before editing."
        )
    elif not context_exists and not session_exists:
        inferences.append("Session Manager has not been initialized in this workspace yet.")

    next_actions: list[str] = []
    if not (paths.state_dir.exists() and context_exists and tasks_exists):
        next_actions.append("Run `session_manager.py init` to initialize missing Session Manager artifacts.")
    if interrupted and interrupted.get("next_action"):
        next_actions.append(f"Resume {interrupted['id']}: {interrupted['next_action']}")
    elif not active_tasks:
        next_actions.append("Start a tracked task with `task start \"<goal>\"`.")
    if git.get("dirty_files"):
        next_actions.append("Inspect uncommitted changes with `git status --short` before making new edits.")

    read_first = [i["path"] for i in instructions if i["kind"] == "file"]
    for p in (paths.session_file, paths.project_context, paths.tasks_file):
        if p.exists():
            read_first.append(relpath(p, paths.root))

    return {
        "workspace": str(paths.root),
        "initialized": paths.state_dir.exists(),
        "instructions": instructions,
        "git": git,
        "active_tasks": active_tasks,
        "blocked_tasks": blocked_tasks,
        "interrupted_task": interrupted,
        "decisions_count": len(decisions),
        "last_checkpoint": last_checkpoint,
        "confirmed_facts": confirmed_facts,
        "inferences": inferences,
        "unknowns": unknowns,
        "next_actions": next_actions[:3],
        "read_first": read_first,
    }


def create_handoff(
    paths: SkillPaths,
    summary: str | None = None,
    commands: list[str] | None = None,
    decisions: list[str] | None = None,
    blockers: list[str] | None = None,
    next_actions: list[str] | None = None,
    read_first: list[str] | None = None,
) -> dict[str, Any]:
    """Generate and persist a complete `.session-manager/SESSION.md` handoff snapshot."""
    if not paths.state_dir.exists():
        raise FileNotFoundError("Session Manager not initialized. Run `init` first.")

    stamp = now_iso(str(paths.config.get("timezone", "UTC")))
    git = git_snapshot(paths.root)
    tasks = parse_tasks(paths)
    adrs = parse_decisions(paths)

    active = [t for t in tasks if t["status"] not in ("completed", "cancelled")]
    primary = next((t for t in active if t["status"] == "in_progress"), active[0] if active else None)

    prev_text = paths.session_file.read_text(encoding="utf-8") if paths.session_file.exists() else ""

    branch = git["branch"] if git["is_repo"] else "N/A (no git repository)"
    working_tree = (
        f"{len(git['dirty_files'])} uncommitted change(s)" if git["is_repo"] else "N/A"
    )

    progress_items: list[str] = []
    if summary:
        progress_items.append(summary.strip())
    elif primary and primary.get("progress"):
        progress_items.extend(primary["progress"][-5:])
    else:
        progress_items.extend(_extract_session_bullets(prev_text, "Progress"))

    changed_files: list[str] = []
    if git["dirty_files"]:
        changed_files.extend(git["dirty_files"][:20])
    else:
        changed_files.extend(_extract_session_bullets(prev_text, "Files changed"))

    verification_items = list(commands or [])
    if not verification_items and primary and primary.get("evidence"):
        verification_items.extend(primary["evidence"][-5:])
    if not verification_items:
        verification_items.extend(_extract_session_bullets(prev_text, "Verification"))

    decision_items = list(decisions or [])
    if not decision_items and adrs:
        decision_items.extend(
            f"{d['title']} [{d['status']}] ({d['source_path']})" for d in adrs[-3:]
        )
    if not decision_items:
        decision_items.extend(_extract_session_bullets(prev_text, "Decisions / assumptions"))

    blocker_items = list(blockers or [])
    if not blocker_items:
        for task in active:
            for b in task.get("blockers", []):
                blocker_items.append(f"{task['id']}: {b}")
    if not blocker_items:
        blocker_items.extend(_extract_session_bullets(prev_text, "Blockers"))

    next_items = list(next_actions or [])
    if not next_items and primary and primary.get("next_action"):
        next_items.append(f"{primary['id']}: {primary['next_action']}")
    if not next_items:
        next_items.extend(_extract_session_bullets(prev_text, "Next actions"))
    if not next_items:
        next_items.append("Run `/session-manager recover` at the start of the next session.")

    read_first_items = list(read_first or [])
    if not read_first_items:
        for inst in discover_agent_instructions(paths.root):
            if inst["kind"] == "file":
                read_first_items.append(f"`{inst['path']}`")
        if paths.project_context.exists():
            read_first_items.append(f"`{relpath(paths.project_context, paths.root)}`")
        if paths.tasks_file.exists():
            read_first_items.append(f"`{relpath(paths.tasks_file, paths.root)}`")
        for dirty in git.get("dirty_files", [])[:5]:
            # Extract path from `XY path` status format
            path_part = dirty[3:].strip() if len(dirty) > 3 else dirty
            if path_part and f"`{path_part}`" not in read_first_items:
                read_first_items.append(f"`{path_part}`")

    def _fmt_bullets(items: list[str], fallback: str = "-") -> str:
        clean = [i for i in items if i and i != "-"]
        return "\n".join(f"- {i}" for i in clean) if clean else fallback

    def _fmt_numbered(items: list[str]) -> str:
        clean = [i for i in items if i and i != "-"][:3]
        if not clean:
            return "1."
        return "\n".join(f"{idx}. {item}" for idx, item in enumerate(clean, start=1))

    task_id_val = primary["id"] if primary else "None"
    task_goal_val = primary.get("objective", primary["title"]) if primary else "No active task"
    task_status_val = primary["status"] if primary else "idle"

    content = (
        "# Session Snapshot\n\n"
        "> Keep this file concise. It is a handoff, not a project encyclopedia.\n\n"
        f"- Updated: {stamp}\n"
        f"- Project: {paths.root.name}\n"
        f"- Branch: {branch}\n"
        f"- Working tree: {working_tree}\n\n"
        "## Active task\n"
        f"- ID: {task_id_val}\n"
        f"- Goal: {task_goal_val}\n"
        f"- Status: {task_status_val}\n\n"
        "## Progress\n"
        f"{_fmt_bullets(progress_items)}\n\n"
        "## Files changed\n"
        f"{_fmt_bullets(changed_files)}\n\n"
        "## Verification\n"
        f"{_fmt_bullets(verification_items, '- Command: (none recorded yet)')}\n\n"
        "## Decisions / assumptions\n"
        f"{_fmt_bullets(decision_items)}\n\n"
        "## Blockers\n"
        f"{_fmt_bullets(blocker_items)}\n\n"
        "## Next actions\n"
        f"{_fmt_numbered(next_items)}\n\n"
        "## Read first next session\n"
        f"{_fmt_bullets(read_first_items)}\n"
    )

    paths.session_file.parent.mkdir(parents=True, exist_ok=True)
    paths.session_file.write_text(content, encoding="utf-8")

    saved_text = paths.session_file.read_text(encoding="utf-8")
    required_markers = ("# Session Snapshot", f"- Updated: {stamp}", "## Active task", "## Next actions")
    verified = all(marker in saved_text for marker in required_markers)
    if not verified:
        raise IOError("Failed to verify persisted SESSION.md snapshot")

    record_session_event(
        paths,
        branch=branch,
        active_task_id=task_id_val,
        summary=(summary or task_goal_val)[:200],
    )

    return {
        "session_file": relpath(paths.session_file, paths.root),
        "updated": stamp,
        "branch": branch,
        "active_task": task_id_val,
        "files_changed": len(changed_files),
        "verified": verified,
    }
