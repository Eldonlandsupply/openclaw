import type { TelegramExecutionTier, TelegramIntakePolicyResult } from "./telegram-types.js";

const BLOCK_PATTERNS = [
  /\brm\s+-rf\b/i,
  /\bsecret\b/i,
  /\bprivilege\s+escalation\b/i,
  /\braw\s+shell\b/i,
];
const TIER2_PATTERNS = [
  /\bsend\s+(that\s+)?email\b/i,
  /\bcalendar\s+(change|update|move|cancel|create)\b/i,
  /\bcreate\s+pull\s+request\b/i,
  /\bmerge\s+pr\b/i,
  /\bcommit\b/i,
  /\bdeploy\b/i,
];
const TIER1_PATTERNS = [/\bcheck\b/i, /\bstatus\b/i, /\bsummary\b/i, /\broute this to cto\b/i];

function classifyTier(text: string): TelegramExecutionTier {
  if (BLOCK_PATTERNS.some((pattern) => pattern.test(text))) {
    return 3;
  }
  if (TIER2_PATTERNS.some((pattern) => pattern.test(text))) {
    return 2;
  }
  if (TIER1_PATTERNS.some((pattern) => pattern.test(text))) {
    return 1;
  }
  return 0;
}

function parseAllowlist(raw?: string): Set<string> {
  if (!raw?.trim()) {
    return new Set();
  }
  return new Set(
    raw
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean),
  );
}

export function evaluateTelegramIntakePolicy(params: {
  text: string;
  userId: string;
  chatId: string;
  allowedUserIds?: string;
  allowedChatIds?: string;
}): TelegramIntakePolicyResult {
  const tier = classifyTier(params.text);
  if (tier === 3) {
    return { allowed: false, reason: "blocked high-risk request", tier };
  }

  const allowedUsers = parseAllowlist(params.allowedUserIds);
  if (allowedUsers.size > 0 && !allowedUsers.has(params.userId)) {
    return { allowed: false, reason: "telegram user is not allowlisted", tier };
  }

  const allowedChats = parseAllowlist(params.allowedChatIds);
  if (allowedChats.size > 0 && !allowedChats.has(params.chatId)) {
    return { allowed: false, reason: "telegram chat is not allowlisted", tier };
  }

  return { allowed: true, reason: "policy pass", tier };
}
