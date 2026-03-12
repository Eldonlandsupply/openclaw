# Codex task pickup runbook

## Purpose

Provide a short operator flow for orchestration first task pickup and execution.

## Steps

1. Confirm new task arrived from n8n ingestion with attachments in S3 inbox.
2. Verify MCP task record exists, then set status to `planning`.
3. Build execution plan using route order: API, n8n, MCP, repo edit, DB or storage, CLI, browser.
4. Execute first viable direct route.
5. Update MCP task record after each step.
6. If all direct routes fail, document failures and use browser fallback only if policy allows.
7. Write required outputs: execution path, browser rejection reason, files used, actions taken, result, blockers, retry or escalation state.
8. Escalate only for approvals, missing credentials, policy blocks, low confidence, or repeated failure.

## Operator checks

- Attachments are present in both n8n payload and S3 inbox.
- Task transitions are visible in MCP logs.
- Browser fallback has explicit rejection evidence for all direct routes.
- Final status is `completed`, `blocked`, `retry_scheduled`, or `escalated`.
