#!/usr/bin/env python3
"""Task lifecycle tracking backed by Markdown and synchronized to SQLite."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sm_core import SkillPaths, now_iso, today_compact

VALID_TASK_STATUSES = ("backlog", "in_progress", "blocked", "completed", "cancelled")

_SECTION_FOR_STATUS = {
    "backlog": "Backlog",
    "in_progress": "Active",
    "blocked": "Active",
    "completed": "Completed",
    "cancelled": "Completed",
}


def strip_html_comments(text: str) -> str:
    """Remove HTML comments so template examples are ignored during parsing."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _extract_bullets(block: str, heading: str) -> list[str]:
    pattern = rf"^- {re.escape(heading)}:[ \t]*(.*)\n((?:[ \t]+-[ \t]+.*\n?)*)"
    match = re.search(pattern, block, flags=re.M)
    if not match:
        return []
    inline = match.group(1).strip()
    items: list[str] = [inline] if inline else []
    for line in match.group(2).splitlines():
        cleaned = re.sub(r"^[ \t]+-[ \t]+", "", line).strip()
        if cleaned:
            items.append(cleaned)
    return items


def _extract_criteria(block: str) -> list[dict[str, Any]]:
    match = re.search(
        r"^- Acceptance criteria:[ \t]*\n((?:[ \t]+- \[[ xX]\][^\n]*\n?)*)",
        block,
        flags=re.M,
    )
    if not match:
        return []
    criteria: list[dict[str, Any]] = []
    for line in match.group(1).splitlines():
        item = re.match(r"^[ \t]+- \[([ xX])\]\s*(.+)$", line)
        if item:
            criteria.append({"done": item.group(1).lower() == "x", "text": item.group(2).strip()})
    return criteria


def _extract_field(block: str, name: str) -> str:
    match = re.search(rf"^- {re.escape(name)}:[ \t]*(.*)$", block, flags=re.M)
    return match.group(1).strip() if match else ""


def parse_tasks(paths: SkillPaths) -> list[dict[str, Any]]:
    """Parse all real task blocks from `TASKS.md`, ignoring HTML comments."""
    if not paths.tasks_file.exists():
        return []
    raw = strip_html_comments(paths.tasks_file.read_text(encoding="utf-8"))
    current_section = "Active"
    tasks: list[dict[str, Any]] = []

    # Track section headings alongside task blocks.
    parts = re.split(r"(?=^(?:## [^\n]+|### [A-Z]+-[\w-]+ — ))", raw, flags=re.M)
    for part in parts:
        sec_match = re.match(r"^## ([^\n]+)$", part.strip().splitlines()[0] if part.strip() else "")
        if sec_match and not part.lstrip().startswith("### "):
            current_section = sec_match.group(1).strip()
            continue
        head = re.match(r"^### ([A-Z]+-[\w-]+) — (.+)$", part, flags=re.M)
        if not head:
            continue
        status = _extract_field(part, "Status") or "unknown"
        decisions_raw = _extract_bullets(part, "Decisions")
        decisions = []
        for entry in decisions_raw:
            for token in re.split(r"[,\s]+", entry):
                cleaned = token.strip()
                if cleaned:
                    decisions.append(cleaned)
        tasks.append(
            {
                "id": head.group(1).strip(),
                "title": head.group(2).strip(),
                "section": current_section,
                "status": status,
                "created": _extract_field(part, "Created"),
                "updated": _extract_field(part, "Updated"),
                "objective": _extract_field(part, "Objective"),
                "acceptance_criteria": _extract_criteria(part),
                "progress": _extract_bullets(part, "Progress"),
                "evidence": _extract_bullets(part, "Evidence"),
                "blockers": _extract_bullets(part, "Blockers"),
                "decisions": decisions,
                "next_action": _extract_field(part, "Next action"),
            }
        )
    return tasks


def format_task_block(task: dict[str, Any]) -> str:
    """Serialize a task dict into the canonical Markdown block format."""
    lines = [
        f"### {task['id']} — {task['title']}",
        f"- Status: {task.get('status', 'in_progress')}",
        f"- Created: {task.get('created', '')}",
        f"- Updated: {task.get('updated', '')}",
        f"- Objective: {task.get('objective', task['title'])}".rstrip(),
        "- Acceptance criteria:",
    ]
    criteria = task.get("acceptance_criteria") or []
    if criteria:
        for item in criteria:
            mark = "x" if item.get("done") else " "
            lines.append(f"  - [{mark}] {item['text']}")
    else:
        lines.append("  - [ ] Define and verify completion criteria")

    for label, key in [("Progress", "progress"), ("Evidence", "evidence")]:
        items = task.get(key) or []
        if items:
            lines.append(f"- {label}:")
            for item in items:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {label}:")

    blockers = task.get("blockers") or []
    if blockers:
        lines.append("- Blockers:")
        for item in blockers:
            lines.append(f"  - {item}")

    decisions = task.get("decisions") or []
    if decisions:
        lines.append(f"- Decisions: {', '.join(decisions)}")

    next_action = task.get("next_action", "")
    lines.append(f"- Next action: {next_action}".rstrip())
    return "\n".join(lines) + "\n"


def next_task_id(paths: SkillPaths) -> str:
    """Compute the next sequential task ID for today using configured prefix/timezone."""
    prefix = str(paths.config.get("task_id_prefix", "SM")).strip().upper() or "SM"
    day = today_compact(str(paths.config.get("timezone", "UTC")))
    existing = [t["id"] for t in parse_tasks(paths) if t["id"].startswith(f"{prefix}-{day}-")]
    nums = [int(x.rsplit("-", 1)[-1]) for x in existing if x.rsplit("-", 1)[-1].isdigit()]
    return f"{prefix}-{day}-{max(nums, default=0) + 1:03d}"


def _insert_into_section(text: str, section_name: str, block: str) -> str:
    heading = re.search(rf"^## {re.escape(section_name)}\s*$", text, flags=re.M)
    if heading:
        pos = heading.end()
        return text[:pos] + "\n\n" + block.rstrip("\n") + "\n" + text[pos:].lstrip("\n")
    return text.rstrip("\n") + f"\n\n## {section_name}\n\n" + block.rstrip("\n") + "\n"


def _remove_task_block(text: str, task_id: str) -> tuple[str, bool]:
    """Remove an active (non-commented) task block matching `task_id`."""
    pattern = re.compile(
        rf"(?ms)^### {re.escape(task_id)} — [^\n]+\n.*?(?=^### [A-Z]+-[\w-]+ — |^## |\Z)"
    )
    # Protect HTML comments from matching or replacement.
    placeholders: dict[str, str] = {}

    def _hide(m: re.Match[str]) -> str:
        key = f"__SM_COMMENT_{len(placeholders)}__"
        placeholders[key] = m.group(0)
        return key

    masked = re.sub(r"<!--.*?-->", _hide, text, flags=re.S)
    new_masked, count = pattern.subn("", masked, count=1)
    for key, val in placeholders.items():
        new_masked = new_masked.replace(key, val)
    new_masked = re.sub(r"\n{3,}", "\n\n", new_masked)
    return new_masked, count > 0


def _save_task_update(paths: SkillPaths, task: dict[str, Any], target_section: str | None = None) -> None:
    text = paths.tasks_file.read_text(encoding="utf-8")
    text, _ = _remove_task_block(text, task["id"])
    section = target_section or _SECTION_FOR_STATUS.get(task["status"], task.get("section", "Active"))
    block = format_task_block(task)
    updated = _insert_into_section(text, section, block)
    paths.tasks_file.write_text(updated, encoding="utf-8")


def _archive_task_if_configured(paths: SkillPaths, task: dict[str, Any]) -> Path | None:
    if not paths.config.get("archive_completed", False):
        return None
    paths.archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = today_compact(str(paths.config.get("timezone", "UTC")))[:6]
    archive_file = paths.archive_dir / f"TASKS-{stamp}.md"
    if not archive_file.exists():
        archive_file.write_text(f"# Archived Tasks ({stamp})\n\n", encoding="utf-8")
    existing = archive_file.read_text(encoding="utf-8")
    archive_file.write_text(existing.rstrip("\n") + "\n\n" + format_task_block(task), encoding="utf-8")
    text, _ = _remove_task_block(paths.tasks_file.read_text(encoding="utf-8"), task["id"])
    paths.tasks_file.write_text(text, encoding="utf-8")
    return archive_file


def start_task(
    paths: SkillPaths,
    title: str,
    objective: str | None = None,
    criteria: list[str] | None = None,
    status: str = "in_progress",
) -> dict[str, Any]:
    """Create a new task record in `TASKS.md`."""
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Expected one of: {', '.join(VALID_TASK_STATUSES)}")
    tid = next_task_id(paths)
    stamp = now_iso(str(paths.config.get("timezone", "UTC")))
    clean_title = title.strip()
    criteria_items = [
        {"done": False, "text": c.strip()} for c in (criteria or []) if c.strip()
    ] or [{"done": False, "text": "Define and verify completion criteria"}]

    task: dict[str, Any] = {
        "id": tid,
        "title": clean_title,
        "section": _SECTION_FOR_STATUS.get(status, "Active"),
        "status": status,
        "created": stamp,
        "updated": stamp,
        "objective": (objective or clean_title).strip(),
        "acceptance_criteria": criteria_items,
        "progress": [],
        "evidence": [],
        "blockers": [],
        "decisions": [],
        "next_action": "Inspect relevant project context and begin work",
    }
    _save_task_update(paths, task, target_section=task["section"])
    return task


def find_task(paths: SkillPaths, task_id: str) -> dict[str, Any] | None:
    """Find a task by exact ID (case-insensitive)."""
    needle = task_id.strip().upper()
    for task in parse_tasks(paths):
        if task["id"].upper() == needle:
            return task
    return None


def list_tasks(
    paths: SkillPaths,
    status_filter: str | None = None,
    blocked_only: bool = False,
    include_closed: bool = False,
) -> list[dict[str, Any]]:
    """Return tasks filtered by status or blocked state."""
    tasks = parse_tasks(paths)
    if status_filter:
        tasks = [t for t in tasks if t["status"] == status_filter]
    elif not include_closed:
        tasks = [t for t in tasks if t["status"] not in ("completed", "cancelled")]
    if blocked_only:
        tasks = [t for t in tasks if t["status"] == "blocked" or bool(t.get("blockers"))]
    return tasks


def update_task(
    paths: SkillPaths,
    task_id: str,
    status: str | None = None,
    progress: str | None = None,
    evidence: str | None = None,
    blocker: str | None = None,
    clear_blockers: bool = False,
    next_action: str | None = None,
    decision_id: str | None = None,
    add_criterion: str | None = None,
    check_criterion: int | None = None,
) -> dict[str, Any]:
    """Update task fields, criteria, progress, blockers, or decision links."""
    task = find_task(paths, task_id)
    if not task:
        raise KeyError(f"Task '{task_id}' not found")
    if status is not None:
        if status not in VALID_TASK_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Expected one of: {', '.join(VALID_TASK_STATUSES)}")
        task["status"] = status
    if progress:
        task["progress"].append(progress.strip())
    if evidence:
        task["evidence"].append(evidence.strip())
    if clear_blockers:
        task["blockers"] = []
    if blocker:
        task["blockers"].append(blocker.strip())
        if status is None:
            task["status"] = "blocked"
    if next_action is not None:
        task["next_action"] = next_action.strip()
    if decision_id:
        norm = decision_id.strip().upper()
        if not norm.startswith("ADR-"):
            norm = f"ADR-{norm.zfill(4)}" if norm.isdigit() else norm
        if norm not in task["decisions"]:
            task["decisions"].append(norm)
    if add_criterion:
        task["acceptance_criteria"].append({"done": False, "text": add_criterion.strip()})
    if check_criterion is not None:
        idx = check_criterion - 1
        if idx < 0 or idx >= len(task["acceptance_criteria"]):
            raise IndexError(f"Criterion index {check_criterion} out of range")
        task["acceptance_criteria"][idx]["done"] = True

    task["updated"] = now_iso(str(paths.config.get("timezone", "UTC")))
    _save_task_update(paths, task)
    return task


def complete_task(
    paths: SkillPaths,
    task_id: str,
    evidence: str | None = None,
    verify_all: bool = False,
    force: bool = False,
) -> tuple[dict[str, Any], list[str], Path | None]:
    """Complete a task after checking acceptance criteria; returns (task, unchecked, archive_path)."""
    task = find_task(paths, task_id)
    if not task:
        raise KeyError(f"Task '{task_id}' not found")

    if verify_all:
        for item in task["acceptance_criteria"]:
            item["done"] = True
    unchecked = [c["text"] for c in task["acceptance_criteria"] if not c["done"]]
    if unchecked and not force:
        return task, unchecked, None

    if evidence:
        task["evidence"].append(evidence.strip())
    task["status"] = "completed"
    task["blockers"] = []
    task["next_action"] = "Completed"
    task["updated"] = now_iso(str(paths.config.get("timezone", "UTC")))
    _save_task_update(paths, task, target_section="Completed")
    archived = _archive_task_if_configured(paths, task)
    return task, [], archived


def cancel_task(
    paths: SkillPaths, task_id: str, reason: str | None = None
) -> tuple[dict[str, Any], Path | None]:
    """Cancel a task and record the cancellation reason."""
    task = find_task(paths, task_id)
    if not task:
        raise KeyError(f"Task '{task_id}' not found")
    task["status"] = "cancelled"
    if reason:
        task["progress"].append(f"Cancelled: {reason.strip()}")
    task["next_action"] = "Cancelled"
    task["updated"] = now_iso(str(paths.config.get("timezone", "UTC")))
    _save_task_update(paths, task, target_section="Completed")
    archived = _archive_task_if_configured(paths, task)
    return task, archived
