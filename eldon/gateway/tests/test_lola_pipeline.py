"""Tests for Lola pipeline."""

from __future__ import annotations
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.lola.classifier import classify
from app.gateway.lola_models import LolaIntent, RiskTier
from app.lola.dedupe import is_duplicate


def test_status_intent():
    intent, tier, conf = classify("status")
    assert intent == LolaIntent.STATUS_REQUEST
    assert tier == RiskTier.READ_ONLY
    assert conf >= 0.9


def test_email_send_approval_required():
    intent, tier, _ = classify("send email to John")
    assert intent == LolaIntent.EMAIL_SEND
    assert tier == RiskTier.APPROVAL_REQUIRED


def test_reminder_draft():
    intent, tier, _ = classify("remind me to call Sarah tomorrow at 3pm")
    assert intent == LolaIntent.REMINDER_CREATE
    assert tier == RiskTier.DRAFT_ONLY


def test_approval_grant():
    intent, tier, _ = classify("approve AB12CD34")
    assert intent == LolaIntent.APPROVAL_GRANT
    assert tier == RiskTier.READ_ONLY


def test_approval_deny():
    intent, tier, _ = classify("deny AB12CD34")
    assert intent == LolaIntent.APPROVAL_DENY


def test_blocked_financial():
    _, tier, _ = classify("transfer money to account")
    assert tier == RiskTier.BLOCKED


def test_calendar_query():
    intent, tier, _ = classify("what's on my calendar today")
    assert intent == LolaIntent.CALENDAR_QUERY
    assert tier == RiskTier.READ_ONLY


def test_briefing():
    intent, _, _ = classify("give me my morning brief")
    assert intent == LolaIntent.BRIEFING_REQUEST


def test_calendar_mutation_approval():
    intent, tier, _ = classify("book meeting with David next Tuesday")
    assert intent == LolaIntent.CALENDAR_MUTATION
    assert tier == RiskTier.APPROVAL_REQUIRED


def test_dedupe_first_not_duplicate():
    assert is_duplicate("lola-unique-001") is False


def test_dedupe_second_is_duplicate():
    is_duplicate("lola-unique-002")
    assert is_duplicate("lola-unique-002") is True


def test_dedupe_different_not_duplicate():
    assert is_duplicate("lola-unique-003") is False
    assert is_duplicate("lola-unique-004") is False


def test_approval_create_and_resolve():
    from app.lola.approvals import create, resolve
    from app.gateway.lola_models import LolaApprovalStatus
    req = create(sender_id="+15550000001", thread_id="+15550000001",
                 channel="whatsapp", intent=LolaIntent.EMAIL_SEND,
                 action_summary="Send email to client",
                 action_payload={"to": "client@example.com"})
    assert req.status == LolaApprovalStatus.PENDING
    result = resolve(req.approval_id, "+15550000001", grant=True)
    assert result is not None
    assert result.status == LolaApprovalStatus.APPROVED


def test_approval_wrong_sender_rejected():
    from app.lola.approvals import create, resolve
    req = create(sender_id="+15550000002", thread_id="+15550000002",
                 channel="whatsapp", intent=LolaIntent.EMAIL_SEND,
                 action_summary="Test", action_payload={})
    result = resolve(req.approval_id, "+15559999999", grant=True)
    assert result is None


def test_approval_cannot_be_used_twice():
    from app.lola.approvals import create, resolve
    req = create(sender_id="+15550000003", thread_id="+15550000003",
                 channel="whatsapp", intent=LolaIntent.EMAIL_SEND,
                 action_summary="Double consume test", action_payload={})
    resolve(req.approval_id, "+15550000003", grant=True)
    result = resolve(req.approval_id, "+15550000003", grant=True)
    assert result is None
