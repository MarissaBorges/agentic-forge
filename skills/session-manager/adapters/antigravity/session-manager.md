---
description: Session Manager orchestration entrypoint for Antigravity workflows (/session-manager).
---

# Session Manager Workflow Adapter (Antigravity)

This is a thin platform adapter. All behavioral rules, safety boundaries,
adaptive interaction policies, and persistence formats live in `SKILL.md`.

1. Load and follow the skill contract in `skills/session-manager/SKILL.md`
   (or your installed `~/.gemini/skills/session-manager/SKILL.md`).
2. Route the user's request (`$ARGUMENTS` or natural language) using
   `python scripts/session_manager.py route "<request>" --json` when helpful.
3. Prefer deterministic bundled helpers (`scripts/session_manager.py`) for
   `init`, `recover`, `task`, `decision`, `handoff`, `optimize`, `audit`, and `index`.
4. Never bypass the destructive-action approval boundary defined in `docs/SAFETY.md`.
