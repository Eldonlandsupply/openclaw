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
  });
});
