import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { ApprovalEngine } from "./approval-engine.js";
import { Executor } from "./executor.js";
import { listAuditLog, listExternalActions } from "./memory-store.js";
import { PolicyEngine } from "./policy-engine.js";
import { registerLola } from "./register-lola.js";

let tempDir: string | null = null;

afterEach(async () => {
  if (tempDir) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = null;
  }
});

async function makeWorkspace() {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-lola-phase3-"));
  return tempDir;
}

describe("lola phase 3 external action scaffolding", () => {
  it("registers the external actions surface", () => {
    expect(registerLola({ writeEnabled: true })).toMatchObject({
      surfaces: ["drafts", "approvalQueue", "memoryUpdates", "openLoops", "externalActions"],
    });
  });

  it("blocks high-risk external actions by policy", async () => {
    const workspaceDir = await makeWorkspace();
    const executor = new Executor(new PolicyEngine(0.5), new ApprovalEngine({ workspaceDir }), {
      workspaceDir,
      dryRun: true,
    });

    const result = await executor.execute(
      "send-risky",
      {
        draftId: "draft-9",
        subject: "Sensitive outreach",
        to: ["recipient@example.com"],
        body: "Test",
        risk: 0.9,
      },
      true,
    );

    expect(result).toMatchObject({ ok: false, reason: "blocked-by-policy" });
    const auditLog = await listAuditLog(workspaceDir);
    expect(auditLog.at(-1)?.event).toBe("external_action_blocked");
  });

  it("records dry-run external actions for Outlook", async () => {
    const workspaceDir = await makeWorkspace();
    const executor = new Executor(new PolicyEngine(0.5), new ApprovalEngine({ workspaceDir }), {
      workspaceDir,
      dryRun: true,
    });

    const result = await executor.execute(
      "send-safe",
      {
        draftId: "draft-10",
        subject: "Board update",
        to: ["board@example.com"],
        body: "Draft body",
        risk: 0.2,
      },
      true,
    );

    expect(result).toMatchObject({ ok: true, dryRun: true, externalRef: "dryrun:draft-10" });
    const actions = await listExternalActions(workspaceDir);
    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({ provider: "Outlook", status: "dry_run" });
  });
});
