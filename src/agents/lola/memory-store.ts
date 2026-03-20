import type { MemoryFact } from "./schemas/memory-fact.js";
import type { OpenLoop } from "./schemas/open-loop.js";

export type DraftStatus = "pending_approval" | "approved" | "denied";

export type DraftRecord = {
  id: string;
  text: string;
  status: DraftStatus;
  relatedIds?: string[];
  createdAt: string;
  updatedAt: string;
};

export type MemoryFactRecord = MemoryFact & {
  createdAt: string;
};

export type OpenLoopRecord = OpenLoop & {
  createdAt: string;
};

export class MemoryStore {
  #drafts: DraftRecord[] = [];
  #memories: MemoryFactRecord[] = [];
  #openLoops: OpenLoopRecord[] = [];

  writeDraft(input: Omit<DraftRecord, "createdAt" | "updatedAt">, now = new Date()): DraftRecord {
    const timestamp = now.toISOString();
    const record: DraftRecord = {
      ...input,
      id: input.id || `draft_${now.getTime()}`,
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    this.#drafts.push(record);
    return record;
  }

  writeMemory(input: Omit<MemoryFactRecord, "createdAt">, now = new Date()): MemoryFactRecord {
    const record: MemoryFactRecord = {
      ...input,
      id: input.id || `mem_${now.getTime()}`,
      createdAt: now.toISOString(),
    };
    this.#memories.push(record);
    return record;
  }

  writeOpenLoop(input: Omit<OpenLoopRecord, "createdAt">, now = new Date()): OpenLoopRecord {
    const record: OpenLoopRecord = {
      ...input,
      id: input.id || `ol_${now.getTime()}`,
      createdAt: now.toISOString(),
    };
    this.#openLoops.push(record);
    return record;
  }

  listDrafts(): DraftRecord[] {
    return [...this.#drafts];
  }

  listMemories(): MemoryFactRecord[] {
    return [...this.#memories];
  }

  listOpenLoops(): OpenLoopRecord[] {
    return [...this.#openLoops];
  }
import fs from "node:fs/promises";
import path from "node:path";
import type { ApprovalQueueItem } from "./schemas/approval-queue.js";
import type { AuditRecord } from "./schemas/audit-record.js";
import type { DraftRecord } from "./schemas/draft.js";
import type { MemoryFact } from "./schemas/memory-fact.js";
import type { OpenLoop } from "./schemas/open-loop.js";

export type LolaAuditLogRecord = {
  at: string;
  event: string;
  agent: string;
  queueId?: string;
  targetType?: string;
  targetId?: string;
  status?: string;
  summary: string;
  details?: Record<string, unknown>;
  redactionApplied: boolean;
};

type LolaDataStore = {
  version: 2;
  drafts: DraftRecord[];
  approvalQueue: ApprovalQueueItem[];
  memoryFacts: MemoryFact[];
  openLoops: OpenLoop[];
  auditRecords: AuditRecord[];
  auditLog: LolaAuditLogRecord[];
};

function assertWithinRoot(root: string, target: string) {
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Path escapes workspace root: ${target}`);
  }
}

export function resolveLolaStorePaths(workspaceDir: string) {
  const root = path.resolve(workspaceDir);
  const dataDir = path.resolve(root, ".lola");
  const storePath = path.resolve(dataDir, "phase2-store.json");
  assertWithinRoot(root, dataDir);
  assertWithinRoot(root, storePath);
  return { root, dataDir, storePath };
}

function normalizeStore(raw: unknown): LolaDataStore {
  if (!raw || typeof raw !== "object") {
    return {
      version: 2,
      drafts: [],
      approvalQueue: [],
      memoryFacts: [],
      openLoops: [],
      auditRecords: [],
      auditLog: [],
    };
  }
  const candidate = raw as Partial<LolaDataStore>;
  return {
    version: 2,
    drafts: Array.isArray(candidate.drafts) ? candidate.drafts : [],
    approvalQueue: Array.isArray(candidate.approvalQueue) ? candidate.approvalQueue : [],
    memoryFacts: Array.isArray(candidate.memoryFacts) ? candidate.memoryFacts : [],
    openLoops: Array.isArray(candidate.openLoops) ? candidate.openLoops : [],
    auditRecords: Array.isArray(candidate.auditRecords) ? candidate.auditRecords : [],
    auditLog: Array.isArray(candidate.auditLog) ? candidate.auditLog : [],
  };
}

async function loadStore(workspaceDir: string): Promise<LolaDataStore> {
  const { storePath } = resolveLolaStorePaths(workspaceDir);
  try {
    const raw = await fs.readFile(storePath, "utf-8");
    return normalizeStore(JSON.parse(raw));
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (code === "ENOENT") {
      return normalizeStore(undefined);
    }
    throw error;
  }
}

async function writeStore(workspaceDir: string, store: LolaDataStore) {
  const { dataDir, storePath } = resolveLolaStorePaths(workspaceDir);
  await fs.mkdir(dataDir, { recursive: true });
  const tmpPath = `${storePath}.${process.pid}.${Math.random().toString(16).slice(2)}.tmp`;
  await fs.writeFile(tmpPath, `${JSON.stringify(store, null, 2)}\n`, "utf-8");
  await fs.rename(tmpPath, storePath);
}

async function updateStore<T>(
  workspaceDir: string,
  updater: (store: LolaDataStore) => T | Promise<T>,
): Promise<T> {
  const store = await loadStore(workspaceDir);
  const result = await updater(store);
  await writeStore(workspaceDir, store);
  return result;
}

function upsertById<T extends { id: string }>(items: T[], item: T): T[] {
  const index = items.findIndex((entry) => entry.id === item.id);
  if (index === -1) {
    return [...items, item];
  }
  const next = [...items];
  next[index] = item;
  return next;
}

export async function enqueueApproval(workspaceDir: string, item: ApprovalQueueItem) {
  return updateStore(workspaceDir, (store) => {
    store.approvalQueue = upsertById(store.approvalQueue, item);
    return item;
  });
}

export async function listApprovalQueue(workspaceDir: string) {
  const store = await loadStore(workspaceDir);
  return [...store.approvalQueue].toSorted((a, b) =>
    (a.createdAt ?? "").localeCompare(b.createdAt ?? ""),
  );
}

export async function saveDraft(workspaceDir: string, draft: DraftRecord) {
  return updateStore(workspaceDir, (store) => {
    store.drafts = upsertById(store.drafts, draft);
    return draft;
  });
}

export async function listDrafts(workspaceDir: string) {
  return (await loadStore(workspaceDir)).drafts;
}

export async function saveMemoryFact(workspaceDir: string, fact: MemoryFact) {
  return updateStore(workspaceDir, (store) => {
    store.memoryFacts = upsertById(store.memoryFacts, fact);
    return fact;
  });
}

export async function listMemoryFacts(workspaceDir: string) {
  return (await loadStore(workspaceDir)).memoryFacts;
}

export async function saveOpenLoop(workspaceDir: string, loop: OpenLoop) {
  return updateStore(workspaceDir, (store) => {
    store.openLoops = upsertById(store.openLoops, loop);
    return loop;
  });
}

export async function listOpenLoops(workspaceDir: string) {
  return (await loadStore(workspaceDir)).openLoops;
}

export async function saveAuditRecord(workspaceDir: string, record: AuditRecord) {
  return updateStore(workspaceDir, (store) => {
    store.auditRecords = upsertById(store.auditRecords, record);
    return record;
  });
}

export async function listAuditRecords(workspaceDir: string) {
  return (await loadStore(workspaceDir)).auditRecords;
}

export async function appendAuditLog(workspaceDir: string, record: LolaAuditLogRecord) {
  return updateStore(workspaceDir, (store) => {
    store.auditLog = [...store.auditLog, record];
    return record;
  });
}

export async function listAuditLog(workspaceDir: string) {
  return (await loadStore(workspaceDir)).auditLog;
}
