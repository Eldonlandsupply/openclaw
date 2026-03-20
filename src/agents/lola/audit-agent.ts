import type { AuditRecord } from "./schemas/audit-record.js";

export class AuditAgent {
  review(records: AuditRecord[] = []): AuditRecord[] {
    return records;
  }
}
