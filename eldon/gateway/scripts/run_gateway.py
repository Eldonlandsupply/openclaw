#!/usr/bin/env python3
"""
Run the OpenClaw Lola WhatsApp gateway.
Usage: python scripts/run_gateway.py
"""

import logging
import os
import sys
from pathlib import Path

# load_dotenv MUST run before any app module imports that read env at module level.
from dotenv import load_dotenv

_GATEWAY_ROOT = Path(__file__).parent.parent
_ENV_PATH = _GATEWAY_ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
else:
    _PI_ENV = Path("/opt/openclaw/.env")
    if _PI_ENV.exists():
        load_dotenv(_PI_ENV)

sys.path.insert(0, str(_GATEWAY_ROOT))
from app.main import create_app  # noqa: E402 — must come after load_dotenv

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

if __name__ == "__main__":
    from aiohttp import web

    port = int(os.getenv("GATEWAY_PORT", "8000"))
    host = os.getenv("GATEWAY_HOST", "0.0.0.0")
    lola_enabled = os.getenv("ENABLE_LOLA_WHATSAPP", "false").lower() == "true"

    print(f"Starting OpenClaw gateway on {host}:{port}")
    print(f"  Telegram : {os.getenv('ENABLE_TELEGRAM', 'true')}")
    print(f"  SMS      : {os.getenv('ENABLE_SMS', 'false')}")
    print(f"  Lola WA  : {lola_enabled}")
    if lola_enabled:
        print(f"  Allowed  : {os.getenv('LOLA_ALLOWED_SENDERS', '(not set)')}")

    web.run_app(create_app(), host=host, port=port)
