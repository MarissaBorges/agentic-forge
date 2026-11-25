#!/usr/bin/env python3
"""Deterministic Session Manager CLI; Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure sibling helper modules import reliably regardless of caller cwd.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from sm_audit_optimize import run_audit, run_optimize  # noqa: E402
from sm_core import (  # noqa: E402
    ADAPTERS_DIR,
    DEFAULT_CONFIG,
    SkillPaths,
    discover_agent_instructions,
    find_workspace_root,
    read_template,
    relpath,
    resolve_paths,
    write_missing,
)
from sm_db import query_decisions, query_tasks, sync_index  # noqa: E402
from sm_decisions import (  # noqa: E402
    VALID_DECISION_STATUSES,
    find_decision,
    parse_decisions,
    record_decision,
    update_decision_status,
)
from sm_recovery_handoff import build_recovery_report, create_handoff  # noqa: E402
from sm_router import route_request  # noqa: E402
from sm_tasks import (  # noqa: E402
    VALID_TASK_STATUSES,
    cancel_task,
    complete_task,
    find_task,
    list_tasks,
    parse_tasks,
    start_task,
    update_task,
)

# Backwards-compatible module globals (also patchable in unit tests).
ROOT = Path.cwd()
STATE = ROOT / ".session-manager"
CONFIG = STATE / "config.json"
SESSION = STATE / "SESSION.md"
TASKS = STATE / "TASKS.md"
DB = STATE / "index.sqlite"


def _active_paths(workspace: str | None = None) -> SkillPaths:
    """Resolve SkillPaths honoring either explicit workspace or patched module globals."""
    if workspace:
        return resolve_paths(Path(workspace).resolve())
    # If tests patched ROOT/STATE/etc. away from defaults, build SkillPaths from those overrides.
    cwd = Path.cwd()
    if (
        ROOT != cwd
        or STATE != (ROOT / ".session-manager")
        or CONFIG != (STATE / "config.json")
        or SESSION != (STATE / "SESSION.md")
        or TASKS != (STATE / "TASKS.md")
        or DB != (STATE / "index.sqlite")
    ):
        cfg = dict(DEFAULT_CONFIG)
        cfg_err = None
        if CONFIG.exists():
            try:
                loaded = json.loads(CONFIG.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg.update(loaded)
                else:
                    cfg_err = "config.json must be a JSON object"
            except (json.JSONDecodeError, OSError) as exc:
                cfg_err = str(exc)
        return SkillPaths(
            root=ROOT,
            state_dir=STATE,
            config_file=CONFIG,
            project_context=ROOT / str(cfg.get("project_context", "PROJECT_CONTEXT.md")),
            session_file=SESSION,
            tasks_file=TASKS,
            database_file=DB,
            decisions_dir=STATE / "decisions",
            notes_dir=STATE / "notes",
            archive_dir=STATE / "archive",
            config=cfg,
            config_error=cfg_err,
        )
    return resolve_paths(find_workspace_root(cwd))


def _sync_if_db_exists(paths: SkillPaths) -> None:
    if paths.database_file.exists():
        sync_index(paths, parse_tasks(paths), parse_decisions(paths))


def _emit(payload: Any, text: str, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(text)


def init(workspace: str | None = None, as_json: bool = False) -> int:
    paths = _active_paths(workspace)
    created: list[str] = []
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    for target, tpl in [
        (paths.config_file, "config.json"),
        (paths.session_file, "SESSION.md"),
        (paths.tasks_file, "TASKS.md"),
        (paths.project_context, "PROJECT_CONTEXT.md"),
    ]:
        if write_missing(target, read_template(tpl)):
            created.append(relpath(target, paths.root))
    for folder in (paths.decisions_dir, paths.notes_dir, paths.archive_dir):
        folder.mkdir(parents=True, exist_ok=True)
    msg = (
        "Created: "
        + (", ".join(created) if created else "no files; existing files preserved")
        + "\nNext: inspect the repository and populate PROJECT_CONTEXT.md with verified facts."
    )
    _emit({"workspace": str(paths.root), "created": created}, msg, as_json=as_json)
    return 0


def task_blocks(workspace: str | None = None) -> list[dict[str, Any]]:
    return parse_tasks(_active_paths(workspace))


def task_start(
    title: str,
    objective: str | None = None,
    criteria: list[str] | None = None,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    if not paths.tasks_file.exists():
        print("Run `init` first.", file=sys.stderr)
        return 2
    task = start_task(paths, title, objective=objective, criteria=criteria)
    _sync_if_db_exists(paths)
    _emit(task, f"Started {task['id']}: {task['title']}", as_json=as_json)
    return 0


def task_list_cmd(
    status_filter: str | None = None,
    blocked_only: bool = False,
    include_closed: bool = False,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    tasks = list_tasks(
        paths, status_filter=status_filter, blocked_only=blocked_only, include_closed=include_closed
    )
    if as_json:
        _emit({"tasks": tasks}, "", as_json=True)
    else:
        if not tasks:
            print("No matching tasks found.")
        else:
            for t in tasks:
                done = sum(1 for c in t.get("acceptance_criteria", []) if c["done"])
                total = len(t.get("acceptance_criteria", []))
                print(f"- {t['id']} [{t['status']}] ({done}/{total} criteria) {t['title']}")
    return 0


def task_show_cmd(task_id: str, workspace: str | None = None, as_json: bool = False) -> int:
    paths = _active_paths(workspace)
    task = find_task(paths, task_id)
    if not task:
        print(f"Task '{task_id}' not found.", file=sys.stderr)
        return 2
    lines = [
        f"{task['id']} — {task['title']}",
        f"Status: {task['status']} | Section: {task['section']}",
        f"Objective: {task['objective']}",
        "Acceptance criteria:",
    ]
    for idx, c in enumerate(task.get("acceptance_criteria", []), start=1):
        lines.append(f"  {idx}. [{'x' if c['done'] else ' '}] {c['text']}")
    if task.get("progress"):
        lines.append("Progress: " + "; ".join(task["progress"]))
    if task.get("evidence"):
        lines.append("Evidence: " + "; ".join(task["evidence"]))
    if task.get("blockers"):
        lines.append("Blockers: " + "; ".join(task["blockers"]))
    if task.get("decisions"):
        lines.append("Decisions: " + ", ".join(task["decisions"]))
    lines.append(f"Next action: {task.get('next_action', '')}")
    _emit(task, "\n".join(lines), as_json=as_json)
    return 0


def task_update_cmd(
    task_id: str,
    workspace: str | None = None,
    as_json: bool = False,
    **kwargs: Any,
) -> int:
    paths = _active_paths(workspace)
    if not paths.tasks_file.exists():
        print("Run `init` first.", file=sys.stderr)
        return 2
    try:
        task = update_task(paths, task_id, **kwargs)
    except (KeyError, ValueError, IndexError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _sync_if_db_exists(paths)
    _emit(task, f"Updated {task['id']} [{task['status']}]: {task['title']}", as_json=as_json)
    return 0


def task_complete_cmd(
    task_id: str,
    evidence: str | None = None,
    verify_all: bool = False,
    force: bool = False,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    try:
        task, unchecked, archived = complete_task(
            paths, task_id, evidence=evidence, verify_all=verify_all, force=force
        )
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if unchecked:
        msg = (
            f"Cannot complete {task['id']}; unchecked acceptance criteria remain:\n"
            + "\n".join(f"- [ ] {c}" for c in unchecked)
        )
        _emit({"completed": False, "unchecked": unchecked, "task": task}, msg, as_json=as_json)
        return 1
    _sync_if_db_exists(paths)
    extra = f" (archived to {relpath(archived, paths.root)})" if archived else ""
    _emit(
        {"completed": True, "task": task, "archived": str(archived) if archived else None},
        f"Completed {task['id']}: {task['title']}{extra}",
        as_json=as_json,
    )
    return 0


def task_cancel_cmd(
    task_id: str, reason: str | None = None, workspace: str | None = None, as_json: bool = False
) -> int:
    paths = _active_paths(workspace)
    try:
        task, archived = cancel_task(paths, task_id, reason=reason)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _sync_if_db_exists(paths)
    _emit(
        {"cancelled": True, "task": task, "archived": str(archived) if archived else None},
        f"Cancelled {task['id']}: {task['title']}",
        as_json=as_json,
    )
    return 0


def status(workspace: str | None = None, as_json: bool = False) -> int:
    paths = _active_paths(workspace)
    tasks = parse_tasks(paths)
    active = [t for t in tasks if t["status"] not in ("completed", "cancelled")]
    blocked = [t for t in active if t["status"] == "blocked" or t.get("blockers")]
    lines = [
        f"Workspace: {paths.root}",
        f"Session files: {'initialized' if paths.state_dir.exists() else 'not initialized'}",
        f"Tasks: {len(tasks)} total, {len(active)} active ({len(blocked)} blocked)",
    ]
    for task in active:
        lines.append(f"- {task['id']} [{task['status']}] {task['title']}")
    if not tasks:
        lines.append("No task records found.")
    _emit(
        {
            "workspace": str(paths.root),
            "initialized": paths.state_dir.exists(),
            "total_tasks": len(tasks),
            "active_tasks": active,
            "blocked_tasks": blocked,
        },
        "\n".join(lines),
        as_json=as_json,
    )
    return 0


def recover_cmd(workspace: str | None = None, as_json: bool = False) -> int:
    paths = _active_paths(workspace)
    report = build_recovery_report(paths)
    lines = [f"Workspace: {report['workspace']}"]
    lines.append("Confirmed facts:")
    lines.extend(f"- {f}" for f in report["confirmed_facts"])
    if report["inferences"]:
        lines.append("Inferences:")
        lines.extend(f"- {i}" for i in report["inferences"])
    if report["unknowns"]:
        lines.append("Unknowns / gaps:")
        lines.extend(f"- {u}" for u in report["unknowns"])
    if report["next_actions"]:
        lines.append("Suggested next actions:")
        lines.extend(f"{idx}. {a}" for idx, a in enumerate(report["next_actions"], start=1))
    _emit(report, "\n".join(lines), as_json=as_json)
    return 0


def handoff(
    summary: str | None = None,
    commands: list[str] | None = None,
    decisions: list[str] | None = None,
    blockers: list[str] | None = None,
    next_actions: list[str] | None = None,
    read_first: list[str] | None = None,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    if not paths.session_file.exists() and not paths.state_dir.exists():
        print("Run `init` first.", file=sys.stderr)
        return 2
    try:
        result = create_handoff(
            paths,
            summary=summary,
            commands=commands,
            decisions=decisions,
            blockers=blockers,
            next_actions=next_actions,
            read_first=read_first,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    msg = (
        f"Session handoff saved and verified: {result['session_file']} "
        f"(branch={result['branch']}, active_task={result['active_task']}, files_changed={result['files_changed']})."
    )
    _emit(result, msg, as_json=as_json)
    return 0


def index_rebuild(workspace: str | None = None, as_json: bool = False) -> int:
    paths = _active_paths(workspace)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    tasks = parse_tasks(paths)
    decisions = parse_decisions(paths)
    version = sync_index(paths, tasks, decisions)
    _emit(
        {
            "database": relpath(paths.database_file, paths.root),
            "schema_version": version,
            "tasks_indexed": len(tasks),
            "decisions_indexed": len(decisions),
        },
        f"SQLite index rebuilt (schema v{version}): {relpath(paths.database_file, paths.root)}",
        as_json=as_json,
    )
    return 0


def index_query_cmd(
    table: str = "tasks",
    status_filter: str | None = None,
    text: str | None = None,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    if not paths.database_file.exists():
        print("SQLite index not found. Run `index rebuild` first.", file=sys.stderr)
        return 2
    rows = (
        query_tasks(paths.database_file, status=status_filter, text=text)
        if table == "tasks"
        else query_decisions(paths.database_file, status=status_filter, text=text)
    )
    if as_json:
        _emit({"table": table, "rows": rows}, "", as_json=True)
    else:
        if not rows:
            print(f"No matching {table} in SQLite index.")
        else:
            for r in rows:
                print(f"- {r['id']} [{r['status']}] {r['title']}")
    return 0


def audit(fix: bool = False, workspace: str | None = None, as_json: bool = False) -> int:
    paths = _active_paths(workspace)
    report = run_audit(paths, fix=fix)
    lines: list[str] = []
    if report["applied_fixes"]:
        lines.append("Auto-fixes applied:")
        lines.extend(f"- {fx}" for fx in report["applied_fixes"])
    if report["findings"]:
        for f in report["findings"]:
            lines.append(f"[{f['severity']}] {f['code']}: {f['message']}")
    if report["passed"]:
        lines.append("Audit passed: required files present; task/ADR integrity and index valid.")
    else:
        lines.append(f"{report['blocking_count']} blocking issue(s) found ({report['info_count']} info).")
    _emit(report, "\n".join(lines), as_json=as_json)
    return 0 if report["passed"] else 1


def optimize_cmd(
    symptom: str = "",
    command: str | None = None,
    runs: int = 1,
    sql_db: str | None = None,
    query: str | None = None,
    profile_py: str | None = None,
    save_baseline: bool = False,
    compare: bool = False,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    report = run_optimize(
        paths,
        symptom=symptom,
        command=command,
        runs=runs,
        sql_db=sql_db,
        query=query,
        profile_py=profile_py,
        save_baseline=save_baseline,
        compare=compare,
    )
    lines = [
        f"Optimize diagnostics ({paths.root.name}):",
        f"- Context footprint: {report['context']['total_bytes']} bytes (~{report['context']['est_tokens']} tokens)",
        f"- Workspace scanned: {report['workspace']['file_count']} files ({report['workspace']['total_bytes']} bytes)",
    ]
    if report.get("benchmark"):
        b = report["benchmark"]
        lines.append(f"- Benchmark '{b['command']}': avg {b['avg_ms']} ms (runs={b['runs']})")
    if report.get("python_profile"):
        p = report["python_profile"]
        if "error" in p:
            lines.append(f"- Python profile error: {p['error']}")
        else:
            lines.append(f"- Python profile '{p['script']}': {p['elapsed_ms']} ms, peak {p['peak_mem_kb']} KB")
    if report.get("comparison"):
        c = report["comparison"]
        lines.append(f"- Baseline comparison: context delta {c['delta_context_bytes']} bytes")
    if report["findings"]:
        lines.append("Findings:")
        for item in report["findings"]:
            lines.append(
                f"  - [{item['impact'].upper()} | {item['source']}] {item['category']}: {item['evidence']} -> {item['recommendation']}"
            )
    else:
        lines.append("No significant bottlenecks flagged from collected measurements.")
    _emit(report, "\n".join(lines), as_json=as_json)
    return 0


def decision_record_cmd(
    title: str,
    context: str = "",
    decision: str = "",
    alternatives: str = "",
    status: str = "accepted",
    task_id: str | None = None,
    supersedes: str | None = None,
    update_context: bool = False,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    try:
        result = record_decision(
            paths,
            title=title,
            context=context,
            decision=decision,
            alternatives=alternatives,
            status=status,
            task_id=task_id,
            supersedes=supersedes,
            update_context=update_context,
        )
    except (ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _sync_if_db_exists(paths)
    dec = result["decision"]
    lines = [f"Recorded {dec['title']} [{dec['status']}] at {dec['source_path']}"]
    if result["conflicts"]:
        lines.append(
            "Warning - potentially overlapping active ADR(s): "
            + ", ".join(c["adr_key"] for c in result["conflicts"])
        )
    _emit(result, "\n".join(lines), as_json=as_json)
    return 0


def decision_list_cmd(
    status_filter: str | None = None, workspace: str | None = None, as_json: bool = False
) -> int:
    paths = _active_paths(workspace)
    decisions = parse_decisions(paths)
    if status_filter:
        decisions = [d for d in decisions if d.get("status") == status_filter]
    if as_json:
        _emit({"decisions": [{k: v for k, v in d.items() if k != "path"} for d in decisions]}, "", as_json=True)
    else:
        if not decisions:
            print("No decisions recorded.")
        else:
            for d in decisions:
                print(f"- {d['adr_key']} [{d['status']}] {d['title']} ({d['source_path']})")
    return 0


def decision_show_cmd(decision_id: str, workspace: str | None = None, as_json: bool = False) -> int:
    paths = _active_paths(workspace)
    dec = find_decision(paths, decision_id)
    if not dec:
        print(f"Decision '{decision_id}' not found.", file=sys.stderr)
        return 2
    payload = {k: v for k, v in dec.items() if k != "path"}
    _emit(payload, dec["path"].read_text(encoding="utf-8"), as_json=as_json)
    return 0


def decision_status_cmd(
    decision_id: str,
    new_status: str,
    superseded_by: str | None = None,
    update_context: bool = False,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    try:
        dec = update_decision_status(
            paths, decision_id, new_status, superseded_by=superseded_by, update_context=update_context
        )
    except (ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _sync_if_db_exists(paths)
    payload = {k: v for k, v in dec.items() if k != "path"}
    _emit(payload, f"Updated {dec['adr_key']} status to {dec['status']}.", as_json=as_json)
    return 0


def adapter_cmd(
    action: str,
    platform: str | None = None,
    target: str | None = None,
    dry_run: bool = False,
    workspace: str | None = None,
    as_json: bool = False,
) -> int:
    paths = _active_paths(workspace)
    if action == "status":
        instructions = discover_agent_instructions(paths.root)
        available = sorted(
            p.name for p in ADAPTERS_DIR.iterdir() if p.is_dir()
        ) if ADAPTERS_DIR.exists() else []
        payload = {"workspace": str(paths.root), "detected": instructions, "adapters": available}
        lines = [f"Available adapters: {', '.join(available) or 'none'}"]
        if instructions:
            lines.append("Detected in workspace: " + ", ".join(f"{i['path']} ({i['platform']})" for i in instructions))
        else:
            lines.append("Detected in workspace: none")
        _emit(payload, "\n".join(lines), as_json=as_json)
        return 0

    mapping = {
        "antigravity": (ADAPTERS_DIR / "antigravity" / "session-manager.md", ".agents/workflows/session-manager.md"),
        "claude-code": (ADAPTERS_DIR / "claude-code" / "session-manager.md", ".claude/commands/session-manager.md"),
        "codex": (ADAPTERS_DIR / "codex" / "AGENTS.snippet.md", "AGENTS.md"),
    }
    if platform not in mapping:
        print(f"Unknown platform '{platform}'. Choose: {', '.join(mapping)}", file=sys.stderr)
        return 2
    src, default_rel = mapping[platform]
    if not src.is_file():
        print(f"Adapter template missing: {src}", file=sys.stderr)
        return 2
    dest_root = Path(target).resolve() if target else paths.root
    dest = dest_root / default_rel
    if dry_run:
        _emit(
            {"dry_run": True, "source": str(src), "destination": str(dest)},
            f"[dry-run] Would write {src.name} -> {dest}",
            as_json=as_json,
        )
        return 0
    if dest.exists():
        print(f"Destination already exists (preserving user file): {dest}", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    _emit(
        {"installed": True, "platform": platform, "destination": str(dest)},
        f"Installed {platform} adapter at {dest}",
        as_json=as_json,
    )
    return 0


def help_cmd(as_json: bool = False) -> int:
    text = (
        "Session Manager commands:\n"
        "  init | recover | status | handoff | audit [--fix]\n"
        "  task start|list|show|update|complete|cancel\n"
        "  decision record|list|show|status\n"
        "  optimize [symptom] [--cmd ...] [--sql ...] [--profile-py ...]\n"
        "  index rebuild | index query\n"
        "  route <raw command or natural language>\n"
        "  adapter status | adapter install <platform>"
    )
    _emit({"help": text}, text, as_json=as_json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default=argparse.SUPPRESS, help="Explicit workspace root path")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Emit JSON output")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=None, help="Explicit workspace root path")
    parser.add_argument("--json", action="store_true", default=False, help="Emit JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("help", parents=[common])
    sub.add_parser("init", parents=[common])
    sub.add_parser("recover", parents=[common])
    sub.add_parser("status", parents=[common])

    audit_p = sub.add_parser("audit", parents=[common])
    audit_p.add_argument("--fix", action="store_true", help="Apply safe autonomous fixes")

    handoff_p = sub.add_parser("handoff", parents=[common])
    handoff_p.add_argument("--summary")
    handoff_p.add_argument("--command", action="append", dest="commands")
    handoff_p.add_argument("--decision", action="append", dest="decisions")
    handoff_p.add_argument("--blocker", action="append", dest="blockers")
    handoff_p.add_argument("--next-action", action="append", dest="next_actions")
    handoff_p.add_argument("--read-first", action="append", dest="read_first")

    opt_p = sub.add_parser("optimize", parents=[common])
    opt_p.add_argument("symptom", nargs="*")
    opt_p.add_argument("--cmd", dest="bench_cmd")
    opt_p.add_argument("--runs", type=int, default=1)
    opt_p.add_argument("--sql", dest="sql_db")
    opt_p.add_argument("--query")
    opt_p.add_argument("--profile-py")
    opt_p.add_argument("--save-baseline", action="store_true")
    opt_p.add_argument("--compare", action="store_true")

    task_p = sub.add_parser("task")
    task_sub = task_p.add_subparsers(dest="task_command", required=True)
    t_start = task_sub.add_parser("start", parents=[common])
    t_start.add_argument("title", nargs="+")
    t_start.add_argument("--objective")
    t_start.add_argument("--criterion", action="append", dest="criteria")

    t_list = task_sub.add_parser("list", parents=[common])
    t_list.add_argument("--status", choices=VALID_TASK_STATUSES)
    t_list.add_argument("--blocked", action="store_true")
    t_list.add_argument("--all", action="store_true", dest="include_closed")

    t_show = task_sub.add_parser("show", parents=[common])
    t_show.add_argument("id")

    t_upd = task_sub.add_parser("update", parents=[common])
    t_upd.add_argument("id")
    t_upd.add_argument("--status", choices=VALID_TASK_STATUSES)
    t_upd.add_argument("--progress")
    t_upd.add_argument("--evidence")
    t_upd.add_argument("--blocker")
    t_upd.add_argument("--clear-blockers", action="store_true")
    t_upd.add_argument("--next-action")
    t_upd.add_argument("--decision")
    t_upd.add_argument("--add-criterion")
    t_upd.add_argument("--check-criterion", type=int)

    t_comp = task_sub.add_parser("complete", parents=[common])
    t_comp.add_argument("id")
    t_comp.add_argument("--evidence")
    t_comp.add_argument("--verify-all", action="store_true")
    t_comp.add_argument("--force", action="store_true")

    t_can = task_sub.add_parser("cancel", parents=[common])
    t_can.add_argument("id")
    t_can.add_argument("--reason")

    dec_p = sub.add_parser("decision")
    dec_sub = dec_p.add_subparsers(dest="decision_command", required=True)
    d_rec = dec_sub.add_parser("record", parents=[common])
    d_rec.add_argument("title", nargs="+")
    d_rec.add_argument("--context", default="")
    d_rec.add_argument("--decision", default="")
    d_rec.add_argument("--alternatives", default="")
    d_rec.add_argument("--status", default="accepted", choices=VALID_DECISION_STATUSES)
    d_rec.add_argument("--task")
    d_rec.add_argument("--supersedes")
    d_rec.add_argument("--update-context", action="store_true")

    d_list = dec_sub.add_parser("list", parents=[common])
    d_list.add_argument("--status", choices=VALID_DECISION_STATUSES)

    d_show = dec_sub.add_parser("show", parents=[common])
    d_show.add_argument("id")

    d_stat = dec_sub.add_parser("status", parents=[common])
    d_stat.add_argument("id")
    d_stat.add_argument("status", choices=VALID_DECISION_STATUSES)
    d_stat.add_argument("--superseded-by")
    d_stat.add_argument("--update-context", action="store_true")

    index_p = sub.add_parser("index")
    index_sub = index_p.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("rebuild", parents=[common])
    i_q = index_sub.add_parser("query", parents=[common])
    i_q.add_argument("--table", default="tasks", choices=("tasks", "decisions"))
    i_q.add_argument("--status")
    i_q.add_argument("--text")

    route_p = sub.add_parser("route", parents=[common])
    route_p.add_argument("input", nargs="+")

    ad_p = sub.add_parser("adapter")
    ad_sub = ad_p.add_subparsers(dest="adapter_command", required=True)
    ad_sub.add_parser("status", parents=[common])
    ad_inst = ad_sub.add_parser("install", parents=[common])
    ad_inst.add_argument("platform", choices=("antigravity", "claude-code", "codex"))
    ad_inst.add_argument("--target")
    ad_inst.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ws = getattr(args, "workspace", None)
    as_json = getattr(args, "json", False)

    if args.command == "help":
        return help_cmd(as_json=as_json)
    if args.command == "init":
        return init(workspace=ws, as_json=as_json)
    if args.command == "recover":
        return recover_cmd(workspace=ws, as_json=as_json)
    if args.command == "status":
        return status(workspace=ws, as_json=as_json)
    if args.command == "audit":
        return audit(fix=args.fix, workspace=ws, as_json=as_json)
    if args.command == "handoff":
        return handoff(
            summary=args.summary,
            commands=args.commands,
            decisions=args.decisions,
            blockers=args.blockers,
            next_actions=args.next_actions,
            read_first=args.read_first,
            workspace=ws,
            as_json=as_json,
        )
    if args.command == "optimize":
        return optimize_cmd(
            symptom=" ".join(args.symptom),
            command=args.bench_cmd,
            runs=args.runs,
            sql_db=args.sql_db,
            query=args.query,
            profile_py=args.profile_py,
            save_baseline=args.save_baseline,
            compare=args.compare,
            workspace=ws,
            as_json=as_json,
        )
    if args.command == "task":
        tc = args.task_command
        if tc == "start":
            return task_start(
                " ".join(args.title),
                objective=args.objective,
                criteria=args.criteria,
                workspace=ws,
                as_json=as_json,
            )
        if tc == "list":
            return task_list_cmd(
                status_filter=args.status,
                blocked_only=args.blocked,
                include_closed=args.include_closed,
                workspace=ws,
                as_json=as_json,
            )
        if tc == "show":
            return task_show_cmd(args.id, workspace=ws, as_json=as_json)
        if tc == "update":
            return task_update_cmd(
                args.id,
                workspace=ws,
                as_json=as_json,
                status=args.status,
                progress=args.progress,
                evidence=args.evidence,
                blocker=args.blocker,
                clear_blockers=args.clear_blockers,
                next_action=args.next_action,
                decision_id=args.decision,
                add_criterion=args.add_criterion,
                check_criterion=args.check_criterion,
            )
        if tc == "complete":
            return task_complete_cmd(
                args.id,
                evidence=args.evidence,
                verify_all=args.verify_all,
                force=args.force,
                workspace=ws,
                as_json=as_json,
            )
        if tc == "cancel":
            return task_cancel_cmd(args.id, reason=args.reason, workspace=ws, as_json=as_json)
    if args.command == "decision":
        dc = args.decision_command
        if dc == "record":
            return decision_record_cmd(
                " ".join(args.title),
                context=args.context,
                decision=args.decision,
                alternatives=args.alternatives,
                status=args.status,
                task_id=args.task,
                supersedes=args.supersedes,
                update_context=args.update_context,
                workspace=ws,
                as_json=as_json,
            )
        if dc == "list":
            return decision_list_cmd(status_filter=args.status, workspace=ws, as_json=as_json)
        if dc == "show":
            return decision_show_cmd(args.id, workspace=ws, as_json=as_json)
        if dc == "status":
            return decision_status_cmd(
                args.id,
                args.status,
                superseded_by=args.superseded_by,
                update_context=args.update_context,
                workspace=ws,
                as_json=as_json,
            )
    if args.command == "index":
        if args.index_command == "rebuild":
            return index_rebuild(workspace=ws, as_json=as_json)
        if args.index_command == "query":
            return index_query_cmd(
                table=args.table,
                status_filter=args.status,
                text=args.text,
                workspace=ws,
                as_json=as_json,
            )
    if args.command == "route":
        routed = route_request(" ".join(args.input))
        _emit(
            routed,
            f"Route -> module={routed['module']} action={routed['action']} "
            f"risk={routed['risk']} mode={routed['interaction_mode']} args={routed['args']!r}",
            as_json=as_json,
        )
        return 0
    if args.command == "adapter":
        if args.adapter_command == "status":
            return adapter_cmd("status", workspace=ws, as_json=as_json)
        if args.adapter_command == "install":
            return adapter_cmd(
                "install",
                platform=args.platform,
                target=args.target,
                dry_run=args.dry_run,
                workspace=ws,
                as_json=as_json,
            )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
