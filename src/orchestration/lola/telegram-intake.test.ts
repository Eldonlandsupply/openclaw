import { describe, expect, it, beforeEach } from "vitest";
import { resetTelegramApprovalsForTest } from "./telegram-approvals.js";
import { evaluateTelegramIntake } from "./telegram-intake.js";

type FakeCtx = {
  message: {
    text?: string;
    caption?: string;
    from?: { id?: number };
    chat: { id: number };
    message_id: number;
    date?: number;
    reply_to_message?: { message_id?: number };
  };
  update?: { update_id?: number; message?: unknown };
};

function ctx(text: string, userId = 1001, chatId = 2001): FakeCtx {
  return {
    message: {
      text,
      from: { id: userId },
      chat: { id: chatId },
      message_id: 3001,
      date: 1_700_000_000,
    },
    update: { update_id: 4001, message: {} },
  };
}

describe("lola telegram intake", () => {
  beforeEach(() => {
    resetTelegramApprovalsForTest();
    process.env.TELEGRAM_ALLOWED_USER_IDS = "1001";
    process.env.TELEGRAM_ALLOWED_CHAT_IDS = "2001";
    delete process.env.GITHUB_TOKEN;
    delete process.env.GH_TOKEN;
    delete process.env.COPILOT_GITHUB_TOKEN;
    delete process.env.ATTIO_API_KEY;
    delete process.env.LOLA_M365_GRAPH_ACCESS_TOKEN;
    delete process.env.LOLA_M365_CLIENT_ID;
    delete process.env.LOLA_M365_CLIENT_SECRET;
    delete process.env.LOLA_M365_TENANT_ID;
    delete process.env.M365_CLIENT_ID;
    delete process.env.M365_CLIENT_SECRET;
    delete process.env.M365_TENANT_ID;
  });

  it("rejects unauthorized users", () => {
    const result = evaluateTelegramIntake(ctx("hello", 9999, 2001) as never);
    expect(result.outcome).toBe("blocked");
  });

  it("accepts authorized users", () => {
    const result = evaluateTelegramIntake(ctx("Lola, what follow-ups am I missing?") as never);
    expect(result.outcome).toBe("pass");
  });

  it("rejects unauthorized chats when chat allowlist is enabled", () => {
    const result = evaluateTelegramIntake(ctx("hello", 1001, 9999) as never);
    expect(result.outcome).toBe("blocked");
  });

  it("routes engineering requests to CTO", () => {
    const result = evaluateTelegramIntake(
      ctx("Check the repo health and send CTO anything failing.") as never,
    );
    expect(result.outcome).toBe("pass");
    if (result.outcome !== "pass") {
      throw new Error("expected pass");
    }
    expect(result.route.target).toBe("cto");
  });

  it("routes operations requests to workflow runner", () => {
    const result = evaluateTelegramIntake(ctx("Lola, what follow-ups am I missing?") as never);
    expect(result.outcome).toBe("pass");
    if (result.outcome !== "pass") {
      throw new Error("expected pass");
    }
    expect(result.route.target).toBe("workflow_runner");
    expect(result.route.intent).toBe("operations");
  });

  it("routes generic questions to conversational path", () => {
    const result = evaluateTelegramIntake(ctx("Summarize this thread for me.") as never);
    expect(result.outcome).toBe("pass");
    if (result.outcome !== "pass") {
      throw new Error("expected pass");
    }
    expect(result.route.target).toBe("lola");
    expect(result.route.intent).toBe("communication");
  });

  it("returns exact blocker when engineering executor dependency is missing", () => {
    const result = evaluateTelegramIntake(ctx("Open a GitHub pull request for this fix.") as never);
    expect(result.outcome).toBe("handled");
    if (result.outcome !== "handled") {
      throw new Error("expected handled");
    }
    expect(result.responseText).toContain("requires GITHUB_TOKEN");
  });

  it("does not use powerless default refusal language", () => {
    const result = evaluateTelegramIntake(ctx("Open a GitHub pull request for this fix.") as never);
    if (result.outcome !== "handled") {
      throw new Error("expected handled");
    }
    const lowered = result.responseText.toLowerCase();
    expect(lowered).not.toContain("i cannot");
    expect(lowered).not.toContain("text-based routing");
  });

  it("blocks high-risk destructive actions", () => {
    const result = evaluateTelegramIntake(ctx("Run rm -rf on the server") as never);
    expect(result.outcome).toBe("blocked");
  });

  it("requires explicit approval for tier 2 actions", () => {
    const initial = evaluateTelegramIntake(ctx("Send that email now.") as never);
    expect(initial.outcome).toBe("handled");

    const pending = evaluateTelegramIntake(ctx("what is pending?") as never);
    expect(pending.outcome).toBe("handled");
    if (pending.outcome !== "handled") {
      throw new Error("expected handled");
    }
    expect(pending.responseText).toContain("Pending approvals");
  });

  it("runs tier 2 action after explicit approval", () => {
    const initial = evaluateTelegramIntake(ctx("Send that email now.") as never);
    expect(initial.outcome).toBe("handled");

    const pending = evaluateTelegramIntake(ctx("what is pending?") as never);
    if (pending.outcome !== "handled") {
      throw new Error("expected handled");
    }
    const id = /• ([a-z0-9]{8}):/.exec(pending.responseText)?.[1];
    expect(id).toBeTruthy();

    const approved = evaluateTelegramIntake(ctx(`approve ${id}`) as never);
    expect(approved.outcome).toBe("pass");
  });

  it("returns response text for /help", () => {
    const result = evaluateTelegramIntake(ctx("/help") as never);
    expect(result.outcome).toBe("handled");
    if (result.outcome !== "handled") {
      throw new Error("expected handled");
    }
    expect(result.responseText).toContain("Commands");
  });
});
