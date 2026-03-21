"""Lola audit logger."""

from __future__ import annotations
import os
from pathlib import Path
from .models_import import LolaAuditRecord

_AUDIT_PATH = Path(os.getenv("LOLA_STORE_PATH", "/opt/openclaw/.lola")) / "audit.jsonl"


def record(user, channel, thread_id, message_id, intent, risk_tier, action_taken,
           execution_status, tools_used=None, approval_id=None, approval_result=None,
           error=None, retry_count=0, summary="") -> LolaAuditRecord:
    rec = LolaAuditRecord(
        user=user, channel=channel, thread_id=thread_id, message_id=message_id,
        intent=intent, risk_tier=risk_tier, action_taken=action_taken,
        execution_status=execution_status, tools_used=tools_used or [],
        approval_id=approval_id, approval_result=approval_result,
        error=error, retry_count=retry_count, summary=summary,
    )
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(rec.model_dump_json() + "\n")
    except Exception:
        pass
    return rec
