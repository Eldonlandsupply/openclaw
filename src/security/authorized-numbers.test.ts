import { describe, expect, it } from "vitest";
import {
  isAuthorizedWhatsAppCommandSender,
  resolveAuthorizedNumbersConfig,
  validateAuthorizedNumbersConfig,
} from "./authorized-numbers.js";

describe("authorized numbers", () => {
  it("matches CEO and assistant numbers after E.164 normalization", () => {
    const env = {
      LOLA_ENABLED: "true",
      WHATSAPP_CEO_PRIMARY_NUMBER: "CEO|+1 (555) 000-0001",
      WHATSAPP_AUTHORIZED_ASSISTANTS: "EA|+1 555 000 0002",
    } as NodeJS.ProcessEnv;

    const cfg = resolveAuthorizedNumbersConfig(env);
    expect(cfg.enabled).toBe(true);
    expect(cfg.entries).toHaveLength(2);

    const ceoMatch = isAuthorizedWhatsAppCommandSender({
      senderCandidates: ["whatsapp:+15550000001"],
      env,
    });
    expect(ceoMatch.authorized).toBe(true);
    expect(ceoMatch.entry?.role).toBe("ceo");
    expect(ceoMatch.entry?.label).toBe("CEO");

    const assistantMatch = isAuthorizedWhatsAppCommandSender({
      senderCandidates: ["+1-555-000-0002"],
      env,
    });
    expect(assistantMatch.authorized).toBe(true);
    expect(assistantMatch.entry?.role).toBe("assistant");
  });

  it("rejects unauthorized numbers", () => {
    const env = {
      LOLA_ENABLED: "true",
      WHATSAPP_CEO_PRIMARY_NUMBER: "+15550000001",
      WHATSAPP_ALLOWED_NUMBERS: "+15550000003|Ops",
    } as NodeJS.ProcessEnv;

    const result = isAuthorizedWhatsAppCommandSender({
      senderCandidates: ["+15550009999"],
      env,
    });

    expect(result.authorized).toBe(false);
    expect(result.reason).toMatch(/not in WHATSAPP allowed list/i);
  });

  it("fails validation when allowlist is empty or CEO is missing", () => {
    const missingCeo = {
      LOLA_ENABLED: "true",
      WHATSAPP_ALLOWED_NUMBERS: "+15550000003",
    } as NodeJS.ProcessEnv;
    expect(validateAuthorizedNumbersConfig(missingCeo).join(" ")).toMatch(
      /WHATSAPP_CEO_PRIMARY_NUMBER is required/i,
    );
  });
});
