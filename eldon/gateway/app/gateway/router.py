"""
Intent router: deterministic, rule-based.
No LLM needed for safety classification.

Routing table:
  APPROVE         — confirmation token present
  STATUS          — health / ping / uptime keywords
  HELP            — help / commands / greeting
  CREATE_AGENT    — create/make/build agent
  SCHEDULE_TASK   — schedule / cron / every / at
  INGEST_ATTACH   — file attachment present or explicit attach keyword
  REPO_OP         — repo mutations: commit, push, merge, PR, deploy, implement,
                    fix, patch, write code, refactor, install, migrate, rollback
  DEV_QUERY       — read-only dev: tests, logs, diff, lint, check, review
  EXECUTE_TASK    — explicit run/execute/workflow verbs
  LLM_FALLBACK    — everything else (orchestrator handles via LLM)
"""

from __future__ import annotations

import re

from .models import GatewayRequest, Intent

# ── Keyword patterns ──────────────────────────────────────────────────────

_APPROVE_RE = re.compile(r"^approve\s+(\S+)$", re.IGNORECASE)

_STATUS_WORDS = {"status", "health", "healthcheck", "health_check", "ping", "uptime"}
_TASK_WORDS   = {"run", "execute", "workflow", "morning_brief", "brief",
                 "git_pull", "pull", "check_failed"}
_AGENT_WORDS  = {"create agent", "make agent", "build agent", "new agent", "create_agent"}
_SCHEDULE_WORDS = {"schedule", "cron", "at ", "every "}
_ATTACH_WORDS   = {"attach", "attachment", "file", "upload", "note", "ingest"}
_HELP_WORDS     = {"help", "commands", "what can", "hi", "hello"}

# Repo-mutation keywords (REPO_OP — may require approval path)
_REPO_OP_WORDS = {
    "commit", "push", "merge", "pull request", "open pr", "create pr",
    "deploy", "implement", "build ", "refactor", "rewrite", "patch",
    "write code", "write a", "add feature", "add ", "remove feature",
    "install package", "install dependency", "migrate", "rollback",
    "update the repo", "update repo", "change the code", "fix the bug",
    "fix bug", "fix ", "update code", "make changes", "apply changes",
    "integrate", "wire up", "wire ", "update ", "set up ", "setup ",
    "generate ", "create file", "create a file", "create the file",
    "write test", "write tests", "add test", "add tests",
    "edit ", "modify ", "rename ", "delete file", "remove file",
    "configure ", "enable feature", "disable feature", "bump version",
    "release ", "tag ", "publish ",
}

# Read-only dev queries (DEV_QUERY — safe to execute without approval)
_DEV_QUERY_WORDS = {
    "run tests", "run the tests", "run test", "check tests",
    "show diff", "git diff", "git log", "git status", "show log",
    "show logs", "view logs", "tail logs", "lint", "check lint",
    "review code", "code review", "what changed", "last commit",
    "show changes", "list files", "list branches", "show branch",
    "check branch", "test results", "test output", "build output",
    "ci status", "pipeline status",
}


def route(req: GatewayRequest) -> GatewayRequest:
    """
    Classify req.intent and extract req.action_name / req.action_args.
    Mutates and returns req.
    """
    text = req.normalized_text.lower().strip()

    # APPROVE — must check first
    m = _APPROVE_RE.match(text)
    if m:
        req.intent = Intent.APPROVE
        req.action_name = "approve"
        req.action_args = {"token": m.group(1)}
        req.route_reason = "approve_token_present"
        return req

    # STATUS
    if any(w in text for w in _STATUS_WORDS):
        req.intent = Intent.STATUS
        req.action_name = "status"
        req.route_reason = "keyword_status"
        return req

    # HELP
    if any(w in text for w in _HELP_WORDS):
        req.intent = Intent.HELP
        req.action_name = "help"
        req.route_reason = "keyword_help"
        return req

    # CREATE AGENT
    if any(w in text for w in _AGENT_WORDS):
        req.intent = Intent.CREATE_AGENT
        req.action_name = "create_agent"
        req.action_args = {"description": req.normalized_text}
        req.route_reason = "keyword_create_agent"
        return req

    # SCHEDULE
    if any(w in text for w in _SCHEDULE_WORDS):
        req.intent = Intent.SCHEDULE_TASK
        req.action_name = "schedule_task"
        req.action_args = {"description": req.normalized_text}
        req.route_reason = "keyword_schedule"
        return req

    # INGEST ATTACHMENT
    if req.attachments or any(w in text for w in _ATTACH_WORDS):
        req.intent = Intent.INGEST_ATTACHMENT
        req.action_name = "ingest_attachment"
        req.route_reason = "attachment_or_keyword"
        return req

    # DEV_QUERY — check before REPO_OP so read-only wins on overlap
    if any(w in text for w in _DEV_QUERY_WORDS):
        req.intent = Intent.DEV_QUERY
        req.action_name = "dev_query"
        req.action_args = {"description": req.normalized_text}
        req.route_reason = "keyword_dev_query"
        return req

    # REPO_OP — engineering mutations
    if any(w in text for w in _REPO_OP_WORDS):
        req.intent = Intent.REPO_OP
        req.action_name = "repo_op"
        req.action_args = {"description": req.normalized_text}
        req.route_reason = "keyword_repo_op"
        return req

    # EXECUTE TASK — explicit run/execute verbs
    if any(w in text for w in _TASK_WORDS):
        req.intent = Intent.EXECUTE_TASK
        parts = text.split()
        req.action_name = parts[0] if parts else "unknown"
        req.action_args = {"args": req.normalized_text}
        req.route_reason = "keyword_execute_task"
        return req

    # Everything else → LLM orchestrator (not hard error)
    req.intent = Intent.LLM_FALLBACK
    req.action_name = "llm_orchestrate"
    req.action_args = {"description": req.normalized_text}
    req.route_reason = "no_keyword_match_llm_fallback"
    return req
