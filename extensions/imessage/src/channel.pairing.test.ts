import { PAIRING_APPROVED_MESSAGE } from "openclaw/plugin-sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { imessagePlugin } from "./channel.js";

const sendMessageIMessage = vi.fn();

vi.mock("./runtime.js", () => ({
  getIMessageRuntime: () => ({
    channel: {
      imessage: { sendMessageIMessage },
      text: { chunkText: (text: string) => [text] },
    },
  }),
}));

describe("imessagePlugin pairing notifyApproval", () => {
  beforeEach(() => {
    sendMessageIMessage.mockReset();
  });

  it("normalizes imessage-prefixed ids before notifying", async () => {
    const notifyApproval = imessagePlugin.pairing?.notifyApproval;
    if (!notifyApproval) {
      throw new Error("notifyApproval is required");
    }

    await notifyApproval({ cfg: {}, id: "imessage:+1 (555) 123-4567" });

    expect(sendMessageIMessage).toHaveBeenCalledWith(
      "imessage:+15551234567",
      PAIRING_APPROVED_MESSAGE,
    );
  });

  it("throws for invalid sender id", async () => {
    const notifyApproval = imessagePlugin.pairing?.notifyApproval;
    if (!notifyApproval) {
      throw new Error("notifyApproval is required");
    }

    await expect(notifyApproval({ cfg: {}, id: "   " })).rejects.toThrow(
      "imessage sender id is invalid",
    );
    expect(sendMessageIMessage).not.toHaveBeenCalled();
  });
});
