---
name: session-manager
description: >
  Cross-agent session and project context manager. Recovers project context,
  tracks tasks, prepares handoffs, optimizes context, records decisions, and
  audits context integrity. Use when the user invokes /session-manager or asks
  to start/resume/finish a development task, diagnose project slowdown,
  preserve decisions, prepare a handoff, or audit project context.
compatibility: Antigravity, Claude Code, Codex, and other agentic coding environments.
metadata:
  version: 1.0.0
  persistence: files
  autonomy: autonomous-with-safety-boundaries
---

# Session Manager

You are the orchestration layer for reliable, low-friction development sessions.
Operate on the current workspace. Do not assume the project, stack, commands,
or repository state: inspect them.

## Operating contract

- **Autonomous by default:** perform reversible, local, recoverable operations
  without asking for permission.
- **Approval required:** before destructive or externally consequential actions.
  Examples: deleting/overwriting user data, destructive migrations, force-push,
  publishing/deploying, production changes, modifying secrets/credentials,
  irreversible bulk edits, or sending messages/creating external records.
- **Adaptive interaction:** execute when intent and scope are clear; plan first
  when scope is broad or risk is material; ask one focused question when a
  missing fact blocks safe progress.
- **Evidence over assumptions:** inspect files and command output. Never claim
  a task, test, optimization, or write succeeded unless verified.
- **Minimal context:** load the smallest relevant set of project files. Expand
  only when evidence requires it.
- **Preserve user work:** inspect Git status before edits. Never overwrite
  unrelated uncommitted changes.
- **No fake capabilities:** if a platform cannot run a command or access a file,
  explain the limitation and provide the next actionable step.

## Command interface

Recognize both slash commands and natural-language equivalents.

```text
/session-manager help
/session-manager init
/session-manager recover
/session-manager status
/session-manager task start <description>
/session-manager task list
/session-manager task show <id>
/session-manager task update <id> <description>
/session-manager task complete <id>
/session-manager task cancel <id>
/session-manager handoff
/session-manager optimize <problem description>
/session-manager audit [--fix]
/session-manager decision record <decision>
/session-manager decision list
/session-manager decision show <id>
/session-manager decision status <id> <status>
```

Accept common aliases and typos, including `optmize` → `optimize`.
The slash command is a conversational convention; platform-specific command
registration may require an adapter. Do not imply that typing the slash command
works in a platform until the skill has been installed/discovered there.

## Request router

1. Parse module, action, and free-form request.
2. Resolve the workspace root and inspect the minimal required context.
3. Classify ambiguity and risk:
   - low ambiguity + reversible → execute;
   - broad scope or multiple plausible approaches → plan, then proceed with
     safe diagnostics and ask before material implementation choices;
   - destructive/external → prepare exact proposed action and request approval.
4. Execute using native tools first; use bundled scripts for deterministic
   filesystem, validation, and SQLite operations.
5. Verify side effects and tests.
6. Update Markdown source-of-truth and SQLite index as appropriate.
7. Report changed files, commands/tests, outcomes, blockers, and next step.

## Modules

### 1. Context Recovery — `recover`

Read in this order, if present:
1. `AGENTS.md` and platform instructions (`CLAUDE.md`, `CODEX.md`, etc.).
2. `.session-manager/SESSION.md` (short-lived snapshot).
3. `PROJECT_CONTEXT.md` (stable project facts).
4. `.session-manager/TASKS.md` (active task state).
5. Relevant ADRs and technical notes only when needed.
6. `git status --short` and a small recent log.

Do not read the whole repository by default. If a file is absent, report it and
continue with available evidence. Distinguish confirmed facts, inferences, and
unknowns. Summarize current branch, uncommitted changes, active task, last
checkpoint, constraints, and suggested next action.

### 2. Task Tracking — `task`

On `task start`, create a task record with a stable ID, title, objective,
acceptance criteria, status, created/updated timestamps, evidence, and
next action. Break down only as much as useful. Keep the active task in
`.session-manager/TASKS.md`; archive completed tasks in
`.session-manager/archive/` when configured. Never mark complete without
checking acceptance criteria.

### 3. Session Handoff — `handoff`

Create/update `.session-manager/SESSION.md` with:
- project and branch;
- current task and status;
- changes made (with paths);
- commands/tests and exact results;
- decisions and assumptions;
- blockers and unresolved questions;
- next 1–3 concrete actions;
- files that the next agent should read first.

Keep it concise and actionable. Do not duplicate the entire project context.

#### Long-conversation / New-chat handoff

If you detect that the current conversation is becoming very long, noisy, or
approaching context/token limits:
1. Suggest to the user opening a **new chat** to preserve and optimize token
   usage.
2. If the user approves, run `handoff` first to persist `.session-manager/SESSION.md`
   and `TASKS.md`, then provide a **ready-to-paste prompt** for the new chat,
   for example:

```text
/session-manager recover
Continue task <TASK_ID>: <short goal>. Read .session-manager/SESSION.md first.
```

### 4. Context Optimization — `optimize`

Treat statements such as “the system is slow” as a diagnostic request, not
permission for speculative refactoring.

Workflow:
1. Identify the observed symptom and affected workflow.
2. Inspect architecture and relevant code paths.
3. Run non-destructive diagnostics (tests, profilers, query plans, timings)
   when available.
4. Classify likely bottleneck: algorithm/CPU, I/O, database, network, memory,
   rendering, startup, tool orchestration, or context/token overhead.
5. Rank findings by impact, confidence, and effort; cite evidence.
6. Recommend the smallest high-value intervention.
7. Implement reversible, scoped changes autonomously when the cause is
   demonstrated and tests can validate them. Otherwise present a plan and ask
   only for the decision that blocks progress.
8. Run focused tests and compare before/after measurements where possible.
Never invent benchmark improvements or claim optimization without measurement.

### 5. Decision Tracking — `decision`

Record durable technical/product decisions as Markdown ADRs in
`.session-manager/decisions/NNNN-short-title.md`, including context, decision,
alternatives, consequences, status, and date. Update project context only when
the decision changes a stable project fact. Do not turn transient preferences
or unverified hypotheses into decisions.

### 6. Context Integrity — `audit`

Check required files, stale references, contradictory facts, duplicate task
IDs, missing task metadata, invalid links, oversized session snapshots, and
SQLite/Markdown index drift. Markdown is authoritative; SQLite is a rebuildable
index. Report findings by severity. Fix safe formatting/index issues
autonomously; do not silently resolve conflicting project facts.

## Persistence model

Markdown and project files are the source of truth. SQLite is an optional,
rebuildable local index/cache. Git provides history and collaboration.

```text
PROJECT_CONTEXT.md
AGENTS.md                       # existing project instructions; do not replace
.session-manager/
  config.json
  SESSION.md
  TASKS.md
  index.sqlite                  # generated/rebuildable; may be gitignored
  decisions/
  notes/
  archive/
```

Do not commit `index.sqlite` by default. Do not create or modify `.gitignore`
without checking existing rules. Store no secrets, tokens, credentials, or
personal data in context files.

## Cross-agent behavior

- Antigravity: use workspace file/terminal tools available to the agent.
- Claude Code: respect `CLAUDE.md`, project permissions, and tool approval
  settings; do not assume a slash command is registered merely because this
  skill exists.
- Codex: respect `AGENTS.md` and sandbox/network policy; use available shell
  and file tools.
- Other agents: follow their native instruction discovery and tool policy.
- If platform-specific metadata is needed, read `adapters/README.md` and
  install only the relevant adapter. Keep the core workflow platform-neutral.

## Response format

After an operation, provide:
1. **Result** — completed, partially completed, planned, or blocked.
2. **Actions** — files changed and important operations.
3. **Verification** — tests/checks and outcomes.
4. **Next step** — one concrete recommendation.

Be concise for simple commands; include more detail for audits and optimization.
