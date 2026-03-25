"""
Lola Meeting Ops — follow-up draft creator.

Creates a follow-up email draft in Matthew's Drafts folder.
NEVER auto-sends. Draft-only by default.

Recipient selection is conservative:
- If followup_mode = "draft_only", saves to Drafts with all likely recipients pre-filled
- Always flags ambiguous recipient choices for human review
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from .config import MeetingOpsConfig
from .graph_client import create_mail_draft
from .models import ActionItem, AttendeeProfile, FollowUpDraftPayload, StructuredMeetingNote

logger = logging.getLogger("lola.meeting_ops.followup_draft")


def render_followup_html(
    note: StructuredMeetingNote,
    external_attendees: list[AttendeeProfile],
) -> str:
    """Render HTML body for the follow-up email."""
    sections: list[str] = []

    # Opening
    sections.append("<p>Thank you for your time today. Below is a brief summary of our discussion.</p>")

    # Summary
    if note.executive_summary:
        sections.append(f"<h3>What We Discussed</h3><p>{_esc(note.executive_summary)}</p>")

    # Topics
    if note.topics:
        sections.append("<h3>Topics Covered</h3><ul>")
        for t in note.topics:
            sections.append(f"<li>{_esc(t)}</li>")
        sections.append("</ul>")

    # Decisions
    if note.decisions:
        sections.append("<h3>Decisions Made</h3><ul>")
        for d in note.decisions:
            sections.append(f"<li>{_esc(d)}</li>")
        sections.append("</ul>")

    # Action items
    if note.action_items:
        sections.append("<h3>Action Items</h3>")
        sections.append('<table style="border-collapse:collapse;width:100%;max-width:640px">')
        sections.append(
            '<tr style="background:#f0f0f0">'
            '<th style="text-align:left;padding:6px 10px;border:1px solid #ddd">Owner</th>'
            '<th style="text-align:left;padding:6px 10px;border:1px solid #ddd">Task</th>'
            '<th style="text-align:left;padding:6px 10px;border:1px solid #ddd">Due</th>'
            "</tr>"
        )
        for ai in note.action_items:
            due = _esc(ai.due_date or "—")
            sections.append(
                f'<tr><td style="padding:6px 10px;border:1px solid #ddd">{_esc(ai.owner)}</td>'
                f'<td style="padding:6px 10px;border:1px solid #ddd">{_esc(ai.task)}</td>'
                f'<td style="padding:6px 10px;border:1px solid #ddd">{due}</td></tr>'
            )
        sections.append("</table>")
    else:
        sections.append("<p>No specific action items were identified in the meeting notes.</p>")

    # Open questions
    if note.open_questions:
        sections.append("<h3>Open Items / Pending Information</h3><ul>")
        for q in note.open_questions:
            sections.append(f"<li>{_esc(q)}</li>")
        sections.append("</ul>")

    # Closing
    sections.append(
        "<p>Please let me know if I've missed anything or if any of the above needs correction.</p>"
        "<p>Best regards,<br>Matthew Tynski<br>Eldon Land Supply</p>"
    )

    # Confidence notice if low
    if note.source_confidence == "low":
        sections.append(
            '<p style="color:#999;font-size:11px">'
            "<em>Note: Meeting transcript was unavailable. Summary may be incomplete. "
            "Please verify action items before sending.</em></p>"
        )

    return f"<html><body style='font-family:Arial,sans-serif;max-width:680px;margin:auto'>{''.join(sections)}</body></html>"


def render_followup_text(
    note: StructuredMeetingNote,
) -> str:
    """Plain-text version of the follow-up."""
    lines = [
        "Thank you for your time today. Below is a summary of our discussion.",
        "",
        f"MEETING: {note.subject}",
        f"DATE: {note.start_time.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    if note.executive_summary:
        lines += ["SUMMARY", note.executive_summary, ""]
    if note.decisions:
        lines += ["DECISIONS"] + [f"- {d}" for d in note.decisions] + [""]
    if note.action_items:
        lines += ["ACTION ITEMS"]
        for ai in note.action_items:
            due = f" (due: {ai.due_date})" if ai.due_date else ""
            lines.append(f"- {ai.owner}: {ai.task}{due}")
        lines.append("")
    if note.open_questions:
        lines += ["OPEN ITEMS"] + [f"- {q}" for q in note.open_questions] + [""]
    lines.append("Best regards,\nMatthew Tynski\nEldon Land Supply")
    return "\n".join(lines)


def build_followup_payload(
    note: StructuredMeetingNote,
    external_attendees: list[AttendeeProfile],
    cfg: MeetingOpsConfig,
) -> FollowUpDraftPayload:
    """
    Build the FollowUpDraftPayload.
    Recipients are pre-filled but review_flags indicate any ambiguity.
    """
    review_flags: list[str] = []

    # External recipients — default for follow-up
    to_emails: list[str] = []
    for ep in external_attendees:
        if ep.email and not ep.uncertain:
            to_emails.append(ep.email)
        elif ep.uncertain:
            review_flags.append(
                f"Attendee '{ep.name or 'unknown'}' has uncertain identity — verify before sending."
            )

    # If no external attendees, flag for review
    if not to_emails:
        review_flags.append("No confirmed external recipients — review To: field before sending.")

    # Low confidence note
    if note.source_confidence == "low":
        review_flags.append(
            "Meeting transcript unavailable — notes derived from limited sources. Verify content before sending."
        )

    # Action items with unknown owners
    unknown_owners = [ai for ai in note.action_items if ai.owner.lower() in ("unknown", "")]
    if unknown_owners:
        review_flags.append(
            f"{len(unknown_owners)} action item(s) have unknown owner — assign before sending."
        )

    subject = f"Follow-Up: {note.subject} | {note.start_time.strftime('%Y-%m-%d')}"

    return FollowUpDraftPayload(
        meeting_id=note.meeting_id,
        to=to_emails,
        cc=[],
        subject=subject,
        body_html=render_followup_html(note, external_attendees),
        body_text=render_followup_text(note),
        generated_at=datetime.utcnow(),
        review_flags=review_flags,
    )


async def create_followup_draft(
    note: StructuredMeetingNote,
    external_attendees: list[AttendeeProfile],
    cfg: MeetingOpsConfig,
) -> Optional[str]:
    """
    Build and save a follow-up draft to Matthew's Drafts folder.
    Returns the Graph message ID, or None on failure.
    Never sends.
    """
    payload = build_followup_payload(note, external_attendees, cfg)

    if payload.review_flags:
        logger.info(
            "Follow-up draft has %d review flag(s) for meeting %s: %s",
            len(payload.review_flags), note.meeting_id, payload.review_flags,
        )

    draft_id = await create_mail_draft(
        cfg,
        to_emails=payload.to,
        cc_emails=payload.cc,
        subject=payload.subject,
        body_html=payload.body_html,
    )

    if draft_id:
        logger.info(
            "Follow-up draft saved meeting=%s draft_id=%s flags=%d",
            note.meeting_id, draft_id[:16], len(payload.review_flags),
        )
    else:
        logger.error("Failed to save follow-up draft for meeting %s", note.meeting_id)

    return draft_id


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
