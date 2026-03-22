import { beforeEach, describe, expect, it, vi } from "vitest";
import { checkInboundAccessControl } from "./access-control.js";

const loadConfigMock = vi.fn();
const readChannelAllowFromStoreMock = vi.fn();
const upsertChannelPairingRequestMock = vi.fn();

vi.mock("../../config/config.js", () => ({
  loadConfig: () => loadConfigMock(),
}));

vi.mock("../../pairing/pairing-store.js", () => ({
  readChannelAllowFromStore: (...args: unknown[]) => readChannelAllowFromStoreMock(...args),
  upsertChannelPairingRequest: (...args: unknown[]) => upsertChannelPairingRequestMock(...args),
}));

describe("WhatsApp group allowFrom overrides", () => {
  beforeEach(() => {
    loadConfigMock.mockReset();
    readChannelAllowFromStoreMock.mockReset();
    upsertChannelPairingRequestMock.mockReset();
    readChannelAllowFromStoreMock.mockResolvedValue([]);
    upsertChannelPairingRequestMock.mockResolvedValue({
      code: "PAIR",
      created: true,
    });
  });

  it("allows a sender listed in the group-specific allowFrom override", async () => {
    loadConfigMock.mockReturnValue({
      channels: {
        whatsapp: {
          allowFrom: ["+15550000000"],
          groupPolicy: "allowlist",
          groupAllowFrom: ["+15559999999"],
          groups: {
            "120363022222222222@g.us": {
              allowFrom: ["+15551234567"],
            },
          },
        },
      },
    });

    const result = await checkInboundAccessControl({
      accountId: "default",
      from: "120363022222222222@g.us",
      selfE164: "+15550000000",
      senderE164: "+15551234567",
      group: true,
      isFromMe: false,
      sock: { sendMessage: vi.fn() },
      remoteJid: "120363022222222222@g.us",
    });

    expect(result.allowed).toBe(true);
  });

  it("blocks a sender not listed in the group-specific allowFrom override", async () => {
    loadConfigMock.mockReturnValue({
      channels: {
        whatsapp: {
          allowFrom: ["+15550000000"],
          groupPolicy: "allowlist",
          groupAllowFrom: ["+15551234567"],
          groups: {
            "120363022222222222@g.us": {
              allowFrom: ["+15557654321"],
            },
          },
        },
      },
    });

    const result = await checkInboundAccessControl({
      accountId: "default",
      from: "120363022222222222@g.us",
      selfE164: "+15550000000",
      senderE164: "+15551234567",
      group: true,
      isFromMe: false,
      sock: { sendMessage: vi.fn() },
      remoteJid: "120363022222222222@g.us",
    });

    expect(result.allowed).toBe(false);
  });
});
