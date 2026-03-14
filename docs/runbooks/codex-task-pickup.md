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
