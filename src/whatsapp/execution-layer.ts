import { z } from "zod";

const WhatsAppIntentTypes = [
  "informational_only",
  "note_to_memory",
  "task_creation",
  "workflow_trigger",
  "draft_content",
  "research_request",
  "monitoring_request",
  "delegation_request",
  "approval_request",
  "direct_execution_command",
  "repository_inspection",
  "repository_update_request",
  "bug_fix_request",
  "feature_request",
  "branch_pr_issue_operation",
  "unsafe_blocked",
] as const;

const ExecutionTiers = [
  "tier_0_log_only",
  "tier_1_prepare",
  "tier_2_auto_execute",
  "tier_3_approval",
  "tier_4_blocked",
] as const;
const RepoRiskTiers = ["tier_a_read", "tier_b_low", "tier_c_moderate", "tier_d_high"] as const;
const ActionStatuses = [
  "queued",
  "planning",
  "awaiting_approval",
  "running",
  "completed",
  "failed",
  "blocked",
  "retry_scheduled",
  "escalated",
] as const;
const ApprovalDecisions = [
  "approve",
  "approve_pr_only",
  "apply_do_not_merge",
  "show_diff_first",
  "edit_plan",
  "cancel",
  "expired",
] as const;

const IsoDateTimeSchema = z.string().datetime({ offset: true });

export const WhatsAppAttachmentSchema = z
  .object({
    attachmentId: z.string().min(1),
    kind: z.enum(["audio", "image", "video", "document", "link", "contact", "location", "other"]),
    mimeType: z.string().min(1),
    filename: z.string().optional(),
    sizeBytes: z.number().int().nonnegative().optional(),
    sourceUrl: z.string().url().optional(),
    storageUrl: z.string().optional(),
    checksumSha256: z.string().optional(),
    transcription: z.string().optional(),
    extractionStatus: z.enum(["pending", "completed", "failed", "skipped"]).default("pending"),
  })
  .strict();

export const WhatsAppReferencedEntitySchema = z
  .object({
    kind: z.enum([
      "person",
      "project",
      "workflow",
      "repository",
      "issue",
      "pull_request",
      "branch",
      "service",
    ]),
    id: z.string().optional(),
    name: z.string().min(1),
    confidence: z.number().min(0).max(1),
  })
  .strict();

export const WhatsAppActionSchema = z
  .object({
    messageId: z.string().min(1),
    userId: z.string().min(1),
    channel: z.literal("whatsapp"),
    rawText: z.string(),
    normalizedText: z.string(),
    attachments: z.array(WhatsAppAttachmentSchema).default([]),
    referencedEntities: z.array(WhatsAppReferencedEntitySchema).default([]),
    referencedRepositories: z.array(z.string()).default([]),
    intentType: z.enum(WhatsAppIntentTypes),
    confidence: z.number().min(0).max(1),
    project: z.string().optional(),
    owner: z.string().optional(),
    urgency: z.enum(["low", "normal", "high", "critical"]).default("normal"),
    executionTier: z.enum(ExecutionTiers),
    repoRiskTier: z.enum(RepoRiskTiers).optional(),
    approvalRequired: z.boolean(),
    requestedAction: z.string().min(1),
    successDefinition: z.string().min(1),
    dueDate: IsoDateTimeSchema.optional(),
    followUpRule: z.string().optional(),
    memoryWrite: z.boolean().default(true),
    agentRoute: z.string().optional(),
    toolRoute: z.array(z.string()).default([]),
    repoRoute: z.string().optional(),
    status: z.enum(ActionStatuses).default("queued"),
  })
  .strict();

export const WhatsAppRepoChangeSchema = z
  .object({
    repoId: z.string().min(1),
    repoName: z.string().min(1),
    repoOwner: z.string().min(1),
    targetBranch: z.string().min(1),
    baseBranch: z.string().min(1),
    requestedChangeType: z.enum([
      "explanation_only",
      "issue_creation",
      "planning_only",
      "code_modification",
      "documentation_update",
      "bug_fix",
      "new_feature",
      "config_change",
      "workflow_change",
      "pr_comment",
      "rollback",
    ]),
    filesTargeted: z.array(z.string()).default([]),
    rationale: z.string().min(1),
    implementationPlan: z.array(z.string()).min(1),
    riskTier: z.enum(RepoRiskTiers),
    approvalRequired: z.boolean(),
    testsToRun: z.array(z.string()).default([]),
    expectedOutputs: z.array(z.string()).default([]),
    rollbackMethod: z.string().min(1),
    commitStrategy: z.enum(["single_commit", "scoped_commits", "branch_only"]),
    prRequired: z.boolean().default(true),
    status: z.enum(ActionStatuses).default("queued"),
  })
  .strict();

export const WhatsAppApprovalRequestSchema = z
  .object({
    approvalId: z.string().min(1),
    actionId: z.string().min(1),
    requestedAt: IsoDateTimeSchema,
    expiresAt: IsoDateTimeSchema,
    summary: z.string().min(1),
    riskLabel: z.enum(["low", "moderate", "high", "critical"]),
    impactedSystems: z.array(z.string()).default([]),
    impactedRepositories: z.array(z.string()).default([]),
    likelyFiles: z.array(z.string()).default([]),
    irreversibleConsequences: z.array(z.string()).default([]),
    options: z.array(z.enum(ApprovalDecisions)).min(1),
    fallbackDecision: z.enum(["cancel", "hold", "expire"]).default("expire"),
  })
  .strict();

export const WhatsAppExecutionLogSchema = z
  .object({
    logId: z.string().min(1),
    timestamp: IsoDateTimeSchema,
    taskId: z.string().min(1),
    sourceMessageId: z.string().min(1),
    interpretedIntent: z.enum(WhatsAppIntentTypes),
    structuredCommand: z.string().min(1),
    executionPath: z.array(z.string()).min(1),
    browserRejectedReason: z.string().min(1),
    toolOrAgentUsed: z.array(z.string()).default([]),
    repositoryTouched: z.string().optional(),
    filesChanged: z.array(z.string()).default([]),
    diffSummary: z.string().optional(),
    approvalState: z.enum(["not_required", "pending", "approved", "denied", "expired"]),
    executionResult: z.enum(["success", "partial_success", "failed", "blocked"]),
    failureReason: z.string().optional(),
    testsRun: z.array(z.string()).default([]),
    pullRequestUrl: z.string().url().optional(),
    branchName: z.string().optional(),
    rollbackPath: z.string().optional(),
    retryState: z.enum(["none", "scheduled", "exhausted", "escalated"]).default("none"),
  })
  .strict();

export type WhatsAppAction = z.infer<typeof WhatsAppActionSchema>;
export type WhatsAppAttachment = z.infer<typeof WhatsAppAttachmentSchema>;
export type WhatsAppApprovalRequest = z.infer<typeof WhatsAppApprovalRequestSchema>;
export type WhatsAppExecutionLog = z.infer<typeof WhatsAppExecutionLogSchema>;
export type WhatsAppRepoChange = z.infer<typeof WhatsAppRepoChangeSchema>;

export function defaultExecutionTierForIntent(
  intentType: WhatsAppAction["intentType"],
):
  | "tier_0_log_only"
  | "tier_1_prepare"
  | "tier_2_auto_execute"
  | "tier_3_approval"
  | "tier_4_blocked" {
  switch (intentType) {
    case "informational_only":
      return "tier_0_log_only";
    case "note_to_memory":
    case "draft_content":
    case "research_request":
    case "repository_inspection":
      return "tier_1_prepare";
    case "task_creation":
    case "workflow_trigger":
    case "monitoring_request":
    case "delegation_request":
      return "tier_2_auto_execute";
    case "approval_request":
    case "direct_execution_command":
    case "repository_update_request":
    case "bug_fix_request":
    case "feature_request":
    case "branch_pr_issue_operation":
      return "tier_3_approval";
    case "unsafe_blocked":
      return "tier_4_blocked";
  }
}

export function approvalRequiredForRepoRisk(riskTier: WhatsAppRepoChange["riskTier"]): boolean {
  return riskTier === "tier_c_moderate" || riskTier === "tier_d_high";
}

export function repoChangeShouldOpenPr(riskTier: WhatsAppRepoChange["riskTier"]): boolean {
  return riskTier !== "tier_a_read";
}
