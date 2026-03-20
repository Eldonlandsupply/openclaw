export interface MeetingPrepPack {
  id: string;
  eventId?: string;
  title: string;
  attendees?: string[];
  purpose?: string;
  context?: string;
  objective?: string;
  openQuestions?: string[];
  materialsNeeded?: string[];
  decisionPoints?: string[];
  suggestedFollowUp?: string[];
}
