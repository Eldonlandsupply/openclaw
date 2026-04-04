"""
tests/test_chat_client_api.py

Tests for ChatClient._call_api and the full chat() pipeline with a mocked
HTTP session. Zero real network calls.

Covers:
 - Successful MiniMax HTTP call returns clean reply
 - <think> reasoning blocks are stripped before reply is returned
 - HTTP 4xx/5xx raises RuntimeError (caller gets LLM error message)
 - asyncio.TimeoutError → clean "[OpenClaw] LLM request timed out" reply,
   user message popped from history
 - History is appended on success (user + assistant)
 - History is NOT appended on error (user message popped)
 - MAX_HISTORY: history is trimmed when it grows beyond 40 entries
 - ConnectorHealth: record_ok/record_failure/alert threshold
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cfg(provider="minimax", model="MiniMax-M1-mini"):
    cfg = MagicMock()
    cfg.llm.provider = provider
    cfg.llm.chat_model = model
    cfg.llm.base_url = None
    cfg.llm.system_prompt = None
    cfg.llm.max_requests_per_minute = 60
    cfg.llm.request_timeout_seconds = 30
    cfg.secrets.minimax_api_key = "sk-minimax-test"
    cfg.secrets.openrouter_api_key = None
    cfg.secrets.openai_api_key = None
    cfg.secrets.xai_api_key = None
    return cfg


def _mock_api_response(content: str, status: int = 200):
    """Return a mock aiohttp response for a chat/completions call."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value={
        "choices": [{"message": {"content": content}}]
    })
    resp.text = AsyncMock(return_value=f"HTTP {status}")
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_error_response(status: int, body: str = "error body"):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value={})
    resp.text = AsyncMock(return_value=body)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# _call_api: HTTP success path
# ---------------------------------------------------------------------------

class TestCallApi:
    @pytest.mark.asyncio
    async def test_successful_call_returns_content(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        client._history = [{"role": "user", "content": "hello"}]

        session = MagicMock()
        session.post.return_value = _mock_api_response("Hi there!")
        session.closed = False
        client._session = session

        reply = await client._call_api()
        assert reply == "Hi there!"

    @pytest.mark.asyncio
    async def test_call_api_strips_think_blocks(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        client._history = [{"role": "user", "content": "hello"}]

        raw = "<think>\nLet me reason.\n</think>\n\nActual reply."
        session = MagicMock()
        session.post.return_value = _mock_api_response(raw)
        session.closed = False
        client._session = session

        reply = await client._call_api()
        assert "<think>" not in reply
        assert "Actual reply." in reply

    @pytest.mark.asyncio
    async def test_call_api_raises_on_http_error(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        client._history = [{"role": "user", "content": "hello"}]

        session = MagicMock()
        session.post.return_value = _mock_error_response(401, "Unauthorized")
        session.closed = False
        client._session = session

        with pytest.raises(RuntimeError, match="HTTP 401"):
            await client._call_api()

    @pytest.mark.asyncio
    async def test_call_api_url_is_minimax_endpoint(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        client._history = [{"role": "user", "content": "test"}]

        session = MagicMock()
        session.post.return_value = _mock_api_response("response")
        session.closed = False
        client._session = session

        await client._call_api()
        call_url = session.post.call_args[0][0]
        assert "minimax.io" in call_url
        assert "chat/completions" in call_url

    @pytest.mark.asyncio
    async def test_call_api_sends_system_prompt_and_history(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        client._history = [{"role": "user", "content": "status?"}]

        session = MagicMock()
        session.post.return_value = _mock_api_response("All good.")
        session.closed = False
        client._session = session

        await client._call_api()
        payload = session.post.call_args[1]["json"]
        messages = payload["messages"]
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "status?"


# ---------------------------------------------------------------------------
# chat(): full pipeline
# ---------------------------------------------------------------------------

class TestChatPipeline:
    @pytest.mark.asyncio
    async def test_chat_appends_to_history_on_success(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())

        with patch.object(client, "_call_api", new=AsyncMock(return_value="Reply text")):
            reply = await client.chat("Hello!")
        assert reply == "Reply text"
        assert len(client._history) == 2
        assert client._history[0] == {"role": "user", "content": "Hello!"}
        assert client._history[1] == {"role": "assistant", "content": "Reply text"}

    @pytest.mark.asyncio
    async def test_chat_pops_user_message_on_error(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        initial_history_len = len(client._history)

        with patch.object(client, "_call_api", new=AsyncMock(side_effect=Exception("LLM down"))):
            reply = await client.chat("Hello!")
        assert "LLM error" in reply or "LLM down" in reply
        # History should be back to pre-call length (user message popped)
        assert len(client._history) == initial_history_len

    @pytest.mark.asyncio
    async def test_chat_timeout_returns_clean_message(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        client._request_timeout = 1

        async def slow_api():
            await asyncio.sleep(100)
            return "never"

        with patch.object(client, "_call_api", new=slow_api):
            reply = await client.chat("Hello!")
        assert "timed out" in reply.lower() or "timeout" in reply.lower()
        # User message should be popped
        assert not any(m.get("content") == "Hello!" for m in client._history)

    @pytest.mark.asyncio
    async def test_chat_history_trim_evicts_oldest(self, monkeypatch):
        """
        When history exceeds MAX_HISTORY, _trim_history evicts oldest entries.
        After trim (before API call) history is MAX_HISTORY, then the assistant
        reply is appended, so the final length is MAX_HISTORY + 1 = 41.
        The important invariant is that very old messages are gone.
        """
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-test")
        from openclaw.chat.client import ChatClient
        client = ChatClient(_make_cfg())
        # Pre-fill to MAX_HISTORY messages (this will trigger trim on next append)
        for i in range(client.MAX_HISTORY):
            client._history.append({"role": "user", "content": f"old_msg_{i}"})

        with patch.object(client, "_call_api", new=AsyncMock(return_value="ok")):
            await client.chat("overflow msg")
        # Oldest messages should be evicted
        texts = [m["content"] for m in client._history]
        assert "old_msg_0" not in texts   # evicted
        assert "overflow msg" in texts    # kept

    @pytest.mark.asyncio
    async def test_chat_no_llm_configured_returns_echo(self):
        from openclaw.chat.client import ChatClient
        cfg = MagicMock()
        cfg.llm.provider = "none"
        cfg.llm.chat_model = "none"
        cfg.llm.base_url = None
        cfg.llm.system_prompt = None
        cfg.llm.max_requests_per_minute = 60
        cfg.llm.request_timeout_seconds = 30
        cfg.secrets.minimax_api_key = None
        cfg.secrets.openrouter_api_key = None
        cfg.secrets.openai_api_key = None
        cfg.secrets.xai_api_key = None
        client = ChatClient(cfg)
        reply = await client.chat("hello")
        assert "echo" in reply.lower()
        await client.close()


# ---------------------------------------------------------------------------
# ConnectorHealth (from main.py)
# ---------------------------------------------------------------------------

class TestConnectorHealth:
    def test_record_ok_resets_failures(self):
        from openclaw.main import ConnectorHealth
        h = ConnectorHealth()
        h._failures["telegram"] = 3
        h._alerted.add("telegram")
        h.record_ok("telegram")
        assert h._failures["telegram"] == 0
        assert "telegram" not in h._alerted

    def test_record_failure_increments(self):
        from openclaw.main import ConnectorHealth
        h = ConnectorHealth()
        crossed = h.record_failure("telegram")
        assert h._failures["telegram"] == 1
        assert crossed is False

    def test_record_failure_crosses_threshold(self):
        from openclaw.main import ConnectorHealth, MAX_CONNECTOR_FAILURES
        h = ConnectorHealth()
        crossed = False
        for _ in range(MAX_CONNECTOR_FAILURES):
            crossed = h.record_failure("telegram")
        assert crossed is True

    def test_alert_only_fires_once(self):
        from openclaw.main import ConnectorHealth, MAX_CONNECTOR_FAILURES
        h = ConnectorHealth()
        alerts = 0
        for _ in range(MAX_CONNECTOR_FAILURES * 2):
            if h.record_failure("telegram"):
                alerts += 1
        assert alerts == 1

    def test_record_ok_allows_re_alert(self):
        from openclaw.main import ConnectorHealth, MAX_CONNECTOR_FAILURES
        h = ConnectorHealth()
        for _ in range(MAX_CONNECTOR_FAILURES):
            h.record_failure("telegram")
        h.record_ok("telegram")
        alerts = 0
        for _ in range(MAX_CONNECTOR_FAILURES):
            if h.record_failure("telegram"):
                alerts += 1
        assert alerts == 1

    def test_failures_independent_per_connector(self):
        from openclaw.main import ConnectorHealth, MAX_CONNECTOR_FAILURES
        h = ConnectorHealth()
        for _ in range(MAX_CONNECTOR_FAILURES - 1):
            h.record_failure("telegram")
        crossed = h.record_failure("whatsapp")
        assert crossed is False  # whatsapp only has 1 failure


# ---------------------------------------------------------------------------
# _message_loop integration
# ---------------------------------------------------------------------------

class TestMessageLoop:
    """Integration test: connector → dedup → dispatcher → reply sent back."""

    @pytest.mark.asyncio
    async def test_message_dispatched_and_reply_sent(self):
        from openclaw.main import Dispatcher, MessageDeduplicator, ConnectorHealth, _message_loop, _shutdown
        from openclaw.connectors.base import Message

        # Mock connector that yields one message then raises StopAsyncIteration
        msg = Message(text="echo hello", source="cli", chat_id=None)

        async def mock_messages():
            yield msg
            # Signal shutdown so _message_loop exits
            _shutdown.set()

        connector = MagicMock()
        connector.name = "cli"
        connector.messages.return_value = mock_messages()
        connector.send = AsyncMock()

        registry = MagicMock()
        registry.is_allowed.return_value = True
        from openclaw.actions.base import ActionResult
        registry.dispatch = AsyncMock(return_value=ActionResult(success=True, output="hello"))

        memory = MagicMock()
        memory.get = AsyncMock(return_value=None)
        memory.list_keys = AsyncMock(return_value=[])
        memory.set = AsyncMock()
        memory.log_event = AsyncMock()

        chat_client = MagicMock()
        chat_client.chat = AsyncMock(return_value="LLM reply")

        dispatcher = Dispatcher(registry, memory, chat_client)
        dedup = MessageDeduplicator()
        health = ConnectorHealth()

        try:
            await _message_loop(connector, dispatcher, dedup, health)
        except Exception:
            pass
        finally:
            _shutdown.clear()

        connector.send.assert_awaited_once()
        sent_text = connector.send.call_args[0][1]
        assert "hello" in sent_text

    @pytest.mark.asyncio
    async def test_duplicate_message_suppressed(self):
        from openclaw.main import Dispatcher, MessageDeduplicator, ConnectorHealth, _message_loop, _shutdown
        from openclaw.connectors.base import Message

        msg = Message(text="duplicate text", source="cli", chat_id=None)

        async def mock_messages():
            yield msg
            yield msg  # Same text = duplicate
            _shutdown.set()

        connector = MagicMock()
        connector.name = "cli"
        connector.messages.return_value = mock_messages()
        connector.send = AsyncMock()

        registry = MagicMock()
        registry.is_allowed.return_value = False
        memory = MagicMock()
        memory.log_event = AsyncMock()
        chat_client = MagicMock()
        chat_client.chat = AsyncMock(return_value="reply")
        chat_client.reset = MagicMock()

        dispatcher = Dispatcher(registry, memory, chat_client)
        dedup = MessageDeduplicator()
        health = ConnectorHealth()

        try:
            await _message_loop(connector, dispatcher, dedup, health)
        except Exception:
            pass
        finally:
            _shutdown.clear()

        # Only one send call — duplicate was suppressed
        assert connector.send.call_count == 1
