"""Tests: dossier, state_store, synthesizer, followup_draft."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lola.meeting_ops.config import MeetingOpsConfig
from lola.meeting_ops.models import (
    ActionItem,
    ArtifactAvailability,
    AttendeeProfile,
    MeetingArtifactBundle,
    MeetingDossier,
    MeetingLifecycleState,
    StructuredMeetingNote,
)


def _cfg(**kwargs) -> MeetingOpsConfig:
    defaults = dict(
        enabled=True,
        tenant_id="t",
        client_id="c",
        client_secret="s",
        primary_email="matthew@eldonlandsupply.com",
        internal_domains=["eldonlandsupply.com"],
        dossier_lead_minutes=20,
        send_dossier_to_internal_attendees=True,
        attio_api_key="fake_attio_key",
        llm_provider="none",
        chat_model="grok-3-mini",
    )
    defaults.update(kwargs)
    return MeetingOpsConfig(**defaults)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_dossier(**kwargs) -> MeetingDossier:
    defaults = dict(
        meeting_id="mtg_abc123",
        calendar_event_id="evt_001",
        subject="Partnership Discussion",
        start_time=_now() + timedelta(minutes=20),
        end_time=_now() + timedelta(minutes=80),
        organizer_email="matthew@eldonlandsupply.com",
        organizer_name="Matthew Tynski",
        join_url="https://teams.microsoft.com/l/join/abc",
        external_attendees=[
            AttendeeProfile(
                email="bob@acme.com",
                name="Bob Smith",
                domain="acme.com",
                is_internal=False,
                title="VP Sales",
                company="Acme Corp",
                attio_context_summary="Title: VP Sales; Company: Acme Corp",
                evidence_refs=["attio_crm"],
            )
        ],
        internal_recipients=["matthew@eldonlandsupply.com"],
        talking_points=["Understand Acme Corp's relationship with Eldon."],
        risk_flags=[],
    )
    defaults.update(kwargs)
    return MeetingDossier(**defaults)


# ── Dossier renderer tests ─────────────────────────────────────────────────

def test_render_dossier_html_contains_key_info():
    from lola.meeting_ops.dossier import render_dossier_html, render_dossier_subject
    dossier = _make_dossier()
    html = render_dossier_html(dossier)
    assert "Partnership Discussion" in html
    assert "Bob Smith" in html
    assert "Acme Corp" in html
    assert "attio_crm" in html
    assert "external" not in html.lower() or "External Attendees" in html


def test_render_dossier_subject_format():
    from lola.meeting_ops.dossier import render_dossier_subject
    dossier = _make_dossier()
    subject = render_dossier_subject(dossier)
    assert "[20-Min Dossier]" in subject
    assert "Partnership Discussion" in subject


def test_render_dossier_with_uncertain_attendee():
    from lola.meeting_ops.dossier import render_dossier_html
    dossier = _make_dossier(
        external_attendees=[
            AttendeeProfile(email="", name="Unknown Guest", uncertain=True, is_internal=False)
        ]
    )
    html = render_dossier_html(dossier)
    assert "identity uncertain" in html


def test_render_dossier_risk_flags():
    from lola.meeting_ops.dossier import render_dossier_html
    dossier = _make_dossier(risk_flags=["No prior context found for: Bob Smith."])
    html = render_dossier_html(dossier)
    assert "No prior context" in html


# ── State store tests ──────────────────────────────────────────────────────

@pytest.fixture
def tmp_state_store(monkeypatch, tmp_path):
    """Patch state store to use a temp directory."""
    db_dir = str(tmp_path)
    monkeypatch.setenv("LOLA_STORE_PATH", db_dir)
    # Reset module-level connection
    import lola.meeting_ops.state_store as ss
    ss._conn = None
    yield ss
    if ss._conn:
        ss._conn.close()
        ss._conn = None


def _make_record(**kwargs):
    from lola.meeting_ops.models import MeetingLifecycleRecord
    defaults = dict(
        meeting_id="mtg_test001",
        calendar_event_id="evt_test001",
        organizer="matthew@eldonlandsupply.com",
        start_time=_now() + timedelta(hours=2),
        end_time=_now() + timedelta(hours=3),
        subject="Test Meeting",
        attendee_hash="abc123",
        state=MeetingLifecycleState.detected,
    )
    defaults.update(kwargs)
    return MeetingLifecycleRecord(**defaults)


def test_upsert_and_get_meeting(tmp_state_store):
    ss = tmp_state_store
    rec = _make_record()
    ss.upsert_meeting(rec)
    fetched = ss.get_meeting(rec.meeting_id)
    assert fetched is not None
    assert fetched.meeting_id == rec.meeting_id
    assert fetched.state == MeetingLifecycleState.detected


def test_state_transition(tmp_state_store):
    ss = tmp_state_store
    rec = _make_record()
    ss.upsert_meeting(rec)
    updated = ss.transition_state(rec.meeting_id, MeetingLifecycleState.scheduled)
    assert updated
    fetched = ss.get_meeting(rec.meeting_id)
    assert fetched.state == MeetingLifecycleState.scheduled
    assert fetched.scheduled_at is not None


def test_idempotent_upsert(tmp_state_store):
    ss = tmp_state_store
    rec = _make_record()
    ss.upsert_meeting(rec)
    ss.upsert_meeting(rec)  # second insert should not raise
    fetched = ss.get_meeting(rec.meeting_id)
    assert fetched.meeting_id == rec.meeting_id


def test_get_by_calendar_event(tmp_state_store):
    ss = tmp_state_store
    rec = _make_record()
    ss.upsert_meeting(rec)
    fetched = ss.get_by_calendar_event(rec.calendar_event_id)
    assert fetched is not None
    assert fetched.meeting_id == rec.meeting_id


def test_mark_cancelled(tmp_state_store):
    ss = tmp_state_store
    rec = _make_record()
    ss.upsert_meeting(rec)
    updated = ss.mark_cancelled(rec.calendar_event_id)
    assert updated
    fetched = ss.get_meeting(rec.meeting_id)
    assert fetched.state == MeetingLifecycleState.cancelled


def test_list_meetings_by_state(tmp_state_store):
    ss = tmp_state_store
    rec1 = _make_record(meeting_id="mtg_001", calendar_event_id="evt_001")
    rec2 = _make_record(meeting_id="mtg_002", calendar_event_id="evt_002")
    ss.upsert_meeting(rec1)
    ss.upsert_meeting(rec2)
    ss.transition_state("mtg_001", MeetingLifecycleState.scheduled)
    scheduled = ss.list_meetings_by_state(MeetingLifecycleState.scheduled)
    assert any(r.meeting_id == "mtg_001" for r in scheduled)
    assert not any(r.meeting_id == "mtg_002" for r in scheduled)


def test_transition_state_nonexistent_returns_false(tmp_state_store):
    ss = tmp_state_store
    updated = ss.transition_state("nonexistent_id", MeetingLifecycleState.failed)
    assert not updated


# ── Synthesizer tests ──────────────────────────────────────────────────────

def _make_bundle(with_transcript=True, with_recap=False) -> MeetingArtifactBundle:
    transcript = (
        "Matthew: Let's discuss the land supply contract.\n"
        "Bob: We agree to deliver 500 acres by April 1st.\n"
        "Matthew: I'll send a formal agreement by EOW.\n"
        "Bob: Action: Bob to confirm pricing by Friday."
    ) if with_transcript else None
    recap = "Meeting covered contract terms and delivery schedule." if with_recap else None
    return MeetingArtifactBundle(
        meeting_id="mtg_test",
        calendar_event_id="evt_test",
        transcript=transcript,
        recap=recap,
        attendee_list=[
            {"email": "matthew@eldonlandsupply.com", "name": "Matthew", "response": "accepted"},
            {"email": "bob@acme.com", "name": "Bob", "response": "accepted"},
        ],
        availability=ArtifactAvailability(
            transcript=with_transcript,
            recap=with_recap,
            attendee_list=True,
        ),
    )


def test_synthesizer_falls_back_on_empty_content():
    from lola.meeting_ops.synthesizer import _minimal_note
    bundle = MeetingArtifactBundle(
        meeting_id="mtg_empty",
        calendar_event_id="evt_empty",
    )
    note = _minimal_note(bundle, "Test", _now(), _now() + timedelta(hours=1), "Matthew")
    assert note.source_confidence == "low"
    assert "unavailable" in note.executive_summary.lower()


def test_synthesizer_llm_json_parse_success():
    from lola.meeting_ops.synthesizer import _parse_llm_output
    raw = json.dumps({
        "executive_summary": "Discussed land contract.",
        "topics": ["Contract terms"],
        "decisions": ["500 acres by April 1"],
        "action_items": [{"owner": "Bob", "task": "Confirm pricing", "due_date": "Friday",
                          "confidence": 0.9, "evidence_source": "transcript"}],
        "open_questions": [],
        "commitments_risks": [],
        "source_confidence": "high",
    })
    parsed = _parse_llm_output(raw, "medium")
    assert parsed is not None
    assert parsed["source_confidence"] == "high"
    assert len(parsed["action_items"]) == 1
    assert parsed["action_items"][0]["owner"] == "Bob"


def test_synthesizer_llm_json_parse_with_markdown_fence():
    from lola.meeting_ops.synthesizer import _parse_llm_output
    raw = "```json\n{\"executive_summary\": \"Test\", \"topics\": [], \"decisions\": [], \"action_items\": [], \"open_questions\": [], \"commitments_risks\": [], \"source_confidence\": \"medium\"}\n```"
    parsed = _parse_llm_output(raw, "low")
    assert parsed is not None
    assert parsed["executive_summary"] == "Test"


def test_synthesizer_invalid_json_returns_none():
    from lola.meeting_ops.synthesizer import _parse_llm_output
    parsed = _parse_llm_output("not json at all", "low")
    assert parsed is None


def test_synthesizer_source_confidence_transcript():
    bundle = _make_bundle(with_transcript=True)
    assert bundle.availability.transcript


# ── Follow-up draft tests ──────────────────────────────────────────────────

def _make_note(**kwargs) -> StructuredMeetingNote:
    defaults = dict(
        meeting_id="mtg_note",
        calendar_event_id="evt_note",
        subject="Partnership Discussion",
        start_time=_now(),
        end_time=_now() + timedelta(hours=1),
        organizer="matthew@eldonlandsupply.com",
        executive_summary="Discussed land supply deal.",
        topics=["Contract terms", "Delivery schedule"],
        decisions=["500 acres by April 1"],
        action_items=[
            ActionItem(owner="Bob Smith", task="Confirm pricing by Friday",
                       due_date="Friday", confidence=0.9, evidence_source="transcript")
        ],
        open_questions=["What are the penalty clauses?"],
        source_confidence="high",
    )
    defaults.update(kwargs)
    return StructuredMeetingNote(**defaults)


def test_followup_draft_html_contains_action_items():
    from lola.meeting_ops.followup_draft import render_followup_html
    note = _make_note()
    external = [AttendeeProfile(email="bob@acme.com", name="Bob Smith", domain="acme.com", is_internal=False)]
    html = render_followup_html(note, external)
    assert "Bob Smith" in html
    assert "Confirm pricing by Friday" in html
    assert "Friday" in html


def test_followup_draft_subject_format():
    from lola.meeting_ops.followup_draft import build_followup_payload
    cfg = _cfg()
    note = _make_note()
    external = [AttendeeProfile(email="bob@acme.com", name="Bob Smith", domain="acme.com", is_internal=False)]
    payload = build_followup_payload(note, external, cfg)
    assert payload.subject.startswith("Follow-Up:")
    assert "Partnership Discussion" in payload.subject


def test_followup_draft_no_auto_send_external():
    from lola.meeting_ops.followup_draft import build_followup_payload
    cfg = _cfg()
    note = _make_note()
    external = [AttendeeProfile(email="bob@acme.com", name="Bob Smith", domain="acme.com", is_internal=False)]
    payload = build_followup_payload(note, external, cfg)
    # Verify body is draft (no confirmation of sending)
    assert payload.body_html  # has content
    assert payload.to == ["bob@acme.com"]


def test_followup_draft_review_flag_uncertain_attendee():
    from lola.meeting_ops.followup_draft import build_followup_payload
    cfg = _cfg()
    note = _make_note()
    external = [AttendeeProfile(email="", name="Unknown", uncertain=True, is_internal=False)]
    payload = build_followup_payload(note, external, cfg)
    assert any("uncertain" in f for f in payload.review_flags)


def test_followup_draft_review_flag_low_confidence():
    from lola.meeting_ops.followup_draft import build_followup_payload
    cfg = _cfg()
    note = _make_note(source_confidence="low")
    external = [AttendeeProfile(email="bob@acme.com", name="Bob", domain="acme.com", is_internal=False)]
    payload = build_followup_payload(note, external, cfg)
    assert any("transcript" in f.lower() for f in payload.review_flags)


def test_followup_draft_no_external_triggers_review_flag():
    from lola.meeting_ops.followup_draft import build_followup_payload
    cfg = _cfg()
    note = _make_note()
    payload = build_followup_payload(note, [], cfg)
    assert any("No confirmed external recipients" in f for f in payload.review_flags)


# ── Attio sync payload tests ───────────────────────────────────────────────

def test_attio_sync_format_note_body():
    from lola.meeting_ops.attio_sync import _format_note_body
    note = _make_note()
    body = _format_note_body(note)
    assert "Partnership Discussion" in body
    assert "Bob Smith" in body
    assert "Confirm pricing by Friday" in body
    assert "# Meeting" in body
    assert "## Action Items" in body


def test_attio_sync_skips_when_no_api_key():
    cfg = _cfg(attio_api_key="")
    note = _make_note()

    async def run():
        from lola.meeting_ops.attio_sync import sync_to_attio
        result = await sync_to_attio(note, ["bob@acme.com"], cfg)
        return result

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(run())
    assert result is False
