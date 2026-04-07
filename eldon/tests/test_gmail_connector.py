"""
tests/test_gmail_connector.py

Unit tests for GmailConnector.

Covers:
 - start() sets _running and creates poll task
 - _fetch_unread: parses simple text email, multipart email, marks as seen
 - messages() async generator: yields items, exits when stopped
 - send() is suppressed (replies disabled) — logs but does not call SMTP
 - stop() sets _running=False
 - poll error: IMAP error is caught and logged, loop continues
"""

from __future__ import annotations

import asyncio
import email as email_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


def _make_connector(user="test@gmail.com", app_password="secret", poll_interval=30):
    from openclaw.connectors.gmail import GmailConnector
    return GmailConnector(user=user, app_password=app_password, poll_interval=poll_interval)


def _build_simple_email(subject: str, body: str, sender: str = "alice@example.com") -> bytes:
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "test@gmail.com"
    return msg.as_bytes()


def _build_multipart_email(subject: str, body: str, sender: str = "alice@example.com") -> bytes:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "test@gmail.com"
    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(f"<html><body>{body}</body></html>", "html"))
    return msg.as_bytes()


class TestFetchUnread:
    """
    _fetch_unread uses self._loop.call_soon_threadsafe to put messages
    onto the queue.  In these tests we run _fetch_unread in a thread via
    asyncio.to_thread (via run_in_executor) and then yield to flush pending
    callbacks, OR we just patch call_soon_threadsafe to call put_nowait
    directly (simplest approach).
    """

    def _make_imap_mock(self, raw_emails: list[bytes]):
        """Build a minimal imaplib.IMAP4_SSL mock."""
        imap = MagicMock()
        uids = [str(i + 1).encode() for i in range(len(raw_emails))]
        imap.search.return_value = (None, [b" ".join(uids)])
        def fetch_side(num, spec):
            idx = int(num) - 1
            return (None, [(num, raw_emails[idx])])
        imap.fetch.side_effect = fetch_side
        imap.store.return_value = (None, None)
        imap.__enter__ = MagicMock(return_value=imap)
        imap.__exit__ = MagicMock(return_value=False)
        return imap

    def _run_fetch(self, c, raw_emails):
        """Set up the loop mock so call_soon_threadsafe is synchronous, then call _fetch_unread."""
        loop = MagicMock()
        # Make call_soon_threadsafe invoke the callback synchronously
        loop.is_closed.return_value = False
        loop.call_soon_threadsafe.side_effect = lambda fn, *args: fn(*args)
        c._loop = loop
        return loop

    def test_simple_email_queued(self):
        c = _make_connector()
        raw = _build_simple_email("Invoice ready", "Please review the invoice.")
        imap = self._make_imap_mock([raw])
        self._run_fetch(c, [raw])
        with patch("imaplib.IMAP4_SSL", return_value=imap):
            c._fetch_unread()
        assert c._queue.qsize() == 1
        msg = c._queue.get_nowait()
        assert "Invoice ready" in msg.text
        assert msg.source == "gmail"

    def test_multipart_email_queued(self):
        c = _make_connector()
        raw = _build_multipart_email("Meeting notes", "Great meeting today!")
        imap = self._make_imap_mock([raw])
        self._run_fetch(c, [raw])
        with patch("imaplib.IMAP4_SSL", return_value=imap):
            c._fetch_unread()
        assert c._queue.qsize() == 1
        msg = c._queue.get_nowait()
        assert "Meeting notes" in msg.text

    def test_email_chat_id_is_sender(self):
        c = _make_connector()
        raw = _build_simple_email("Hello", "body", sender="bob@example.com")
        imap = self._make_imap_mock([raw])
        self._run_fetch(c, [raw])
        with patch("imaplib.IMAP4_SSL", return_value=imap):
            c._fetch_unread()
        msg = c._queue.get_nowait()
        assert "bob@example.com" in msg.chat_id

    def test_marks_email_as_seen(self):
        c = _make_connector()
        raw = _build_simple_email("Subj", "body")
        imap = self._make_imap_mock([raw])
        self._run_fetch(c, [raw])
        with patch("imaplib.IMAP4_SSL", return_value=imap):
            c._fetch_unread()
        imap.store.assert_called_once_with(b"1", "+FLAGS", "\\Seen")

    def test_no_emails_no_queue(self):
        c = _make_connector()
        loop = MagicMock()
        loop.is_closed.return_value = False
        loop.call_soon_threadsafe.side_effect = lambda fn, *args: fn(*args)
        c._loop = loop
        imap = MagicMock()
        imap.search.return_value = (None, [b""])
        imap.__enter__ = MagicMock(return_value=imap)
        imap.__exit__ = MagicMock(return_value=False)
        with patch("imaplib.IMAP4_SSL", return_value=imap):
            c._fetch_unread()
        assert c._queue.qsize() == 0

    def test_imap_error_propagates(self):
        c = _make_connector()
        loop = MagicMock()
        loop.is_closed.return_value = False
        c._loop = loop
        with patch("imaplib.IMAP4_SSL", side_effect=Exception("IMAP connection refused")):
            with pytest.raises(Exception, match="IMAP connection refused"):
                c._fetch_unread()


class TestMessages:
    @pytest.mark.asyncio
    async def test_messages_yields_from_queue(self):
        c = _make_connector()
        c._running = True
        from openclaw.connectors.base import Message
        c._queue.put_nowait(Message(text="email body", source="gmail", chat_id="alice@example.com"))
        collected = []
        async for msg in c.messages():
            collected.append(msg)
            c._running = False
        assert len(collected) == 1
        assert collected[0].source == "gmail"

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
        """Replies are disabled — send() logs but does not call SMTP."""
        c = _make_connector()
        # Should not raise and should not call smtplib
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            await c.send("alice@example.com", "reply text")
        mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_none_chat_id_is_safe(self):
        c = _make_connector()
        await c.send(None, "nobody")  # must not raise


class TestStart:
    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        c = _make_connector()
        with patch("asyncio.create_task"):
            await c.start()
        assert c._running is True


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        c = _make_connector()
        c._running = True
        await c.stop()
        assert c._running is False


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_poll_loop_calls_fetch_unread(self):
        c = _make_connector(poll_interval=1)
        c._running = True
        c._loop = asyncio.get_running_loop()
        call_count = 0

        async def mock_executor(fn_or_none, fn=None):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                c._running = False

        with patch.object(asyncio.get_running_loop(), "run_in_executor", side_effect=mock_executor):
            with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                await c._poll_loop()

        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_poll_loop_handles_fetch_error(self):
        c = _make_connector(poll_interval=1)
        c._running = True
        c._loop = asyncio.get_running_loop()
        call_count = 0

        async def mock_executor_error(fn_or_none, fn=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("IMAP timeout")
            c._running = False

        with patch.object(asyncio.get_running_loop(), "run_in_executor", side_effect=mock_executor_error):
            with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                await c._poll_loop()  # must not raise
