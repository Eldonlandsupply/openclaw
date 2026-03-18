"""
ADAS — Automated Design of Agentic Systems
eldon/src/openclaw/learning/adas.py

Implements a local, persistent agent design archive based on:
  "Automated Design of Agentic Systems" (arXiv:2408.08435)
  Shengran Hu, Cong Lu, Jeff Clune — ICLR 2025

Ported concept from openclaw-foundry (MIT, lekt9/openclaw-foundry),
rewritten for Eldon's Python/asyncio runtime.

Design rules for Eldon:
  - The archive is read-only at runtime. No agent design is auto-promoted.
  - New designs from generate_next() feed the human review queue only.
  - Evaluation is offline/scheduled, never inline on Pi.
  - The LLM client is injected; no direct API calls from this module.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_ARCHIVE_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "adas_archive.json"
)

DEFAULT_MIN_FITNESS: float = 0.40


class LLMClient(Protocol):
    async def complete(self, prompt: str, max_tokens: int = 512) -> str: ...


@dataclass
class AgentFitness:
    accuracy: float = 0.0
    confidence_low: float = 0.0
    confidence_high: float = 0.0
    evaluation_count: int = 0

    @property
    def wilson_lower(self) -> float:
        n = self.evaluation_count
        if n == 0:
            return 0.0
        p = self.accuracy
        z = 1.96
        denom = 1 + z**2 / n
        centre = p + z**2 / (2 * n)
        spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
        return (centre - spread) / denom


@dataclass
class AgentDesign:
    id: str
    name: str
    thought: str
    system_prompt: str
    tool_filter: list[str]
    generation: int | str
    fitness: AgentFitness = field(default_factory=AgentFitness)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    enabled: bool = True
    status: str = "candidate"
    notes: str = ""


@dataclass
class EvaluationResult:
    design_id: str
    success: bool
    accuracy: float
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _baseline_designs() -> list[AgentDesign]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        AgentDesign(
            id=str(uuid.uuid4()),
            name="Chain-of-Thought",
            thought="Break complex problems into explicit reasoning steps before committing to an answer or action.",
            system_prompt=(
                "Think step by step. Before taking any action or producing output, "
                "reason through the problem explicitly. Show your reasoning, then act."
            ),
            tool_filter=[],
            generation="initial",
            fitness=AgentFitness(accuracy=0.50, confidence_low=0.40, confidence_high=0.60),
            created_at=now,
            enabled=True,
            status="active",
        ),
        AgentDesign(
            id=str(uuid.uuid4()),
            name="Self-Consistency",
            thought="Generate multiple independent reasoning paths and take the majority answer.",
            system_prompt=(
                "Approach the problem from three independent angles before deciding. "
                "If two or more paths agree, use that answer. "
                "If they disagree, flag the uncertainty explicitly."
            ),
            tool_filter=[],
            generation="initial",
            fitness=AgentFitness(accuracy=0.60, confidence_low=0.50, confidence_high=0.70),
            created_at=now,
            enabled=True,
            status="active",
        ),
        AgentDesign(
            id=str(uuid.uuid4()),
            name="ReAct",
            thought="Interleave reasoning and tool use. Observe the result of each action before deciding the next step.",
            system_prompt=(
                "Reason, then act, then observe. "
                "After each tool call, reflect on the result before proceeding. "
                "Do not chain multiple tool calls without reasoning between them."
            ),
            tool_filter=[],
            generation="initial",
            fitness=AgentFitness(accuracy=0.65, confidence_low=0.55, confidence_high=0.75),
            created_at=now,
            enabled=True,
            status="active",
        ),
    ]


class ADASArchive:
    """
    Persistent, fitness-ranked archive of agent designs.
    Backed by data/adas_archive.json. Seeded with three baselines on first run.
    """

    def __init__(self, path: Path = _ARCHIVE_PATH, min_fitness: float = DEFAULT_MIN_FITNESS) -> None:
        self.path = path
        self.min_fitness = min_fitness
        self._designs: list[AgentDesign] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._designs = [_design_from_dict(r) for r in raw if isinstance(r, dict)]
                logger.info("adas archive loaded", extra={"count": len(self._designs)})
                return
            except Exception as exc:
                logger.warning("adas: could not load archive, seeding: %s", exc)
        self._designs = _baseline_designs()
        self._save()
        logger.info("adas archive seeded with %d baseline designs", len(self._designs))

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps([_design_to_dict(d) for d in self._designs], indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("adas: could not save archive: %s", exc)

    @property
    def designs(self) -> list[AgentDesign]:
        return list(self._designs)

    def active(self) -> list[AgentDesign]:
        return [d for d in self._designs if d.enabled and d.status == "active"]

    def top_k(self, k: int = 5) -> list[AgentDesign]:
        ranked = sorted(self.active(), key=lambda d: d.fitness.wilson_lower, reverse=True)
        return ranked[:k]

    def get(self, design_id: str) -> AgentDesign | None:
        for d in self._designs:
            if d.id == design_id:
                return d
        return None

    def add(self, design: AgentDesign) -> None:
        design.status = "candidate"
        self._designs.append(design)
        self._save()
        logger.info("adas: candidate design added", extra={"name": design.name})

    def record_evaluation(self, result: EvaluationResult) -> None:
        design = self.get(result.design_id)
        if design is None:
            logger.warning("adas: evaluation for unknown design %s", result.design_id)
            return
        f = design.fitness
        n = f.evaluation_count + 1
        f.accuracy = (f.accuracy * f.evaluation_count + result.accuracy) / n
        f.evaluation_count = n
        z = 1.96
        p = f.accuracy
        if n > 0:
            denom = 1 + z**2 / n
            centre = p + z**2 / (2 * n)
            spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
            f.confidence_low = round((centre - spread) / denom, 4)
            f.confidence_high = round((centre + spread) / denom, 4)
        if n >= 3 and f.wilson_lower < self.min_fitness:
            design.status = "retired"
            design.enabled = False
            logger.info("adas: design retired below fitness threshold", extra={"name": design.name})
        self._save()

    def activate(self, design_id: str) -> bool:
        design = self.get(design_id)
        if design is None:
            return False
        design.status = "active"
        design.enabled = True
        self._save()
        return True

    def retire(self, design_id: str) -> bool:
        design = self.get(design_id)
        if design is None:
            return False
        design.status = "retired"
        design.enabled = False
        self._save()
        return True

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self._designs),
            "active": len(self.active()),
            "candidates": sum(1 for d in self._designs if d.status == "candidate"),
            "retired": sum(1 for d in self._designs if d.status == "retired"),
            "top_3": [
                {"name": d.name, "fitness": round(d.fitness.wilson_lower, 3)}
                for d in self.top_k(3)
            ],
        }


async def generate_next(archive: ADASArchive, llm: LLMClient, generation: int) -> AgentDesign:
    """
    Ask the LLM to propose a new agent design based on the current archive.
    Returns a CANDIDATE — must be manually activated via archive.activate().
    Offline/scheduled use only.
    """
    top = archive.top_k(5)
    archive_summary = "\n".join(
        f"- {d.name} (fitness={d.fitness.wilson_lower:.2f}): {d.thought}"
        for d in top
    )
    prompt = f"""You are a meta-agent designing better AI agent systems.

Current top-performing designs:
{archive_summary}

Propose ONE new agent design that could outperform these.

Respond with JSON only, no markdown:
{{
  "name": "short descriptive name",
  "thought": "your reasoning about why this design will work better",
  "system_prompt": "the complete system prompt for this agent design",
  "tool_filter": []
}}"""

    raw = await llm.complete(prompt, max_tokens=512)
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"ADAS: LLM did not return valid JSON: {raw[:200]}")

    design = AgentDesign(
        id=str(uuid.uuid4()),
        name=str(data.get("name", f"generated-gen{generation}")),
        thought=str(data.get("thought", "")),
        system_prompt=str(data.get("system_prompt", "")),
        tool_filter=list(data.get("tool_filter", [])),
        generation=generation,
        status="candidate",
    )
    logger.info("adas: generated new candidate", extra={"name": design.name})
    return design


def _design_to_dict(d: AgentDesign) -> dict:
    return asdict(d)


def _design_from_dict(raw: dict) -> AgentDesign:
    fitness_raw = raw.get("fitness", {})
    fitness = AgentFitness(
        accuracy=fitness_raw.get("accuracy", 0.0),
        confidence_low=fitness_raw.get("confidence_low", 0.0),
        confidence_high=fitness_raw.get("confidence_high", 0.0),
        evaluation_count=fitness_raw.get("evaluation_count", 0),
    )
    return AgentDesign(
        id=raw.get("id", str(uuid.uuid4())),
        name=raw.get("name", "unknown"),
        thought=raw.get("thought", ""),
        system_prompt=raw.get("system_prompt", ""),
        tool_filter=raw.get("tool_filter", []),
        generation=raw.get("generation", "initial"),
        fitness=fitness,
        created_at=raw.get("created_at", datetime.now(timezone.utc).isoformat()),
        enabled=raw.get("enabled", True),
        status=raw.get("status", "candidate"),
        notes=raw.get("notes", ""),
    )
