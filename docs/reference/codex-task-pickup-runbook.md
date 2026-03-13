---
summary: "Codex Desktop runbook for polling, claiming, executing, and writing back queued OpenClaw tasks"
read_when:
  - Operating Codex Desktop against an MCP-backed task queue
  - Defining status transitions and retry behavior for task execution
  - Deciding whether browser automation is justified for task completion
title: "Codex task pickup runbook"
---

# Codex task pickup runbook

Use this runbook to execute queued OpenClaw tasks from Codex Desktop with deterministic status updates and writeback.

## Polling loop

- Poll the MCP-backed task queue every 5 minutes.

## Eligibility

Claim a task only when all conditions pass:

- `status` is `queued`
- Approval is not pending
- Required artifacts are present
- No blocker prevents execution
- The task matches an available execution path

## Execution steps

1. Read the task.
2. Inspect `intent`, `target_system`, `storage_links`, and `execution_plan`.
3. Confirm the highest-leverage direct interface.
4. Retrieve required artifacts from storage.
5. Execute through direct interfaces.
6. Record:
   - Execution path
   - Why browser automation was rejected
   - Actions taken
   - Result
   - Blockers
   - Retry state
7. Update status.

## Status rules

- Set `in_progress` when execution starts.
- Set `blocked` when dependencies or credentials are missing.
- Set `failed` when the task cannot complete after rational retry.
- Set `needs_review` when output is complete but human verification is required.
- Set `completed` when execution and writeback are done.

## Retry rules

Retry only when reasonable:

- Transient API failure
- Temporary lock or rate limit
- Temporary storage read issue

Do not retry blindly for:

- Missing credentials
- Malformed task schema
- Missing integration
- Explicit permissions failure
- Policy block

## Browser rule

Before any browser action, record:

- Which direct interfaces were checked
- Why those interfaces were insufficient
- Why browser use is unavoidable

If this justification cannot be written clearly, do not use the browser.
