import fs from "node:fs/promises";
import path from "node:path";
import type { LolaWriteConfig } from "./config/lola.config.js";
import type { ApprovalQueueItem } from "./schemas/approval-queue.js";
import type { MemoryFact } from "./schemas/memory-fact.js";
import type { OpenLoop } from "./schemas/open-loop.js";

export type LolaDraft = {
  id: string;
  title: string;
  body: string;
  kind: "reply" | "brief" | "follow_up" | "memory_update" | "audit";
  status: "pending_approval" | "approved" | "rejected" | "applied";
  proposedByAgent: string;
  approvalId: string;
  createdAt: string;
  updatedAt: string;
  externalAction: boolean;
};

type LolaApprovalStatus = NonNullable<ApprovalQueueItem["status"]>;

type LolaState = {
  version: 2;
  approvals: ApprovalQueueItem[];
  drafts: LolaDraft[];
  memoryFacts: MemoryFact[];
  openLoops: OpenLoop[];
};

type WriteTarget = "draft" | "memory" | "open_loop";

type ApprovalInput = {
  actionType: string;
  proposedByAgent: string;
  payloadSummary: string;
  reason?: string;
  sensitivity?: ApprovalQueueItem["sensitivity"];
  confidence?: number;
  payloadRef?: string;
};

type DraftInput = {
  id: string;
  title: string;
  body: string;
  kind: LolaDraft["kind"];
  proposedByAgent: string;
  externalAction?: boolean;
  reason?: string;
};

type MemoryInput = Omit<MemoryFact, "reviewStatus" | "createdAt" | "updatedAt"> & {
  proposedByAgent: string;
  reason?: string;
};

type OpenLoopInput = Omit<OpenLoop, "status" | "lastTouchAt"> & {
  proposedByAgent: string;
  reason?: string;
};

function assertWithinRoot(root: string, target: string) {
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Path escapes workspace root: ${target}`);
  }
}

function statePath(workspaceDir: string) {
  const root = path.resolve(workspaceDir);
  const dataDir = path.resolve(root, ".lola");
  const filePath = path.resolve(dataDir, "phase2-state.json");
  assertWithinRoot(root, dataDir);
  assertWithinRoot(root, filePath);
  return { dataDir, filePath };
}

async function loadState(workspaceDir: string): Promise<LolaState> {
  const { filePath } = statePath(workspaceDir);
  try {
    const raw = JSON.parse(await fs.readFile(filePath, "utf-8")) as Partial<LolaState>;
    return {
      version: 2,
      approvals: Array.isArray(raw.approvals) ? raw.approvals : [],
      drafts: Array.isArray(raw.drafts) ? raw.drafts : [],
      memoryFacts: Array.isArray(raw.memoryFacts) ? raw.memoryFacts : [],
      openLoops: Array.isArray(raw.openLoops) ? raw.openLoops : [],
    };
  } catch (err) {
    const code = (err as { code?: string }).code;
    if (code === "ENOENT") {
      return { version: 2, approvals: [], drafts: [], memoryFacts: [], openLoops: [] };
    }
    throw err;
  }
}

async function writeState(workspaceDir: string, state: LolaState) {
  const { dataDir, filePath } = statePath(workspaceDir);
  await fs.mkdir(dataDir, { recursive: true });
  const tmpPath = `${filePath}.${process.pid}.${Math.random().toString(16).slice(2)}.tmp`;
  await fs.writeFile(tmpPath, `${JSON.stringify(state, null, 2)}\n`, "utf-8");
  await fs.rename(tmpPath, filePath);
}

function requireWriteToggle(config: LolaWriteConfig, target: keyof LolaWriteConfig["toggles"]) {
  if (!config.writeEnabled) {
    throw new Error("LOLA write paths are disabled");
  }
  if (!config.toggles[target]) {
    throw new Error(`LOLA ${target} writes are disabled`);
  }
}

function makeApprovalId(target: WriteTarget, id: string) {
  return `${target}:${id}`;
}

function makeApproval(input: ApprovalInput, id: string, nowIso: string): ApprovalQueueItem {
  return {
    id,
    actionType: input.actionType,
    proposedByAgent: input.proposedByAgent,
    payloadSummary: input.payloadSummary,
    payloadRef: input.payloadRef,
    reason: input.reason,
    sensitivity: input.sensitivity ?? "medium",
    confidence: input.confidence,
    requiresHumanApproval: true,
    status: "pending",
    createdAt: nowIso,
    updatedAt: nowIso,
  };
}

function upsertApproval(state: LolaState, approval: ApprovalQueueItem) {
  const idx = state.approvals.findIndex((item) => item.id === approval.id);
  if (idx === -1) {
    state.approvals.push(approval);
    return;
  }
  state.approvals[idx] = approval;
}

export async function queueDraftForApproval(
  workspaceDir: string,
  config: LolaWriteConfig,
  input: DraftInput,
  now = new Date(),
): Promise<{ approval: ApprovalQueueItem; draft: LolaDraft }> {
  requireWriteToggle(config, "inbox");
  const nowIso = now.toISOString();
  const state = await loadState(workspaceDir);
  const approvalId = makeApprovalId("draft", input.id);
  const approval = makeApproval(
    {
      actionType: input.externalAction ? "external_send" : "internal_draft_write",
      proposedByAgent: input.proposedByAgent,
      payloadSummary: input.title,
      reason: input.reason,
      payloadRef: input.id,
    },
    approvalId,
    nowIso,
  );
  const draft: LolaDraft = {
    id: input.id,
    title: input.title.trim(),
    body: input.body,
    kind: input.kind,
    status: "pending_approval",
    proposedByAgent: input.proposedByAgent,
    approvalId,
    createdAt: nowIso,
    updatedAt: nowIso,
    externalAction: input.externalAction ?? false,
  };
  upsertApproval(state, approval);
  const draftIdx = state.drafts.findIndex((item) => item.id === draft.id);
  if (draftIdx === -1) {
    state.drafts.push(draft);
  } else {
    state.drafts[draftIdx] = draft;
  }
  await writeState(workspaceDir, state);
  return { approval, draft };
}

export async function queueMemoryFactForApproval(
  workspaceDir: string,
  config: LolaWriteConfig,
  input: MemoryInput,
  now = new Date(),
): Promise<{ approval: ApprovalQueueItem; fact: MemoryFact }> {
  requireWriteToggle(config, "memory");
  const nowIso = now.toISOString();
  const state = await loadState(workspaceDir);
  const approvalId = makeApprovalId("memory", input.id);
  const approval = makeApproval(
    {
      actionType: "memory_write",
      proposedByAgent: input.proposedByAgent,
      payloadSummary: `${input.subject}: ${input.value}`,
      reason: input.reason,
      payloadRef: input.id,
    },
    approvalId,
    nowIso,
  );
  const fact: MemoryFact = {
    ...input,
    proposedByAgent: input.proposedByAgent,
    approvalId,
    reviewStatus: "proposed",
    writeStatus: "pending_approval",
    createdAt: nowIso,
    updatedAt: nowIso,
  };
  upsertApproval(state, approval);
  const idx = state.memoryFacts.findIndex((item) => item.id === fact.id);
  if (idx === -1) {
    state.memoryFacts.push(fact);
  } else {
    state.memoryFacts[idx] = fact;
  }
  await writeState(workspaceDir, state);
  return { approval, fact };
}

export async function queueOpenLoopForApproval(
  workspaceDir: string,
  config: LolaWriteConfig,
  input: OpenLoopInput,
  now = new Date(),
): Promise<{ approval: ApprovalQueueItem; loop: OpenLoop }> {
  requireWriteToggle(config, "followthrough");
  const nowIso = now.toISOString();
  const state = await loadState(workspaceDir);
  const approvalId = makeApprovalId("open_loop", input.id);
  const approval = makeApproval(
    {
      actionType: "open_loop_write",
      proposedByAgent: input.proposedByAgent,
      payloadSummary: input.summary ?? input.id,
      reason: input.reason,
      payloadRef: input.id,
    },
    approvalId,
    nowIso,
  );
  const loop: OpenLoop = {
    ...input,
    proposedByAgent: input.proposedByAgent,
    approvalId,
    status: "pending_approval",
    writeStatus: "pending_approval",
    lastTouchAt: nowIso,
  };
  upsertApproval(state, approval);
  const idx = state.openLoops.findIndex((item) => item.id === loop.id);
  if (idx === -1) {
    state.openLoops.push(loop);
  } else {
    state.openLoops[idx] = loop;
  }
  await writeState(workspaceDir, state);
  return { approval, loop };
}

export async function updateApprovalStatus(params: {
  workspaceDir: string;
  approvalId: string;
  status: LolaApprovalStatus;
  now?: Date;
}): Promise<ApprovalQueueItem> {
  const nowIso = (params.now ?? new Date()).toISOString();
  const state = await loadState(params.workspaceDir);
  const idx = state.approvals.findIndex((item) => item.id === params.approvalId);
  if (idx === -1) {
    throw new Error(`Approval item not found: ${params.approvalId}`);
  }
  const updated: ApprovalQueueItem = {
    ...state.approvals[idx],
    status: params.status,
    updatedAt: nowIso,
    resolvedAt: params.status === "pending" ? undefined : nowIso,
  };
  state.approvals[idx] = updated;

  for (const draft of state.drafts) {
    if (draft.approvalId === params.approvalId) {
      draft.status =
        params.status === "approved"
          ? "approved"
          : params.status === "rejected"
            ? "rejected"
            : "pending_approval";
      draft.updatedAt = nowIso;
    }
  }
  for (const fact of state.memoryFacts) {
    if (fact.approvalId === params.approvalId) {
      fact.reviewStatus =
        params.status === "approved"
          ? "approved"
          : params.status === "rejected"
            ? "rejected"
            : "proposed";
      fact.writeStatus =
        params.status === "approved"
          ? "approved"
          : params.status === "rejected"
            ? "rejected"
            : "pending_approval";
      fact.updatedAt = nowIso;
    }
  }
  for (const loop of state.openLoops) {
    if (loop.approvalId === params.approvalId) {
      loop.status =
        params.status === "approved"
          ? "open"
          : params.status === "rejected"
            ? "rejected"
            : "pending_approval";
      loop.writeStatus =
        params.status === "approved"
          ? "approved"
          : params.status === "rejected"
            ? "rejected"
            : "pending_approval";
      loop.lastTouchAt = nowIso;
    }
  }

  await writeState(params.workspaceDir, state);
  return updated;
}

export async function getLolaWriteState(workspaceDir: string) {
  return loadState(workspaceDir);
}
