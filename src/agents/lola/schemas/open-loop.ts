export interface OpenLoop {
  id: string;
  sourceType: string;
  sourceRef: string;
  relatedPerson?: string;
  relatedCompany?: string;
  relatedProject?: string;
  summary?: string;
  owner?: string;
  dueDate?: string;
  status?: string;
  lastTouchAt?: string;
  nextTouchAt?: string;
  riskIfMissed?: string;
  sourceAgent?: string;
  approvalId?: string;
  writeStatus?: "proposed" | "approved" | "rejected" | "written";
}
