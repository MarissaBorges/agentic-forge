# Changelog

## 1.0.0

- Complete implementation of all six modules across agent contract (`SKILL.md`)
  and deterministic Python helpers (`scripts/session_manager.py` and `sm_*.py`).
- Cross-agent, platform-neutral orchestration contract with thin adapters for
  Antigravity, Claude Code, Codex, and generic agents (`adapters/`).
- Adaptive execution, natural-language/typo intent routing (`sm_router.py`),
  and explicit destructive-action approval boundary (`docs/SAFETY.md`).
- Full task lifecycle (`start`, `list`, `show`, `update`, `complete`, `cancel`),
  ADR lifecycle (`record`, `list`, `show`, `status` with conflict detection),
  context recovery, automated handoff snapshot generation, diagnostics/baseline
  comparison (`optimize`), and multi-severity integrity audit (`audit --fix`).
- Versioned SQLite migrations (`schema_migrations`, `tasks`, `decisions`,
  `task_decision_links`, `sessions`) and Git integration.
- Comprehensive unit, integration, safety, and structural validation suites.
