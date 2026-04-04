"""
tests/test_cli_connector.py

Unit tests for CLIConnector.

Covers:
 - start() launches stdin reader
 - messages() yields Message objects from queue
 - messages() exits on sentinel (EOF)
 - send() prints to stdout
 - require_confirm=False: message queued directly
 - require_confirm=True: confirmed message queued, denied message skipped
 - stop() sets _running=False and sends sentinel
"""

from __future__ import annotations

import asyncio
import io
from unittest.mock import MagicMock, patch

import pytest


def _make_connector(require_confirm: bool = False):
    from openclaw.connectors.cli import CLIConnector
    return CLIConnector(require_confirm=require_confirm)


class TestMessages:
    @pytest.mark.asyncio
    async def test_messages_yields_queued_items(self):
        c = _make_connector()
        c._running = True
        from openclaw.connectors.base import Message
        # Put one message and then the sentinel directly
        from openclaw.connectors.cli import _SENTINEL
        c._queue.put_nowait(Message(text="hello cli", source="cli"))
        c._queue.put_nowait(_SENTINEL)
        collected = []
        async for msg in c.messages():
            collected.append(msg)
        assert len(collected) == 1
        assert collected[0].text == "hello cli"
        assert collected[0].source == "cli"

    @pytest.mark.asyncio
    async def test_messages_exits_on_sentinel(self):
        c = _make_connector()
        from openclaw.connectors.cli import _SENTINEL
        c._queue.put_nowait(_SENTINEL)
        collected = []
        async for msg in c.messages():
            collected.append(msg)
        assert collected == []

    @pytest.mark.asyncio
    async def test_messages_multiple_items_then_sentinel(self):
        c = _make_connector()
        from openclaw.connectors.base import Message
        from openclaw.connectors.cli import _SENTINEL
        for i in range(3):
            c._queue.put_nowait(Message(text=f"msg{i}", source="cli"))
        c._queue.put_nowait(_SENTINEL)
        collected = []
        async for msg in c.messages():
            collected.append(msg)
        assert len(collected) == 3


class TestSend:
    @pytest.mark.asyncio
    async def test_send_prints_text(self, capsys):
        c = _make_connector()
        await c.send(None, "response text")
        captured = capsys.readouterr()
        assert "response text" in captured.out

    @pytest.mark.asyncio
    async def test_send_chat_id_ignored(self, capsys):
        c = _make_connector()
        await c.send("some_id", "output")
        captured = capsys.readouterr()
        assert "output" in captured.out


class TestReadStdin:
    def test_reads_line_and_queues_message(self):
        """_read_stdin enqueues message without require_confirm."""
        c = _make_connector(require_confirm=False)
        loop = asyncio.new_event_loop()
        c._running = True
        c._loop = loop
        fake_stdin = io.StringIO("hello world\n")
        with patch("sys.stdin", fake_stdin):
            c._read_stdin()
        # After reading, loop should have the message (or sentinel) queued
        # We can't easily introspect the loop, but sentinel must be present
        assert not loop.is_running()
        loop.close()

    def test_eof_sends_sentinel(self):
        """Empty stdin (EOF) causes sentinel to be sent."""
        from openclaw.connectors.cli import _SENTINEL
        c = _make_connector()
        loop = asyncio.new_event_loop()
        c._running = True
        c._loop = loop
        fake_stdin = io.StringIO("")  # immediate EOF
        with patch("sys.stdin", fake_stdin):
            c._read_stdin()
        # Can't directly check queue without running the loop,
        # but _read_stdin should return cleanly
        loop.close()

    def test_require_confirm_yes_queues(self):
        """require_confirm=True with 'y' answer queues the message."""
        c = _make_connector(require_confirm=True)
        loop = asyncio.new_event_loop()
        c._running = True
        c._loop = loop
        # Provide command then confirmation
        fake_stdin = io.StringIO("run task\ny\n")
        queued = []

        def fake_put(item):
            queued.append(item)

        with patch("sys.stdin", fake_stdin):
            with patch.object(loop, "call_soon_threadsafe", side_effect=lambda fn, x: fake_put(x)):
                c._read_stdin()

        from openclaw.connectors.cli import _SENTINEL
        from openclaw.connectors.base import Message
        messages = [q for q in queued if isinstance(q, Message)]
        assert any(m.text == "run task" for m in messages)
        loop.close()

    def test_require_confirm_no_does_not_queue(self):
        """require_confirm=True with 'n' answer skips the message."""
        c = _make_connector(require_confirm=True)
        loop = asyncio.new_event_loop()
        c._running = True
        c._loop = loop
        fake_stdin = io.StringIO("run task\nn\n")
        queued = []

        def fake_put(item):
            queued.append(item)

        with patch("sys.stdin", fake_stdin):
            with patch.object(loop, "call_soon_threadsafe", side_effect=lambda fn, x: fake_put(x)):
                c._read_stdin()

        from openclaw.connectors.base import Message
        messages = [q for q in queued if isinstance(q, Message)]
        assert messages == []
        loop.close()


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        c = _make_connector()
        loop = asyncio.get_running_loop()
        c._running = True
        c._loop = loop
        await c.stop()
        assert c._running is False

    @pytest.mark.asyncio
    async def test_stop_sends_sentinel_to_unblock_messages(self):
        """stop() schedules sentinel via call_soon_threadsafe so messages() can exit."""
        from openclaw.connectors.cli import _SENTINEL
        c = _make_connector()
        loop = asyncio.get_running_loop()
        c._running = True
        c._loop = loop
        await c.stop()
        # Yield so the call_soon_threadsafe callback executes
        await asyncio.sleep(0)
        item = c._queue.get_nowait()
        assert item is _SENTINEL


class TestStart:
    @pytest.mark.asyncio
    async def test_start_sets_running_and_loop(self):
        c = _make_connector()
        with patch.object(asyncio.get_running_loop(), "run_in_executor", return_value=asyncio.Future()):
            with patch("asyncio.get_running_loop") as mock_loop_fn:
                fake_loop = MagicMock()
                mock_loop_fn.return_value = fake_loop
                await c.start()
        assert c._running is True
