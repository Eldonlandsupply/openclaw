"""
Lola Meeting Ops — Microsoft Graph client.

Thin async wrapper on top of the existing aiohttp pattern
from eldon/gateway/app/lola/adapters/outlook.py.

Adds:
  - calendar event fetching with full attendee detail
  - online meeting metadata + Teams join info
  - transcript / recap / notes fetching (with partial-failure tolerance)
  - mail draft creation (save-to-drafts only)
  - mail send for dossier emails

Never auto-sends follow-up emails. Draft creation only.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp

from .config import MeetingOpsConfig

logger = logging.getLogger("lola.meeting_ops.graph_client")

_GRAPH = "https://graph.microsoft.com/v1.0"
_TOKEN_CACHE: dict = {"token": None, "expiry": 0.0}


class GraphError(Exception):
    """Raised when Graph returns a non-2xx that is not retryable."""
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"Graph {status}: {message}")


class GraphThrottle(Exception):
    """Raised on 429 — caller should back off."""
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Graph throttled, retry after {retry_after}s")


async def get_token(cfg: MeetingOpsConfig) -> str:
    if _TOKEN_CACHE["token"] and time.time() < _TOKEN_CACHE["expiry"] - 60:
        return _TOKEN_CACHE["token"]
    url = f"https://login.microsoftonline.com/{cfg.tenant_id}/oauth2/v2.0/token"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, data={
            "grant_type": "client_credentials",
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Token error: {data.get('error_description', data)}")
    _TOKEN_CACHE["token"] = data["access_token"]
    _TOKEN_CACHE["expiry"] = time.time() + data.get("expires_in", 3600)
    logger.debug("Refreshed Graph token, expires in %ds", data.get("expires_in", 3600))
    return _TOKEN_CACHE["token"]


async def _get(cfg: MeetingOpsConfig, path: str, params: Optional[dict] = None) -> dict:
    token = await get_token(cfg)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{_GRAPH}{path}" if path.startswith("/") else path
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers, params=params,
                         timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 429:
                ra = int(resp.headers.get("Retry-After", "60"))
                raise GraphThrottle(ra)
            if resp.status == 404:
                return {}
            if resp.status >= 400:
                body = await resp.text()
                raise GraphError(resp.status, body[:300])
            return await resp.json()


async def _post(cfg: MeetingOpsConfig, path: str, payload: dict) -> dict:
    token = await get_token(cfg)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url = f"{_GRAPH}{path}"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, headers=headers, json=payload,
                          timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 429:
                ra = int(resp.headers.get("Retry-After", "60"))
                raise GraphThrottle(ra)
            if resp.status >= 400:
                body = await resp.text()
                raise GraphError(resp.status, body[:300])
            return await resp.json()


# ── Calendar ──────────────────────────────────────────────────────────────


async def list_calendar_events(cfg: MeetingOpsConfig, hours_ahead: int = 48) -> list[dict]:
    """Return events in the next `hours_ahead` hours for the primary user."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours_ahead)
    params = {
        "startDateTime": now.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": (
            "id,subject,start,end,organizer,attendees,isAllDay,isCancelled,"
            "isOnlineMeeting,onlineMeetingUrl,onlineMeeting,bodyPreview,"
            "sensitivity,showAs,categories,onlineMeetingProvider"
        ),
        "$orderby": "start/dateTime",
        "$top": "50",
    }
    data = await _get(cfg, f"/users/{cfg.primary_email}/calendarView", params)
    return data.get("value", [])


async def get_calendar_event(cfg: MeetingOpsConfig, event_id: str) -> dict:
    """Fetch a single calendar event by ID."""
    data = await _get(
        cfg,
        f"/users/{cfg.primary_email}/events/{event_id}",
        params={
            "$select": (
                "id,subject,start,end,organizer,attendees,isAllDay,isCancelled,"
                "isOnlineMeeting,onlineMeetingUrl,onlineMeeting,bodyPreview,"
                "sensitivity,showAs,categories,onlineMeetingProvider"
            )
        },
    )
    return data


async def get_online_meeting(cfg: MeetingOpsConfig, join_web_url: str) -> dict:
    """
    Fetch the OnlineMeeting resource by JoinWebUrl.
    Returns empty dict if not found or permission denied.
    """
    try:
        data = await _get(
            cfg,
            f"/users/{cfg.primary_email}/onlineMeetings",
            params={"$filter": f"JoinWebUrl eq '{join_web_url}'"},
        )
        meetings = data.get("value", [])
        return meetings[0] if meetings else {}
    except GraphError as e:
        logger.warning("get_online_meeting failed (status=%d): %s", e.status, e)
        return {}


# ── Transcripts / artifacts ───────────────────────────────────────────────


async def get_meeting_transcript(cfg: MeetingOpsConfig, meeting_id: str) -> Optional[str]:
    """
    Attempt to fetch transcript for a Teams meeting.
    Returns None if unavailable (not ready, no permission, or no transcript).
    """
    try:
        # List transcripts
        data = await _get(cfg, f"/users/{cfg.primary_email}/onlineMeetings/{meeting_id}/transcripts")
        transcripts = data.get("value", [])
        if not transcripts:
            return None
        # Fetch the most recent transcript content (plain text)
        transcript_id = transcripts[0]["id"]
        content_data = await _get(
            cfg,
            f"/users/{cfg.primary_email}/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content",
            params={"$format": "text/vtt"},
        )
        # content_data may be raw text via a redirect; handle both
        if isinstance(content_data, str):
            return content_data[:20000]  # cap at 20k chars
        return str(content_data)[:20000]
    except GraphError as e:
        if e.status == 403:
            logger.info("Transcript permission denied for meeting %s (need OnlineMeetingArtifact.Read.All)", meeting_id)
        elif e.status == 404:
            logger.debug("No transcript yet for meeting %s", meeting_id)
        else:
            logger.warning("Transcript fetch error meeting=%s: %s", meeting_id, e)
        return None
    except Exception as e:
        logger.warning("Transcript fetch unexpected error meeting=%s: %s", meeting_id, e)
        return None


async def get_meeting_recordings(cfg: MeetingOpsConfig, meeting_id: str) -> list[dict]:
    """Fetch recording metadata if available."""
    try:
        data = await _get(cfg, f"/users/{cfg.primary_email}/onlineMeetings/{meeting_id}/recordings")
        return data.get("value", [])
    except (GraphError, Exception) as e:
        logger.debug("Recordings fetch error meeting=%s: %s", meeting_id, e)
        return []


# ── Mail ──────────────────────────────────────────────────────────────────


async def send_mail(cfg: MeetingOpsConfig, to_emails: list[str],
                    subject: str, body_html: str) -> bool:
    """
    Send an email from the primary mailbox.
    Used for dossier delivery only — not for follow-up drafts.
    """
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [
                {"emailAddress": {"address": e}} for e in to_emails
            ],
        },
        "saveToSentItems": True,
    }
    try:
        await _post(cfg, f"/users/{cfg.primary_email}/sendMail", payload)
        logger.info("Sent dossier email to %s subject=%r", to_emails, subject[:60])
        return True
    except GraphError as e:
        logger.error("send_mail failed status=%d: %s", e.status, e)
        return False


async def create_mail_draft(cfg: MeetingOpsConfig, to_emails: list[str],
                             cc_emails: list[str], subject: str,
                             body_html: str) -> Optional[str]:
    """
    Save a draft email to the Drafts folder.
    Returns the draft message ID, or None on failure.
    Never sends.
    """
    payload = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [{"emailAddress": {"address": e}} for e in to_emails],
        "ccRecipients": [{"emailAddress": {"address": e}} for e in cc_emails],
    }
    try:
        resp = await _post(cfg, f"/users/{cfg.primary_email}/messages", payload)
        draft_id = resp.get("id", "")
        logger.info("Created draft %s subject=%r", draft_id[:16], subject[:60])
        return draft_id
    except GraphError as e:
        logger.error("create_mail_draft failed status=%d: %s", e.status, e)
        return None
