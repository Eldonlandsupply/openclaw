import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { LolaActionLogger } from "./action-logger.js";
import { ApprovalEngine } from "./approval-engine.js";
import { LOLA_CONFIG_DEFAULTS } from "./config/lola.config.js";
import {
  listApprovalQueue,
  listAuditLog,
  listDrafts,
  listMemoryFacts,
  listOpenLoops,
} from "./memory-store.js";
import { registerLola } from "./register-lola.js";
import { SendGate } from "./send-gate.js";

let tempDir: string | null = null;

afterEach(async () => {
  if (tempDir) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = null;
  }
});

async function makeWorkspace() {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-lola-phase2-"));
  return tempDir;
}

describe("lola phase 2 approvals and writes", () => {
  it("keeps write paths disabled by default", async () => {
    const workspaceDir = await makeWorkspace();
    const engine = new ApprovalEngine({ workspaceDir });
    const queue = await engine.requestWrite({
      agent: "memory",
      reason: "Promote durable fact",
      payload: {
        kind: "memory_fact",
        record: {
          id: "fact-1",
          factType: "preference",
          subject: "exec",
          value: "tea",
        },
      },
    });

    expect(LOLA_CONFIG_DEFAULTS.writeEnabled).toBe(false);
    expect(queue.status).toBe("blocked");
    expect(new SendGate().canQueueInternalWrite("memory")).toBe(false);
    expect(await listMemoryFacts(workspaceDir)).toEqual([]);
  });

  it("queues approved writes and materializes them only after approval", async () => {
    const workspaceDir = await makeWorkspace();
    const engine = new ApprovalEngine({
      workspaceDir,
      dryRun: true,
      writeEnabled: true,
      writeToggles: { inbox: true, memory: true, followthrough: true },
    });

    const draftPayload = {
      kind: "draft" as const,
      record: {
        id: "draft-1",
        draftType: "reply" as const,
        title: "Reply to board",
        body: "Detailed body",
        sourceAgent: "inbox",
      },
    };
    const queue = await engine.requestWrite({
      agent: "inbox",
      reason: "Draft reply is ready for approval",
      payload: draftPayload,
    });

    expect(queue.status).toBe("pending");
    expect(await listDrafts(workspaceDir)).toEqual([]);

    await engine.decide({
      queueId: queue.id,
      decidedBy: "operator",
      approved: true,
    });
    await engine.applyApprovedWrite(draftPayload, queue.id);

    const drafts = await listDrafts(workspaceDir);
    expect(drafts).toHaveLength(1);
    expect(drafts[0]?.approvalId).toBe(queue.id);
    expect(drafts[0]?.status).toBe("approved");

    const approvalQueue = await listApprovalQueue(workspaceDir);
    expect(approvalQueue.find((item) => item.id === queue.id)?.status).toBe("applied");
  });

  it("logs approval outcomes with redaction", async () => {
    const workspaceDir = await makeWorkspace();
    const logger = new LolaActionLogger(workspaceDir);
    await logger.log({
      event: "write_intent",
      agent: "memory",
      summary: "Attempted memory write",
      redactionApplied: false,
      details: {
        value: "private note",
        body: "sensitive body",
        nested: { notes: "secret" },
      },
    });

    const entries = await listAuditLog(workspaceDir);
    expect(entries).toHaveLength(1);
    expect(entries[0]?.redactionApplied).toBe(true);
    expect(entries[0]?.details).toEqual({
      value: "[REDACTED]",
      body: "[REDACTED]",
      nested: { notes: "[REDACTED]" },
    });
  });

  it("registers dashboard panels for approval surfaces", async () => {
    const registration = registerLola();
    expect(registration.readOnly).toBe(false);
    expect(registration.panels).toContain("Drafts awaiting approval");
    expect(registration.panels).toContain("Approval queue");
  });

  it("supports open loop writes after approval", async () => {
    const workspaceDir = await makeWorkspace();
    const engine = new ApprovalEngine({
      workspaceDir,
      dryRun: true,
      writeEnabled: true,
      writeToggles: { followthrough: true },
    });
    const payload = {
      kind: "open_loop" as const,
      record: {
        id: "loop-1",
        sourceType: "meeting",
        sourceRef: "event-1",
        summary: "Send revised model",
      },
    };

    const queue = await engine.requestWrite({
      agent: "followthrough",
      reason: "Track commitment follow-up",
      payload,
    });
    await engine.decide({
      queueId: queue.id,
      decidedBy: "operator",
      approved: true,
    });
    await engine.applyApprovedWrite(payload, queue.id);

    const loops = await listOpenLoops(workspaceDir);
    expect(loops[0]?.writeStatus).toBe("approved");
  });
});
