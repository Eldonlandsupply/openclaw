import type { CronJobCreate, CronPayload, CronSchedule } from "./types.js";

export type LolaFollowThroughPayloadOptions = {
  message: string;
  model?: string;
  thinking?: string;
  timeoutSeconds?: number;
  lightContext?: boolean;
};

export type LolaFollowThroughScheduleOptions = {
  expr: string;
  tz?: string;
};

export type LolaFollowThroughJobOptions = {
  name: string;
  description?: string;
  enabled?: boolean;
  wakeMode?: "now" | "next-heartbeat";
  agentId?: string;
  schedule: LolaFollowThroughScheduleOptions;
  payload: LolaFollowThroughPayloadOptions;
};

export function buildLolaFollowThroughSchedule(
  options: LolaFollowThroughScheduleOptions,
): CronSchedule {
  const expr = options.expr.trim();
  if (!expr) {
    throw new Error("LOLA follow-through cron expression is required");
  }

  const tz = typeof options.tz === "string" ? options.tz.trim() : "";
  return tz ? { kind: "cron", expr, tz } : { kind: "cron", expr };
}

export function buildLolaFollowThroughPayload(
  options: LolaFollowThroughPayloadOptions,
): Extract<CronPayload, { kind: "agentTurn" }> {
  const message = options.message.trim();
  if (!message) {
    throw new Error("LOLA follow-through message is required");
  }

  const payload: Extract<CronPayload, { kind: "agentTurn" }> = {
    kind: "agentTurn",
    message,
  };

  const model = options.model?.trim();
  if (model) {
    payload.model = model;
  }

  const thinking = options.thinking?.trim();
  if (thinking) {
    payload.thinking = thinking;
  }

  if (typeof options.timeoutSeconds === "number" && Number.isFinite(options.timeoutSeconds)) {
    payload.timeoutSeconds = Math.max(1, Math.floor(options.timeoutSeconds));
  }

  if (typeof options.lightContext === "boolean") {
    payload.lightContext = options.lightContext;
  }

  return payload;
}

export function buildLolaFollowThroughJob(options: LolaFollowThroughJobOptions): CronJobCreate {
  const name = options.name.trim();
  if (!name) {
    throw new Error("LOLA follow-through job name is required");
  }

  const description = options.description?.trim();
  const wakeMode = options.wakeMode ?? "next-heartbeat";
  const agentId = options.agentId?.trim();

  return {
    name,
    description: description || undefined,
    enabled: options.enabled ?? true,
    schedule: buildLolaFollowThroughSchedule(options.schedule),
    sessionTarget: "isolated",
    wakeMode,
    payload: buildLolaFollowThroughPayload(options.payload),
    agentId: agentId || undefined,
  };
}
