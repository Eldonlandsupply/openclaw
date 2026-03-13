---
title: "Task Routing Spec"
summary: "Operational specification for orchestration-first task routing and execution"
---

# Task Routing Spec

## Routing contract

OpenClaw routes each task through direct interfaces in this strict order:

`API > n8n > MCP > repo edit > DB/storage > CLI > browser`

Task runners should stop at the first route that can complete the objective with acceptable confidence and policy compliance.

## Route decision rules

1. **API**: Use provider or service APIs first when available.
2. **n8n**: Use workflow automation for ingestion, triggers, and repeatable workflows.
3. **MCP**: Use MCP servers for structured context, task reads/writes, and actions.
4. **Repo edit**: Apply direct repository edits when the task is source or config change.
5. **DB/storage**: Write/read operational data in approved storage systems.
6. **CLI**: Use CLI commands when APIs are unavailable or less reliable.
7. **Browser**: Use only if all prior routes are not possible.

## Attachment and task ingestion

- Attachments must be sent to the n8n ingestion workflow.
- Attachment metadata and object links must be persisted in S3-compatible storage.
- A task item must be created in the MCP-backed task system before execution.

## Completion record requirements

Each completed task record must store:

- execution path used
- why browser automation was rejected
- files used
- actions taken
- result summary
- blockers
- retry or escalation state
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
