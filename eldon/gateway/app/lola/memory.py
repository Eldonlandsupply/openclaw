"""Lola memory layer — durable typed facts."""

from __future__ import annotations
import os, threading
from pathlib import Path
from typing import Optional
from .models_import import LolaMemoryFact

_FACTS: list = []
_LOCK = threading.Lock()
_MEM_PATH = Path(os.getenv("LOLA_STORE_PATH", "/opt/openclaw/.lola")) / "memory.jsonl"


def _load_from_disk():
    if not _MEM_PATH.exists():
        return
    try:
        with _MEM_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    _FACTS.append(LolaMemoryFact.model_validate_json(line))
    except Exception:
        pass


def _persist(fact: LolaMemoryFact):
    try:
        _MEM_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _MEM_PATH.open("a", encoding="utf-8") as f:
            f.write(fact.model_dump_json() + "\n")
    except Exception:
        pass


def record_fact(source_channel, source_thread_id, fact_type, subject, content,
                confidence=1.0, is_assumption=False, audit_source="") -> LolaMemoryFact:
    fact = LolaMemoryFact(
        source_channel=source_channel, source_thread_id=source_thread_id,
        fact_type=fact_type, subject=subject, content=content,
        confidence=confidence, is_assumption=is_assumption, audit_source=audit_source,
    )
    with _LOCK:
        _FACTS.append(fact)
    _persist(fact)
    return fact


def recall(subject: Optional[str] = None, fact_type: Optional[str] = None,
           limit: int = 10) -> list:
    with _LOCK:
        results = []
        for fact in reversed(_FACTS):
            if subject and subject.lower() not in fact.subject.lower() and subject.lower() not in fact.content.lower():
                continue
            if fact_type and fact.fact_type != fact_type:
                continue
            results.append(fact)
            if len(results) >= limit:
                break
        return results


_load_from_disk()
