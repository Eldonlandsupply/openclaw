"""
Lola Meeting Ops — meeting classifier.

Determines whether a calendar event qualifies for meeting-ops processing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .config import MeetingOpsConfig

logger = logging.getLogger("lola.meeting_ops.classifier")


def _parse_dt(dt_obj: dict) -> Optional[datetime]:
    """Parse Graph dateTimeTimeZone object or plain ISO string."""
    if not dt_obj:
        return None
    raw = dt_obj.get("dateTime", "") if isinstance(dt_obj, dict) else str(dt_obj)
    if not raw:
        return None
    try:
        # Graph returns UTC without Z suffix sometimes
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        if "+" not in raw and "-" not in raw[10:]:
            raw += "+00:00"
        return datetime.fromisoformat(raw).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(raw.replace("Z", ""))
        except Exception:
            logger.warning("Cannot parse datetime: %r", raw)
            return None


def is_qualifying_meeting(event: dict, cfg: MeetingOpsConfig) -> tuple[bool, str]:
    """
    Returns (qualifies, reason_for_exclusion).
    qualifies=True means the event should trigger meeting-ops.
    """
    # Skip cancelled
    if event.get("isCancelled", False):
        return False, "cancelled"

    # Skip all-day events
    if event.get("isAllDay", False):
        return False, "all_day"

    # Skip declined (when showAs == "free" and attendee response == "declined")
    if cfg.skip_declined:
        my_response = _get_my_response(event, cfg.primary_email)
        if my_response == "declined":
            return False, "declined"

    # Must have Teams / online meeting info
    if not _has_teams_meeting(event):
        return False, "no_teams_join_url"

    # Organizer filter
    if cfg.organizer_only:
        organizer_email = event.get("organizer", {}).get("emailAddress", {}).get("address", "").lower()
        if organizer_email != cfg.primary_email.lower():
            return False, "not_organizer"

    # Category filter
    categories = event.get("categories", [])
    if cfg.blocked_categories and any(c in cfg.blocked_categories for c in categories):
        return False, f"blocked_category:{categories}"
    if cfg.allowed_categories and not any(c in cfg.allowed_categories for c in categories):
        return False, f"not_in_allowed_categories:{categories}"

    # Must be in the future (or ongoing)
    end = _parse_dt(event.get("end", {}))
    if end and end < datetime.now(timezone.utc):
        return False, "already_ended"

    return True, ""


def _has_teams_meeting(event: dict) -> bool:
    """Return True if event has a Teams join URL or online meeting info."""
    if event.get("isOnlineMeeting", False):
        return True
    if event.get("onlineMeetingUrl"):
        return True
    if event.get("onlineMeeting", {}).get("joinUrl"):
        return True
    # Check body for teams join links as fallback
    body = event.get("bodyPreview", "").lower()
    return "teams.microsoft.com" in body or "meet.google" in body


def _get_my_response(event: dict, my_email: str) -> str:
    """Return Matthew's response status: accepted / declined / tentativelyAccepted / none."""
    me = my_email.lower()
    for a in event.get("attendees", []):
        addr = a.get("emailAddress", {}).get("address", "").lower()
        if addr == me:
            return a.get("status", {}).get("response", "none").lower()
    return "none"


def extract_join_url(event: dict) -> Optional[str]:
    """Extract the Teams join URL from an event."""
    if event.get("onlineMeeting", {}).get("joinUrl"):
        return event["onlineMeeting"]["joinUrl"]
    if event.get("onlineMeetingUrl"):
        return event["onlineMeetingUrl"]
    return None


def parse_event_times(event: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    """Return (start, end) as UTC datetimes."""
    return _parse_dt(event.get("start", {})), _parse_dt(event.get("end", {}))
