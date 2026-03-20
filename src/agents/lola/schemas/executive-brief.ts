export interface ExecutiveBrief {
  id: string;
  generatedAt: string;
  dateScope: string;
  topPriorities: string[];
  calendarWatchouts: string[];
  inboxItemsNeedingAttention: string[];
  overdueFollowUps: string[];
  pendingDecisions: string[];
  risks: string[];
  recommendations: string[];
}
