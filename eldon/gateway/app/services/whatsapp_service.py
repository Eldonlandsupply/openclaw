"""WhatsApp Cloud API service."""

from __future__ import annotations
import os
from typing import Optional
import aiohttp

_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v19.0")
_BASE = f"https://graph.facebook.com/{_API_VERSION}"
_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")


def verify_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    if mode == "subscribe" and token == _VERIFY_TOKEN and _VERIFY_TOKEN:
        return challenge
    return None


def parse_inbound(payload: dict) -> Optional[dict]:
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        msg = messages[0]
        if msg.get("type") != "text":
            return None
        contacts = value.get("contacts", [{}])
        profile = (contacts[0] if contacts else {}).get("profile", {})
        return {
            "message_id": msg.get("id", ""),
            "sender_phone": msg.get("from", ""),
            "sender_display": profile.get("name", ""),
            "thread_id": msg.get("from", ""),
            "text": msg.get("text", {}).get("body", ""),
            "timestamp": msg.get("timestamp", ""),
        }
    except (KeyError, IndexError, TypeError):
        return None


async def send_message(to_phone: str, text: str) -> bool:
    if not _PHONE_NUMBER_ID or not _ACCESS_TOKEN:
        return False
    text = text[:4096]
    url = f"{_BASE}/{_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    headers = {"Authorization": f"Bearer {_ACCESS_TOKEN}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status == 200
    except Exception:
        return False
