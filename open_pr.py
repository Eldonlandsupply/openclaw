#!/usr/bin/env python3
"""
OpenClaw PR Opener.
Opens a pull request from feature/imessage-notifier to main.
Usage: GITHUB_TOKEN=... python open_pr.py
"""

from __future__ import annotations

import getpass
import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "Eldonlandsupply/EldonOpenClaw"
TOKEN_ENV_VAR = "GITHUB_TOKEN"

PR_TITLE = "fix: OpenClaw audit - 16 reliability, security and architecture fixes"

PR_BODY = """## Summary

This PR delivers 16 targeted audit fixes across the OpenClaw agent system, addressing reliability, security, observability, and architectural correctness issues identified during the audit pass.

-----

## Changes by area

### Agents

- `agents/base_agent.py` - Enforce tool permission boundaries; agents can only invoke tools they are explicitly permitted to use
- `agents/orchestrator.py` - Add human-in-the-loop approval gate before risky task delegations
- `agents/agent_registry.py` - Enforce unique agent IDs; prevent silent duplicate registration

### Memory

- `memory/memory_manager.py` - Separate durable vs transient memory with TTL enforcement and expiry purging

### Hooks and Jobs

- `hooks/event_hooks.py` - Add idempotency keys to all hook invocations; prevent duplicate execution
- `jobs/job_runner.py` - Add retry logic with exponential backoff and dead-letter queue for failed jobs

### Security

- `security/secrets.py` - Centralize all secrets access; eliminate inline `os.environ` reads scattered across the codebase
- `dashboard/api_routes.py` - Add auth middleware to all dashboard API routes; reject unauthenticated requests with 401

### Audit and Observability

- `audit/audit_trail.py` - Make audit trail append-only with SHA-256 chained tamper detection
- `observability/logger.py` - Structured JSON logging with consistent schema across all agents and services
- `monitoring/health_check.py` - Structured health check endpoint covering all subsystems with degraded/error states

### Routing and Orchestration

- `routing/task_router.py` - Detect and prevent routing loops; raise on orphaned or unroutable tasks

### Collaboration and Silos

- `collaboration/silo_manager.py` - Enforce silo boundaries; block cross-silo agent collaboration at the permission layer

### Scheduling

- `cron/cron_manager.py` - Prevent duplicate cron job registration; add per-job enable/disable toggle

### Config

- `config/agent_schema.py` - Validate agent config schema at load time; fail fast on missing required fields

### Notifiers

- `notifiers/imessage_notifier.py` - Add retry logic, structured error handling, and logging to iMessage notifier

-----

## Testing

Each module is self-contained with clear interfaces. Unit tests should cover:

- Permission boundary enforcement on `BaseAgent`
- Approval gate flow on `Orchestrator`
- TTL expiry on `MemoryManager`
- Idempotency key deduplication on `EventHookRunner`
- Retry and dead-letter on `JobRunner`
- Tamper detection on `AuditTrail`

-----

## Risk

Low. All changes are additive or hardening existing interfaces. No breaking API changes. No database migrations required.
"""


def _decode_json_or_text(payload: bytes) -> dict:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        text = payload.decode("utf-8", errors="replace").strip()
        return {"message": text or "<non-JSON response body>"}


def _load_token() -> str:
    token = os.getenv(TOKEN_ENV_VAR, "").strip()
    if token:
        return token
    return getpass.getpass("GitHub token: ").strip()


def api(token: str, method: str, path: str, body: dict | None = None):
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req) as response:
            return _decode_json_or_text(response.read()), response.status
    except HTTPError as error:
        return _decode_json_or_text(error.read()), error.code


def main() -> None:
    token = _load_token()
    if not token:
        print(f"✗ Missing token. Set {TOKEN_ENV_VAR} or enter one when prompted.")
        sys.exit(1)

    print(f"\nOpening PR on {REPO}")
    print(f"  {PR_TITLE[:60]}...")

    data, status = api(
        token,
        "POST",
        f"/repos/{REPO}/pulls",
        {
            "title": PR_TITLE,
            "body": PR_BODY,
            "head": "feature/imessage-notifier",
            "base": "main",
            "draft": False,
        },
    )

    if status == 201:
        print("\n✓ PR opened successfully!")
        print(f"  URL:    {data['html_url']}")
        print(f"  Number: #{data['number']}")
        print(f"  Title:  {data['title']}")
    elif status == 422:
        errors = data.get("errors", [])
        for error in errors:
            if "already exists" in str(error):
                print("\n⚠ A PR for this branch already exists.")
                prs, _ = api(
                    token,
                    "GET",
                    (
                        "/repos/"
                        f"{REPO}/pulls?head=Eldonlandsupply:feature/imessage-notifier&state=open"
                    ),
                )
                if prs:
                    print(f"  Existing PR: {prs[0]['html_url']}")
            else:
                print(f"\n✗ Validation error: {error}")
    else:
        print(f"\n✗ Failed (HTTP {status})")
        print(f"  {data.get('message', data)}")
        if status == 404:
            print("  Check: repo name spelling, token has 'repo' scope")
        if status == 422:
            print("  Check: branch exists on remote, not already an open PR")


if __name__ == "__main__":
    main()
