---
title: "Telegram Lola bridge"
description: "Operator-safe Telegram intake, routing, approvals, and audit behavior"
---

## What this bridge does

The Telegram Lola bridge turns Telegram inbound messages into a controlled operator entrypoint for OpenClaw.

It enforces:

- Telegram user and chat allowlists
- deterministic intent classification and route selection
- execution tier classification
- explicit Telegram approval for Tier 2 actions
- concise Telegram acknowledgements and outcomes
- audit logs for request, routing, approval, and outcome

## Required environment variables

Set these in `~/.openclaw/.env`:

- `LOLA_TELEGRAM_ENABLED=true`
- `TELEGRAM_BOT_TOKEN=<bot token>`
- `TELEGRAM_ALLOWED_USER_IDS=<comma-separated telegram user IDs>`
- optional `TELEGRAM_ALLOWED_CHAT_IDS=<comma-separated chat IDs>`
- `TELEGRAM_MODE=polling` or `TELEGRAM_MODE=webhook`
- for webhook mode: `TELEGRAM_WEBHOOK_URL` and `TELEGRAM_WEBHOOK_SECRET`

Startup validation fails if the bridge is enabled and required values are missing.

## Deterministic routing and intents

The bridge uses deterministic keywords first, then assigns both an intent and a route.

- Engineering requests classify as `engineering` and route to **CTO** with `repo_executor`.
- Operations requests classify as `operations` and route to **workflow_runner** with `workflow_engine`.
- Research synthesis requests classify as `research` and route to **research**.
- General communication requests classify as `communication` and route to **Lola** conversationally.
- Disallowed requests route to **blocked**.

Fallback now runs only after routing and capability checks. When execution is blocked, Lola returns the concrete blocker, for example missing `GITHUB_TOKEN`, missing `ATTIO_API_KEY`, or missing Microsoft Graph credentials.

## Approval flow

Tier behavior:

- Tier 0: read-only/status/summary
- Tier 1: low-risk preapproved actions
- Tier 2: side-effect actions, requires explicit Telegram approval
- Tier 3: blocked

Tier 2 flow:

1. Request arrives, stored as pending approval
2. Bridge replies with `approve <id>` / `deny <id>`
3. Operator confirms in same Telegram chat
4. Request executes once, replay is blocked

Use `what is pending?` to list pending approval IDs for the current chat.

## Blocked actions

Examples blocked immediately:

- raw shell requests
- destructive command text such as `rm -rf`
- secret retrieval attempts
- privilege escalation prompts

## Verification steps

1. Start OpenClaw with bridge enabled.
2. Send `/start` and `/help` to bot.
3. Send `Check the repo health and send CTO anything failing.` and verify CTO route status.
4. Send `Send that email now.` and verify approval prompt appears.
5. Send `approve <id>` and verify execution acknowledgement.
6. Send `Run rm -rf on the server.` and verify blocked response.

## Risks and limits

- Routing is keyword deterministic first, add org-specific patterns as operations evolve.
- Approval state is in-memory, restarts clear pending items.
- Tier 2 execution still relies on downstream agent/tool policy and should remain least-privilege.
