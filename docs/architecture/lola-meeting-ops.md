# Lola Meeting Ops

Pre-meeting dossiers and post-meeting notes for every Teams meeting on Matthew's calendar.

---

## What This Does

**Pre-meeting (T-20 minutes):**

- Polls Matthew's Outlook calendar for upcoming Teams meetings
- Classifies attendees as internal (Eldon) or external
- Enriches external attendees from Attio CRM and prior email threads
- Sends a dossier email to Matthew (and internal attendees if configured)

**Post-meeting:**

- Waits for the meeting to end
- Fetches transcript (retries for up to 60 minutes — transcript publication is delayed)
- Fetches recap if available
- Synthesises structured notes via the configured LLM
- Pushes notes into Attio as a note on each external attendee's record
- Creates a follow-up email draft in Matthew's Drafts folder (never auto-sends)

---

## Required Secrets

Add to `/opt/openclaw/.env`:

```env
# Enable the feature
LOLA_MEETINGS_ENABLED=true

# Microsoft Graph credentials (same app registration as existing Outlook connector)
OUTLOOK_TENANT_ID=5afeb96a-473a-4650-81f7-4c61f3bf3461
OUTLOOK_CLIENT_ID=a1c063c0-eefb-465d-90c2-d3eca184d33f
OUTLOOK_CLIENT_SECRET=<your_client_secret>

# Primary calendar/mailbox
LOLA_MEETINGS_PRIMARY_EMAIL=tynski@eldonlandsupply.com

# Attio (already set if CRM integration active)
ATTIO_API_KEY=<your_attio_key>
```

---

## Required Microsoft App Registration Permissions

**Application permissions** (not delegated — this runs as a background service):

| Permission                       | Required    | Purpose                                   |
| -------------------------------- | ----------- | ----------------------------------------- |
| `Calendars.Read`                 | ✅ Required | Read Matthew's calendar                   |
| `Mail.ReadWrite`                 | ✅ Required | Create draft emails in Drafts folder      |
| `Mail.Send`                      | ✅ Required | Send dossier emails                       |
| `Mail.Read`                      | ✅ Required | Search prior email threads for context    |
| `OnlineMeetings.Read`            | ✅ Required | Fetch Teams meeting metadata              |
| `OnlineMeetingArtifact.Read.All` | ✅ Required | Fetch transcripts (Teams Premium feature) |
| `User.Read.All`                  | Optional    | Resolve attendee display names            |

> **Note:** `OnlineMeetingArtifact.Read.All` requires Teams Premium on the tenant.
> If not available, transcript collection falls back to partial — notes are still
> produced from recap/attendee list with lower confidence.

### Grant Admin Consent

After adding these permissions in the Azure portal:

1. Go to **API permissions** → click **Grant admin consent for [tenant]**
2. All permissions must show ✅ **Granted**

---

## Config Reference

All settings are env vars. Defaults shown.

```env
LOLA_MEETINGS_ENABLED=false                    # Master on/off switch
LOLA_MEETINGS_PRIMARY_EMAIL=                   # Matthew's mailbox UPN
LOLA_MEETINGS_INTERNAL_DOMAINS=eldonlandsupply.com  # Comma-separated list
LOLA_MEETINGS_DOSSIER_LEAD_MINUTES=20          # Send dossier this many minutes before start
LOLA_MEETINGS_RETRY_INTERVAL_MINUTES=5         # Retry interval for transcript collection
LOLA_MEETINGS_MAX_RETRY_MINUTES=60             # Stop retrying after this many minutes
LOLA_MEETINGS_POLL_INTERVAL_MINUTES=5          # Calendar polling interval
LOLA_MEETINGS_ORGANIZER_ONLY=false             # Only process meetings Matthew organises
LOLA_MEETINGS_INCLUDE_CHAT=false               # Include Teams chat excerpt (requires extra scope)
LOLA_MEETINGS_INCLUDE_FILES=false              # Include shared files list
LOLA_MEETINGS_DOSSIER_INTERNAL=true            # Send dossier to other internal attendees too
LOLA_MEETINGS_FOLLOWUP_MODE=draft_only         # Only mode currently supported
LOLA_MEETINGS_SKIP_DECLINED=true               # Skip meetings Matthew has declined
LOLA_MEETINGS_ALLOWED_CATEGORIES=             # If set, only process these calendar categories
LOLA_MEETINGS_BLOCKED_CATEGORIES=             # Skip meetings with these categories (e.g. Personal)
```

---

## How Scheduling Works

The scheduler is an asyncio background task that starts alongside the LOLA gateway.

1. Every `LOLA_MEETINGS_POLL_INTERVAL_MINUTES` minutes, it fetches the next 48 hours of calendar events
2. Qualifying meetings are stored in `lola.db` with state `detected`
3. Each meeting gets an asyncio task that sleeps until T-20 min, then builds and sends the dossier
4. After the dossier is sent, a second task waits for the meeting end time + 30 seconds, then starts artifact collection
5. Artifact collection retries on `LOLA_MEETINGS_RETRY_INTERVAL_MINUTES` until transcript is available or `LOLA_MEETINGS_MAX_RETRY_MINUTES` expires

**On Pi restart:** the scheduler reads `lola.db` on startup and re-schedules any in-progress meetings. No data is lost.

---

## Transcript Delay Handling

Teams transcripts are typically available 5–30 minutes after a meeting ends, depending on meeting length and tenant processing load.

The system:

- Marks state as `transcript_pending` while waiting
- Polls every 5 minutes (configurable)
- Falls back gracefully if transcript never arrives — notes are still generated from recap/attendee list with `source_confidence: low`
- Follow-up draft is always created even without transcript, with a review flag indicating lower confidence

---

## How to Inspect State

```bash
# Live state of all meetings
sqlite3 /opt/openclaw/.lola/lola.db \
  "SELECT meeting_id, subject, state, start_time FROM meeting_lifecycle ORDER BY start_time DESC LIMIT 20"

# Meetings currently in retry
sqlite3 /opt/openclaw/.lola/lola.db \
  "SELECT meeting_id, subject, state, retry_count, last_error FROM meeting_lifecycle WHERE state='retrying' OR state='transcript_pending'"

# Check scheduler logs
sudo journalctl -u openclaw -n 100 --no-pager | grep meeting_ops
```

---

## Disable or Narrow the Workflow

**Disable entirely:**

```env
LOLA_MEETINGS_ENABLED=false
```

**Only process meetings Matthew organises:**

```env
LOLA_MEETINGS_ORGANIZER_ONLY=true
```

**Block personal calendar items:**

```env
LOLA_MEETINGS_BLOCKED_CATEGORIES=Personal,Private
```

**Don't send dossier to other Eldon attendees (Matthew only):**

```env
LOLA_MEETINGS_DOSSIER_INTERNAL=false
```

---

## Attio Setup

1. Ensure `ATTIO_API_KEY` is set in `.env`
2. The integration reuses the existing Attio client at `eldon/src/openclaw/integrations/attio/`
3. Meeting notes are created as Attio "Notes" attached to each external attendee's person record
4. If no Attio person record is found for an attendee email, that attendee is skipped (not an error)
5. Notes are append-only — existing CRM data is never overwritten

---

## Known Limitations

- **Teams Premium required** for transcript access. Without it, transcript collection silently returns `None` and falls back to recap/notes only.
- **Channel meetings** (Teams channel-based meetings) require `ChannelMessage.Read.All` for chat export — currently not implemented.
- **Enrichment is evidence-only.** No external APIs (LinkedIn, Clearbit) are called. Dossier quality depends on what's in Attio and the prior email thread history.
- **Follow-up drafts** are always saved to Drafts, never auto-sent. Matthew must review and send manually.
- **Recurring meetings** are treated as individual instances — one lifecycle record per occurrence.

---

## Privacy / Security Notes

- Dossiers are never sent to external attendees.
- Follow-up drafts are never auto-sent.
- Transcript content is never dumped raw into Attio — only structured synthesis output is stored.
- All Graph calls use application credentials (client credentials flow). The service account must have appropriate Exchange/Teams admin delegation.
- Secrets are read from `.env` only — never logged or committed.
