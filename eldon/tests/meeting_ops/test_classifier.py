"""Tests: attendee_resolver + classifier."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from lola.meeting_ops.attendee_resolver import (
    attendee_hash,
    internal_recipient_emails,
    resolve_attendees,
)
from lola.meeting_ops.classifier import (
    _has_teams_meeting,
    is_qualifying_meeting,
    extract_join_url,
    parse_event_times,
)
from lola.meeting_ops.config import MeetingOpsConfig


def _cfg(**kwargs) -> MeetingOpsConfig:
    defaults = dict(
        enabled=True,
        tenant_id="t",
        client_id="c",
        client_secret="s",
        primary_email="matthew@eldonlandsupply.com",
        internal_domains=["eldonlandsupply.com"],
        skip_declined=True,
        organizer_only=False,
        allowed_categories=[],
        blocked_categories=[],
    )
    defaults.update(kwargs)
    return MeetingOpsConfig(**defaults)


def _future_event(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    start = now + timedelta(hours=2)
    end = start + timedelta(hours=1)
    ev = {
        "id": "evt_001",
        "subject": "Q2 Review",
        "isCancelled": False,
        "isAllDay": False,
        "isOnlineMeeting": True,
        "onlineMeetingUrl": "https://teams.microsoft.com/l/meetup-join/abc",
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        "organizer": {"emailAddress": {"address": "matthew@eldonlandsupply.com", "name": "Matthew"}},
        "attendees": [
            {"emailAddress": {"address": "matthew@eldonlandsupply.com", "name": "Matthew"},
             "status": {"response": "accepted"}},
            {"emailAddress": {"address": "vendor@acme.com", "name": "Bob Vendor"},
             "status": {"response": "accepted"}},
        ],
        "categories": [],
        "bodyPreview": "Quarterly review meeting",
        "showAs": "busy",
    }
    ev.update(overrides)
    return ev


# ── Classifier tests ───────────────────────────────────────────────────────

def test_qualifying_teams_meeting():
    cfg = _cfg()
    ev = _future_event()
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert qualifies, reason


def test_cancelled_event_excluded():
    cfg = _cfg()
    ev = _future_event(isCancelled=True)
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert not qualifies
    assert reason == "cancelled"


def test_all_day_excluded():
    cfg = _cfg()
    ev = _future_event(isAllDay=True)
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert not qualifies
    assert reason == "all_day"


def test_no_teams_url_excluded():
    cfg = _cfg()
    ev = _future_event(isOnlineMeeting=False, onlineMeetingUrl=None,
                       onlineMeeting=None, bodyPreview="plain meeting")
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert not qualifies
    assert reason == "no_teams_join_url"


def test_declined_excluded_when_skip_declined():
    cfg = _cfg(skip_declined=True)
    ev = _future_event()
    # Modify Matthew's response to declined
    ev["attendees"][0]["status"]["response"] = "declined"
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert not qualifies
    assert reason == "declined"


def test_declined_included_when_skip_declined_false():
    cfg = _cfg(skip_declined=False)
    ev = _future_event()
    ev["attendees"][0]["status"]["response"] = "declined"
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert qualifies


def test_blocked_category_excluded():
    cfg = _cfg(blocked_categories=["Personal"])
    ev = _future_event(categories=["Personal"])
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert not qualifies


def test_organizer_only_mode():
    cfg = _cfg(organizer_only=True)
    ev = _future_event()
    ev["organizer"]["emailAddress"]["address"] = "someone_else@eldonlandsupply.com"
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert not qualifies
    assert reason == "not_organizer"


def test_past_meeting_excluded():
    cfg = _cfg()
    now = datetime.now(timezone.utc)
    ev = _future_event()
    ev["end"] = {"dateTime": (now - timedelta(hours=1)).isoformat(), "timeZone": "UTC"}
    qualifies, reason = is_qualifying_meeting(ev, cfg)
    assert not qualifies
    assert reason == "already_ended"


def test_extract_join_url():
    ev = _future_event()
    url = extract_join_url(ev)
    assert "teams.microsoft.com" in url


def test_parse_event_times():
    ev = _future_event()
    start, end = parse_event_times(ev)
    assert start is not None
    assert end is not None
    assert end > start


# ── Attendee resolver tests ────────────────────────────────────────────────

def test_internal_attendee_classification():
    cfg = _cfg()
    ev = _future_event()
    internal, external = resolve_attendees(ev, cfg)
    internal_emails = {p.email for p in internal}
    external_emails = {p.email for p in external}
    assert "matthew@eldonlandsupply.com" in internal_emails
    assert "vendor@acme.com" in external_emails


def test_multiple_internal_domains():
    cfg = _cfg(internal_domains=["eldonlandsupply.com", "eldonpartner.com"])
    ev = _future_event()
    ev["attendees"].append({
        "emailAddress": {"address": "alice@eldonpartner.com", "name": "Alice"},
        "status": {"response": "accepted"},
    })
    internal, external = resolve_attendees(ev, cfg)
    assert any(p.email == "alice@eldonpartner.com" for p in internal)


def test_missing_email_marked_uncertain():
    cfg = _cfg()
    ev = _future_event()
    ev["attendees"].append({
        "emailAddress": {"address": "", "name": "Mystery Guest"},
        "status": {"response": "none"},
    })
    internal, external = resolve_attendees(ev, cfg)
    uncertain = [p for p in external if p.uncertain]
    assert len(uncertain) == 1
    assert uncertain[0].name == "Mystery Guest"


def test_attendee_hash_stable():
    cfg = _cfg()
    ev = _future_event()
    internal, external = resolve_attendees(ev, cfg)
    h1 = attendee_hash(internal + external)
    h2 = attendee_hash(internal + external)
    assert h1 == h2


def test_attendee_hash_changes_on_add():
    cfg = _cfg()
    ev = _future_event()
    internal, external = resolve_attendees(ev, cfg)
    h1 = attendee_hash(internal + external)
    ev["attendees"].append({
        "emailAddress": {"address": "new@acme.com", "name": "New Person"},
        "status": {"response": "accepted"},
    })
    internal2, external2 = resolve_attendees(ev, cfg)
    h2 = attendee_hash(internal2 + external2)
    assert h1 != h2


def test_internal_recipients_excludes_external():
    cfg = _cfg(send_dossier_to_internal_attendees=True)
    ev = _future_event()
    internal, external = resolve_attendees(ev, cfg)
    recipients = internal_recipient_emails(internal, cfg.primary_email, True)
    for ep in external:
        assert ep.email not in recipients


def test_internal_recipients_always_includes_primary():
    cfg = _cfg(send_dossier_to_internal_attendees=False)
    ev = _future_event()
    internal, external = resolve_attendees(ev, cfg)
    recipients = internal_recipient_emails(internal, cfg.primary_email, False)
    assert cfg.primary_email.lower() in [r.lower() for r in recipients]
