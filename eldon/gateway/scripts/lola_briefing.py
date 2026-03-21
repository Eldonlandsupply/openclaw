#!/usr/bin/env python3
"""
Lola daily briefing script.
Generates a morning brief and pushes it to Matthew via WhatsApp.
Run via systemd timer lola-briefing.timer at 07:00 daily.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Ensure gateway app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("lola-briefing")


async def main() -> None:
    phone = os.getenv("LOLA_ALLOWED_SENDERS", "").split(",")[0].strip()
    if not phone:
        logger.error("LOLA_ALLOWED_SENDERS not set — cannot push briefing")
        return

    from app.lola.adapters.outlook import get_calendar_today, get_inbox_unread
    from app.lola.adapters.outlook import format_calendar_for_lola, format_inbox_for_lola
    from app.lola import db
    from app.services.whatsapp_service import send_message

    try:
        events = await get_calendar_today()
        messages = await get_inbox_unread(limit=5)
        stats = db.stats()
        cal = format_calendar_for_lola(events)
        inbox = format_inbox_for_lola(messages)
        pending = stats["pending_approvals"]

        brief = f"*Good morning. Morning Brief:*\n\n{cal}\n\n{inbox}"
        if pending:
            brief += f"\n\n*Pending approvals:* {pending}"

        ok = await send_message(phone, brief)
        if ok:
            logger.info("Morning brief sent to %s", phone)
        else:
            logger.error("Failed to send morning brief to %s", phone)
    except Exception as e:
        logger.exception("Briefing script error: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
