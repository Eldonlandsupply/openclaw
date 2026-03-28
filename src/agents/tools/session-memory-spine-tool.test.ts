import os from "node:os";
import path from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { requireNodeSqlite } from "../../memory/sqlite.js";
import { createSessionMemorySpineTool } from "./session-memory-spine-tool.js";

const originalEnv = { ...process.env };

beforeEach(() => {
  process.env = { ...originalEnv };
  process.env.OPENCLAW_STATE_DIR = path.join(os.tmpdir(), `openclaw-tool-${Date.now()}`);
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

describeIfSqlite("session_memory_spine tool", () => {
  it("writes and retrieves structured context", async () => {
    const tool = createSessionMemorySpineTool({
      config: {
        model: "anthropic/claude-sonnet-4",
      } as never,
      agentSessionKey: "agent:main:direct:tool-test",
    });
    expect(tool).not.toBeNull();

    const started = await tool?.execute?.("1", { action: "start" });
    expect(started).toContain("active");

    await tool?.execute?.("2", {
      action: "record",
      kind: "flag",
      content: "Need procurement sign-off",
      confidence: 0.5,
    });

    const context = await tool?.execute?.("3", {
      action: "context",
      maxChars: 2048,
      recentEventsLimit: 10,
    });
    expect(context).toContain("Need procurement sign-off");
  });
});
