import type { OpenClawConfig } from "../config/config.js";
import { DEFAULT_MODEL, DEFAULT_PROVIDER } from "./defaults.js";
import {
  normalizeProviderId,
  parseModelRef,
  resolveConfiguredModelRef,
} from "./model-selection.js";

const OPENROUTER_HOST = "openrouter.ai";

export function resolveDeterministicProvider(params: {
  env?: NodeJS.ProcessEnv;
}): string | undefined {
  const env = params.env ?? process.env;
  const explicit = normalizeProviderId(String(env.LLM_PROVIDER ?? "").trim());
  if (explicit) {
    return explicit;
  }
  return undefined;
}

export function filterProviderFallbacks<T extends { provider: string }>(params: {
  candidates: T[];
  enforcedProvider?: string;
}): T[] {
  const enforced = normalizeProviderId(String(params.enforcedProvider ?? "").trim());
  if (!enforced) {
    return params.candidates;
  }
  return params.candidates.filter(
    (candidate) => normalizeProviderId(candidate.provider) === enforced,
  );
}

export function validateProviderRuntimeSelection(params: {
  provider: string;
  baseUrl?: string;
  authSource?: string;
}): void {
  const provider = normalizeProviderId(params.provider);
  const baseUrl = String(params.baseUrl ?? "")
    .trim()
    .toLowerCase();
  const authSource = String(params.authSource ?? "")
    .trim()
    .toUpperCase();

  const baseUrlUsesOpenRouter = baseUrl.includes(OPENROUTER_HOST);
  const authUsesOpenRouter = authSource.includes("OPENROUTER_API_KEY");
  const authUsesMiniMax = authSource.includes("MINIMAX_API_KEY");

  if (provider === "minimax" && (baseUrlUsesOpenRouter || authUsesOpenRouter)) {
    throw new Error(
      `Invalid provider routing: provider=minimax must not use OpenRouter settings (baseUrl=${params.baseUrl ?? "(none)"}, authSource=${params.authSource ?? "(none)"}).`,
    );
  }

  if (provider === "openrouter" && authUsesMiniMax) {
    throw new Error(
      `Invalid provider routing: provider=openrouter must not use MINIMAX_API_KEY (authSource=${params.authSource ?? "(none)"}).`,
    );
  }
}

export function validateProviderRoutingConfig(params: {
  cfg: OpenClawConfig;
  env?: NodeJS.ProcessEnv;
}): void {
  const env = params.env ?? process.env;
  const primary = resolveConfiguredModelRef({
    cfg: params.cfg,
    defaultProvider: DEFAULT_PROVIDER,
    defaultModel: DEFAULT_MODEL,
  });
  const primaryProvider = normalizeProviderId(primary.provider);

  if (primaryProvider === "minimax") {
    const fallbacks =
      (typeof params.cfg.agents?.defaults?.model === "object"
        ? params.cfg.agents?.defaults?.model?.fallbacks
        : undefined) ?? [];
    for (const fallback of fallbacks) {
      const parsed = parseModelRef(String(fallback ?? ""), primaryProvider);
      if (!parsed) {
        continue;
      }
      if (normalizeProviderId(parsed.provider) !== "minimax") {
        throw new Error(
          `Invalid fallback configuration: primary provider is minimax, but fallback "${fallback}" routes to ${parsed.provider}.`,
        );
      }
    }

    const minimaxBaseUrl =
      params.cfg.models?.providers?.minimax?.baseUrl ??
      params.cfg.models?.providers?.["minimax-portal"]?.baseUrl;
    validateProviderRuntimeSelection({ provider: "minimax", baseUrl: minimaxBaseUrl });

    const hasMinimax = Boolean(String(env.MINIMAX_API_KEY ?? "").trim());
    const hasOpenRouter = Boolean(String(env.OPENROUTER_API_KEY ?? "").trim());
    if (!hasMinimax && hasOpenRouter) {
      throw new Error(
        "Invalid provider config: primary provider is minimax but MINIMAX_API_KEY is missing while OPENROUTER_API_KEY is set.",
      );
    }
  }
}
