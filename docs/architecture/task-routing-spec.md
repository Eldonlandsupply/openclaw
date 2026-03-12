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
