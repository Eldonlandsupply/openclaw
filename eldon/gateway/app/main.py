"""
OpenClaw Gateway.
GET  /healthz              (alias)
GET  /health
POST /webhooks/telegram
POST /webhooks/sms
GET  /webhooks/lola/whatsapp    (Meta verification)
POST /webhooks/lola/whatsapp    (inbound messages)
GET  /lola/status
GET  /lola/approvals
GET  /lola/audit
"""

from __future__ import annotations

import hmac, json, logging, os
from aiohttp import web

from .gateway.models import AttachmentMeta, Channel, GatewayRequest
from .gateway.pipeline import process
from .services import telegram_service, sms_service, whatsapp_service
from .lola.pipeline import process as lola_process

logger = logging.getLogger("gateway")

def _env_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() == "true"


def _telegram_webhook_secret() -> str:
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


def _enable_telegram() -> bool:
    return _env_bool("ENABLE_TELEGRAM", "true")


def _enable_sms() -> bool:
    return _env_bool("ENABLE_SMS", "false")


def _enable_lola_whatsapp() -> bool:
    return _env_bool("ENABLE_LOLA_WHATSAPP", "false")


def _dashboard_token() -> str:
    return os.getenv("LOLA_DASHBOARD_TOKEN", "")


def _verify_dashboard(request: web.Request) -> bool:
    token = _dashboard_token()
    if not token:
        return True
    return request.headers.get("X-Dashboard-Token", "") == token


async def health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok", "service": "openclaw-gateway",
        "lola_whatsapp": _enable_lola_whatsapp(),
        "telegram": _enable_telegram(), "sms": _enable_sms(),
    })


def _verify_telegram_secret(request: web.Request) -> bool:
    secret = _telegram_webhook_secret()
    if not secret:
        return True
    return hmac.compare_digest(
        request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""),
        secret,
    )


async def telegram_webhook(request: web.Request) -> web.Response:
    if not _enable_telegram():
        return web.json_response({"error": "Telegram disabled"}, status=403)
    body = await request.read()
    if not _verify_telegram_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        update = json.loads(body)
    except json.JSONDecodeError:
        return web.json_response({"error": "Bad JSON"}, status=400)
    normalized = telegram_service.normalize_update(update)
    if not normalized:
        return web.json_response({"ok": True})
    req = GatewayRequest(
        channel=Channel.TELEGRAM,
        sender_id=normalized["sender_id"], sender_display=normalized["sender_display"],
        chat_id=normalized["chat_id"], message_id=normalized["message_id"],
        raw_text=normalized["text"],
        attachments=[AttachmentMeta(**a) for a in normalized["attachments"]],
    )
    reply, _ = await process(req)
    if reply:
        await telegram_service.send_message(req.chat_id, reply)
    return web.json_response({"ok": True})


async def sms_webhook(request: web.Request) -> web.Response:
    if not _enable_sms():
        return web.Response(text=sms_service.twilio_twiml_response("SMS disabled."), content_type="text/xml")
    form_data = await request.post()
    normalized = sms_service.parse_inbound(dict(form_data))
    if not normalized:
        return web.Response(text=sms_service.twilio_twiml_response("Parse error."), content_type="text/xml")
    req = GatewayRequest(
        channel=Channel.SMS, sender_id=normalized["sender_id"],
        sender_display=normalized["sender_display"], chat_id=normalized["chat_id"],
        message_id=normalized["message_id"], raw_text=normalized["text"],
    )
    reply, _ = await process(req)
    return web.Response(text=sms_service.twilio_twiml_response(reply or "OK"), content_type="text/xml")


async def lola_whatsapp_verify(request: web.Request) -> web.Response:
    if not _enable_lola_whatsapp():
        return web.Response(status=404)
    mode = request.rel_url.query.get("hub.mode", "")
    token = request.rel_url.query.get("hub.verify_token", "")
    challenge = request.rel_url.query.get("hub.challenge", "")
    result = whatsapp_service.verify_webhook(mode, token, challenge)
    if result is None:
        return web.Response(status=403, text="Forbidden")
    return web.Response(status=200, text=result)


def _is_status_notification(payload: dict) -> bool:
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        return "statuses" in value and "messages" not in value
    except (KeyError, IndexError, TypeError):
        return False


async def lola_whatsapp_webhook(request: web.Request) -> web.Response:
    if not _enable_lola_whatsapp():
        return web.Response(status=404)
    body = await request.read()

    sig = request.headers.get("X-Hub-Signature-256", "")
    if not whatsapp_service.verify_signature(body, sig):
        logger.warning("WhatsApp webhook signature mismatch — rejected")
        return web.json_response({"error": "Invalid signature"}, status=401)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return web.json_response({"error": "Bad JSON"}, status=400)

    if _is_status_notification(payload):
        return web.json_response({"ok": True})

    normalized = whatsapp_service.parse_inbound(payload)
    if not normalized:
        return web.json_response({"ok": True})

    logger.info(
        "WhatsApp inbound from=%s msg_id=%s type=%s",
        normalized["sender_phone"], normalized["message_id"], normalized.get("msg_type"),
    )

    try:
        reply = await lola_process(
            sender_phone=normalized["sender_phone"],
            thread_id=normalized["thread_id"],
            message_id=normalized["message_id"],
            raw_text=normalized["text"],
            channel="whatsapp",
        )
    except Exception as e:
        logger.exception("lola_process raised: %s", e)
        return web.json_response({"ok": True})

    if reply:
        sent = await whatsapp_service.send_message(normalized["sender_phone"], reply)
        if not sent:
            logger.error("Failed to send WhatsApp reply to %s", normalized["sender_phone"])

    return web.json_response({"ok": True})


async def lola_dashboard_status(request: web.Request) -> web.Response:
    if not _verify_dashboard(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        from .lola import db
        stats = db.stats()
        return web.json_response({"agent": "lola", "whatsapp_enabled": _enable_lola_whatsapp(), "db_path": str(db._DB_PATH), **stats})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def lola_dashboard_approvals(request: web.Request) -> web.Response:
    if not _verify_dashboard(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        from .lola import db
        from datetime import datetime, timezone
        sender = request.rel_url.query.get("sender", "")
        if sender:
            rows = db.get_pending_approvals(sender)
        else:
            c = db._get_conn()
            now = datetime.now(timezone.utc).isoformat()
            cols = [r[1] for r in c.execute("PRAGMA table_info(approvals)").fetchall()]
            raw = c.execute(
                "SELECT * FROM approvals WHERE status='pending' AND (expires_at IS NULL OR expires_at > ?) ORDER BY created_at DESC LIMIT 50",
                (now,)
            ).fetchall()
            rows = [dict(zip(cols, r)) for r in raw]
        return web.json_response({"approvals": rows})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def lola_dashboard_audit(request: web.Request) -> web.Response:
    if not _verify_dashboard(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        from .lola import db
        limit = int(request.rel_url.query.get("limit", "20"))
        rows = db.recent_audit(limit=min(limit, 100))
        return web.json_response({"records": rows})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/healthz", health)
    app.router.add_post("/webhooks/telegram", telegram_webhook)
    app.router.add_post("/webhooks/sms", sms_webhook)
    app.router.add_get("/webhooks/lola/whatsapp", lola_whatsapp_verify)
    app.router.add_post("/webhooks/lola/whatsapp", lola_whatsapp_webhook)
    app.router.add_get("/lola/status", lola_dashboard_status)
    app.router.add_get("/lola/approvals", lola_dashboard_approvals)
    app.router.add_get("/lola/audit", lola_dashboard_audit)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    port = int(os.getenv("GATEWAY_PORT", "8000"))
    web.run_app(create_app(), port=port)
