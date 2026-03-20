import type { ApprovalQueueItem } from "./schemas/approval-queue.js";
import type { MemoryFact } from "./schemas/memory-fact.js";

export type MemoryProposal = {
  proposal: true;
  facts: MemoryFact[];
  pendingApproval?: ApprovalQueueItem;
};

export class MemoryAgent {
  proposeMemoryUpdate(
    facts: MemoryFact[] = [],
    pendingApproval?: ApprovalQueueItem,
  ): MemoryProposal {
    return { proposal: true, facts, pendingApproval };
  }
}
