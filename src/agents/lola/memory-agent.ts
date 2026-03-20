import type { MemoryFact } from "./schemas/memory-fact.js";

export type MemoryProposal = {
  proposal: true;
  facts: MemoryFact[];
};

export class MemoryAgent {
  proposeMemoryUpdate(facts: MemoryFact[] = []): MemoryProposal {
    return { proposal: true, facts };
  }
}
