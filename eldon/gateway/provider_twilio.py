from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Optional
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import aiohttp

from config import get_config
from normalize import NormalizedMessage, normalize_twilio_payload


async def parse_twilio_request(form_data: dict[str, Any]) -> Optional[NormalizedMessage]:
    return normalize_twilio_payload(form_data)



def verify_twilio_signature(url: str, params: dict[str, Any], signature: str, auth_token: str) -> bool:
    if not signature:
        return False
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    signed = base + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), signed.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


async def send_twilio_message(to: str, text: str) -> bool:
    config = get_config()
    if not config.twilio_account_sid or not config.twilio_auth_token:
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.twilio_account_sid}/Messages.json"
    data: dict[str, str] = {"To": to, "Body": text[:1600]}
    if config.twilio_messaging_service_sid:
        data["MessagingServiceSid"] = config.twilio_messaging_service_sid
    elif config.twilio_from_number:
        data["From"] = config.twilio_from_number
    else:
        return False
    auth = aiohttp.BasicAuth(config.twilio_account_sid, config.twilio_auth_token)
    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
            return response.status in {200, 201}



def twiml_response(message: str) -> str:
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{escape(message)}</Message></Response>"
