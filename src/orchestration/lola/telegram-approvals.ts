import crypto from "node:crypto";
import type {
  PendingTelegramApproval,
  TelegramNormalizedRequest,
  TelegramRoutingDecision,
} from "./telegram-types.js";

const DEFAULT_TTL_MS = 10 * 60 * 1000;
const pendingApprovals = new Map<string, PendingTelegramApproval>();

function cleanup(now: number) {
  for (const [id, item] of pendingApprovals.entries()) {
    if (item.expiresAt <= now || item.consumedAt) {
      pendingApprovals.delete(id);
    }
  }
}

export function createTelegramApprovalRequest(params: {
  request: TelegramNormalizedRequest;
  route: TelegramRoutingDecision;
  now?: number;
}): PendingTelegramApproval {
  const now = params.now ?? Date.now();
  cleanup(now);
  const id = crypto.randomUUID().slice(0, 8);
  const approval: PendingTelegramApproval = {
    id,
    createdAt: now,
    expiresAt: now + DEFAULT_TTL_MS,
    userId: params.request.telegramUserId,
    chatId: params.request.telegramChatId,
    request: params.request,
    route: params.route,
    tier: 2,
  };
  pendingApprovals.set(id, approval);
  return approval;
}

export function listPendingTelegramApprovals(params: {
  userId: string;
  chatId: string;
  now?: number;
}) {
  const now = params.now ?? Date.now();
  cleanup(now);
  return Array.from(pendingApprovals.values()).filter(
    (item) =>
      item.userId === params.userId &&
      item.chatId === params.chatId &&
      !item.consumedAt &&
      item.expiresAt > now,
  );
}

export function resolveTelegramApproval(params: {
  approvalId: string;
  userId: string;
  chatId: string;
  approve: boolean;
  now?: number;
}): { ok: boolean; reason?: string; approval?: PendingTelegramApproval } {
  const now = params.now ?? Date.now();
  cleanup(now);
  const pending = pendingApprovals.get(params.approvalId);
  if (!pending) {
    return { ok: false, reason: "approval not found or expired" };
  }
  if (pending.userId !== params.userId || pending.chatId !== params.chatId) {
    return { ok: false, reason: "approval does not belong to this sender" };
  }
  if (pending.consumedAt) {
    return { ok: false, reason: "approval already used" };
  }
  pending.consumedAt = now;
  if (!params.approve) {
    return { ok: false, reason: "approval denied", approval: pending };
  }
  return { ok: true, approval: pending };
}

export function resetTelegramApprovalsForTest() {
  pendingApprovals.clear();
}
