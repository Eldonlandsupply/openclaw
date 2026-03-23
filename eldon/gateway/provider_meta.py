from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

import aiohttp

from config import get_config
from normalize import NormalizedMessage, normalize_meta_payload


async def parse_meta_request(payload: dict[str, Any]) -> Optional[NormalizedMessage]:
    return normalize_meta_payload(payload)



def verify_meta_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    config = get_config()
    if mode == "subscribe" and config.meta_verify_token and token == config.meta_verify_token:
        return challenge
    return None



def verify_meta_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


async def send_meta_message(to: str, text: str) -> bool:
    config = get_config()
    if not config.meta_phone_number_id or not config.meta_access_token:
        return False
    url = f"https://graph.facebook.com/{config.meta_api_version}/{config.meta_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text[:4096]},
    }
    headers = {
        "Authorization": f"Bearer {config.meta_access_token}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
            return response.status == 200
