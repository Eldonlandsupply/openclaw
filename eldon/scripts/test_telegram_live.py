#!/usr/bin/env python3
"""
scripts/test_telegram_live.py
Operator live-connection test for the Telegram bot.

Usage (from repo root, with .env loaded):
    cd /opt/openclaw
    python3 eldon/scripts/test_telegram_live.py

What it does:
    1. Validates TELEGRAM_BOT_TOKEN is set and well-formed
    2. Calls getMe to confirm the token is accepted by Telegram
    3. Calls getUpdates to confirm polling works
    4. Sends a test message to TELEGRAM_CHAT_ID (from env) if provided
    5. Prints a decision-grade pass/fail summary

Set env vars:
    TELEGRAM_BOT_TOKEN=<your token>
    TELEGRAM_CHAT_ID=<your chat id>  # optional but recommended
    TELEGRAM_ALLOWED_CHAT_IDS=<comma-separated ids>  # optional
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

try:
    import aiohttp
except ImportError:
    print("ERROR: aiohttp is not installed. Run: pip install aiohttp")
    sys.exit(1)

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{35,}$")
_API = "https://api.telegram.org/bot{token}/{method}"

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"


def _url(token: str, method: str) -> str:
    return _API.format(token=token, method=method)


async def run_checks() -> bool:
    results: list[tuple[str, bool, str]] = []
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    allowed_raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")

    # ── 1. Token present ──────────────────────────────────────────────────
    if not token:
        results.append(("Token present", False, "TELEGRAM_BOT_TOKEN is not set"))
    elif not _TOKEN_RE.match(token):
        results.append(("Token format", False, f"Token does not match expected format (len={len(token)})"))
    else:
        results.append(("Token present + format", True, f"length={len(token)}"))

    if not all(r[1] for r in results):
        _print_results(results)
        return False

    async with aiohttp.ClientSession() as session:
        # ── 2. getMe ──────────────────────────────────────────────────────
        try:
            async with session.get(_url(token, "getMe"), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
            if data.get("ok"):
                bot = data["result"]
                results.append((
                    "getMe (token valid)",
                    True,
                    f"@{bot.get('username')} id={bot.get('id')}",
                ))
            else:
                results.append(("getMe (token valid)", False, str(data.get("description"))))
                _print_results(results)
                return False
        except Exception as exc:
            results.append(("getMe (network)", False, str(exc)))
            _print_results(results)
            return False

        # ── 3. getUpdates ─────────────────────────────────────────────────
        try:
            async with session.get(
                _url(token, "getUpdates"),
                params={"timeout": 2},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                data = await resp.json()
            if data.get("ok"):
                n = len(data.get("result", []))
                results.append(("getUpdates (polling works)", True, f"{n} pending updates"))
            else:
                results.append(("getUpdates (polling works)", False, str(data)))
        except Exception as exc:
            results.append(("getUpdates", False, str(exc)))

        # ── 4. Allowed chat IDs configured ────────────────────────────────
        if allowed_raw.strip():
            try:
                ids = [int(x.strip()) for x in allowed_raw.split(",") if x.strip()]
                results.append(("TELEGRAM_ALLOWED_CHAT_IDS", True, f"{ids}"))
            except ValueError:
                results.append(("TELEGRAM_ALLOWED_CHAT_IDS", False, f"Cannot parse: {allowed_raw!r}"))
        else:
            results.append(("TELEGRAM_ALLOWED_CHAT_IDS", None, "NOT SET — bot will accept messages from anyone"))

        # ── 5. Send test message ──────────────────────────────────────────
        if chat_id:
            try:
                async with session.post(
                    _url(token, "sendMessage"),
                    json={"chat_id": int(chat_id), "text": "[OpenClaw] Live test ping — bot is reachable"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                if data.get("ok"):
                    results.append(("sendMessage to TELEGRAM_CHAT_ID", True, f"message_id={data['result']['message_id']}"))
                else:
                    results.append(("sendMessage", False, str(data.get("description"))))
            except Exception as exc:
                results.append(("sendMessage", False, str(exc)))
        else:
            results.append(("sendMessage", None, "TELEGRAM_CHAT_ID not set — skipped"))

    _print_results(results)
    return all(r[1] is not False for r in results)


def _print_results(results: list[tuple[str, bool | None, str]]) -> None:
    print()
    print("=" * 60)
    print("  Telegram Live Connection Test")
    print("=" * 60)
    for check, passed, detail in results:
        if passed is True:
            tag = PASS
        elif passed is False:
            tag = FAIL
        else:
            tag = WARN
        print(f"  {tag}  {check}: {detail}")
    print("=" * 60)
    all_pass = all(r[1] is not False for r in results)
    verdict = "PASS — bot is reachable and polling works" if all_pass else "FAIL — see issues above"
    print(f"  Verdict: {verdict}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    ok = asyncio.run(run_checks())
    sys.exit(0 if ok else 1)
