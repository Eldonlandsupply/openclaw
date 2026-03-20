export interface DraftRecord {
  id: string;
  draftType: "reply" | "brief" | "followup" | "note";
  title: string;
  body: string;
  sourceRef?: string;
  sourceAgent?: string;
  approvalId?: string;
  status?: "proposed" | "approved" | "rejected" | "written";
  createdAt?: string;
  updatedAt?: string;
}
