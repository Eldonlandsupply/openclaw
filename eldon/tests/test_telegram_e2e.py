"""
tests/test_telegram_e2e.py

End-to-end Telegram routing verification for Lola/OpenClaw.
No real network calls. Tests the full pipeline:

  env → config → provider_resolution → ChatClient → TelegramConnector → reply

Run:
  cd /opt/openclaw/eldon
  PYTHONPATH=/opt/openclaw/eldon/src pytest tests/test_telegram_e2e.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Constants matching production config
# ---------------------------------------------------------------------------

VALID_TOKEN = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
ALLOWED_CHAT_ID = 7828643627
MINIMAX_KEY = "sk-mini-test-key"
MINIMAX_MODEL = "MiniMax-M1-mini"
MINIMAX_BASE = "https://api.minimax.io/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(json_data: dict, status: int = 200):
    """aiohttp async-context-manager compatible mock."""
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


def _make_mock_cfg(minimax_key=MINIMAX_KEY):
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
    return cfg


def _make_session_mock(responses: list):
    """
    Build an aiohttp.ClientSession mock where session.get() is a coroutine
    that returns successive responses from the list (last one repeated).
    This matches how _poll_loop uses: async with self._session.get(...) as resp
    """
    call_idx = [0]

    def side_effect(*args, **kwargs):
        r = responses[min(call_idx[0], len(responses) - 1)]
        call_idx[0] += 1
        return r

    session = MagicMock()
    session.get.side_effect = side_effect
    session.post.return_value = _mock_response({"ok": True}, status=200)
    session.close = AsyncMock()
    return session


# ===========================================================================
# A. Provider resolution
# ===========================================================================

class TestProviderResolutionMinimax:
    def test_minimax_resolves_correctly(self):
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

    def test_openrouter_key_present_minimax_missing_raises(self):
        """Exact 401 outage scenario — must fail loudly."""
        from openclaw.llm.provider_resolution import (
            LLMProviderResolutionError, resolve_llm_provider,
        )
        with pytest.raises(LLMProviderResolutionError) as exc:
            resolve_llm_provider(
                provider="minimax",
                model=MINIMAX_MODEL,
                env={"OPENROUTER_API_KEY": "sk-or-dead"},
            )
        msg = str(exc.value)
        assert "MINIMAX_API_KEY" in msg or "minimax" in msg.lower()

    def test_minimax_key_absent_raises(self):
        from openclaw.llm.provider_resolution import (
            LLMProviderResolutionError, resolve_llm_provider,
        )
        with pytest.raises(LLMProviderResolutionError):
            resolve_llm_provider(provider="minimax", model=MINIMAX_MODEL, env={})

    def test_openai_base_url_cannot_hijack_minimax(self):
        from openclaw.llm.provider_resolution import resolve_llm_provider
        r = resolve_llm_provider(
            provider="minimax",
            model=MINIMAX_MODEL,
            env={"MINIMAX_API_KEY": MINIMAX_KEY, "OPENAI_BASE_URL": "https://openrouter.ai/api/v1"},
        )
        assert r.base_url == MINIMAX_BASE


# ===========================================================================
# B. Config gate
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


# ===========================================================================
# C. Token validation
# ===========================================================================

class TestConnectorTokenValidation:
    def test_valid_token_accepted(self):
        _make_connector(token=VALID_TOKEN)

    def test_empty_token_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="empty"):
            _validate_token("")

    def test_malformed_token_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="format looks wrong"):
            _validate_token("not_a_token")

    async def test_bad_token_raises_on_start(self):
        c = _make_connector()
        bad = {"ok": False, "description": "Unauthorized", "error_code": 401}
        session = _make_session_mock([_mock_response(bad)])
        with patch("aiohttp.ClientSession", return_value=session):
            with pytest.raises(RuntimeError, match="startup failed"):
                await c.start()
        assert c._running is False

    async def test_good_token_start_sets_running(self):
        c = _make_connector()
        session = _make_session_mock([_mock_response(_getme_ok())])
        with patch("aiohttp.ClientSession", return_value=session):
            with patch("asyncio.create_task"):
                await c.start()
        assert c._running is True


# ===========================================================================
# D. Authorized message routing
# ===========================================================================

class TestAuthorizedMessageRouting:
    async def test_authorized_message_queued(self):
        c = _make_connector()
        c._session = MagicMock()
        update = _make_update(chat_id=ALLOWED_CHAT_ID, text="status")
        await c._handle_update(update)
        assert c._queue.qsize() == 1
        msg = await c._queue.get()
        assert msg.text == "status"
        assert msg.source == "telegram"
        assert msg.chat_id == str(ALLOWED_CHAT_ID)

    async def test_whitespace_text_stripped(self):
        c = _make_connector()
        c._session = MagicMock()
        update = _make_update(text="  hello world  ")
        await c._handle_update(update)
        msg = await c._queue.get()
        assert msg.text == "hello world"


# ===========================================================================
# E. Unauthorized sender
# ===========================================================================

class TestUnauthorizedSender:
    async def test_unauthorized_not_queued(self):
        c = _make_connector(allowed=[ALLOWED_CHAT_ID])
        c._session = MagicMock()
        c.send = AsyncMock()
        update = _make_update(chat_id=9999999, text="hack")
        await c._handle_update(update)
        assert c._queue.qsize() == 0

    async def test_unauthorized_receives_rejection_reply(self):
        c = _make_connector(allowed=[ALLOWED_CHAT_ID])
        c._session = MagicMock()
        c.send = AsyncMock()
        update = _make_update(chat_id=9999999, text="hack")
        await c._handle_update(update)
        c.send.assert_awaited_once()
        assert "Unauthorized" in c.send.call_args[0][1]

    async def test_empty_allowed_list_accepts_all(self):
        c = _make_connector(allowed=[])
        c._session = MagicMock()
        update = _make_update(chat_id=999)
        await c._handle_update(update)
        assert c._queue.qsize() == 1


# ===========================================================================
# F. Env var naming
# ===========================================================================

class TestEnvVarNamingResolution:
    def test_openclaw_connector_telegram_enables(self, tmp_path, monkeypatch):
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
# G. ChatClient MiniMax lock
# ===========================================================================

class TestChatClientMiniMaxLock:
    def test_chat_client_uses_minimax_base_url(self):
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_mock_cfg())
        assert "minimax.io" in client._base_url
        assert client._provider == "minimax"
        assert client._api_key == MINIMAX_KEY
        assert "openrouter" not in client._base_url.lower()

    def test_chat_client_no_key_raises(self):
        from openclaw.chat.client import ChatClient
        from openclaw.llm.provider_resolution import LLMProviderResolutionError
        with pytest.raises(LLMProviderResolutionError):
            ChatClient(_make_mock_cfg(minimax_key=None))


# ===========================================================================
# H. Reasoning tag stripping
# ===========================================================================

class TestReasoningTagStripping:
    def test_think_block_stripped(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        assert strip_reasoning_tags("<think>\nreasoning\n</think>\n\nReply.") == "Reply."

    def test_multiple_blocks_stripped(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        raw = "<think>step 1</think>\nOK\n<think>step 2</think>\ndone"
        result = strip_reasoning_tags(raw)
        assert "step" not in result
        assert "OK" in result

    def test_passthrough_no_tags(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        msg = "Hi Matthew."
        assert strip_reasoning_tags(msg) == msg

    def test_only_think_returns_empty(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        assert strip_reasoning_tags("<think>nothing</think>") == ""

    async def test_think_stripped_before_send(self):
        from openclaw.llm.provider_resolution import strip_reasoning_tags
        c = _make_connector()
        c._session = MagicMock()
        c.send = AsyncMock()
        raw = "<think>Let me think...</think>\n\nAll systems operational."
        clean = strip_reasoning_tags(raw)
        await c.send(str(ALLOWED_CHAT_ID), clean)
        sent = c.send.call_args[0][1]
        assert "<think>" not in sent
        assert "All systems operational." in sent


# ===========================================================================
# I. Long message chunking
# ===========================================================================

class TestLongMessageChunking:
    async def test_9000_chars_sends_3_chunks(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_response({"ok": True}, status=200)
        c._session = session
        await c.send(str(ALLOWED_CHAT_ID), "A" * 9000)
        assert session.post.call_count == 3

    async def test_short_reply_one_chunk(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_response({"ok": True}, status=200)
        c._session = session
        await c.send(str(ALLOWED_CHAT_ID), "Short reply.")
        assert session.post.call_count == 1

    async def test_none_chat_id_noop(self):
        c = _make_connector()
        session = MagicMock()
        c._session = session
        await c.send(None, "nobody")
        session.post.assert_not_called()

    async def test_400_no_retry(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_response({"ok": False}, status=400)
        c._session = session
        await c._send_chunk(str(ALLOWED_CHAT_ID), "bad")
        assert session.post.call_count == 1

    async def test_500_retries_to_success(self):
        c = _make_connector()
        session = MagicMock()
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                return _mock_response({"ok": False}, status=500)
            return _mock_response({"ok": True}, status=200)

        session.post.side_effect = side_effect
        c._session = session
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._send_chunk(str(ALLOWED_CHAT_ID), "retry")
        assert session.post.call_count == 3


# ===========================================================================
# J. Poll loop — fixed mock wiring
# ===========================================================================

class TestPollLoop:
    async def test_poll_loop_enqueues_authorized_messages(self):
        """
        Poll loop must enqueue messages from getUpdates.
        Uses a counter-based stopper instead of asyncio.sleep to avoid hangs.
        """
        c = _make_connector()
        c._running = True

        updates = [
            _make_update(chat_id=ALLOWED_CHAT_ID, text="first", uid=1),
            _make_update(chat_id=ALLOWED_CHAT_ID, text="second", uid=2),
        ]

        call_count = [0]
        responses = [
            _mock_response({"ok": True, "result": updates}),
            _mock_response({"ok": True, "result": []}),
        ]

        def get_side_effect(*args, **kwargs):
            r = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            # Stop after serving all responses
            if call_count[0] >= len(responses):
                c._running = False
            return r

        session = MagicMock()
        session.get.side_effect = get_side_effect
        c._session = session

        await asyncio.wait_for(c._poll_loop(), timeout=5.0)

        queued = []
        while not c._queue.empty():
            queued.append(await c._queue.get())

        assert len(queued) == 2
        assert queued[0].text == "first"
        assert queued[1].text == "second"

    async def test_poll_loop_error_path_retries(self):
        """
        On API error, poll loop logs and continues — must not crash.
        Stopper sets _running=False after second call.
        """
        c = _make_connector()
        c._running = True

        call_count = [0]
        responses = [
            _mock_response({"ok": False, "description": "Flood control"}),
            _mock_response({"ok": True, "result": []}),
        ]

        def get_side_effect(*args, **kwargs):
            r = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            if call_count[0] >= len(responses):
                c._running = False
            return r

        session = MagicMock()
        session.get.side_effect = get_side_effect
        c._session = session

        # Patch sleep so error backoff doesn't actually wait
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await asyncio.wait_for(c._poll_loop(), timeout=5.0)

        # No exception = test passes


# ===========================================================================
# K. Full pipeline simulation
# ===========================================================================

class TestFullPipelineIntegration:
    async def test_message_loop_simulation(self):
        """update → queue → LLM strip → send"""
        from openclaw.llm.provider_resolution import strip_reasoning_tags

        c = _make_connector()
        c._session = MagicMock()
        await c._handle_update(_make_update(text="What is the status?"))
        assert c._queue.qsize() == 1
        msg = await c._queue.get()

        raw_reply = "<think>\nBe concise.\n</think>\n\nAll systems operational. 3 pending approvals."
        clean = strip_reasoning_tags(raw_reply)
        assert "<think>" not in clean
        assert "All systems operational" in clean

        c.send = AsyncMock()
        await c.send(msg.chat_id, clean)
        c.send.assert_awaited_once_with(str(ALLOWED_CHAT_ID), clean)
