# Generic Agent Adapter Guide

To integrate `session-manager` into any agentic coding environment:

1. **Discover `SKILL.md`:** Expose `session-manager/SKILL.md` through the host
   agent's skill, rule, or system-prompt discovery mechanism.
2. **Preserve the contract:** Do not weaken `docs/SAFETY.md` or change Markdown
   as the source of truth.
3. **Wire deterministic helpers (optional but recommended):** Ensure Python 3.10+
   can execute `scripts/session_manager.py` inside the workspace.
4. **Map slash commands:** Forward `/session-manager <args>` to `SKILL.md` and
   optionally call `python scripts/session_manager.py route "<args>" --json`
   to normalize typos, natural language, and risk classification.
