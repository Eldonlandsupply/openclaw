import type { ExecutiveBrief } from "./schemas/executive-brief.js";

export class BriefingAgent {
  draftExecutiveBrief(partial: Partial<ExecutiveBrief> = {}): ExecutiveBrief {
    return {
      id: partial.id ?? "phase-1-draft",
      generatedAt: partial.generatedAt ?? new Date(0).toISOString(),
      dateScope: partial.dateScope ?? "daily",
      topPriorities: partial.topPriorities ?? [],
      calendarWatchouts: partial.calendarWatchouts ?? [],
      inboxItemsNeedingAttention: partial.inboxItemsNeedingAttention ?? [],
      overdueFollowUps: partial.overdueFollowUps ?? [],
      pendingDecisions: partial.pendingDecisions ?? [],
      risks: partial.risks ?? [],
      recommendations: partial.recommendations ?? [],
    };
  }
}
