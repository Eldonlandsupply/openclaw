from __future__ import annotations

from app.lola.pipeline import process as process_lola_message
from normalize import NormalizedMessage
from .router import route_message


async def handle_message(message: NormalizedMessage) -> str:
    _ = route_message(message.text)
    return await process_lola_message(
        sender_phone=message.sender,
        thread_id=message.thread_id,
        message_id=message.message_id,
        raw_text=message.text,
        channel="whatsapp",
    )
