"""
Lola SQLite persistence layer.
Replaces JSONL files. Thread-safe via threading.Lock on writes.
Initialised lazily on first use; safe to import before db path is configured.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DB_PATH = Path(os.getenv("LOLA_STORE_PATH", "/opt/openclaw/.lola")) / "lola.db"
_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id     TEXT PRIMARY KEY,
            created_at      TEXT NOT NULL,
            expires_at      TEXT,
            sender_id       TEXT NOT NULL,
            thread_id       TEXT NOT NULL,
            channel         TEXT NOT NULL,
            intent          TEXT NOT NULL,
            action_summary  TEXT NOT NULL,
            action_payload  TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            decided_at      TEXT,
            execution_receipt TEXT
        );
        CREATE TABLE IF NOT EXISTS memory_facts (
            fact_id         TEXT PRIMARY KEY,
            created_at      TEXT NOT NULL,
            source_channel  TEXT NOT NULL,
            source_thread   TEXT NOT NULL,
            fact_type       TEXT NOT NULL,
            subject         TEXT NOT NULL,
            content         TEXT NOT NULL,
            confidence      REAL NOT NULL DEFAULT 1.0,
            is_assumption   INTEGER NOT NULL DEFAULT 0,
            audit_source    TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_facts_type ON memory_facts(fact_type);
        CREATE INDEX IF NOT EXISTS idx_facts_subject ON memory_facts(subject);
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id        TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL,
            user            TEXT NOT NULL,
            channel         TEXT NOT NULL,
            thread_id       TEXT NOT NULL,
            message_id      TEXT,
            intent          TEXT NOT NULL,
            risk_tier       TEXT NOT NULL,
            action_taken    TEXT NOT NULL,
            tools_used      TEXT NOT NULL DEFAULT '[]',
            approval_id     TEXT,
            approval_result TEXT,
            execution_status TEXT NOT NULL,
            error           TEXT,
            retry_count     INTEGER NOT NULL DEFAULT 0,
            summary         TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user);
    """)
    c.commit()
    _conn = c
    return _conn


# ── Approvals ─────────────────────────────────────────────────────────────

def upsert_approval(a: dict) -> None:
    c = _get_conn()
    with _lock:
        c.execute("""
            INSERT INTO approvals VALUES (
                :approval_id,:created_at,:expires_at,:sender_id,:thread_id,
                :channel,:intent,:action_summary,:action_payload,:status,
                :decided_at,:execution_receipt
            ) ON CONFLICT(approval_id) DO UPDATE SET
                status=excluded.status,
                decided_at=excluded.decided_at,
                execution_receipt=excluded.execution_receipt
        """, {
            "approval_id": a["approval_id"],
            "created_at": a["created_at"],
            "expires_at": a.get("expires_at"),
            "sender_id": a["sender_id"],
            "thread_id": a["thread_id"],
            "channel": a["channel"],
            "intent": a["intent"] if isinstance(a["intent"], str) else a["intent"].value,
            "action_summary": a["action_summary"],
            "action_payload": json.dumps(a.get("action_payload", {})),
            "status": a["status"] if isinstance(a["status"], str) else a["status"].value,
            "decided_at": a.get("decided_at"),
            "execution_receipt": a.get("execution_receipt"),
        })
        c.commit()


def get_pending_approvals(sender_id: str) -> list[dict]:
    c = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    rows = c.execute("""
        SELECT * FROM approvals
        WHERE sender_id=? AND status='pending' AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY created_at DESC
    """, (sender_id, now)).fetchall()
    cols = [d[0] for d in c.execute("SELECT * FROM approvals LIMIT 0").description or
            [("approval_id",),("created_at",),("expires_at",),("sender_id",),("thread_id",),
             ("channel",),("intent",),("action_summary",),("action_payload",),("status",),
             ("decided_at",),("execution_receipt",)]]
    # Get column names via pragma
    cols = [r[1] for r in c.execute("PRAGMA table_info(approvals)").fetchall()]
    return [dict(zip(cols, row)) for row in rows]


def get_approval(approval_id: str) -> Optional[dict]:
    c = _get_conn()
    cols = [r[1] for r in c.execute("PRAGMA table_info(approvals)").fetchall()]
    row = c.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    return dict(zip(cols, row)) if row else None


# ── Memory facts ──────────────────────────────────────────────────────────

def insert_fact(f: dict) -> None:
    c = _get_conn()
    with _lock:
        c.execute("""
            INSERT OR IGNORE INTO memory_facts VALUES (
                :fact_id,:created_at,:source_channel,:source_thread,
                :fact_type,:subject,:content,:confidence,:is_assumption,:audit_source
            )
        """, {
            "fact_id": f["fact_id"],
            "created_at": f["created_at"],
            "source_channel": f["source_channel"],
            "source_thread": f.get("source_thread_id", ""),
            "fact_type": f["fact_type"],
            "subject": f["subject"],
            "content": f["content"],
            "confidence": f.get("confidence", 1.0),
            "is_assumption": int(f.get("is_assumption", False)),
            "audit_source": f.get("audit_source", ""),
        })
        c.commit()


def search_facts(subject: Optional[str] = None, fact_type: Optional[str] = None,
                 limit: int = 10) -> list[dict]:
    c = _get_conn()
    cols = [r[1] for r in c.execute("PRAGMA table_info(memory_facts)").fetchall()]
    q = "SELECT * FROM memory_facts WHERE 1=1"
    params: list = []
    if subject:
        q += " AND (subject LIKE ? OR content LIKE ?)"
        params += [f"%{subject}%", f"%{subject}%"]
    if fact_type:
        q += " AND fact_type=?"
        params.append(fact_type)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = c.execute(q, params).fetchall()
    return [dict(zip(cols, row)) for row in rows]


# ── Audit log ─────────────────────────────────────────────────────────────

def insert_audit(a: dict) -> None:
    c = _get_conn()
    with _lock:
        c.execute("""
            INSERT OR IGNORE INTO audit_log VALUES (
                :audit_id,:timestamp,:user,:channel,:thread_id,:message_id,
                :intent,:risk_tier,:action_taken,:tools_used,:approval_id,
                :approval_result,:execution_status,:error,:retry_count,:summary
            )
        """, {
            "audit_id": a["audit_id"],
            "timestamp": a["timestamp"],
            "user": a["user"],
            "channel": a["channel"],
            "thread_id": a["thread_id"],
            "message_id": a.get("message_id"),
            "intent": a["intent"],
            "risk_tier": a["risk_tier"],
            "action_taken": a["action_taken"],
            "tools_used": json.dumps(a.get("tools_used", [])),
            "approval_id": a.get("approval_id"),
            "approval_result": a.get("approval_result"),
            "execution_status": a["execution_status"],
            "error": a.get("error"),
            "retry_count": a.get("retry_count", 0),
            "summary": a.get("summary", ""),
        })
        c.commit()


def recent_audit(limit: int = 20) -> list[dict]:
    c = _get_conn()
    cols = [r[1] for r in c.execute("PRAGMA table_info(audit_log)").fetchall()]
    rows = c.execute(
        "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def stats() -> dict:
    c = _get_conn()
    total_facts = c.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
    pending_approvals = c.execute(
        "SELECT COUNT(*) FROM approvals WHERE status='pending'"
    ).fetchone()[0]
    total_audit = c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    last_action = c.execute(
        "SELECT timestamp, action_taken FROM audit_log ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    return {
        "total_facts": total_facts,
        "pending_approvals": pending_approvals,
        "total_audit_records": total_audit,
        "last_action_at": last_action[0] if last_action else None,
        "last_action": last_action[1] if last_action else None,
    }
