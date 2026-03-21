"""Tests for the nightly optimizer."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

from openclaw.learning.optimizer import (
    NightlyOptimizer,
    _load_audit_traces,
    _cluster_failures,
    _classify_failure,
)
from openclaw.learning.crystallizer import PatternCrystallizer
from openclaw.learning.adas import ADASArchive


# ── Helpers ────────────────────────────────────────────────────────────────

def _ts(offset_hours: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=offset_hours)).isoformat()


def _make_entry(success: bool, action: str = "echo", reason: str = "", offset_hours: int = 0) -> dict:
    return {
        "timestamp": _ts(offset_hours),
        "action": action,
        "success": success,
        "reason": reason,
        "goal": f"test goal for {action}",
        "tool_sequence": [action],
    }


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def _write_json_array(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")


def _make_optimizer(tmp_path: Path, entries: list[dict], llm=None):
    audit = tmp_path / "audit_log.jsonl"
    _write_jsonl(audit, entries)
    crystallizer = PatternCrystallizer(
        candidates_path=tmp_path / "candidates.json",
        observations_path=tmp_path / "obs.json",
        min_use_count=2,
        min_success_rate=0.60,
    )
    adas = ADASArchive(path=tmp_path / "adas.json")
    return NightlyOptimizer(
        audit_log_path=audit,
        crystallizer=crystallizer,
        adas_archive=adas,
        llm=llm,
        max_hours=48,
    )


# ── _load_audit_traces ─────────────────────────────────────────────────────

class TestLoadAuditTraces:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "audit.jsonl"
        p.write_text("")
        assert _load_audit_traces(p) == []

    def test_missing_file(self, tmp_path: Path) -> None:
        assert _load_audit_traces(tmp_path / "missing.jsonl") == []

    def test_jsonl_format(self, tmp_path: Path) -> None:
        p = tmp_path / "audit.jsonl"
        entries = [_make_entry(True), _make_entry(False)]
        _write_jsonl(p, entries)
        result = _load_audit_traces(p)
        assert len(result) == 2

    def test_json_array_format(self, tmp_path: Path) -> None:
        p = tmp_path / "audit.json"
        entries = [_make_entry(True), _make_entry(False)]
        _write_json_array(p, entries)
        result = _load_audit_traces(p)
        assert len(result) == 2

    def test_old_entries_filtered(self, tmp_path: Path) -> None:
        p = tmp_path / "audit.jsonl"
        old = _make_entry(True, offset_hours=50)
        recent = _make_entry(True, offset_hours=1)
        _write_jsonl(p, [old, recent])
        result = _load_audit_traces(p, max_hours=24)
        assert len(result) == 1

    def test_max_entries_respected(self, tmp_path: Path) -> None:
        p = tmp_path / "audit.jsonl"
        entries = [_make_entry(True) for _ in range(20)]
        _write_jsonl(p, entries)
        result = _load_audit_traces(p, max_entries=5)
        assert len(result) == 5


# ── _classify_failure ──────────────────────────────────────────────────────

class TestClassifyFailure:
    def test_routing(self) -> None:
        assert _classify_failure({"reason": "routing_error"}) == "routing"

    def test_tool(self) -> None:
        assert _classify_failure({"reason": "tool_timeout"}) == "tool"

    def test_memory(self) -> None:
        assert _classify_failure({"reason": "memory_miss"}) == "memory"

    def test_policy(self) -> None:
        assert _classify_failure({"reason": "blocked_high_risk"}) == "policy"

    def test_unknown(self) -> None:
        assert _classify_failure({"reason": "something random"}) == "unknown"

    def test_action_field_used(self) -> None:
        assert _classify_failure({"action": "no_handler"}) == "routing"


# ── _cluster_failures ──────────────────────────────────────────────────────

class TestClusterFailures:
    def test_success_not_counted(self) -> None:
        entries = [_make_entry(True)]
        clusters = _cluster_failures(entries)
        total = sum(c.count for c in clusters.values())
        assert total == 0

    def test_failure_counted(self) -> None:
        entries = [_make_entry(False, reason="tool_error")]
        clusters = _cluster_failures(entries)
        assert clusters["tool"].count == 1

    def test_multiple_categories(self) -> None:
        entries = [
            _make_entry(False, reason="routing_error"),
            _make_entry(False, reason="tool_timeout"),
            _make_entry(False, reason="policy_violation"),
        ]
        clusters = _cluster_failures(entries)
        assert "routing" in clusters
        assert "tool" in clusters
        assert "policy" in clusters

    def test_examples_capped(self) -> None:
        entries = [_make_entry(False, reason="tool_error") for _ in range(10)]
        clusters = _cluster_failures(entries, max_examples=3)
        assert len(clusters["tool"].examples) == 3


# ── NightlyOptimizer ───────────────────────────────────────────────────────

class TestNightlyOptimizer:
    def test_empty_audit_log(self, tmp_path: Path) -> None:
        opt = _make_optimizer(tmp_path, [])
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        assert report.traces_loaded == 0
        assert report.failures_found == 0

    def test_traces_loaded(self, tmp_path: Path) -> None:
        entries = [_make_entry(True) for _ in range(5)]
        opt = _make_optimizer(tmp_path, entries)
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        assert report.traces_loaded == 5

    def test_failures_counted(self, tmp_path: Path) -> None:
        entries = [
            _make_entry(True),
            _make_entry(False, reason="tool_error"),
            _make_entry(False, reason="routing_error"),
        ]
        opt = _make_optimizer(tmp_path, entries)
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        assert report.failures_found == 2

    def test_crystallizer_receives_observations(self, tmp_path: Path) -> None:
        # 3 successful identical sequences should crystallize at threshold=2
        entries = [
            _make_entry(True, action="memory_read") for _ in range(3)
        ]
        opt = _make_optimizer(tmp_path, entries)
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        assert report.patterns_crystallized >= 1

    def test_report_has_run_id(self, tmp_path: Path) -> None:
        opt = _make_optimizer(tmp_path, [])
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        assert len(report.run_id) > 0

    def test_report_serializable(self, tmp_path: Path) -> None:
        opt = _make_optimizer(tmp_path, [_make_entry(True)])
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        d = report.to_dict()
        assert json.dumps(d)  # must be JSON-serializable

    def test_no_llm_skips_adas_generation(self, tmp_path: Path) -> None:
        opt = _make_optimizer(tmp_path, [], llm=None)
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        assert report.adas_candidates_generated == 0
        assert any("skipped" in n for n in report.notes)

    def test_failure_clusters_in_report(self, tmp_path: Path) -> None:
        entries = [_make_entry(False, reason="tool_timeout")]
        opt = _make_optimizer(tmp_path, entries)
        report = asyncio.get_event_loop().run_until_complete(opt.run())
        assert "tool" in report.failure_clusters
