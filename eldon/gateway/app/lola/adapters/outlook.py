"""
Lola Outlook adapter — read-only calendar and inbox via Microsoft Graph.
Uses the existing tenant/client credentials from .env.
All writes are blocked; calendar mutations and email sends require separate approval.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

_TENANT_ID = os.getenv("OUTLOOK_TENANT_ID", os.getenv("MS_TENANT_ID", ""))
_CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID", os.getenv("MS_CLIENT_ID", ""))
_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET", os.getenv("MS_CLIENT_SECRET", ""))
_USER = os.getenv("OUTLOOK_USER", os.getenv("MS_USER", ""))
_GRAPH = "https://graph.microsoft.com/v1.0"

_token_cache: dict = {"token": None, "expiry": 0.0}


async def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expiry"] - 60:
        return _token_cache["token"]
    if not all([_TENANT_ID, _CLIENT_ID, _CLIENT_SECRET]):
        raise RuntimeError("Outlook credentials not configured. Set OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET.")
    url = f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, data={
            "grant_type": "client_credentials",
            "client_id": _CLIENT_ID,
            "client_secret": _CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
        }) as resp:
            data = await resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Token error: {data.get('error_description', data)}")
    _token_cache["token"] = data["access_token"]
    _token_cache["expiry"] = time.time() + data.get("expires_in", 3600)
    return _token_cache["token"]


async def get_calendar_today() -> list[dict]:
    """Return today's calendar events for the configured user."""
    if not _USER:
        return [{"error": "OUTLOOK_USER not configured"}]
    token = await _get_token()
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    url = f"{_GRAPH}/users/{_USER}/calendarView"
    params = {
        "startDateTime": start,
        "endDateTime": end,
        "$select": "subject,start,end,location,organizer,isAllDay,bodyPreview",
        "$orderby": "start/dateTime",
        "$top": "20",
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, params=params,
                             timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
        events = []
        for e in data.get("value", []):
            events.append({
                "subject": e.get("subject", ""),
                "start": e.get("start", {}).get("dateTime", ""),
                "end": e.get("end", {}).get("dateTime", ""),
                "location": e.get("location", {}).get("displayName", ""),
                "organizer": e.get("organizer", {}).get("emailAddress", {}).get("name", ""),
                "is_all_day": e.get("isAllDay", False),
                "body_preview": e.get("bodyPreview", "")[:200],
            })
        return events
    except Exception as e:
        return [{"error": str(e)}]


async def get_inbox_unread(limit: int = 10) -> list[dict]:
    """Return unread inbox messages."""
    if not _USER:
        return [{"error": "OUTLOOK_USER not configured"}]
    token = await _get_token()
    url = f"{_GRAPH}/users/{_USER}/mailFolders/Inbox/messages"
    params = {
        "$filter": "isRead eq false",
        "$select": "subject,from,receivedDateTime,bodyPreview,importance,hasAttachments",
        "$orderby": "receivedDateTime desc",
        "$top": str(limit),
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, params=params,
                             timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
        messages = []
        for m in data.get("value", []):
            messages.append({
                "subject": m.get("subject", ""),
                "from": m.get("from", {}).get("emailAddress", {}).get("address", ""),
                "from_name": m.get("from", {}).get("emailAddress", {}).get("name", ""),
                "received": m.get("receivedDateTime", ""),
                "preview": m.get("bodyPreview", "")[:300],
                "importance": m.get("importance", "normal"),
                "has_attachments": m.get("hasAttachments", False),
            })
        return messages
    except Exception as e:
        return [{"error": str(e)}]


def format_calendar_for_lola(events: list[dict]) -> str:
    if not events:
        return "No events on your calendar today."
    if events and "error" in events[0]:
        return f"Calendar unavailable: {events[0]['error']}"
    lines = [f"*Today — {len(events)} event(s):*"]
    for e in events:
        start = e["start"][:16].replace("T", " ") if e["start"] else "all day"
        loc = f" @ {e['location']}" if e["location"] else ""
        lines.append(f"• {start} — {e['subject']}{loc}")
    return "\n".join(lines)


def format_inbox_for_lola(messages: list[dict]) -> str:
    if not messages:
        return "Inbox is clear — no unread messages."
    if messages and "error" in messages[0]:
        return f"Inbox unavailable: {messages[0]['error']}"
    lines = [f"*Inbox — {len(messages)} unread:*"]
    for m in messages:
        imp = " [!]" if m["importance"] == "high" else ""
        lines.append(f"• {m['from_name'] or m['from']}{imp}: {m['subject']}")
        if m["preview"]:
            lines.append(f"  {m['preview'][:120]}")
    return "\n".join(lines)
