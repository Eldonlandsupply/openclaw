---
title: "Task Routing Specification"
summary: "Normative routing rules for orchestration-first execution"
---

# Task Routing Specification

## Scope

This specification defines how OpenClaw workers select an execution layer and when to escalate.

## Goal

Route every task through the most direct, deterministic interface available, keep execution auditable, and use browser automation only as a last resort.

## Routing algorithm

For each task:

1. Validate the task payload against `schemas/task_item.schema.json`.
2. Build candidate layers in this fixed order:
   - API
   - n8n
   - MCP
   - repo edit
   - DB/storage
   - CLI
   - provider API
   - browser
3. For each candidate layer:
   - Check credentials, policy allowlist, and capability match.
   - Estimate blast radius and determinism.
   - Select the first eligible layer.
4. Record `chosen_layer` and a `Browser Rejection` rationale.
5. Execute with retries according to layer policy.
6. Publish the result and audit metadata.

## Routing rules

- Stop on the first viable interface.
- Record rejected interfaces and the reason they were rejected.
- If browser fallback is selected, record why API, n8n, MCP, repo edit, DB/storage, CLI, and provider API were not viable.
- Keep execution idempotent when retries are possible.
- Persist route decisions in task logs.

## Browser gating

Browser execution is allowed only when all of the following are true:

- No higher-priority layer can complete the task.
- The task includes a non-empty `browser_rejection_reason` that explains why browser use is required.
- The execution plan includes safe stop conditions and artifact capture.

## Attachment and task ingestion

- Attachments must be sent to the n8n ingestion workflow.
- Attachment metadata and object links must be persisted in S3-compatible storage.
- A task item must be created in the MCP-backed task system before execution.

## Task lifecycle states

- `queued`
- `planning`
- `running`
- `blocked`
- `awaiting_approval`
- `retry_scheduled`
- `completed`
- `failed`
- `escalated`

## Completion record requirements

A completed task record must include:

- execution path used
- why browser automation was rejected
- files used
- actions taken
- result summary
- blockers
- retry or escalation state

## Escalation rules

Severity levels:

- `S1`: policy or security block. Stop execution and escalate to the operator.
- `S2`: missing credential or unavailable integration. Pause and escalate.
- `S3`: repeated operational failure after retries. Escalate with diagnostics.
- `S4`: low-confidence ambiguity. Request clarification through task comments.

Required escalation payload:

- `task_id`
- `attempted_layers`
- `failed_checks`
- `recommended_next_action`
- `owner`

## Audit requirements

Each task must log:

- `task_id`, `source`, `priority`
- `chosen_layer`
- `attempted_layers`
- `browser_rejection_reason`
- `escalation` object, if raised
- timestamps for queue, claim, start, and finish
