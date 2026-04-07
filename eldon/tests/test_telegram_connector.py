"""
tests/test_telegram_connector.py
Full unit test suite for the TelegramConnector.

Covers:
 - Token format validation (startup gate)
 - getMe self-test on start() — good token / bad token
 - Authorized inbound message → queued as Message
 - Unauthorized inbound message → sends "Unauthorized" reply, not queued
 - Edited message processed correctly
 - Empty text (sticker/photo) → silently skipped
 - Malformed update (missing chat) → does not crash
 - Callback query (no message key) → silently skipped
 - getUpdates API error → sleeps and retries, does not crash
 - sendMessage success path
 - sendMessage retry on transient 500
 - sendMessage permanent 400/403 → no retry
 - Long message chunked into ≤4096-char pieces
 - stop() cancels poll task and closes session
 - messages() async generator yields queued items and exits when stopped
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_TOKEN = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
ALLOWED_CHAT_ID = 7828643627


def _make_connector(
    token: str = VALID_TOKEN,
    allowed: list[int] | None = None,
) -> "TelegramConnector":
    from openclaw.connectors.telegram import TelegramConnector
    return TelegramConnector(
        token=token,
        allowed_chat_ids=allowed if allowed is not None else [ALLOWED_CHAT_ID],
        poll_timeout=1,
    )


def _mock_response(json_data: dict, status: int = 200):
    """Return a context-manager-compatible mock response."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=str(json_data))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _getme_ok() -> dict:
    return {"ok": True, "result": {"id": 7777, "username": "tynskieldonbot", "is_bot": True}}


def _updates_ok(updates: list[dict]) -> dict:
    return {"ok": True, "result": updates}


def _text_update(chat_id: int = ALLOWED_CHAT_ID, text: str = "Hello", uid: int = 1) -> dict:
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


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

class TestTokenValidation:
    def test_valid_token_accepted(self):
        c = _make_connector(token=VALID_TOKEN)
        assert c is not None

    def test_empty_token_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="empty"):
            _validate_token("")

    def test_whitespace_token_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="empty"):
            _validate_token("   ")

    def test_malformed_token_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="format looks wrong"):
            _validate_token("not_a_real_token")

    def test_short_secret_part_raises(self):
        from openclaw.connectors.telegram import _validate_token
        with pytest.raises(ValueError, match="format looks wrong"):
            _validate_token("123456:tooshort")


# ---------------------------------------------------------------------------
# Startup: getMe self-test
# ---------------------------------------------------------------------------

class TestStartup:
    @pytest.mark.asyncio
    async def test_start_succeeds_when_getme_ok(self):
        c = _make_connector()
        with patch("aiohttp.ClientSession") as MockSession:
            session = MagicMock()
            MockSession.return_value = session
            session.get.return_value = _mock_response(_getme_ok())
            session.close = AsyncMock()
            with patch("asyncio.create_task"):
                await c.start()
            assert c._running is True

    @pytest.mark.asyncio
    async def test_start_fails_loudly_on_bad_token(self):
        c = _make_connector()
        bad_resp = {"ok": False, "description": "Unauthorized", "error_code": 401}
        with patch("aiohttp.ClientSession") as MockSession:
            session = MagicMock()
            MockSession.return_value = session
            session.get.return_value = _mock_response(bad_resp)
            session.close = AsyncMock()
            with pytest.raises(RuntimeError, match="startup failed"):
                await c.start()
        assert c._running is False


# ---------------------------------------------------------------------------
# Update handling
# ---------------------------------------------------------------------------

class TestUpdateHandling:
    @pytest.mark.asyncio
    async def test_authorized_message_queued(self):
        c = _make_connector()
        c._session = MagicMock()
        update = _text_update(chat_id=ALLOWED_CHAT_ID, text="ping")
        await c._handle_update(update)
        assert c._queue.qsize() == 1
        msg = await c._queue.get()
        assert msg.text == "ping"
        assert msg.source == "telegram"
        assert msg.chat_id == str(ALLOWED_CHAT_ID)

    @pytest.mark.asyncio
    async def test_unauthorized_message_not_queued_but_sends_reply(self):
        c = _make_connector(allowed=[ALLOWED_CHAT_ID])
        c._session = MagicMock()
        c.send = AsyncMock()
        update = _text_update(chat_id=9999999, text="hack")
        await c._handle_update(update)
        assert c._queue.qsize() == 0
        c.send.assert_awaited_once()
        call_text = c.send.call_args[0][1]
        assert "Unauthorized" in call_text

    @pytest.mark.asyncio
    async def test_empty_text_skipped(self):
        c = _make_connector()
        c._session = MagicMock()
        update = {
            "update_id": 5,
            "message": {
                "message_id": 5,
                "from": {"id": 9},
                "chat": {"id": ALLOWED_CHAT_ID, "type": "private"},
                "date": 1700000000,
            },
        }
        await c._handle_update(update)
        assert c._queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_edited_message_processed(self):
        c = _make_connector()
        c._session = MagicMock()
        update = {
            "update_id": 6,
            "edited_message": {
                "message_id": 50,
                "from": {"id": 9},
                "chat": {"id": ALLOWED_CHAT_ID, "type": "private"},
                "date": 1700000000,
                "text": "edited",
            },
        }
        await c._handle_update(update)
        assert c._queue.qsize() == 1
        msg = await c._queue.get()
        assert msg.text == "edited"

    @pytest.mark.asyncio
    async def test_callback_query_silently_skipped(self):
        c = _make_connector()
        c._session = MagicMock()
        update = {
            "update_id": 7,
            "callback_query": {"id": "cq1", "from": {"id": 9}, "data": "approve"},
        }
        await c._handle_update(update)
        assert c._queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_malformed_update_does_not_crash(self):
        c = _make_connector()
        c._session = MagicMock()
        await c._handle_update({"update_id": 8, "message": {}})
        assert c._queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_empty_allowed_list_accepts_all_chat_ids(self):
        """When allowed_chat_ids is empty, all senders are accepted."""
        c = _make_connector(allowed=[])
        c._session = MagicMock()
        update = _text_update(chat_id=99999, text="open bot")
        await c._handle_update(update)
        assert c._queue.qsize() == 1


# ---------------------------------------------------------------------------
# Poll loop — counter-based stopping, no asyncio.sleep in test body
# ---------------------------------------------------------------------------

class TestPollLoop:
    @pytest.mark.asyncio
    async def test_poll_loop_enqueues_messages(self):
        """
        Poll loop uses 'async with self._session.get(...) as resp:', so
        session.get must return an async context manager directly (not a
        coroutine). Use a regular (sync) function that returns _mock_response.
        """
        c = _make_connector()
        c._running = True

        updates_first = [_text_update(text="looped", uid=1)]
        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(_updates_ok(updates_first))
            # Stop the loop on second call
            c._running = False
            return _mock_response(_updates_ok([]))

        session = MagicMock()
        session.get = fake_get
        c._session = session

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await c._poll_loop()

        assert c._queue.qsize() >= 1
        msg = await c._queue.get()
        assert msg.text == "looped"

    @pytest.mark.asyncio
    async def test_poll_loop_handles_api_error_gracefully(self):
        """
        A getUpdates error response (ok=False) must not crash the loop.
        session.get returns a sync callable that yields async CMs.
        """
        c = _make_connector()
        c._running = True
        call_count = 0

        def fake_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response({"ok": False, "description": "Flood control"})
            c._running = False
            return _mock_response(_updates_ok([]))

        session = MagicMock()
        session.get = fake_get
        c._session = session

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await c._poll_loop()

        # Must reach here without raising
        assert call_count >= 2


# ---------------------------------------------------------------------------
# Send / retry
# ---------------------------------------------------------------------------

class TestSend:
    @pytest.mark.asyncio
    async def test_send_success(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_response({"ok": True}, status=200)
        c._session = session
        await c.send(str(ALLOWED_CHAT_ID), "hello")
        session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_chat_id_is_noop(self):
        c = _make_connector()
        session = MagicMock()
        c._session = session
        await c.send(None, "should not send")
        session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_chunks_long_message(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_response({"ok": True}, status=200)
        c._session = session
        long_text = "x" * 9000  # ceil(9000/4096) == 3 chunks
        await c.send(str(ALLOWED_CHAT_ID), long_text)
        assert session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_retries_on_transient_error(self):
        c = _make_connector()
        session = MagicMock()
        call_count = 0
        error_resp = _mock_response({"ok": False}, status=500)
        ok_resp = _mock_response({"ok": True}, status=200)

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return error_resp if call_count < 3 else ok_resp

        session.post.side_effect = side_effect
        c._session = session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._send_chunk(str(ALLOWED_CHAT_ID), "retry me")

        assert session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_no_retry_on_400(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_response({"ok": False}, status=400)
        c._session = session
        await c._send_chunk(str(ALLOWED_CHAT_ID), "bad request")
        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_no_retry_on_403(self):
        c = _make_connector()
        session = MagicMock()
        session.post.return_value = _mock_response({"ok": False}, status=403)
        c._session = session
        await c._send_chunk(str(ALLOWED_CHAT_ID), "blocked")
        assert session.post.call_count == 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_stop_cancels_poll_task(self):
        c = _make_connector()
        # Use a real asyncio.Task wrapping a coroutine that immediately raises
        # CancelledError, so stop() can await it safely.
        async def _noop():
            await asyncio.sleep(1000)

        task = asyncio.create_task(_noop())
        c._poll_task = task
        session = MagicMock()
        session.close = AsyncMock()
        c._session = session

        await c.stop()

        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_messages_exits_when_stopped(self):
        c = _make_connector()
        c._running = False  # already stopped — queue is empty
        collected = []
        async for msg in c.messages():
            collected.append(msg)
        assert collected == []


# ---------------------------------------------------------------------------
# Config integration: Telegram enabled but no token → fatal
# ---------------------------------------------------------------------------

class TestConfigGate:
    def test_telegram_enabled_without_token_is_fatal(self, tmp_path, monkeypatch):
        import textwrap
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import openclaw.config as cfg_mod
        cfg_mod.reset_config()

        config_file = tmp_path / "config.yaml"
        config_file.write_text(textwrap.dedent("""
            llm:
              provider: none
              chat_model: gpt-test
            runtime:
              log_level: INFO
              dry_run: true
            connectors:
              cli:
                enabled: false
              telegram:
                enabled: true
        """))

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

        with pytest.raises(SystemExit):
            cfg_mod.AppConfig(yaml_path=str(config_file))

        cfg_mod.reset_config()
