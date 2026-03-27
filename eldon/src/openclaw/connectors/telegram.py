"""
Telegram connector — long-polls getUpdates, emits Message objects, sends replies.
No external library required; uses aiohttp (already a dep).

Hardening over v1:
- Startup validation: token format check + getMe self-test on start()
- sendMessage retry with exponential backoff (3 attempts)
- Structured logs never leak the bot token
- Explicit poll-task teardown on stop()
- send() chunking: Telegram max message length is 4096 chars
- Unknown chat_id: sends "Unauthorized" reply so the sender knows
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator

import aiohttp

from openclaw.connectors.base import BaseConnector, Message
from openclaw.logging import get_logger

logger = get_logger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{35,}$")
_MAX_MSG_LEN = 4096
_SEND_RETRIES = 3
_SEND_BACKOFF = (1.0, 2.0, 4.0)


def _validate_token(token: str) -> None:
    """Raise ValueError if token obviously does not look like a Telegram bot token."""
    if not token or not token.strip():
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")
    if not _TOKEN_RE.match(token.strip()):
        raise ValueError(
            f"TELEGRAM_BOT_TOKEN format looks wrong "
            f"(expected <digits>:<35+ alphanumeric chars>). "
            f"Got length={len(token)}"
        )


class TelegramConnector(BaseConnector):
    name = "telegram"

    def __init__(
        self,
        token: str,
        allowed_chat_ids: list[int],
        poll_timeout: int = 30,
    ) -> None:
        _validate_token(token)
        self._token = token.strip()
        self._allowed = set(allowed_chat_ids)
        self._poll_timeout = poll_timeout
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._offset = 0
        self._session: aiohttp.ClientSession | None = None
        self._poll_task: asyncio.Task | None = None

    def _url(self, method: str) -> str:
        return _API.format(token=self._token, method=method)

    async def _get_me(self) -> dict:
        """Call getMe to verify token is accepted by Telegram."""
        assert self._session is not None
        async with self._session.get(
            self._url("getMe"),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            data = await resp.json()
        if not data.get("ok"):
            raise RuntimeError(
                f"Telegram getMe failed — token rejected: {data.get('description', data)}"
            )
        return data["result"]

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        self._running = True

        # Self-test: verify token before entering poll loop
        try:
            me = await self._get_me()
            logger.info(
                "Telegram connector authenticated",
                extra={
                    "bot_username": me.get("username"),
                    "bot_id": me.get("id"),
                    "allowed_chat_ids": list(self._allowed),
                },
            )
        except Exception as exc:
            await self._session.close()
            self._running = False
            raise RuntimeError(f"Telegram startup failed: {exc}") from exc

        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        assert self._session is not None
        while self._running:
            try:
                async with self._session.get(
                    self._url("getUpdates"),
                    params={"offset": self._offset, "timeout": self._poll_timeout},
                    timeout=aiohttp.ClientTimeout(total=self._poll_timeout + 10),
                ) as resp:
                    data = await resp.json()
                if not data.get("ok"):
                    logger.warning("Telegram getUpdates error", extra={"data": data})
                    await asyncio.sleep(5)
                    continue
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Telegram poll error", extra={"error": str(exc)})
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        chat_id = msg["chat"]["id"]

        if self._allowed and chat_id not in self._allowed:
            logger.warning(
                "Telegram message from unauthorized chat_id",
                extra={"chat_id": chat_id},
            )
            # Notify sender instead of silently ignoring
            await self.send(str(chat_id), "Unauthorized. This bot is private.")
            return

        text = msg.get("text", "").strip()
        if not text:
            return

        logger.info(
            "Telegram message received",
            extra={"chat_id": chat_id, "text_len": len(text)},
        )
        await self._queue.put(Message(text=text, source="telegram", chat_id=str(chat_id)))

    async def messages(self) -> AsyncIterator[Message]:
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield item
            except asyncio.TimeoutError:
                if not self._running:
                    return

    async def send(self, chat_id: str | None, text: str) -> None:
        """Send text to chat_id with auto-chunking and retry on transient errors."""
        if not chat_id or not self._session:
            return
        chunks = [text[i: i + _MAX_MSG_LEN] for i in range(0, len(text), _MAX_MSG_LEN)]
        for chunk in chunks:
            await self._send_chunk(chat_id, chunk)

    async def _send_chunk(self, chat_id: str, text: str) -> None:
        assert self._session is not None
        for attempt, backoff in enumerate(_SEND_BACKOFF, start=1):
            try:
                async with self._session.post(
                    self._url("sendMessage"),
                    json={"chat_id": int(chat_id), "text": text},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        return
                    logger.warning(
                        "Telegram sendMessage failed",
                        extra={"status": resp.status, "attempt": attempt},
                    )
                    if resp.status in (400, 403):
                        return  # permanent errors, no point retrying
            except Exception as exc:
                logger.warning(
                    "Telegram send error",
                    extra={"error": str(exc), "attempt": attempt},
                )
            if attempt < _SEND_RETRIES:
                await asyncio.sleep(backoff)

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
        logger.info("Telegram connector stopped")
