# Browser last resort policy

## Policy

Browser automation is not a default execution path. Use it only after direct orchestration paths are exhausted.

## Required pre checks

Before browser use, validate and log that these paths are unavailable or blocked:

1. API
2. n8n
3. MCP
4. repo edit
5. DB or storage
6. CLI

## Allowed browser fallback cases

- No API or webhook exists for the target action.
- Required system only exposes a browser workflow.
- Temporary outage blocks all direct interfaces and the task is time critical.

## Disallowed browser fallback cases

- A direct endpoint exists but is slower to implement.
- A CLI command exists and is safe to run.
- The task can be completed with repository edits or storage operations.

## Evidence required in task outputs

- execution path used
- explicit reason each direct path was rejected
- browser action trace if browser fallback was used
- final result and follow up recommendation to remove browser dependency
