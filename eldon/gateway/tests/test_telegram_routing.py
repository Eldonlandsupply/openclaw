"""
Tests for Telegram→OpenClaw routing.

Covers:
- Repo/engineering messages are classified as REPO_OP or DEV_QUERY (not UNKNOWN)
- LLM_FALLBACK is used instead of hard error for unclassified messages
- Repo handler dispatches correctly for git queries
- Fallback when LLM orchestrator is offline
- Calendar/Attio messages route to correct paths via Lola classifier
- Structured log fields are populated on routing decisions
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.gateway.models import Channel, GatewayRequest, Intent, RiskLevel
from app.gateway.router import route
from app.gateway.responses import format_fallback_unavailable


# ── Helpers ───────────────────────────────────────────────────────────────

def _tg_req(text: str, sender_id: str = "111", chat_id: str = "999") -> GatewayRequest:
    return GatewayRequest(
        channel=Channel.TELEGRAM,
        sender_id=sender_id,
        chat_id=chat_id,
        message_id=f"msg-{text[:8]}",
        raw_text=text,
        normalized_text=text,
    )


# ── Router: engineering classification ───────────────────────────────────

def test_repo_op_implement_routes_to_repo_op():
    """A request to implement a feature must be REPO_OP, not UNKNOWN."""
    req = _tg_req("implement the Telegram routing fix in the gateway router")
    route(req)
    assert req.intent == Intent.REPO_OP, f"Expected REPO_OP, got {req.intent}"
    assert req.action_name == "repo_op"
    assert req.route_reason == "keyword_repo_op"


def test_repo_op_fix_routes_to_repo_op():
    req = _tg_req("fix the bug in provider_resolution.py")
    route(req)
    assert req.intent == Intent.REPO_OP


def test_repo_op_refactor_routes_to_repo_op():
    req = _tg_req("refactor the executor module to remove OpenRouter references")
    route(req)
    assert req.intent == Intent.REPO_OP


def test_dev_query_tests_routes_to_dev_query():
    """A request to run tests must be DEV_QUERY."""
    req = _tg_req("run tests")
    route(req)
    assert req.intent == Intent.DEV_QUERY, f"Expected DEV_QUERY, got {req.intent}"
    assert req.action_name == "dev_query"


def test_dev_query_show_logs_routes_to_dev_query():
    req = _tg_req("show logs")
    route(req)
    assert req.intent == Intent.DEV_QUERY


def test_dev_query_git_diff_routes_to_dev_query():
    req = _tg_req("show diff")
    route(req)
    assert req.intent == Intent.DEV_QUERY


def test_unclassified_routes_to_llm_fallback_not_error():
    """
    A message that matches no keywords must route to LLM_FALLBACK.
    It must NOT produce Intent.UNKNOWN — that path returns a hard error.
    """
    req = _tg_req("what should I prioritize tomorrow morning")
    route(req)
    assert req.intent == Intent.LLM_FALLBACK, (
        f"Expected LLM_FALLBACK for open-ended message, got {req.intent}. "
        "This is the passive-assistant regression: UNKNOWN causes a hard error response."
    )


def test_repo_op_has_description_in_args():
    """REPO_OP must carry the full description for downstream handlers."""
    text = "commit the current changes with message: fix telegram routing"
    req = _tg_req(text)
    route(req)
    assert req.intent == Intent.REPO_OP
    assert req.action_args.get("description") == text


# ── Repo handler ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_repo_handler_dev_query_git_status(monkeypatch):
    """DEV_QUERY for 'status' calls git status, not an error."""
    from app.handlers.repo_handler import handle_repo_op

    async def fake_run(cmd, timeout=30):
        return 0, "M eldon/src/openclaw/chat/client.py", ""

    monkeypatch.setattr("app.handlers.repo_handler._run", fake_run)

    result = await handle_repo_op(
        intent="DEV_QUERY",
        description="git status",
        channel="telegram",
    )
    assert "git status" in result.lower()
    assert "eldon" in result or "M " in result


@pytest.mark.asyncio
async def test_repo_handler_dev_query_run_tests(monkeypatch):
    """DEV_QUERY for 'run tests' invokes pytest."""
    from app.handlers.repo_handler import handle_repo_op

    async def fake_run(cmd, timeout=30):
        assert "pytest" in cmd
        return 0, "5 passed in 0.42s", ""

    monkeypatch.setattr("app.handlers.repo_handler._run", fake_run)

    result = await handle_repo_op(
        intent="DEV_QUERY",
        description="run tests",
        channel="telegram",
    )
    assert "passed" in result.lower() or "PASSED" in result


@pytest.mark.asyncio
async def test_repo_handler_repo_op_fallback_to_llm_when_executor_offline(monkeypatch):
    """
    When OPENCLAW_EXECUTOR_URL is not set and the request is a complex mutation,
    repo_handler must delegate to LLM action plan instead of returning an error.
    """
    monkeypatch.setenv("OPENCLAW_EXECUTOR_URL", "")

    async def fake_llm(prompt):
        return (
            "Route: github_api\n"
            "Tool: POST /git/commits\n"
            "Risk: MEDIUM\n"
            "Status: action_plan_drafted\n"
            "Result: Commit the staged changes to branch main."
        )

    monkeypatch.setattr("app.lola.executor._llm", fake_llm)

    from app.handlers.repo_handler import handle_repo_op
    result = await handle_repo_op(
        intent="REPO_OP",
        description="commit all changes and push to main",
        channel="telegram",
    )
    # Must return a structured plan, not an error
    assert "ERROR" not in result
    assert "Route" in result or "route" in result.lower() or "github" in result.lower()


# ── LLM fallback degraded mode ────────────────────────────────────────────

def test_format_fallback_unavailable_includes_route_and_blocker():
    """
    format_fallback_unavailable must include route, agent, and blocker fields
    so the operator knows what failed and why — not a generic error message.
    """
    req = _tg_req("what should I do about the failing CI")
    route(req)

    reply = format_fallback_unavailable(req, blocker="Connection refused to api.minimax.io")
    assert "lola_orchestrator" in reply
    assert "llm" in reply
    assert "minimax" in reply.lower() or "MINIMAX" in reply
    assert "Connection refused" in reply


# ── Calendar / Attio routing via Lola classifier ──────────────────────────

def test_lola_classifier_calendar_followup():
    """Calendar follow-up messages must be classified as CALENDAR_QUERY, not UNKNOWN."""
    from app.lola.classifier import classify
    from app.gateway.lola_models import LolaIntent, RiskTier

    intent, tier, conf = classify("what's on my calendar today")
    assert intent == LolaIntent.CALENDAR_QUERY
    assert tier == RiskTier.READ_ONLY
    assert conf >= 0.9


def test_lola_classifier_attio_followup():
    """Attio CRM update requests must be APPROVAL_REQUIRED."""
    from app.lola.classifier import classify
    from app.gateway.lola_models import LolaIntent, RiskTier

    intent, tier, _ = classify("update crm with notes from today's call")
    assert intent == LolaIntent.CRM_UPDATE
    assert tier == RiskTier.APPROVAL_REQUIRED
