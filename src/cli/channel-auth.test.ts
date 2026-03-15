import { beforeEach, describe, expect, it, vi } from "vitest";

const ensurePluginRegistryLoaded = vi.fn();
const normalizeChannelId = vi.fn();
const getChannelPlugin = vi.fn();
const resolveChannelDefaultAccountId = vi.fn();
const loadConfig = vi.fn();
const setVerbose = vi.fn();

vi.mock("./plugin-registry.js", () => ({ ensurePluginRegistryLoaded }));
vi.mock("../channels/plugins/index.js", () => ({
  normalizeChannelId,
  getChannelPlugin,
}));
vi.mock("../channels/plugins/helpers.js", () => ({ resolveChannelDefaultAccountId }));
vi.mock("../config/config.js", () => ({ loadConfig }));
vi.mock("../globals.js", () => ({ setVerbose }));

describe("channel-auth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadConfig.mockReturnValue({});
    normalizeChannelId.mockReturnValue("whatsapp");
  });

  it("loads plugin registry before login", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    getChannelPlugin.mockReturnValue({
      auth: { login },
    });
    resolveChannelDefaultAccountId.mockReturnValue("default");

    const { runChannelLogin } = await import("./channel-auth.js");
    await runChannelLogin({ channel: "whatsapp", verbose: true });

    expect(ensurePluginRegistryLoaded).toHaveBeenCalledTimes(1);
    expect(setVerbose).toHaveBeenCalledWith(true);
    expect(login).toHaveBeenCalledWith(
      expect.objectContaining({ accountId: "default", channelInput: "whatsapp", verbose: true }),
    );
  });

  it("loads plugin registry before logout", async () => {
    const logoutAccount = vi.fn().mockResolvedValue(undefined);
    getChannelPlugin.mockReturnValue({
      gateway: { logoutAccount },
      config: { resolveAccount: vi.fn().mockReturnValue({ id: "default" }) },
    });
    resolveChannelDefaultAccountId.mockReturnValue("default");

    const { runChannelLogout } = await import("./channel-auth.js");
    await runChannelLogout({ channel: "whatsapp" });

    expect(ensurePluginRegistryLoaded).toHaveBeenCalledTimes(1);
    expect(logoutAccount).toHaveBeenCalledWith(
      expect.objectContaining({ accountId: "default", account: { id: "default" } }),
    );
  });
});
