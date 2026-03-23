from __future__ import annotations

from fastapi import HTTPException, Request, status

from config import get_config
from provider_meta import verify_meta_signature
from provider_twilio import verify_twilio_signature


async def verify_request(request: Request, raw_body: bytes, provider: str) -> None:
    config = get_config()
    if provider == "meta" and config.meta_app_secret:
        if not verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256", ""), config.meta_app_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Meta signature")
    if provider == "twilio" and config.twilio_auth_token:
        form = await request.form()
        if not verify_twilio_signature(str(request.url), dict(form), request.headers.get("X-Twilio-Signature", ""), config.twilio_auth_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Twilio signature")



def verify_sender_allowed(sender: str) -> None:
    allowed = get_config().allowed_senders
    if allowed and sender not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sender not allowed")
