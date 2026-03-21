"""Lola memory layer — SQLite-backed typed facts with in-process cache."""

from __future__ import annotations

import os, threading
from pathlib import Path
from typing import Optional
from .models_import import LolaMemoryFact

_CACHE: list = []
_LOCK = threading.Lock()


def record_fact(source_channel, source_thread_id, fact_type, subject, content,
                confidence=1.0, is_assumption=False, audit_source="") -> LolaMemoryFact:
    fact = LolaMemoryFact(
        source_channel=source_channel, source_thread_id=source_thread_id,
        fact_type=fact_type, subject=subject, content=content,
        confidence=confidence, is_assumption=is_assumption, audit_source=audit_source,
    )
    try:
        from . import db
        db.insert_fact(fact.model_dump(mode="json"))
    except Exception:
        # JSONL fallback
        path = Path(os.getenv("LOLA_STORE_PATH", "/opt/openclaw/.lola")) / "memory.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(fact.model_dump_json() + "\n")
        except Exception:
            pass
    with _LOCK:
        _CACHE.append(fact)
    return fact


def recall(subject: Optional[str] = None, fact_type: Optional[str] = None,
           limit: int = 10) -> list:
    try:
        from . import db
        rows = db.search_facts(subject=subject, fact_type=fact_type, limit=limit)
        return [LolaMemoryFact(**{
            **r,
            "source_thread_id": r.get("source_thread", r.get("source_thread_id", "")),
            "is_assumption": bool(r.get("is_assumption", 0)),
        }) for r in rows]
    except Exception:
        # In-process cache fallback
        with _LOCK:
            results = []
            for fact in reversed(_CACHE):
                if subject and subject.lower() not in fact.subject.lower() and subject.lower() not in fact.content.lower():
                    continue
                if fact_type and fact.fact_type != fact_type:
                    continue
                results.append(fact)
                if len(results) >= limit:
                    break
            return results
