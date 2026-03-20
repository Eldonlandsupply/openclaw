export interface InboxTriageItem {
  id: string;
  messageId: string;
  threadId?: string;
  sender: string;
  subject: string;
  receivedAt: string;
  priority?: "low" | "medium" | "high" | "urgent";
  category?: string;
  actionRequired?: boolean;
  recommendedAction?: string;
  deadline?: string;
  riskLevel?: "low" | "medium" | "high";
  draftReply?: string;
  followUpNeeded?: boolean;
  relatedPeople?: string[];
  relatedCompany?: string;
  relatedProject?: string;
  confidence?: number;
}
