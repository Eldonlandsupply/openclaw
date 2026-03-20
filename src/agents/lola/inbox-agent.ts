import type { InboxTriageItem } from "./schemas/inbox-triage.js";

export class InboxAgent {
  triage(items: InboxTriageItem[]): InboxTriageItem[] {
    return items.map((item) => ({
      ...item,
      priority: item.priority ?? "low",
      confidence: item.confidence ?? 0.5,
    }));
  }
}
