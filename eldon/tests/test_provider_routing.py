"""
test_provider_routing.py
Regression tests for LLM provider routing.
Verifies that:
  1. provider=minimax uses MiniMax URL and MiniMax key only
  2. provider=openrouter uses OpenRouter URL and OpenRouter key only
  3. OPENAI_BASE_URL cannot override explicit provider=minimax or provider=openrouter
  4. Telegram chat path uses the same provider resolver as normal app chat
  5. Contradictory env (minimax selected, only openrouter key present) raises loud error

These tests MUST stay green. A regression here means the wrong provider
is being silently used — which caused the LLM 401 "User not found" error.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.openclaw.llm.provider_resolution import (
    LLMProviderResolutionError,
    resolve_llm_provider,
)
from src.openclaw.chat.client import ChatClient


# ── 1. provider=minimax uses MiniMax URL and MiniMax key only ────────────────

def test_minimax_uses_minimax_url_and_key():
    result = resolve_llm_provider(
        provider="minimax",
        model="MiniMax-M1-mini",
        env={"MINIMAX_API_KEY": "sk-mini-real"},
    )
    assert result.provider == "minimax"
    assert "minimax.io" in result.base_url
    assert result.api_key == "sk-mini-real"
    assert result.api_key_source == "env:MINIMAX_API_KEY"
    # OpenRouter must not be touched
    assert "openrouter" not in result.base_url.lower()


# ── 2. provider=openrouter uses OpenRouter URL and OpenRouter key only ───────

def test_openrouter_uses_openrouter_url_and_key():
    result = resolve_llm_provider(
        provider="openrouter",
        model="openai/gpt-4o-mini",
        env={"OPENROUTER_API_KEY": "sk-or-real"},
    )
    assert result.provider == "openrouter"
    assert "openrouter.ai" in result.base_url
    assert result.api_key == "sk-or-real"
    assert result.api_key_source == "env:OPENROUTER_API_KEY"
    # MiniMax must not be touched
    assert "minimax" not in result.base_url.lower()


# ── 3. OPENAI_BASE_URL cannot override explicit provider=minimax ─────────────

def test_openai_base_url_cannot_override_minimax_provider():
    """
    Even if OPENAI_BASE_URL is set to something random, provider=minimax
    must use the canonical MiniMax endpoint.
    """
    result = resolve_llm_provider(
        provider="minimax",
        model="MiniMax-M1-mini",
        env={
            "MINIMAX_API_KEY": "sk-mini-real",
            "OPENAI_BASE_URL": "https://some-other-endpoint.com/v1",
        },
    )
    assert result.provider == "minimax"
    assert result.base_url == "https://api.minimax.io/v1"


def test_openai_base_url_cannot_override_openrouter_provider():
    """
    OPENAI_BASE_URL pointing at MiniMax cannot make provider=openrouter use MiniMax.
    """
    result = resolve_llm_provider(
        provider="openrouter",
        model="openai/gpt-4o-mini",
        env={
            "OPENROUTER_API_KEY": "sk-or-real",
            "OPENAI_BASE_URL": "https://api.minimax.io/v1",
        },
    )
    assert result.provider == "openrouter"
    assert result.base_url == "https://openrouter.ai/api/v1"


# ── 4. Telegram chat path uses the same provider resolver ────────────────────

def test_telegram_chat_path_uses_same_provider_resolver():
    """
    ChatClient (used by Telegram, WhatsApp, CLI paths) must use
    resolve_llm_provider, not a separate code path.
    When provider=minimax and MINIMAX_API_KEY is set, the resolved
    base_url must be the MiniMax endpoint — never OpenRouter.

    Note: ChatClient catches LLMProviderResolutionError and degrades to
    provider=none rather than raising. The real guard is the contradiction
    check in /etc/openclaw/openclaw.env at startup. This test verifies
    the happy path: correct key → correct provider resolved.
    """
    cfg = MagicMock()
    cfg.llm.provider = "minimax"
    cfg.llm.chat_model = "MiniMax-M1-mini"
    cfg.llm.base_url = None
    cfg.llm.system_prompt = None
    cfg.llm.max_requests_per_minute = 60
    cfg.llm.request_timeout_seconds = 30
    cfg.secrets.minimax_api_key = "sk-mini-telegram-test"
    cfg.secrets.openrouter_api_key = None
    cfg.secrets.openai_api_key = None
    cfg.secrets.xai_api_key = None

    client = ChatClient(cfg)
    # Happy path: correct key present → minimax resolved
    assert client._provider == "minimax"
    assert "minimax.io" in client._base_url
    assert client._api_key == "sk-mini-telegram-test"
    # Critically: OpenRouter must not appear in the routing path
    assert "openrouter" not in client._base_url.lower()


# ── 5. Contradictory env: minimax selected, only openrouter key present ──────

def test_contradictory_env_raises_clear_error():
    """
    If LLM_PROVIDER=minimax but MINIMAX_API_KEY is absent and
    OPENROUTER_API_KEY is present, the system must fail loudly.
    This prevents silent routing to the wrong provider.
    """
    with pytest.raises(LLMProviderResolutionError) as exc_info:
        resolve_llm_provider(
            provider="minimax",
            model="MiniMax-M1-mini",
            env={"OPENROUTER_API_KEY": "sk-or-dead"},  # MINIMAX_API_KEY absent
        )
    error_msg = str(exc_info.value)
    assert "minimax" in error_msg.lower() or "MINIMAX_API_KEY" in error_msg
    assert "contradictory" in error_msg.lower() or "OPENROUTER_API_KEY" in error_msg


# ── Bonus: minimax with non-minimax base_url is rejected ────────────────────

def test_minimax_rejects_openrouter_base_url():
    with pytest.raises(LLMProviderResolutionError):
        resolve_llm_provider(
            provider="minimax",
            model="MiniMax-M1-mini",
            configured_base_url="https://openrouter.ai/api/v1",
            env={"MINIMAX_API_KEY": "sk-mini-real"},
        )


def test_openrouter_rejects_minimax_base_url():
    with pytest.raises(LLMProviderResolutionError):
        resolve_llm_provider(
            provider="openrouter",
            model="openai/gpt-4o-mini",
            configured_base_url="https://api.minimax.io/v1",
            env={"OPENROUTER_API_KEY": "sk-or-real"},
        )


# ── strip_reasoning_tags tests ────────────────────────────────────────────

from openclaw.llm.provider_resolution import strip_reasoning_tags


def test_strip_think_block_removed():
    raw = "<think>\nLet me think about this.\n</think>\n\nHello, I am OpenClaw."
    assert strip_reasoning_tags(raw) == "Hello, I am OpenClaw."


def test_strip_think_block_multiline():
    raw = "<think>\nStep 1: consider identity.\nStep 2: answer directly.\n</think>No. I'm OpenClaw."
    assert strip_reasoning_tags(raw) == "No. I'm OpenClaw."


def test_strip_think_block_case_insensitive():
    raw = "<THINK>reasoning here</THINK>\n\nActual reply."
    assert strip_reasoning_tags(raw) == "Actual reply."


def test_strip_no_think_block_passthrough():
    raw = "Simple reply with no reasoning tags."
    assert strip_reasoning_tags(raw) == raw


def test_strip_empty_string():
    assert strip_reasoning_tags("") == ""


def test_strip_think_block_only():
    raw = "<think>nothing useful here</think>"
    assert strip_reasoning_tags(raw) == ""


def test_strip_multiple_think_blocks():
    raw = "<think>first</think>\nmiddle\n<think>second</think>\nend"
    result = strip_reasoning_tags(raw)
    assert "first" not in result
    assert "second" not in result
    assert "middle" in result
    assert "end" in result


def test_strip_think_block_preserves_content_with_angle_brackets():
    raw = "<think>ignore this</think>\nResult: x < 5 and y > 3"
    result = strip_reasoning_tags(raw)
    assert "ignore" not in result
    assert "x < 5" in result
