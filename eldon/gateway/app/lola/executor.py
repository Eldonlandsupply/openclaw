"""Lola executor — intent dispatch with Outlook + Attio adapters."""

from __future__ import annotations

import os, re
import aiohttp

from .models_import import LolaIntent, RiskTier, LolaRequest
from . import audit
from .approvals import create as create_approval, resolve as resolve_approval, list_pending
from .memory import recall as mem_recall, record_fact

_LLM_BASE = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
_LLM_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
_LLM_MODEL = os.getenv("LOLA_LLM_MODEL", os.getenv("LLM_MODEL", "grok-3-mini"))
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.md")


def _load_prompt() -> str:
    try:
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are Lola, an executive assistant. Be concise and professional."


async def _llm(user_message: str, context: str = "") -> str:
    system = _load_prompt()
    if context:
        system += f"\n\n## Context\n{context}"
    payload = {
        "model": _LLM_MODEL,
        "messages": [{"role": "user", "content": user_message}],
        "max_tokens": 600, "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {_LLM_KEY}", "Content-Type": "application/json"}
    if "openrouter" in _LLM_BASE:
        headers["HTTP-Referer"] = "https://eldonlandsupply.com"
        headers["X-Title"] = "Lola Executive Assistant"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_LLM_BASE}/chat/completions", json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[Lola error: {e}]"


async def execute(req: LolaRequest) -> str:
    intent = req.intent
    tier = req.risk_tier
    text = req.normalized_text

    # ── BLOCKED ───────────────────────────────────────────────────────────
    if tier == RiskTier.BLOCKED:
        audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                     message_id=req.message_id, intent=intent.value, risk_tier=tier.value,
                     action_taken="blocked", execution_status="blocked",
                     summary="Request blocked by policy.")
        return "That action is outside what I'm authorized to do."

    # ── APPROVAL FLOW ─────────────────────────────────────────────────────
    if intent == LolaIntent.APPROVAL_GRANT:
        return await _handle_approval(req, grant=True)
    if intent == LolaIntent.APPROVAL_DENY:
        return await _handle_approval(req, grant=False)

    # ── NEEDS APPROVAL — queue ────────────────────────────────────────────
    if tier == RiskTier.APPROVAL_REQUIRED:
        summary = f"{intent.value}: {text[:200]}"
        pending = create_approval(
            sender_id=req.sender_id, thread_id=req.thread_id, channel=req.channel,
            intent=intent, action_summary=summary, action_payload={"text": text},
        )
        audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                     message_id=req.message_id, intent=intent.value, risk_tier=tier.value,
                     action_taken="queued_approval", execution_status="pending_approval",
                     approval_id=pending.approval_id, summary=f"Approval {pending.approval_id} created.")
        return (
            f"I need your approval before proceeding.\n\n"
            f"*Action:* {summary}\n"
            f"*ID:* {pending.approval_id}\n\n"
            f"Reply *APPROVE {pending.approval_id}* to confirm, or *DENY {pending.approval_id}* to cancel.\n"
            f"Expires in 60 minutes."
        )

    # ── READ — use real adapters where available ──────────────────────────
    if intent == LolaIntent.CALENDAR_QUERY:
        return await _calendar_query(req)
    if intent == LolaIntent.EMAIL_QUERY:
        return await _inbox_query(req)
    if intent == LolaIntent.STATUS_REQUEST:
        return await _status(req)
    if intent == LolaIntent.BRIEFING_REQUEST:
        return await _briefing(req)

    # ── CRM READ (auto, no approval) ──────────────────────────────────────
    if "attio" in text.lower() or "contact" in text.lower() or "company" in text.lower():
        if intent in (LolaIntent.TASK_LIST, LolaIntent.MEMORY_RECALL, LolaIntent.CHAT):
            return await _crm_search(req)

    # ── DRAFT / GENERAL LLM ──────────────────────────────────────────────
    facts = mem_recall(limit=6)
    context_lines = []
    for f in facts:
        tag = "[assumption]" if f.is_assumption else "[fact]"
        context_lines.append(f"{tag} [{f.fact_type}] {f.subject}: {f.content}")
    context = "\n".join(context_lines)

    draft_prefix = ""
    if tier == RiskTier.DRAFT_ONLY:
        draft_prefix = "Draft mode: produce the draft clearly labeled. Do not send anything."
    prompt = f"{draft_prefix}\n\nUser request: {text}" if draft_prefix else text
    reply = await _llm(prompt, context=context)

    if intent in (LolaIntent.MEETING_NOTE, LolaIntent.MEMORY_CAPTURE):
        record_fact(source_channel=req.channel, source_thread_id=req.thread_id,
                    fact_type="meeting" if intent == LolaIntent.MEETING_NOTE else "captured",
                    subject="captured note", content=text[:500], audit_source="user_message")

    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=intent.value, risk_tier=tier.value,
                 action_taken="llm_response", execution_status="complete",
                 tools_used=["llm"], summary=reply[:200])
    return reply


async def _calendar_query(req: LolaRequest) -> str:
    from .adapters.outlook import get_calendar_today, format_calendar_for_lola
    events = await get_calendar_today()
    reply = format_calendar_for_lola(events)
    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=req.intent.value, risk_tier=req.risk_tier.value,
                 action_taken="calendar_read", execution_status="complete",
                 tools_used=["outlook_calendar"], summary=f"{len(events)} events returned")
    return reply


async def _inbox_query(req: LolaRequest) -> str:
    from .adapters.outlook import get_inbox_unread, format_inbox_for_lola
    messages = await get_inbox_unread(limit=10)
    reply = format_inbox_for_lola(messages)
    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=req.intent.value, risk_tier=req.risk_tier.value,
                 action_taken="inbox_read", execution_status="complete",
                 tools_used=["outlook_inbox"], summary=f"{len(messages)} messages returned")
    return reply


async def _status(req: LolaRequest) -> str:
    from . import db
    s = db.stats()
    reply = (
        f"*Lola status*\n"
        f"• Memory facts: {s['total_facts']}\n"
        f"• Pending approvals: {s['pending_approvals']}\n"
        f"• Audit records: {s['total_audit_records']}\n"
        f"• Last action: {s.get('last_action', 'none')} at {s.get('last_action_at', 'n/a')[:16] if s.get('last_action_at') else 'n/a'}"
    )
    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=req.intent.value, risk_tier=req.risk_tier.value,
                 action_taken="status_read", execution_status="complete", summary="status returned")
    return reply


async def _briefing(req: LolaRequest) -> str:
    from .adapters.outlook import get_calendar_today, get_inbox_unread, format_calendar_for_lola, format_inbox_for_lola
    from . import db
    events = await get_calendar_today()
    messages = await get_inbox_unread(limit=5)
    s = db.stats()
    cal_section = format_calendar_for_lola(events)
    inbox_section = format_inbox_for_lola(messages)
    pending = s["pending_approvals"]
    brief = (
        f"*Morning Brief*\n\n"
        f"{cal_section}\n\n"
        f"{inbox_section}"
    )
    if pending:
        brief += f"\n\n*Pending approvals:* {pending} — reply STATUS for list"
    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=req.intent.value, risk_tier=req.risk_tier.value,
                 action_taken="briefing_generated", execution_status="complete",
                 tools_used=["outlook_calendar", "outlook_inbox"], summary="briefing sent")
    return brief


async def _crm_search(req: LolaRequest) -> str:
    from .adapters.attio import search_contacts, search_companies, format_contacts_for_lola
    text = req.normalized_text
    # Extract query: strip common prefixes
    import re
    query = re.sub(r"(?i)(find|search|look up|attio|contact|company|who is|what is)\s*", "", text).strip()
    if not query:
        return "What would you like me to search in Attio?"
    results = await search_contacts(query, limit=5)
    reply = format_contacts_for_lola(results)
    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=req.intent.value, risk_tier=req.risk_tier.value,
                 action_taken="crm_search", execution_status="complete",
                 tools_used=["attio"], summary=f"CRM search: {query[:60]}")
    return reply


async def _handle_approval(req: LolaRequest, grant: bool) -> str:
    m = re.search(r"[A-Z0-9]{8}", req.normalized_text.upper())
    approval_id = m.group(0) if m else None
    if not approval_id:
        pending = list_pending(req.sender_id)
        if not pending:
            return "No pending approvals found."
        lines = ["Pending approvals:"]
        for p in pending:
            lines.append(f"- *{p.approval_id}* - {p.action_summary[:80]}")
        lines.append("\nReply *APPROVE <ID>* or *DENY <ID>*.")
        return "\n".join(lines)
    result = resolve_approval(approval_id, req.sender_id, grant=grant)
    if result is None:
        return f"Approval *{approval_id}* not found, already decided, or expired."
    verdict = "approved" if grant else "denied"
    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=req.intent.value, risk_tier=req.risk_tier.value,
                 action_taken=f"approval_{verdict}", execution_status=verdict,
                 approval_id=approval_id, approval_result=verdict,
                 summary=f"Approval {approval_id} {verdict}.")
    if grant:
        return f"Approved *{approval_id}*. Action: {result.action_summary[:120]}"
    return f"Denied *{approval_id}*. Cancelled."
