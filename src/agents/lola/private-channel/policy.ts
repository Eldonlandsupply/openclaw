import type {
  LolaPrivateClassification,
  LolaPrivateIntent,
  LolaPrivateInboundMessage,
  LolaRiskLevel,
  LolaTrustTier,
} from "./types.js";

const APPROVAL_INTENTS = new Set<LolaPrivateIntent>([
  "approval_grant",
  "approval_deny",
  "calendar_mutation",
  "email_send",
  "crm_update",
  "urgent_escalation",
]);

const HIGH_RISK_INTENTS = new Set<LolaPrivateIntent>([
  "calendar_mutation",
  "email_send",
  "crm_update",
]);

export function deriveTrustTier(params: {
  trustedSender: boolean;
  isAdmin?: boolean;
}): LolaTrustTier {
  if (params.isAdmin) {
    return "admin";
  }
  if (params.trustedSender) {
    return "trusted";
  }
  return "blocked";
}

export function classifyLolaMessage(params: {
  message: LolaPrivateInboundMessage;
  intent: LolaPrivateIntent;
  confidence: number;
}): LolaPrivateClassification {
  const { message, intent, confidence } = params;
  const risk = deriveRisk(intent, message.text);
  const requiresApproval = shouldRequireApproval({ intent, confidence, text: message.text, risk });
  return {
    intent,
    confidence,
    risk,
    requiresApproval,
    reason: buildReason({
      intent,
      confidence,
      risk,
      requiresApproval,
      trustedSender: message.trustedSender,
    }),
  };
}

export function shouldRequireApproval(params: {
  intent: LolaPrivateIntent;
  confidence: number;
  text: string;
  risk: LolaRiskLevel;
}): boolean {
  const normalized = params.text.toLowerCase();
  if (APPROVAL_INTENTS.has(params.intent)) {
    return true;
  }
  if (params.risk === "critical" || params.risk === "high") {
    return true;
  }
  if (params.confidence < 0.9 && (params.intent === "command" || params.intent === "task_create")) {
    return true;
  }
  if (normalized.includes("do not send") || normalized.includes("for approval")) {
    return true;
  }
  return false;
}

export function canAutoExecute(params: {
  trustTier: LolaTrustTier;
  classification: LolaPrivateClassification;
}): boolean {
  if (params.trustTier !== "trusted" && params.trustTier !== "admin") {
    return false;
  }
  if (params.classification.requiresApproval) {
    return false;
  }
  return params.classification.confidence >= 0.9;
}

function deriveRisk(intent: LolaPrivateIntent, text: string): LolaRiskLevel {
  const normalized = text.toLowerCase();
  if (HIGH_RISK_INTENTS.has(intent)) {
    return "high";
  }
  if (normalized.includes("urgent") || normalized.includes("immediately")) {
    return "critical";
  }
  if (intent === "task_create" || intent === "command") {
    return "medium";
  }
  return "low";
}

function buildReason(params: {
  intent: LolaPrivateIntent;
  confidence: number;
  risk: LolaRiskLevel;
  requiresApproval: boolean;
  trustedSender: boolean;
}): string {
  const reasons = [
    `intent=${params.intent}`,
    `confidence=${params.confidence.toFixed(2)}`,
    `risk=${params.risk}`,
    `trustedSender=${params.trustedSender ? "yes" : "no"}`,
  ];
  if (params.requiresApproval) {
    reasons.push("approval=required");
  }
  return reasons.join(", ");
}
