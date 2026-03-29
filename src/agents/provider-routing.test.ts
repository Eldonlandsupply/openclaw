import { describe, expect, it } from "vitest";
import type { OpenClawConfig } from "../config/config.js";
import {
  resolveDeterministicProvider,
  validateProviderRoutingConfig,
  validateProviderRuntimeSelection,
} from "./provider-routing.js";

describe("provider routing", () => {
  it("accepts minimax runtime selection with MiniMax auth", () => {
    expect(() =>
      validateProviderRuntimeSelection({
        provider: "minimax",
        baseUrl: "https://api.minimax.chat/v1",
        authSource: "env: MINIMAX_API_KEY",
      }),
    ).not.toThrow();
  });

  it("accepts openrouter runtime selection with OpenRouter auth", () => {
    expect(() =>
      validateProviderRuntimeSelection({
        provider: "openrouter",
        baseUrl: "https://openrouter.ai/api/v1",
        authSource: "env: OPENROUTER_API_KEY",
      }),
    ).not.toThrow();
  });

  it("rejects openrouter base URL for explicit minimax provider", () => {
    expect(() =>
      validateProviderRuntimeSelection({
        provider: "minimax",
        baseUrl: "https://openrouter.ai/api/v1",
        authSource: "env: MINIMAX_API_KEY",
      }),
    ).toThrow(/provider=minimax must not use OpenRouter settings/);
  });

  it("uses LLM_PROVIDER env lock when present", () => {
    const resolved = resolveDeterministicProvider({
      env: { LLM_PROVIDER: "minimax" } as NodeJS.ProcessEnv,
    });
    expect(resolved).toBe("minimax");
  });

  it("throws startup validation error for contradictory minimax/openrouter env", () => {
    const cfg = {
      agents: {
        defaults: {
          model: {
            primary: "minimax/MiniMax-M2.1",
            fallbacks: [],
          },
        },
      },
      models: {
        providers: {
          minimax: {
            baseUrl: "https://api.minimax.chat/v1",
          },
        },
      },
    } as OpenClawConfig;

    expect(() =>
      validateProviderRoutingConfig({
        cfg,
        env: { OPENROUTER_API_KEY: "sk-or-dead" } as NodeJS.ProcessEnv,
      }),
    ).toThrow(/MINIMAX_API_KEY is missing/);
  });
});
