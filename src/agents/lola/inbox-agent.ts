import type { DraftRecord } from "./schemas/draft.js";
import type { InboxTriageItem } from "./schemas/inbox-triage.js";

export class InboxAgent {
  triage(items: InboxTriageItem[]): InboxTriageItem[] {
    return items.map((item) => ({
      ...item,
      priority: item.priority ?? "low",
      confidence: item.confidence ?? 0.5,
    }));
  }

  draftReply(item: InboxTriageItem, body: string): DraftRecord {
    return {
      id: `draft:${item.id}`,
      draftType: "reply",
      title: item.subject,
      body,
      sourceRef: item.messageId,
      sourceAgent: "inbox",
      status: "proposed",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
  }
}
