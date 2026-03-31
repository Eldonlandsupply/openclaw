"""
Normalized inbound message model.
Both Telegram and SMS map into GatewayRequest before any routing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Channel(str, Enum):
    TELEGRAM = "telegram"
    SMS = "sms"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Intent(str, Enum):
    STATUS = "STATUS"
    EXECUTE_TASK = "EXECUTE_TASK"
    CREATE_AGENT = "CREATE_AGENT"
    SCHEDULE_TASK = "SCHEDULE_TASK"
    INGEST_ATTACHMENT = "INGEST_ATTACHMENT"
    APPROVE = "APPROVE"
    HELP = "HELP"
    # Engineering / repo work — routed to repo_handler
    REPO_OP = "REPO_OP"
    # Read-only dev queries (tests, logs, status checks) — routed to repo_handler
    DEV_QUERY = "DEV_QUERY"
    # Anything else that doesn't match a hard keyword — routed to LLM orchestrator
    LLM_FALLBACK = "LLM_FALLBACK"
    UNKNOWN = "UNKNOWN"


class RequestStatus(str, Enum):
    RECEIVED = "RECEIVED"
    AUTHENTICATED = "AUTHENTICATED"
    REJECTED = "REJECTED"
    PENDING_CONFIRM = "PENDING_CONFIRM"
    EXECUTING = "EXECUTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class AttachmentMeta(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    local_path: Optional[str] = None


class GatewayRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    channel: Channel
    sender_id: str
    sender_display: str = ""
    chat_id: str
    message_id: Optional[str] = None
    raw_text: str = ""
    normalized_text: str = ""
    attachments: list[AttachmentMeta] = Field(default_factory=list)
    authenticated: bool = False
    auth_method: str = "none"
    intent: Intent = Intent.UNKNOWN
    risk_level: RiskLevel = RiskLevel.LOW
    action_name: str = ""
    action_args: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    status: RequestStatus = RequestStatus.RECEIVED
    # Populated by pipeline to report routing decision in structured logs
    routed_to: str = ""
    route_reason: str = ""
