---
title: Task routing specification
description: Route incoming requests into durable, auditable tasks with deterministic execution paths.
---

## Purpose

Define how OpenClaw routes incoming requests into durable, executable tasks.

## Routing steps

### Step 1: Classify the request

Parse each request into the following fields:

- `intent`
- `target_system`
- `request_summary`
- `attachments_present`
- `urgency`
- `approval_status`
- `execution_mode`

### Step 2: Choose execution mode

Use this decision order:

1. Immediate direct execution for trivial, synchronous, low risk actions.
2. Queued task execution for multi-step, file-based, cross-system, or auditable work.

### Step 3: Route by request type

#### Attachment-based requests

Examples:

- Website changes from a marked-up PDF
- Content updates from a draft document
- Invoice or contract processing

Routing:

1. Send to n8n ingestion workflow.
2. Store in an S3-compatible inbox.
3. Register metadata.
4. Create task.
5. Codex picks up and executes through direct interfaces.

#### CMS or website updates

Examples:

- Update copy
- Replace assets
- Edit landing pages

Routing:

1. Create task.
2. Use a CMS MCP server or direct CMS API.
3. Avoid browser admin editing unless no direct path exists.

#### Email operations

Examples:

- Send customer update
- Trigger follow-up
- Draft campaign

Routing:

1. Use n8n webhook or provider API.
2. Use templates and structured payloads.
3. Store logs centrally.

#### Repo or code changes

Examples:

- Fix bug
- Update config
- Add docs
- Refactor integration

Routing:

1. Create task.
2. Codex executes directly in the repository.
3. Return changed files, tests run, and risk notes.

#### Logging and audit

Examples:

- Execution trail
- Workflow results
- Incident reports

Routing:

1. Write to structured log sink.
2. Do not use browser inspection as the primary method.

## Required task output

Every task must emit:

- Chosen execution path
- Why that path was chosen
- Why browser automation was rejected
- Artifacts used
- Actions taken
- Result
- Blockers
- Retry state
- Escalation state
