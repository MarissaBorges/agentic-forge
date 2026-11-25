# Architecture

## Design

The product has two cooperating layers:

- **Agent orchestration (SKILL.md):** natural-language intent routing,
  repository understanding, planning, tool selection, code-level reasoning,
  risk assessment, and user communication.
- **Deterministic local helpers (scripts/):** initialization, task metadata,
  indexing, validation, and handoff scaffolding.

Scripts intentionally do not attempt to replace the coding agent. They do not
edit application source, run arbitrary commands, or make architectural choices.

## State hierarchy

| Layer | Artifact | Loading policy |
|---|---|---|
| Session | `.session-manager/SESSION.md` | Always on recovery; keep short |
| Project | `PROJECT_CONTEXT.md` | Always on recovery |
| Task | `.session-manager/TASKS.md` | When work is active |
| Decisions | `.session-manager/decisions/` | Relevant decisions only |
| Technical notes | `.session-manager/notes/` | On demand |
| History | Git log + archive | On demand |
| Index | `.session-manager/index.sqlite` | Query when useful; rebuildable |

## Data flow

1. Agent identifies workspace and reads native instructions.
2. Agent recovers minimal context.
3. Agent classifies request and risk.
4. Agent performs work through native tools.
5. Agent records task/decision/session changes in Markdown.
6. Helper rebuilds SQLite index from Markdown.
7. Audit validates the persisted state.

## SQLite schema

The helper (`scripts/sm_db.py`) maintains versioned migrations via
`schema_migrations` across `tasks`, `decisions`, `task_decision_links`, and
`sessions` tables with source paths, identifiers, status/title, acceptance
counts, blockers, and timestamps. SQLite is disposable: deleting it must not
lose project state. The index is rebuilt with `session_manager.py index rebuild`
and queried with `session_manager.py index query`.

## Portability

The core is Markdown + Python standard library. Platform adapters should only
provide discovery metadata and invocation conventions. They must not fork
business rules or persistence semantics.

## Failure behavior

- No workspace: ask the user to open/select one.
- Missing context: continue with available evidence and report gaps.
- SQLite unavailable: continue using Markdown.
- Git unavailable: omit Git metadata; do not block local workflows.
- Script failure: preserve Markdown and report the exact failure.
