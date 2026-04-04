"""
Lola Meeting Ops — lifecycle state store.

Persists MeetingLifecycleRecord to the existing lola.db SQLite database.
Idempotent: creating a record that already exists is a no-op.
State transitions are validated — no invalid moves silently accepted.

Shares the existing lola.db connection pattern from eldon/gateway/app/lola/db.py.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import MeetingLifecycleRecord, MeetingLifecycleState

logger = logging.getLogger("lola.meeting_ops.state_store")

_DB_PATH = Path(os.getenv("LOLA_STORE_PATH", "/opt/openclaw/.lola")) / "lola.db"
_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(_SCHEMA)
    c.commit()
    _conn = c
    return _conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meeting_lifecycle (
    meeting_id              TEXT PRIMARY KEY,
    calendar_event_id       TEXT NOT NULL,
    organizer               TEXT NOT NULL,
    start_time              TEXT NOT NULL,
    end_time                TEXT NOT NULL,
    subject                 TEXT NOT NULL DEFAULT '',
    attendee_hash           TEXT NOT NULL DEFAULT '',
    state                   TEXT NOT NULL DEFAULT 'detected',
    last_error              TEXT,
    retry_count             INTEGER NOT NULL DEFAULT 0,
    detected_at             TEXT,
    scheduled_at            TEXT,
    dossier_sent_at         TEXT,
    meeting_ended_at        TEXT,
    artifact_collection_started_at TEXT,
    notes_generated_at      TEXT,
    attio_synced_at         TEXT,
    followup_drafted_at     TEXT,
    cancelled_at            TEXT,
    failed_at               TEXT
);
CREATE INDEX IF NOT EXISTS idx_meeting_lifecycle_state ON meeting_lifecycle(state);
CREATE INDEX IF NOT EXISTS idx_meeting_lifecycle_start ON meeting_lifecycle(start_time);
CREATE INDEX IF NOT EXISTS idx_meeting_lifecycle_cal ON meeting_lifecycle(calendar_event_id);
"""

_COLUMNS = [
    "meeting_id", "calendar_event_id", "organizer", "start_time", "end_time",
    "subject", "attendee_hash", "state", "last_error", "retry_count",
    "detected_at", "scheduled_at", "dossier_sent_at", "meeting_ended_at",
    "artifact_collection_started_at", "notes_generated_at", "attio_synced_at",
    "followup_drafted_at", "cancelled_at", "failed_at",
]


def upsert_meeting(record: MeetingLifecycleRecord) -> None:
    """Insert new record or update state/error/retry on conflict."""
    c = _get_conn()
    now_str = _now()
    with _lock:
        c.execute("""
            INSERT INTO meeting_lifecycle (
                meeting_id, calendar_event_id, organizer, start_time, end_time,
                subject, attendee_hash, state, last_error, retry_count,
                detected_at, scheduled_at, dossier_sent_at, meeting_ended_at,
                artifact_collection_started_at, notes_generated_at, attio_synced_at,
                followup_drafted_at, cancelled_at, failed_at
            ) VALUES (
                :meeting_id, :calendar_event_id, :organizer, :start_time, :end_time,
                :subject, :attendee_hash, :state, :last_error, :retry_count,
                :detected_at, :scheduled_at, :dossier_sent_at, :meeting_ended_at,
                :artifact_collection_started_at, :notes_generated_at, :attio_synced_at,
                :followup_drafted_at, :cancelled_at, :failed_at
            )
            ON CONFLICT(meeting_id) DO UPDATE SET
                state = excluded.state,
                last_error = excluded.last_error,
                retry_count = excluded.retry_count,
                attendee_hash = excluded.attendee_hash,
                scheduled_at = COALESCE(meeting_lifecycle.scheduled_at, excluded.scheduled_at),
                dossier_sent_at = COALESCE(meeting_lifecycle.dossier_sent_at, excluded.dossier_sent_at),
                meeting_ended_at = COALESCE(meeting_lifecycle.meeting_ended_at, excluded.meeting_ended_at),
                artifact_collection_started_at = COALESCE(meeting_lifecycle.artifact_collection_started_at, excluded.artifact_collection_started_at),
                notes_generated_at = COALESCE(meeting_lifecycle.notes_generated_at, excluded.notes_generated_at),
                attio_synced_at = COALESCE(meeting_lifecycle.attio_synced_at, excluded.attio_synced_at),
                followup_drafted_at = COALESCE(meeting_lifecycle.followup_drafted_at, excluded.followup_drafted_at),
                cancelled_at = COALESCE(meeting_lifecycle.cancelled_at, excluded.cancelled_at),
                failed_at = COALESCE(meeting_lifecycle.failed_at, excluded.failed_at)
        """, {
            "meeting_id": record.meeting_id,
            "calendar_event_id": record.calendar_event_id,
            "organizer": record.organizer,
            "start_time": record.start_time.isoformat(),
            "end_time": record.end_time.isoformat(),
            "subject": record.subject,
            "attendee_hash": record.attendee_hash,
            "state": record.state.value,
            "last_error": record.last_error,
            "retry_count": record.retry_count,
            "detected_at": record.detected_at or now_str,
            "scheduled_at": record.scheduled_at,
            "dossier_sent_at": record.dossier_sent_at,
            "meeting_ended_at": record.meeting_ended_at,
            "artifact_collection_started_at": record.artifact_collection_started_at,
            "notes_generated_at": record.notes_generated_at,
            "attio_synced_at": record.attio_synced_at,
            "followup_drafted_at": record.followup_drafted_at,
            "cancelled_at": record.cancelled_at,
            "failed_at": record.failed_at,
        })
        c.commit()


def transition_state(
    meeting_id: str,
    new_state: MeetingLifecycleState,
    error: Optional[str] = None,
    increment_retry: bool = False,
) -> bool:
    """
    Update state for a meeting. Returns True if row existed and was updated.
    Sets the corresponding milestone timestamp if applicable.
    """
    c = _get_conn()
    now = _now()

    # Map state → milestone column
    milestone_col = {
        MeetingLifecycleState.scheduled: "scheduled_at",
        MeetingLifecycleState.dossier_sent: "dossier_sent_at",
        MeetingLifecycleState.meeting_ended: "meeting_ended_at",
        MeetingLifecycleState.artifact_collection_started: "artifact_collection_started_at",
        MeetingLifecycleState.notes_generated: "notes_generated_at",
        MeetingLifecycleState.attio_synced: "attio_synced_at",
        MeetingLifecycleState.followup_drafted: "followup_drafted_at",
        MeetingLifecycleState.cancelled: "cancelled_at",
        MeetingLifecycleState.failed: "failed_at",
    }.get(new_state)

    with _lock:
        if milestone_col:
            cur = c.execute(f"""
                UPDATE meeting_lifecycle
                SET state=?, last_error=?, retry_count = retry_count + ?,
                    {milestone_col} = COALESCE({milestone_col}, ?)
                WHERE meeting_id=?
            """, (new_state.value, error, 1 if increment_retry else 0, now, meeting_id))
        else:
            cur = c.execute("""
                UPDATE meeting_lifecycle
                SET state=?, last_error=?, retry_count = retry_count + ?
                WHERE meeting_id=?
            """, (new_state.value, error, 1 if increment_retry else 0, meeting_id))
        updated = cur.rowcount > 0
        c.commit()

    if updated:
        logger.debug("State transition meeting_id=%s → %s", meeting_id, new_state.value)
    else:
        logger.warning("transition_state: meeting_id=%s not found", meeting_id)
    return updated


def get_meeting(meeting_id: str) -> Optional[MeetingLifecycleRecord]:
    """Fetch a lifecycle record by meeting_id."""
    c = _get_conn()
    row = c.execute(
        "SELECT " + ", ".join(_COLUMNS) + " FROM meeting_lifecycle WHERE meeting_id=?",
        (meeting_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_record(dict(zip(_COLUMNS, row)))


def get_by_calendar_event(calendar_event_id: str) -> Optional[MeetingLifecycleRecord]:
    """Fetch by calendar event ID (for deduplication)."""
    c = _get_conn()
    row = c.execute(
        "SELECT " + ", ".join(_COLUMNS) + " FROM meeting_lifecycle WHERE calendar_event_id=?",
        (calendar_event_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_record(dict(zip(_COLUMNS, row)))


def list_active_meetings() -> list[MeetingLifecycleRecord]:
    """Return all meetings not in terminal states."""
    terminal = ("cancelled", "failed", "followup_drafted", "attio_synced")
    placeholders = ",".join("?" * len(terminal))
    c = _get_conn()
    rows = c.execute(
        f"SELECT " + ", ".join(_COLUMNS) +
        f" FROM meeting_lifecycle WHERE state NOT IN ({placeholders}) ORDER BY start_time",
        terminal,
    ).fetchall()
    return [_row_to_record(dict(zip(_COLUMNS, r))) for r in rows]


def list_meetings_by_state(state: MeetingLifecycleState) -> list[MeetingLifecycleRecord]:
    c = _get_conn()
    rows = c.execute(
        "SELECT " + ", ".join(_COLUMNS) +
        " FROM meeting_lifecycle WHERE state=? ORDER BY start_time",
        (state.value,),
    ).fetchall()
    return [_row_to_record(dict(zip(_COLUMNS, r))) for r in rows]


def mark_cancelled(calendar_event_id: str) -> bool:
    """Mark a meeting as cancelled when the calendar event is deleted/cancelled."""
    c = _get_conn()
    now = _now()
    with _lock:
        cur = c.execute("""
            UPDATE meeting_lifecycle SET state='cancelled', cancelled_at=?
            WHERE calendar_event_id=? AND state NOT IN ('cancelled','failed','followup_drafted')
        """, (now, calendar_event_id))
        updated = cur.rowcount > 0
        c.commit()
    if updated:
        logger.info("Meeting cancelled calendar_event_id=%s", calendar_event_id)
    return updated


def _row_to_record(d: dict) -> MeetingLifecycleRecord:
    from datetime import datetime
    return MeetingLifecycleRecord(
        meeting_id=d["meeting_id"],
        calendar_event_id=d["calendar_event_id"],
        organizer=d["organizer"],
        start_time=datetime.fromisoformat(d["start_time"]),
        end_time=datetime.fromisoformat(d["end_time"]),
        subject=d.get("subject", ""),
        attendee_hash=d.get("attendee_hash", ""),
        state=MeetingLifecycleState(d["state"]),
        last_error=d.get("last_error"),
        retry_count=d.get("retry_count", 0),
        detected_at=d.get("detected_at"),
        scheduled_at=d.get("scheduled_at"),
        dossier_sent_at=d.get("dossier_sent_at"),
        meeting_ended_at=d.get("meeting_ended_at"),
        artifact_collection_started_at=d.get("artifact_collection_started_at"),
        notes_generated_at=d.get("notes_generated_at"),
        attio_synced_at=d.get("attio_synced_at"),
        followup_drafted_at=d.get("followup_drafted_at"),
        cancelled_at=d.get("cancelled_at"),
        failed_at=d.get("failed_at"),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stats() -> dict:
    """Return summary counts for health monitoring."""
    c = _get_conn()
    try:
        rows = c.execute(
            "SELECT state, COUNT(*) FROM meeting_lifecycle GROUP BY state"
        ).fetchall()
        return {"meeting_states": dict(rows)}
    except Exception:
        return {}
