"""
Core gateway pipeline.
Orchestrates: auth → dedupe → route → risk → confirm/execute → audit.

Routing decisions and outcomes are emitted as structured log events so
operators can see: inbound message → classified intent → selected route →
selected agent/tool → outcome.
"""

from __future__ import annotations

import logging

from .auth import authenticate, is_duplicate
from .confirmations import get_store
from .models import (
    GatewayRequest, Intent,
    RequestStatus, RiskLevel,
)
from .responses import format_error, format_rejection, format_response, format_fallback_unavailable
from .risk import classify_risk
from .router import route
from ..services import audit_log
from ..services.command_registry import get_registry

logger = logging.getLogger("gateway.pipeline")

# In-memory dedupe set (bounded by restart)
_seen_message_ids: set[str] = set()
_MAX_SEEN = 10_000


def _normalize_text(raw: str) -> str:
    return raw.strip()


def _log_routing(req: GatewayRequest, route_target: str, tool: str, outcome: str) -> None:
    """Emit a structured routing event visible in journald / log aggregators."""
    logger.info(
        "routing_decision",
        extra={
            "event": "routing_decision",
            "channel": req.channel.value,
            "sender_id": req.sender_id,
            "message_id": req.message_id or "",
            "intent": req.intent.value,
            "route_reason": req.route_reason,
            "risk_level": req.risk_level.value,
            "routed_to": route_target,
            "tool": tool,
            "outcome": outcome,
            "request_id": req.request_id,
        },
    )


async def process(req: GatewayRequest) -> tuple[str, GatewayRequest]:
    """
    Run the full pipeline for a GatewayRequest.
    Returns (reply_text, updated_req).
    """
    req.normalized_text = _normalize_text(req.raw_text)

    logger.info(
        "message_received",
        extra={
            "event": "message_received",
            "channel": req.channel.value,
            "sender_id": req.sender_id,
            "message_id": req.message_id or "",
            "text_len": len(req.raw_text),
            "request_id": req.request_id,
        },
    )

    # 1. Dedupe
    if req.message_id:
        if is_duplicate(req, _seen_message_ids):
            return ("", req)  # silently drop duplicate
        if len(_seen_message_ids) < _MAX_SEEN:
            _seen_message_ids.add(req.message_id)

    # 2. Auth
    authenticate(req)
    if not req.authenticated:
        req.status = RequestStatus.REJECTED
        audit_log.record(req, "rejected_auth")
        _log_routing(req, "none", "none", "rejected_auth")
        return (format_rejection("Unauthorized sender"), req)

    req.status = RequestStatus.AUTHENTICATED

    # 3. Route intent
    route(req)

    logger.info(
        "intent_classified",
        extra={
            "event": "intent_classified",
            "channel": req.channel.value,
            "intent": req.intent.value,
            "route_reason": req.route_reason,
            "action_name": req.action_name,
            "request_id": req.request_id,
        },
    )

    # 4. APPROVE flow — before risk classification
    if req.intent == Intent.APPROVE:
        return await _handle_approve(req)

    # 5. REPO_OP and DEV_QUERY — engineering path
    if req.intent in (Intent.REPO_OP, Intent.DEV_QUERY):
        return await _handle_repo_op(req)

    # 6. LLM_FALLBACK — orchestrator path (Lola pipeline)
    if req.intent == Intent.LLM_FALLBACK:
        return await _handle_llm_fallback(req)

    # 7. Risk classification for remaining registry-backed intents
    classify_risk(req)

    # 8. Registry check
    registry = get_registry()
    entry = registry.get(req.action_name)

    if entry is None and req.action_name not in ("unknown", ""):
        req.status = RequestStatus.FAILED
        reply = format_error(f"\'{req.action_name}\' is not a registered command. Type \'help\'.")
        audit_log.record(req, "rejected_unknown_action")
        _log_routing(req, "command_registry", req.action_name, "not_registered")
        return (reply, req)

    # 9. Confirmation gate for HIGH risk
    if req.risk_level == RiskLevel.HIGH:
        return await _require_confirmation(req)

    # 10. Execute registry action
    return await _execute(req)


async def _handle_repo_op(req: GatewayRequest) -> tuple[str, GatewayRequest]:
    """Route engineering requests to repo_handler."""
    from ..handlers.repo_handler import handle_repo_op
    classify_risk(req)
    req.routed_to = "repo_handler"
    req.status = RequestStatus.EXECUTING

    _log_routing(req, "repo_handler", "repo_handler", "executing")

    if req.risk_level == RiskLevel.HIGH:
        return await _require_confirmation(req)

    try:
        result = await handle_repo_op(
            intent=req.intent.value,
            description=req.action_args.get("description", req.normalized_text),
            channel=req.channel.value,
        )
        req.status = RequestStatus.COMPLETE
        audit_log.record(req, "complete")
        _log_routing(req, "repo_handler", "repo_handler", "complete")
        return (format_response(req, result), req)
    except Exception as exc:
        logger.error("repo_handler error: %s", exc, exc_info=True)
        req.status = RequestStatus.FAILED
        audit_log.record(req, "failed")
        _log_routing(req, "repo_handler", "repo_handler", f"error:{exc}")
        return (format_error(f"Repo operation failed: {exc}"), req)


async def _handle_llm_fallback(req: GatewayRequest) -> tuple[str, GatewayRequest]:
    """
    Route unclassified messages to the Lola LLM orchestrator.
    Falls back to a structured 'unavailable' message if the LLM stack is unreachable.
    """
    req.routed_to = "lola_orchestrator"
    req.status = RequestStatus.EXECUTING

    _log_routing(req, "lola_orchestrator", "llm", "attempting")

    try:
        from ..lola.executor import _llm as lola_llm
        reply = await lola_llm(req.normalized_text)
        req.status = RequestStatus.COMPLETE
        audit_log.record(req, "complete")
        _log_routing(req, "lola_orchestrator", "llm", "complete")
        return (reply, req)
    except Exception as exc:
        logger.error("LLM fallback error: %s", exc, exc_info=True)
        req.status = RequestStatus.FAILED
        audit_log.record(req, "failed")
        _log_routing(req, "lola_orchestrator", "llm", f"unavailable:{exc}")
        return (format_fallback_unavailable(req, str(exc)), req)


async def _handle_approve(req: GatewayRequest) -> tuple[str, GatewayRequest]:
    token = req.action_args.get("token", "")
    store = get_store()
    pending = store.resolve(token, req.sender_id)
    if pending is None:
        req.status = RequestStatus.FAILED
        reply = format_error("Invalid, expired, or already-used confirmation token.")
        audit_log.record(req, "confirm_rejected")
        _log_routing(req, "confirmation_store", "approval", "rejected")
        return (reply, req)

    req.action_name = pending.action_name
    req.action_args = pending.action_args
    req.risk_level = RiskLevel.HIGH
    req.status = RequestStatus.EXECUTING

    registry = get_registry()
    result = await registry.dispatch(pending.action_name, action_name=pending.action_name, **pending.action_args)
    req.status = RequestStatus.COMPLETE
    reply = format_response(req, result)
    audit_log.record(req, "complete")
    _log_routing(req, "command_registry", pending.action_name, "approved_and_executed")
    return (reply, req)


async def _require_confirmation(req: GatewayRequest) -> tuple[str, GatewayRequest]:
    store = get_store()
    token = store.create(
        sender_id=req.sender_id,
        chat_id=req.chat_id,
        channel=req.channel.value,
        action_name=req.action_name,
        action_args=req.action_args,
        request_id=req.request_id,
    )
    req.status = RequestStatus.PENDING_CONFIRM
    req.requires_confirmation = True
    reply = format_response(
        req,
        result="CONFIRM REQUIRED",
        confirm_token=token,
        next_step=f"Reply exactly: APPROVE {token}",
    )
    audit_log.record(req, "pending_confirm")
    _log_routing(req, "confirmation_store", req.action_name, "pending_confirm")
    return (reply, req)


async def _execute(req: GatewayRequest) -> tuple[str, GatewayRequest]:
    req.status = RequestStatus.EXECUTING
    registry = get_registry()

    result = await registry.dispatch(
        req.action_name,
        action_name=req.action_name,
        description=req.action_args.get("description", req.normalized_text),
        channel=req.channel.value,
        **req.action_args,
    )

    req.status = RequestStatus.COMPLETE
    reply = format_response(req, result)
    audit_log.record(req, "complete")
    _log_routing(req, "command_registry", req.action_name, "complete")
    return (reply, req)
