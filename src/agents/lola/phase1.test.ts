import { describe, expect, it, vi } from "vitest";
import { logAction } from "./action-logger.js";
import { ApprovalEngine } from "./approval-engine.js";
import { AuditAgent } from "./audit-agent.js";
import { BriefingAgent } from "./briefing-agent.js";
import { CalendarAgent } from "./calendar-agent.js";
import { LOLA_CONFIG_DEFAULTS } from "./config/lola.config.js";
import { initializeLolaPhaseOne } from "./first-boot.js";
import { InboxAgent } from "./inbox-agent.js";
import { MemoryAgent } from "./memory-agent.js";
import { MemoryStore } from "./memory-store.js";
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
    expect(state.dashboard.approvalRequired).toBe(true);
    expect(state.dashboard).toEqual(registerLola());
    expect(state.dashboard.readOnly).toBe(false);
    expect(state.dashboard.panels).toContain("Approval queue");
    expect(state.config).toEqual(LOLA_CONFIG_DEFAULTS);

    const brief = new BriefingAgent().draftExecutiveBrief();
    expect(brief.id).toBe("phase-1-draft");

    const memory = new MemoryAgent().proposeMemoryUpdate();
    expect(memory).toEqual({ proposal: true, facts: [] });

    expect(new AuditAgent().review()).toEqual([]);
  });
  it("adds approval-backed internal write paths for phase 2", () => {
    const now = new Date("2026-03-20T00:00:00.000Z");
    const memory = new MemoryStore();
    const inboxAgent = new InboxAgent(memory);
    const calendarAgent = new CalendarAgent(memory);

    const [draft] = inboxAgent.draftFromTriaged(
      [
        {
          id: "msg-2",
          messageId: "msg-2",
          sender: "sender@example.com",
          subject: "Schedule review",
          receivedAt: now.toISOString(),
        },
      ],
      now,
    );

    const [prep] = calendarAgent.draftCalendarNotes(
      [
        {
          id: "evt-1",
          title: "Board sync",
          startAt: now.toISOString(),
          endAt: now.toISOString(),
          severity: "medium",
        },
      ],
      now,
    );

    const storedMemory = memory.writeMemory(
      {
        id: "",
        factType: "preference",
        subject: "operator",
        value: "Prefers concise updates",
        durability: "durable",
      },
      now,
    );

    const openLoop = memory.writeOpenLoop(
      {
        id: "",
        sourceType: "email",
        sourceRef: "msg-2",
        owner: "LOLA",
        dueDate: now.toISOString(),
        status: "open",
        summary: "Awaiting approval",
      },
      now,
    );

    expect(draft).toMatchObject({ status: "pending_approval", relatedIds: ["msg-2"] });
    expect(prep).toMatchObject({ status: "pending_approval", relatedIds: ["evt-1"] });
    expect(memory.listDrafts()).toHaveLength(2);
    expect(storedMemory.id).toMatch(/^mem_/);
    expect(openLoop.id).toMatch(/^ol_/);
  });

  it("tracks approvals and redacts action logs", () => {
    const approvals = new ApprovalEngine();
    const queued = approvals.enqueue({
      id: "approval-1",
      type: "draft",
      payload: { sender: "sender@example.com", subject: "Secret" },
    });

    expect(queued.status).toBe("pending");
    expect(approvals.approve("approval-1")?.status).toBe("approved");
    expect(approvals.deny("missing")).toBeUndefined();

    const spy = vi.spyOn(console, "log").mockImplementation(() => {});
    expect(logAction("draft.created", { sender: "sender@example.com", subject: "Secret" })).toBe(
      true,
    );
    expect(spy).toHaveBeenCalledWith(
      'ACTION:draft.created {"sender":"[redacted]","subject":"[redacted]"}',
    );
    spy.mockRestore();
  });
});
