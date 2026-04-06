# Operator Tool Policy

## Allowed

- exec — primary tool; use with care, prefer non-destructive flags
- read, write, edit — full workspace access
- web_fetch — for API calls and health checks
- memory_get, memory_set — for operation logs and state tracking

## Restricted

- Destructive exec (rm -rf, DROP TABLE, etc.) — requires orchestrator confirmation
- sessions_spawn — only to delegate scoped subtasks

## Guidance

Use --dry-run or equivalent flags when available. Log commands and their output.
