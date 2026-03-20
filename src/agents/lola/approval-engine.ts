export type ApprovalStatus = "pending" | "approved" | "denied";

export type ApprovalQueueItem = {
  id: string;
  type: string;
  payload?: Record<string, unknown>;
  status: ApprovalStatus;
  createdAt: string;
};

export class ApprovalEngine {
  #queue: ApprovalQueueItem[] = [];

  enqueue(item: Omit<ApprovalQueueItem, "status" | "createdAt">, now = new Date()) {
    const queued: ApprovalQueueItem = {
      ...item,
      status: "pending",
      createdAt: now.toISOString(),
    };
    this.#queue.push(queued);
    return queued;
  }

  approve(itemId: string) {
    return this.#setStatus(itemId, "approved");
  }

  deny(itemId: string) {
    return this.#setStatus(itemId, "denied");
  }

  list() {
    return [...this.#queue];
  }

  #setStatus(itemId: string, status: ApprovalStatus) {
    const index = this.#queue.findIndex((item) => item.id === itemId);
    if (index === -1) {
      return undefined;
    }
    const updated: ApprovalQueueItem = {
      ...this.#queue[index],
      status,
    };
    this.#queue[index] = updated;
    return updated;
import type { ApprovalQueueItem } from "./schemas/approval-queue.js";
import type { AuditRecord } from "./schemas/audit-record.js";
import type { DraftRecord } from "./schemas/draft.js";
import type { MemoryFact } from "./schemas/memory-fact.js";
import type { OpenLoop } from "./schemas/open-loop.js";
import { LolaActionLogger } from "./action-logger.js";
import { LOLA_WRITE_TOGGLES_DEFAULTS, type LolaSubagentKey } from "./config/lola.config.js";
import {
  enqueueApproval,
  listApprovalQueue,
  saveAuditRecord,
  saveDraft,
  saveMemoryFact,
  saveOpenLoop,
} from "./memory-store.js";

export type LolaWritePayload =
  | { kind: "draft"; record: DraftRecord }
  | { kind: "memory_fact"; record: MemoryFact }
  | { kind: "open_loop"; record: OpenLoop }
  | { kind: "audit_record"; record: AuditRecord };

export type LolaApprovalEngineConfig = {
  workspaceDir: string;
  dryRun?: boolean;
  writeEnabled?: boolean;
  writeToggles?: Partial<Record<LolaSubagentKey, boolean>>;
};

export type ApprovalDecision = {
  queueId: string;
  decidedBy: string;
  approved: boolean;
  decidedAt?: string;
};

function inferTargetId(payload: LolaWritePayload): string {
  return payload.record.id;
}

function summarizePayload(payload: LolaWritePayload): string {
  if (payload.kind === "draft") {
    return payload.record.title;
  }
  if (payload.kind === "memory_fact") {
    return `${payload.record.subject}: ${payload.record.factType}`;
  }
  if (payload.kind === "open_loop") {
    return payload.record.summary ?? payload.record.sourceRef;
  }
  return payload.record.finding;
}

export class ApprovalEngine {
  readonly #logger: LolaActionLogger;
  readonly #config: Required<
    Pick<LolaApprovalEngineConfig, "workspaceDir" | "dryRun" | "writeEnabled">
  > & {
    writeToggles: Record<LolaSubagentKey, boolean>;
  };

  constructor(config: LolaApprovalEngineConfig) {
    this.#config = {
      workspaceDir: config.workspaceDir,
      dryRun: config.dryRun ?? true,
      writeEnabled: config.writeEnabled ?? false,
      writeToggles: { ...LOLA_WRITE_TOGGLES_DEFAULTS, ...config.writeToggles },
    };
    this.#logger = new LolaActionLogger(this.#config.workspaceDir);
  }

  canRequestWrites(agent: LolaSubagentKey) {
    return this.#config.writeEnabled && this.#config.writeToggles[agent];
  }

  async requestWrite(params: {
    agent: LolaSubagentKey;
    reason: string;
    confidence?: number;
    payload: LolaWritePayload;
    now?: Date;
  }): Promise<ApprovalQueueItem> {
    const nowIso = (params.now ?? new Date()).toISOString();
    const enabled = this.canRequestWrites(params.agent);
    const queue: ApprovalQueueItem = {
      id: `approval:${params.agent}:${inferTargetId(params.payload)}`,
      actionType: `write:${params.payload.kind}`,
      targetType: params.payload.kind,
      targetId: inferTargetId(params.payload),
      proposedByAgent: params.agent,
      payloadSummary: summarizePayload(params.payload),
      reason: params.reason,
      confidence: params.confidence,
      requiresHumanApproval: true,
      status: enabled ? "pending" : "blocked",
      createdAt: nowIso,
      dryRun: this.#config.dryRun,
    };
    await enqueueApproval(this.#config.workspaceDir, queue);
    await this.#logger.logQueueEvent({
      event: enabled ? "approval_requested" : "write_blocked",
      summary: enabled ? "Queued internal write for approval" : "Blocked internal write request",
      queue,
      details: {
        reason: params.reason,
        payload: params.payload,
      },
    });
    return queue;
  }

  async decide(decision: ApprovalDecision) {
    const queue = (await listApprovalQueue(this.#config.workspaceDir)).find(
      (item) => item.id === decision.queueId,
    );
    if (!queue) {
      throw new Error(`Approval queue item not found: ${decision.queueId}`);
    }
    const next: ApprovalQueueItem = {
      ...queue,
      status: decision.approved ? "approved" : "rejected",
      decidedBy: decision.decidedBy,
      decidedAt: decision.decidedAt ?? new Date().toISOString(),
      approvedAt: decision.approved
        ? (decision.decidedAt ?? new Date().toISOString())
        : queue.approvedAt,
    };
    await enqueueApproval(this.#config.workspaceDir, next);
    await this.#logger.logQueueEvent({
      event: "approval_decided",
      summary: decision.approved ? "Approved internal write" : "Rejected internal write",
      queue: next,
    });
    return next;
  }

  async applyApprovedWrite(payload: LolaWritePayload, queueId: string) {
    const queue = (await listApprovalQueue(this.#config.workspaceDir)).find(
      (item) => item.id === queueId,
    );
    if (!queue) {
      throw new Error(`Approval queue item not found: ${queueId}`);
    }
    if (queue.status !== "approved") {
      throw new Error(`Approval queue item is not approved: ${queueId}`);
    }

    if (payload.kind === "draft") {
      await saveDraft(this.#config.workspaceDir, {
        ...payload.record,
        approvalId: queueId,
        status: this.#config.dryRun ? "approved" : "written",
      });
    } else if (payload.kind === "memory_fact") {
      await saveMemoryFact(this.#config.workspaceDir, {
        ...payload.record,
        approvalId: queueId,
        reviewStatus: this.#config.dryRun ? "approved" : "written",
      });
    } else if (payload.kind === "open_loop") {
      await saveOpenLoop(this.#config.workspaceDir, {
        ...payload.record,
        approvalId: queueId,
        writeStatus: this.#config.dryRun ? "approved" : "written",
      });
    } else {
      await saveAuditRecord(this.#config.workspaceDir, payload.record);
    }

    const appliedQueue: ApprovalQueueItem = {
      ...queue,
      status: "applied",
      outcomeRef: `${payload.kind}:${inferTargetId(payload)}`,
    };
    await enqueueApproval(this.#config.workspaceDir, appliedQueue);
    await this.#logger.logQueueEvent({
      event: "write_applied",
      summary: this.#config.dryRun
        ? "Recorded approved write in dry-run mode"
        : "Applied approved write",
      queue: appliedQueue,
      details: { payload },
    });
    return appliedQueue;
  }
}
