"""Lola pipeline."""

from __future__ import annotations
import os, re
from .classifier import classify
from .dedupe import is_duplicate
from .executor import execute
from . import audit
from .models_import import LolaRequest, LolaIntent, RiskTier

_LOLA_ALLOWED_SENDERS = set(
    s.strip() for s in os.getenv("LOLA_ALLOWED_SENDERS", "").split(",") if s.strip()
)


def _normalize(text: str) -> str:
    return text.strip()


def _is_authorized(sender_phone: str) -> bool:
    if not _LOLA_ALLOWED_SENDERS:
        return False
    return sender_phone in _LOLA_ALLOWED_SENDERS


async def process(sender_phone, thread_id, message_id, raw_text, channel="whatsapp") -> str:
    if message_id and is_duplicate(message_id):
        return ""
    if not _is_authorized(sender_phone):
        audit.record(user=sender_phone, channel=channel, thread_id=thread_id,
                     message_id=message_id, intent="unknown", risk_tier="blocked",
                     action_taken="rejected_auth", execution_status="rejected",
                     summary="Unauthorized sender.")
        return ""
    normalized = _normalize(raw_text)
    if not normalized:
        return ""
    intent, risk_tier, confidence = classify(normalized)
    req = LolaRequest(
        channel=channel, sender_id=sender_phone, sender_phone=sender_phone,
        thread_id=thread_id, message_id=message_id,
        raw_text=raw_text, normalized_text=normalized,
        intent=intent, risk_tier=risk_tier, confidence=confidence,
    )
    return await execute(req)
