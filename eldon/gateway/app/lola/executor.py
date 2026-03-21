"""Lola executor."""

from __future__ import annotations
import os, re
import aiohttp
from .models_import import LolaIntent, RiskTier, LolaRequest
from . import audit, approvals as approval_store, memory as mem_store

_LLM_BASE = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
_LLM_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
_LLM_MODEL = os.getenv("LOLA_LLM_MODEL", os.getenv("LLM_MODEL", "grok-3-mini"))

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.md")


def _load_system_prompt() -> str:
    try:
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are Lola, an executive assistant. Be concise, accurate, and professional."


async def _llm(user_message: str, context: str = "") -> str:
    system = _load_system_prompt()
    if context:
        system += f"\n\n## Context\n{context}"
    payload = {
        "model": _LLM_MODEL,
        "messages": [{"role": "user", "content": user_message}],
        "max_tokens": 600,
        "temperature": 0.3,
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

    if tier == RiskTier.BLOCKED:
        audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                     message_id=req.message_id, intent=intent.value, risk_tier=tier.value,
                     action_taken="blocked", execution_status="blocked",
                     summary="Request blocked by policy.")
        return "That action is outside what I'm authorized to do."

    if intent == LolaIntent.APPROVAL_GRANT:
        return await _handle_approval(req, grant=True)
    if intent == LolaIntent.APPROVAL_DENY:
        return await _handle_approval(req, grant=False)

    if tier == RiskTier.APPROVAL_REQUIRED:
        action_summary = f"{intent.value}: {text[:200]}"
        pending = approval_store.create(
            sender_id=req.sender_id, thread_id=req.thread_id, channel=req.channel,
            intent=intent, action_summary=action_summary, action_payload={"text": text},
        )
        audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                     message_id=req.message_id, intent=intent.value, risk_tier=tier.value,
                     action_taken="queued_approval", execution_status="pending_approval",
                     approval_id=pending.approval_id,
                     summary=f"Approval {pending.approval_id} created.")
        return (
            f"I need your approval before proceeding.\n\n"
            f"*Action:* {action_summary}\n"
            f"*ID:* {pending.approval_id}\n\n"
            f"Reply *APPROVE {pending.approval_id}* to confirm, or *DENY {pending.approval_id}* to cancel.\n"
            f"Expires in 60 minutes."
        )

    facts = mem_store.recall(limit=6)
    context_lines = []
    for f in facts:
        tag = "[assumption]" if f.is_assumption else "[fact]"
        context_lines.append(f"{tag} [{f.fact_type}] {f.subject}: {f.content}")
    context = "\n".join(context_lines)

    draft_prefix = "Draft mode: produce the draft but do not send anything. Label it clearly as a draft." if tier == RiskTier.DRAFT_ONLY else ""
    prompt = f"{draft_prefix}\n\nUser request: {text}" if draft_prefix else text
    reply = await _llm(prompt, context=context)

    if intent in (LolaIntent.MEETING_NOTE, LolaIntent.MEMORY_CAPTURE):
        mem_store.record_fact(
            source_channel=req.channel, source_thread_id=req.thread_id,
            fact_type="meeting" if intent == LolaIntent.MEETING_NOTE else "captured",
            subject="captured note", content=text[:500], audit_source="user_message",
        )

    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=intent.value, risk_tier=tier.value,
                 action_taken="llm_response", execution_status="complete",
                 tools_used=["llm"], summary=reply[:200])
    return reply


async def _handle_approval(req: LolaRequest, grant: bool) -> str:
    m = re.search(r"[A-Z0-9]{8}", req.normalized_text.upper())
    approval_id = m.group(0) if m else None
    if not approval_id:
        pending = approval_store.list_pending(req.sender_id)
        if not pending:
            return "No pending approvals found."
        lines = ["Pending approvals:"]
        for p in pending:
            lines.append(f"- *{p.approval_id}* - {p.action_summary[:80]}")
        lines.append("\nReply *APPROVE <ID>* or *DENY <ID>*.")
        return "\n".join(lines)
    result = approval_store.resolve(approval_id, req.sender_id, grant=grant)
    if result is None:
        return f"Approval *{approval_id}* not found, already decided, or expired."
    verdict = "approved" if grant else "denied"
    audit.record(user=req.sender_id, channel=req.channel, thread_id=req.thread_id,
                 message_id=req.message_id, intent=req.intent.value, risk_tier=req.risk_tier.value,
                 action_taken=f"approval_{verdict}", execution_status=verdict,
                 approval_id=approval_id, approval_result=verdict,
                 summary=f"Approval {approval_id} {verdict}.")
    if grant:
        return f"Approved *{approval_id}*. Proceeding with: {result.action_summary[:120]}\n[Connect provider adapters in v2 to execute.]"
    return f"Denied *{approval_id}*. Action cancelled."
