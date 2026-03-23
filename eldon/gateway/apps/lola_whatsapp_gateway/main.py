from __future__ import annotations

from fastapi import FastAPI

from .routes import router

app = FastAPI(title="Lola WhatsApp Gateway")
app.include_router(router)
