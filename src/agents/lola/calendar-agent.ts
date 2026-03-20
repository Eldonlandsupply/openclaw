import type { CalendarRiskItem } from "./schemas/calendar-risk.js";

export class CalendarAgent {
  assess(events: CalendarRiskItem[]): CalendarRiskItem[] {
    return events;
  }
}
