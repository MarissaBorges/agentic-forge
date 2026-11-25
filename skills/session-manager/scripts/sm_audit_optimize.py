#!/usr/bin/env python3
"""Context Integrity (audit) and Context Optimization (optimize) engines."""
from __future__ import annotations

import cProfile
import io
import json
import os
import pstats
import re
import sqlite3
import subprocess
import time
import tracemalloc
from contextlib import closing
from pathlib import Path
from typing import Any

from sm_core import (
    SkillPaths,
    git_snapshot,
    now_iso,
    read_template,
    relpath,
    run_git,
    write_missing,
)
from sm_db import inspect_db_drift, sync_index
from sm_decisions import VALID_DECISION_STATUSES, find_conflicting_decisions, parse_decisions
from sm_tasks import VALID_TASK_STATUSES, parse_tasks, strip_html_comments

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI/API-style sk token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub personal token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "Hardcoded secret assignment",
        re.compile(r"(?i)\b(?:api_key|secret_key|password|access_token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
    ),
]

_SKIP_SCAN_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "vendor",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".phpunit.cache",
    ".cache",
    "agents-history",
    "dist",
    "build",
    "target",
    "coverage",
}


def _finding(severity: str, code: str, message: str, fixable: bool = False) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "fixable": fixable}


def _check_markdown_links(paths: SkillPaths, md_path: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not md_path.exists():
        return issues
    text = strip_html_comments(md_path.read_text(encoding="utf-8"))
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
        raw_target = match.group(1).strip()
        if not raw_target or raw_target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target_part = raw_target.split("#", 1)[0].strip()
        if not target_part:
            continue
        rel_candidate = (md_path.parent / target_part).resolve()
        root_candidate = (paths.root / target_part).resolve()
        if not rel_candidate.exists() and not root_candidate.exists():
            issues.append(
                _finding(
                    "WARNING",
                    "BROKEN_LINK",
                    f"{relpath(md_path, paths.root)} references missing path '{target_part}'",
                )
            )
    return issues


def run_audit(paths: SkillPaths, fix: bool = False) -> dict[str, Any]:
    """Audit context files, task/ADR integrity, links, secrets, Git hygiene, and SQLite drift."""
    applied_fixes: list[str] = []

    if fix:
        paths.state_dir.mkdir(parents=True, exist_ok=True)
        for d in (paths.decisions_dir, paths.notes_dir, paths.archive_dir):
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                applied_fixes.append(f"Created directory {relpath(d, paths.root)}")
        for target, tpl in [
            (paths.config_file, "config.json"),
            (paths.session_file, "SESSION.md"),
            (paths.tasks_file, "TASKS.md"),
            (paths.project_context, "PROJECT_CONTEXT.md"),
        ]:
            if write_missing(target, read_template(tpl)):
                applied_fixes.append(f"Created missing {relpath(target, paths.root)}")

    findings: list[dict[str, Any]] = []

    # 1. Required files & config validity
    for req in (paths.project_context, paths.config_file, paths.session_file, paths.tasks_file):
        if not req.exists():
            findings.append(_finding("CRITICAL", "MISSING_FILE", f"MISSING: {relpath(req, paths.root)}", fixable=True))

    if paths.config_file.exists() and paths.config_error:
        findings.append(
            _finding(
                "CRITICAL",
                "INVALID_CONFIG",
                f"INVALID: {relpath(paths.config_file, paths.root)} is not valid JSON: {paths.config_error}",
            )
        )

    # 2. Task integrity
    tasks = parse_tasks(paths)
    seen_ids: set[str] = set()
    dup_reported = False
    for task in tasks:
        tid = task["id"]
        if tid in seen_ids and not dup_reported:
            findings.append(_finding("CRITICAL", "DUPLICATE_TASK_ID", "DUPLICATE: task IDs are not unique"))
            dup_reported = True
        seen_ids.add(tid)

        if task["status"] not in VALID_TASK_STATUSES:
            findings.append(
                _finding("CRITICAL", "INVALID_TASK_STATUS", f"INCOMPLETE: {tid} has invalid/unknown status '{task['status']}'")
            )
        if not task.get("objective"):
            findings.append(_finding("WARNING", "MISSING_TASK_OBJECTIVE", f"{tid} is missing an Objective"))
        if not task.get("acceptance_criteria"):
            findings.append(_finding("WARNING", "MISSING_TASK_CRITERIA", f"{tid} has no Acceptance criteria"))
        if task["status"] == "completed":
            open_criteria = [c["text"] for c in task.get("acceptance_criteria", []) if not c["done"]]
            if open_criteria:
                findings.append(
                    _finding(
                        "WARNING",
                        "UNCHECKED_COMPLETED_TASK",
                        f"{tid} is marked completed with {len(open_criteria)} unchecked criterion/criteria",
                    )
                )
        if task["status"] == "blocked" and not task.get("blockers"):
            findings.append(_finding("WARNING", "BLOCKED_NO_REASON", f"{tid} is blocked without a Blockers entry"))
        if task["status"] in ("in_progress", "blocked") and not task.get("next_action"):
            findings.append(_finding("WARNING", "MISSING_NEXT_ACTION", f"{tid} has no Next action"))

    # 3. Decision integrity & conflicts
    decisions = parse_decisions(paths)
    for dec in decisions:
        if dec["status"] not in VALID_DECISION_STATUSES:
            findings.append(
                _finding(
                    "WARNING",
                    "INVALID_ADR_STATUS",
                    f"{dec['source_path']} has invalid status '{dec['status']}'",
                )
            )
        if not dec.get("context") or not dec.get("decision"):
            findings.append(
                _finding(
                    "WARNING",
                    "INCOMPLETE_ADR",
                    f"{dec['source_path']} is missing Context or Decision content",
                )
            )
        if dec["status"] == "superseded" and not dec.get("superseded_by"):
            findings.append(
                _finding("INFO", "SUPERSEDED_NO_TARGET", f"{dec['source_path']} is superseded without 'Superseded by'")
            )
        findings.extend(_check_markdown_links(paths, dec["path"]))

    # Detect pairwise overlapping active ADRs
    checked_pairs: set[tuple[str, str]] = set()
    for idx, dec in enumerate(decisions):
        if dec.get("status") not in ("proposed", "accepted"):
            continue
        others = [d for j, d in enumerate(decisions) if j != idx]
        for conflict in find_conflicting_decisions(others, dec["title"], dec.get("decision", "")):
            pair = tuple(sorted((dec["id"], conflict["id"])))
            if pair not in checked_pairs:
                checked_pairs.add(pair)  # type: ignore[arg-type]
                findings.append(
                    _finding(
                        "WARNING",
                        "CONFLICTING_ADRS",
                        f"Active ADRs {pair[0]} and {pair[1]} overlap on: {', '.join(conflict['overlap'])}",
                    )
                )

    # 4. Snapshot size, broken links, stale/contradictory facts
    max_lines = int(paths.config.get("max_session_lines", 150))
    max_bytes = int(paths.config.get("max_session_bytes", 12288))
    if paths.session_file.exists():
        sess_text = paths.session_file.read_text(encoding="utf-8")
        line_count = len(sess_text.splitlines())
        byte_count = len(sess_text.encode("utf-8"))
        if line_count > max_lines or byte_count > max_bytes:
            findings.append(
                _finding(
                    "WARNING",
                    "OVERSIZED_SESSION",
                    f"SESSION.md is oversized ({line_count} lines, {byte_count} bytes; limits: {max_lines} lines / {max_bytes} bytes)",
                )
            )
        findings.extend(_check_markdown_links(paths, paths.session_file))

        # Contradiction checks against Git & TASKS.md
        git = git_snapshot(paths.root)
        branch_m = re.search(r"^- Branch:\s*(.+)$", sess_text, flags=re.M)
        if git["is_repo"] and branch_m:
            sess_branch = branch_m.group(1).strip()
            if sess_branch and not sess_branch.startswith("N/A") and sess_branch != git["branch"]:
                findings.append(
                    _finding(
                        "WARNING",
                        "STALE_SESSION_BRANCH",
                        f"SESSION.md records branch '{sess_branch}' but Git HEAD is '{git['branch']}'",
                    )
                )
        active_id_m = re.search(r"^- ID:\s*([A-Z]+-[\w-]+)$", sess_text, flags=re.M)
        if active_id_m:
            sid = active_id_m.group(1).strip()
            task_map = {t["id"]: t for t in tasks}
            if sid in task_map and task_map[sid]["status"] in ("completed", "cancelled"):
                findings.append(
                    _finding(
                        "WARNING",
                        "STALE_SESSION_TASK",
                        f"SESSION.md active task {sid} is already {task_map[sid]['status']} in TASKS.md",
                    )
                )

    if paths.project_context.exists():
        ctx_text = paths.project_context.read_text(encoding="utf-8")
        if "Last verified: YYYY-MM-DD" in ctx_text:
            findings.append(
                _finding(
                    "INFO",
                    "UNVERIFIED_CONTEXT_DATE",
                    "PROJECT_CONTEXT.md still has placeholder 'Last verified: YYYY-MM-DD'",
                )
            )
        findings.extend(_check_markdown_links(paths, paths.project_context))
    if paths.tasks_file.exists():
        findings.extend(_check_markdown_links(paths, paths.tasks_file))

    # 5. Secret / data hygiene scan
    md_targets = [paths.project_context, paths.session_file, paths.tasks_file]
    if paths.decisions_dir.exists():
        md_targets.extend(sorted(paths.decisions_dir.glob("*.md")))
    if paths.notes_dir.exists():
        md_targets.extend(sorted(paths.notes_dir.glob("*.md")))
    for md in md_targets:
        if not md.exists():
            continue
        content = md.read_text(encoding="utf-8")
        for label, pattern in _SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(
                    _finding(
                        "CRITICAL",
                        "SECRET_EXPOSURE",
                        f"Potential {label} detected in {relpath(md, paths.root)}",
                    )
                )

    # 6. Git hygiene for index.sqlite
    if paths.database_file.exists() and paths.config.get("sqlite_gitignored_by_default", True):
        ok_repo, _ = run_git(paths.root, "rev-parse", "--is-inside-work-tree")
        if ok_repo:
            db_rel = relpath(paths.database_file, paths.root)
            ok_tracked, tracked_out = run_git(paths.root, "ls-files", db_rel)
            if ok_tracked and tracked_out.strip():
                findings.append(
                    _finding(
                        "WARNING",
                        "SQLITE_TRACKED_IN_GIT",
                        f"{db_rel} is tracked by Git despite sqlite_gitignored_by_default=true",
                    )
                )
            else:
                ok_ignored, _ = run_git(paths.root, "check-ignore", "-q", db_rel)
                if not ok_ignored:
                    findings.append(
                        _finding(
                            "INFO",
                            "SQLITE_NOT_GITIGNORED",
                            f"{db_rel} is not covered by .gitignore (consider adding it after reviewing existing rules)",
                        )
                    )

    # 7. SQLite drift
    if paths.database_file.exists():
        drift_msgs = inspect_db_drift(paths.database_file, tasks, decisions)
        if drift_msgs and fix:
            sync_index(paths, tasks, decisions)
            applied_fixes.append(f"Rebuilt SQLite index {relpath(paths.database_file, paths.root)}")
            drift_msgs = inspect_db_drift(paths.database_file, tasks, decisions)
        for msg in drift_msgs:
            findings.append(_finding("WARNING", "SQLITE_DRIFT", msg, fixable=True))

    blocking = [f for f in findings if f["severity"] in ("CRITICAL", "WARNING")]
    return {
        "passed": len(blocking) == 0,
        "findings": findings,
        "blocking_count": len(blocking),
        "info_count": sum(1 for f in findings if f["severity"] == "INFO"),
        "applied_fixes": applied_fixes,
    }


def _scan_workspace_bloat(paths: SkillPaths) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    largest: list[tuple[int, str]] = []
    heavy_dirs: list[dict[str, Any]] = []

    for dirpath, dirnames, filenames in os.walk(paths.root):
        current = Path(dirpath)
        kept: list[str] = []
        for d in dirnames:
            if d in _SKIP_SCAN_DIRS:
                if d != ".git":
                    heavy_dirs.append({"path": relpath(current / d, paths.root), "kind": d})
                continue
            kept.append(d)
        dirnames[:] = kept

        for fname in filenames:
            fpath = current / fname
            try:
                size = fpath.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_bytes += size
            largest.append((size, relpath(fpath, paths.root)))

    largest.sort(reverse=True)
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "largest_files": [{"path": p, "bytes": s} for s, p in largest[:5]],
        "heavy_dirs": heavy_dirs[:10],
    }


def _measure_context_overhead(paths: SkillPaths) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    total_bytes = 0
    candidates = [paths.project_context, paths.session_file, paths.tasks_file]
    if paths.decisions_dir.exists():
        candidates.extend(sorted(paths.decisions_dir.glob("*.md")))
    for p in candidates:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        b = len(text.encode("utf-8"))
        total_bytes += b
        files.append(
            {
                "path": relpath(p, paths.root),
                "lines": len(text.splitlines()),
                "bytes": b,
                "est_tokens": max(1, b // 4),
            }
        )
    return {
        "files": files,
        "total_bytes": total_bytes,
        "est_tokens": total_bytes // 4 if total_bytes else 0,
    }


def _benchmark_command(root: Path, command: str, runs: int = 1) -> dict[str, Any]:
    timings_ms: list[float] = []
    exit_codes: list[int] = []
    stderr_sample = ""
    for _ in range(max(1, runs)):
        t0 = time.perf_counter()
        proc = subprocess.run(
            command,
            cwd=str(root),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        elapsed = (time.perf_counter() - t0) * 1000.0
        timings_ms.append(round(elapsed, 2))
        exit_codes.append(proc.returncode)
        if proc.stderr and not stderr_sample:
            stderr_sample = proc.stderr.strip()[:400]
    return {
        "command": command,
        "runs": len(timings_ms),
        "timings_ms": timings_ms,
        "avg_ms": round(sum(timings_ms) / len(timings_ms), 2),
        "min_ms": min(timings_ms),
        "max_ms": max(timings_ms),
        "exit_codes": exit_codes,
        "stderr_sample": stderr_sample,
    }


def _profile_python_script(root: Path, script_path: str) -> dict[str, Any]:
    target = (root / script_path).resolve()
    if not target.is_file():
        return {"error": f"Python script not found: {script_path}"}
    code = compile(target.read_text(encoding="utf-8"), str(target), "exec")
    profiler = cProfile.Profile()
    tracemalloc.start()
    t0 = time.perf_counter()
    ns: dict[str, Any] = {"__name__": "__main__", "__file__": str(target)}
    try:
        profiler.enable()
        exec(code, ns)  # noqa: S102 - explicit user/agent requested diagnostic target
    except SystemExit:
        pass
    finally:
        profiler.disable()
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    sio = io.StringIO()
    pstats.Stats(profiler, stream=sio).sort_stats("cumulative").print_stats(8)
    return {
        "script": script_path,
        "elapsed_ms": elapsed_ms,
        "current_mem_kb": round(current_mem / 1024.0, 2),
        "peak_mem_kb": round(peak_mem / 1024.0, 2),
        "top_profile": sio.getvalue().strip().splitlines()[:14],
    }


def _inspect_sqlite_perf(db_path: Path, query: str | None = None) -> dict[str, Any]:
    if not db_path.exists():
        return {"exists": False}
    info: dict[str, Any] = {"exists": True, "size_bytes": db_path.stat().st_size, "tables": {}}
    with closing(sqlite3.connect(db_path)) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for tbl in tables:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            idxs = conn.execute(f"PRAGMA index_list({tbl})").fetchall()
            info["tables"][tbl] = {"rows": cnt, "indexes": len(idxs)}
        if query:
            cleaned = query.strip().lstrip("(")
            if not re.match(r"(?i)^select\b", cleaned):
                info["query_error"] = "Only read-only SELECT queries are supported for EXPLAIN QUERY PLAN."
            else:
                plan = conn.execute(f"EXPLAIN QUERY PLAN {query}").fetchall()
                info["query_plan"] = [" | ".join(str(x) for x in row) for row in plan]
    return info


def run_optimize(
    paths: SkillPaths,
    symptom: str = "",
    command: str | None = None,
    runs: int = 1,
    sql_db: str | None = None,
    query: str | None = None,
    profile_py: str | None = None,
    save_baseline: bool = False,
    compare: bool = False,
) -> dict[str, Any]:
    """Run non-destructive performance & context-overhead diagnostics with before/after comparison."""
    context_metrics = _measure_context_overhead(paths)
    workspace_metrics = _scan_workspace_bloat(paths)
    benchmark = _benchmark_command(paths.root, command, runs=runs) if command else None
    py_profile = _profile_python_script(paths.root, profile_py) if profile_py else None

    target_db = (paths.root / sql_db).resolve() if sql_db else paths.database_file
    sqlite_metrics = _inspect_sqlite_perf(target_db, query=query) if (sql_db or target_db.exists()) else None

    findings: list[dict[str, Any]] = []

    # Context / agent-overhead diagnostics
    if not paths.project_context.exists():
        findings.append(
            {
                "category": "context/token overhead",
                "source": "agent-context",
                "impact": "high",
                "confidence": "high",
                "effort": "low",
                "evidence": "PROJECT_CONTEXT.md is missing, forcing agents to scan more repository files.",
                "recommendation": "Run `init` and populate PROJECT_CONTEXT.md with verified stack and map.",
            }
        )
    if context_metrics["est_tokens"] > 6000:
        findings.append(
            {
                "category": "context/token overhead",
                "source": "agent-context",
                "impact": "medium",
                "confidence": "high",
                "effort": "low",
                "evidence": f"Context artifacts total {context_metrics['total_bytes']} bytes (~{context_metrics['est_tokens']} tokens).",
                "recommendation": "Trim SESSION.md and enable archive_completed in config.json.",
            }
        )
    for f in context_metrics["files"]:
        if f["path"].endswith("SESSION.md") and f["lines"] > int(paths.config.get("max_session_lines", 150)):
            findings.append(
                {
                    "category": "context/token overhead",
                    "source": "agent-context",
                    "impact": "medium",
                    "confidence": "high",
                    "effort": "low",
                    "evidence": f"{f['path']} has {f['lines']} lines.",
                    "recommendation": "Keep SESSION.md concise (<150 lines) and move durable facts to PROJECT_CONTEXT.md.",
                }
            )

    # Workspace / I/O bloat diagnostics
    if workspace_metrics["heavy_dirs"]:
        dirs_str = ", ".join(d["path"] for d in workspace_metrics["heavy_dirs"][:4])
        findings.append(
            {
                "category": "I/O & tool orchestration",
                "source": "workspace/tooling",
                "impact": "medium",
                "confidence": "medium",
                "effort": "low",
                "evidence": f"Heavy artifact/cache directories present: {dirs_str}",
                "recommendation": "Exclude cache/dependency directories from broad search and packaging.",
            }
        )
    large_files = [lf for lf in workspace_metrics["largest_files"] if lf["bytes"] > 1_000_000]
    if large_files:
        findings.append(
            {
                "category": "I/O & memory",
                "source": "application/data",
                "impact": "medium",
                "confidence": "high",
                "effort": "medium",
                "evidence": f"Large file(s) >1MB detected: {', '.join(lf['path'] for lf in large_files)}",
                "recommendation": "Avoid loading large artifacts into memory or agent context.",
            }
        )

    # Database diagnostics
    if sqlite_metrics and sqlite_metrics.get("query_plan"):
        scans = [line for line in sqlite_metrics["query_plan"] if "SCAN " in line]
        if scans:
            findings.append(
                {
                    "category": "database",
                    "source": "application/database",
                    "impact": "high",
                    "confidence": "high",
                    "effort": "low",
                    "evidence": f"Full table scan in SQLite query plan: {scans[0]}",
                    "recommendation": "Add an index on the filtered/joined columns.",
                }
            )

    # Command timing diagnostics
    if benchmark and benchmark["avg_ms"] > 1000.0:
        findings.append(
            {
                "category": "startup/execution",
                "source": "application/runtime",
                "impact": "high",
                "confidence": "high",
                "effort": "medium",
                "evidence": f"Measured command '{benchmark['command']}' avg {benchmark['avg_ms']} ms over {benchmark['runs']} run(s).",
                "recommendation": "Profile the hot path or reduce work performed during startup/execution.",
            }
        )

    # Python cProfile diagnostics
    if py_profile and py_profile.get("peak_mem_kb", 0) > 50_000:
        findings.append(
            {
                "category": "memory",
                "source": "application/runtime",
                "impact": "high",
                "confidence": "high",
                "effort": "medium",
                "evidence": f"Peak traced memory {py_profile['peak_mem_kb']} KB in {py_profile['script']}.",
                "recommendation": "Stream large structures or eliminate redundant in-memory copies.",
            }
        )

    snapshot = {
        "recorded_at": now_iso(str(paths.config.get("timezone", "UTC"))),
        "symptom": symptom,
        "context": context_metrics,
        "workspace": workspace_metrics,
        "benchmark": benchmark,
        "python_profile": py_profile,
        "sqlite": sqlite_metrics,
        "findings": findings,
    }

    baseline_path = paths.notes_dir / "perf-baseline.json"
    comparison: dict[str, Any] | None = None
    if compare and baseline_path.exists():
        prev = json.loads(baseline_path.read_text(encoding="utf-8"))
        comparison = {
            "baseline_recorded_at": prev.get("recorded_at"),
            "delta_context_bytes": context_metrics["total_bytes"] - prev.get("context", {}).get("total_bytes", 0),
            "delta_est_tokens": context_metrics["est_tokens"] - prev.get("context", {}).get("est_tokens", 0),
        }
        if benchmark and prev.get("benchmark"):
            prev_avg = prev["benchmark"].get("avg_ms", 0.0)
            delta_ms = round(benchmark["avg_ms"] - prev_avg, 2)
            pct = round((delta_ms / prev_avg) * 100.0, 2) if prev_avg else 0.0
            comparison["delta_benchmark_ms"] = delta_ms
            comparison["delta_benchmark_pct"] = pct

    if save_baseline:
        paths.notes_dir.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        snapshot["baseline_saved"] = relpath(baseline_path, paths.root)

    if comparison is not None:
        snapshot["comparison"] = comparison
    return snapshot
