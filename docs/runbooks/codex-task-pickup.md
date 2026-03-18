---
title: "Codex Task Pickup"
summary: "Operational runbook for polling MCP tasks and executing by priority"
---

# Codex Task Pickup

## Purpose

Define repeatable steps for Codex workers to poll MCP-backed tasks, ingest attachments, and execute with orchestration-first routing.

## Preconditions

- MCP task queue is reachable.
- n8n ingestion workflow is active.
- S3-compatible storage bucket is configured.
- The worker has access to required credentials and policy config.

## Pickup flow

1. Poll the MCP task queue for `status=queued`.
2. Claim one task with an optimistic lock.
3. Validate the payload using `schemas/task_item.schema.json`.
4. Resolve attachment references from S3-compatible storage via signed URLs.
5. Route execution using `/architecture/task-routing-spec`.
6. Record a `Browser Rejection` rationale.
7. Execute the selected layer and stream structured logs.
8. Update task status to `completed` or `escalated`.

## Attachment handling

- Never ingest binary payload directly from ad hoc URLs.
- Accept only n8n-issued object keys and signed URLs.
- Fail closed on checksum mismatch, MIME mismatch, or expired signatures.

## Escalation procedure

If escalation is required:

1. Set task status to `escalated`.
2. Include escalation severity, `S1` through `S4`.
3. Include attempted layers and a failure summary.
4. Assign an owner and proposed next action.

## Completion checklist

- Task status is updated in the MCP backend.
- Output includes execution path.
- Output includes why browser automation was rejected.
- Files used are listed.
- Actions taken are listed.
- Result and blockers are recorded.
- Retry or escalation state is set.
