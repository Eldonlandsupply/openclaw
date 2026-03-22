"""WhatsApp Cloud API service — Meta Cloud API path."""

from __future__ import annotations
import hashlib
import hmac
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger("gateway.whatsapp")


def _cfg(key: str, default: str = "") -> str:
    """Read env at call-time, not at import-time."""
    return os.getenv(key, default)


def verify_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    verify_token = _cfg("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    if not verify_token:
        logger.error("WHATSAPP_WEBHOOK_VERIFY_TOKEN is not set")
        return None
    if mode == "subscribe" and token == verify_token:
        return challenge
    return None


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verify Meta X-Hub-Signature-256. Returns True if valid or secret not configured."""
    app_secret = _cfg("WHATSAPP_APP_SECRET")
    if not app_secret:
        logger.warning("WHATSAPP_APP_SECRET not set — skipping signature verification")
        return True
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)


def parse_inbound(payload: dict) -> Optional[dict]:
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        msg = messages[0]
        msg_type = msg.get("type", "")
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "audio":
            text = "[voice message — transcription not yet implemented]"
        else:
            text = f"[{msg_type} message — unsupported type]"
        contacts = value.get("contacts", [{}])
        profile = (contacts[0] if contacts else {}).get("profile", {})
        sender_raw = msg.get("from", "")
        sender_phone = sender_raw if sender_raw.startswith("+") else f"+{sender_raw}"
        return {
            "message_id": msg.get("id", ""),
            "sender_phone": sender_phone,
            "sender_display": profile.get("name", sender_phone),
            "thread_id": sender_phone,
            "text": text,
            "timestamp": msg.get("timestamp", ""),
            "msg_type": msg_type,
        }
    except (KeyError, IndexError, TypeError) as e:
        logger.warning("parse_inbound failed: %s", e)
        return None


async def send_message(to_phone: str, text: str) -> bool:
    phone_number_id = _cfg("WHATSAPP_PHONE_NUMBER_ID")
    access_token = _cfg("WHATSAPP_ACCESS_TOKEN")
    api_version = _cfg("WHATSAPP_API_VERSION", "v19.0")
    if not phone_number_id or not access_token:
        logger.error("WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN not set")
        return False
    text = text[:4096]
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("WhatsApp send failed %s: %s", resp.status, body[:200])
                    return False
                return True
    except Exception as e:
        logger.error("WhatsApp send exception: %s", e)
        return False
