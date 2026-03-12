---
title: "Orchestration-First Execution Framework"
summary: "Task execution priorities, escalation, and task lifecycle for OpenClaw"
---

# Orchestration-First Execution Framework

OpenClaw routes every task through deterministic orchestration layers before considering UI automation.

## Mandatory Execution Priority

Use this exact order:

1. API
2. n8n
3. MCP
4. repo edit
5. DB/storage
6. CLI
7. provider API
8. browser

Do not skip to lower-priority layers when a higher-priority layer can satisfy the task safely.

## Browser Rejection Requirement

Every task execution record must include a `Browser Rejection` field.

- If browser is **not used**, state why it was rejected.
- If browser **is used**, state why all higher-priority layers were unavailable, unsafe, or insufficient.

## Attachments and Binary Inputs

All binary attachments must be ingested through n8n and persisted in S3-compatible object storage.

Required data flow:

1. n8n receives payload + attachment metadata.
2. n8n validates content type and size limits.
3. n8n stores attachment in S3-compatible storage.
4. n8n emits a task item with object keys and signed read URLs.
5. MCP exposes the task item for Codex pickup.

## MCP-Backed Task Lifecycle

1. Task source submits normalized payload to n8n.
2. n8n enriches and validates payload against `/schemas/task_item.schema.json`.
3. n8n stores task data and attachments.
4. n8n publishes task item into MCP task queue.
5. Codex polls MCP queue, claims task, executes by priority.
6. Codex writes status updates and final result back through MCP.

## Escalation Triggers

Escalate immediately when any of the following occurs:

- Missing credentials for required higher-priority layer.
- Policy conflict, safety guardrail, or missing approvals.
- Task ambiguity that can produce unsafe side effects.
- Repeated transient failures over retry budget.
- Browser required for authentication or anti-bot flow not reproducible in APIs.

See `/architecture/task-routing-spec` for routing rules and escalation severities.
