import fs from "node:fs/promises";
import path from "node:path";

export type CommitmentStatus = "open" | "in_progress" | "blocked" | "done";

export type CommitmentHistoryEntry = {
  at: string;
  from: CommitmentStatus | null;
  to: CommitmentStatus;
  note?: string;
};

export type CommitmentRecord = {
  id: string;
  title: string;
  owner?: string;
  dueDate?: string;
  status: CommitmentStatus;
  tags?: string[];
  notes?: string;
  createdAt: string;
  updatedAt: string;
  history: CommitmentHistoryEntry[];
};

type CommitmentStore = {
  version: 1;
  commitments: CommitmentRecord[];
};

export type CommitmentInput = {
  id: string;
  title: string;
  owner?: string;
  dueDate?: string;
  status?: CommitmentStatus;
  tags?: string[];
  notes?: string;
};

function assertWithinRoot(root: string, target: string) {
  const relative = path.relative(root, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Path escapes workspace root: ${target}`);
  }
}

function isStatus(value: string): value is CommitmentStatus {
  return value === "open" || value === "in_progress" || value === "blocked" || value === "done";
}

function normalizeDate(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid ISO date: ${value}`);
  }
  return date.toISOString();
}

function sortRecords(records: CommitmentRecord[]): CommitmentRecord[] {
  return [...records].toSorted((a, b) => {
    const dueA = a.dueDate ?? "9999-12-31T23:59:59.999Z";
    const dueB = b.dueDate ?? "9999-12-31T23:59:59.999Z";
    if (dueA !== dueB) {
      return dueA.localeCompare(dueB);
    }
    return a.id.localeCompare(b.id);
  });
}

function normalizeStore(raw: unknown): CommitmentStore {
  if (!raw || typeof raw !== "object") {
    return { version: 1, commitments: [] };
  }
  const candidate = raw as { version?: unknown; commitments?: unknown };
  const commitments = Array.isArray(candidate.commitments)
    ? candidate.commitments.filter((item): item is CommitmentRecord => {
        if (!item || typeof item !== "object") {
          return false;
        }
        const record = item as CommitmentRecord;
        return (
          typeof record.id === "string" &&
          typeof record.title === "string" &&
          typeof record.status === "string" &&
          isStatus(record.status)
        );
      })
    : [];
  return {
    version: 1,
    commitments: sortRecords(commitments),
  };
}

export function resolveOpsMemoryPaths(workspaceDir: string) {
  const root = path.resolve(workspaceDir);
  const dataDir = path.resolve(root, ".lola");
  const ledgerPath = path.resolve(dataDir, "commitments.json");
  assertWithinRoot(root, dataDir);
  assertWithinRoot(root, ledgerPath);
  return { root, dataDir, ledgerPath };
}

export async function loadCommitments(workspaceDir: string): Promise<CommitmentRecord[]> {
  const { ledgerPath } = resolveOpsMemoryPaths(workspaceDir);
  try {
    const raw = await fs.readFile(ledgerPath, "utf-8");
    return normalizeStore(JSON.parse(raw)).commitments;
  } catch (err) {
    const code = (err as { code?: string }).code;
    if (code === "ENOENT") {
      return [];
    }
    throw err;
  }
}

async function writeStore(workspaceDir: string, records: CommitmentRecord[]) {
  const { dataDir, ledgerPath } = resolveOpsMemoryPaths(workspaceDir);
  await fs.mkdir(dataDir, { recursive: true });
  const store: CommitmentStore = {
    version: 1,
    commitments: sortRecords(records),
  };
  const tmpPath = `${ledgerPath}.${process.pid}.${Math.random().toString(16).slice(2)}.tmp`;
  const body = `${JSON.stringify(store, null, 2)}\n`;
  await fs.writeFile(tmpPath, body, "utf-8");
  await fs.rename(tmpPath, ledgerPath);
}

export async function upsertCommitment(
  workspaceDir: string,
  input: CommitmentInput,
  now = new Date(),
): Promise<CommitmentRecord> {
  const id = input.id.trim();
  const title = input.title.trim();
  if (!id) {
    throw new Error("Commitment id is required");
  }
  if (!title) {
    throw new Error("Commitment title is required");
  }

  const records = await loadCommitments(workspaceDir);
  const nowIso = now.toISOString();
  const nextStatus = input.status ?? "open";
  const idx = records.findIndex((record) => record.id === id);

  if (idx === -1) {
    const created: CommitmentRecord = {
      id,
      title,
      owner: input.owner?.trim() || undefined,
      dueDate: normalizeDate(input.dueDate),
      status: nextStatus,
      tags: input.tags?.map((tag) => tag.trim()).filter(Boolean),
      notes: input.notes?.trim() || undefined,
      createdAt: nowIso,
      updatedAt: nowIso,
      history: [{ at: nowIso, from: null, to: nextStatus, note: "created" }],
    };
    await writeStore(workspaceDir, [...records, created]);
    return created;
  }

  const current = records[idx];
  const updated: CommitmentRecord = {
    ...current,
    title,
    owner: input.owner?.trim() || current.owner,
    dueDate: normalizeDate(input.dueDate ?? current.dueDate),
    tags: input.tags ? input.tags.map((tag) => tag.trim()).filter(Boolean) : current.tags,
    notes: input.notes?.trim() || current.notes,
    status: nextStatus,
    updatedAt: nowIso,
    history:
      current.status === nextStatus
        ? current.history
        : [
            ...current.history,
            { at: nowIso, from: current.status, to: nextStatus, note: "upsert" },
          ],
  };

  const next = [...records];
  next[idx] = updated;
  await writeStore(workspaceDir, next);
  return updated;
}

export async function transitionCommitmentStatus(params: {
  workspaceDir: string;
  id: string;
  to: CommitmentStatus;
  note?: string;
  now?: Date;
}): Promise<CommitmentRecord> {
  const id = params.id.trim();
  if (!id) {
    throw new Error("Commitment id is required");
  }
  const records = await loadCommitments(params.workspaceDir);
  const idx = records.findIndex((record) => record.id === id);
  if (idx === -1) {
    throw new Error(`Commitment not found: ${id}`);
  }

  const current = records[idx];
  const nowIso = (params.now ?? new Date()).toISOString();
  if (current.status === params.to) {
    return current;
  }

  const nextRecord: CommitmentRecord = {
    ...current,
    status: params.to,
    updatedAt: nowIso,
    history: [
      ...current.history,
      {
        at: nowIso,
        from: current.status,
        to: params.to,
        note: params.note?.trim() || undefined,
      },
    ],
  };

  const next = [...records];
  next[idx] = nextRecord;
  await writeStore(params.workspaceDir, next);
  return nextRecord;
}

export async function listDueCommitments(params: {
  workspaceDir: string;
  asOf?: string | Date;
  includeCompleted?: boolean;
}): Promise<CommitmentRecord[]> {
  const asOf = params.asOf ? new Date(params.asOf) : new Date();
  if (Number.isNaN(asOf.getTime())) {
    throw new Error("Invalid asOf date");
  }
  const records = await loadCommitments(params.workspaceDir);
  return records.filter((record) => {
    if (!record.dueDate) {
      return false;
    }
    if (!params.includeCompleted && record.status === "done") {
      return false;
    }
    return new Date(record.dueDate).getTime() <= asOf.getTime();
  });
}
