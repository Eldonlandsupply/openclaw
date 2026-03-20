import type { DraftRecord, MemoryStore } from "./memory-store.js";
import type { CalendarRiskItem } from "./schemas/calendar-risk.js";

export class CalendarAgent {
  constructor(private readonly memory?: MemoryStore) {}

  assess(events: CalendarRiskItem[]): CalendarRiskItem[] {
    return events;
  }

  draftCalendarNotes(events: CalendarRiskItem[], now = new Date()): DraftRecord[] {
    if (!this.memory) {
      return events.map((event) => ({
        id: event.id,
        text: `Prep for: ${event.title}`,
        status: "pending_approval",
        relatedIds: [event.id],
        createdAt: now.toISOString(),
        updatedAt: now.toISOString(),
      }));
    }

    return events.map((event) =>
      this.memory.writeDraft(
        {
          id: event.id,
          text: `Prep for: ${event.title}`,
          status: "pending_approval",
          relatedIds: [event.id],
        },
        now,
      ),
    );
  }
}
