"""
tests/test_outlook_connector.py

Unit tests for OutlookConnector.

Covers:
 - _get_token: returns cached token, fetches new token, raises on error
 - _poll_loop: queues messages from Graph API, marks as read, handles errors
 - messages() async generator: yields items, exits when stopped
 - send() is suppressed (replies disabled)
 - start()/stop() lifecycle
 - HTML stripping in message body
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_connector(
    tenant_id="t1",
    client_id="c1",
    client_secret="s1",
    user="user@company.com",
    poll_interval=30,
):
    from openclaw.connectors.outlook import OutlookConnector
    return OutlookConnector(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        user=user,
        poll_interval=poll_interval,
    )


def _mock_resp(json_data: dict, status: int = 200):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestGetToken:
    @pytest.mark.asyncio
    async def test_fetches_token_on_first_call(self):
        c = _make_connector()
        c._session = MagicMock()
        token_resp = {"access_token": "tok123", "expires_in": 3600}
        c._session.post.return_value = _mock_resp(token_resp)
        token = await c._get_token()
        assert token == "tok123"

    @pytest.mark.asyncio
    async def test_returns_cached_token(self):
        c = _make_connector()
        c._token = "cached_tok"
        c._token_expiry = time.time() + 3600  # far future
        c._session = MagicMock()
        token = await c._get_token()
        assert token == "cached_tok"
        c._session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_refreshes_expired_token(self):
        c = _make_connector()
        c._token = "old_tok"
        c._token_expiry = time.time() - 10  # expired
        c._session = MagicMock()
        token_resp = {"access_token": "new_tok", "expires_in": 3600}
        c._session.post.return_value = _mock_resp(token_resp)
        token = await c._get_token()
        assert token == "new_tok"

    @pytest.mark.asyncio
    async def test_raises_on_token_error(self):
        c = _make_connector()
        c._session = MagicMock()
        error_resp = {"error": "invalid_client", "error_description": "Bad credentials"}
        c._session.post.return_value = _mock_resp(error_resp, status=400)
        with pytest.raises(RuntimeError, match="Token error"):
            await c._get_token()


class TestPollLoop:
    """
    The Outlook poll loop uses:
      async with self._session.get(...) as resp:   — needs async CM
      await self._session.patch(...)               — needs awaitable
    We configure the mock accordingly.
    """

    def _make_graph_message(self, msg_id="m1", subject="Test Subject",
                            sender="alice@example.com", body="Hello text"):
        return {
            "id": msg_id,
            "subject": subject,
            "from": {"emailAddress": {"address": sender}},
            "body": {"content": body, "contentType": "text"},
        }

    def _setup_session(self, c, messages_first_call, *, stop_after_first=True):
        """Wire up c._session so the poll loop works correctly.

        get() is used with async with, so returns an async CM.
        patch() is used with await, so is an AsyncMock.
        """
        call_count = 0

        def get_side(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = {"value": messages_first_call}
            else:
                if stop_after_first:
                    c._running = False
                resp = {"value": []}
            return _mock_resp(resp)

        c._session.get.side_effect = get_side
        c._session.patch = AsyncMock(return_value=MagicMock(status=200))

        async def get_token():
            return "tok"
        c._get_token = get_token

    @pytest.mark.asyncio
    async def test_poll_loop_enqueues_message(self):
        c = _make_connector(poll_interval=1)
        c._session = MagicMock()
        c._running = True
        msg = self._make_graph_message()
        self._setup_session(c, [msg])

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await c._poll_loop()

        assert c._queue.qsize() >= 1
        queued = await c._queue.get()
        assert "Test Subject" in queued.text
        assert queued.source == "outlook"

    @pytest.mark.asyncio
    async def test_poll_loop_strips_html_from_body(self):
        c = _make_connector(poll_interval=1)
        c._session = MagicMock()
        c._running = True
        html_body = "<html><body><p>Plain text content</p></body></html>"
        msg = self._make_graph_message(body=html_body)
        self._setup_session(c, [msg])

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await c._poll_loop()

        queued = await c._queue.get()
        assert "<html>" not in queued.text
        assert "Plain text content" in queued.text

    @pytest.mark.asyncio
    async def test_poll_loop_marks_messages_read(self):
        c = _make_connector(poll_interval=1)
        c._session = MagicMock()
        c._running = True
        msg = self._make_graph_message(msg_id="m42")
        self._setup_session(c, [msg])

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            await c._poll_loop()

        c._session.patch.assert_awaited()
        call_args = c._session.patch.call_args
        assert "m42" in str(call_args)

    @pytest.mark.asyncio
    async def test_poll_loop_handles_error_gracefully(self):
        c = _make_connector(poll_interval=1)
        c._session = MagicMock()
        c._running = True
        call_count = 0

        async def get_token():
            raise RuntimeError("Token fetch failed")
        c._get_token = get_token

        async def fake_sleep(_):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                c._running = False

        with patch("asyncio.sleep", side_effect=fake_sleep):
            await c._poll_loop()  # must not raise


class TestMessages:
    @pytest.mark.asyncio
    async def test_messages_yields_from_queue(self):
        c = _make_connector()
        c._running = True
        from openclaw.connectors.base import Message
        c._queue.put_nowait(Message(text="outlook msg", source="outlook", chat_id="a@b.com"))
        collected = []
        async for msg in c.messages():
            collected.append(msg)
            c._running = False
        assert len(collected) == 1
        assert collected[0].source == "outlook"

    @pytest.mark.asyncio
    async def test_messages_exits_when_stopped_and_empty(self):
        c = _make_connector()
        c._running = False
        collected = []
        async for msg in c.messages():
            collected.append(msg)
        assert collected == []


class TestSend:
    @pytest.mark.asyncio
    async def test_send_is_suppressed(self):
        """Replies are disabled; send() must not call Graph sendMail."""
        c = _make_connector()
        c._session = MagicMock()
        await c.send("alice@example.com", "reply")
        c._session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_none_chat_id_is_safe(self):
        c = _make_connector()
        c._session = MagicMock()
        await c.send(None, "nobody")  # must not raise


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        c = _make_connector()
        with patch("aiohttp.ClientSession"), patch("asyncio.create_task"):
            await c.start()
        assert c._running is True

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        c = _make_connector()
        c._running = True
        c._session = MagicMock()
        c._session.close = AsyncMock()
        await c.stop()
        assert c._running is False

    @pytest.mark.asyncio
    async def test_stop_closes_session(self):
        c = _make_connector()
        c._running = True
        session = MagicMock()
        session.close = AsyncMock()
        c._session = session
        await c.stop()
        session.close.assert_awaited_once()
