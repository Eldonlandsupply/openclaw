"""
Repository and development operations handler.

Routes engineering requests from Telegram to execution paths:
  - DEV_QUERY (read-only): git status, logs, test results, lint output
  - REPO_OP (mutation): commit, push, PR, deploy, implement, fix

All mutations require MEDIUM risk or higher — HIGH-risk ones (deploy, rollback,
destructive ops) will be intercepted by the pipeline confirmation gate before
this handler is called.

If the Pi executor is available (OPENCLAW_EXECUTOR_URL env), operations are
forwarded to it. Otherwise, git CLI operations are run directly (where safe)
and LLM is used to produce structured action plans for higher-level requests.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("gateway.repo_handler")

_EXECUTOR_URL = os.getenv("OPENCLAW_EXECUTOR_URL", "").strip()
_REPO_PATH    = os.getenv("OPENCLAW_REPO_PATH", "/opt/openclaw").strip()


async def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"Timeout after {timeout}s"
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


# ── Read-only dev queries ─────────────────────────────────────────────────

async def _git_status() -> str:
    rc, out, err = await _run(["git", "-C", _REPO_PATH, "status", "--short"])
    if rc != 0:
        return f"git status failed: {err.strip()[:300]}"
    return f"git status:\n{out.strip()[:800] or '(clean)'}"


async def _git_log(n: int = 5) -> str:
    rc, out, err = await _run([
        "git", "-C", _REPO_PATH, "log",
        f"--max-count={n}", "--oneline", "--no-decorate",
    ])
    if rc != 0:
        return f"git log failed: {err.strip()[:300]}"
    return f"Recent commits:\n{out.strip()[:800] or '(no commits)'}"


async def _git_diff() -> str:
    rc, out, err = await _run(["git", "-C", _REPO_PATH, "diff", "--stat"])
    if rc != 0:
        return f"git diff failed: {err.strip()[:300]}"
    return f"git diff --stat:\n{out.strip()[:800] or '(no unstaged changes)'}"


async def _run_tests() -> str:
    rc, out, err = await _run(
        ["python3", "-m", "pytest", "eldon/tests/", "-q", "--tb=short", "--no-header"],
        timeout=120,
    )
    combined = (out + err).strip()[:1200]
    status = "PASSED" if rc == 0 else "FAILED"
    return f"Tests {status} (rc={rc}):\n{combined}"


async def _show_logs(lines: int = 40) -> str:
    rc, out, err = await _run([
        "sudo", "journalctl", "-u", "openclaw", f"-n{lines}", "--no-pager",
    ])
    if rc != 0:
        return f"journalctl failed: {err.strip()[:300]}"
    return f"Last {lines} log lines:\n{out.strip()[:2000]}"


# ── Mutation helpers ──────────────────────────────────────────────────────

async def _git_pull() -> str:
    rc, out, err = await _run(["git", "-C", _REPO_PATH, "pull"])
    if rc == 0:
        return f"git pull OK: {out.strip()[:300] or 'already up to date'}"
    return f"git pull failed: {err.strip()[:300]}"


async def _llm_action_plan(description: str) -> str:
    """
    For complex repo/dev requests that can't be mapped to a single CLI command,
    generate a structured action plan via the Lola LLM.
    """
    from app.lola.executor import _llm as lola_llm
    prompt = (
        f"You are OpenClaw, an engineering-capable orchestrator running on a Raspberry Pi "
        f"for Eldon Land Supply (repo: Eldonlandsupply/openclaw, branch: main).\n\n"
        f"The operator has requested the following engineering task via Telegram:\n\n"
        f"  {description}\n\n"
        f"Respond with:\n"
        f"1. ROUTE: which execution path handles this "
        f"(git_cli / github_api / systemd / pip / shell_command / manual_required)\n"
        f"2. TOOL: exact command or API call (if deterministic)\n"
        f"3. RISK: LOW / MEDIUM / HIGH\n"
        f"4. NEXT STEP: what happens after this step\n"
        f"5. RESULT STATUS: what you're doing right now (executing / drafting_plan / "
        f"blocked_needs_approval / executor_offline)\n\n"
        f"Be concise. Do not say you cannot do things unless the executor is genuinely "
        f"offline or the operation requires a human."
    )
    return await lola_llm(prompt)


# ── Keyword dispatch ──────────────────────────────────────────────────────

_DEV_QUERY_DISPATCH = {
    "status":   _git_status,
    "git diff": _git_diff,
    "diff":     _git_diff,
    "log":      _git_log,
    "logs":     _show_logs,
    "journalctl": _show_logs,
    "test":     _run_tests,
    "tests":    _run_tests,
    "lint":     _run_tests,   # closest available, update when lint wired
}

_REPO_OP_DISPATCH = {
    "pull":     _git_pull,
    "git pull": _git_pull,
}


async def handle_repo_op(
    intent: str,
    description: str,
    channel: str = "telegram",
    **kwargs: Any,
) -> str:
    t = description.lower().strip()

    logger.info(
        "repo_handler_dispatch",
        extra={
            "event": "repo_handler_dispatch",
            "intent": intent,
            "description_snippet": description[:120],
            "channel": channel,
        },
    )

    # ── Read-only dev queries ─────────────────────────────────────────────
    if intent == "DEV_QUERY":
        for kw, fn in _DEV_QUERY_DISPATCH.items():
            if kw in t:
                result = await fn()
                logger.info(
                    "dev_query_result",
                    extra={"event": "dev_query_result", "kw": kw, "result_len": len(result)},
                )
                return result
        # No specific match — show git status as sensible default
        return await _git_status()

    # ── Repo mutations ────────────────────────────────────────────────────
    if intent == "REPO_OP":
        # Simple git pull — can do directly
        if "pull" in t or "git pull" in t:
            return await _git_pull()

        # For all other mutations: check if executor is available
        if _EXECUTOR_URL:
            # Forward to executor service
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{_EXECUTOR_URL}/execute",
                        json={"description": description, "channel": channel},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        data = await resp.json()
                        logger.info(
                            "executor_response",
                            extra={"event": "executor_response", "status": resp.status},
                        )
                        return data.get("result", str(data))
            except Exception as exc:
                logger.warning("Executor unavailable: %s — falling back to LLM plan", exc)
                # fall through to LLM plan below

        # No executor or executor offline — produce structured action plan via LLM
        plan = await _llm_action_plan(description)
        logger.info(
            "llm_action_plan_generated",
            extra={"event": "llm_action_plan_generated", "plan_len": len(plan)},
        )
        return plan

    # ── Shouldn't reach here ──────────────────────────────────────────────
    return await _llm_action_plan(description)
