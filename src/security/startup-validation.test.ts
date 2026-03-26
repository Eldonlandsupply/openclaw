import { describe, expect, it } from "vitest";
import { validateSecurityStartupEnv } from "./startup-validation.js";

describe("security startup validation", () => {
  it("fails fast when LOLA Graph is enabled without required secrets", () => {
    const env = {
      LOLA_ENABLED: "true",
      LOLA_EXTERNAL_ACTIONS_ENABLED: "true",
      WHATSAPP_CEO_PRIMARY_NUMBER: "+15550000001",
    } as NodeJS.ProcessEnv;

    expect(() => validateSecurityStartupEnv(env)).toThrow(/Microsoft Graph is enabled/i);
  });

  it("accepts alias M365_* variables and encrypted token cache path", () => {
    const env = {
      LOLA_ENABLED: "true",
      WHATSAPP_CEO_PRIMARY_NUMBER: "+15550000001",
      M365_TENANT_ID: "tenant-id",
      M365_CLIENT_ID: "client-id",
      M365_CLIENT_SECRET: "top-secret",
      M365_USER_EMAIL: "ceo@example.com",
      M365_TOKEN_CACHE_FILE: "/secure/state/m365/token-cache.enc.json",
    } as NodeJS.ProcessEnv;

    expect(() => validateSecurityStartupEnv(env)).not.toThrow();
  });

  it("fails loudly when Lola Telegram bridge is enabled without required env", () => {
    const env = {
      LOLA_TELEGRAM_ENABLED: "true",
      TELEGRAM_MODE: "webhook",
    } as NodeJS.ProcessEnv;

    expect(() => validateSecurityStartupEnv(env)).toThrow(/LOLA Telegram bridge is enabled/i);
    expect(() => validateSecurityStartupEnv(env)).toThrow(/TELEGRAM_WEBHOOK_URL/);
  });
});
