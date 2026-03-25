"""
Lola Meeting Ops — data models.

All schemas for the meeting lifecycle, attendees, dossiers,
artifacts, structured notes, and follow-up drafts.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Lifecycle states ──────────────────────────────────────────────────────


class MeetingLifecycleState(str, Enum):
    detected = "detected"
    scheduled = "scheduled"
    dossier_building = "dossier_building"
    dossier_sent = "dossier_sent"
    meeting_ended = "meeting_ended"
    artifact_collection_started = "artifact_collection_started"
    transcript_pending = "transcript_pending"
    artifact_partial = "artifact_partial"
    notes_generated = "notes_generated"
    attio_synced = "attio_synced"
    followup_drafted = "followup_drafted"
    retrying = "retrying"
    failed = "failed"
    cancelled = "cancelled"


# ── Attendee ──────────────────────────────────────────────────────────────


class AttendeeProfile(BaseModel):
    email: str
    name: str = ""
    domain: str = ""
    is_internal: bool = False
    confidence: float = 1.0  # 0–1, confidence that classification is correct
    title: Optional[str] = None
    company: Optional[str] = None
    linkedin_url: Optional[str] = None
    prior_meetings_summary: Optional[str] = None
    prior_email_summary: Optional[str] = None
    attio_context_summary: Optional[str] = None
    notes: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    uncertain: bool = False  # True if email missing or domain unclear


# ── Dossier ───────────────────────────────────────────────────────────────


class MeetingDossier(BaseModel):
    meeting_id: str
    calendar_event_id: str
    subject: str
    start_time: datetime
    end_time: datetime
    organizer_email: str
    organizer_name: str
    join_url: Optional[str] = None
    external_attendees: list[AttendeeProfile] = Field(default_factory=list)
    internal_recipients: list[str] = Field(default_factory=list)  # emails
    relationship_summary: Optional[str] = None
    talking_points: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Artifacts ─────────────────────────────────────────────────────────────


class ArtifactAvailability(BaseModel):
    transcript: bool = False
    recap: bool = False
    notes: bool = False
    chat: bool = False
    files: bool = False
    attendee_list: bool = False


class MeetingArtifactBundle(BaseModel):
    meeting_id: str
    calendar_event_id: str
    transcript: Optional[str] = None
    recap: Optional[str] = None
    notes: Optional[str] = None
    chat_excerpt: Optional[str] = None
    shared_files: list[str] = Field(default_factory=list)
    attendee_list: list[dict] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    availability: ArtifactAvailability = Field(default_factory=ArtifactAvailability)
    collected_at: datetime = Field(default_factory=datetime.utcnow)


# ── Structured notes ──────────────────────────────────────────────────────


class ActionItem(BaseModel):
    owner: str
    task: str
    due_date: Optional[str] = None  # free text, e.g. "EOD Friday" or "2026-04-01"
    confidence: float = 1.0
    evidence_source: str = ""  # "transcript", "recap", "notes", "inferred"


class StructuredMeetingNote(BaseModel):
    meeting_id: str
    calendar_event_id: str
    subject: str
    start_time: datetime
    end_time: datetime
    organizer: str
    attendees: list[str] = Field(default_factory=list)
    executive_summary: str = ""
    topics: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    commitments_risks: list[str] = Field(default_factory=list)
    source_confidence: str = "low"  # "high" | "medium" | "low"
    raw_artifact_refs: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Follow-up draft ───────────────────────────────────────────────────────


class FollowUpDraftPayload(BaseModel):
    meeting_id: str
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str = ""
    body_html: str = ""
    body_text: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    review_flags: list[str] = Field(default_factory=list)


# ── Lifecycle record ──────────────────────────────────────────────────────


class MeetingLifecycleRecord(BaseModel):
    meeting_id: str  # stable key, derived from calendar event ID
    calendar_event_id: str
    organizer: str
    start_time: datetime
    end_time: datetime
    subject: str
    attendee_hash: str = ""  # SHA1 of sorted attendee emails — detects list changes
    state: MeetingLifecycleState = MeetingLifecycleState.detected
    last_error: Optional[str] = None
    retry_count: int = 0

    # Milestone timestamps — ISO strings, nullable
    detected_at: Optional[str] = None
    scheduled_at: Optional[str] = None
    dossier_sent_at: Optional[str] = None
    meeting_ended_at: Optional[str] = None
    artifact_collection_started_at: Optional[str] = None
    notes_generated_at: Optional[str] = None
    attio_synced_at: Optional[str] = None
    followup_drafted_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    failed_at: Optional[str] = None
