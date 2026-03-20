export function logAction(action: string, payload: Record<string, unknown>) {
  const redacted = { ...payload };
  if ("subject" in redacted) {
    redacted.subject = "[redacted]";
  }
  if ("sender" in redacted) {
    redacted.sender = "[redacted]";
  }
  console.log(`ACTION:${action} ${JSON.stringify(redacted)}`);
  return true;
import type { ApprovalQueueItem } from "./schemas/approval-queue.js";
import { appendAuditLog } from "./memory-store.js";

const REDACTED_KEYS = new Set(["body", "value", "notes", "payload", "content"]);

export type LolaActionLogEntry = {
  at?: string;
  event:
    | "write_intent"
    | "approval_requested"
    | "approval_decided"
    | "write_applied"
    | "write_blocked";
  agent: string;
  queueId?: string;
  targetType?: string;
  targetId?: string;
  status?: string;
  summary: string;
  details?: Record<string, unknown>;
  redactionApplied: boolean;
};

function redactValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((entry) => redactValue(entry));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [
        key,
        REDACTED_KEYS.has(key) ? "[REDACTED]" : redactValue(entry),
      ]),
    );
  }
  return value;
}

export function redactDetails(details: Record<string, unknown> | undefined): {
  details: Record<string, unknown> | undefined;
  redactionApplied: boolean;
} {
  if (!details) {
    return { details: undefined, redactionApplied: false };
  }
  const redacted = redactValue(details) as Record<string, unknown>;
  return {
    details: redacted,
    redactionApplied: JSON.stringify(redacted) !== JSON.stringify(details),
  };
}

export class LolaActionLogger {
  constructor(private readonly workspaceDir: string) {}

  async log(entry: LolaActionLogEntry) {
    const at = entry.at ?? new Date().toISOString();
    const { details, redactionApplied } = redactDetails(entry.details);
    await appendAuditLog(this.workspaceDir, {
      at,
      event: entry.event,
      agent: entry.agent,
      queueId: entry.queueId,
      targetType: entry.targetType,
      targetId: entry.targetId,
      status: entry.status,
      summary: entry.summary,
      details,
      redactionApplied: entry.redactionApplied || redactionApplied,
    });
  }

  async logQueueEvent(entry: {
    event: LolaActionLogEntry["event"];
    summary: string;
    queue: ApprovalQueueItem;
    details?: Record<string, unknown>;
  }) {
    await this.log({
      event: entry.event,
      agent: entry.queue.proposedByAgent,
      queueId: entry.queue.id,
      targetType: entry.queue.targetType,
      targetId: entry.queue.targetId,
      status: entry.queue.status,
      summary: entry.summary,
      details: entry.details,
      redactionApplied: entry.queue.redactionApplied ?? false,
    });
  }
}
