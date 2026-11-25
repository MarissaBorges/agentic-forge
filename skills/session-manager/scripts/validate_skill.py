#!/usr/bin/env python3
"""Lightweight structural validation for the skill package."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    "SKILL.md", "README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml",
    "docs/ARCHITECTURE.md", "docs/SAFETY.md", "adapters/README.md",
    "adapters/antigravity/session-manager.md",
    "adapters/claude-code/session-manager.md",
    "adapters/codex/AGENTS.snippet.md",
    "adapters/generic/INTEGRATION.md",
    "scripts/session_manager.py", "scripts/sm_core.py", "scripts/sm_db.py",
    "scripts/sm_tasks.py", "scripts/sm_decisions.py",
    "scripts/sm_recovery_handoff.py", "scripts/sm_audit_optimize.py",
    "scripts/sm_router.py",
    "templates/PROJECT_CONTEXT.md", "templates/SESSION.md",
    "templates/TASKS.md", "templates/ADR.md", "templates/config.json",
]
issues = [f"Missing file: {p}" for p in required if not (ROOT / p).is_file()]

skill_path = ROOT / "SKILL.md"
if skill_path.is_file():
    skill = skill_path.read_text(encoding="utf-8")
    frontmatter = re.match(r"^---\r?\n(.*?)\r?\n---", skill, flags=re.S)
    if not frontmatter:
        issues.append("SKILL.md missing YAML frontmatter")
    else:
        fm_text = frontmatter.group(1)
        for key in ["name:", "description:", "compatibility:"]:
            if key not in fm_text:
                issues.append(f"SKILL.md frontmatter missing key: {key}")
    for token in ["Context Recovery", "Task Tracking", "Session Handoff",
                  "Context Optimization", "Decision Tracking", "Context Integrity"]:
        if token not in skill:
            issues.append(f"SKILL.md missing module: {token}")

config_path = ROOT / "templates/config.json"
if config_path.is_file():
    try:
        json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(f"templates/config.json invalid JSON: {exc}")

tasks_tpl = ROOT / "templates/TASKS.md"
if tasks_tpl.is_file() and "## Active" not in tasks_tpl.read_text(encoding="utf-8"):
    issues.append("templates/TASKS.md missing '## Active' heading")

if issues:
    print("Validation failed:")
    print("\n".join(f"- {x}" for x in issues))
    sys.exit(1)
print(f"Validation passed: {len(required)} required files, frontmatter, config, and six modules present.")
