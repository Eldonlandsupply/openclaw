"""Lola pipeline."""

from __future__ import annotations
import logging
import os

from .classifier import classify
from .dedupe import is_duplicate
from .executor import execute
from . import audit
from .models_import import LolaRequest, LolaIntent, RiskTier

logger = logging.getLogger("gateway.lola.pipeline")


def _get_allowed_senders() -> set:
    raw = os.getenv("LOLA_ALLOWED_SENDERS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


def _normalize(text: str) -> str:
    return text.strip()


def _is_authorized(sender_phone: str) -> bool:
    allowed = _get_allowed_senders()
    if not allowed:
        logger.error(
            "LOLA_ALLOWED_SENDERS is not set or empty — all senders will be rejected. "
            "Set it in .env to your WhatsApp number in E.164 format, e.g. +15551234567"
        )
        return False
    return sender_phone in allowed


async def process(sender_phone, thread_id, message_id, raw_text, channel="whatsapp") -> str:
    if message_id and is_duplicate(message_id):
        logger.info("Dedupe hit for message_id=%s", message_id)
        return ""

    if not _is_authorized(sender_phone):
        logger.warning("Unauthorized sender %s on %s", sender_phone, channel)
        audit.record(
            user=sender_phone, channel=channel, thread_id=thread_id,
            message_id=message_id, intent="unknown", risk_tier="blocked",
            action_taken="rejected_auth", execution_status="rejected",
            summary="Unauthorized sender.",
        )
        return ""

    normalized = _normalize(raw_text)
    if not normalized:
        return ""

    intent, risk_tier, confidence = classify(normalized)
    logger.info("Classified sender=%s intent=%s risk=%s conf=%.2f",
                sender_phone, intent.value, risk_tier.value, confidence)

    req = LolaRequest(
        channel=channel, sender_id=sender_phone, sender_phone=sender_phone,
        thread_id=thread_id, message_id=message_id,
        raw_text=raw_text, normalized_text=normalized,
        intent=intent, risk_tier=risk_tier, confidence=confidence,
    )
    return await execute(req)
