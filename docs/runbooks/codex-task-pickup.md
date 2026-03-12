---
title: "Codex Task Pickup Runbook"
summary: "Operational runbook for polling MCP tasks and executing by priority"
---

# Codex Task Pickup Runbook

## Purpose

Define repeatable steps for Codex workers to poll MCP-backed tasks, ingest attachments, and execute with orchestration-first routing.

## Preconditions

- MCP task queue is reachable.
- n8n ingestion workflow is active.
- S3-compatible storage bucket is configured.
- Worker has access to required credentials and policy config.

## Poll and Claim Loop

1. Poll MCP task queue for `status=queued`.
2. Claim one task with optimistic lock.
3. Validate payload using `schemas/task_item.schema.json`.
4. Resolve attachment references from S3-compatible storage via signed URLs.
5. Route execution using `/architecture/task-routing-spec`.
6. Record `Browser Rejection` rationale.
7. Execute selected layer and stream structured logs.
8. Update task status to `completed` or `escalated`.

## Attachment Handling

- Never ingest binary payload directly from ad hoc URLs.
- Accept only n8n-issued object keys and signed URLs.
- Fail closed on checksum mismatch, MIME mismatch, or expired signatures.

## Escalation Procedure

If escalation is required:

1. Set task status `escalated`.
2. Include escalation severity (`S1` to `S4`).
3. Include attempted layers and failure summary.
4. Assign owner and proposed next action.

## Operational Checklist

- [ ] Task validated against schema.
- [ ] Attachment URLs verified.
- [ ] Highest eligible layer selected.
- [ ] Browser rejection rationale captured.
- [ ] Result or escalation written to MCP.
