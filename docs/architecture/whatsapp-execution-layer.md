---
title: "WhatsApp execution layer"
description: "Production design for turning WhatsApp conversations into auditable OpenClaw execution, including controlled repository updates."
---

# WhatsApp execution layer

This document defines the production execution layer that turns WhatsApp conversations into controlled OpenClaw actions. It is not a chatbot design. It is an execution system with routing, approvals, memory, repo controls, dashboard visibility, and audit records.

## Executive architecture summary

OpenClaw should treat WhatsApp as an operator surface that feeds a deterministic execution pipeline:

1. **WhatsApp inbound** receives text, voice, images, documents, links, and reply context.
2. **Ingestion** normalizes content, transcribes voice, scans attachments, and stores canonical artifacts through n8n plus S3-compatible inbox storage.
3. **Task registration** creates or updates an MCP-backed task item. If MCP is unavailable, log `MISSING INTEGRATION` and stop before claiming task-backed execution guarantees.
4. **Router** classifies the message into intent buckets, extracts entities, assigns execution and repo risk tiers, and selects the first viable execution layer using the task routing spec.
5. **Planner** converts the discussion into structured action objects, repo change objects, approval requests, and success criteria.
6. **Executor** dispatches to OpenClaw tools, subagents, repo edits, workflows, schedules, or external integrations within policy.
7. **Approval gate** pauses Tier 3 and Tier 4 actions, shows a WhatsApp-native approval card, and waits for an explicit decision or expiry.
8. **Audit and memory** persists logs, diffs, outcomes, approvals, and follow-up patterns into short-term session memory and long-term operational memory.
9. **Delivery** sends a final WhatsApp update, dashboard status, artifacts, and retry or escalation state.

## Best integration path

**Recommended path:** keep WhatsApp on the existing Baileys-based Web channel, then add a dedicated execution layer behind the shared inbound envelope.

Why this path is best:

- It reuses the production WhatsApp transport already present in `src/web`.
- It keeps execution logic channel-agnostic where possible and WhatsApp-native where needed, especially for approvals and delivery formatting.
- It fits OpenClaw's orchestration-first model without introducing a parallel command plane.

## System design document

### Core goals

- Turn discussion into execution, not suggestions.
- Make repo updates explicit, reversible, and auditable.
- Minimize clarifying questions by inferring intent when confidence is high.
- Force policy checks before risky side effects.
- Keep every action visible in both WhatsApp and the OpenClaw dashboard.

### Non-goals

- No free-form autonomous browsing for tasks with direct system interfaces.
- No silent execution for high-risk repo or external communication actions.
- No claiming success before a tool, workflow, commit, branch, or PR actually exists.

## End-to-end workflow map

```text
WhatsApp message
  -> inbound envelope normalization
  -> attachment scan + transcription
  -> n8n ingestion + S3 artifact persistence
  -> MCP task creation/update
  -> memory lookup
  -> intent classification
  -> action object + repo change object
  -> execution tier + repo risk tier
  -> planner
  -> approval gate if required
  -> executor (tool, subagent, workflow, repo operator)
  -> validation/tests
  -> audit log + memory writeback
  -> dashboard event stream
  -> WhatsApp final summary
```

## Component list and responsibilities

| Component                                     | Responsibility                                                                      | Notes                                             |
| --------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------- |
| `src/web/inbound/*`                           | Receive and normalize WhatsApp messages and media                                   | Existing transport entrypoint                     |
| `src/whatsapp/execution-layer.ts`             | Canonical schemas and policy helpers for actions, approvals, repo changes, and logs | Added in this change                              |
| `src/whatsapp/router.ts`                      | Intent classification, entity extraction, tiering, and route selection              | New implementation phase                          |
| `src/whatsapp/planner.ts`                     | Convert normalized messages into action and repo plans                              | New implementation phase                          |
| `src/whatsapp/approvals.ts`                   | Render and resolve WhatsApp approval prompts                                        | Should bridge to existing exec approval framework |
| `src/whatsapp/executor.ts`                    | Dispatch tasks to tools, workflows, and repo operator                               | Must emit audit events                            |
| `src/whatsapp/repo-operator.ts`               | Repo inspect, branch, patch, test, and PR lifecycle                                 | Branch plus PR by default                         |
| `src/whatsapp/memory.ts`                      | Session memory and long-term operational memory adapters                            | Should build on `src/memory/*`                    |
| `src/infra/cms-task.ts` + MCP task backend    | Task creation and execution status                                                  | `MISSING INTEGRATION` if unavailable              |
| `src/infra/agent-events.ts`                   | Dashboard event fan-out                                                             | Reuse existing event stream                       |
| `src/gateway/server-methods/exec-approval.ts` | Approval plumbing for high-risk execution                                           | Existing gateway contract                         |
| `src/agents/lola/*`                           | Delegation target for executive assistant workflows                                 | Route by policy or explicit request               |

## Canonical schemas

### Message and action schema

Use `WhatsAppActionSchema` for the canonical action object. Required fields include:

- `messageId`, `userId`, `channel`, `rawText`, `normalizedText`
- `attachments`, `referencedEntities`, `referencedRepositories`
- `intentType`, `confidence`, `executionTier`, `repoRiskTier`
- `approvalRequired`, `requestedAction`, `successDefinition`
- `followUpRule`, `memoryWrite`, `agentRoute`, `toolRoute`, `repoRoute`, `status`

### Repository change schema

Use `WhatsAppRepoChangeSchema` for repo operations:

- repo identity and branch targeting
- change type
- files targeted
- rationale and implementation plan
- risk tier and approval state
- tests to run
- rollback method
- commit strategy and PR requirement

### Approval schema

Use `WhatsAppApprovalRequestSchema`:

- summary, risk label, impacted systems, impacted repositories
- likely files, irreversible consequences, expiry
- supported options: `approve`, `approve_pr_only`, `apply_do_not_merge`, `show_diff_first`, `edit_plan`, `cancel`, `expired`

### Execution log schema

Use `WhatsAppExecutionLogSchema`:

- source message and interpreted intent
- structured command
- execution path
- browser rejection reason
- tool or agent used
- files changed and diff summary
- approval state, result, tests run, branch, PR, rollback path, retry state

## Safety model and execution-tier policy

### Execution tiers

| Tier   | Meaning               | Default behavior                                                         |
| ------ | --------------------- | ------------------------------------------------------------------------ |
| Tier 0 | Log only              | Save note, context, or memory. No side effect beyond logging.            |
| Tier 1 | Draft or prepare only | Build draft, memo, plan, or issue proposal. No external execution.       |
| Tier 2 | Auto-execute low-risk | Create internal task, reminder, monitor, or safe workflow automatically. |
| Tier 3 | Approval required     | Prepare execution, show summary, wait for approval.                      |
| Tier 4 | Blocked               | Reject unless explicitly whitelisted by policy.                          |

### Default classification rules

- Informational notes map to Tier 0.
- Drafting, research, and repo inspection map to Tier 1.
- Internal task creation, monitoring, and delegation map to Tier 2.
- Direct execution commands and repo modifications map to Tier 3 unless allowlisted and low-risk.
- Secrets, destructive changes, production mutations, and sensitive outreach map to Tier 4 unless explicitly authorized.

### Additional safety controls

- Allowed sender list per WhatsApp account.
- Role-based execution scopes by sender, contact, or group.
- Attachment malware scanning and MIME validation before ingestion.
- Prompt-injection filtering for fetched links and uploaded documents.
- Execution cooldowns for dangerous commands.
- No secret material echoed back into WhatsApp replies.
- No merge to protected branches without explicit approval.

## Repository safety and merge policy

### Repo risk tiers

| Repo tier | Scope                                                                    | Default policy                                  |
| --------- | ------------------------------------------------------------------------ | ----------------------------------------------- |
| Tier A    | Read-only inspection                                                     | Auto-run                                        |
| Tier B    | Docs, prompts, comments, low-risk config, tests                          | Auto-run or batched approval                    |
| Tier C    | Feature code, workflow files, integrations, moderate-risk config         | Approval before applying changes                |
| Tier D    | Auth, infra, secrets, billing, permissions, production routing, deletion | Explicit approval, high-visibility confirmation |

### Safest repo defaults

1. Default to **branch plus PR** for any file change.
2. Keep diffs minimal and scoped to the approved request.
3. Never merge protected branches from WhatsApp without explicit policy approval.
4. Require `show_diff_first` or `approve_pr_only` for Tier C by default.
5. Escalate Tier D changes to dashboard plus WhatsApp with irreversible-impact warning.
6. Log exact files changed, tests run, and rollback path.

## Tool-routing framework

### Route order

OpenClaw must continue using:

`API > n8n > MCP > repo edit > DB/storage > CLI > provider API > browser`

### Router decision tree

1. Classify message intent and entity set.
2. Check for attachment ingestion requirements.
3. Look up memory and contact policy.
4. Evaluate whether a direct internal API can satisfy the request.
5. If not, check n8n workflow registry.
6. If not, check MCP-backed tasks and tools.
7. If not, determine whether repo edit is the correct execution layer.
8. Only fall to CLI or provider API when higher-priority deterministic interfaces are missing.
9. Use browser only as a last resort and always record `Browser Rejection` for why higher layers were unsuitable.

### Suggested route map

| Intent bucket    | Primary route         | Secondary route             |
| ---------------- | --------------------- | --------------------------- |
| Note to memory   | memory service        | MCP task update             |
| Task creation    | task service          | n8n workflow                |
| Workflow trigger | API or n8n            | MCP tool                    |
| Delegation       | Lola orchestrator     | subagent spawn              |
| Research         | research agent        | web tools with fetch only   |
| Monitoring       | cron tool             | n8n scheduler               |
| Repo inspection  | repo edit             | GitHub API                  |
| Repo update      | repo operator         | GitHub issue or PR workflow |
| Approval request | exec approval service | WhatsApp approval responder |

## Memory design

### Short-term memory

Store recent conversation context per WhatsApp session key:

- last 20 to 50 relevant turns
- active approvals
- pending follow-ups
- current project and repo focus
- recent tool outputs and blockers

### Long-term operational memory

Persist structured records for:

- people, stakeholder sensitivity, and no-auto-send policies
- recurring workflows and templates
- approval history and exceptions
- repo conventions, branch naming, test commands, protected branch rules
- recurring bug classes, CI failures, and effective fixes
- routing preferences, such as “anything from this contact is high priority”

### Memory write policy

- Write only structured, non-secret operational facts.
- Store message provenance with source channel and message ID.
- Separate user preference memory from execution audit memory.
- Mark uncertain inferences with confidence and expiry.

## WhatsApp-native approval UX

### Approval message template

```text
Approval needed: Patch OpenClaw prompt router
Risk: Repo Tier C, execution Tier 3
Systems: GitHub, OpenClaw repo, CI
Likely files: src/auto-reply/reply/agent-runner.ts, src/agents/system-prompt.ts, tests
Impact: code changes on a feature branch, no merge
Options: Approve | Approve as PR only | Apply but do not merge | Show diff first | Edit plan | Cancel
Expires: 2026-03-21T18:00:00Z
Default if no reply: expire
```

### Approval button semantics

- **Approve**: execute the approved plan and open PR if required.
- **Approve as PR only**: apply branch changes and open PR, never merge.
- **Apply but do not merge**: branch, commit, test, and stop before PR or merge if policy allows branch-only.
- **Show diff first**: generate plan and diff preview without applying.
- **Edit plan**: return the structured plan for revision.
- **Cancel**: block execution and record denial.

## WhatsApp conversation UX examples

### Example 1, task creation

**User:** “Follow up with Mike tomorrow about pricing.”

**System action:** create task, set due date, draft follow-up, keep external send in draft unless policy explicitly allows.

**WhatsApp reply:**

```text
Created follow-up task for tomorrow at 09:00 local time.
Draft prepared, not sent.
Next: Reply APPROVE to send, or EDIT to change the draft.
```

### Example 2, repo update

**User:** “Fix the CI failure and send me the diff.”

**System action:** inspect repo, classify as bug fix request, assign Repo Tier C, build plan, request approval.

**WhatsApp reply:**

```text
Plan ready for approval.
Risk: Repo Tier C.
Will inspect failing checks, patch the smallest fix, run local validation, create a branch, and send the diff summary.
Reply APPROVE AS PR ONLY, SHOW DIFF FIRST, or CANCEL.
```

### Example 3, delegated assistant flow

**User:** “Have Lola handle this and keep me posted.”

**System action:** route to Lola with context packet, task ownership, and update cadence.

## Dashboard visibility requirements

Every WhatsApp-originated task must appear with:

- task ID and owner
- source message and attachments
- route choice and browser rejection note
- approval state
- live logs and artifacts
- repo context, branch, PR, and test status when relevant
- retry and escalation controls

## API and webhook contracts

### WhatsApp inbound normalized payload

```json
{
  "messageId": "wamid-123",
  "channel": "whatsapp",
  "accountId": "work",
  "from": "+15551234567",
  "chatType": "direct",
  "body": "Patch the prompt router and create a PR",
  "attachments": [],
  "timestamp": "2026-03-20T10:15:00Z"
}
```

### Task creation contract

```json
{
  "task_id": "task-123",
  "source": "whatsapp",
  "request_summary": "Patch the prompt router and create a PR",
  "target_system": "openclaw-repo",
  "attachments": [],
  "storage_links": []
}
```

### Approval resolve contract

```json
{
  "approvalId": "approval-123",
  "decision": "approve_pr_only",
  "actor": "+15551234567",
  "channel": "whatsapp",
  "timestamp": "2026-03-20T10:20:00Z"
}
```

## GitHub integration contract definitions

The repo operator should emit and persist:

- `repo`, `owner`, `base_branch`, `target_branch`
- `requested_change_type`, `risk_tier`, `approval_state`
- `files_targeted`, `files_changed`
- `tests_requested`, `tests_run`, `test_results`
- `commit_shas`
- `pull_request_number`, `pull_request_url`
- `merge_allowed`, `merge_executed`, `merge_actor`
- `rollback_commit` or `revert_plan`

## Failure-mode and edge-case analysis

| Failure mode                                                      | Expected behavior                                                                             |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Ambiguous instruction, “do it now” with multiple possible targets | Use highest-confidence target, return structured plan, require approval before side effects   |
| Voice note with partial transcription                             | Preserve original audio, show extracted action items with uncertainty marks                   |
| Attachment fails malware scan                                     | Block execution, log security event, notify operator                                          |
| MCP task backend unavailable                                      | Mark `MISSING INTEGRATION`, keep draft-only mode, do not claim full task auditability         |
| Repo target not specified                                         | Infer from recent context if confidence is high, otherwise ask one scoped clarifying question |
| CI commands unknown                                               | Read repo docs and config, run smallest safe validation set, log unknown coverage gaps        |
| Protected branch push requested                                   | Refuse direct push, offer branch plus PR path                                                 |
| External send requested to sensitive stakeholder                  | Require explicit approval, draft only by default                                              |
| Repeated failing automation                                       | Escalate after rational retry count and log the blocker                                       |

## Repo folder structure recommendation

```text
src/
  whatsapp/
    execution-layer.ts
    router.ts
    planner.ts
    approvals.ts
    executor.ts
    memory.ts
    repo-operator.ts
    delivery.ts
    audit.ts
    prompts.ts
    types.ts
```

## Environment variable list

| Variable                              | Purpose                                        |
| ------------------------------------- | ---------------------------------------------- |
| `OPENCLAW_WHATSAPP_EXECUTION_ENABLED` | Enable execution layer behind WhatsApp channel |
| `OPENCLAW_WHATSAPP_ALLOWED_SENDERS`   | Global sender allowlist override               |
| `OPENCLAW_ATTACHMENT_SCAN_WEBHOOK`    | n8n ingestion webhook for files                |
| `OPENCLAW_S3_INBOX_BUCKET`            | Canonical artifact storage bucket              |
| `OPENCLAW_S3_INBOX_REGION`            | Storage region                                 |
| `OPENCLAW_S3_INBOX_ENDPOINT`          | S3-compatible endpoint                         |
| `OPENCLAW_TASK_BACKEND_URL`           | MCP or task proxy endpoint                     |
| `OPENCLAW_GITHUB_APP_ID`              | GitHub App integration                         |
| `OPENCLAW_GITHUB_APP_PRIVATE_KEY`     | GitHub App private key                         |
| `OPENCLAW_GITHUB_WEBHOOK_SECRET`      | GitHub callback verification                   |
| `OPENCLAW_APPROVAL_TTL_SECONDS`       | WhatsApp approval expiry                       |
| `OPENCLAW_EXECUTION_AUDIT_DATA_DIR`   | Persistent audit store path                    |
| `OPENCLAW_MEMORY_NAMESPACE_WHATSAPP`  | Memory partition for WhatsApp execution state  |

## Build order in phases

### MVP

1. Add canonical schemas, routing policy helpers, and audit log types.
2. Add WhatsApp router that classifies inbound messages and produces action objects.
3. Add approval prompt rendering for Tier 3 repo and external-send actions.
4. Add draft-only repo operator for inspect, plan, branch strategy, and diff preview.
5. Add dashboard event emission and WhatsApp final summaries.

### Production hardening

6. Add attachment ingestion through n8n plus S3 storage.
7. Add MCP task lifecycle integration and retries.
8. Add repo executor with branch, patch, test, and PR flows.
9. Add long-term operational memory and pattern learning.
10. Add alerting, rate limits, and risk analytics.

## MVP scope versus full production scope

| Scope               | MVP                                    | Full production                                        |
| ------------------- | -------------------------------------- | ------------------------------------------------------ |
| Text commands       | Yes                                    | Yes                                                    |
| Voice transcription | Basic                                  | Full with confidence spans                             |
| Attachments         | Metadata only                          | Full ingestion, scan, OCR, storage                     |
| Memory              | Session plus lightweight facts         | Structured long-term memory with learning loops        |
| Repo updates        | Plan, diff preview, branch and PR path | Full repo execution with rollback and GitHub callbacks |
| Dashboard           | Basic event stream                     | Full observability and replay                          |
| Self-improvement    | Manual review of outcomes              | Automated template promotion and failure clustering    |

## Testing plan

- Unit tests for intent classification, tier mapping, and policy evaluation.
- Unit tests for schema validation and approval option parsing.
- Integration tests for inbound WhatsApp message to action object.
- Integration tests for repo operator branch-plus-PR flow using fixture repos.
- Security tests for prompt injection, attachment policy, and sender spoofing.
- E2E tests for approval expiry, retry scheduling, and dashboard sync.
- Smoke tests for high-priority user journeys: reminder creation, Lola delegation, repo inspection, repo patch with PR.

## Monitoring and alerting plan

Track:

- inbound volume by sender and intent class
- auto-execute rate versus approval-required rate
- approval latency and expiry rate
- execution success rate and mean time to completion
- repo change failure rate by risk tier
- test failure and rollback counts
- repeated clarification count, which is a friction signal
- `MISSING INTEGRATION` events, which are launch blockers

Alert on:

- approval backlog over threshold
- attachment scan failures
- repo operator failures on protected branches
- repeated webhook delivery failures
- memory write failures
- dashboard event-stream gaps

## Internal prompt recommendations

### Router prompt

```text
Classify the WhatsApp message into one or more execution intents. Prefer action over commentary. Output only JSON matching WhatsAppActionSchema. Infer project, repo, owner, and urgency when confidence is high. If a risky side effect is requested, set executionTier to tier_3_approval or tier_4_blocked.
```

### Planner prompt

```text
Convert the action object into a deterministic execution plan. Minimize clarifying questions. Include successDefinition, required tools, approval rationale, repo risk tier, and rollback path. Output only structured JSON.
```

### Executor prompt

```text
Execute only the approved plan. Never claim completion before tool output, branch creation, commit, or PR creation exists. Emit audit events for every state transition. If uncertain, stop and mark blocked.
```

### Repo operator prompt

```text
Inspect the target repository, identify the smallest correct change, preserve repo conventions, run targeted validation, and prefer branch plus PR. Never merge protected branches without explicit approval. Output changed files, tests run, diff summary, remaining risks, and rollback steps.
```

## Sample WhatsApp conversations that trigger real execution

### Sample A, recurring monitor

**User:** “Watch this issue daily and tell me when it changes.”

**Action:** create monitor job, link GitHub issue, set daily schedule, write task record, send confirmation.

### Sample B, docs update

**User:** “Update the README and env example, apply but do not merge.”

**Action:** inspect repo, classify Repo Tier B, branch, patch docs, run docs checks, commit, stop before merge, send summary and branch name.

### Sample C, issue triage

**User:** “Open an issue for this bug and assign it.”

**Action:** draft issue, create GitHub issue through API, log task owner, send issue URL.

## Example branch and PR lifecycle

1. WhatsApp request is classified as repo modification.
2. Repo risk tier is assigned.
3. Approval request is sent if required.
4. Branch is created with repo naming convention, such as `codex/whatsapp-execution-layer`.
5. Minimal patch is applied.
6. Targeted checks run.
7. Commit is created with scoped message.
8. PR is opened against base branch.
9. Diff summary, tests, and risks are sent to WhatsApp.
10. Merge waits for explicit approval and branch protection compliance.

## Example diff-summary format returned to WhatsApp

```text
Execution complete.
Repo: openclaw/openclaw
Branch: codex/whatsapp-execution-layer
PR: #1234
Files changed:
- src/whatsapp/router.ts
- src/whatsapp/execution-layer.ts
- docs/architecture/whatsapp-execution-layer.md
Checks:
- pnpm test -- src/whatsapp/execution-layer.test.ts, passed
- pnpm check, passed
Impact:
- Added structured action and repo schemas
- Added execution tier and repo risk policy helpers
- Added production design doc for WhatsApp execution routing
Remaining risk:
- MCP task backend integration still marked MISSING INTEGRATION in this environment
Next:
- Reply MERGE PR if policy allows, otherwise review PR comments
```

## Result standard

If implemented this way, WhatsApp becomes a real operational cockpit for OpenClaw:

- discussion becomes structured execution
- risky actions stop at approval gates
- repo updates stay branch-first and auditable
- dashboard and WhatsApp stay in sync
- outcomes improve over time through memory and failure analysis
