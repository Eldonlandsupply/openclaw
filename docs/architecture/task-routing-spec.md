---
title: "Task Routing Specification"
summary: "Normative routing rules for orchestration-first execution"
---

# Task Routing Specification

## Scope

This specification defines how OpenClaw workers select an execution layer and when to escalate.

## Routing Algorithm

For each task:

1. Validate task against `schemas/task_item.schema.json`.
2. Build candidate layer list in fixed order:
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
   - Estimate blast radius and determinism score.
   - Select first eligible layer.
4. Record `chosen_layer` and required `Browser Rejection` rationale.
5. Execute with retries according to layer policy.
6. Publish result and audit metadata.

## Browser Gating

Browser layer can execute only when all are true:

- No higher-priority layer can complete the task.
- The task includes a non-empty `browser_rejection_reason` explaining why browser was previously rejected and why it is now required.
- Execution plan includes safe stop conditions and artifact capture.

## Escalation Rules

Severity levels:

- `S1`: policy/security block. Stop execution and escalate to operator.
- `S2`: missing credential or unavailable integration. Pause and escalate.
- `S3`: repeated operational failure after retries. Escalate with diagnostics.
- `S4`: low-confidence ambiguity. Request clarification through task comments.

Required escalation payload:

- `task_id`
- `attempted_layers`
- `failed_checks`
- `recommended_next_action`
- `owner`

## Audit Requirements

Each task must log:

- `task_id`, `source`, `priority`
- `chosen_layer`
- `attempted_layers`
- `browser_rejection_reason`
- `escalation` object if raised
- timestamps for queue, claim, start, finish
