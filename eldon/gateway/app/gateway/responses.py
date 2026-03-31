"""
Outbound response formatting.
Concise operational format for message channels.
"""

from __future__ import annotations

from .models import GatewayRequest


def format_response(
    req: GatewayRequest,
    result: str,
    confirm_token: str | None = None,
    next_step: str | None = None,
) -> str:
    lines = [
        f"Authenticated: {'YES' if req.authenticated else 'NO'}",
        f"Intent: {req.intent.value}",
        f"Risk: {req.risk_level.value}",
        f"Action: {req.action_name}",
        f"Result: {result}",
    ]

    if req.routed_to:
        lines.append(f"Route: {req.routed_to}")

    if confirm_token:
        lines.append(f"Reply exactly: APPROVE {confirm_token}")

    if next_step:
        lines.append(f"Next step: {next_step}")

    return "\n".join(lines)


def format_rejection(reason: str = "Unauthorized sender") -> str:
    return f"REJECTED: {reason}"


def format_error(msg: str) -> str:
    return f"ERROR: {msg}"


def format_fallback_unavailable(req: GatewayRequest, blocker: str = "") -> str:
    """
    Structured 'unavailable' message returned when the LLM orchestrator is
    unreachable. Differs from a hard ERROR — it reports the routing decision
    and specific blocker so the operator knows what failed and why.
    """
    lines = [
        f"Route: lola_orchestrator",
        f"Agent: llm",
        f"Intent: {req.intent.value}",
        f"Status: orchestrator_unavailable",
    ]
    if blocker:
        lines.append(f"Blocker: {blocker[:200]}")
    lines.append(
        "The LLM orchestrator is temporarily unreachable. "
        "Check MINIMAX_API_KEY is set and LLM_PROVIDER=minimax in /etc/openclaw/openclaw.env, "
        "then retry."
    )
    return "\n".join(lines)


def format_help(channel: str) -> str:
    cmds = [
        "status              — system health and queue summary",
        "health              — quick health check",
        "git pull            — pull latest repo (MEDIUM)",
        "run tests           — run test suite",
        "show logs           — tail journalctl logs",
        "git diff            — show unstaged changes",
        "git log             — recent commits",
        "restart openclaw    — (HIGH risk, requires APPROVE)",
        "run morning brief   — run morning brief workflow",
        "create agent <desc> — generate agent spec",
        "schedule <task>     — schedule a task",
        "help                — this message",
        "",
        "Engineering requests (repo changes, fixes, features):",
        "  Just describe what you need in plain English.",
        "  e.g. 'fix the Telegram routing bug' or 'implement X'",
        "  OpenClaw will classify, plan, and execute or draft an action plan.",
        "",
        "HIGH-risk commands require confirmation:",
        "  1. Send command",
        "  2. Receive: APPROVE <token>",
        "  3. Reply: APPROVE <token>",
    ]
    header = f"OpenClaw — Commands ({channel.upper()})"
    return header + "\n\n" + "\n".join(cmds)
