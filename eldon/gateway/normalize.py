from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class NormalizedMessage:
    provider: str
    message_id: str
    sender: str
    thread_id: str
    text: str
    sender_name: str = ""
    raw_payload: dict[str, Any] | None = None


def normalize_meta_payload(payload: dict[str, Any]) -> Optional[NormalizedMessage]:
    try:
        entry = payload.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0]
        value = change.get("value", {})
        message = value.get("messages", [{}])[0]
        if message.get("type") != "text":
            return None
        contact = value.get("contacts", [{}])[0]
        sender = message.get("from", "")
        text = message.get("text", {}).get("body", "").strip()
        if not sender or not text:
            return None
        return NormalizedMessage(
            provider="meta",
            message_id=message.get("id", ""),
            sender=sender,
            thread_id=sender,
            text=text,
            sender_name=contact.get("profile", {}).get("name", ""),
            raw_payload=payload,
        )
    except (AttributeError, IndexError, TypeError):
        return None



def normalize_twilio_payload(payload: dict[str, Any]) -> Optional[NormalizedMessage]:
    sender = str(payload.get("From", "")).strip()
    body = str(payload.get("Body", "")).strip()
    if not sender or not body:
        return None
    message_id = str(payload.get("MessageSid", payload.get("SmsSid", ""))).strip()
    return NormalizedMessage(
        provider="twilio",
        message_id=message_id,
        sender=sender,
        thread_id=sender,
        text=body,
        sender_name=str(payload.get("ProfileName", "")).strip(),
        raw_payload=dict(payload),
    )
