export type TelegramRouteTarget = "lola" | "cto" | "research" | "workflow_runner" | "blocked";

export type TelegramExecutionTier = 0 | 1 | 2 | 3;

export type TelegramAttachmentMetadata = {
  kind: "photo" | "video" | "audio" | "voice" | "document" | "sticker" | "location";
  count?: number;
};

export type TelegramNormalizedRequest = {
  channel: "telegram";
  telegramUserId: string;
  telegramChatId: string;
  telegramMessageId: string;
  timestamp: string;
  text: string;
  replyToMessageId?: string;
  attachmentMetadata?: TelegramAttachmentMetadata[];
  rawPayloadRef: {
    updateId?: number;
    hasMessage: boolean;
  };
};

export type TelegramIntakePolicyResult = {
  allowed: boolean;
  reason: string;
  tier: TelegramExecutionTier;
};

export type TelegramRoutingDecision = {
  target: TelegramRouteTarget;
  reason: string;
};

export type PendingTelegramApproval = {
  id: string;
  createdAt: number;
  expiresAt: number;
  consumedAt?: number;
  userId: string;
  chatId: string;
  route: TelegramRoutingDecision;
  tier: 2;
  request: TelegramNormalizedRequest;
};
