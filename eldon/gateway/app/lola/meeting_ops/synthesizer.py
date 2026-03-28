"""
Lola Meeting Ops — meeting note synthesizer.

Produces StructuredMeetingNote from a MeetingArtifactBundle.
Uses the existing LLM routing (xAI Grok / OpenRouter).

Rules:
- Never fabricate action items or dates
- All action items must be explicitly stated in source material
- If source is weak, source_confidence = "low" and notes reflect that
- Transcript → high confidence; recap only → medium; no artifacts → low
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from .config import MeetingOpsConfig
from .models import ActionItem, MeetingArtifactBundle, StructuredMeetingNote
from openclaw.llm.provider_resolution import LLMProviderResolutionError, resolve_llm_provider

logger = logging.getLogger("lola.meeting_ops.synthesizer")


_SYNTHESIS_SYSTEM = """\
You are an executive assistant producing structured meeting notes.
You receive meeting artifacts (transcript, recap, notes, attendee list) 
and must produce a JSON object with the exact schema below.

RULES:
- Never fabricate action items, decisions, or due dates
- Only include information that is explicitly stated in the provided material
- If material is thin, say so honestly in executive_summary
- action_items must list who said they would do what — exact names if available
- due_date must be blank ("") unless a specific date or deadline was explicitly mentioned
- source_confidence: "high" if transcript present, "medium" if recap only, "low" if nothing

REQUIRED OUTPUT (JSON only, no markdown):
{
  "executive_summary": "2-3 sentence summary",
  "topics": ["topic 1", "topic 2"],
  "decisions": ["decision 1"],
  "action_items": [
    {"owner": "Name or Unknown", "task": "task description", "due_date": "", "confidence": 0.9, "evidence_source": "transcript"}
  ],
  "open_questions": ["question 1"],
  "commitments_risks": ["commitment or risk 1"],
  "source_confidence": "high|medium|low"
}
"""


async def synthesize_notes(
    bundle: MeetingArtifactBundle,
    event_subject: str,
    start_time: datetime,
    end_time: datetime,
    organizer: str,
    cfg: MeetingOpsConfig,
) -> StructuredMeetingNote:
    """
    Build structured notes from artifact bundle.
    Falls back to a minimal note if LLM fails or no content exists.
    """
    source_refs = []
    content_parts = []

    if bundle.transcript:
        content_parts.append(f"TRANSCRIPT:\n{bundle.transcript[:15000]}")
        source_refs.append("transcript")

    if bundle.recap:
        content_parts.append(f"MEETING RECAP:\n{bundle.recap[:3000]}")
        source_refs.append("recap")

    if bundle.notes:
        content_parts.append(f"MEETING NOTES:\n{bundle.notes[:3000]}")
        source_refs.append("notes")

    if bundle.attendee_list:
        attendee_str = "\n".join(
            f"- {a.get('name', '')} <{a.get('email', '')}> ({a.get('response', '')})"
            for a in bundle.attendee_list
        )
        content_parts.append(f"ATTENDEES:\n{attendee_str}")

    if not content_parts:
        # Nothing to synthesize — return minimal note
        return _minimal_note(bundle, event_subject, start_time, end_time, organizer)

    # Determine confidence level
    if bundle.availability.transcript:
        confidence = "high"
    elif bundle.availability.recap or bundle.availability.notes:
        confidence = "medium"
    else:
        confidence = "low"

    user_prompt = (
        f"Meeting: {event_subject}\n"
        f"Date: {start_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Organizer: {organizer}\n\n"
        + "\n\n---\n\n".join(content_parts)
    )

    raw = await _call_llm(cfg, _SYNTHESIS_SYSTEM, user_prompt)

    if not raw:
        logger.warning("LLM synthesis returned empty for meeting %s", bundle.meeting_id)
        return _minimal_note(bundle, event_subject, start_time, end_time, organizer, confidence)

    parsed = _parse_llm_output(raw, confidence)
    if not parsed:
        logger.warning("Failed to parse LLM output for meeting %s", bundle.meeting_id)
        return _minimal_note(bundle, event_subject, start_time, end_time, organizer, confidence)

    attendee_emails = [a.get("email", "") for a in bundle.attendee_list if a.get("email")]

    return StructuredMeetingNote(
        meeting_id=bundle.meeting_id,
        calendar_event_id=bundle.calendar_event_id,
        subject=event_subject,
        start_time=start_time,
        end_time=end_time,
        organizer=organizer,
        attendees=attendee_emails,
        executive_summary=parsed.get("executive_summary", ""),
        topics=parsed.get("topics", []),
        decisions=parsed.get("decisions", []),
        action_items=[ActionItem(**ai) for ai in parsed.get("action_items", [])],
        open_questions=parsed.get("open_questions", []),
        commitments_risks=parsed.get("commitments_risks", []),
        source_confidence=parsed.get("source_confidence", confidence),
        raw_artifact_refs=source_refs,
        generated_at=datetime.utcnow(),
    )


def _minimal_note(
    bundle: MeetingArtifactBundle,
    subject: str,
    start: datetime,
    end: datetime,
    organizer: str,
    confidence: str = "low",
) -> StructuredMeetingNote:
    attendee_emails = [a.get("email", "") for a in bundle.attendee_list if a.get("email")]
    return StructuredMeetingNote(
        meeting_id=bundle.meeting_id,
        calendar_event_id=bundle.calendar_event_id,
        subject=subject,
        start_time=start,
        end_time=end,
        organizer=organizer,
        attendees=attendee_emails,
        executive_summary=(
            "Meeting artifacts were unavailable or too limited for synthesis. "
            "Manual review recommended."
        ),
        source_confidence=confidence,
        raw_artifact_refs=[],
        generated_at=datetime.utcnow(),
    )


def _parse_llm_output(raw: str, fallback_confidence: str) -> Optional[dict]:
    """Parse JSON from LLM response, tolerating markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        data = json.loads(text)
        # Validate action_items structure
        validated_items = []
        for ai in data.get("action_items", []):
            if isinstance(ai, dict) and "owner" in ai and "task" in ai:
                validated_items.append({
                    "owner": str(ai.get("owner", "Unknown")),
                    "task": str(ai.get("task", "")),
                    "due_date": str(ai.get("due_date", "")) or None,
                    "confidence": float(ai.get("confidence", 1.0)),
                    "evidence_source": str(ai.get("evidence_source", "unknown")),
                })
        data["action_items"] = validated_items
        if "source_confidence" not in data:
            data["source_confidence"] = fallback_confidence
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("LLM JSON parse error: %s | raw[:200]=%r", e, raw[:200])
        return None


async def _call_llm(cfg: MeetingOpsConfig, system: str, user: str) -> str:
    """Call the configured LLM and return raw text response."""
    provider = cfg.llm_provider.lower()
    model = cfg.chat_model

    try:
        resolved = resolve_llm_provider(
            provider=provider,
            model=model,
            configured_base_url=os.getenv("OPENAI_BASE_URL", "").strip() or None,
        )
        logger.info(
            "meeting-ops llm route",
            extra={
                "provider": resolved.provider,
                "base_url": resolved.base_url,
                "model": resolved.model,
                "api_key_source": resolved.api_key_source,
            },
        )
        if resolved.provider == "xai":
            return await _call_xai(resolved.model, system, user)
        return await _call_openai_compat(
            model=resolved.model,
            system=system,
            user=user,
            base_url=resolved.base_url,
            api_key=resolved.api_key,
        )
    except LLMProviderResolutionError as e:
        logger.error("LLM provider config invalid: %s", e)
        return ""
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return ""


async def _call_xai(model: str, system: str, user: str) -> str:
    import aiohttp
    api_key = os.getenv("XAI_API_KEY", "")
    if not api_key:
        logger.warning("XAI_API_KEY not set")
        return ""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            data = await resp.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _call_openai_compat(model: str, system: str, user: str, base_url: str, api_key: str) -> str:
    import aiohttp
    if not api_key:
        logger.warning("LLM API key not set for %s", base_url)
        return ""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            data = await resp.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")
