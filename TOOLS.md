# TOOLS

## Security-sensitive environment controls for LOLA

- `WHATSAPP_CEO_PRIMARY_NUMBER` (required when `LOLA_ENABLED=true`)
- `WHATSAPP_AUTHORIZED_ASSISTANTS` (optional)
- `WHATSAPP_ALLOWED_NUMBERS` (optional)
- `M365_TENANT_ID`, `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `M365_USER_EMAIL`
- `M365_SCOPES` (optional scope declaration)
- `M365_TOKEN_CACHE_FILE` (must end in `.enc.json`)

## Operational checks

- Startup fails when strict WhatsApp authorization is enabled and no CEO number exists.
- Startup fails when Graph-enabled LOLA is missing required M365 secrets.
- Unauthorized WhatsApp slash commands get a denial response.
- Logs should not include plaintext secret values.
