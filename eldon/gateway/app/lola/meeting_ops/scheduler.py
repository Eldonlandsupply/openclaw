"""
Lola Meeting Ops — scheduler.

Runs an asyncio polling loop that:
  1. Fetches upcoming calendar events every N minutes
  2. Classifies and registers new qualifying meetings
  3. Schedules T-20 min dossier tasks
  4. Fires post-meeting artifact collection after end time
  5. Handles cancellations and updates

Restart-safe: all state is persisted in SQLite.
Duplicate-safe: idempotency keys are the calendar event ID.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .artifact_collector import collect_with_retry
from .attendee_resolver import attendee_hash, resolve_attendees
from .attio_sync import sync_to_attio
from .classifier import (
    extract_join_url,
    is_qualifying_meeting,
    parse_event_times,
)
from .config import MeetingOpsConfig, load_config
from .dossier import build_dossier, send_dossier
from .followup_draft import create_followup_draft
from .graph_client import (
    GraphError,
    GraphThrottle,
    list_calendar_events,
    get_online_meeting,
)
from .models import MeetingLifecycleState
from .state_store import (
    get_by_calendar_event,
    list_meetings_by_state,
    mark_cancelled,
    transition_state,
    upsert_meeting,
)
from .models import MeetingLifecycleRecord
from .synthesizer import synthesize_notes

logger = logging.getLogger("lola.meeting_ops.scheduler")


def _make_meeting_id(calendar_event_id: str) -> str:
    """Stable, short meeting ID derived from the calendar event ID."""
    return "mtg_" + hashlib.sha1(calendar_event_id.encode()).hexdigest()[:12]


class MeetingOpsScheduler:
    """
    Long-running asyncio scheduler for meeting ops.
    Instantiate once and call run() as a background task.
    """

    def __init__(self, cfg: Optional[MeetingOpsConfig] = None):
        self.cfg = cfg or load_config()
        self._dossier_tasks: dict[str, asyncio.Task] = {}   # meeting_id → scheduled task
        self._post_tasks: dict[str, asyncio.Task] = {}       # meeting_id → post-meeting task
        self._running = False

    async def run(self) -> None:
        """Main loop — polls calendar and dispatches lifecycle tasks."""
        if not self.cfg.enabled:
            logger.info("Meeting ops disabled (LOLA_MEETINGS_ENABLED=false). Scheduler not starting.")
            return

        self._running = True
        logger.info(
            "Meeting ops scheduler started. poll_interval=%dm primary=%s",
            self.cfg.calendar_poll_interval_minutes, self.cfg.primary_email,
        )

        # On restart: reschedule any in-progress meetings from DB
        await self._recover_from_state()

        poll_interval = self.cfg.calendar_poll_interval_minutes * 60

        while self._running:
            try:
                await self._poll_calendar()
            except GraphThrottle as e:
                logger.warning("Calendar poll throttled, sleeping %ds", e.retry_after)
                await asyncio.sleep(e.retry_after)
                continue
            except GraphError as e:
                logger.error("Calendar poll Graph error (status=%d): %s", e.status, e)
            except Exception as e:
                logger.exception("Calendar poll unexpected error: %s", e)

            await asyncio.sleep(poll_interval)

    def stop(self) -> None:
        self._running = False
        for t in list(self._dossier_tasks.values()) + list(self._post_tasks.values()):
            if not t.done():
                t.cancel()

    # ── Recovery on restart ────────────────────────────────────────────────

    async def _recover_from_state(self) -> None:
        """
        On startup, re-schedule anything that was mid-flight.
        This handles Pi reboots gracefully.
        """
        now = datetime.now(timezone.utc)

        # Re-schedule dossiers that haven't been sent yet
        for state in (MeetingLifecycleState.detected, MeetingLifecycleState.scheduled,
                      MeetingLifecycleState.dossier_building):
            for rec in list_meetings_by_state(state):
                if rec.start_time > now:
                    self._schedule_dossier_task(rec)
                    logger.info("Recovery: re-scheduled dossier for %s (%s)", rec.meeting_id, rec.subject)

        # Re-trigger post-meeting collection that was in progress
        for state in (MeetingLifecycleState.meeting_ended,
                      MeetingLifecycleState.artifact_collection_started,
                      MeetingLifecycleState.transcript_pending,
                      MeetingLifecycleState.artifact_partial,
                      MeetingLifecycleState.retrying):
            for rec in list_meetings_by_state(state):
                self._schedule_post_meeting_task(rec)
                logger.info("Recovery: re-triggered post-meeting for %s (%s)", rec.meeting_id, rec.subject)

    # ── Calendar polling ───────────────────────────────────────────────────

    async def _poll_calendar(self) -> None:
        events = await list_calendar_events(self.cfg, hours_ahead=48)
        logger.debug("Polled calendar: %d events", len(events))
        seen_ids: set[str] = set()

        for event in events:
            event_id = event.get("id", "")
            if not event_id:
                continue
            seen_ids.add(event_id)

            if event.get("isCancelled", False):
                mark_cancelled(event_id)
                continue

            qualifies, reason = is_qualifying_meeting(event, self.cfg)
            if not qualifies:
                logger.debug("Event %r excluded: %s", event.get("subject", "")[:40], reason)
                continue

            await self._register_or_update_meeting(event)

    async def _register_or_update_meeting(self, event: dict) -> None:
        event_id = event.get("id", "")
        meeting_id = _make_meeting_id(event_id)
        start, end = parse_event_times(event)
        if not start or not end:
            logger.warning("Cannot parse times for event %s — skipping", event_id)
            return

        organizer = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
        subject = event.get("subject", "(no subject)")

        internal, external = resolve_attendees(event, self.cfg)
        a_hash = attendee_hash(internal + external)

        existing = get_by_calendar_event(event_id)

        if existing:
            # Check if anything changed that requires re-running dossier
            if existing.attendee_hash != a_hash:
                logger.info(
                    "Attendee list changed for %s — re-building dossier", meeting_id
                )
                transition_state(meeting_id, MeetingLifecycleState.detected)
                existing = None  # fall through to schedule fresh

            elif existing.state not in (
                MeetingLifecycleState.cancelled,
                MeetingLifecycleState.failed,
            ):
                # Already tracked and unchanged — nothing to do
                return

        # New or reset meeting
        rec = MeetingLifecycleRecord(
            meeting_id=meeting_id,
            calendar_event_id=event_id,
            organizer=organizer,
            start_time=start,
            end_time=end,
            subject=subject,
            attendee_hash=a_hash,
            state=MeetingLifecycleState.detected,
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        upsert_meeting(rec)
        logger.info("Registered meeting %s (%r) start=%s", meeting_id, subject[:50], start.isoformat())
        self._schedule_dossier_task(rec)

    # ── Dossier scheduling ─────────────────────────────────────────────────

    def _schedule_dossier_task(self, rec: MeetingLifecycleRecord) -> None:
        if rec.meeting_id in self._dossier_tasks:
            existing = self._dossier_tasks[rec.meeting_id]
            if not existing.done():
                return  # already scheduled

        task = asyncio.create_task(
            self._run_dossier_at_t_minus(rec),
            name=f"dossier_{rec.meeting_id}",
        )
        self._dossier_tasks[rec.meeting_id] = task
        task.add_done_callback(lambda t: self._on_dossier_done(t, rec.meeting_id))

    async def _run_dossier_at_t_minus(self, rec: MeetingLifecycleRecord) -> None:
        """Sleep until T-20min, then build and send dossier."""
        now = datetime.now(timezone.utc)
        send_at = rec.start_time - timedelta(minutes=self.cfg.dossier_lead_minutes)

        if send_at < now:
            # Meeting starts within the lead window or already past — skip dossier
            if rec.start_time > now:
                logger.info(
                    "Meeting %s starts in <=%dmin — building dossier immediately",
                    rec.meeting_id, self.cfg.dossier_lead_minutes,
                )
            else:
                # Meeting already started — skip to post-meeting
                logger.info("Meeting %s already started — skipping dossier, scheduling post-meeting", rec.meeting_id)
                self._schedule_post_meeting_task(rec)
                return
        else:
            wait_secs = (send_at - now).total_seconds()
            logger.info(
                "Dossier for %s scheduled in %.0fs (at %s)",
                rec.meeting_id, wait_secs, send_at.isoformat(),
            )
            transition_state(rec.meeting_id, MeetingLifecycleState.scheduled)
            await asyncio.sleep(wait_secs)

        # Build dossier
        transition_state(rec.meeting_id, MeetingLifecycleState.dossier_building)
        try:
            event = await _refetch_event(self.cfg, rec.calendar_event_id)
            if not event:
                logger.warning("Event %s disappeared — cancelling", rec.calendar_event_id)
                mark_cancelled(rec.calendar_event_id)
                return

            if event.get("isCancelled", False):
                mark_cancelled(rec.calendar_event_id)
                return

            internal, external = resolve_attendees(event, self.cfg)
            dossier = await build_dossier(event, rec.meeting_id, internal, external, self.cfg)
            sent = await send_dossier(dossier, self.cfg)

            if sent:
                transition_state(rec.meeting_id, MeetingLifecycleState.dossier_sent)
            else:
                transition_state(
                    rec.meeting_id, MeetingLifecycleState.failed,
                    error="Dossier send failed",
                )
                return

        except Exception as e:
            logger.exception("Dossier build/send failed for %s: %s", rec.meeting_id, e)
            transition_state(
                rec.meeting_id, MeetingLifecycleState.failed,
                error=str(e)[:500], increment_retry=True,
            )
            return

        # Now wait for the meeting to end, then trigger post-meeting
        self._schedule_post_meeting_task(rec)

    def _on_dossier_done(self, task: asyncio.Task, meeting_id: str) -> None:
        if task.cancelled():
            logger.debug("Dossier task cancelled for %s", meeting_id)
        elif task.exception():
            logger.error("Dossier task raised for %s: %s", meeting_id, task.exception())
        self._dossier_tasks.pop(meeting_id, None)

    # ── Post-meeting pipeline ──────────────────────────────────────────────

    def _schedule_post_meeting_task(self, rec: MeetingLifecycleRecord) -> None:
        if rec.meeting_id in self._post_tasks:
            existing = self._post_tasks[rec.meeting_id]
            if not existing.done():
                return

        task = asyncio.create_task(
            self._run_post_meeting(rec),
            name=f"post_{rec.meeting_id}",
        )
        self._post_tasks[rec.meeting_id] = task
        task.add_done_callback(lambda t: self._on_post_done(t, rec.meeting_id))

    async def _run_post_meeting(self, rec: MeetingLifecycleRecord) -> None:
        """Wait for meeting end, collect artifacts, synthesize notes, sync, draft."""
        now = datetime.now(timezone.utc)

        if rec.end_time > now:
            wait_secs = (rec.end_time - now).total_seconds() + 30  # 30s grace
            logger.info(
                "Post-meeting task for %s sleeping %.0fs until end",
                rec.meeting_id, wait_secs,
            )
            await asyncio.sleep(wait_secs)

        transition_state(rec.meeting_id, MeetingLifecycleState.meeting_ended)
        transition_state(rec.meeting_id, MeetingLifecycleState.artifact_collection_started)

        # Resolve online meeting ID for transcript fetch
        online_meeting_id = await _resolve_online_meeting_id(self.cfg, rec.calendar_event_id)

        # Collect artifacts with retry
        bundle = await collect_with_retry(
            meeting_id=rec.meeting_id,
            calendar_event_id=rec.calendar_event_id,
            online_meeting_id=online_meeting_id,
            cfg=self.cfg,
            state_store_update_fn=lambda s: transition_state(
                rec.meeting_id, MeetingLifecycleState.transcript_pending
            ),
        )

        # Synthesize notes
        try:
            event = await _refetch_event(self.cfg, rec.calendar_event_id)
            subject = event.get("subject", rec.subject) if event else rec.subject
            organizer = ""
            if event:
                organizer = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
            internal, external = resolve_attendees(event or {}, self.cfg)

            note = await synthesize_notes(
                bundle=bundle,
                event_subject=subject,
                start_time=rec.start_time,
                end_time=rec.end_time,
                organizer=organizer,
                cfg=self.cfg,
            )
            transition_state(rec.meeting_id, MeetingLifecycleState.notes_generated)

        except Exception as e:
            logger.exception("Note synthesis failed for %s: %s", rec.meeting_id, e)
            transition_state(
                rec.meeting_id, MeetingLifecycleState.failed,
                error=f"synthesis: {str(e)[:300]}", increment_retry=True,
            )
            return

        # Attio sync
        try:
            external_emails = [ep.email for ep in external if ep.email]
            await sync_to_attio(note, external_emails, self.cfg)
            transition_state(rec.meeting_id, MeetingLifecycleState.attio_synced)
        except Exception as e:
            logger.warning("Attio sync failed for %s: %s", rec.meeting_id, e)
            # Non-fatal — continue to draft

        # Follow-up draft
        try:
            draft_id = await create_followup_draft(note, external, self.cfg)
            if draft_id:
                transition_state(rec.meeting_id, MeetingLifecycleState.followup_drafted)
            else:
                logger.warning("Follow-up draft not created for %s", rec.meeting_id)
                transition_state(
                    rec.meeting_id, MeetingLifecycleState.failed,
                    error="draft creation failed",
                )
        except Exception as e:
            logger.exception("Follow-up draft failed for %s: %s", rec.meeting_id, e)
            transition_state(
                rec.meeting_id, MeetingLifecycleState.failed,
                error=f"draft: {str(e)[:300]}",
            )

    def _on_post_done(self, task: asyncio.Task, meeting_id: str) -> None:
        if task.cancelled():
            logger.debug("Post-meeting task cancelled for %s", meeting_id)
        elif task.exception():
            logger.error("Post-meeting task raised for %s: %s", meeting_id, task.exception())
        self._post_tasks.pop(meeting_id, None)


# ── Helpers ────────────────────────────────────────────────────────────────


async def _refetch_event(cfg: MeetingOpsConfig, calendar_event_id: str) -> Optional[dict]:
    from .graph_client import get_calendar_event
    try:
        return await get_calendar_event(cfg, calendar_event_id)
    except GraphError as e:
        if e.status == 404:
            return None
        raise


async def _resolve_online_meeting_id(cfg: MeetingOpsConfig, calendar_event_id: str) -> Optional[str]:
    """Resolve the Teams onlineMeeting ID from a calendar event."""
    try:
        event = await _refetch_event(cfg, calendar_event_id)
        if not event:
            return None
        join_url = extract_join_url(event)
        if not join_url:
            return None
        meeting = await get_online_meeting(cfg, join_url)
        return meeting.get("id") if meeting else None
    except Exception as e:
        logger.debug("Could not resolve online meeting ID for %s: %s", calendar_event_id, e)
        return None


# ── Entry point ─────────────────────────────────────────────────────────────


_scheduler: Optional[MeetingOpsScheduler] = None


def get_scheduler() -> MeetingOpsScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = MeetingOpsScheduler()
    return _scheduler


async def start_meeting_ops() -> None:
    """
    Start the meeting ops scheduler as a background asyncio task.
    Call this from the FastAPI startup handler or main asyncio loop.
    """
    scheduler = get_scheduler()
    asyncio.create_task(scheduler.run(), name="meeting_ops_scheduler")
    logger.info("Meeting ops background scheduler task created")
