"""Lola approval store."""

from __future__ import annotations
import os, threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from .models_import import LolaApprovalRequest, LolaApprovalStatus, LolaIntent

_STORE: dict = {}
_LOCK = threading.Lock()
_TTL = int(os.getenv("LOLA_APPROVAL_TTL_MINUTES", "60"))
_PATH = Path(os.getenv("LOLA_STORE_PATH", "/opt/openclaw/.lola")) / "approvals.jsonl"


def _persist(r: LolaApprovalRequest):
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PATH.open("a", encoding="utf-8") as f:
            f.write(r.model_dump_json() + "\n")
    except Exception:
        pass


def create(sender_id, thread_id, channel, intent, action_summary, action_payload) -> LolaApprovalRequest:
    expires = datetime.now(timezone.utc) + timedelta(minutes=_TTL)
    req = LolaApprovalRequest(
        sender_id=sender_id, thread_id=thread_id, channel=channel,
        intent=intent, action_summary=action_summary, action_payload=action_payload,
        expires_at=expires,
    )
    with _LOCK:
        _STORE[req.approval_id] = req
    _persist(req)
    return req


def resolve(approval_id, sender_id, grant) -> Optional[LolaApprovalRequest]:
    with _LOCK:
        req = _STORE.get(approval_id)
        if not req:
            return None
        if req.sender_id != sender_id:
            return None
        if req.status != LolaApprovalStatus.PENDING:
            return None
        now = datetime.now(timezone.utc)
        if req.expires_at and now > req.expires_at:
            req.status = LolaApprovalStatus.EXPIRED
            _persist(req)
            return None
        req.status = LolaApprovalStatus.APPROVED if grant else LolaApprovalStatus.DENIED
        req.decided_at = now
        del _STORE[approval_id]
    _persist(req)
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
        return result
