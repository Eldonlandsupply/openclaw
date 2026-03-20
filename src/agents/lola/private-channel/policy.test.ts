import { describe, expect, it } from "vitest";
import type { LolaPrivateInboundMessage } from "./types.js";
import {
  canAutoExecute,
  classifyLolaMessage,
  deriveTrustTier,
  shouldRequireApproval,
} from "./policy.js";

const baseMessage: LolaPrivateInboundMessage = {
  id: "msg-1",
  channel: "whatsapp",
  senderId: "+15551234567",
  senderE164: "+15551234567",
  trustedSender: true,
  threadId: "thread-1",
  text: "Summarize my priorities today",
  receivedAt: "2026-03-20T00:00:00.000Z",
};

describe("lola private-channel policy", () => {
  it("blocks unknown senders by default", () => {
    expect(deriveTrustTier({ trustedSender: false })).toBe("blocked");
  });

  it("requires approval for send actions", () => {
    expect(
      shouldRequireApproval({
        intent: "email_send",
        confidence: 0.99,
        text: "Approve and send",
        risk: "high",
      }),
    ).toBe(true);
  });

  it("keeps simple status requests auto-executable for trusted senders", () => {
    const classification = classifyLolaMessage({
      message: baseMessage,
      intent: "status_request",
      confidence: 0.97,
    });
    expect(classification).toMatchObject({ risk: "low", requiresApproval: false });
    expect(canAutoExecute({ trustTier: "trusted", classification })).toBe(true);
  });

  it("forces approval for ambiguous commands", () => {
    const classification = classifyLolaMessage({
      message: { ...baseMessage, text: "Handle that for approval" },
      intent: "command",
      confidence: 0.7,
    });
    expect(classification.requiresApproval).toBe(true);
    expect(canAutoExecute({ trustTier: "trusted", classification })).toBe(false);
  });
});
