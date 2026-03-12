---
title: "Codex Task Pickup"
summary: "Operator runbook for task ingestion and orchestration-first execution"
---

# Codex Task Pickup

## Purpose

Define the minimum operator flow for Codex workers that pick up MCP-backed tasks created from n8n ingestion.

## Prerequisites

- n8n ingestion workflow is reachable and writing attachments to S3-compatible inbox storage.
- MCP task backend is available for read/write operations.
- Codex worker has credentials for direct API, repo, storage, and CLI paths.

## Pickup flow

1. Poll MCP task queue for `status=queued`.
2. Read task payload and verify schema (`schemas/task_item.schema.json`).
3. Confirm attachment links exist in S3-compatible inbox.
4. Select execution route using strict order:
   `API > n8n > MCP > repo edit > DB/storage > CLI > browser`.
5. Execute via the first direct route that satisfies the task.
6. Use browser automation only when all direct routes are unavailable.
7. Write completion record with required output envelope fields.

## Escalation triggers

Escalate only when:

- approval is required
- credentials are missing
- policy blocks execution
- confidence is too low
- repeated failures exceed retry policy

## Completion checklist

- Task status updated in MCP backend.
- Output includes execution path.
- Output includes why browser automation was rejected.
- Files used are listed.
- Actions taken are listed.
- Result and blockers are recorded.
- Retry or escalation state is set.
