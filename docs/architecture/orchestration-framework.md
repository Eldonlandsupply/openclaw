---
title: "Orchestration-First Framework"
summary: "Task execution priorities, escalation, and task lifecycle for OpenClaw"
---

# Orchestration-First Framework

OpenClaw routes every task through deterministic orchestration layers before considering UI automation.

## Routing order

Use this exact order:

1. API
2. n8n
3. MCP
4. repo edit
5. DB/storage
6. CLI
7. browser

Do not skip to a lower-priority layer when a higher-priority layer can satisfy the task safely.

## Core flow

1. Ingest the request and attachments.
2. Send attachments to the n8n ingestion workflow.
3. Store canonical attachment copies in the S3-compatible inbox.
4. Create a task record in the MCP-backed task system.
5. Build the execution plan using the routing order.
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

Escalate only when one of these conditions is true:

- approvals are required
- credentials are missing
- policy blocks execution
- confidence is too low for safe completion
- repeated failures exceed retry policy

## Browser Rejection requirement

Every task execution record must include a `Browser Rejection` field.

- If browser is not used, state why it was rejected.
- If browser is used, state why all higher-priority layers were unavailable, unsafe, or insufficient.

## Attachments and binary inputs

All binary attachments must be ingested through n8n and persisted in S3-compatible object storage.

Required data flow:

1. n8n receives payload and attachment metadata.
2. n8n validates content type and size limits.
3. n8n stores the attachment in S3-compatible storage.
4. n8n emits a task item with object keys and signed read URLs.
5. MCP exposes the task item for Codex pickup.

## MCP-backed task lifecycle

1. Task source submits normalized payload to n8n.
2. n8n enriches and validates the payload against `/schemas/task_item.schema.json`.
   - `/schemas/parcels.schema.json` is reserved for GeoJSON validator config consumed by `/scripts/validate_geojson.py`.
3. n8n stores task data and attachments.
4. n8n publishes the task item into the MCP task queue.
5. Codex polls the MCP queue, claims the task, and executes by priority.
6. Codex writes status updates and the final result back through MCP.

## Escalation triggers

Escalate immediately when any of the following occurs:

- Missing credentials for a required higher-priority layer.
- A policy conflict, safety guardrail, or missing approval blocks execution.
- Task ambiguity can produce unsafe side effects.
- Repeated transient failures exceed the retry budget.
- Browser use is required for authentication or an anti-bot flow that direct interfaces cannot reproduce.

See `/architecture/task-routing-spec` for routing rules and escalation severities.
