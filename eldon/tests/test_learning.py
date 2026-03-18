"""Tests for eldon/src/openclaw/learning/ — crystallizer and ADAS archive."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from openclaw.learning.crystallizer import PatternCrystallizer, WorkflowObservation
from openclaw.learning.adas import ADASArchive, AgentDesign, EvaluationResult


class TestCrystallizer:
    def _make(self, tmp_path: Path) -> PatternCrystallizer:
        return PatternCrystallizer(
            candidates_path=tmp_path / "candidates.json",
            observations_path=tmp_path / "obs.json",
            min_use_count=3,
            min_success_rate=0.60,
        )

    def _obs(self, outcome: str = "success") -> WorkflowObservation:
        return WorkflowObservation(
            goal="send daily digest",
            tool_sequence=["memory_read", "gmail_send"],
            outcome=outcome,
        )

    def test_observe_persists(self, tmp_path: Path) -> None:
        c = self._make(tmp_path)
        c.observe(self._obs())
        assert (tmp_path / "obs.json").exists()

    def test_below_threshold_no_candidate(self, tmp_path: Path) -> None:
        c = self._make(tmp_path)
        c.observe(self._obs())
        c.observe(self._obs())
        assert c.evaluate() == []

    def test_above_threshold_emits_candidate(self, tmp_path: Path) -> None:
        c = self._make(tmp_path)
        for _ in range(3):
            c.observe(self._obs("success"))
        new = c.evaluate()
        assert len(new) == 1
        assert new[0].status == "candidate"
        assert new[0].use_count == 3

    def test_candidate_written_to_file(self, tmp_path: Path) -> None:
        c = self._make(tmp_path)
        for _ in range(3):
            c.observe(self._obs("success"))
        c.evaluate()
        raw = json.loads((tmp_path / "candidates.json").read_text())
        assert len(raw) == 1
        assert raw[0]["source"] == "crystallizer"

    def test_duplicate_not_re_emitted(self, tmp_path: Path) -> None:
        c = self._make(tmp_path)
        for _ in range(3):
            c.observe(self._obs("success"))
        c.evaluate()
        assert c.evaluate() == []

    def test_high_failure_rate_blocks(self, tmp_path: Path) -> None:
        c = self._make(tmp_path)
        c.observe(self._obs("success"))
        c.observe(self._obs("failure"))
        c.observe(self._obs("failure"))
        assert c.evaluate() == []

    def test_summary_structure(self, tmp_path: Path) -> None:
        c = self._make(tmp_path)
        c.observe(self._obs())
        s = c.summary()
        assert "total_observations" in s
        assert s["total_observations"] == 1


class TestADASArchive:
    def _make(self, tmp_path: Path) -> ADASArchive:
        return ADASArchive(path=tmp_path / "archive.json", min_fitness=0.40)

    def _design(self) -> AgentDesign:
        return AgentDesign(
            id=str(uuid.uuid4()),
            name="Test",
            thought="test",
            system_prompt="test prompt",
            tool_filter=[],
            generation=1,
        )

    def test_seeds_on_first_run(self, tmp_path: Path) -> None:
        archive = self._make(tmp_path)
        assert len(archive.active()) >= 3

    def test_persists_and_reloads(self, tmp_path: Path) -> None:
        path = tmp_path / "archive.json"
        a1 = ADASArchive(path=path)
        count = len(a1.designs)
        a2 = ADASArchive(path=path)
        assert len(a2.designs) == count

    def test_top_k_sorted(self, tmp_path: Path) -> None:
        archive = self._make(tmp_path)
        scores = [d.fitness.wilson_lower for d in archive.top_k(3)]
        assert scores == sorted(scores, reverse=True)

    def test_add_candidate_not_active(self, tmp_path: Path) -> None:
        archive = self._make(tmp_path)
        baseline = len(archive.active())
        archive.add(self._design())
        assert len(archive.active()) == baseline

    def test_activate_promotes(self, tmp_path: Path) -> None:
        archive = self._make(tmp_path)
        d = self._design()
        archive.add(d)
        assert archive.activate(d.id) is True
        assert archive.get(d.id).status == "active"

    def test_evaluation_updates_count(self, tmp_path: Path) -> None:
        archive = self._make(tmp_path)
        d = archive.active()[0]
        orig = d.fitness.evaluation_count
        archive.record_evaluation(EvaluationResult(design_id=d.id, success=True, accuracy=1.0))
        assert archive.get(d.id).fitness.evaluation_count == orig + 1

    def test_low_fitness_retires(self, tmp_path: Path) -> None:
        archive = self._make(tmp_path)
        d = archive.active()[0]
        for _ in range(3):
            archive.record_evaluation(EvaluationResult(design_id=d.id, success=False, accuracy=0.0))
        assert archive.get(d.id).status == "retired"

    def test_summary_keys(self, tmp_path: Path) -> None:
        s = self._make(tmp_path).summary()
        for k in ("total", "active", "candidates", "retired", "top_3"):
            assert k in s
