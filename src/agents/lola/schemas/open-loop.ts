export interface OpenLoop {
  id: string;
  sourceType: string;
  sourceRef: string;
  proposedByAgent?: string;
  approvalId?: string;
  relatedPerson?: string;
  relatedCompany?: string;
  relatedProject?: string;
  summary?: string;
  owner?: string;
  dueDate?: string;
  status?: string;
  writeStatus?: "pending_approval" | "approved" | "rejected" | "applied";
  lastTouchAt?: string;
  nextTouchAt?: string;
  riskIfMissed?: string;
}
