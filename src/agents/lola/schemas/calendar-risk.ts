export interface CalendarRiskItem {
  id: string;
  eventId?: string;
  title: string;
  startAt?: string;
  endAt?: string;
  issueType?: string;
  severity?: "low" | "medium" | "high";
  whyItMatters?: string;
  recommendation?: string;
  confidence?: number;
}
