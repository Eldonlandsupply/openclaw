"""
WhatsApp connector — bridges to the local whatsmeow HTTP bridge.

The whatsmeow bridge runs on localhost:8181 and exposes:
  POST /send      -> send a message {to, text}
  GET  /status    -> {connected, logged_in}

Inbound messages are read directly from the bridge's SQLite DB
(whatsmeow_event_buffer table) since the bridge has no /messages
drain endpoint. Messages are consumed once processed and deleted
from the buffer to prevent redelivery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from typing import AsyncIterator

import aiohttp

from openclaw.connectors.base import BaseConnector, Message
from openclaw.logging import get_logger

logger = get_logger(__name__)

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8181"
DEFAULT_BRIDGE_DB = "/var/lib/wabridge/wabridge.db"

# Wabridge stores plaintext as protobuf-encoded bytes.
# We extract the message text by looking for the text payload
# embedded in the raw bytes — whatsmeow WebMessageInfo has the
# text body in a known field. We use a simple heuristic: find
# the longest UTF-8 printable string of length > 1 in the blob.


def _extract_text(plaintext: bytes) -> str:
    """
    Extract message text from whatsmeow plaintext bytes.
    The plaintext is a protobuf-encoded WebMessageInfo. Rather than
    pulling in a protobuf dependency, we scan for the conversation
    field (field 2, wire type 2 = length-delimited string).
    Falls back to longest printable ASCII run if protobuf parse fails.
    """
    try:
        # Protobuf field 2 wire type 2: tag = (2 << 3) | 2 = 0x12
        # Walk the bytes looking for 0x12 <varint-length> <utf8-text>
        i = 0
        candidates: list[str] = []
        while i < len(plaintext) - 2:
            if plaintext[i] == 0x12:
                i += 1
                # decode varint length
                length = 0
                shift = 0
                while i < len(plaintext):
                    b = plaintext[i]
                    i += 1
                    length |= (b & 0x7F) << shift
                    if not (b & 0x80):
                        break
                    shift += 7
                if 0 < length <= 4096 and i + length <= len(plaintext):
                    chunk = plaintext[i : i + length]
                    try:
                        s = chunk.decode("utf-8")
                        if s.isprintable() and len(s) > 1:
                            candidates.append(s)
                    except UnicodeDecodeError:
                        pass
                i += length
            else:
                i += 1
        if candidates:
            return max(candidates, key=len)
    except Exception:
        pass

    # Fallback: longest printable ASCII run
    best = ""
    current = ""
    for b in plaintext:
        if 0x20 <= b <= 0x7E:
            current += chr(b)
        else:
            if len(current) > len(best):
                best = current
            current = ""
    if len(current) > len(best):
        best = current
    return best if len(best) > 2 else ""


class WhatsAppConnector(BaseConnector):
    name = "whatsapp"

    def __init__(
        self,
        allowed_numbers: list[str],
        bridge_url: str = DEFAULT_BRIDGE_URL,
        bridge_db: str = DEFAULT_BRIDGE_DB,
        poll_interval: int = 5,
    ) -> None:
        self._allowed = set(allowed_numbers)
        self._bridge_url = bridge_url.rstrip("/")
        self._bridge_db = bridge_db
        self._poll_interval = poll_interval
        self._queue: asyncio.Queue | None = None
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None
        # Track processed event hashes to avoid redelivery across polls
        self._seen_hashes: set[bytes] = set()

    async def start(self) -> None:
        self._queue = asyncio.Queue()
        self._session = aiohttp.ClientSession()
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "WhatsApp connector started",
            extra={
                "bridge": self._bridge_url,
                "bridge_db": self._bridge_db,
                "allowed_numbers": list(self._allowed),
            },
        )

    def _read_events(self) -> list[dict]:
        """
        Read and consume pending events from whatsmeow_event_buffer.
        Opens a separate connection per poll to avoid threading issues
        with asyncio. Deletes consumed rows immediately.
        """
        results: list[dict] = []
        try:
            con = sqlite3.connect(self._bridge_db, timeout=3)
            con.row_factory = sqlite3.Row
            try:
                # Get all buffered events not yet seen
                rows = con.execute(
                    "SELECT our_jid, ciphertext_hash, plaintext, server_timestamp "
                    "FROM whatsmeow_event_buffer ORDER BY server_timestamp ASC"
                ).fetchall()

                hashes_to_delete: list[bytes] = []
                for row in rows:
                    h = bytes(row["ciphertext_hash"])
                    if h in self._seen_hashes:
                        hashes_to_delete.append(h)
                        continue
                    plaintext = row["plaintext"]
                    if not plaintext:
                        self._seen_hashes.add(h)
                        hashes_to_delete.append(h)
                        continue
                    text = _extract_text(bytes(plaintext))
                    if text:
                        results.append(
                            {
                                "our_jid": row["our_jid"],
                                "hash": h,
                                "text": text,
                                "timestamp": row["server_timestamp"],
                            }
                        )
                    self._seen_hashes.add(h)
                    hashes_to_delete.append(h)

                # Delete processed rows
                if hashes_to_delete:
                    con.executemany(
                        "DELETE FROM whatsmeow_event_buffer "
                        "WHERE our_jid=? AND ciphertext_hash=?",
                        [
                            (row["our_jid"], row_hash)
                            for row in rows
                            if (row_hash := bytes(row["ciphertext_hash"]))
                            in set(hashes_to_delete)
                        ],
                    )
                    con.commit()

                # Bound seen_hashes memory: keep last 500 only
                if len(self._seen_hashes) > 500:
                    self._seen_hashes = set(list(self._seen_hashes)[-500:])

            finally:
                con.close()
        except Exception as exc:
            logger.warning("WhatsApp DB read error", extra={"error": str(exc)})
        return results

    async def _poll_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                # Run blocking DB read in thread pool
                events = await loop.run_in_executor(None, self._read_events)
                for ev in events:
                    text = ev["text"].strip()
                    if not text:
                        continue
                    # our_jid is the linked device JID; derive sender from context
                    # Since wabridge doesn't expose per-message sender in the buffer,
                    # we route to the first allowed number as the implicit sender
                    # (single-user setup). For multi-user, extend wabridge.
                    sender = list(self._allowed)[0] if self._allowed else "unknown"
                    jid = sender.lstrip("+") + "@s.whatsapp.net"
                    logger.info(
                        "WhatsApp inbound event", extra={"text": text[:80], "jid": jid}
                    )
                    await self._queue.put(
                        Message(text=text, source="whatsapp", chat_id=jid)
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("WhatsApp poll loop error", extra={"error": str(exc)})
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def messages(self) -> AsyncIterator[Message]:
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield item
            except asyncio.TimeoutError:
                if not self._running:
                    return

    async def send(self, chat_id: str | None, text: str) -> None:
        if not chat_id:
            logger.warning("WhatsApp send called with no chat_id")
            return
        jid = chat_id if "@" in chat_id else f"{chat_id}@s.whatsapp.net"
        # Strip leading + from JID number part for wabridge
        if jid.startswith("+"):
            jid = jid[1:]
        try:
            async with self._session.post(
                f"{self._bridge_url}/send",
                json={"to": jid, "text": text},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                if body.strip() == "ok":
                    logger.info("WhatsApp sent", extra={"to": jid})
                else:
                    logger.error(
                        "WhatsApp send failed",
                        extra={"status": resp.status, "body": body[:200]},
                    )
        except Exception as exc:
            logger.error("WhatsApp send error", extra={"error": str(exc)})

    async def stop(self) -> None:
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
        self._poll_task = None
        self._session = None
