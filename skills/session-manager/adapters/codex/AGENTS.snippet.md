## Session Manager (Codex / AGENTS.md Adapter)

This repository uses the cross-agent `session-manager` skill. Keep all core rules
in `SKILL.md`; use this snippet only for discovery and command forwarding.

- When the user invokes `/session-manager ...` or asks to recover context,
  track tasks, record decisions, optimize slowness, prepare a handoff, or audit
  project context, follow `session-manager/SKILL.md`.
- Prefer deterministic operations via `python <path-to-skill>/scripts/session_manager.py`
  with `--json` when structured output helps.
- Respect sandbox/network rules and never perform destructive or external actions
  without explicit user approval.
