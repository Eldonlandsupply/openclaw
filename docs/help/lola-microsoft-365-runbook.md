# LOLA Microsoft 365 validation runbook

## Execution path

- Path chosen: repo edit plus CLI validation.
- Browser rejection: browser automation is not appropriate for mailbox or Teams authorization proof when direct Microsoft Graph and Bot Framework credentials are the required control plane.

## Preconditions

1. The tenant admin has approved the exact Graph permissions LOLA needs.
2. `LOLA_M365_MAILBOX_UPN` is set to `tynski@eldonlandsupply.com`.
3. `LOLA_M365_TENANT_ID` matches the target Entra tenant.
4. If using delegated validation, the access token belongs to `tynski@eldonlandsupply.com`.
5. If using Teams bot transport, `MSTEAMS_APP_ID`, `MSTEAMS_APP_PASSWORD`, and `MSTEAMS_TENANT_ID` are set.

## Local proof steps

### 1. Static matrix validation

```bash
pnpm vitest run src/agents/lola/microsoft365-audit.test.ts
```

Success means the repo audit helpers are working. It does **not** prove live tenant access.

### 2. Teams transport probe

Use the existing Teams plugin probe path after setting real credentials.

### 3. Mailbox binding proof

Provide a real delegated token or explicit permission inventory through environment variables and run the LOLA audit helper in a local script or REPL before enabling writes.

Required checks:

- token tenant ID equals `LOLA_M365_TENANT_ID`
- delegated token UPN equals `LOLA_M365_MAILBOX_UPN`
- required scopes or roles cover the capability matrix entries you intend to use

## Production enablement checklist

- [ ] Mail read path verified
- [ ] Draft creation verified
- [ ] Send or reply path verified
- [ ] Calendar read verified
- [ ] Contacts read verified if used
- [ ] Teams chat read verified if used
- [ ] Teams channel read or send verified if used
- [ ] Transcript access verified if used
- [ ] Approval gate remains enabled for high-impact actions
- [ ] Audit log redaction reviewed

## Failure labels

- `BLOCKED`: no legitimate tenant credentials or admin consent
- `MISSING`: config or permission inventory missing
- `MISCONFIGURED`: wrong tenant, mailbox, or auth mode
- `UNPROVEN`: code exists but live capability has not been validated
