from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from agents.lola.agent import handle_message
from auth import verify_request, verify_sender_allowed
from config import get_config
from dedupe import is_duplicate
from provider_meta import parse_meta_request, send_meta_message, verify_meta_webhook
from provider_twilio import parse_twilio_request, send_twilio_message, twiml_response

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "lola-whatsapp-gateway"}


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready", "provider": get_config().provider}


@router.get("/webhook")
async def verify_webhook(request: Request) -> Response:
    challenge = verify_meta_webhook(
        request.query_params.get("hub.mode", ""),
        request.query_params.get("hub.verify_token", ""),
        request.query_params.get("hub.challenge", ""),
    )
    if challenge is None:
        raise HTTPException(status_code=403, detail="Verification failed")
    return PlainTextResponse(challenge)


@router.post("/webhook")
async def webhook(request: Request) -> Response:
    provider = _resolve_provider(request)
    raw_body = await request.body()
    await verify_request(request, raw_body, provider)

    if provider == "meta":
        payload = await request.json()
        message = await parse_meta_request(payload)
        if not message:
            return JSONResponse({"ok": True, "ignored": True})
        verify_sender_allowed(message.sender)
        if is_duplicate(message.message_id):
            return JSONResponse({"ok": True, "duplicate": True})
        reply = await handle_message(message)
        if reply:
            await send_meta_message(message.sender, reply)
        return JSONResponse({"ok": True})

    form = dict(await request.form())
    message = await parse_twilio_request(form)
    if not message:
        return Response(content=twiml_response("ignored"), media_type="application/xml")
    verify_sender_allowed(message.sender)
    if is_duplicate(message.message_id):
        return Response(content=twiml_response("duplicate"), media_type="application/xml")
    reply = await handle_message(message)
    if reply:
        await send_twilio_message(message.sender, reply)
        return Response(content=twiml_response(reply), media_type="application/xml")
    return Response(content=twiml_response("ok"), media_type="application/xml")



def _resolve_provider(request: Request) -> str:
    configured = get_config().provider
    if configured in {"meta", "twilio"}:
        return configured
    if request.headers.get("X-Twilio-Signature"):
        return "twilio"
    if request.headers.get("X-Hub-Signature-256") or "hub.mode" in request.query_params:
        return "meta"
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/x-www-form-urlencoded"):
        return "twilio"
    return "meta"
