export interface MemoryFact {
  id: string;
  factType: string;
  subject: string;
  value: string;
  proposedByAgent?: string;
  approvalId?: string;
  confidence?: number;
  sourceRefs?: string[];
  durability?: "ephemeral" | "session" | "durable";
  reviewStatus?: "proposed" | "approved" | "rejected" | "written";
  writeStatus?: "pending_approval" | "approved" | "rejected" | "applied" | "written";
  sourceAgent?: string;
  redactionApplied?: boolean;
  createdAt?: string;
  updatedAt?: string;
}
