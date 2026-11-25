#!/usr/bin/env python3
"""Architecture Decision Record (ADR) management and conflict detection."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sm_core import SkillPaths, now_iso, relpath
from sm_tasks import find_task, update_task

VALID_DECISION_STATUSES = ("proposed", "accepted", "superseded", "deprecated")

_STOPWORDS = {
    "with", "from", "that", "this", "into", "over", "using", "para", "como", "sobre",
    "entre", "usar", "decisao", "decision", "architecture", "system", "sistema",
}


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:48] or "decision"


def _extract_section(content: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", content)
    return match.group(1).strip() if match else ""


def parse_decisions(paths: SkillPaths) -> list[dict[str, Any]]:
    """Parse all ADR Markdown files in `.session-manager/decisions/`."""
    if not paths.decisions_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(paths.decisions_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title_line = next(
            (line[2:].strip() for line in content.splitlines() if line.startswith("# ")),
            path.stem,
        )
        did = path.stem.split("-", 1)[0]
        status_m = re.search(r"^- Status:\s*(.+)$", content, flags=re.M)
        date_m = re.search(r"^- Date:\s*(.+)$", content, flags=re.M)
        deciders_m = re.search(r"^- Deciders:\s*(.+)$", content, flags=re.M)
        sup_m = re.search(r"^- Superseded by:\s*(.+)$", content, flags=re.M)
        tasks_m = re.search(r"^- Related tasks:\s*(.+)$", content, flags=re.M)
        records.append(
            {
                "id": did,
                "adr_key": f"ADR-{did}",
                "title": title_line,
                "status": status_m.group(1).strip() if status_m else "",
                "date": date_m.group(1).strip() if date_m else "",
                "deciders": deciders_m.group(1).strip() if deciders_m else "",
                "superseded_by": sup_m.group(1).strip() if sup_m else "",
                "related_tasks": [
                    t.strip() for t in (tasks_m.group(1).split(",") if tasks_m else []) if t.strip()
                ],
                "context": _extract_section(content, "Context"),
                "decision": _extract_section(content, "Decision"),
                "consequences": _extract_section(content, "Consequences"),
                "source_path": relpath(path, paths.root),
                "path": path,
            }
        )
    return records


def find_decision(paths: SkillPaths, decision_id: str) -> dict[str, Any] | None:
    """Locate an ADR by numeric ID (`1`, `0001`, `ADR-0001`) or filename stem."""
    needle = decision_id.strip().upper().removeprefix("ADR-")
    if needle.isdigit():
        needle = needle.zfill(4)
    for dec in parse_decisions(paths):
        if dec["id"].upper() == needle or dec["path"].stem.upper() == decision_id.strip().upper():
            return dec
    return None


def _keywords(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]{4,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def find_conflicting_decisions(
    decisions: list[dict[str, Any]], title: str, decision_text: str = ""
) -> list[dict[str, Any]]:
    """Return active (proposed/accepted) ADRs that overlap significantly in topic."""
    target_tokens = _keywords(f"{title} {decision_text}")
    if not target_tokens:
        return []
    conflicts: list[dict[str, Any]] = []
    for dec in decisions:
        if dec.get("status") not in ("proposed", "accepted"):
            continue
        existing_tokens = _keywords(f"{dec['title']} {dec.get('decision', '')}")
        overlap = target_tokens & existing_tokens
        if len(overlap) >= 2 or (len(target_tokens) == 1 and overlap):
            conflicts.append({**dec, "overlap": sorted(overlap)})
    return conflicts


def _next_decision_id(decisions: list[dict[str, Any]]) -> str:
    nums = [int(d["id"]) for d in decisions if d["id"].isdigit()]
    return f"{max(nums, default=0) + 1:04d}"


def _update_project_context_decision(paths: SkillPaths, dec: dict[str, Any]) -> bool:
    """Append an accepted ADR reference under `## 10. Important decisions` if missing."""
    if not paths.project_context.exists():
        return False
    text = paths.project_context.read_text(encoding="utf-8")
    link = f"- [{dec['title']}]({dec['source_path']}) ({dec['status']}, {dec['date']})"
    if dec["source_path"] in text or dec["adr_key"] in text:
        return False
    heading = re.search(r"^## 10\. Important decisions\s*$", text, flags=re.M)
    if not heading:
        return False
    pos = heading.end()
    placeholder = "\n- Link relevant ADRs."
    if text[pos:].startswith(placeholder):
        updated = text[:pos] + "\n" + link + text[pos + len(placeholder) :]
    else:
        updated = text[:pos] + "\n" + link + text[pos:]
    paths.project_context.write_text(updated, encoding="utf-8")
    return True


def update_decision_status(
    paths: SkillPaths,
    decision_id: str,
    new_status: str,
    superseded_by: str | None = None,
    update_context: bool = False,
) -> dict[str, Any]:
    """Update the status (and optional Superseded by metadata) of an existing ADR."""
    if new_status not in VALID_DECISION_STATUSES:
        raise ValueError(
            f"Invalid decision status '{new_status}'. Expected: {', '.join(VALID_DECISION_STATUSES)}"
        )
    dec = find_decision(paths, decision_id)
    if not dec:
        raise KeyError(f"Decision '{decision_id}' not found")
    path: Path = dec["path"]
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^- Status:.*$", f"- Status: {new_status}", text, count=1)
    if superseded_by:
        sup_norm = superseded_by.strip().upper()
        if not sup_norm.startswith("ADR-"):
            sup_norm = f"ADR-{sup_norm.zfill(4)}" if sup_norm.isdigit() else sup_norm
        if re.search(r"(?m)^- Superseded by:.*$", text):
            text = re.sub(r"(?m)^- Superseded by:.*$", f"- Superseded by: {sup_norm}", text, count=1)
        else:
            text = re.sub(
                r"(?m)^(- Date:.*)$",
                rf"\1\n- Superseded by: {sup_norm}",
                text,
                count=1,
            )
    path.write_text(text, encoding="utf-8")
    refreshed = find_decision(paths, dec["id"]) or dec
    if update_context and new_status == "accepted":
        _update_project_context_decision(paths, refreshed)
    return refreshed


def record_decision(
    paths: SkillPaths,
    title: str,
    context: str = "",
    decision: str = "",
    alternatives: str = "",
    consequences_pos: str = "",
    consequences_neg: str = "",
    status: str = "accepted",
    deciders: str = "Session Manager / User",
    task_id: str | None = None,
    supersedes: str | None = None,
    update_context: bool = False,
) -> dict[str, Any]:
    """Create a numbered ADR Markdown file, link tasks/supersedes, and detect conflicts."""
    if status not in VALID_DECISION_STATUSES:
        raise ValueError(
            f"Invalid decision status '{status}'. Expected: {', '.join(VALID_DECISION_STATUSES)}"
        )
    paths.decisions_dir.mkdir(parents=True, exist_ok=True)
    existing = parse_decisions(paths)
    did = _next_decision_id(existing)
    clean_title = title.strip()
    date_str = now_iso(str(paths.config.get("timezone", "UTC")))[:10]
    slug = _slugify(clean_title)
    target = paths.decisions_dir / f"{did}-{slug}.md"

    conflicts = find_conflicting_decisions(existing, clean_title, decision)
    if supersedes:
        sup_dec = find_decision(paths, supersedes)
        if not sup_dec:
            raise KeyError(f"Superseded decision '{supersedes}' not found")
        conflicts = [c for c in conflicts if c["id"] != sup_dec["id"]]
        update_decision_status(paths, sup_dec["id"], "superseded", superseded_by=f"ADR-{did}")

    related_line = f"- Related tasks: {task_id.strip()}\n" if task_id else ""
    content = (
        f"# ADR-{did}: {clean_title}\n\n"
        f"- Status: {status}\n"
        f"- Date: {date_str}\n"
        f"- Deciders: {deciders}\n"
        f"{related_line}\n"
        f"## Context\n{context.strip() or 'Document the technical or product constraint motivating this decision.'}\n\n"
        f"## Decision\n{decision.strip() or clean_title}\n\n"
        f"## Alternatives considered\n"
        f"- {alternatives.strip() or 'Option: (document alternatives and trade-offs)'}\n\n"
        f"## Consequences\n"
        f"- Positive: {consequences_pos.strip() or 'TBD'}\n"
        f"- Negative: {consequences_neg.strip() or 'TBD'}\n"
        f"- Follow-up:\n\n"
        f"## Evidence and references\n-\n"
    )
    target.write_text(content, encoding="utf-8")

    if task_id and find_task(paths, task_id):
        update_task(paths, task_id, decision_id=f"ADR-{did}")

    created = find_decision(paths, did)
    assert created is not None
    context_updated = False
    if (update_context or status == "accepted") and paths.project_context.exists():
        context_updated = _update_project_context_decision(paths, created)

    return {
        "decision": created,
        "conflicts": conflicts,
        "context_updated": context_updated,
    }
