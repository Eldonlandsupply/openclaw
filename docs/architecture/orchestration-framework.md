# Orchestration first framework

This framework makes OpenClaw execute work through direct integrations first, and use browser automation only when no direct interface is available.

## Routing order

Use this order for every task:

1. API
2. n8n
3. MCP
4. repo edit
5. DB or storage
6. CLI
7. browser

## Core flow

1. Ingest request and attachments.
2. Send attachments to n8n ingestion workflow.
3. Store canonical attachment copies in the S3 compatible inbox.
4. Create a task record in the MCP backed task system.
5. Build execution plan following the routing order.
6. Execute directly through server, API, repo, storage, or CLI interfaces.
7. Use browser automation only if all direct paths are blocked.
8. Write task outputs and audit logs back to MCP task storage.

## Required task output fields

Every task result must include:

- execution path
- why browser automation was rejected
- files used
- actions taken
- result
- blockers
- retry or escalation state

## Escalation policy

Escalate only for:

- approvals
- missing credentials
- policy blocks
- low confidence
- repeated failure
