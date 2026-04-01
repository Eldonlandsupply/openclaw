import type { Message } from "@grammyjs/types";
import type { TelegramContext } from "../../telegram/bot/types.js";
import type {
  TelegramNormalizedRequest,
  TelegramRouteTarget,
  TelegramRoutingDecision,
} from "./telegram-types.js";
import { createSubsystemLogger } from "../../logging/subsystem.js";
import {
  createTelegramApprovalRequest,
  listPendingTelegramApprovals,
  resolveTelegramApproval,
} from "./telegram-approvals.js";
import { evaluateTelegramIntakePolicy } from "./telegram-policy.js";
import { routeTelegramRequest } from "./telegram-router.js";

const auditLogger = createSubsystemLogger("lola/telegram-audit");

export type TelegramIntakeResult =
  | {
      outcome: "pass";
      route: TelegramRoutingDecision;
      normalized: TelegramNormalizedRequest;
      responseText?: string;
    }
  | { outcome: "handled"; responseText: string }
  | { outcome: "blocked"; responseText: string };

function buildAttachments(msg: Message): TelegramNormalizedRequest["attachmentMetadata"] {
  const items: TelegramNormalizedRequest["attachmentMetadata"] = [];
  if (msg.photo?.length) {
    items.push({ kind: "photo", count: msg.photo.length });
  }
  if (msg.video) {
    items.push({ kind: "video" });
  }
  if (msg.audio) {
    items.push({ kind: "audio" });
  }
  if (msg.voice) {
    items.push({ kind: "voice" });
  }
  if (msg.document) {
    items.push({ kind: "document" });
  }
  if (msg.sticker) {
    items.push({ kind: "sticker" });
  }
  if (msg.location) {
    items.push({ kind: "location" });
  }
  return items.length > 0 ? items : undefined;
}

function normalizeRequest(ctx: TelegramContext): TelegramNormalizedRequest {
  const msg = ctx.message;
  const text = (msg.text ?? msg.caption ?? "").trim();
  return {
    channel: "telegram",
    telegramUserId: String(msg.from?.id ?? ""),
    telegramChatId: String(msg.chat.id),
    telegramMessageId: String(msg.message_id),
    timestamp: new Date((msg.date ?? Math.floor(Date.now() / 1000)) * 1000).toISOString(),
    text,
    replyToMessageId:
      typeof msg.reply_to_message?.message_id === "number"
        ? String(msg.reply_to_message.message_id)
        : undefined,
    attachmentMetadata: buildAttachments(msg),
    rawPayloadRef: {
      updateId: undefined,
      hasMessage: true,
    },
  };
}

function parseApprovalInstruction(text: string): { id: string; approve: boolean } | null {
  const normalized = text.trim().toLowerCase();
  const approveMatch = /^approve\s+([a-z0-9-]{4,})$/.exec(normalized);
  if (approveMatch?.[1]) {
    return { id: approveMatch[1], approve: true };
  }
  const denyMatch = /^(deny|reject)\s+([a-z0-9-]{4,})$/.exec(normalized);
  if (denyMatch?.[2]) {
    return { id: denyMatch[2], approve: false };
  }
  return null;
}

function routeToAgentId(target: TelegramRouteTarget): string {
  if (target === "cto") {
    return "cto";
  }
  if (target === "research") {
    return "research";
  }
  if (target === "workflow_runner") {
    return "workflow_runner";
  }
  return "lola";
}

export function resolveTelegramTargetAgentId(target: TelegramRouteTarget): string {
  return routeToAgentId(target);
}

export function evaluateTelegramIntake(ctx: TelegramContext): TelegramIntakeResult {
  const normalized = normalizeRequest(ctx);
  const text = normalized.text;
  const userId = normalized.telegramUserId;
  const chatId = normalized.telegramChatId;

  auditLogger.info("telegram intake request", {
    event: "request_received",
    userId,
    chatId,
    messageId: normalized.telegramMessageId,
    text,
  });

  if (text === "/start") {
    return {
      outcome: "handled",
      responseText: "OpenClaw Telegram bridge is active. Send /help for operator commands.",
    };
  }
  if (text === "/help") {
    return {
      outcome: "handled",
      responseText:
        "Commands: /start, /help, what is pending?, approve <id>, deny <id>. Engineering work auto-routes to CTO.",
    };
  }

  if (text.toLowerCase() === "what is pending?") {
    const pending = listPendingTelegramApprovals({ userId, chatId });
    if (pending.length === 0) {
      return { outcome: "handled", responseText: "No pending approvals for this chat." };
    }
    const list = pending.map((item) => `• ${item.id}: ${item.request.text}`).join("\n");
    return { outcome: "handled", responseText: `Pending approvals:\n${list}` };
  }

  const instruction = parseApprovalInstruction(text);
  if (instruction) {
    const resolved = resolveTelegramApproval({
      approvalId: instruction.id,
      userId,
      chatId,
      approve: instruction.approve,
    });
    auditLogger.info("telegram approval decision", {
      event: instruction.approve ? "approval_received" : "approval_denied",
      approvalId: instruction.id,
      ok: resolved.ok,
      reason: resolved.reason,
    });
    if (!resolved.ok || !resolved.approval || !instruction.approve) {
      return { outcome: "handled", responseText: resolved.reason ?? "Approval resolution failed." };
    }
    return {
      outcome: "pass",
      normalized: resolved.approval.request,
      route: resolved.approval.route,
      responseText: `Approval ${instruction.id} accepted. Executing now.`,
    };
  }

  const policy = evaluateTelegramIntakePolicy({
    text,
    userId,
    chatId,
    allowedUserIds: process.env.TELEGRAM_ALLOWED_USER_IDS,
    allowedChatIds: process.env.TELEGRAM_ALLOWED_CHAT_IDS,
  });

  auditLogger.info("telegram intake policy", {
    event: "policy_checked",
    allowed: policy.allowed,
    reason: policy.reason,
    tier: policy.tier,
  });

  if (!policy.allowed) {
    return { outcome: "blocked", responseText: `Request blocked: ${policy.reason}.` };
  }

  const route = routeTelegramRequest(text);
  auditLogger.info("telegram route selected", {
    event: "route_selected",
    target: route.target,
    intent: route.intent,
    executor: route.executor,
    reason: route.reason,
    tier: policy.tier,
  });

  if (route.target === "blocked") {
    return { outcome: "blocked", responseText: "Request blocked by policy routing." };
  }

  const loweredText = text.toLowerCase();
  const githubTokenPresent = Boolean(
    process.env.GITHUB_TOKEN || process.env.GH_TOKEN || process.env.COPILOT_GITHUB_TOKEN,
  );
  const attioApiKeyPresent = Boolean(process.env.ATTIO_API_KEY);
  const outlookCredentialsPresent = Boolean(
    (process.env.LOLA_M365_GRAPH_ACCESS_TOKEN ||
      process.env.M365_GRAPH_ACCESS_TOKEN ||
      (process.env.LOLA_M365_CLIENT_ID &&
        process.env.LOLA_M365_CLIENT_SECRET &&
        process.env.LOLA_M365_TENANT_ID) ||
      (process.env.M365_CLIENT_ID &&
        process.env.M365_CLIENT_SECRET &&
        process.env.M365_TENANT_ID)) ??
    false,
  );

  if (
    route.intent === "engineering" &&
    (loweredText.includes("pull request") ||
      loweredText.includes("github") ||
      /\bpr\b/.test(loweredText)) &&
    !githubTokenPresent
  ) {
    return {
      outcome: "handled",
      responseText:
        "Telegram request classified as engineering workflow. Repo executor requires GITHUB_TOKEN/GH_TOKEN (or COPILOT_GITHUB_TOKEN), but none is configured.",
    };
  }

  if (route.intent === "operations" && loweredText.includes("attio") && !attioApiKeyPresent) {
    return {
      outcome: "handled",
      responseText:
        "Telegram request classified as operations workflow. Attio execution is unavailable because ATTIO_API_KEY is missing.",
    };
  }

  const routeKeyword = route.reason.startsWith("operations keyword:")
    ? route.reason.split(":")[1]?.trim().toLowerCase()
    : undefined;
  const graphOperationKeywords = new Set([
    "outlook",
    "calendar",
    "meeting",
    "inbox",
    "follow-up",
    "follow up",
    "followups",
  ]);
  const graphOperationRequested =
    routeKeyword !== undefined
      ? graphOperationKeywords.has(routeKeyword)
      : ["outlook", "calendar", "meeting", "inbox", "follow-up", "follow up", "followups"].some(
          (keyword) => loweredText.includes(keyword),
        );

  if (route.intent === "operations" && graphOperationRequested && !outlookCredentialsPresent) {
    return {
      outcome: "handled",
      responseText:
        "Telegram request classified as operations workflow. Outlook execution is unavailable because Microsoft Graph credentials are missing.",
    };
  }

  if (policy.tier === 2) {
    const approval = createTelegramApprovalRequest({ request: normalized, route });
    auditLogger.info("telegram approval requested", {
      event: "approval_requested",
      approvalId: approval.id,
      expiresAt: approval.expiresAt,
    });
    return {
      outcome: "handled",
      responseText: `Approval required (Tier 2). Reply with: approve ${approval.id} or deny ${approval.id}.`,
    };
  }

  return { outcome: "pass", normalized, route };
}
