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
}
