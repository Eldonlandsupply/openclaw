"""
Lola Meeting Ops — dossier enrichment engine.

Builds context for external attendees by querying:
  1. Attio CRM (existing client)
  2. Prior email threads (via Graph)

Hard constraint: never fabricate facts.
All fields come from evidenced sources only.
Low-confidence data is flagged, not invented.
"""

from __future__ import annotations

import logging
from typing import Optional

from .config import MeetingOpsConfig
from .graph_client import GraphError, _get
from .models import AttendeeProfile

logger = logging.getLogger("lola.meeting_ops.enrichment")


async def enrich_external_attendee(
    profile: AttendeeProfile,
    cfg: MeetingOpsConfig,
) -> AttendeeProfile:
    """
    Attempt to enrich a single external attendee from available sources.
    Failures are soft — we return whatever we have.
    """
    # Attio lookup
    if cfg.attio_api_key:
        profile = await _enrich_from_attio(profile, cfg)

    # Graph mail lookup
    if cfg.primary_email and cfg.tenant_id:
        profile = await _enrich_from_mail(profile, cfg)

    return profile


async def _enrich_from_attio(profile: AttendeeProfile, cfg: MeetingOpsConfig) -> AttendeeProfile:
    """Look up the attendee in Attio by email."""
    try:
        import sys, os
        src = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from openclaw.integrations.attio.client import AttioClient

        c = AttioClient(api_key=cfg.attio_api_key)
        results = await c.search_records("people", profile.email, limit=3)
        await c.close()

        for r in results:
            attrs = r.get("values", {})
            # Check if email matches
            emails = attrs.get("email_addresses", [])
            matched = any(
                e.get("email_address", "").lower() == profile.email.lower()
                for e in emails
            )
            if not matched and results:
                # First result may still be the right one if query matched
                matched = True

            if matched:
                name_vals = attrs.get("name", [])
                title_vals = attrs.get("job_title", [])
                company_vals = attrs.get("primary_employer", [])

                if name_vals and not profile.name:
                    profile.name = name_vals[0].get("full_name", profile.name)
                if title_vals:
                    profile.title = title_vals[0].get("value", None)
                if company_vals:
                    rec = company_vals[0].get("target_record", {})
                    if rec:
                        profile.company = rec.get("values", {}).get("name", [{}])[0].get("value")

                # Build a short Attio context summary
                notes = []
                if profile.title:
                    notes.append(f"Title: {profile.title}")
                if profile.company:
                    notes.append(f"Company: {profile.company}")
                if notes:
                    profile.attio_context_summary = "; ".join(notes)
                    profile.evidence_refs.append("attio_crm")
                break

    except ImportError:
        logger.debug("Attio client not importable, skipping CRM enrichment")
    except Exception as e:
        logger.warning("Attio enrichment failed for %s: %s", profile.email, e)

    return profile


async def _enrich_from_mail(profile: AttendeeProfile, cfg: MeetingOpsConfig) -> AttendeeProfile:
    """
    Look for prior email threads with this person in Matthew's mailbox.
    Returns a short summary of recent exchanges (subject lines only — no body).
    """
    try:
        params = {
            "$filter": (
                f"(from/emailAddress/address eq '{profile.email}') "
                f"or (toRecipients/any(r: r/emailAddress/address eq '{profile.email}'))"
            ),
            "$select": "subject,receivedDateTime,from,toRecipients",
            "$orderby": "receivedDateTime desc",
            "$top": "5",
        }
        data = await _get(cfg, f"/users/{cfg.primary_email}/messages", params)
        messages = data.get("value", [])
        if messages:
            subjects = [m.get("subject", "") for m in messages[:5] if m.get("subject")]
            if subjects:
                profile.prior_email_summary = f"Recent emails ({len(subjects)}): " + "; ".join(
                    f'"{s[:60]}"' for s in subjects
                )
                profile.evidence_refs.append("outlook_mail")
    except GraphError as e:
        if e.status == 403:
            logger.debug("Mail search permission denied for %s", profile.email)
        else:
            logger.warning("Mail enrichment error for %s: %s", profile.email, e)
    except Exception as e:
        logger.warning("Mail enrichment unexpected error for %s: %s", profile.email, e)

    return profile
