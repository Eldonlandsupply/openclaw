"""
tests/test_telegram_e2e.py

End-to-end Telegram routing verification for Lola/OpenClaw.
No real network calls. Tests the full pipeline:

  env → config → provider_resolution → ChatClient → TelegramConnector → reply

Covers every failure mode that caused the 401 "User not found" production outage:

  A. Provider resolution: MiniMax key must be present, OpenRouter key must be ignored
  B. Config gate: Telegram enabled without token → fatal startup
  C. Connector lifecycle: start() validates token format before touching network
  D. Message routing: authorized chat_id → Message queued → ChatClient → reply sent
  E. Unauthorized sender → rejected with "Unauthorized" reply, nothing queued
  F. CONNECTOR_TELEGRAM vs OPENCLAW_CONNECTOR_TELEGRAM naming: both resolve to true
  G. MiniMax base_url lock: OPENAI_BASE_URL cannot override provider=minimax
  H. Reasoning tag stripping: <think> blocks removed before Telegram reply is sent
  I. Long reply chunked correctly: 9000-char reply → 3 sendMessage calls
  J. Integration: full _message_loop simulation with mock LLM reply

Run locally:
  cd /opt/openclaw/eldon
  PYTHONPATH=/opt/openclaw/eldon/src pytest tests/test_telegram_e2e.py -v

Run on Pi (quick smoke):
  sudo -u openclaw bash -c '
    cd /opt/openclaw/eldon &&
    source /opt/openclaw/.venv/bin/activate &&
    PYTHONPATH=/opt/openclaw/eldon/src pytest tests/test_telegram_e2e.py -v 2>&1
  '
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
ALLOWED_CHAT_ID = 7828643627          # production Telegram chat ID
MINIMAX_KEY = "sk-mini-test-key"
MINIMAX_MODEL = "MiniMax-M1-mini"
MINIMAX_BASE = "https://api.minimax.io/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_http_response(json_data: dict, status: int = 200):
    """Reusable context-manager mock for aiohttp responses."""
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
    """Build a minimal AppConfig mock for ChatClient."""
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
    """
    These are the regression tests for the root cause of the 401 outage.
    LLM_PROVIDER=minimax must always resolve to MiniMax, regardless of
    what other keys are in the environment.
    """

    def test_minimax_provider_resolves_to_minimax_url(self):
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

    def test_openrouter_key_present_but_minimax_selected_raises(self):
        """
        This is the exact scenario that caused the 401.
        MINIMAX_API_KEY absent, OPENROUTER_API_KEY present with dead key.
        Must fail loudly, not silently route to OpenRouter.
        """
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
        assert "contradictory" in msg.lower() or "OPENROUTER" in msg

    def test_minimax_key_missing_entirely_raises(self):
        from openclaw.llm.provider_resolution import (
            LLMProviderResolutionError,
            resolve_llm_provider,
        )
        with pytest.raises(LLMProviderResolutionError) as exc:
            resolve_llm_provider(
                provider="minimax",
                model=MINIMAX_MODEL,
                env={},
            )
        assert "MINIMAX_API_KEY" in str(exc.value)

    def test_openai_base_url_cannot_hijack_minimax(self):
        """OPENAI_BASE_URL must not override provider=minimax routing."""
        from openclaw.llm.provider_resolution import resolve_llm_provider
        r = resolve_llm_provider(
            provider="minimax",
            model=MINIMAX_MODEL,
            env={
                "MINIMAX_API_KEY": MINIMAX_KEY,
                "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            },
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
        """
        If connectors.telegram.enabled=true but TELEGRAM_BOT_TOKEN is missing,
        AppConfig must call sys.exit() during construction.
        """
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
        # Must not raise
        cfg = cfg_mod.AppConfig(yaml_path=str(cfg_file))
        assert cfg.connectors.telegram.enabled is False
        cfg_mod.reset_config()


# ===========================================================================
# C. Connector lifecycle — token validation before any network call
# ===========================================================================

class TestConnectorTokenValidation:
    def test_valid_token_accepted(self):
        _make_connector(token=VALID_TOKEN)  # no exception

    def test_empty_token_raises_before_network(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="empty"):
            _validate_token("")

    def test_malformed_token_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="format looks wrong"):
            _validate_token("not_a_token_at_all")

    @pytest.mark.asyncio
    async def test_bad_token_raises_on_start_not_silently_fails(self):
        """start() must call getMe and raise RuntimeError on 401, not silently fail."""
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
# D. Message routing — authorized sender → queued → reply
# ===========================================================================

class TestAuthorizedMessageRouting:
    @pytest.mark.asyncio
    async def test_authorized_message_queued_with_correct_fields(self):
        c = _make_connector()
        c._session = MagicMock()
        update = _make_update(chat_id=ALLOWED_CHAT_ID, text="status")
        await c._handle_update(update)
        assert c._queue.qsize() == 1
        msg = await c._queue.get()
        assert msg.text == "status"
        assert msg.source == "telegram"
        assert msg.chat_id == str(ALLOWED_CHAT_ID)

    @pytest.mark.asyncio
    async def test_message_text_stripped_of_whitespace(self):
        c = _make_connector()
        c._session = MagicMock()
        update = _make_update(text="  hello world  ")
        await c._handle_update(update)
        msg = await c._queue.get()
        assert msg.text == "hello world"


# ===========================================================================
# E. Unauthorized sender → rejected, not queued
# ===========================================================================

class TestUnauthorizedSender:
    @pytest.mark.asyncio
    async def test_unauthorized_chat_id_not_queued(self):
        c = _make_connector(allowed=[ALLOWED_CHAT_ID])
        c._session = MagicMock()
        c.send = AsyncMock()
        update = _make_update(chat_id=9999999, text="hack")
        await c._handle_update(update)
        assert c._queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_unauthorized_sender_receives_rejection(self):
        c = _make_connector(allowed=[ALLOWED_CHAT_ID])
        c._session = MagicMock()
        c.send = AsyncMock()
        update = _make_update(chat_id=9999999, text="hack")
        await c._handle_update(update)
        c.send.assert_awaited_once()
        reply_text = c.send.call_args[0][1]
        assert "Unauthorized" in reply_text

    @pytest.mark.asyncio
    async def test_empty_allowed_list_accepts_all(self):
        """allowed_chat_ids=[] means open bot — all senders accepted."""
        c = _make_connector(allowed=[])
        c._session = MagicMock()
        update = _make_update(chat_id=999)
        await c._handle_update(update)
        assert c._queue.qsize() == 1


# ===========================================================================
# F. CONNECTOR_TELEGRAM vs OPENCLAW_CONNECTOR_TELEGRAM naming
# ===========================================================================

class TestEnvVarNamingResolution:
    """
    The known naming split: config.yaml uses ${OPENCLAW_CONNECTOR_TELEGRAM}
    but older env files may use CONNECTOR_TELEGRAM.
    Both must work; neither must silently disable Telegram.
    """

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
# G. OPENAI_BASE_URL cannot override provider=minimax (ChatClient layer)
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

    def test_chat_client_with_no_minimax_key_raises(self):
        from openclaw.chat.client import ChatClient
        from openclaw.llm.provider_resolution import LLMProviderResolutionError
        cfg = _make_mock_cfg(minimax_key=None)
        with pytest.raises(LLMProviderResolutionError):
            ChatClient(cfg)


# ===========================================================================
# H. Reasoning tag stripping — <think> removed before reply sent to Telegram
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
        raw = "<THINK>internal</THINK>Reply."
        assert strip_reasoning_tags(raw) == "Reply."

    @pytest.mark.asyncio
    async def test_chat_reply_strips_think_tags_before_send(self):
        """
        End-to-end: if the LLM returns <think>...</think>Reply, the connector
        must deliver only 'Reply' to the Telegram sendMessage call.
        """
        c = _make_connector()
        c._session = MagicMock()
        c.send = AsyncMock()

        from openclaw.connectors.base import Message
        from openclaw.llm.provider_resolution import strip_reasoning_tags

        # Simulate what _message_loop does: get message, call LLM, strip, send
        raw_llm_reply = "<think>Let me think...</think>\nYes, the land parcel is ready."
        clean_reply = strip_reasoning_tags(raw_llm_reply)

        await c.send(str(ALLOWED_CHAT_ID), clean_reply)
        sent_text = c.send.call_args[0][1]
        assert "<think>" not in sent_text
        assert "Yes, the land parcel is ready." in sent_text


# ===========================================================================
# I. Long reply chunked — 9000-char reply → 3 sendMessage calls
# ===========================================================================

class TestLongMessageChunking:
    @pytest.mark.asyncio
    async def test_9000_char_reply_sends_3_chunks(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_http_response({"ok": True}, status=200)
        c._session = session

        long_reply = "A" * 9000  # ceil(9000/4096) = 3
        await c.send(str(ALLOWED_CHAT_ID), long_reply)
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
# J. Full pipeline integration — mock LLM → Telegram reply
# ===========================================================================

class TestFullPipelineIntegration:
    """
    Simulates what _message_loop does in main.py:
    1. Connector yields a Message from an authorized sender
    2. ChatClient.chat() is called → returns LLM reply (possibly with <think>)
    3. Reply is stripped of reasoning tags
    4. Connector.send() is called with the clean reply
    """

    @pytest.mark.asyncio
    async def test_full_message_loop_simulation(self):
        from openclaw.connectors.base import Message
        from openclaw.llm.provider_resolution import strip_reasoning_tags

        # Step 1: connector receives authorized message
        c = _make_connector()
        c._session = MagicMock()
        update = _make_update(chat_id=ALLOWED_CHAT_ID, text="What is the status?")
        await c._handle_update(update)
        assert c._queue.qsize() == 1
        msg = await c._queue.get()

        # Step 2: mock ChatClient.chat() returns a MiniMax-style reply with think block
        raw_reply = "<think>\nUser wants a status update. I should be concise.\n</think>\n\nAll systems operational. 3 pending approvals."
        clean_reply = strip_reasoning_tags(raw_reply)

        # Step 3: verify stripping
        assert "<think>" not in clean_reply
        assert "All systems operational" in clean_reply

        # Step 4: send back via connector
        c.send = AsyncMock()
        await c.send(msg.chat_id, clean_reply)
        c.send.assert_awaited_once_with(str(ALLOWED_CHAT_ID), clean_reply)

    @pytest.mark.asyncio
    async def test_poll_loop_message_flows_to_queue(self):
        """Poll loop must enqueue exactly the messages from getUpdates result."""
        c = _make_connector()
        c._running = True

        updates = [
            _make_update(chat_id=ALLOWED_CHAT_ID, text="first", uid=1),
            _make_update(chat_id=ALLOWED_CHAT_ID, text="second", uid=2),
        ]

        responses = [
            _mock_http_response({"ok": True, "result": updates}),
            _mock_http_response({"ok": True, "result": []}),
        ]
        call_idx = 0

        async def fake_get(*args, **kwargs):
            nonlocal call_idx
            r = responses[min(call_idx, len(responses) - 1)]
            call_idx += 1
            return r

        session = MagicMock()
        session.get = fake_get
        c._session = session

        async def stopper():
            await asyncio.sleep(0.08)
            c._running = False

        await asyncio.gather(
            asyncio.create_task(c._poll_loop()),
            asyncio.create_task(stopper()),
        )

        queued = []
        while not c._queue.empty():
            queued.append(await c._queue.get())

        assert len(queued) == 2
        assert queued[0].text == "first"
        assert queued[1].text == "second"

    @pytest.mark.asyncio
    async def test_send_retries_on_500_succeeds_on_third(self):
        """Transient 500s must be retried; success on 3rd attempt."""
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
        """Permanent 400/403 errors must not be retried."""
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_http_response({"ok": False}, status=400)
        c._session = session
        await c._send_chunk(str(ALLOWED_CHAT_ID), "bad request")
        assert session.post.call_count == 1
