import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { SessionMemorySpine } from "./session-memory-spine.js";
import { requireNodeSqlite } from "./sqlite.js";

const tmpRoots: string[] = [];

function createSpine(): { spine: SessionMemorySpine; dbPath: string } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "openclaw-spine-"));
  tmpRoots.push(root);
  const dbPath = path.join(root, "spine.sqlite");
  return { spine: new SessionMemorySpine(dbPath), dbPath };
}

afterEach(() => {
  for (const root of tmpRoots.splice(0)) {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

const supportsNodeSqlite = (() => {
  try {
    requireNodeSqlite();
    return true;
  } catch {
    return false;
  }
})();

const describeIfSqlite = supportsNodeSqlite ? describe : describe.skip;

describeIfSqlite("SessionMemorySpine", () => {
  it("creates and resumes sessions with stable keys", () => {
    const { spine } = createSpine();
    const created = spine.startOrResumeSession("agent:main:direct:alice");
    expect(created.state).toBe("active");
    expect(created.resumedFromInterrupted).toBe(false);

    spine.transitionSessionState("agent:main:direct:alice", "interrupted");

    const resumed = spine.startOrResumeSession("agent:main:direct:alice");
    expect(resumed.state).toBe("active");
    expect(resumed.resumedFromInterrupted).toBe(true);
    spine.close();
  });

  it("records events, unresolved flags, and resolves flags", () => {
    const { spine } = createSpine();
    spine.startOrResumeSession("agent:main:direct:bob");
    spine.appendEvent({
      sessionKey: "agent:main:direct:bob",
      kind: "record",
      content: "picked plan A",
    });
    const flag = spine.appendEvent({
      sessionKey: "agent:main:direct:bob",
      kind: "flag",
      content: "Need legal approval",
      flagThread: "legal",
      confidence: 0.4,
    });
    let flags = spine.listUnresolvedFlags("agent:main:direct:bob");
    expect(flags).toHaveLength(1);
    expect(flags[0]?.thread).toBe("legal");

    spine.resolveFlag(flag.id);
    flags = spine.listUnresolvedFlags("agent:main:direct:bob");
    expect(flags).toHaveLength(0);
    spine.close();
  });

  it("creates checkpoints and supports interrupted session continuation", () => {
    const { spine } = createSpine();
    spine.startOrResumeSession("agent:main:group:ops");
    const checkpoint = spine.createCheckpoint("agent:main:group:ops", {
      openThreads: ["ops", "finance"],
      currentTask: "vendor-eval",
    });
    expect(checkpoint.id).toBeGreaterThan(0);

    spine.transitionSessionState("agent:main:group:ops", "interrupted");
    const resumed = spine.startOrResumeSession("agent:main:group:ops");
    expect(resumed.resumedFromInterrupted).toBe(true);
    spine.close();
  });

  it("compacts history and enforces context cap", () => {
    const { spine } = createSpine();
    const sessionKey = "agent:main:group:compaction";
    spine.startOrResumeSession(sessionKey);
    for (let i = 0; i < 90; i += 1) {
      spine.appendEvent({
        sessionKey,
        kind: i % 11 === 0 ? "task" : "log",
        content: `event-${i} ${"x".repeat(40)}`,
        taskKey: i % 11 === 0 ? `task-${i}` : undefined,
        taskStatus: i % 11 === 0 ? "in_progress" : undefined,
      });
    }
    const compacted = spine.compactSession({
      sessionKey,
      maxSourceEvents: 70,
      keepRecentEvents: 20,
    });
    expect(compacted.compacted).toBe(true);
    expect(compacted.sourceEvents).toBeGreaterThan(0);

    const context = spine.assembleContext({ sessionKey, maxChars: 500, recentEventsLimit: 40 });
    expect(context.truncated).toBe(true);
    expect(context.summary.length).toBeLessThanOrEqual(500);
    expect(context.estimatedTokens).toBeGreaterThan(0);
    spine.close();
  });

  it("persists data across restart", () => {
    const { spine, dbPath } = createSpine();
    const sessionKey = "agent:main:direct:restart";
    spine.startOrResumeSession(sessionKey);
    spine.appendEvent({
      sessionKey,
      kind: "task",
      content: "draft contract",
      taskKey: "contract",
      taskStatus: "todo",
    });
    spine.transitionSessionState(sessionKey, "interrupted");
    spine.close();

    const reopened = new SessionMemorySpine(dbPath);
    const resumed = reopened.startOrResumeSession(sessionKey);
    expect(resumed.resumedFromInterrupted).toBe(true);
    const context = reopened.assembleContext({ sessionKey, maxChars: 5000 });
    expect(context.recentEvents.some((event) => event.taskKey === "contract")).toBe(true);
    reopened.close();
  });
});
