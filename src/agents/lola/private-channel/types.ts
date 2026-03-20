export const LOLA_PRIVATE_INTENTS = [
  "chat",
  "status_request",
  "command",
  "approval_grant",
  "approval_deny",
  "reminder_create",
  "follow_up_create",
  "task_create",
  "calendar_query",
  "calendar_mutation",
  "email_query",
  "email_draft",
  "email_send",
  "crm_update",
  "urgent_escalation",
  "memory_capture",
] as const;

export type LolaPrivateIntent = (typeof LOLA_PRIVATE_INTENTS)[number];

export type LolaRiskLevel = "low" | "medium" | "high" | "critical";
export type LolaTrustTier = "blocked" | "known" | "trusted" | "admin";

export interface LolaPrivateInboundMessage {
  id: string;
  channel: "whatsapp" | "imessage" | "sms";
  channelAccountId?: string;
  senderId: string;
  senderHandle?: string;
  senderE164?: string;
  trustedSender: boolean;
  threadId: string;
  text: string;
  receivedAt: string;
  replyToMessageId?: string;
  attachments?: Array<{
    id: string;
    mimeType: string;
    sha256?: string;
    storageRef?: string;
  }>;
}

export interface LolaPrivateIdentity {
  operatorId: string;
  displayName: string;
  allowedChannels: Array<"whatsapp" | "imessage" | "sms">;
  allowedSenderIds: string[];
  allowedE164?: string[];
  allowedHandles?: string[];
  trustTier: LolaTrustTier;
  requireKnownThread: boolean;
}

export interface LolaPrivateClassification {
  intent: LolaPrivateIntent;
  confidence: number;
  risk: LolaRiskLevel;
  requiresApproval: boolean;
  reason: string;
}

export interface LolaApprovalRequest {
  id: string;
  operatorId: string;
  threadId: string;
  actionType: LolaPrivateIntent;
  actionHash: string;
  summary: string;
  requestedAt: string;
  expiresAt: string;
  status: "pending" | "approved" | "denied" | "expired" | "applied";
}

export interface LolaExecutionReceipt {
  id: string;
  operatorId: string;
  threadId: string;
  messageId: string;
  actionType: LolaPrivateIntent;
  status: "drafted" | "executed" | "blocked" | "failed" | "awaiting_approval";
  summary: string;
  taskId?: string;
  approvalId?: string;
  createdAt: string;
}

export interface LolaMemoryCheckpoint {
  id: string;
  operatorId: string;
  threadId: string;
  category: "preference" | "task" | "contact" | "standing_rule" | "fact";
  summary: string;
  sourceMessageId: string;
  createdAt: string;
}
