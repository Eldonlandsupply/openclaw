"""
OpenClaw Gateway.
GET  /health
POST /webhooks/telegram
POST /webhooks/sms
GET  /webhooks/lola/whatsapp    (Meta verification)
POST /webhooks/lola/whatsapp    (inbound messages)
GET  /lola/status               (dashboard panel)
GET  /lola/approvals            (pending approvals)
GET  /lola/audit                (recent audit log)
"""

from __future__ import annotations

import hmac, json, logging, os
from aiohttp import web

from .gateway.models import AttachmentMeta, Channel, GatewayRequest
from .gateway.pipeline import process
from .services import telegram_service, sms_service, whatsapp_service
from .lola.pipeline import process as lola_process

logger = logging.getLogger("gateway")

_TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
_ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "true").lower() == "true"
_ENABLE_SMS = os.getenv("ENABLE_SMS", "false").lower() == "true"
_ENABLE_LOLA_WHATSAPP = os.getenv("ENABLE_LOLA_WHATSAPP", "false").lower() == "true"
_DASHBOARD_TOKEN = os.getenv("LOLA_DASHBOARD_TOKEN", "")


def _verify_dashboard(request: web.Request) -> bool:
    if not _DASHBOARD_TOKEN:
        return True  # if not configured, open (warn in logs)
    return request.headers.get("X-Dashboard-Token", "") == _DASHBOARD_TOKEN


async def health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok", "service": "openclaw-gateway",
        "lola_whatsapp": _ENABLE_LOLA_WHATSAPP,
        "telegram": _ENABLE_TELEGRAM, "sms": _ENABLE_SMS,
    })


def _verify_telegram_secret(request: web.Request) -> bool:
    if not _TELEGRAM_WEBHOOK_SECRET:
        return True
    return hmac.compare_digest(
        request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""),
        _TELEGRAM_WEBHOOK_SECRET,
    )


async def telegram_webhook(request: web.Request) -> web.Response:
    if not _ENABLE_TELEGRAM:
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
    if not _ENABLE_SMS:
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
    if not _ENABLE_LOLA_WHATSAPP:
        return web.Response(status=404)
    mode = request.rel_url.query.get("hub.mode", "")
    token = request.rel_url.query.get("hub.verify_token", "")
    challenge = request.rel_url.query.get("hub.challenge", "")
    result = whatsapp_service.verify_webhook(mode, token, challenge)
    if result is None:
        return web.Response(status=403, text="Forbidden")
    return web.Response(status=200, text=result)


async def lola_whatsapp_webhook(request: web.Request) -> web.Response:
    if not _ENABLE_LOLA_WHATSAPP:
        return web.Response(status=404)
    body = await request.read()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return web.json_response({"error": "Bad JSON"}, status=400)
    normalized = whatsapp_service.parse_inbound(payload)
    if not normalized:
        return web.json_response({"ok": True})
    reply = await lola_process(
        sender_phone=normalized["sender_phone"], thread_id=normalized["thread_id"],
        message_id=normalized["message_id"], raw_text=normalized["text"], channel="whatsapp",
    )
    if reply:
        await whatsapp_service.send_message(normalized["sender_phone"], reply)
    return web.json_response({"ok": True})


# ── Dashboard endpoints ────────────────────────────────────────────────────

async def lola_dashboard_status(request: web.Request) -> web.Response:
    """GET /lola/status — Lola agent health for dashboard panel."""
    if not _verify_dashboard(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        from .lola import db
        stats = db.stats()
        return web.json_response({
            "agent": "lola",
            "whatsapp_enabled": _ENABLE_LOLA_WHATSAPP,
            "db_path": str(db._DB_PATH),
            **stats,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def lola_dashboard_approvals(request: web.Request) -> web.Response:
    """GET /lola/approvals — all pending approvals."""
    if not _verify_dashboard(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        from .lola import db
        sender = request.rel_url.query.get("sender", "")
        if sender:
            rows = db.get_pending_approvals(sender)
        else:
            # All pending
            c = db._get_conn()
            from datetime import datetime, timezone
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
    """GET /lola/audit — recent audit records."""
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
    port = int(os.getenv("GATEWAY_PORT", "8443"))
    web.run_app(create_app(), port=port)
