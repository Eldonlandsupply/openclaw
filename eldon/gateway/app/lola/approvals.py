"""Lola approval store — SQLite-backed with in-process pending cache."""

from __future__ import annotations

import os, threading
from datetime import datetime, timedelta, timezone
from typing import Optional
from .models_import import LolaApprovalRequest, LolaApprovalStatus, LolaIntent

_STORE: dict = {}
_LOCK = threading.Lock()
_TTL = int(os.getenv("LOLA_APPROVAL_TTL_MINUTES", "60"))


def create(sender_id, thread_id, channel, intent, action_summary, action_payload) -> LolaApprovalRequest:
    expires = datetime.now(timezone.utc) + timedelta(minutes=_TTL)
    req = LolaApprovalRequest(
        sender_id=sender_id, thread_id=thread_id, channel=channel,
        intent=intent, action_summary=action_summary, action_payload=action_payload,
        expires_at=expires,
    )
    with _LOCK:
        _STORE[req.approval_id] = req
    try:
        from . import db
        db.upsert_approval(req.model_dump(mode="json"))
    except Exception:
        pass
    return req


def resolve(approval_id, sender_id, grant) -> Optional[LolaApprovalRequest]:
    with _LOCK:
        req = _STORE.get(approval_id)
        if not req:
            # Try DB
            try:
                from . import db
                row = db.get_approval(approval_id)
                if row and row["sender_id"] == sender_id and row["status"] == "pending":
                    req = LolaApprovalRequest(**{
                        **row,
                        "action_payload": __import__("json").loads(row.get("action_payload", "{}")),
                        "status": LolaApprovalStatus(row["status"]),
                        "intent": LolaIntent(row["intent"]),
                    })
                else:
                    return None
            except Exception:
                return None
        if req.sender_id != sender_id:
            return None
        if req.status != LolaApprovalStatus.PENDING:
            return None
        now = datetime.now(timezone.utc)
        if req.expires_at and now > req.expires_at:
            req.status = LolaApprovalStatus.EXPIRED
            return None
        req.status = LolaApprovalStatus.APPROVED if grant else LolaApprovalStatus.DENIED
        req.decided_at = now
        if req.approval_id in _STORE:
            del _STORE[req.approval_id]
    try:
        from . import db
        db.upsert_approval(req.model_dump(mode="json"))
    except Exception:
        pass
    return req


def list_pending(sender_id) -> list:
    with _LOCK:
        now = datetime.now(timezone.utc)
        result = []
        for req in list(_STORE.values()):
            if req.sender_id != sender_id:
                continue
            if req.expires_at and now > req.expires_at:
                req.status = LolaApprovalStatus.EXPIRED
                continue
            if req.status == LolaApprovalStatus.PENDING:
                result.append(req)
    if not result:
        try:
            from . import db
            rows = db.get_pending_approvals(sender_id)
            for row in rows:
                result.append(LolaApprovalRequest(**{
                    **row,
                    "action_payload": __import__("json").loads(row.get("action_payload", "{}")),
                    "status": LolaApprovalStatus(row["status"]),
                    "intent": LolaIntent(row["intent"]),
                }))
        except Exception:
            pass
    return result
