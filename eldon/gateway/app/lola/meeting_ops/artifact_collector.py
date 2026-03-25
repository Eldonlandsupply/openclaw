"""
Lola Meeting Ops — post-meeting artifact collector.

Fetches available artifacts after a Teams meeting ends.
Implements backoff/retry since transcripts are often delayed.

Never fails silently — partial bundles are recorded and flagged.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import MeetingOpsConfig
from .graph_client import GraphError, GraphThrottle, _get, get_meeting_transcript
from .models import ArtifactAvailability, MeetingArtifactBundle

logger = logging.getLogger("lola.meeting_ops.artifact_collector")


async def collect_artifacts(
    meeting_id: str,
    calendar_event_id: str,
    online_meeting_id: Optional[str],
    cfg: MeetingOpsConfig,
) -> MeetingArtifactBundle:
    """
    Attempt one pass of artifact collection.
    Returns a bundle with whatever was available.
    Callers should retry if transcript is unavailable.
    """
    bundle = MeetingArtifactBundle(
        meeting_id=meeting_id,
        calendar_event_id=calendar_event_id,
        collected_at=datetime.utcnow(),
    )

    # Transcript
    if online_meeting_id:
        transcript = await get_meeting_transcript(cfg, online_meeting_id)
        if transcript:
            bundle.transcript = transcript
            bundle.availability.transcript = True
            logger.info("Transcript collected meeting_id=%s len=%d", meeting_id, len(transcript))
        else:
            logger.info("Transcript not yet available meeting_id=%s", meeting_id)

    # Attendee list from the calendar event
    try:
        event_data = await _get(
            cfg,
            f"/users/{cfg.primary_email}/events/{calendar_event_id}",
            {"$select": "attendees,organizer,subject,start,end"},
        )
        attendees = []
        for a in event_data.get("attendees", []):
            ea = a.get("emailAddress", {})
            attendees.append({
                "email": ea.get("address", ""),
                "name": ea.get("name", ""),
                "response": a.get("status", {}).get("response", "none"),
            })
        bundle.attendee_list = attendees
        bundle.availability.attendee_list = bool(attendees)
    except (GraphError, Exception) as e:
        logger.warning("Failed to fetch attendee list for %s: %s", calendar_event_id, e)

    # Recap / meeting notes (available via onlineMeeting if applicable)
    if online_meeting_id:
        recap = await _try_fetch_recap(cfg, online_meeting_id)
        if recap:
            bundle.recap = recap
            bundle.availability.recap = True

    # Meeting notes (channel messages approach for scheduled channel meetings)
    # Omitted — requires ChannelMessage.Read.All and channel ID resolution which
    # requires significant additional setup. Flagged as known limitation.

    # Metadata
    bundle.metadata = {
        "online_meeting_id": online_meeting_id or "",
        "calendar_event_id": calendar_event_id,
        "collection_attempt_at": datetime.utcnow().isoformat(),
    }

    return bundle


async def _try_fetch_recap(cfg: MeetingOpsConfig, online_meeting_id: str) -> Optional[str]:
    """
    Attempt to retrieve AI-generated recap for a Teams meeting.
    Returns None if not available.
    """
    try:
        # Intelligence recap: /onlineMeetings/{id}/intelligenceReport (beta)
        # Use v1.0 which is more stable, may 404 if feature not available
        data = await _get(
            cfg,
            f"/users/{cfg.primary_email}/onlineMeetings/{online_meeting_id}/recap",
        )
        if data:
            return str(data)[:5000]
    except GraphError as e:
        if e.status not in (404, 403):
            logger.debug("Recap fetch status=%d meeting=%s: %s", e.status, online_meeting_id, e)
    except Exception as e:
        logger.debug("Recap fetch error meeting=%s: %s", online_meeting_id, e)
    return None


async def collect_with_retry(
    meeting_id: str,
    calendar_event_id: str,
    online_meeting_id: Optional[str],
    cfg: MeetingOpsConfig,
    state_store_update_fn=None,  # callback(state_str) to update state
) -> MeetingArtifactBundle:
    """
    Retry artifact collection until transcript is available or max time exceeded.

    Calls state_store_update_fn("transcript_pending") while waiting.
    Returns best bundle available at end of retry window.
    """
    deadline = datetime.now(timezone.utc) + timedelta(minutes=cfg.post_meeting_max_retry_minutes)
    interval = cfg.post_meeting_retry_interval_minutes * 60  # seconds
    attempt = 0
    best_bundle = None

    while datetime.now(timezone.utc) < deadline:
        attempt += 1
        logger.info(
            "Artifact collection attempt %d meeting_id=%s",
            attempt, meeting_id,
        )

        try:
            bundle = await collect_artifacts(meeting_id, calendar_event_id, online_meeting_id, cfg)
            best_bundle = bundle

            if bundle.availability.transcript:
                logger.info("Transcript available — stopping retry. meeting_id=%s", meeting_id)
                return bundle

            if state_store_update_fn:
                await _call_maybe_async(state_store_update_fn, "transcript_pending")

        except GraphThrottle as e:
            logger.warning("Graph throttled on artifact collection, sleeping %ds", e.retry_after)
            await asyncio.sleep(e.retry_after)
            continue
        except Exception as e:
            logger.error("Artifact collection error attempt=%d meeting=%s: %s", attempt, meeting_id, e)

        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            break
        sleep_secs = min(interval, remaining)
        logger.info(
            "Transcript not ready, sleeping %ds before retry. meeting_id=%s",
            int(sleep_secs), meeting_id,
        )
        await asyncio.sleep(sleep_secs)

    logger.info(
        "Artifact collection window exhausted. transcript_available=%s meeting_id=%s",
        best_bundle.availability.transcript if best_bundle else False,
        meeting_id,
    )
    if best_bundle is None:
        # Return empty bundle to allow fallback note generation
        best_bundle = MeetingArtifactBundle(
            meeting_id=meeting_id,
            calendar_event_id=calendar_event_id,
            collected_at=datetime.utcnow(),
        )
    return best_bundle


async def _call_maybe_async(fn, *args):
    import asyncio as _asyncio
    import inspect
    if inspect.iscoroutinefunction(fn):
        await fn(*args)
    else:
        fn(*args)
