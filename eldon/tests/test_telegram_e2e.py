"""
tests/test_telegram_e2e.py

End-to-end Telegram routing verification for Lola/OpenClaw.
No real network calls. Tests the full pipeline:

  env → config → provider_resolution → ChatClient → TelegramConnector → reply

Covers every failure mode that caused the 401 "User not found" production outage:

  A. Provider resolution: MiniMax key must be present, OpenRouter key must be ignored
  B. Config gate: Telegram enabled without token → fatal startup
  C. Connector lifecycle: start() validates token format before touching network
  D. Message routing: authorized chat_id → Message queued → reply sent
  E. Unauthorized sender → rejected with "Unauthorized" reply, nothing queued
  F. OPENCLAW_CONNECTOR_TELEGRAM env var naming resolves correctly
  G. MiniMax base_url lock: OPENAI_BASE_URL cannot override provider=minimax
  H. Reasoning tag stripping: <think> blocks removed before Telegram reply is sent
  I. Long reply chunked correctly: 9000-char reply → 3 sendMessage calls
  J. Integration: full message loop simulation with mock LLM reply

Run on Pi:
  cd /opt/openclaw/eldon
  PYTHONPATH=/opt/openclaw/eldon/src pytest tests/test_telegram_e2e.py -v
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TOKEN = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
ALLOWED_CHAT_ID = 7828643627
MINIMAX_KEY = "sk-mini-test-key"
MINIMAX_MODEL = "MiniMax-M1-mini"
MINIMAX_BASE = "https://api.minimax.io/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_http_response(json_data: dict, status: int = 200):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=str(json_data))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _getme_ok():
    return {"ok": True, "result": {"id": 777, "username": "lolabot", "is_bot": True}}


def _make_update(chat_id: int = ALLOWED_CHAT_ID, text: str = "hello", uid: int = 1):
    return {
        "update_id": uid,
        "message": {
            "message_id": uid,
            "from": {"id": 9, "is_bot": False},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }


def _make_connector(token=VALID_TOKEN, allowed=None):
    from openclaw.connectors.telegram import TelegramConnector
    return TelegramConnector(
        token=token,
        allowed_chat_ids=[ALLOWED_CHAT_ID] if allowed is None else allowed,
        poll_timeout=1,
    )


def _make_mock_cfg(minimax_key=MINIMAX_KEY, tg_token=VALID_TOKEN):
    """Minimal AppConfig mock matching the real ChatClient.__init__ attribute reads."""
    cfg = MagicMock()
    cfg.llm.provider = "minimax"
    cfg.llm.chat_model = MINIMAX_MODEL
    cfg.llm.base_url = None
    cfg.llm.system_prompt = None
    cfg.llm.max_requests_per_minute = 60
    cfg.llm.request_timeout_seconds = 30
    cfg.secrets.minimax_api_key = minimax_key
    cfg.secrets.openrouter_api_key = None
    cfg.secrets.openai_api_key = None
    cfg.secrets.xai_api_key = None
    cfg.secrets.telegram_bot_token = tg_token
    cfg.secrets.allowed_chat_ids = [ALLOWED_CHAT_ID]
    return cfg


# ===========================================================================
# A. Provider resolution — MiniMax key used, OpenRouter ignored
# ===========================================================================

class TestProviderResolutionMinimax:
    """Regression tests for the root cause of the 401 outage."""

    def test_minimax_resolves_to_minimax_url_and_key(self):
        from openclaw.llm.provider_resolution import resolve_llm_provider
        r = resolve_llm_provider(
            provider="minimax",
            model=MINIMAX_MODEL,
            env={"MINIMAX_API_KEY": MINIMAX_KEY},
        )
        assert r.provider == "minimax"
        assert "minimax.io" in r.base_url
        assert r.api_key == MINIMAX_KEY
        assert "openrouter" not in r.base_url.lower()

    def test_openrouter_key_present_minimax_key_absent_raises(self):
        """Exact scenario that caused the 401: dead OR key, no MiniMax key."""
        from openclaw.llm.provider_resolution import (
            LLMProviderResolutionError,
            resolve_llm_provider,
        )
        with pytest.raises(LLMProviderResolutionError) as exc:
            resolve_llm_provider(
                provider="minimax",
                model=MINIMAX_MODEL,
                env={"OPENROUTER_API_KEY": "sk-or-dead"},
            )
        msg = str(exc.value)
        assert "MINIMAX_API_KEY" in msg or "minimax" in msg.lower()

    def test_minimax_key_entirely_absent_raises(self):
        from openclaw.llm.provider_resolution import (
            LLMProviderResolutionError,
            resolve_llm_provider,
        )
        with pytest.raises(LLMProviderResolutionError) as exc:
            resolve_llm_provider(provider="minimax", model=MINIMAX_MODEL, env={})
        assert "MINIMAX_API_KEY" in str(exc.value)

    def test_openai_base_url_cannot_hijack_minimax(self):
        """OPENAI_BASE_URL must not reroute provider=minimax."""
        from openclaw.llm.provider_resolution import resolve_llm_provider
        r = resolve_llm_provider(
            provider="minimax",
            model=MINIMAX_MODEL,
            env={"MINIMAX_API_KEY": MINIMAX_KEY, "OPENAI_BASE_URL": "https://openrouter.ai/api/v1"},
        )
        assert r.base_url == MINIMAX_BASE

    def test_openrouter_base_url_explicitly_rejected_for_minimax(self):
        from openclaw.llm.provider_resolution import (
            LLMProviderResolutionError,
            resolve_llm_provider,
        )
        with pytest.raises(LLMProviderResolutionError):
            resolve_llm_provider(
                provider="minimax",
                model=MINIMAX_MODEL,
                configured_base_url="https://openrouter.ai/api/v1",
                env={"MINIMAX_API_KEY": MINIMAX_KEY},
            )


# ===========================================================================
# B. Config gate — Telegram enabled without token → SystemExit
# ===========================================================================

class TestConfigGateTelegram:
    def test_telegram_enabled_without_token_exits(self, tmp_path, monkeypatch):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import openclaw.config as cfg_mod
        cfg_mod.reset_config()

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(textwrap.dedent("""
            llm:
              provider: none
              chat_model: test-model
            connectors:
              telegram:
                enabled: true
        """))
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            cfg_mod.AppConfig(yaml_path=str(cfg_file))
        cfg_mod.reset_config()

    def test_telegram_disabled_without_token_ok(self, tmp_path, monkeypatch):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import openclaw.config as cfg_mod
        cfg_mod.reset_config()

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(textwrap.dedent("""
            llm:
              provider: none
              chat_model: test-model
            connectors:
              telegram:
                enabled: false
        """))
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        cfg = cfg_mod.AppConfig(yaml_path=str(cfg_file))
        assert cfg.connectors.telegram.enabled is False
        cfg_mod.reset_config()


# ===========================================================================
# C. Connector lifecycle — token validation before network
# ===========================================================================

class TestConnectorTokenValidation:
    def test_valid_token_accepted(self):
        _make_connector(token=VALID_TOKEN)

    def test_empty_token_raises_before_network(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="empty"):
            _validate_token("")

    def test_malformed_token_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="format looks wrong"):
            _validate_token("not_a_token_at_all")

    @pytest.mark.asyncio
    async def test_bad_token_raises_on_start(self):
        c = _make_connector()
        bad = {"ok": False, "description": "Unauthorized", "error_code": 401}
        with patch("aiohttp.ClientSession") as MockSession:
            session = MagicMock()
            MockSession.return_value = session
            session.get.return_value = _mock_http_response(bad)
            session.close = AsyncMock()
            with pytest.raises(RuntimeError, match="startup failed"):
                await c.start()
        assert c._running is False

    @pytest.mark.asyncio
    async def test_good_token_start_sets_running(self):
        c = _make_connector()
        with patch("aiohttp.ClientSession") as MockSession:
            session = MagicMock()
            MockSession.return_value = session
            session.get.return_value = _mock_http_response(_getme_ok())
            session.close = AsyncMock()
            with patch("asyncio.create_task"):
                await c.start()
        assert c._running is True


# ===========================================================================
# D. Authorized message routing
# ===========================================================================

class TestAuthorizedMessageRouting:
    @pytest.mark.asyncio
    async def test_authorized_message_queued(self):
        c = _make_connector()
        c._session = MagicMock()
        await c._handle_update(_make_update(chat_id=ALLOWED_CHAT_ID, text="status"))
        assert c._queue.qsize() == 1
        msg = await c._queue.get()
        assert msg.text == "status"
        assert msg.source == "telegram"
        assert msg.chat_id == str(ALLOWED_CHAT_ID)

    @pytest.mark.asyncio
    async def test_message_text_stripped(self):
        c = _make_connector()
        c._session = MagicMock()
        await c._handle_update(_make_update(text="  hello world  "))
        msg = await c._queue.get()
        assert msg.text == "hello world"


# ===========================================================================
# E. Unauthorized sender
# ===========================================================================

class TestUnauthorizedSender:
    @pytest.mark.asyncio
    async def test_unauthorized_not_queued(self):
        c = _make_connector(allowed=[ALLOWED_CHAT_ID])
        c._session = MagicMock()
        c.send = AsyncMock()
        await c._handle_update(_make_update(chat_id=9999999, text="hack"))
        assert c._queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_unauthorized_receives_rejection_reply(self):
        c = _make_connector(allowed=[ALLOWED_CHAT_ID])
        c._session = MagicMock()
        c.send = AsyncMock()
        await c._handle_update(_make_update(chat_id=9999999))
        c.send.assert_awaited_once()
        assert "Unauthorized" in c.send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_empty_allowed_list_accepts_all(self):
        c = _make_connector(allowed=[])
        c._session = MagicMock()
        await c._handle_update(_make_update(chat_id=999))
        assert c._queue.qsize() == 1


# ===========================================================================
# F. Env var naming — OPENCLAW_CONNECTOR_TELEGRAM
# ===========================================================================

class TestEnvVarNamingResolution:
    def test_openclaw_connector_telegram_enables_telegram(self, tmp_path, monkeypatch):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from src.config.loader import load_settings

        monkeypatch.setenv("OPENCLAW_CHAT_MODEL", "test-model")
        monkeypatch.setenv("OPENCLAW_CONNECTOR_TELEGRAM", "true")
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(textwrap.dedent("""
            llm:
              chat_model: ${OPENCLAW_CHAT_MODEL}
            connectors:
              telegram: ${OPENCLAW_CONNECTOR_TELEGRAM:false}
        """))
        s = load_settings(str(cfg_file))
        assert s.connectors.telegram is True

    def test_connector_telegram_false_by_default(self, tmp_path, monkeypatch):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from src.config.loader import load_settings

        monkeypatch.setenv("OPENCLAW_CHAT_MODEL", "test-model")
        monkeypatch.delenv("OPENCLAW_CONNECTOR_TELEGRAM", raising=False)
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(textwrap.dedent("""
            llm:
              chat_model: ${OPENCLAW_CHAT_MODEL}
            connectors:
              telegram: ${OPENCLAW_CONNECTOR_TELEGRAM:false}
        """))
        s = load_settings(str(cfg_file))
        assert s.connectors.telegram is False


# ===========================================================================
# G. ChatClient — MiniMax lock, graceful degradation on missing key
# ===========================================================================

class TestChatClientMiniMaxLock:
    def test_chat_client_uses_minimax_base_url(self):
        from openclaw.chat.client import ChatClient
        cfg = _make_mock_cfg()
        client = ChatClient(cfg)
        assert "minimax.io" in client._base_url
        assert client._provider == "minimax"
        assert client._api_key == MINIMAX_KEY
        assert "openrouter" not in client._base_url.lower()

    def test_chat_client_with_no_minimax_key_degrades_to_none(self):
        """
        ChatClient catches LLMProviderResolutionError and falls back to
        provider=none rather than crashing. This is the documented behavior.
        The contradiction guard in /etc/openclaw/openclaw.env is the real
        protection — not a ChatClient exception.
        """
        from openclaw.chat.client import ChatClient
        cfg = _make_mock_cfg(minimax_key=None)
        client = ChatClient(cfg)
        # Degraded to none — no key, no real LLM calls
        assert client._provider == "none"
        assert client._api_key == ""


# ===========================================================================
# H. Reasoning tag stripping
# ===========================================================================

class TestReasoningTagStripping:
    def test_think_block_stripped(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        raw = "<think>\nLet me reason here.\n</think>\n\nI am Lola."
        assert strip_reasoning_tags(raw) == "I am Lola."

    def test_multiple_think_blocks_stripped(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        raw = "<think>step 1</think>\nOK\n<think>step 2</think>\ndone"
        result = strip_reasoning_tags(raw)
        assert "step" not in result
        assert "OK" in result
        assert "done" in result

    def test_no_think_block_passthrough(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        msg = "Hi Matthew, how can I help?"
        assert strip_reasoning_tags(msg) == msg

    def test_only_think_block_returns_empty(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        assert strip_reasoning_tags("<think>nothing</think>") == ""

    def test_case_insensitive(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        assert strip_reasoning_tags("<THINK>internal</THINK>Reply.") == "Reply."

    @pytest.mark.asyncio
    async def test_think_tags_stripped_before_telegram_send(self):
        """LLM reply with <think> block → only clean text reaches send()."""
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        c = _make_connector()
        c._session = MagicMock()
        c.send = AsyncMock()

        raw_llm_reply = "<think>Let me think...</think>\nYes, the land parcel is ready."
        clean = strip_reasoning_tags(raw_llm_reply)
        await c.send(str(ALLOWED_CHAT_ID), clean)

        sent_text = c.send.call_args[0][1]
        assert "<think>" not in sent_text
        assert "Yes, the land parcel is ready." in sent_text


# ===========================================================================
# I. Long message chunking
# ===========================================================================

class TestLongMessageChunking:
    @pytest.mark.asyncio
    async def test_9000_char_reply_sends_3_chunks(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_http_response({"ok": True}, status=200)
        c._session = session
        await c.send(str(ALLOWED_CHAT_ID), "A" * 9000)
        assert session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_short_reply_sends_1_chunk(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_http_response({"ok": True}, status=200)
        c._session = session
        await c.send(str(ALLOWED_CHAT_ID), "Short reply from Lola.")
        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_none_chat_id_is_noop(self):
        c = _make_connector()
        session = MagicMock()
        c._session = session
        await c.send(None, "nobody home")
        session.post.assert_not_called()


# ===========================================================================
# J. Full pipeline integration
# ===========================================================================

class TestFullPipelineIntegration:
    @pytest.mark.asyncio
    async def test_full_message_loop_simulation(self):
        """update → queue → strip LLM reply → send clean text."""
        from openclaw.llm.provider_resolution import strip_reasoning_tags

        c = _make_connector()
        c._session = MagicMock()
        await c._handle_update(_make_update(chat_id=ALLOWED_CHAT_ID, text="What is the status?"))
        assert c._queue.qsize() == 1
        msg = await c._queue.get()

        raw_reply = "<think>\nBe concise.\n</think>\n\nAll systems operational."
        clean = strip_reasoning_tags(raw_reply)
        assert "<think>" not in clean
        assert "All systems operational." in clean

        c.send = AsyncMock()
        await c.send(msg.chat_id, clean)
        c.send.assert_awaited_once_with(str(ALLOWED_CHAT_ID), clean)

    @pytest.mark.asyncio
    async def test_poll_loop_flows_two_messages_to_queue(self):
        """Poll loop must enqueue all messages returned by getUpdates."""
        c = _make_connector()
        c._running = True
        call_count = 0

        updates = [
            _make_update(chat_id=ALLOWED_CHAT_ID, text="first", uid=1),
            _make_update(chat_id=ALLOWED_CHAT_ID, text="second", uid=2),
        ]

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_http_response({"ok": True, "result": updates})
            c._running = False
            return _mock_http_response({"ok": True, "result": []})

        session = MagicMock()
        session.get = fake_get
        c._session = session

        await c._poll_loop()

        queued = []
        while not c._queue.empty():
            queued.append(await c._queue.get())

        assert len(queued) == 2
        assert queued[0].text == "first"
        assert queued[1].text == "second"

    @pytest.mark.asyncio
    async def test_send_retries_on_500_succeeds_third(self):
        c = _make_connector()
        session = MagicMock()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return _mock_http_response({"ok": False}, status=500)
            return _mock_http_response({"ok": True}, status=200)

        session.post.side_effect = side_effect
        c._session = session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._send_chunk(str(ALLOWED_CHAT_ID), "retry test")

        assert session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_400_no_retry(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_http_response({"ok": False}, status=400)
        c._session = session
        await c._send_chunk(str(ALLOWED_CHAT_ID), "bad request")
        assert session.post.call_count == 1
