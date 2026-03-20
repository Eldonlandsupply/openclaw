export interface ApprovalQueueItem {
  id: string;
  actionType: string;
  proposedByAgent: string;
  payloadSummary: string;
  payloadRef?: string;
  reason?: string;
  sensitivity?: "low" | "medium" | "high";
  confidence?: number;
  requiresHumanApproval?: boolean;
  status?: "pending" | "approved" | "rejected" | "expired";
  createdAt?: string;
}
