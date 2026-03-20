export interface MemoryFact {
  id: string;
  factType: string;
  subject: string;
  value: string;
  confidence?: number;
  sourceRefs?: string[];
  durability?: "ephemeral" | "session" | "durable";
  reviewStatus?: "proposed" | "approved" | "rejected";
  createdAt?: string;
  updatedAt?: string;
}
