---
title: "Orchestration-First Framework"
summary: "Default execution framework that prioritizes direct integrations and treats browser automation as a fallback"
---

# Orchestration-First Framework

OpenClaw defaults to direct orchestration through system integrations before any browser automation.

## Routing order

Use this routing order for task execution:

1. API
2. n8n
3. MCP
4. Repo edit
5. DB/storage
6. CLI
7. Browser

## Execution model

- Prefer deterministic machine interfaces over visual interaction.
- Send inbound attachments to the n8n ingestion workflow and store originals in the S3-compatible inbox.
- Create a task record in the MCP-backed task system before execution begins.
- Execute tasks directly via API/server/repo/tool paths whenever possible.
- Use browser automation only when all direct interfaces are unavailable or insufficient.

## Required task output envelope

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
