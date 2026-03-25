"""
Lola WhatsApp Gateway — with Meeting Ops scheduler wired in.

Replaces apps/lola_whatsapp_gateway/main.py.
Only change: adds asyncio lifespan that starts meeting_ops scheduler
when LOLA_MEETINGS_ENABLED=true.
"""
from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI

from .routes import router

logger = logging.getLogger("lola.gateway")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Start meeting ops scheduler if enabled
    try:
        from lola.meeting_ops.scheduler import start_meeting_ops
        await start_meeting_ops()
    except Exception as e:
        logger.warning("Meeting ops scheduler failed to start: %s", e)
    yield
    # Shutdown
    try:
        from lola.meeting_ops.scheduler import get_scheduler
        get_scheduler().stop()
    except Exception:
        pass


app = FastAPI(title="Lola WhatsApp Gateway", lifespan=lifespan)
app.include_router(router)
