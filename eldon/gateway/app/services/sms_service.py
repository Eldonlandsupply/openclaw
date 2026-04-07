"""
SMS service via Twilio.
Sends and parses inbound SMS.
"""

from __future__ import annotations

import os
from typing import Optional


def _account_sid() -> str:
    return os.getenv("TWILIO_ACCOUNT_SID", "")


def _auth_token() -> str:
    return os.getenv("TWILIO_AUTH_TOKEN", "")


def _from_number() -> str:
    return os.getenv("TWILIO_PHONE_NUMBER", "")


def parse_inbound(form_data: dict) -> Optional[dict]:
    """Parse Twilio inbound webhook form payload."""
    sender = form_data.get("From", "")
    body = form_data.get("Body", "")
    message_sid = form_data.get("MessageSid", "")
    if not sender:
        return None
    return {
        "sender_id": sender,
        "sender_display": sender,
        "chat_id": sender,
        "message_id": message_sid,
        "text": body,
        "attachments": [],
    }


async def send_message(to: str, body: str) -> bool:
    """
    Send SMS via Twilio REST API.
    Returns True on success.
    """
    account_sid = _account_sid()
    auth_token = _auth_token()
    from_number = _from_number()
    if not (account_sid and auth_token and from_number):
        return False

    # Truncate SMS
    body = body[:1600]

    try:
        import aiohttp
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {"To": to, "From": from_number, "Body": body}
        auth = aiohttp.BasicAuth(account_sid, auth_token)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, auth=auth, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status in (200, 201)
    except Exception:
        return False


def twilio_twiml_response(body: str) -> str:
    """Return a minimal TwiML response."""
    escaped = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:1500]
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped}</Message></Response>'
