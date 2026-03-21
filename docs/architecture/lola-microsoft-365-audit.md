---
title: "LOLA Microsoft 365 audit"
description: "Audit findings, permission matrix, validation path, and operator controls for LOLA mailbox and Teams access."
---

# LOLA Microsoft 365 audit

## Executive findings

1. The current LOLA TypeScript scaffold does **not** have real Microsoft 365 mailbox access. The shipped Outlook action provider is a stub that always returns success-shaped output without talking to Microsoft Graph. Treat every mailbox write claim in the current LOLA scaffold as **UNPROVEN** until a real Graph client exists and passes validation.
2. The legacy Python `eldon` Outlook connector is **not production-grade** for LOLA. It uses client-credentials polling only, hard-marks unread mail as read, suppresses replies, has no mailbox capability matrix, no tenant binding proof, no webhook path, and no durable refresh-token or delegated auth path.
3. Teams support exists in the OpenClaw plugin ecosystem, but it is focused on Bot Framework channel transport, not LOLA executive-ops access. That covers bot messaging, not complete mailbox-plus-Teams operator access for `tynski@eldonlandsupply.com`.
4. There was no repo-native permission inventory mapping LOLA capabilities to exact Microsoft Graph scopes and roles. That gap is now fixed in code and docs, but **real tenant validation is still blocked without live credentials and admin consent**.
5. There was no repo-native auth audit that could prove mailbox binding, tenant binding, token identity, or permission sufficiency. That gap is now fixed with a typed audit module and tests.

## What exists

- LOLA Phase 1 to Phase 3 TypeScript scaffolding for drafts, approvals, open loops, memory, and dry-run external actions.
- A Teams extension that can probe Graph and Bot Framework credentials for channel transport.
- A legacy Python Outlook polling connector under `eldon/`.

## What is broken, fake, partial, or risky

### Fake or partial

- `src/agents/lola/providers/outlook-action.ts` is a stub. It does not authenticate, call Graph, draft, send, reply, or verify anything.
- LOLA executor success in Phase 3 tests proves only local bookkeeping, not real email delivery.
- There is no real LOLA mailbox health check, auth health check, or capability probe before production enablement.

### Risky

- The Python Outlook connector uses application auth only and polls unread messages every 30 seconds.
- It marks messages as read immediately after ingest. That is a silent destructive side effect.
- It logs generic warnings but does not surface structured mailbox capability health.
- It has no subscription lifecycle, delta sync, replay cursor, or durable failure recovery.
- It has no explicit proof that the configured tenant and mailbox are the authorized ones.

### Missing

- No explicit permission matrix for mailbox, calendar, contacts, Teams chat, Teams channel, meetings, and transcripts.
- No auth-mode inventory separating delegated, application, and bot access.
- No code-level tenant and mailbox binding validation for LOLA.
- No proof path for `tynski@eldonlandsupply.com` specifically.

## Architecture map

### LOLA TypeScript path

1. LOLA sub-agents create drafts, memory proposals, and open-loop records.
2. `ApprovalEngine` persists internal approval queue items into `.lola/phase3-store.json`.
3. `Executor` asks `PolicyEngine` for a risk decision.
4. `OutlookActionProvider` currently returns a fake success-shaped result.
5. `MemoryStore` records audit entries and external-action records.

### Teams path

1. `extensions/msteams` resolves Bot Framework credentials.
2. The plugin can probe Graph token claims and live directory lookups.
3. This is useful for Teams transport, but it is not a complete LOLA executive-ops authorization layer.

### Legacy Python path

1. `eldon/src/openclaw/main.py` conditionally enables `OutlookConnector` when Azure app settings and `outlook_user` are present.
2. `eldon/src/openclaw/connectors/outlook.py` acquires an app-only Graph token with `.default` scope.
3. It polls inbox messages, enqueues stripped text, and marks them read.
4. Reply send is deliberately suppressed.

## Permission matrix

| LOLA capability                | Delegated Graph scope(s)                | Application Graph role(s)                    | Teams bot / RSC                               | Notes                                       |
| ------------------------------ | --------------------------------------- | -------------------------------------------- | --------------------------------------------- | ------------------------------------------- |
| Read inbox                     | `Mail.Read`                             | `Mail.Read`                                  | n/a                                           | Minimum mail read path.                     |
| Search mail                    | `Mail.Read`                             | `Mail.Read`                                  | n/a                                           | Graph search rides on mail read permission. |
| Read thread context            | `Mail.Read`                             | `Mail.Read`                                  | n/a                                           | Same as read.                               |
| Draft email                    | `Mail.ReadWrite`                        | `Mail.ReadWrite`                             | n/a                                           | Needed for create/update draft flows.       |
| Send email                     | `Mail.Send`                             | `Mail.Send`                                  | n/a                                           | Usually paired with `Mail.ReadWrite`.       |
| Reply / reply-all              | `Mail.ReadWrite`, `Mail.Send`           | `Mail.ReadWrite`, `Mail.Send`                | n/a                                           | Needs read/write plus send.                 |
| Move / archive / categorize    | `Mail.ReadWrite`                        | `Mail.ReadWrite`                             | n/a                                           | Folder and metadata updates.                |
| Calendar context               | `Calendars.Read`                        | `Calendars.Read`                             | n/a                                           | Minimum meeting awareness.                  |
| Contacts lookup                | `Contacts.Read`                         | `Contacts.Read`                              | n/a                                           | Optional, only if used.                     |
| Teams direct chat read         | `Chat.Read`                             | `Chat.Read.All`                              | n/a                                           | App permission is broader.                  |
| Teams direct chat send         | `Chat.ReadWrite`                        | `Chat.ReadWrite.All`                         | n/a                                           | High-risk, approval gate recommended.       |
| Teams channel read             | `ChannelMessage.Read.All`               | `ChannelMessage.Read.Group`                  | `ChannelMessage.Read.Group`                   | Prefer RSC where possible.                  |
| Teams channel send             | `ChannelMessage.Send`                   | `ChannelMessage.Send`                        | `ChannelMessage.Send`                         | Use only for approved flows.                |
| Meeting context                | `OnlineMeetings.Read`, `Calendars.Read` | `OnlineMeetings.Read.All`, `Calendars.Read`  | n/a                                           | Meeting metadata and calendar join.         |
| Transcript read                | `OnlineMeetingTranscript.Read.All`      | `OnlineMeetingTranscript.Read.All`           | n/a                                           | Often blocked by tenant policy.             |
| Teams notifications / mentions | `Chat.Read`, `ChannelMessage.Read.All`  | `Chat.Read.All`, `ChannelMessage.Read.Group` | `Chat.ReadBasic`, `ChannelMessage.Read.Group` | Needs permissions plus eventing.            |

## Validation standard

A capability is only valid when all four are true:

1. Code path exists.
2. Config path exists.
3. Permission inventory proves the needed scope or role.
4. A live validation path succeeds against the authorized tenant and mailbox.

## New validation path added in this pass

Use the new TypeScript audit module to check configuration and token claims before enabling production writes.

```bash
pnpm vitest run src/agents/lola/microsoft365-audit.test.ts
```

What it proves:

- mailbox binding is explicit
- tenant binding is explicit
- delegated token UPN mismatches are caught
- Graph roles and scopes can be compared to the capability matrix
- unsupported capabilities are marked `UNPROVEN`

What it does **not** prove:

- live admin consent
- live mailbox data access
- live Teams data access
- live send capability

## Required external admin action

These items cannot be completed from this repo alone:

1. Create or confirm the Entra app registration for LOLA.
2. Grant the minimum Graph delegated or application permissions required by the desired capability set.
3. Grant Teams resource-specific consent where channel access is needed.
4. Bind the authorized mailbox `tynski@eldonlandsupply.com`.
5. Run live auth and capability probes with tenant-approved credentials.

## Browser rejection

Browser automation was rejected for this audit because repo inspection, code changes, and local tests are deterministic and higher priority in the orchestration order. Microsoft tenant proof requires legitimate credentials and admin consent, not UI automation.
