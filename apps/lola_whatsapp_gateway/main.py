from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

LOLA_SYSTEM_PROMPT = (
    "You are LOLA, the executive assistant and operating coordinator for Matthew Tynski. "
    "Your role is active execution, follow-through, prioritization, and coordination. "
    "Be direct, concise, and practical. Reduce noise, protect time, close loops. "
    "Fail loudly when blocked or missing context. "
    "For every task respond with: 1.Objective 2.What I checked 3.What I did "
    "4.Waiting on approval 5.Risks/blockers 6.Next actions"
)

AZURE_TENANT_ID     = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID     = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
OUTLOOK_USER        = os.getenv("OUTLOOK_USER", "tynski@eldonlandsupply.com")
LLM_BASE_URL        = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY         = os.getenv("OPENROUTER_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_MODEL           = os.getenv("LOLA_MODEL", "openai/gpt-4o-mini")
ALLOWED_NUMBERS     = {
    x.strip()
    for x in os.getenv("LOLA_ALLOWED_NUMBERS", "17087525462").split(",")
    if x.strip()
}

log = logging.getLogger("lola")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = FastAPI(title="Lola Executive Assistant")

_graph_token: dict = {}


async def get_graph_token() -> str:
    global _graph_token
    import time
    if _graph_token.get("expires_at", 0) > time.time() + 60:
        return _graph_token["access_token"]
    url = "https://login.microsoftonline.com/" + AZURE_TENANT_ID + "/oauth2/v2.0/token"
    async with httpx.AsyncClient() as c:
        r = await c.post(url, data={
            "client_id": AZURE_CLIENT_ID,
            "client_secret": AZURE_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        })
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError("Graph token error: " + str(data))
    _graph_token = {
        "access_token": data["access_token"],
        "expires_at": time.time() + data["expires_in"],
    }
    return _graph_token["access_token"]


async def graph_get(path: str) -> dict:
    token = await get_graph_token()
    async with httpx.AsyncClient() as c:
        r = await c.get(
            "https://graph.microsoft.com/v1.0" + path,
            headers={"Authorization": "Bearer " + token},
        )
    return r.json()


async def get_inbox_summary(top: int = 10) -> str:
    try:
        path = (
            "/users/" + OUTLOOK_USER
            + "/mailFolders/Inbox/messages?$top=" + str(top)
            + "&$select=subject,from,receivedDateTime,isRead"
            + "&$orderby=receivedDateTime desc"
        )
        data = await graph_get(path)
        msgs = data.get("value", [])
        if not msgs:
            return "Inbox: no messages found."
        lines = ["Recent inbox:"]
        for m in msgs:
            read = "" if m.get("isRead") else "[UNREAD] "
            sender = m.get("from", {}).get("emailAddress", {}).get("address", "?")
            subject = m.get("subject", "(no subject)")
            date = m.get("receivedDateTime", "")[:10]
            lines.append("  " + read + subject + " | from: " + sender + " | " + date)
        return "\n".join(lines)
    except Exception as e:
        return "Inbox fetch error: " + str(e)


async def get_calendar_summary(top: int = 5) -> str:
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        path = (
            "/users/" + OUTLOOK_USER
            + "/calendarView?startDateTime=" + now
            + "&endDateTime=2099-01-01T00:00:00Z"
            + "&$top=" + str(top)
            + "&$select=subject,start,end"
        )
        data = await graph_get(path)
        events = data.get("value", [])
        if not events:
            return "Calendar: no upcoming events."
        lines = ["Upcoming events:"]
        for e in events:
            start = e.get("start", {}).get("dateTime", "?")[:16]
            subject = e.get("subject", "(no subject)")
            lines.append("  " + subject + " | " + start)
        return "\n".join(lines)
    except Exception as e:
        return "Calendar fetch error: " + str(e)


async def lola_respond(user_message: str, extra_context: str = "") -> str:
    system = LOLA_SYSTEM_PROMPT
    if extra_context:
        system = system + "\n\nCURRENT CONTEXT:\n" + extra_context
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            LLM_BASE_URL + "/chat/completions",
            headers={
                "Authorization": "Bearer " + LLM_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 1000,
            },
        )
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return "LLM error: " + str(data)


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok", "service": "lola", "outlook_user": OUTLOOK_USER})


@app.get("/inbox")
async def inbox():
    return PlainTextResponse(await get_inbox_summary())


@app.get("/calendar")
async def calendar():
    return PlainTextResponse(await get_calendar_summary())


@app.get("/briefing")
async def briefing():
    inbox_ctx, cal_ctx = await asyncio.gather(get_inbox_summary(15), get_calendar_summary(5))
    reply = await lola_respond(
        "Give me a full morning executive briefing.",
        extra_context=inbox_ctx + "\n\n" + cal_ctx,
    )
    return PlainTextResponse(reply)


@app.get("/webhook")
async def webhook_verify(request: Request):
    return PlainTextResponse("ok")


@app.post("/webhook")
async def webhook(request: Request):
    form = await request.form()
    from_number = form.get("From", "").replace("whatsapp:", "")
    body = form.get("Body", "").strip()
    if from_number not in ALLOWED_NUMBERS:
        raise HTTPException(status_code=403, detail="sender not allowed")
    log.info("Lola inbound from %s: %s", from_number, body[:80])
    inbox_ctx, cal_ctx = await asyncio.gather(get_inbox_summary(10), get_calendar_summary(5))
    reply = await lola_respond(body, extra_context=inbox_ctx + "\n\n" + cal_ctx)
    xml_open = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>'
    xml_close = '</Message></Response>'
    return PlainTextResponse(xml_open + reply + xml_close, media_type="text/xml")


@app.post("/command")
async def command(request: Request):
    body = await request.json()
    msg = body.get("message", "")
    if not msg:
        raise HTTPException(status_code=400, detail="message required")
    inbox_ctx, cal_ctx = await asyncio.gather(get_inbox_summary(10), get_calendar_summary(5))
    reply = await lola_respond(msg, extra_context=inbox_ctx + "\n\n" + cal_ctx)
    return {"reply": reply}
