"""
Lola Meeting Ops — configuration.

Reads from env vars (consistent with existing eldon pattern).
Fails loudly at startup if required values are missing while feature is enabled.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("lola.meeting_ops.config")


@dataclass
class MeetingOpsConfig:
    enabled: bool = False

    # Graph credentials (reuse existing OUTLOOK_ or MS_ prefix that the adapter already reads)
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    primary_email: str = ""  # Matthew's UPN / mailbox

    # Behaviour
    internal_domains: list[str] = field(default_factory=list)
    dossier_lead_minutes: int = 20
    post_meeting_retry_interval_minutes: int = 5
    post_meeting_max_retry_minutes: int = 60
    calendar_poll_interval_minutes: int = 5
    organizer_only: bool = False  # if True, only watch meetings where Matthew is organizer
    include_meeting_chat: bool = False
    include_shared_files: bool = False
    send_dossier_to_internal_attendees: bool = True
    default_followup_mode: str = "draft_only"
    skip_declined: bool = True
    allowed_categories: list[str] = field(default_factory=list)
    blocked_categories: list[str] = field(default_factory=list)

    # Attio
    attio_api_key: str = ""

    # LLM for synthesis (reuses existing OPENCLAW env)
    llm_provider: str = "xai"
    chat_model: str = "grok-3-mini"


_config: Optional[MeetingOpsConfig] = None


def load_config() -> MeetingOpsConfig:
    global _config
    if _config is not None:
        return _config

    enabled = os.getenv("LOLA_MEETINGS_ENABLED", "false").lower() == "true"

    cfg = MeetingOpsConfig(
        enabled=enabled,
        tenant_id=os.getenv("OUTLOOK_TENANT_ID", os.getenv("MS_TENANT_ID", os.getenv("AZURE_TENANT_ID", ""))),
        client_id=os.getenv("OUTLOOK_CLIENT_ID", os.getenv("MS_CLIENT_ID", os.getenv("AZURE_CLIENT_ID", ""))),
        client_secret=os.getenv("OUTLOOK_CLIENT_SECRET", os.getenv("MS_CLIENT_SECRET", os.getenv("AZURE_CLIENT_SECRET", ""))),
        primary_email=os.getenv("LOLA_MEETINGS_PRIMARY_EMAIL", os.getenv("OUTLOOK_USER", os.getenv("MS_USER", ""))),
        internal_domains=_split_list(os.getenv("LOLA_MEETINGS_INTERNAL_DOMAINS", "eldonlandsupply.com")),
        dossier_lead_minutes=int(os.getenv("LOLA_MEETINGS_DOSSIER_LEAD_MINUTES", "20")),
        post_meeting_retry_interval_minutes=int(os.getenv("LOLA_MEETINGS_RETRY_INTERVAL_MINUTES", "5")),
        post_meeting_max_retry_minutes=int(os.getenv("LOLA_MEETINGS_MAX_RETRY_MINUTES", "60")),
        calendar_poll_interval_minutes=int(os.getenv("LOLA_MEETINGS_POLL_INTERVAL_MINUTES", "5")),
        organizer_only=os.getenv("LOLA_MEETINGS_ORGANIZER_ONLY", "false").lower() == "true",
        include_meeting_chat=os.getenv("LOLA_MEETINGS_INCLUDE_CHAT", "false").lower() == "true",
        include_shared_files=os.getenv("LOLA_MEETINGS_INCLUDE_FILES", "false").lower() == "true",
        send_dossier_to_internal_attendees=os.getenv("LOLA_MEETINGS_DOSSIER_INTERNAL", "true").lower() == "true",
        default_followup_mode=os.getenv("LOLA_MEETINGS_FOLLOWUP_MODE", "draft_only"),
        skip_declined=os.getenv("LOLA_MEETINGS_SKIP_DECLINED", "true").lower() == "true",
        allowed_categories=_split_list(os.getenv("LOLA_MEETINGS_ALLOWED_CATEGORIES", "")),
        blocked_categories=_split_list(os.getenv("LOLA_MEETINGS_BLOCKED_CATEGORIES", "")),
        attio_api_key=os.getenv("ATTIO_API_KEY", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "xai"),
        chat_model=os.getenv("OPENCLAW_CHAT_MODEL", "grok-3-mini"),
    )

    if enabled:
        _validate(cfg)

    _config = cfg
    return _config


def _split_list(val: str) -> list[str]:
    return [x.strip() for x in val.split(",") if x.strip()]


def _validate(cfg: MeetingOpsConfig) -> None:
    missing = []
    if not cfg.tenant_id:
        missing.append("OUTLOOK_TENANT_ID (or MS_TENANT_ID / AZURE_TENANT_ID)")
    if not cfg.client_id:
        missing.append("OUTLOOK_CLIENT_ID (or MS_CLIENT_ID / AZURE_CLIENT_ID)")
    if not cfg.client_secret:
        missing.append("OUTLOOK_CLIENT_SECRET (or MS_CLIENT_SECRET / AZURE_CLIENT_SECRET)")
    if not cfg.primary_email:
        missing.append("LOLA_MEETINGS_PRIMARY_EMAIL (or OUTLOOK_USER)")
    if missing:
        msg = (
            "LOLA_MEETINGS_ENABLED=true but required config is missing:\n"
            + "\n".join(f"  • {m}" for m in missing)
        )
        logger.critical(msg)
        raise RuntimeError(msg)
    logger.info(
        "Meeting ops config validated: primary=%s internal_domains=%s lead_minutes=%d",
        cfg.primary_email, cfg.internal_domains, cfg.dossier_lead_minutes,
    )
