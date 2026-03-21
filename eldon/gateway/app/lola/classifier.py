"""Lola intent classifier — deterministic keyword layer."""

from __future__ import annotations
import re
from typing import Tuple
from .models_import import LolaIntent, RiskTier

_APPROVE_RE = re.compile(r"^(?:approve|yes|confirm|ok|go ahead)[\s,]*([A-Z0-9]{8})?", re.IGNORECASE)
_DENY_RE = re.compile(r"^(?:deny|reject|cancel|no)[\s,]*([A-Z0-9]{8})?", re.IGNORECASE)

_CALENDAR_READ = {"calendar", "schedule", "meetings today", "what's on", "what is on", "agenda", "free time", "busy"}
_EMAIL_READ = {"inbox", "emails", "unread", "check email", "any messages", "email summary"}
_TASK_READ = {"open tasks", "task list", "pending tasks", "open loops", "follow ups", "follow-ups"}
_STATUS = {"status", "ping", "health", "uptime", "how are you", "lola status"}
_BRIEF = {"brief", "briefing", "morning brief", "daily brief", "summary", "recap", "day ahead"}

_DRAFT_EMAIL = {"draft email", "draft a reply", "write email", "compose email", "write back", "draft message"}
_REMINDER = {"remind me", "reminder", "set a reminder", "don't let me forget"}
_FOLLOW_UP = {"follow up", "follow-up", "check back", "circle back", "nudge"}
_MEETING_NOTE = {"note from meeting", "meeting notes", "capture notes", "from the call", "jot down"}
_TASK_CREATE = {"create task", "add task", "new task", "add to my list", "put on my list"}

_SEND_EMAIL = {"send email", "send it", "send that", "go ahead and send", "send the draft"}
_CALENDAR_WRITE = {"book meeting", "schedule meeting", "block time", "add to calendar", "cancel meeting", "reschedule"}
_CRM = {"update crm", "log in crm", "attio", "add note to", "contact update"}
_DELEGATE = {"delegate", "assign to", "send to team", "tell the team"}


def classify(text: str) -> Tuple[LolaIntent, RiskTier, float]:
    t = text.strip().lower()
    if _APPROVE_RE.match(t):
        return LolaIntent.APPROVAL_GRANT, RiskTier.READ_ONLY, 0.98
    if _DENY_RE.match(t):
        return LolaIntent.APPROVAL_DENY, RiskTier.READ_ONLY, 0.98
    if any(w in t for w in ("transfer money", "wire", "send payment", "delete all", "drop table", "rm -rf")):
        return LolaIntent.UNKNOWN, RiskTier.BLOCKED, 0.99
    if any(w in t for w in _SEND_EMAIL):
        return LolaIntent.EMAIL_SEND, RiskTier.APPROVAL_REQUIRED, 0.92
    if any(w in t for w in _CALENDAR_WRITE):
        return LolaIntent.CALENDAR_MUTATION, RiskTier.APPROVAL_REQUIRED, 0.88
    if any(w in t for w in _CRM):
        return LolaIntent.CRM_UPDATE, RiskTier.APPROVAL_REQUIRED, 0.88
    if any(w in t for w in _DELEGATE):
        return LolaIntent.TASK_DELEGATE, RiskTier.APPROVAL_REQUIRED, 0.85
    if any(w in t for w in _DRAFT_EMAIL):
        return LolaIntent.EMAIL_DRAFT, RiskTier.DRAFT_ONLY, 0.90
    if any(w in t for w in _REMINDER):
        return LolaIntent.REMINDER_CREATE, RiskTier.DRAFT_ONLY, 0.92
    if any(w in t for w in _FOLLOW_UP):
        return LolaIntent.FOLLOW_UP_CREATE, RiskTier.DRAFT_ONLY, 0.88
    if any(w in t for w in _MEETING_NOTE):
        return LolaIntent.MEETING_NOTE, RiskTier.DRAFT_ONLY, 0.88
    if any(w in t for w in _TASK_CREATE):
        return LolaIntent.TASK_DRAFT, RiskTier.DRAFT_ONLY, 0.90
    if any(w in t for w in _CALENDAR_READ):
        return LolaIntent.CALENDAR_QUERY, RiskTier.READ_ONLY, 0.92
    if any(w in t for w in _EMAIL_READ):
        return LolaIntent.EMAIL_QUERY, RiskTier.READ_ONLY, 0.90
    if any(w in t for w in _TASK_READ):
        return LolaIntent.TASK_LIST, RiskTier.READ_ONLY, 0.90
    if any(w in t for w in _STATUS):
        return LolaIntent.STATUS_REQUEST, RiskTier.READ_ONLY, 0.95
    if any(w in t for w in _BRIEF):
        return LolaIntent.BRIEFING_REQUEST, RiskTier.READ_ONLY, 0.92
    return LolaIntent.CHAT, RiskTier.READ_ONLY, 0.45
