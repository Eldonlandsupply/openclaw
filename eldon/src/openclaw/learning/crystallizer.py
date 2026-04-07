"""
Pattern Crystallizer — eldon/src/openclaw/learning/crystallizer.py

Observes agent workflow outcomes and detects high-frequency patterns
that warrant promotion to the action allowlist.

Ported concept from openclaw-foundry (MIT, lekt9/openclaw-foundry),
rewritten in Python for Eldon's asyncio runtime.

Key design rule: this module NEVER auto-executes or auto-approves.
Crystallized patterns are written to action_allowlist/action_candidates.json
for human review. The allowlist governance gates remain in full effect.

Reference: HexMachina artifact-centric learning + ADAS pattern extraction.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

MIN_USE_COUNT: int = 5
MIN_SUCCESS_RATE: float = 0.70

_CANDIDATES_PATH = (
    Path(__file__).resolve().parents[4] / "action_allowlist" / "action_candidates.json"
)
_OBSERVATIONS_PATH = (
    Path(__file__).resolve().parents[4]
    / "action_allowlist"
    / "_crystallizer_observations.json"
)


@dataclass
class WorkflowObservation:
    goal: str
    tool_sequence: list[str]
    outcome: Literal["success", "failure", "partial"]
    context: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class CrystallizedPattern:
    id: str
    name: str
    description: str
    trigger_pattern: str
    tool_sequence: list[str]
    use_count: int
    success_rate: float
    created_at: str
    status: Literal["candidate", "approved", "rejected"] = "candidate"
    source: str = "crystallizer"


class PatternCrystallizer:
    """
    Records workflow observations and emits crystallized pattern candidates
    when frequency and success rate thresholds are met.

    Usage:
        crystallizer = PatternCrystallizer()
        crystallizer.observe(WorkflowObservation(
            goal="send daily digest",
            tool_sequence=["memory_read", "gmail_send"],
            outcome="success",
        ))
        new_candidates = crystallizer.evaluate()
    """

    def __init__(
        self,
        candidates_path: Path = _CANDIDATES_PATH,
        observations_path: Path = _OBSERVATIONS_PATH,
        min_use_count: int = MIN_USE_COUNT,
        min_success_rate: float = MIN_SUCCESS_RATE,
    ) -> None:
        self.candidates_path = candidates_path
        self.observations_path = observations_path
        self.min_use_count = min_use_count
        self.min_success_rate = min_success_rate
        self._observations: list[WorkflowObservation] = []
        self._load_observations()

    def _load_observations(self) -> None:
        if self.observations_path.exists():
            try:
                raw = json.loads(self.observations_path.read_text(encoding="utf-8"))
                self._observations = [
                    WorkflowObservation(**r) for r in raw if isinstance(r, dict)
                ]
            except Exception as exc:
                logger.warning("crystallizer: could not load observations: %s", exc)
                self._observations = []

    def _save_observations(self) -> None:
        try:
            self.observations_path.parent.mkdir(parents=True, exist_ok=True)
            self.observations_path.write_text(
                json.dumps([asdict(o) for o in self._observations], indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("crystallizer: could not save observations: %s", exc)

    def _load_candidates(self) -> list[dict]:
        if self.candidates_path.exists():
            try:
                raw = json.loads(self.candidates_path.read_text(encoding="utf-8"))
                return raw if isinstance(raw, list) else []
            except Exception:
                return []
        return []

    def _save_candidates(self, candidates: list[dict]) -> None:
        try:
            self.candidates_path.parent.mkdir(parents=True, exist_ok=True)
            self.candidates_path.write_text(
                json.dumps(candidates, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("crystallizer: could not save candidates: %s", exc)

    def observe(self, obs: WorkflowObservation) -> None:
        """Record one workflow outcome. Call after each agent task completes."""
        self._observations.append(obs)
        self._save_observations()
        logger.debug(
            "crystallizer observation recorded",
            extra={"goal": obs.goal, "outcome": obs.outcome},
        )

    def evaluate(self) -> list[CrystallizedPattern]:
        """
        Scan observations for patterns that meet thresholds.
        New patterns are appended to action_candidates.json.
        Returns the list of newly emitted candidates this call.
        """
        groups: dict[str, list[WorkflowObservation]] = {}
        for obs in self._observations:
            key = _pattern_key(obs)
            groups.setdefault(key, []).append(obs)

        existing_candidates = self._load_candidates()
        existing_keys = {c.get("trigger_pattern") for c in existing_candidates}

        new_patterns: list[CrystallizedPattern] = []
        for key, observations in groups.items():
            if key in existing_keys:
                continue
            successes = sum(1 for o in observations if o.outcome == "success")
            rate = successes / len(observations) if observations else 0.0
            if (
                len(observations) >= self.min_use_count
                and rate >= self.min_success_rate
            ):
                pattern = _build_pattern(key, observations, rate)
                new_patterns.append(pattern)
                logger.info(
                    "crystallizer: new pattern candidate",
                    extra={"name": pattern.name, "use_count": pattern.use_count},
                )

        if new_patterns:
            updated = existing_candidates + [asdict(p) for p in new_patterns]
            self._save_candidates(updated)

        return new_patterns

    def summary(self) -> dict:
        groups: dict[str, list[WorkflowObservation]] = {}
        for obs in self._observations:
            groups.setdefault(_pattern_key(obs), []).append(obs)
        return {
            "total_observations": len(self._observations),
            "unique_patterns": len(groups),
            "patterns": [
                {
                    "key": key,
                    "count": len(obs),
                    "success_rate": (
                        sum(1 for o in obs if o.outcome == "success") / len(obs)
                        if obs
                        else 0.0
                    ),
                    "meets_threshold": (
                        len(obs) >= self.min_use_count
                        and (
                            sum(1 for o in obs if o.outcome == "success") / len(obs)
                            >= self.min_success_rate
                        )
                    ),
                }
                for key, obs in sorted(groups.items(), key=lambda kv: -len(kv[1]))
            ],
        }


def _pattern_key(obs: WorkflowObservation) -> str:
    goal_slug = obs.goal.lower().strip().replace(" ", "_")[:40]
    tool_sig = "|".join(obs.tool_sequence)
    return f"{goal_slug}::{tool_sig}"


def _build_pattern(
    key: str,
    observations: list[WorkflowObservation],
    success_rate: float,
) -> CrystallizedPattern:
    representative = observations[-1]
    goal_slug = representative.goal.strip()[:60]
    return CrystallizedPattern(
        id=str(uuid.uuid4()),
        name=f"crystallized::{key.split('::')[0]}",
        description=(
            f"Auto-detected pattern from {len(observations)} observations "
            f"({success_rate:.0%} success rate). Goal: {goal_slug}"
        ),
        trigger_pattern=key,
        tool_sequence=representative.tool_sequence,
        use_count=len(observations),
        success_rate=round(success_rate, 4),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
