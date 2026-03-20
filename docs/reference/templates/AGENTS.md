---
title: "AGENTS.md Template"
summary: "Workspace template for AGENTS.md"
read_when:
  - Bootstrapping a workspace manually
---

# AGENTS.md

This folder is home. Treat it that way.

## Non-negotiable rules

- Start every task by choosing the highest-priority direct execution path:
  API, n8n, MCP, repo edit, storage, CLI, provider API, browser last.
- If browser automation is not used, include a short Browser Rejection note in
  task output.
- If browser automation is used, explain why higher-priority paths were not
  suitable.
- Write durable memory to files. Do not rely on mental notes.
- Require every child agent to return an artifact path or an explicit
  `NO_ARTIFACT` result.
- Keep child-agent fan-out conservative by default. Spawn more only when the
  task clearly benefits.
- Ask before destructive commands or external side effects.

## Session start

Before doing anything else:

1. Read `SOUL.md`.
2. Read `USER.md`.
3. Read `memory/YYYY-MM-DD.md` for today and yesterday, creating today's file if needed.
4. If in the main private session, also read `MEMORY.md`.
5. Route the task before taking action.

## Task-start router

At the start of each non-trivial task, record:

- execution path chosen
- why that path won
- browser rejection note
- files or artifacts involved
- approvals needed, if any
- blockers or unknowns

## Memory

Use two layers:

- `memory/YYYY-MM-DD.md`, append-only daily log for fresh notes
- `MEMORY.md`, distilled long-term memory for durable facts and preferences

Nightly, or on another regular cadence, distill recent daily logs into
`MEMORY.md` and prune stale entries.

## Child agents

When delegating:

- give a narrow goal
- set a clear spawn ceiling
- require artifact output
- require explicit unknowns and blockers
- prefer direct interfaces over browser steps

## Tool risk tiers

Classify tools before use:

- Low risk: read-only inspection, local analysis, drafting
- Medium risk: repo edits, local writes, internal workflow triggers
- High risk: destructive commands, credential use, external sends, public actions

Put high-risk and destructive actions behind approval wrappers.

## Compaction discipline

When context gets crowded, summarize or compact early instead of letting the
session drift. Promote durable facts to memory files before compaction.

## File roles

- `AGENTS.md`: durable rules and workflow policy
- `SOUL.md`: identity, tone, boundaries
- `USER.md`: human-specific preferences and facts
- `TOOLS.md`: local environment notes
- `BOOTSTRAP.md`: one-time first-run interview only
- `BOOT.md`: tiny startup checklist
- `HEARTBEAT.md`: tiny recurring checklist

Keep this file small and durable. Move one-off notes elsewhere.
