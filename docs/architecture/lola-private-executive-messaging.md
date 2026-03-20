---
title: "LOLA private executive messaging"
description: "Production architecture for a secure 1-to-1 Lola channel over WhatsApp first, with iMessage as an optional secondary adapter."
---

# LOLA private executive messaging

This document defines the first production architecture for a private, 1-to-1 executive-assistant channel where Matthew can message LOLA over WhatsApp, and later iMessage where the operational tradeoffs are acceptable.

## 1. Recommended architecture

### Single most important architectural decision

Build **WhatsApp first, through the existing OpenClaw WhatsApp Web channel**, then add LOLA-specific identity, approvals, memory, and audit controls behind the shared inbound envelope.

Do **not** build the MVP around iMessage.

Why:

- WhatsApp already has a production-ready OpenClaw channel path. `/channels/whatsapp` documents the Web channel, allowlists, pairing, and routing model already in the product. `/channels/whatsapp`
- iMessage in OpenClaw is either legacy `imsg` or BlueBubbles-backed, both of which depend on a Mac bridge and are weaker operationally. `/channels/imessage`, `/channels/bluebubbles`
- LOLA already has approval, audit, memory, and external-action scaffolding, so the missing piece is the executive messaging layer and policy logic, not a new agent framework. `/architecture/lola-phase-1`, `/architecture/lola-phase-2`, `/architecture/lola-phase-3`

### Target production topology

```text
Matthew WhatsApp
  -> WhatsApp Web account dedicated to LOLA
  -> OpenClaw gateway WhatsApp listener
  -> LOLA private-channel ingress
  -> identity + trust check
  -> dedupe + replay guard
  -> intent classifier + confidence scorer
  -> policy engine + approval gate
  -> Lola orchestrator
  -> memory lookup + task store + audit log
  -> tool or provider executor
  -> approval queue if needed
  -> execution receipt
  -> WhatsApp reply to Matthew
```

Optional iMessage later:

```text
Matthew iMessage
  -> BlueBubbles or imsg bridge on dedicated Mac
  -> OpenClaw iMessage adapter
  -> same LOLA private-channel ingress
  -> same identity, policy, approval, memory, and audit path
```

### Message flow

```text
Inbound text
  -> channel adapter normalize
  -> sender identity allowlist check
  -> channel-session trust lookup
  -> message id dedupe + replay TTL check
  -> intent taxonomy classification
  -> confidence scoring
  -> action plan build
  -> approval rule evaluation
  -> memory retrieval
  -> tool execution or approval queue
  -> audit/event log write
  -> response formatter
  -> outbound reply + execution receipt
```

### Memory and context preservation

Use three memory layers:

1. **Thread memory**
   - one durable thread per operator identity and channel endpoint
   - stores turns, message ids, reply linkage, pending approvals, and latest routing context
2. **Executive memory**
   - durable facts about preferences, recurring priorities, contact aliases, approval preferences, and operating rules
3. **Task memory**
   - structured open loops, pending approvals, delegated tasks, follow-ups, reminders, and execution receipts

Rules:

- conversational text is not memory by default
- only approved memory facts or high-confidence low-risk facts become durable
- outbound receipts must reference task ids or approval ids
- memory writes must be auditable and reversible

### Permissions and approvals

Use explicit trust tiers:

| Trust tier | Sender                                        | Allowed actions                       |
| ---------- | --------------------------------------------- | ------------------------------------- |
| T0         | unknown or unpaired sender                    | blocked, or pairing-only              |
| T1         | known sender, low-trust session               | informational replies only            |
| T2         | Matthew trusted sender                        | drafts, status, reminders, safe reads |
| T3         | Matthew trusted sender with explicit approval | sends, mutations, external actions    |
| T4         | admin override                                | policy maintenance only               |

Approval defaults:

- read-only queries, no approval
- draft creation, no approval
- external send, approval required unless the message explicitly references an existing draft and includes a high-confidence send approval phrase
- calendar changes, CRM writes, contact updates, and delegated tasks with side effects, approval required
- any destructive, sensitive, or ambiguous action, block or escalate

## 2. Channel comparison table

| Path                              | Reliability                                                         | Maintainability                                                 | Speed             | Security                                                                     | Cost   | Fragility                                          | Vendor dependence               | Suitability for OpenClaw                | Verdict         |
| --------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------- | ----------------- | ---------------------------------------------------------------------------- | ------ | -------------------------------------------------- | ------------------------------- | --------------------------------------- | --------------- |
| WhatsApp Web via built-in channel | High enough for production if run on dedicated number and monitored | Good, because it matches existing OpenClaw channel architecture | Fast              | Strong if allowlist, pairing, and approval gates are enforced                | Low    | Moderate, because Web session health still matters | Medium, Meta client behavior    | Best current path                       | **Build first** |
| iMessage via BlueBubbles          | Medium                                                              | Medium to poor, requires dedicated Mac and bridge upkeep        | Good when healthy | Acceptable with dedicated Mac and webhook secret                             | Medium | High, because Apple and bridge behavior change     | High, Apple + BlueBubbles       | Viable secondary channel                | Build later     |
| iMessage via legacy `imsg`        | Medium to low                                                       | Poor for long-term production                                   | Good when healthy | Acceptable only with isolated macOS account                                  | Medium | High, CLI and macOS permission fragility           | High, Apple + CLI behavior      | Legacy only                             | Avoid for MVP   |
| SMS relay fallback                | Medium                                                              | Medium                                                          | Fast              | Weakest identity layer unless combined with a second factor or strict policy | Medium | Medium                                             | High, carrier or relay provider | Only for alerts or break-glass receipts | Fallback only   |

### Recommended production path

1. Dedicated WhatsApp number for LOLA.
2. Matthew primary number allowlisted.
3. Pairing disabled after bootstrap, then hard allowlist only.
4. LOLA private-channel policy layer on top of OpenClaw WhatsApp transport.
5. Optional BlueBubbles-backed iMessage mirror only after WhatsApp path is stable.

### Brutal honesty on iMessage

- iMessage is not the operationally stable first channel.
- It requires a Mac, bridge software, Apple permissions, and more recovery work.
- It is acceptable as a convenience mirror, not as the primary executive control surface.

## 3. MVP recommendation

**Single best MVP path: dedicated WhatsApp number + OpenClaw WhatsApp Web adapter + LOLA private-channel policy layer.**

Why this wins:

- It fits the existing OpenClaw channel model directly. `/channels/whatsapp`
- It avoids the Mac bridge dependency and fragility of iMessage. `/channels/imessage`
- It lets you ship identity controls, approvals, memory, audit, and task routing now, which are the actual hard requirements.

## 4. Repo structure

Recommended repo-ready layout:

```text
src/agents/lola/private-channel/
  types.ts
  policy.ts
  ingress.ts
  router.ts
  approvals.ts
  memory.ts
  receipts.ts
  audit.ts
  config.ts
  templates.ts
  policy.test.ts
  ingress.test.ts
  approvals.test.ts

src/agents/lola/providers/
  outlook-action.ts
  calendar-action.ts
  crm-action.ts

src/agents/lola/schemas/
  inbound-message.ts
  approval-request.ts
  execution-receipt.ts
  escalation-record.ts

src/channels/whatsapp/
  lola-private-adapter.ts

src/imessage/
  lola-private-adapter.ts

docs/architecture/
  lola-private-executive-messaging.md
```

### File responsibilities

- `types.ts`: canonical enums and interfaces for intents, approvals, threads, tasks, and receipts
- `policy.ts`: trust model, confidence thresholds, and approval requirements
- `ingress.ts`: normalize channel message into LOLA inbound shape, apply dedupe and replay protection
- `router.ts`: classify message type and select route
- `approvals.ts`: create, resolve, and expire approval requests
- `memory.ts`: thread memory, executive memory, and task-memory adapters
- `receipts.ts`: short execution summaries suitable for messaging channels
- `audit.ts`: audit log writer with redaction
- `config.ts`: env parsing and guardrails
- `templates.ts`: canned response templates for confirmations, denials, partial completion, and escalation
- `lola-private-adapter.ts`: channel-specific bridge that hands normalized messages to the private-channel ingress

## 5. Config / env spec

### Required environment variables

```dotenv
# Channel selection
LOLA_PRIVATE_CHANNEL_ENABLED=true
LOLA_PRIVATE_PRIMARY_CHANNEL=whatsapp
LOLA_PRIVATE_FALLBACK_CHANNEL=sms

# Identity and trust
LOLA_ALLOWED_E164=+15551234567
LOLA_ALLOWED_IMESSAGE_HANDLES=matthew@icloud.example
LOLA_ALLOWED_BLUEBUBBLES_GUIDS=
LOLA_REQUIRE_KNOWN_THREAD=true
LOLA_REQUIRE_REPLAY_PROTECTION=true
LOLA_MESSAGE_MAX_AGE_SECONDS=300

# WhatsApp adapter
LOLA_WHATSAPP_ACCOUNT_ID=executive
LOLA_WHATSAPP_DM_POLICY=allowlist
LOLA_WHATSAPP_ALLOW_FROM=+15551234567

# Optional BlueBubbles bridge
LOLA_IMESSAGE_ENABLED=false
LOLA_IMESSAGE_MODE=bluebubbles
LOLA_BLUEBUBBLES_WEBHOOK_SECRET=
LOLA_BLUEBUBBLES_ALLOWED_CHAT_IDS=

# Memory and tasking
LOLA_MEMORY_ENABLED=true
LOLA_MEMORY_PROVIDER=file
LOLA_MEMORY_ROOT=.lola/private-channel
LOLA_TASK_STORE_PROVIDER=file
LOLA_TASK_STORE_PATH=.lola/private-channel/tasks.json
LOLA_AUDIT_LOG_PATH=.lola/private-channel/audit.jsonl

# Approvals and policy
LOLA_APPROVAL_MODE=required
LOLA_AUTO_APPROVE_LOW_RISK=false
LOLA_HIGH_RISK_KEYWORDS=send,wire,delete,archive,publish,notify
LOLA_EXECUTION_RECEIPTS_ENABLED=true
LOLA_DEFAULT_TIMEZONE=America/New_York

# External actions
LOLA_EXTERNAL_ACTIONS_ENABLED=false
LOLA_EXTERNAL_ACTIONS_DEFAULT_PROVIDER=Outlook
LOLA_CALENDAR_PROVIDER=Outlook
LOLA_CRM_PROVIDER=Attio

# Webhook and adapter validation
LOLA_VALIDATE_WEBHOOK_SIGNATURES=true
LOLA_DEDUPE_TTL_SECONDS=600
LOLA_RATE_LIMIT_PER_MINUTE=20
```

### Production guidance

- store all secrets in the existing deployment secret manager, not in repo files
- use a dedicated WhatsApp account id for LOLA
- keep iMessage disabled until the BlueBubbles path is validated
- require approval mode in production for all external writes

## 6. Data schemas

Use the interfaces in `src/agents/lola/private-channel/types.ts` as the initial contracts.

### Intent taxonomy

- `chat`
- `status_request`
- `command`
- `approval_grant`
- `approval_deny`
- `reminder_create`
- `follow_up_create`
- `task_create`
- `calendar_query`
- `calendar_mutation`
- `email_query`
- `email_draft`
- `email_send`
- `crm_update`
- `urgent_escalation`
- `memory_capture`

### Confidence thresholds

| Confidence    | Meaning      | Behavior                                          |
| ------------- | ------------ | ------------------------------------------------- |
| `>= 0.9`      | unambiguous  | execute if policy allows                          |
| `0.75 - 0.89` | mostly clear | ask one clarifying question if side effects exist |
| `0.5 - 0.74`  | ambiguous    | draft only or clarify                             |
| `< 0.5`       | unsafe       | refuse to execute                                 |

### Approval triggers

Approval is required when any of the following are true:

- external communication will be sent
- a calendar event will be changed
- CRM or contact data will be modified
- a task will be delegated to another person or system
- the message includes urgent language plus a side effect
- confidence is below the route's auto-execute threshold
- message content conflicts with standing instruction such as "do not send without approval"

## 7. Execution flow diagrams in text

### WhatsApp primary flow

```text
WhatsApp inbound
  -> OpenClaw WhatsApp adapter
  -> LOLA ingress normalize
  -> allowlist + pairing + thread trust
  -> dedupe + replay TTL
  -> intent classification
  -> confidence score
  -> policy evaluation
  -> memory lookup
  -> execute safe read OR create approval request OR refuse
  -> audit log + task update
  -> concise executive reply
```

### Approval flow

```text
Inbound message
  -> classified as action requiring approval
  -> create ApprovalRequest(pending)
  -> send summary with approval id and short options
  -> wait for explicit grant or denial
  -> re-check sender identity and approval TTL
  -> execute or reject
  -> write execution receipt and audit record
```

### iMessage secondary flow

```text
iMessage inbound via BlueBubbles or imsg
  -> adapter-specific webhook or CLI event
  -> same LOLA ingress
  -> same policy and memory path
  -> same approval queue
  -> iMessage response if bridge healthy
  -> otherwise fallback notification to WhatsApp if policy allows
```

## 8. Implementation phases

### Phase 1

Scope:

- secure WhatsApp 1-to-1 ingress
- Matthew identity allowlist
- dedupe and replay protection
- read-only and draft-only Lola interactions
- simple OpenClaw execution for status, summaries, reminders, and task drafts

Key files:

- `src/agents/lola/private-channel/types.ts`
- `src/agents/lola/private-channel/policy.ts`
- `src/agents/lola/private-channel/ingress.ts`
- `src/channels/whatsapp/lola-private-adapter.ts`

Risks:

- mistaken identity from misconfigured allowlist
- duplicate message execution
- over-eager command interpretation

Dependencies:

- existing WhatsApp transport
- Lola orchestrator
- durable local `.lola/` store

Completion criteria:

- Matthew can send WhatsApp messages and receive status or draft responses
- only allowlisted sender is accepted
- duplicate inbound messages do not execute twice
- all actions produce audit rows

Tests:

- sender authorization
- replay protection
- intent classification basics
- receipt generation

### Phase 2

Scope:

- approval queue
- thread and executive memory
- task routing
- Outlook/email and calendar reads, drafts, then approved sends
- status summaries and follow-up task creation

Risks:

- memory drift
- approval bypass
- policy conflicts with standing rules

Dependencies:

- Lola phase 2 and phase 3 scaffolding
- Outlook provider wrapper
- task store durability

Completion criteria:

- approval-required sends pause correctly
- memory facts persist with auditability
- email/calendar read paths work
- explicit approvals unlock pending actions only once

Tests:

- approval lifecycle
- memory writeback
- expired approvals
- idempotent execution receipts

### Phase 3

Scope:

- BlueBubbles-backed iMessage bridge if still needed
- richer context retrieval
- voice-note ingestion if available through adapter
- proactive alerts and daily briefings
- admin dashboard visibility

Risks:

- Mac bridge instability
- webhook security errors
- split-thread context between channels

Dependencies:

- dedicated Mac runtime
- BlueBubbles webhook path and secret management
- cross-channel identity mapping

Completion criteria:

- iMessage bridge remains stable through restart and reconnect tests
- approvals and receipts behave the same as WhatsApp
- cross-channel thread identity is deterministic

Tests:

- webhook signature validation
- BlueBubbles disconnect handling
- cross-channel thread mapping
- fallback to WhatsApp notification when iMessage send fails

## 9. Failure modes and mitigations

| Failure mode                | Mitigation                                                                                   |
| --------------------------- | -------------------------------------------------------------------------------------------- |
| unauthorized access         | strict allowlist, pairing only during bootstrap, and per-channel trusted identities          |
| mistaken identity           | map sender to canonical operator id, reject unknown aliases, require existing trusted thread |
| ambiguous command execution | confidence thresholds, draft-only fallback, one-question clarification flow                  |
| duplicate execution         | message-id dedupe store plus approval nonce consumption                                      |
| webhook outage              | queue retry, dead-letter log, and operator alert                                             |
| adapter disconnect          | heartbeat checks and failover notification path                                              |
| memory drift                | write memory as typed facts, not raw chat transcript, with reviewable updates                |
| wrong tool invocation       | route by intent taxonomy and tool permission map, not free-form model selection              |
| silent failure              | mandatory execution receipt or explicit failure reply                                        |
| approval bypass             | approval ids bound to sender, thread, action hash, and TTL                                   |

## 10. Test plan

### Unit tests

- intent classification thresholds
- approval decision logic
- trust-tier derivation
- sender normalization
- receipt formatting

### Integration tests

- WhatsApp inbound normalization to LOLA ingress
- task creation and audit log persistence
- approval creation, grant, deny, and expiry
- Outlook draft path

### Security tests

- unauthorized sender rejected
- spoofed approval from wrong sender rejected
- replayed message rejected
- webhook signature failure rejected

### Ordering and dedupe tests

- out-of-order approval messages
- duplicate inbound webhook deliveries
- repeated "approve and send" after first completion

### Edge-case parsing tests

- “draft only” vs “send now”
- “do not send anything without my approval” as standing instruction
- “mark this as urgent” without a referenced object
- “approve and send” with multiple pending drafts

## 11. First-build starter files

This change adds:

- `docs/architecture/lola-private-executive-messaging.md`
- `src/agents/lola/private-channel/types.ts`
- `src/agents/lola/private-channel/policy.ts`
- `src/agents/lola/private-channel/policy.test.ts`

These starter files define the initial contracts, risk policy, and tests for the first implementation slice.

## 12. Exact next steps

1. Add the WhatsApp private-channel ingress and bind it to the existing WhatsApp adapter.
2. Enforce a single canonical operator identity for Matthew across WhatsApp and future iMessage mappings.
3. Wire approval requests into the existing Lola approval engine.
4. Persist task and receipt records under `.lola/private-channel/`.
5. Keep iMessage disabled until the WhatsApp path is stable in production.
6. Only then build the BlueBubbles adapter, not `imsg`, as the secondary channel.

## Execution log

- Execution path: repo edit.
- Why chosen: the request was for a repo-ready architecture and implementation plan grounded in the current OpenClaw codebase.
- Browser rejection: browser automation was not used because the required work was deterministic repo inspection and local file edits.
- Systems involved: docs, LOLA agent scaffolding, channel docs, and local tests.
- Files used: `docs/channels/whatsapp.md`, `docs/channels/imessage.md`, `docs/channels/bluebubbles.md`, `docs/architecture/lola-phase-1.md`, `docs/architecture/lola-phase-2.md`, `docs/architecture/lola-phase-3.md`, `src/agents/lola/*`.
- Result: architecture document and starter implementation contracts added.
- Blockers: MCP task resources were not available in this workspace, so task-store integration remains local-first.
- Retry or escalation state: no escalation required.
