import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { LOLA_CONFIG_DEFAULTS } from "./config/lola.config.js";
import {
  getLolaWriteState,
  queueDraftForApproval,
  queueMemoryFactForApproval,
  queueOpenLoopForApproval,
  updateApprovalStatus,
} from "./phase2-store.js";
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

describe("lola phase 2 approvals and write paths", () => {
  it("queues draft, memory, and open-loop writes behind approval", async () => {
    const workspace = await makeWorkspace();
    const config = {
      writeEnabled: true,
      toggles: LOLA_CONFIG_DEFAULTS.toggles,
    };

    const { approval: draftApproval, draft } = await queueDraftForApproval(workspace, config, {
      id: "draft-1",
      title: "Reply to board request",
      body: "Draft body",
      kind: "reply",
      proposedByAgent: "lola-inbox-agent",
      externalAction: true,
    });
    const { fact } = await queueMemoryFactForApproval(workspace, config, {
      id: "memory-1",
      factType: "relationship",
      subject: "Partner A",
      value: "Prefers Tuesday updates",
      proposedByAgent: "lola-memory-agent",
    });
    const { loop } = await queueOpenLoopForApproval(workspace, config, {
      id: "loop-1",
      sourceType: "meeting",
      sourceRef: "mtg-123",
      summary: "Confirm vendor timeline",
      proposedByAgent: "lola-followthrough-agent",
    });

    expect(draft.status).toBe("pending_approval");
    expect(draftApproval.status).toBe("pending");
    expect(fact.writeStatus).toBe("pending_approval");
    expect(loop.writeStatus).toBe("pending_approval");

    await updateApprovalStatus({
      workspaceDir: workspace,
      approvalId: draftApproval.id,
      status: "approved",
      now: new Date("2026-03-20T10:00:00.000Z"),
    });

    const state = await getLolaWriteState(workspace);
    expect(state.approvals).toHaveLength(3);
    expect(state.drafts[0]?.status).toBe("approved");
    expect(state.memoryFacts[0]?.approvalId).toBe("memory:memory-1");
    expect(state.openLoops[0]?.approvalId).toBe("open_loop:loop-1");
  });

  it("keeps dashboard write surfaces visible and send gate in dry run", () => {
    expect(registerLola({ writeEnabled: true })).toMatchObject({
      readOnly: false,
      surfaces: ["drafts", "approvalQueue", "memoryUpdates", "openLoops"],
    });

    const gate = new SendGate({
      writeEnabled: true,
      dryRun: true,
      approvalMode: "required",
    });
    expect(
      gate.approve({
        id: "draft:d-1",
        actionType: "external_send",
        proposedByAgent: "lola-inbox-agent",
        payloadSummary: "Send reply",
        status: "approved",
      }),
    ).toBe(false);
    expect(gate.requiresApproval()).toBe(true);
  });

  it("rejects disabled write toggles loudly", async () => {
    const workspace = await makeWorkspace();
    await expect(
      queueMemoryFactForApproval(
        workspace,
        {
          writeEnabled: true,
          toggles: { ...LOLA_CONFIG_DEFAULTS.toggles, memory: false },
        },
        {
          id: "memory-2",
          factType: "preference",
          subject: "Executive",
          value: "Morning briefings",
          proposedByAgent: "lola-memory-agent",
        },
      ),
    ).rejects.toThrow("LOLA memory writes are disabled");
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
