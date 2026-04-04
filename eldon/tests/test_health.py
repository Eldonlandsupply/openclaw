"""
tests/test_health.py

Unit tests for the health server module (src/openclaw/health.py).

Covers:
 - record_tick() sets _last_tick
 - mark_degraded() sets _degraded flag and reason
 - record_connector_ok/degraded updates _connector_status
 - _compute_status(): ok, degraded via mark_degraded, degraded via stale tick,
   degraded via connector status
 - _handle_health request: returns JSON with correct fields, status 200/503
 - _handle_ready request: returns 200 when ok, 503 when degraded
 - _handle_ping: always 200 "pong"

Note: health module uses module-level globals. Tests reset them explicitly.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers: reset module globals before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_health_globals():
    import openclaw.health as h
    # Save originals
    orig_last_tick       = h._last_tick
    orig_degraded        = h._degraded
    orig_degraded_reason = h._degraded_reason
    orig_connector_status = dict(h._connector_status)
    orig_start_time      = h._start_time
    # Reset to clean state
    h._last_tick       = None
    h._degraded        = False
    h._degraded_reason = ""
    h._connector_status.clear()
    yield
    # Restore after test
    h._last_tick       = orig_last_tick
    h._degraded        = orig_degraded
    h._degraded_reason = orig_degraded_reason
    h._connector_status.clear()
    h._connector_status.update(orig_connector_status)


# ---------------------------------------------------------------------------
# record_tick
# ---------------------------------------------------------------------------

class TestRecordTick:
    def test_record_tick_sets_last_tick(self):
        import openclaw.health as h
        assert h._last_tick is None
        h.record_tick()
        assert h._last_tick is not None

    def test_record_tick_is_iso_format(self):
        import openclaw.health as h
        h.record_tick()
        # Must be parseable as ISO 8601
        dt = datetime.fromisoformat(h._last_tick.replace("Z", "+00:00"))
        assert dt is not None

    def test_record_tick_updates_on_repeated_calls(self):
        import openclaw.health as h
        h.record_tick()
        first = h._last_tick
        h.record_tick()
        assert h._last_tick >= first


# ---------------------------------------------------------------------------
# mark_degraded
# ---------------------------------------------------------------------------

class TestMarkDegraded:
    def test_mark_degraded_sets_flag(self):
        import openclaw.health as h
        assert h._degraded is False
        h.mark_degraded("disk full")
        assert h._degraded is True

    def test_mark_degraded_sets_reason(self):
        import openclaw.health as h
        h.mark_degraded("connector telegram dispatch error: timeout")
        assert "telegram" in h._degraded_reason

    def test_mark_degraded_no_reason(self):
        import openclaw.health as h
        h.mark_degraded()
        assert h._degraded is True
        assert h._degraded_reason == ""


# ---------------------------------------------------------------------------
# record_connector_ok / record_connector_degraded
# ---------------------------------------------------------------------------

class TestConnectorStatus:
    def test_record_connector_ok(self):
        import openclaw.health as h
        h.record_connector_ok("telegram")
        assert h._connector_status["telegram"] == "ok"

    def test_record_connector_degraded(self):
        import openclaw.health as h
        h.record_connector_degraded("whatsapp")
        assert h._connector_status["whatsapp"] == "degraded"

    def test_multiple_connectors(self):
        import openclaw.health as h
        h.record_connector_ok("telegram")
        h.record_connector_degraded("whatsapp")
        assert h._connector_status["telegram"] == "ok"
        assert h._connector_status["whatsapp"] == "degraded"


# ---------------------------------------------------------------------------
# _compute_status
# ---------------------------------------------------------------------------

class TestComputeStatus:
    def test_ok_when_fresh_tick_and_no_degraded(self):
        import openclaw.health as h
        h.record_tick()
        status, code = h._compute_status()
        assert status == "ok"
        assert code == 200

    def test_ok_when_no_tick_yet(self):
        """No tick yet is treated as ok (not stale — never started counting)."""
        import openclaw.health as h
        assert h._last_tick is None
        status, code = h._compute_status()
        assert status == "ok"
        assert code == 200

    def test_degraded_via_mark_degraded(self):
        import openclaw.health as h
        h.record_tick()
        h.mark_degraded("test failure")
        status, code = h._compute_status()
        assert status == "degraded"
        assert code == 503

    def test_degraded_via_stale_tick(self):
        import openclaw.health as h
        # Manually set a very old tick
        old = (datetime.now(timezone.utc).replace(
            year=2000)).isoformat()
        h._last_tick = old
        status, code = h._compute_status()
        assert status == "degraded"
        assert code == 503

    def test_degraded_via_connector_status(self):
        import openclaw.health as h
        h.record_tick()
        h.record_connector_degraded("telegram")
        status, code = h._compute_status()
        assert status == "degraded"
        assert code == 503

    def test_ok_with_all_connectors_ok(self):
        import openclaw.health as h
        h.record_tick()
        h.record_connector_ok("telegram")
        h.record_connector_ok("whatsapp")
        status, code = h._compute_status()
        assert status == "ok"
        assert code == 200


# ---------------------------------------------------------------------------
# _handle_health
# ---------------------------------------------------------------------------

class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_health_endpoint_returns_json(self):
        import openclaw.health as h
        h.record_tick()
        request = MagicMock()
        response = await h._handle_health(request)
        data = json.loads(response.text)
        assert "status" in data
        assert "uptime_s" in data
        assert "last_tick" in data
        assert "version" in data
        assert "connectors" in data

    @pytest.mark.asyncio
    async def test_health_endpoint_200_when_ok(self):
        import openclaw.health as h
        h.record_tick()
        request = MagicMock()
        response = await h._handle_health(request)
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_503_when_degraded(self):
        import openclaw.health as h
        h.record_tick()
        h.mark_degraded("intentional")
        request = MagicMock()
        response = await h._handle_health(request)
        assert response.status == 503
        data = json.loads(response.text)
        assert data["status"] == "degraded"
        assert data["reason"] == "intentional"

    @pytest.mark.asyncio
    async def test_health_endpoint_reason_empty_when_ok(self):
        import openclaw.health as h
        h.record_tick()
        request = MagicMock()
        response = await h._handle_health(request)
        data = json.loads(response.text)
        assert data["reason"] == ""


# ---------------------------------------------------------------------------
# _handle_ready
# ---------------------------------------------------------------------------

class TestHandleReady:
    @pytest.mark.asyncio
    async def test_ready_200_when_ok(self):
        import openclaw.health as h
        h.record_tick()
        request = MagicMock()
        response = await h._handle_ready(request)
        assert response.status == 200
        assert response.text == "ready"

    @pytest.mark.asyncio
    async def test_ready_503_when_degraded(self):
        import openclaw.health as h
        h.mark_degraded("intentional")
        request = MagicMock()
        response = await h._handle_ready(request)
        assert response.status == 503
        assert response.text == "not ready"


# ---------------------------------------------------------------------------
# _handle_ping
# ---------------------------------------------------------------------------

class TestHandlePing:
    @pytest.mark.asyncio
    async def test_ping_always_200(self):
        import openclaw.health as h
        h.mark_degraded("even degraded")
        request = MagicMock()
        response = await h._handle_ping(request)
        assert response.status == 200
        assert response.text == "pong"
