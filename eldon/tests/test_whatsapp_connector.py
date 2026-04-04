"""
tests/test_whatsapp_connector.py

Full unit test suite for WhatsAppConnector and _extract_text.

Covers:
 - _extract_text: protobuf field-2 wire path, fallback ASCII, empty blob
 - WhatsAppConnector init defaults
 - _read_events: SQLite read, seen-hash deduplication, memory bound
 - _poll_loop: enqueues messages, handles cancelled error
 - messages() async generator: yields items, exits when stopped
 - send(): happy path, no chat_id noop, JID normalization, HTTP error
 - start()/stop() lifecycle
"""

from __future__ import annotations

import asyncio
import sqlite3
import struct
import tempfile
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _extract_text unit tests
# ---------------------------------------------------------------------------

class TestExtractText:
    def _import(self):
        from openclaw.connectors.whatsapp import _extract_text
        return _extract_text

    def _build_proto_field2(self, text: str) -> bytes:
        """Manually encode a protobuf field 2 (wire type 2) with the given text."""
        tag = 0x12  # field 2, wire type 2
        encoded = text.encode("utf-8")
        length = len(encoded)
        # Encode varint length
        varint = bytearray()
        v = length
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                varint.append(b | 0x80)
            else:
                varint.append(b)
                break
        return bytes([tag]) + bytes(varint) + encoded

    def test_extracts_text_from_proto_field2(self):
        extract = self._import()
        blob = self._build_proto_field2("Hello from WhatsApp")
        result = extract(blob)
        assert result == "Hello from WhatsApp"

    def test_extracts_longest_candidate(self):
        extract = self._import()
        # Two field-2 strings; the longer should win
        blob = self._build_proto_field2("short") + self._build_proto_field2("much longer string here")
        result = extract(blob)
        assert result == "much longer string here"

    def test_falls_back_to_ascii_when_no_proto_field(self):
        extract = self._import()
        # Build bytes with no field-2 tag but plenty of ASCII
        blob = b"\x01\x02\x03" + b"hello world" + b"\x00\xFF"
        result = extract(blob)
        assert result == "hello world"

    def test_empty_bytes_returns_empty(self):
        extract = self._import()
        assert extract(b"") == ""

    def test_only_non_printable_returns_empty(self):
        extract = self._import()
        assert extract(b"\x00\x01\x02\x03\x04") == ""

    def test_single_char_ascii_ignored(self):
        extract = self._import()
        # Only single chars — below minimum length of 2
        result = extract(b"\x41\x00\x42\x00")  # A and B separated by nulls
        assert result == "" or len(result) <= 1

    def test_unicode_text_extracted(self):
        extract = self._import()
        blob = self._build_proto_field2("Hola España")
        result = extract(blob)
        assert "Hola" in result


# ---------------------------------------------------------------------------
# WhatsAppConnector unit tests
# ---------------------------------------------------------------------------

ALLOWED = ["17087525462"]


def _make_connector(
    allowed: list[str] = ALLOWED,
    bridge_url: str = "http://127.0.0.1:8181",
    bridge_db: str = ":memory:",
    poll_interval: int = 5,
):
    from openclaw.connectors.whatsapp import WhatsAppConnector
    return WhatsAppConnector(
        allowed_numbers=allowed,
        bridge_url=bridge_url,
        bridge_db=bridge_db,
        poll_interval=poll_interval,
    )


def _make_db(tmp_path: Path) -> str:
    """Create a minimal whatsmeow_event_buffer table and return the db path."""
    db_path = str(tmp_path / "wabridge.db")
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE whatsmeow_event_buffer (
            our_jid TEXT,
            ciphertext_hash BLOB,
            plaintext BLOB,
            server_timestamp INTEGER
        )
        """
    )
    con.commit()
    con.close()
    return db_path


def _insert_event(db_path: str, our_jid: str, plaintext: bytes, hash_: bytes, ts: int = 1700000000):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO whatsmeow_event_buffer (our_jid, ciphertext_hash, plaintext, server_timestamp) "
        "VALUES (?, ?, ?, ?)",
        (our_jid, hash_, plaintext, ts),
    )
    con.commit()
    con.close()


class TestReadEvents:
    def test_empty_db_returns_empty(self, tmp_path):
        db = _make_db(tmp_path)
        c = _make_connector(bridge_db=db)
        result = c._read_events()
        assert result == []

    def test_event_with_text_returned(self, tmp_path):
        from openclaw.connectors.whatsapp import _extract_text, WhatsAppConnector

        db = _make_db(tmp_path)
        # Build a valid proto field-2 blob
        tag = 0x12
        msg = b"Land parcel 42"
        blob = bytes([tag, len(msg)]) + msg
        _insert_event(db, "17087525462@s.whatsapp.net", blob, b"hash1")
        c = _make_connector(bridge_db=db)
        result = c._read_events()
        assert len(result) == 1
        assert result[0]["text"] == "Land parcel 42"

    def test_seen_hash_not_reprocessed(self, tmp_path):
        db = _make_db(tmp_path)
        tag = 0x12
        msg = b"duplicate message"
        blob = bytes([tag, len(msg)]) + msg
        _insert_event(db, "jid@s.whatsapp.net", blob, b"dup_hash")
        c = _make_connector(bridge_db=db)
        c._seen_hashes.add(b"dup_hash")
        result = c._read_events()
        assert result == []

    def test_empty_plaintext_skipped(self, tmp_path):
        db = _make_db(tmp_path)
        _insert_event(db, "jid@s.whatsapp.net", b"", b"empty_hash")
        c = _make_connector(bridge_db=db)
        result = c._read_events()
        assert result == []

    def test_seen_hashes_bounded_at_500(self, tmp_path):
        db = _make_db(tmp_path)
        c = _make_connector(bridge_db=db)
        # Fill _seen_hashes past 500
        for i in range(600):
            c._seen_hashes.add(bytes([i % 256, i // 256]))
        c._read_events()  # triggers bound
        assert len(c._seen_hashes) <= 500

    def test_bad_db_path_returns_empty(self):
        c = _make_connector(bridge_db="/nonexistent/path/to.db")
        result = c._read_events()
        assert result == []


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_poll_loop_enqueues_message(self, tmp_path):
        db = _make_db(tmp_path)
        tag = 0x12
        msg = b"status check"
        blob = bytes([tag, len(msg)]) + msg
        _insert_event(db, "jid@s.whatsapp.net", blob, b"ph1")

        c = _make_connector(allowed=ALLOWED, bridge_db=db, poll_interval=1)
        c._queue = asyncio.Queue()
        c._running = True
        call_count = 0

        original_read = c._read_events

        def patched_read():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_read()
            c._running = False
            return []

        c._read_events = patched_read

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = lambda _: asyncio.sleep(0)
            await c._poll_loop()

        assert c._queue.qsize() >= 1
        msg_obj = await c._queue.get()
        assert "status check" in msg_obj.text

    @pytest.mark.asyncio
    async def test_poll_loop_exits_on_cancelled(self, tmp_path):
        db = _make_db(tmp_path)
        c = _make_connector(bridge_db=db, poll_interval=1)
        c._queue = asyncio.Queue()
        c._running = True

        async def fake_sleep(_):
            raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=fake_sleep):
            await c._poll_loop()  # should not raise

        assert True  # reached here without exception

    @pytest.mark.asyncio
    async def test_poll_loop_handles_exception_gracefully(self, tmp_path):
        db = _make_db(tmp_path)
        c = _make_connector(bridge_db=db, poll_interval=1)
        c._queue = asyncio.Queue()
        c._running = True
        call_count = 0

        def bad_read():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB exploded")
            c._running = False
            return []

        c._read_events = bad_read

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = lambda _: asyncio.sleep(0)
            await c._poll_loop()  # must not raise


class TestSend:
    @pytest.mark.asyncio
    async def test_send_no_chat_id_is_noop(self):
        c = _make_connector()
        session = MagicMock()
        c._session = session
        await c.send(None, "no one home")
        session.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_posts_to_bridge(self):
        c = _make_connector()
        resp = MagicMock()
        resp.status = 200
        resp.text = AsyncMock(return_value="ok")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post.return_value = cm
        c._session = session

        await c.send("17087525462", "hello")
        session.post.assert_called_once()
        call_kwargs = session.post.call_args
        assert "/send" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_send_normalizes_jid_with_at_sign(self):
        c = _make_connector()
        sent_to = []
        resp = MagicMock()
        resp.status = 200
        resp.text = AsyncMock(return_value="ok")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)

        def capture(*args, **kwargs):
            sent_to.append(kwargs.get("json", {}).get("to", ""))
            return cm

        session = MagicMock()
        session.post.side_effect = capture
        c._session = session

        await c.send("17087525462@s.whatsapp.net", "test")
        assert sent_to[0] == "17087525462@s.whatsapp.net"

    @pytest.mark.asyncio
    async def test_send_strips_leading_plus(self):
        c = _make_connector()
        sent_to = []
        resp = MagicMock()
        resp.status = 200
        resp.text = AsyncMock(return_value="ok")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)

        def capture(*args, **kwargs):
            sent_to.append(kwargs.get("json", {}).get("to", ""))
            return cm

        session = MagicMock()
        session.post.side_effect = capture
        c._session = session

        await c.send("+17087525462", "test")
        # Should not start with +
        assert not sent_to[0].startswith("+")

    @pytest.mark.asyncio
    async def test_send_handles_http_error_gracefully(self):
        c = _make_connector()
        session = MagicMock()
        session.post.side_effect = Exception("connection refused")
        c._session = session
        # Should not raise
        await c.send("17087525462", "hello")


class TestMessages:
    @pytest.mark.asyncio
    async def test_messages_yields_from_queue(self):
        c = _make_connector()
        c._queue = asyncio.Queue()
        c._running = True
        from openclaw.connectors.base import Message
        c._queue.put_nowait(Message(text="wa_msg", source="whatsapp", chat_id="jid"))
        # Stop after one message
        collected = []
        async for msg in c.messages():
            collected.append(msg)
            c._running = False  # stop after first
        assert len(collected) == 1
        assert collected[0].text == "wa_msg"

    @pytest.mark.asyncio
    async def test_messages_exits_when_stopped_and_empty(self):
        c = _make_connector()
        c._queue = asyncio.Queue()
        c._running = False
        collected = []
        async for msg in c.messages():
            collected.append(msg)
        assert collected == []


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        c = _make_connector()
        with patch("aiohttp.ClientSession"), patch("asyncio.create_task"):
            await c.start()
        assert c._running is True

    @pytest.mark.asyncio
    async def test_stop_clears_running(self):
        c = _make_connector()
        c._running = True
        c._session = MagicMock()
        c._session.close = AsyncMock()
        task = asyncio.create_task(asyncio.sleep(1000))
        c._poll_task = task
        await c.stop()
        assert c._running is False
        assert task.cancelled()
