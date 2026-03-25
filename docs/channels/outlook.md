---
title: "Outlook and Microsoft Graph"
summary: "LOLA Microsoft Graph environment variables, validation, and secret handling"
---

# Outlook and Microsoft Graph

## Required environment variables for LOLA Graph access

Use either `M365_*` or legacy `LOLA_M365_*` names.

Required when Graph-backed LOLA actions are enabled:

- `M365_TENANT_ID`
- `M365_CLIENT_ID`
- `M365_CLIENT_SECRET`
- `M365_USER_EMAIL`

Optional:

- `M365_SCOPES`
- `M365_TOKEN_CACHE_FILE` (must end in `.enc.json`)

## Startup validation behavior

When `LOLA_ENABLED=true` and Graph actions are enabled or Graph env is present, startup validation fails fast if required values are missing.

This prevents silent fallback to insecure or partial configuration.

## Secret storage

- Store `.env` in `~/.openclaw/.env`.
- Keep token cache under `~/.openclaw/credentials/m365/`.
- Do not commit secret files, token caches, private keys, or credential exports.
