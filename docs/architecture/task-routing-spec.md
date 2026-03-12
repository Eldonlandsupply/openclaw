# Task routing specification

## Goal

Define deterministic routing so task execution is direct, auditable, and browser last.

## Routing decision sequence

For each task step, evaluate options in this exact order:

1. API endpoint exists and credentials are valid.
2. n8n workflow exists and accepts the required payload.
3. MCP tool or MCP task service can complete the step.
4. Repository edit path can satisfy the step.
5. DB or storage operation can satisfy the step.
6. CLI command can satisfy the step safely.
7. Browser automation fallback, only if all prior checks fail.

## Routing rules

- Stop on first viable interface.
- Record rejected interfaces and reason.
- If browser fallback is selected, record why API, n8n, MCP, repo edit, DB or storage, and CLI were not viable.
- Keep execution idempotent when retries are possible.
- Persist route decisions in task logs.

## Task lifecycle states

- `queued`
- `planning`
- `running`
- `blocked`
- `awaiting_approval`
- `retry_scheduled`
- `completed`
- `failed`
- `escalated`

## Output contract

A finished task must include:

- execution path
- browser rejection reason
- files used
- actions taken
- result
- blockers
- retry or escalation state
