import type { DraftRecord, MemoryStore } from "./memory-store.js";
import type { InboxTriageItem } from "./schemas/inbox-triage.js";

export class InboxAgent {
  constructor(private readonly memory?: MemoryStore) {}

  triage(items: InboxTriageItem[]): InboxTriageItem[] {
    return items.map((item) => ({
      ...item,
      priority: item.priority ?? "low",
      confidence: item.confidence ?? 0.5,
    }));
  }

  draftFromTriaged(items: InboxTriageItem[], now = new Date()): DraftRecord[] {
    if (!this.memory) {
      return items.map((item) => ({
        id: item.id,
        text: `Draft for: ${item.subject}`,
        status: "pending_approval",
        relatedIds: [item.id],
        createdAt: now.toISOString(),
        updatedAt: now.toISOString(),
      }));
    }

    return items.map((item) =>
      this.memory.writeDraft(
        {
          id: item.id,
          text: `Draft for: ${item.subject}`,
          status: "pending_approval",
          relatedIds: [item.id],
        },
        now,
      ),
    );
  }
}
