"""
Lola-specific data models extending the base gateway models.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field


class LolaIntent(str, Enum):
    STATUS_REQUEST = "status_request"
    CALENDAR_QUERY = "calendar_query"
    EMAIL_QUERY = "email_query"
    TASK_LIST = "task_list"
    MEMORY_RECALL = "memory_recall"
    BRIEFING_REQUEST = "briefing_request"
    FOLLOW_UP_LIST = "follow_up_list"
    EMAIL_DRAFT = "email_draft"
    TASK_DRAFT = "task_draft"
    MEETING_NOTE = "meeting_note"
    REMINDER_CREATE = "reminder_create"
    FOLLOW_UP_CREATE = "follow_up_create"
    EMAIL_SEND = "email_send"
    CALENDAR_MUTATION = "calendar_mutation"
    CRM_UPDATE = "crm_update"
    TASK_DELEGATE = "task_delegate"
    APPROVAL_GRANT = "approval_grant"
    APPROVAL_DENY = "approval_deny"
    MEMORY_CAPTURE = "memory_capture"
    URGENT_ESCALATION = "urgent_escalation"
    CHAT = "chat"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class RiskTier(str, Enum):
    READ_ONLY = "read_only"
    DRAFT_ONLY = "draft_only"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


class LolaApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class LolaApprovalRequest(BaseModel):
    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    sender_id: str
    thread_id: str
    channel: str
    intent: LolaIntent
    action_summary: str
    action_payload: dict = Field(default_factory=dict)
    status: LolaApprovalStatus = LolaApprovalStatus.PENDING
    decided_at: Optional[datetime] = None
    execution_receipt: Optional[str] = None


class LolaMemoryFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_channel: str
    source_thread_id: str
    fact_type: str
    subject: str
    content: str
    confidence: float = 1.0
    is_assumption: bool = False
    audit_source: str = ""


class LolaAuditRecord(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user: str
    channel: str
    thread_id: str
    message_id: Optional[str] = None
    intent: str
    risk_tier: str
    action_taken: str
    tools_used: list = Field(default_factory=list)
    approval_id: Optional[str] = None
    approval_result: Optional[str] = None
    execution_status: str
    error: Optional[str] = None
    retry_count: int = 0
    summary: str = ""


class LolaRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    channel: str
    sender_id: str
    sender_phone: str = ""
    thread_id: str
    message_id: Optional[str] = None
    raw_text: str = ""
    normalized_text: str = ""
    intent: LolaIntent = LolaIntent.UNKNOWN
    risk_tier: RiskTier = RiskTier.READ_ONLY
    confidence: float = 0.0
    requires_approval: bool = False
    approval_id: Optional[str] = None
    is_duplicate: bool = False
    context_facts: list = Field(default_factory=list)
