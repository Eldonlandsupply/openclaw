"""
Lola Meeting Ops — dossier builder, renderer, and sender.

Builds the pre-meeting dossier and sends it as an HTML email
to Matthew and internal Eldon attendees.

External attendees are never included in the recipient list.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .attendee_resolver import internal_recipient_emails
from .config import MeetingOpsConfig
from .enrichment import enrich_external_attendee
from .graph_client import GraphError, send_mail
from .models import AttendeeProfile, MeetingDossier

logger = logging.getLogger("lola.meeting_ops.dossier")


async def build_dossier(
    event: dict,
    meeting_id: str,
    internal_attendees: list[AttendeeProfile],
    external_attendees: list[AttendeeProfile],
    cfg: MeetingOpsConfig,
) -> MeetingDossier:
    """Build a MeetingDossier by enriching external attendees."""
    from .classifier import extract_join_url, parse_event_times

    start, end = parse_event_times(event)
    if not start or not end:
        raise ValueError(f"Cannot parse start/end for event {event.get('id')}")

    organizer = event.get("organizer", {}).get("emailAddress", {})
    join_url = extract_join_url(event)

    # Enrich external attendees (soft failure — partial enrichment is fine)
    enriched_externals: list[AttendeeProfile] = []
    for ep in external_attendees:
        if ep.email:
            try:
                ep = await enrich_external_attendee(ep, cfg)
            except Exception as e:
                logger.warning("Enrichment failed for %s: %s", ep.email, e)
        enriched_externals.append(ep)

    # Build relationship summary
    rel_summary = _build_relationship_summary(enriched_externals)
    talking_points = _build_talking_points(enriched_externals, event)
    risk_flags = _build_risk_flags(enriched_externals)

    recipients = internal_recipient_emails(
        internal_attendees, cfg.primary_email, cfg.send_dossier_to_internal_attendees
    )

    return MeetingDossier(
        meeting_id=meeting_id,
        calendar_event_id=event.get("id", ""),
        subject=event.get("subject", "(no subject)"),
        start_time=start,
        end_time=end,
        organizer_email=organizer.get("address", ""),
        organizer_name=organizer.get("name", ""),
        join_url=join_url,
        external_attendees=enriched_externals,
        internal_recipients=recipients,
        relationship_summary=rel_summary,
        talking_points=talking_points,
        risk_flags=risk_flags,
        generated_at=datetime.utcnow(),
    )


def _build_relationship_summary(externals: list[AttendeeProfile]) -> Optional[str]:
    parts = []
    for ep in externals:
        ctx_parts = []
        if ep.attio_context_summary:
            ctx_parts.append(ep.attio_context_summary)
        if ep.prior_email_summary:
            ctx_parts.append(ep.prior_email_summary)
        if ctx_parts:
            parts.append(f"**{ep.name or ep.email}**: " + " | ".join(ctx_parts))
    return "\n".join(parts) if parts else None


def _build_talking_points(externals: list[AttendeeProfile], event: dict) -> list[str]:
    """
    Build suggested talking points from evidence only.
    No fabrication — only points that are directly supported.
    """
    points = []
    body = event.get("bodyPreview", "")
    if body:
        points.append(f"Agenda/context from invite: {body[:200]}")
    for ep in externals:
        if ep.company:
            points.append(f"Understand {ep.company}'s relationship with Eldon Land Supply.")
        if ep.prior_email_summary:
            points.append(f"Prior email context with {ep.name or ep.email} noted — review before meeting.")
    return points[:8]  # cap at 8


def _build_risk_flags(externals: list[AttendeeProfile]) -> list[str]:
    flags = []
    uncertain = [ep for ep in externals if ep.uncertain]
    if uncertain:
        flags.append(f"{len(uncertain)} attendee(s) have uncertain/missing identity — verify before meeting.")
    no_context = [ep for ep in externals if not ep.attio_context_summary and not ep.prior_email_summary]
    if no_context:
        names = ", ".join(ep.name or ep.email for ep in no_context[:3])
        flags.append(f"No prior context found for: {names}.")
    return flags


# ── Renderer ──────────────────────────────────────────────────────────────


def render_dossier_html(dossier: MeetingDossier) -> str:
    local_start = dossier.start_time.strftime("%Y-%m-%d %H:%M UTC")
    local_end = dossier.end_time.strftime("%H:%M UTC")

    sections: list[str] = []

    # Header
    sections.append(f"""
<h2 style="color:#1a1a2e">📋 Pre-Meeting Dossier</h2>
<table style="border-collapse:collapse;width:100%;max-width:700px">
  <tr><td style="padding:4px 8px;font-weight:bold">Meeting</td>
      <td style="padding:4px 8px">{_esc(dossier.subject)}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Time</td>
      <td style="padding:4px 8px">{local_start} – {local_end}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Organizer</td>
      <td style="padding:4px 8px">{_esc(dossier.organizer_name)} ({_esc(dossier.organizer_email)})</td></tr>
</table>
""")

    # External attendee dossiers
    if dossier.external_attendees:
        sections.append("<h3>External Attendees</h3>")
        for ep in dossier.external_attendees:
            name_label = _esc(ep.name or ep.email)
            uncertain_badge = " <span style='color:#e74c3c'>[identity uncertain]</span>" if ep.uncertain else ""
            sections.append(f"<div style='margin-bottom:16px;padding:12px;border:1px solid #ddd;border-radius:6px'>")
            sections.append(f"<strong>{name_label}</strong>{uncertain_badge}<br>")
            sections.append(f"<em>{_esc(ep.email)}</em> | Domain: {_esc(ep.domain)}<br>")
            if ep.title:
                sections.append(f"Title: {_esc(ep.title)}<br>")
            if ep.company:
                sections.append(f"Company: {_esc(ep.company)}<br>")
            if ep.attio_context_summary:
                sections.append(f"<strong>CRM context:</strong> {_esc(ep.attio_context_summary)}<br>")
            if ep.prior_email_summary:
                sections.append(f"<strong>Email history:</strong> {_esc(ep.prior_email_summary)}<br>")
            if not ep.attio_context_summary and not ep.prior_email_summary:
                sections.append("<em style='color:#888'>No prior context found in CRM or email.</em><br>")
            if ep.evidence_refs:
                sections.append(f"<small>Sources: {', '.join(ep.evidence_refs)}</small>")
            sections.append("</div>")
    else:
        sections.append("<p>No external attendees detected.</p>")

    # Relationship summary
    if dossier.relationship_summary:
        sections.append("<h3>Prior Relationship Context</h3>")
        sections.append(f"<p>{_esc(dossier.relationship_summary)}</p>")

    # Talking points
    if dossier.talking_points:
        sections.append("<h3>Suggested Talking Points</h3><ul>")
        for tp in dossier.talking_points:
            sections.append(f"<li>{_esc(tp)}</li>")
        sections.append("</ul>")

    # Risks
    if dossier.risk_flags:
        sections.append("<h3 style='color:#c0392b'>⚠ Risks / Open Questions</h3><ul>")
        for rf in dossier.risk_flags:
            sections.append(f"<li style='color:#c0392b'>{_esc(rf)}</li>")
        sections.append("</ul>")

    # Footer
    sections.append(
        f"<hr><small>Generated by Lola at {dossier.generated_at.strftime('%Y-%m-%d %H:%M UTC')} | "
        "For Matthew Tynski — not for external distribution.</small>"
    )

    return f"<html><body style='font-family:Arial,sans-serif;max-width:720px;margin:auto'>{''.join(sections)}</body></html>"


def render_dossier_subject(dossier: MeetingDossier) -> str:
    date_str = dossier.start_time.strftime("%Y-%m-%d")
    time_str = dossier.start_time.strftime("%H:%M UTC")
    return f"[20-Min Dossier] {dossier.subject} | {date_str} | {time_str}"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Sender ────────────────────────────────────────────────────────────────


async def send_dossier(dossier: MeetingDossier, cfg: MeetingOpsConfig) -> bool:
    """
    Send the dossier email to internal recipients only.
    Returns True on success.
    """
    if not dossier.internal_recipients:
        logger.warning("No recipients for dossier meeting_id=%s", dossier.meeting_id)
        return False

    subject = render_dossier_subject(dossier)
    body = render_dossier_html(dossier)

    success = await send_mail(cfg, dossier.internal_recipients, subject, body)
    if success:
        logger.info(
            "Dossier sent meeting_id=%s recipients=%s",
            dossier.meeting_id, dossier.internal_recipients,
        )
    else:
        logger.error("Dossier send failed meeting_id=%s", dossier.meeting_id)
    return success
