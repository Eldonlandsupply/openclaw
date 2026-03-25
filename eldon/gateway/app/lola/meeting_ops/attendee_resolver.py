"""
Lola Meeting Ops — attendee resolver and classifier.

Normalises attendee data from Graph events and classifies
each as internal (Eldon) or external.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from .config import MeetingOpsConfig
from .models import AttendeeProfile

logger = logging.getLogger("lola.meeting_ops.attendee_resolver")


def resolve_attendees(
    event: dict,
    cfg: MeetingOpsConfig,
) -> tuple[list[AttendeeProfile], list[AttendeeProfile]]:
    """
    Parse event attendees and return (internal_list, external_list).

    Internal = email domain is in cfg.internal_domains.
    External = everything else.
    Uncertain attendees (missing email) are included in external with uncertain=True.
    """
    raw_attendees = event.get("attendees", [])
    # Also include organizer if not already in attendees
    organizer = event.get("organizer", {}).get("emailAddress", {})
    org_email = organizer.get("address", "").lower().strip()
    org_name = organizer.get("name", "")

    seen: set[str] = set()
    profiles: list[AttendeeProfile] = []

    # Add organizer first
    if org_email:
        seen.add(org_email)
        profiles.append(_build_profile(org_email, org_name, cfg))

    for a in raw_attendees:
        ea = a.get("emailAddress", {})
        email = ea.get("address", "").lower().strip()
        name = ea.get("name", "")
        if not email:
            # uncertain attendee — no email
            profiles.append(AttendeeProfile(
                email="", name=name, domain="", uncertain=True, is_internal=False, confidence=0.0,
            ))
            continue
        if email in seen:
            continue
        seen.add(email)
        profiles.append(_build_profile(email, name, cfg))

    internal = [p for p in profiles if p.is_internal]
    external = [p for p in profiles if not p.is_internal]
    return internal, external


def _build_profile(email: str, name: str, cfg: MeetingOpsConfig) -> AttendeeProfile:
    domain = email.split("@")[-1] if "@" in email else ""
    is_internal = domain.lower() in [d.lower() for d in cfg.internal_domains]
    return AttendeeProfile(
        email=email,
        name=name,
        domain=domain,
        is_internal=is_internal,
        confidence=1.0,
        uncertain=False,
    )


def attendee_hash(profiles: list[AttendeeProfile]) -> str:
    """Stable hash of attendee list — detects changes on event updates."""
    emails = sorted(p.email for p in profiles if p.email)
    return hashlib.sha1(",".join(emails).encode()).hexdigest()[:12]


def internal_recipient_emails(
    internal_attendees: list[AttendeeProfile],
    primary_email: str,
    send_to_internal: bool,
) -> list[str]:
    """
    Build recipient list for dossier email.
    Always includes primary_email (Matthew).
    Optionally includes other internal attendees.
    """
    recipients = {primary_email.lower()}
    if send_to_internal:
        for p in internal_attendees:
            if p.email:
                recipients.add(p.email.lower())
    return sorted(recipients)
