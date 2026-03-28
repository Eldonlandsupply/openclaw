import type { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";
import { resolveStateDir } from "../config/paths.js";
import { normalizeAgentId } from "../routing/session-key.js";
import { requireNodeSqlite } from "./sqlite.js";

export type SessionLifecycleState = "active" | "interrupted" | "completed";
export type SessionMemoryEventKind = "record" | "log" | "flag" | "task";
export type SessionTaskStatus = "todo" | "in_progress" | "done" | "blocked";

export type SessionMemoryEventInput = {
  sessionKey: string;
  kind: SessionMemoryEventKind;
  content: string;
  confidence?: number;
  taskKey?: string;
  taskStatus?: SessionTaskStatus;
  flagThread?: string;
  metadata?: Record<string, unknown>;
};

export type SessionMemoryContext = {
  sessionKey: string;
  sessionState: SessionLifecycleState;
  summary: string;
  recentEvents: Array<{
    id: number;
    kind: SessionMemoryEventKind;
    content: string;
    confidence: number | null;
    createdAt: number;
    taskKey: string | null;
    taskStatus: SessionTaskStatus | null;
  }>;
  unresolvedFlags: Array<{
    id: number;
    content: string;
    thread: string | null;
    createdAt: number;
  }>;
  estimatedTokens: number;
  truncated: boolean;
};

const VALID_STATE_TRANSITIONS: Record<SessionLifecycleState, Set<SessionLifecycleState>> = {
  active: new Set(["active", "interrupted", "completed"]),
  interrupted: new Set(["interrupted", "active", "completed"]),
  completed: new Set(["completed"]),
};

function nowTs(): number {
  return Date.now();
}

function clampConfidence(value?: number): number | null {
  if (value === undefined || Number.isNaN(value)) {
    return null;
  }
  return Math.min(1, Math.max(0, value));
}

function assertSessionKey(value: string): string {
  const sessionKey = value.trim();
  if (!sessionKey) {
    throw new Error("Session key must not be empty");
  }
  if (sessionKey.length > 256) {
    throw new Error("Session key too long");
  }
  return sessionKey;
}

function estimateTokensFromChars(chars: number): number {
  return Math.ceil(chars / 4);
}

export class SessionMemorySpine {
  private db: DatabaseSync;

  constructor(dbPath: string) {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    const { DatabaseSync } = requireNodeSqlite();
    this.db = new DatabaseSync(dbPath);
    this.db.exec("PRAGMA journal_mode=WAL;");
    this.db.exec("PRAGMA foreign_keys=ON;");
    this.ensureSchema();
  }

  close(): void {
    this.db.close();
  }

  startOrResumeSession(sessionKeyRaw: string): {
    sessionKey: string;
    state: SessionLifecycleState;
    resumedFromInterrupted: boolean;
  } {
    const sessionKey = assertSessionKey(sessionKeyRaw);
    const existing = this.db
      .prepare("SELECT state FROM sessions WHERE session_key = ?")
      .get(sessionKey) as { state: SessionLifecycleState } | undefined;
    if (!existing) {
      this.db
        .prepare(
          "INSERT INTO sessions(session_key, state, created_at, updated_at, last_heartbeat_at) VALUES(?, 'active', ?, ?, ?)",
        )
        .run(sessionKey, nowTs(), nowTs(), nowTs());
      return { sessionKey, state: "active", resumedFromInterrupted: false };
    }
    if (existing.state === "interrupted") {
      this.transitionSessionState(sessionKey, "active");
      return { sessionKey, state: "active", resumedFromInterrupted: true };
    }
    return { sessionKey, state: existing.state, resumedFromInterrupted: false };
  }

  touchHeartbeat(sessionKeyRaw: string): void {
    const sessionKey = assertSessionKey(sessionKeyRaw);
    this.startOrResumeSession(sessionKey);
    this.db
      .prepare("UPDATE sessions SET last_heartbeat_at = ?, updated_at = ? WHERE session_key = ?")
      .run(nowTs(), nowTs(), sessionKey);
  }

  transitionSessionState(sessionKeyRaw: string, nextState: SessionLifecycleState): void {
    const sessionKey = assertSessionKey(sessionKeyRaw);
    const row = this.db
      .prepare("SELECT state FROM sessions WHERE session_key = ?")
      .get(sessionKey) as { state: SessionLifecycleState } | undefined;
    if (!row) {
      throw new Error(`Session not found: ${sessionKey}`);
    }
    if (!VALID_STATE_TRANSITIONS[row.state].has(nextState)) {
      throw new Error(`Invalid state transition: ${row.state} -> ${nextState}`);
    }
    const endedAt = nextState === "completed" ? nowTs() : null;
    this.db
      .prepare(
        "UPDATE sessions SET state = ?, ended_at = COALESCE(?, ended_at), updated_at = ? WHERE session_key = ?",
      )
      .run(nextState, endedAt, nowTs(), sessionKey);
  }

  appendEvent(input: SessionMemoryEventInput): { id: number } {
    const sessionKey = assertSessionKey(input.sessionKey);
    const content = input.content.trim();
    if (!content) {
      throw new Error("Event content must not be empty");
    }
    this.startOrResumeSession(sessionKey);
    const stmt = this.db.prepare(
      "INSERT INTO events(session_key, kind, content, confidence, task_key, task_status, flag_thread, metadata_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
    );
    const confidence = clampConfidence(input.confidence);
    const info = stmt.run(
      sessionKey,
      input.kind,
      content,
      confidence,
      input.taskKey ?? null,
      input.taskStatus ?? null,
      input.flagThread ?? null,
      input.metadata ? JSON.stringify(input.metadata) : null,
      nowTs(),
    );
    this.db
      .prepare("UPDATE sessions SET updated_at = ? WHERE session_key = ?")
      .run(nowTs(), sessionKey);
    return { id: Number(info.lastInsertRowid) };
  }

  createCheckpoint(sessionKeyRaw: string, snapshot: Record<string, unknown>): { id: number } {
    const sessionKey = assertSessionKey(sessionKeyRaw);
    this.startOrResumeSession(sessionKey);
    const seqRow = this.db
      .prepare(
        "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM checkpoints WHERE session_key = ?",
      )
      .get(sessionKey) as { next_seq: number };
    const info = this.db
      .prepare(
        "INSERT INTO checkpoints(session_key, seq, snapshot_json, created_at) VALUES(?, ?, ?, ?)",
      )
      .run(sessionKey, seqRow.next_seq, JSON.stringify(snapshot), nowTs());
    return { id: Number(info.lastInsertRowid) };
  }

  listUnresolvedFlags(sessionKeyRaw: string): SessionMemoryContext["unresolvedFlags"] {
    const sessionKey = assertSessionKey(sessionKeyRaw);
    return this.db
      .prepare(
        "SELECT id, content, flag_thread, created_at FROM events WHERE session_key = ? AND kind = 'flag' AND resolved_at IS NULL ORDER BY created_at ASC",
      )
      .all(sessionKey) as SessionMemoryContext["unresolvedFlags"];
  }

  resolveFlag(flagId: number): void {
    this.db
      .prepare("UPDATE events SET resolved_at = ? WHERE id = ? AND kind = 'flag'")
      .run(nowTs(), flagId);
  }

  compactSession(params: {
    sessionKey: string;
    maxSourceEvents?: number;
    keepRecentEvents?: number;
  }): { compacted: boolean; summary: string; sourceEvents: number } {
    const sessionKey = assertSessionKey(params.sessionKey);
    const maxSourceEvents = Math.max(1, params.maxSourceEvents ?? 120);
    const keepRecentEvents = Math.max(5, params.keepRecentEvents ?? 30);
    const events = this.db
      .prepare(
        "SELECT id, kind, content, task_key, task_status, created_at FROM events WHERE session_key = ? ORDER BY id DESC LIMIT ?",
      )
      .all(sessionKey, maxSourceEvents + keepRecentEvents) as Array<{
      id: number;
      kind: SessionMemoryEventKind;
      content: string;
      task_key: string | null;
      task_status: SessionTaskStatus | null;
      created_at: number;
    }>;
    if (events.length <= keepRecentEvents) {
      const currentSummary = this.getSessionSummary(sessionKey);
      return { compacted: false, summary: currentSummary, sourceEvents: 0 };
    }

    const source = events.slice(keepRecentEvents).toReversed();
    const counts = source.reduce<Record<SessionMemoryEventKind, number>>(
      (acc, event) => {
        acc[event.kind] += 1;
        return acc;
      },
      { record: 0, log: 0, flag: 0, task: 0 },
    );
    const importantTasks = source
      .filter((event) => event.kind === "task" && event.task_key && event.task_status)
      .slice(-5)
      .map((event) => `- task ${event.task_key}: ${event.task_status}`);
    const openFlags = this.listUnresolvedFlags(sessionKey)
      .slice(0, 5)
      .map((flag) => `- ${flag.content}`);
    const summaryParts = [
      `Compaction at ${new Date().toISOString()}`,
      `Events summarized: ${source.length}`,
      `Counts: records=${counts.record}, logs=${counts.log}, flags=${counts.flag}, tasks=${counts.task}`,
      importantTasks.length > 0 ? `Recent task states:\n${importantTasks.join("\n")}` : "",
      openFlags.length > 0 ? `Open flags:\n${openFlags.join("\n")}` : "",
    ].filter(Boolean);
    const summary = summaryParts.join("\n\n");

    this.db
      .prepare(
        "INSERT INTO compactions(session_key, source_event_count, summary, created_at) VALUES(?, ?, ?, ?)",
      )
      .run(sessionKey, source.length, summary, nowTs());
    this.db
      .prepare("UPDATE sessions SET summary = ?, updated_at = ? WHERE session_key = ?")
      .run(summary, nowTs(), sessionKey);
    return { compacted: true, summary, sourceEvents: source.length };
  }

  assembleContext(params: {
    sessionKey: string;
    maxChars?: number;
    recentEventsLimit?: number;
    includeUnresolvedFlags?: boolean;
  }): SessionMemoryContext {
    const sessionKey = assertSessionKey(params.sessionKey);
    const maxChars = Math.max(512, params.maxChars ?? 6_000);
    const recentEventsLimit = Math.max(1, Math.min(200, params.recentEventsLimit ?? 25));
    const session = this.db
      .prepare("SELECT state, COALESCE(summary, '') AS summary FROM sessions WHERE session_key = ?")
      .get(sessionKey) as { state: SessionLifecycleState; summary: string } | undefined;
    if (!session) {
      throw new Error(`Session not found: ${sessionKey}`);
    }
    const recentEvents = this.db
      .prepare(
        "SELECT id, kind, content, confidence, created_at, task_key, task_status FROM events WHERE session_key = ? ORDER BY id DESC LIMIT ?",
      )
      .all(sessionKey, recentEventsLimit)
      .toReversed() as SessionMemoryContext["recentEvents"];
    const unresolvedFlags =
      params.includeUnresolvedFlags === false ? [] : this.listUnresolvedFlags(sessionKey);

    const lines = [
      session.summary ? `Summary:\n${session.summary}` : "Summary: (none)",
      "Recent events:",
      ...recentEvents.map((event) => {
        const confidence =
          typeof event.confidence === "number"
            ? ` [confidence=${event.confidence.toFixed(2)}]`
            : "";
        const taskSuffix =
          event.taskKey && event.taskStatus ? ` [task=${event.taskKey}:${event.taskStatus}]` : "";
        return `- ${event.kind}${confidence}${taskSuffix}: ${event.content}`;
      }),
      unresolvedFlags.length > 0
        ? `Unresolved flags:\n${unresolvedFlags.map((flag) => `- ${flag.content}`).join("\n")}`
        : "",
    ].filter(Boolean);

    let body = lines.join("\n");
    let truncated = false;
    if (body.length > maxChars) {
      body = body.slice(body.length - maxChars);
      truncated = true;
    }

    return {
      sessionKey,
      sessionState: session.state,
      summary: body,
      recentEvents,
      unresolvedFlags,
      estimatedTokens: estimateTokensFromChars(body.length),
      truncated,
    };
  }

  private getSessionSummary(sessionKey: string): string {
    const row = this.db
      .prepare("SELECT COALESCE(summary, '') AS summary FROM sessions WHERE session_key = ?")
      .get(sessionKey) as { summary: string } | undefined;
    return row?.summary ?? "";
  }

  private ensureSchema(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS sessions (
        session_key TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK(state IN ('active','interrupted','completed')),
        summary TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        last_heartbeat_at INTEGER,
        ended_at INTEGER
      );
      CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('record','log','flag','task')),
        content TEXT NOT NULL,
        confidence REAL,
        task_key TEXT,
        task_status TEXT CHECK(task_status IN ('todo','in_progress','done','blocked')),
        flag_thread TEXT,
        metadata_json TEXT,
        resolved_at INTEGER,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(session_key) REFERENCES sessions(session_key)
      );
      CREATE TABLE IF NOT EXISTS checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL,
        seq INTEGER NOT NULL,
        snapshot_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        UNIQUE(session_key, seq),
        FOREIGN KEY(session_key) REFERENCES sessions(session_key)
      );
      CREATE TABLE IF NOT EXISTS compactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL,
        source_event_count INTEGER NOT NULL,
        summary TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(session_key) REFERENCES sessions(session_key)
      );
      CREATE INDEX IF NOT EXISTS idx_spine_events_session ON events(session_key, id DESC);
      CREATE INDEX IF NOT EXISTS idx_spine_events_flags ON events(session_key, kind, resolved_at);
      CREATE INDEX IF NOT EXISTS idx_spine_checkpoints_session ON checkpoints(session_key, seq DESC);
    `);
  }
}

export function resolveSessionMemorySpineDbPath(agentId?: string): string {
  const normalizedAgentId = normalizeAgentId(agentId);
  const stateDir = resolveStateDir(process.env);
  return path.join(stateDir, "agents", normalizedAgentId, "memory-spine.sqlite");
}

export function createSessionMemorySpine(options?: {
  agentId?: string;
  dbPath?: string;
}): SessionMemorySpine {
  const dbPath = options?.dbPath?.trim() || resolveSessionMemorySpineDbPath(options?.agentId);
  return new SessionMemorySpine(dbPath);
}
