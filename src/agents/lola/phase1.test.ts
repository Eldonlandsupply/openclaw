import { describe, expect, it } from "vitest";
import { AuditAgent } from "./audit-agent.js";
import { BriefingAgent } from "./briefing-agent.js";
import { LOLA_CONFIG_DEFAULTS } from "./config/lola.config.js";
import { initializeLolaPhaseOne } from "./first-boot.js";
import { InboxAgent } from "./inbox-agent.js";
import { MemoryAgent } from "./memory-agent.js";
import { LolaOrchestrator } from "./orchestrator.js";
import { registerLola } from "./register-lola.js";
import { SendGate } from "./send-gate.js";

describe("lola phase 1 scaffold", () => {
  it("keeps orchestrator deduped and queue-backed", () => {
    const orchestrator = new LolaOrchestrator();
    orchestrator.start();
    expect(orchestrator.isRunning()).toBe(true);

    expect(orchestrator.route({ id: "task-1", type: "brief" })).toBe("queued:brief");
    orchestrator.enqueue({ id: "task-1", type: "brief" });

    expect(orchestrator.next()).toEqual({ id: "task-1", type: "brief" });
    expect(orchestrator.next()).toBeUndefined();
  });

  it("fills inbox triage defaults and keeps send gate blocked", () => {
    const inboxAgent = new InboxAgent();
    const [item] = inboxAgent.triage([
      {
        id: "1",
        messageId: "msg-1",
        sender: "sender@example.com",
        subject: "Review contract",
        receivedAt: "2026-03-19T00:00:00.000Z",
      },
    ]);

    expect(item).toMatchObject({ priority: "low", confidence: 0.5 });
    expect(new SendGate().approve()).toBe(false);
    expect(new SendGate().block()).toBe(true);
  });

  it("builds read-only first boot state and placeholder outputs", () => {
    const state = initializeLolaPhaseOne();
    expect(state.externalEffectsBlocked).toBe(true);
    expect(state.dashboard).toEqual(registerLola());
    expect(state.config).toEqual(LOLA_CONFIG_DEFAULTS);

    const brief = new BriefingAgent().draftExecutiveBrief();
    expect(brief.id).toBe("phase-1-draft");

    const memory = new MemoryAgent().proposeMemoryUpdate();
    expect(memory).toEqual({ proposal: true, facts: [] });

    expect(new AuditAgent().review()).toEqual([]);
  });
});
