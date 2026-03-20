export interface AuditRecord {
  id: string;
  auditType: string;
  finding: string;
  impact?: string;
  recommendation?: string;
  status?: "open" | "accepted" | "resolved";
  createdAt?: string;
}
