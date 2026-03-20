export interface ApprovalQueueItem {
  id: string;
  actionType: string;
  targetType?: "draft" | "memory_fact" | "open_loop" | "audit_record";
  targetId?: string;
  proposedByAgent: string;
  payloadSummary: string;
  payloadRef?: string;
  reason?: string;
  sensitivity?: "low" | "medium" | "high";
  confidence?: number;
  requiresHumanApproval?: boolean;
  status?: "pending" | "approved" | "rejected" | "expired" | "applied" | "blocked";
  createdAt?: string;
  updatedAt?: string;
  resolvedAt?: string;
  approvedAt?: string;
  decidedAt?: string;
  decidedBy?: string;
  dryRun?: boolean;
  redactionApplied?: boolean;
  outcomeRef?: string;
}
