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
  reviewStatus?: "proposed" | "approved" | "rejected";
  writeStatus?: "pending_approval" | "approved" | "rejected" | "applied";
  createdAt?: string;
  updatedAt?: string;
}
