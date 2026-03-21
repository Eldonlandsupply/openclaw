---
title: "Lola WhatsApp Channel"
description: "Production architecture for the dedicated Lola WhatsApp executive assistant channel."
---

# Lola WhatsApp Channel

## Provider Decision

**Meta WhatsApp Cloud API.** Not Twilio (10x more expensive, no compensating benefit). Not Baileys (requires paired device, breaks on WhatsApp updates, no webhook, wrong for production).

## Architecture

```
Matthew WhatsApp
  -> Meta Cloud API
  -> POST /webhooks/lola/whatsapp
  -> whatsapp_service.parse_inbound()
  -> lola/pipeline.process()
      dedupe -> auth -> normalize -> classify -> execute
  -> whatsapp_service.send_message()
  -> audit.record()
```

## Files Added

```
eldon/gateway/app/gateway/lola_models.py
eldon/gateway/app/lola/__init__.py
eldon/gateway/app/lola/classifier.py
eldon/gateway/app/lola/pipeline.py
eldon/gateway/app/lola/executor.py
eldon/gateway/app/lola/approvals.py
eldon/gateway/app/lola/memory.py
eldon/gateway/app/lola/audit.py
eldon/gateway/app/lola/dedupe.py
eldon/gateway/app/lola/system_prompt.md
eldon/gateway/app/services/whatsapp_service.py
eldon/gateway/app/main.py (updated)
eldon/gateway/.env.lola.example
eldon/gateway/tests/test_lola_pipeline.py
docs/architecture/lola-whatsapp-channel.md
```

## Permission Matrix

| Action | Auto | Approval | Blocked |
|--------|------|----------|---------|
| Read calendar | x | | |
| Read inbox | x | | |
| List tasks | x | | |
| Status / health | x | | |
| Daily briefing | x | | |
| Draft email | x (draft only) | | |
| Create reminder | x | | |
| Log meeting note | x | | |
| Create follow-up | x | | |
| Send email | | x | |
| Book / cancel meeting | | x | |
| Update CRM | | x | |
| Delegate to team | | x | |
| Financial transactions | | | x |
| Delete records | | | x |
| Change prod config | | | x |

## Deployment Steps

1. `mkdir -p /opt/openclaw/.lola && chmod 700 /opt/openclaw/.lola`
2. Add vars from `.env.lola.example` to `/opt/openclaw/.env`
3. Create Meta App at developers.facebook.com, add WhatsApp product
4. Set `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
5. Set `LOLA_ALLOWED_SENDERS` to your E.164 phone number
6. Set `ENABLE_LOLA_WHATSAPP=true`
7. `sudo systemctl restart openclaw`
8. Register webhook with Meta: `https://<host>/webhooks/lola/whatsapp`
9. Subscribe to `messages` event in Meta dashboard
10. Send test message

## v2 Roadmap

- Outlook calendar + inbox read adapters
- Email draft -> approved send flow
- SQLite persistence (replace JSONL)
- Attio CRM read + write with approval
- Daily briefing cron (push to WhatsApp)

## v3 Roadmap

- Voice note transcription (Whisper on Pi)
- PDF / document ingestion via WhatsApp attachment
- Proactive follow-up alerts
- Dashboard panel: pending approvals, memory, audit log
- Multi-user with role scoping
