---
description: Invoke the cross-agent Session Manager skill without forking its contract.
argument-hint: "[help|init|recover|status|task|handoff|optimize|audit|decision] ..."
---

# Session Manager Command Adapter (Claude Code)

Follow the behavioral contract in `SKILL.md` (located in your installed
`session-manager` skill directory). Respect `CLAUDE.md` and configured tool
permissions.

User request: `$ARGUMENTS`

1. Classify intent and risk via `SKILL.md` (or `python <skill>/scripts/session_manager.py route "$ARGUMENTS" --json`).
2. Execute reversible local operations autonomously using native tools and
   `<skill>/scripts/session_manager.py`.
3. Ask for explicit approval before any destructive or externally consequential action.
