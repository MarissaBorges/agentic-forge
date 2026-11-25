# Session Manager

A cross-agent skill for managing development-session context, tasks, handoffs,
technical decisions, context optimization, and integrity checks.

**Targets:** Antigravity · Claude Code · Codex · other agentic coding tools  
**Persistence:** Markdown source of truth + SQLite rebuildable index + Git history  
**Autonomy:** autonomous for reversible local work; explicit approval for
destructive or externally consequential actions  
**Interaction:** adaptive (execute, plan, or clarify according to ambiguity/risk)

## Why it exists

Long-running coding work loses context between sessions and agents. Session
Manager makes the project state explicit and portable without forcing every
agent to load the entire repository.

## Quick start

1. Copy `session-manager/` into your agent's skills directory or configure the
   platform to discover this folder.
2. Open the project in the coding agent.
3. Invoke `/session-manager init` or ask: “Initialize Session Manager here.”
4. Start work with `/session-manager task start <goal>`.
5. Before leaving, run `/session-manager handoff`.

The slash syntax is interpreted by the agent when this skill is loaded. Native
slash-command registration varies by platform; see `adapters/README.md`.

## Commands

| Command | Purpose |
|---|---|
| `help` | Show commands and safety rules |
| `init` | Inspect workspace and create missing Session Manager files |
| `recover` | Reconstruct current project/session state (facts, inferences, unknowns) |
| `status` | Show branch, tasks, and session state |
| `task start <description>` | Create and begin a task |
| `task list` | List active, blocked, or closed tasks |
| `task show <id>` | Show full details and acceptance criteria of a task |
| `task update <id> ...` | Update status, progress, evidence, blockers, or decision links |
| `task complete <id>` | Verify acceptance criteria and complete/archive a task |
| `task cancel <id>` | Cancel a task with reason |
| `handoff` | Collect Git/task/decision state and write a verified `SESSION.md` snapshot |
| `optimize <symptom>` | Diagnose performance/context overhead with timings, SQL plans, and baselines |
| `audit [--fix]` | Validate files, links, secrets, ADRs, contradictions, and SQLite drift |
| `decision record <text>` | Record a numbered ADR, detect conflicts, and link tasks/context |
| `decision list` | List recorded ADRs |
| `decision show <id>` | Show an ADR's full contents |
| `decision status <id> <status>` | Transition ADR status (`proposed`, `accepted`, `superseded`, `deprecated`) |
| `index rebuild` / `index query` | Rebuild or query the versioned SQLite index |
| `route <text>` | Classify slash/natural-language intent and risk boundary |
| `adapter status` / `adapter install` | Inspect or install thin platform adapters |

`optmize` is accepted as a typo alias for `optimize` (alongside other common typos and PT-BR/EN natural language).

## Six modules

1. Context Recovery
2. Task Tracking
3. Session Handoff
4. Context Optimization
5. Decision Tracking
6. Context Integrity

See `docs/ARCHITECTURE.md` for design details and `docs/SAFETY.md` for the
autonomy boundary.

## Repository layout

```text
session-manager/
├── SKILL.md
├── README.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── adapters/
├── docs/
├── scripts/
├── templates/
└── tests/
```

## Deterministic tooling

The skill can work with native agent tools alone. Bundled scripts provide
repeatable local operations:

```bash
python -B scripts/session_manager.py init
python -B scripts/session_manager.py recover
python -B scripts/session_manager.py task start "Investigate item matching"
python -B scripts/session_manager.py task list
python -B scripts/session_manager.py decision record "Use SQLite rebuildable index"
python -B scripts/session_manager.py handoff
python -B scripts/session_manager.py optimize "Slow query" --save-baseline
python -B scripts/session_manager.py audit --fix
```

Python 3.10+; standard library only. The SQLite database uses versioned schema
migrations and is always rebuildable from Markdown. Run checks (using `-B` to
avoid leaving `__pycache__` artifacts) with:

```bash
python -B -m unittest discover -s tests -v
python -B scripts/validate_skill.py
```

## Design guarantees

- Markdown is authoritative; SQLite is an index/cache.
- No destructive operation is performed silently.
- Existing project instructions and user changes are preserved.
- Scripts do not execute arbitrary shell commands or edit source code.
- Missing evidence is reported rather than fabricated.

## Tips & best practices

- **Start every session with `recover`:** avoid asking the agent to read the whole repository; `recover` loads only `SESSION.md`, `PROJECT_CONTEXT.md`, active tasks, and Git state.
- **Keep `SESSION.md` short:** treat it as a baton pass (current task, changed files, verification results, blockers, next 1–3 actions), not a full project doc.
- **Keep `PROJECT_CONTEXT.md` factual:** update `Last verified` when stack, architecture, or workflows change.
- **Verify criteria before `task complete`:** record concrete evidence (`unittest`, `phpstan`, `curl`, etc.) before closing tasks.
- **Use `handoff` + new chat on long conversations:** when a chat gets very long, approve the agent's suggestion to run `handoff` and start a fresh chat using the generated `/session-manager recover` prompt — this keeps token usage lean and responses sharp.
- **Run `audit --fix` periodically:** catches broken links, oversized snapshots, accidental secrets, and SQLite/Markdown drift.
- **Keep `index.sqlite` out of Git:** it is a local rebuildable cache (`index rebuild`).
