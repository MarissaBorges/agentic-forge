# Platform adapters

The core skill is platform-neutral. Install the skill according to each
platform's skill-discovery mechanism and preserve the same `SKILL.md` behavioral
contract. Thin adapter templates are bundled in subdirectories here and can be
inspected or installed safely with:

```bash
python scripts/session_manager.py adapter status
python scripts/session_manager.py adapter install antigravity --dry-run
```

## Antigravity

- Skill location: `.agents/skills/session-manager/` (workspace) or
  `~/.gemini/skills/session-manager/` (global).
- Workflow adapter: `adapters/antigravity/session-manager.md` (installs to
  `.agents/workflows/session-manager.md`).
- Use native file/terminal tools and `scripts/session_manager.py`.

## Claude Code

- Respect `CLAUDE.md`, tool permissions, and approval settings.
- Slash command adapter: `adapters/claude-code/session-manager.md` (installs
  to `.claude/commands/session-manager.md`).

## Codex

- Respect `AGENTS.md` and sandbox/network policy.
- Snippet adapter: `adapters/codex/AGENTS.snippet.md` (use as an `AGENTS.md`
  section without overwriting existing user instructions).

## Other agents

- Follow `adapters/generic/INTEGRATION.md`: expose `SKILL.md`, allow Python 3.10+
  execution of `scripts/session_manager.py`, and never fork persistence or
  safety rules.
