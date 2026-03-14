import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  listDueCommitments,
  loadCommitments,
  resolveOpsMemoryPaths,
  transitionCommitmentStatus,
  upsertCommitment,
} from "./ops-memory.js";

let tempDir: string | null = null;

afterEach(async () => {
  if (tempDir) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = null;
  }
});

async function makeWorkspace() {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-lola-ops-"));
  return tempDir;
}

describe("lola ops memory", () => {
  it("upserts idempotently for same status", async () => {
    const workspace = await makeWorkspace();
    const now = new Date("2026-01-01T10:00:00.000Z");

    await upsertCommitment(
      workspace,
      { id: "c-1", title: "Prepare board packet", status: "open" },
      now,
    );
    await upsertCommitment(
      workspace,
      { id: "c-1", title: "Prepare board packet", status: "open", notes: "still pending" },
      new Date("2026-01-01T11:00:00.000Z"),
    );

    const items = await loadCommitments(workspace);
    expect(items).toHaveLength(1);
    expect(items[0]?.history).toHaveLength(1);
    expect(items[0]?.notes).toBe("still pending");
  });

  it("tracks status transition history", async () => {
    const workspace = await makeWorkspace();
    await upsertCommitment(workspace, { id: "c-2", title: "Finalize procurement brief" });

    const updated = await transitionCommitmentStatus({
      workspaceDir: workspace,
      id: "c-2",
      to: "in_progress",
      note: "review with COO",
      now: new Date("2026-01-02T09:30:00.000Z"),
    });

    expect(updated.status).toBe("in_progress");
    expect(updated.history).toHaveLength(2);
    expect(updated.history[1]?.from).toBe("open");
    expect(updated.history[1]?.to).toBe("in_progress");
    expect(updated.history[1]?.note).toBe("review with COO");
  });

  it("filters due commitments and excludes done by default", async () => {
    const workspace = await makeWorkspace();
    await upsertCommitment(workspace, {
      id: "c-3",
      title: "Call logistics partner",
      dueDate: "2026-01-02T10:00:00.000Z",
    });
    await upsertCommitment(workspace, {
      id: "c-4",
      title: "Sign PO",
      dueDate: "2026-01-02T09:00:00.000Z",
      status: "done",
    });

    const due = await listDueCommitments({
      workspaceDir: workspace,
      asOf: "2026-01-02T12:00:00.000Z",
    });
    expect(due.map((item) => item.id)).toEqual(["c-3"]);

    const dueWithDone = await listDueCommitments({
      workspaceDir: workspace,
      asOf: "2026-01-02T12:00:00.000Z",
      includeCompleted: true,
    });
    expect(dueWithDone.map((item) => item.id)).toEqual(["c-4", "c-3"]);
  });

  it("keeps ledger path scoped to workspace", async () => {
    const workspace = await makeWorkspace();
    const paths = resolveOpsMemoryPaths(workspace);
    expect(paths.ledgerPath.startsWith(path.resolve(workspace))).toBe(true);
  });
});
