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

  it("routes assistant requests to Lola", () => {
    const result = evaluateTelegramIntake(ctx("Lola, what follow-ups am I missing?") as never);
    expect(result.outcome).toBe("pass");
    if (result.outcome !== "pass") {
      throw new Error("expected pass");
    }
    expect(result.route.target).toBe("lola");
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
