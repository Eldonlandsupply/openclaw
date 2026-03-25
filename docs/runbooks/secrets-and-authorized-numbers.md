---
title: "Secrets and authorized numbers"
summary: "Runbook for LOLA WhatsApp command authorization and Microsoft Graph secret operations"
---

# Secrets and authorized numbers

## Execution path

- Startup validation: `src/security/startup-validation.ts`
- WhatsApp command authorization: `src/security/authorized-numbers.ts` + `src/auto-reply/command-auth.ts`
- Slash-command deny response: `src/auto-reply/reply/commands-core.ts`

## Where secrets live

- Primary env file: `~/.openclaw/.env`
- Microsoft token cache: `~/.openclaw/credentials/m365/token-cache.enc.json`

Repo-local `.env` is rejected by default.

## Configure authorized numbers

1. Set CEO number:
   - `WHATSAPP_CEO_PRIMARY_NUMBER=CEO|+15555550123`
2. Add assistants:
   - `WHATSAPP_AUTHORIZED_ASSISTANTS=EA|+15555550124,Ops|+15555550125`
3. Optional extra allowlist:
   - `WHATSAPP_ALLOWED_NUMBERS=Board|+15555550126`

All numbers are normalized to E.164 before matching.

## Add or remove an authorized assistant

1. Edit `WHATSAPP_AUTHORIZED_ASSISTANTS` in `~/.openclaw/.env`.
2. Restart OpenClaw gateway.
3. Send `/status` from the assistant number to verify authorization.

## What happens when unauthorized sender messages LOLA command

- Slash command is blocked.
- User receives an unauthorized command response.
- A safe log line is emitted without exposing secrets.

## Microsoft Graph secret rotation

1. Create new app secret in Entra.
2. Update `M365_CLIENT_SECRET` in `~/.openclaw/.env`.
3. Restart gateway.
4. Validate with LOLA Graph-related command flow.
5. Revoke old secret.

## Misconfiguration recovery

If startup exits with security validation errors:

1. Read listed missing variables.
2. Set required `WHATSAPP_*` and `M365_*` values.
3. Confirm token cache file ends with `.enc.json`.
4. Restart gateway.

## Verification checklist

- Authorized CEO number can run `/status` on WhatsApp.
- Unauthorized number is denied.
- Startup fails when required M365 values are missing.
- Logs do not show plaintext `M365_CLIENT_SECRET`.
