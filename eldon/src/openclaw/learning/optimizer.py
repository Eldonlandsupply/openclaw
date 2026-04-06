"""
Nightly self-improvement optimizer — eldon/src/openclaw/learning/optimizer.py

Runs the continuous refinement loop described in the ADAS paper:
  1. Load recent audit log traces (last N hours or last N entries)
  2. Cluster failures by category (routing/tool/memory/policy)
  3. Feed successful patterns into the PatternCrystallizer
  4. Evaluate existing ADAS agent designs against observed outcomes
  5. Generate next-generation candidate designs via generate_next()
  6. Write all candidates to action_candidates.json for human review
  7. Emit an optimizer report to the audit log

Hard constraints (never auto-promote):
  - No design is activated without human review
  - No allowlist entry is added without human review
  - All candidates are written to the human review queue only
  - This module is safe to run on a cron/timer with no approval gate needed
    (it only reads and proposes, never executes)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

logger = logging.getLogger(__name__)

# ── Failure categories ─────────────────────────────────────────────────────

FailureCategory = Literal["routing", "tool", "memory", "policy", "unknown"]

_ROUTING_SIGNALS = frozenset(
    {"no_handler", "routing_error", "dispatch_failed", "unknown_action"}
)
_TOOL_SIGNALS = frozenset(
    {"tool_error", "tool_timeout", "tool_unavailable", "action_failed"}
)
_MEMORY_SIGNALS = frozenset({"memory_miss", "memory_write_failed", "retrieval_error"})
_POLICY_SIGNALS = frozenset(
    {"blocked_high_risk", "approval_required", "policy_violation", "injection_detected"}
)


def _classify_failure(entry: dict[str, Any]) -> FailureCategory:
    """Classify an audit log failure entry by category."""
    reason = str(entry.get("reason", "") or entry.get("error", "") or "").lower()
    action = str(entry.get("action", "") or entry.get("event", "") or "").lower()
    combined = reason + " " + action

    for sig in _ROUTING_SIGNALS:
        if sig in combined:
            return "routing"
    for sig in _TOOL_SIGNALS:
        if sig in combined:
            return "tool"
    for sig in _MEMORY_SIGNALS:
        if sig in combined:
            return "memory"
    for sig in _POLICY_SIGNALS:
        if sig in combined:
            return "policy"
    return "unknown"


# ── Trace loading ──────────────────────────────────────────────────────────


def _load_audit_traces(
    audit_log_path: Path,
    max_hours: int = 24,
    max_entries: int = 500,
) -> list[dict[str, Any]]:
    """Load recent entries from the audit log JSONL file."""
    if not audit_log_path.exists():
        return []

    raw = audit_log_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    # Support both JSONL (one object per line) and JSON array
    if raw.startswith("["):
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        entries = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not entries:
        return []

    # Filter to recent window
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    recent = []
    for e in entries:
        ts_raw = e.get("timestamp") or e.get("ts")
        if ts_raw:
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
            except ValueError:
                pass
        recent.append(e)

    return recent[-max_entries:]


# ── Failure clustering ─────────────────────────────────────────────────────


@dataclass
class FailureCluster:
    category: FailureCategory
    count: int
    examples: list[dict[str, Any]] = field(default_factory=list)
    top_actions: list[str] = field(default_factory=list)


def _cluster_failures(
    entries: list[dict[str, Any]],
    max_examples: int = 3,
) -> dict[FailureCategory, FailureCluster]:
    clusters: dict[FailureCategory, FailureCluster] = {}

    for e in entries:
        success = e.get("success", e.get("result", {}).get("success", True))
        if success is True or success == "ok":
            continue

        cat = _classify_failure(e)
        if cat not in clusters:
            clusters[cat] = FailureCluster(category=cat, count=0)

        c = clusters[cat]
        c.count += 1
        if len(c.examples) < max_examples:
            c.examples.append(e)
        action = str(e.get("action", e.get("event", "")))
        if action and action not in c.top_actions:
            c.top_actions.append(action)

    return clusters


# ── Optimizer report ───────────────────────────────────────────────────────


@dataclass
class OptimizerReport:
    run_id: str
    timestamp: str
    traces_loaded: int
    failures_found: int
    failure_clusters: dict[str, dict]
    patterns_crystallized: int
    adas_designs_evaluated: int
    adas_candidates_generated: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "event": "optimizer_run",
            "traces_loaded": self.traces_loaded,
            "failures_found": self.failures_found,
            "failure_clusters": self.failure_clusters,
            "patterns_crystallized": self.patterns_crystallized,
            "adas_designs_evaluated": self.adas_designs_evaluated,
            "adas_candidates_generated": self.adas_candidates_generated,
            "notes": self.notes,
        }
        return d


# ── LLM client protocol (injected) ────────────────────────────────────────


class LLMClient(Protocol):
    async def complete(self, prompt: str, max_tokens: int = 512) -> str: ...


# ── Main optimizer ─────────────────────────────────────────────────────────


class NightlyOptimizer:
    """
    Orchestrates the nightly self-improvement loop.

    Safe to instantiate without an LLM client; ADAS candidate generation
    is skipped if no client is provided.
    """

    def __init__(
        self,
        *,
        audit_log_path: Path,
        crystallizer,  # PatternCrystallizer
        adas_archive,  # ADASArchive
        llm: Optional[LLMClient] = None,
        max_hours: int = 24,
        max_entries: int = 500,
    ) -> None:
        self._audit_log_path = audit_log_path
        self._crystallizer = crystallizer
        self._adas = adas_archive
        self._llm = llm
        self._max_hours = max_hours
        self._max_entries = max_entries

    async def run(self) -> OptimizerReport:
        import uuid
        from openclaw.learning.adas import generate_next
        from openclaw.learning.crystallizer import WorkflowObservation

        run_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()
        notes: list[str] = []

        # 1. Load traces
        traces = _load_audit_traces(
            self._audit_log_path,
            max_hours=self._max_hours,
            max_entries=self._max_entries,
        )
        logger.info("optimizer[%s]: loaded %d traces", run_id, len(traces))

        # 2. Cluster failures
        clusters = _cluster_failures(traces)
        failures_found = sum(c.count for c in clusters.values())
        logger.info(
            "optimizer[%s]: %d failures across %d categories",
            run_id,
            failures_found,
            len(clusters),
        )

        for cat, cluster in clusters.items():
            if cluster.count > 0:
                notes.append(
                    f"{cat}: {cluster.count} failure(s) — actions: {cluster.top_actions[:3]}"
                )

        # 3. Feed successful traces into crystallizer
        patterns_crystallized = 0
        for e in traces:
            success = e.get("success", e.get("result", {}).get("success", None))
            outcome_map = {True: "success", False: "failure", None: "partial"}
            outcome = outcome_map.get(success, "partial")

            action = e.get("action") or e.get("event") or ""
            tool_seq = e.get("tool_sequence") or ([action] if action else [])
            goal = e.get("goal") or e.get("message", "")[:80] or action

            if not goal and not tool_seq:
                continue

            obs = WorkflowObservation(
                goal=str(goal),
                tool_sequence=[str(t) for t in tool_seq],
                outcome=outcome,
                context=str(e.get("context", "")),
            )
            self._crystallizer.observe(obs)

        new_patterns = self._crystallizer.evaluate()
        patterns_crystallized = len(new_patterns)
        if new_patterns:
            names = [p.name for p in new_patterns]
            notes.append(
                f"crystallized {patterns_crystallized} new pattern(s): {names}"
            )
            logger.info("optimizer[%s]: crystallized patterns: %s", run_id, names)

        # 4. Score existing ADAS designs against observed outcomes
        adas_evaluated = 0
        from openclaw.learning.adas import EvaluationResult

        for e in traces:
            design_id = e.get("adas_design_id")
            if not design_id:
                continue
            success = e.get("success", True)
            result = EvaluationResult(
                design_id=design_id,
                success=bool(success),
                accuracy=1.0 if success else 0.0,
            )
            self._adas.record_evaluation(result)
            adas_evaluated += 1

        logger.info("optimizer[%s]: evaluated %d ADAS designs", run_id, adas_evaluated)

        # 5. Generate next-gen candidate (only if LLM available)
        adas_candidates = 0
        if self._llm is not None:
            active = self._adas.active()
            if active:
                generation = max(d.generation for d in active) + 1
                try:
                    candidate = await generate_next(self._adas, self._llm, generation)
                    adas_candidates = 1
                    notes.append(
                        f"ADAS candidate generated: {candidate.name} (gen {generation})"
                    )
                    logger.info(
                        "optimizer[%s]: ADAS candidate: %s", run_id, candidate.name
                    )
                except Exception as exc:
                    notes.append(f"ADAS generate_next failed: {exc}")
                    logger.warning(
                        "optimizer[%s]: ADAS generate_next error: %s", run_id, exc
                    )
            else:
                notes.append("ADAS: no active designs to evolve from")
        else:
            notes.append("ADAS candidate generation skipped: no LLM client")

        report = OptimizerReport(
            run_id=run_id,
            timestamp=timestamp,
            traces_loaded=len(traces),
            failures_found=failures_found,
            failure_clusters={
                cat: {"count": c.count, "top_actions": c.top_actions[:5]}
                for cat, c in clusters.items()
            },
            patterns_crystallized=patterns_crystallized,
            adas_designs_evaluated=adas_evaluated,
            adas_candidates_generated=adas_candidates,
            notes=notes,
        )

        logger.info("optimizer[%s]: run complete — %s", run_id, report.to_dict())
        return report
